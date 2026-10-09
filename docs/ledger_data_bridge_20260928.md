# C 线：契约层（事实账本 / 数据桥 / 观测快照 / 发布包）

日期：2026-09-28｜智能体 C｜状态措辞：**已实现 + 回放通过**（合成账本、mock driver、临时
registry），未接真机、未接真实训练、未用真实 rollout 验证。

## 0. 分工与写入范围

三条线并行，写入范围互不重叠：

| 线 | 在做什么 | 写入范围 |
| --- | --- | --- |
| A | 官方 LeRobot ACT：v3.0 数据集 + `lerobot-train` 两 lr 臂 | `/root/venvs/lerobot_act`、`runs/infra/lerobot_act_lift_v30/`、`scripts/build_lerobot_act_dataset.py` |
| B | 自研 MLP ACT 欠拟合判定 + minibatch 重训 + 真值/flick 门禁 | `scripts/b_*.py`、`runs/infra/b_*/` |
| **C** | **契约层：事实账本、四种训练视图、观测快照存储、发布包身份、参考 learner** | `harness/ledger.py`、`harness/obs_store.py`、`harness/data_bridge.py`、`harness/queue_td_learner.py`、`registry/release_bundle.py`、`scripts/selfcheck_{ledger_views,obs_store,release_bundle}.py`、`scripts/c_*.py`、`runs/infra/c_*` |

选这一层的依据：`docs/baseline_gap_analysis_20260924.md` 的 P0/P1 缺口表指出，当前代码
"可以回答这一局成不成功，但不能重建真实 TD"，且 `registry/publish.py` 只发布 checkpoint、
缺 `ReleaseBundle`/`DeploymentManifest`。v4 附录 01 §5.1 要求的五类长期数据对象此前只有
`harness/contracts.py` 的**内存态** `ReplayDriver`，没有持久账本、没有派生视图、没有观测身份、
没有发布身份。A、B 任一条线拿到 controlled 成功之后，下一步都是 BC＋RL 与晋级发布，
这四件事都只能由这一层给出。

## 1. 交付内容

### 1.1 `harness/ledger.py` —— 只存物理事实，不含训练语义

| 表 | 对应契约对象 | 关键列 |
| --- | --- | --- |
| `frame_fact` | 真实执行日志 | `abs_frame` / `abs_time_ns` / `chunk_id`（来源 request）/ `chunk_index`（原 chunk 绝对索引）/ `proposed_action` / `a_rl` / `driver_command` / `measured_state` / `obs_ref` / `lease_generation` / `execution_status` |
| `schedule_event` | 真实调度事件 | `kind ∈ {request_received, request_admitted, result_committed, physical_activated, partially_executed, cancelled, expired, takeover, goal_switch, version_switch, ...}` |
| `proposal_label` | 纠正标签池 | `admitted`（真实接纳 / 影子查询分开）、`valid_indices`、`quality`、`observation_ref` |
| `label_record` | 标签账本 | `label_kind ∈ {reward, progress, success, quality, unknown, revoke}`、`reward_state ∈ {pending, final, unknown}`、`rubric_version` |
| `view_manifest` | 训练视图 manifest | 由 `data_bridge.write_manifests()` 写入，含 `source_seqs` / `affected_requests`，供撤销反查 |

三条硬约束的实现方式：

1. **迟到标签不改写物理事实**：四张事实表各挂 `BEFORE UPDATE` / `BEFORE DELETE` 触发器，
   改写直接 `RAISE(FAIL, '... is append-only')`；撤销走 `revoke_label()` 追加 `revoke` 行，
   `revocation_impact()` 沿 manifest 反查受影响视图。
2. **四种动作量分开存**：`proposed_action` / `a_rl` / `driver_command` / `measured_state`
   各占一列，实测位移无处可倒填（附录 01 §2.1）。
3. **不用 `executed_length`**：逐帧存 `chunk_id + chunk_index`，块级只保留生效索引集合（§2.2）。

`ingest_runtime_result()`（`harness/ledger.py:359`）把既有 `harness/runtime_adapter.py` 的
`RuntimeResult` 事件原样落账本（只读消费，**没有修改** `contracts.py` / `runtime_adapter.py`）：
requested→`request_received`、accepted→`request_admitted`、committed→`result_committed`、
activated→`physical_activated`；`OutcomeEvent` 拆成一行帧事实 + 一条奖励标签。

### 1.2 `harness/obs_store.py` —— 内容寻址观测快照 + 表征版本冻结

补附录 01 §2.3 / §5.1 的两条要求：

- **观测时刻可解释**：每条快照记 `sampled_at_ns`、`decided_at_ns`、`source_clock`、
  `sync_error_ns`；`reuse_as()` 在超龄或超同步容差时抛 `StaleObservation`，
  `put()` 拒绝把同一份内容重打时间戳当成新观察。
- **表征缓存不能伪装成新表征**：每条快照绑定 `representation_version` / `normalizer_hash` /
  `features_version`；同一份内容被标成两个表征版本直接抛 `RepresentationMismatch`。
  原始数组按 sha256 存 `<root>/blobs/<aa>/<sha>.npz`，保留原样以便日后重算表征。

### 1.3 `harness/data_bridge.py` —— 从账本派生四种视图

`build_slots()`（`harness/data_bridge.py:146`）按附录 02 §1 的时间轴重组决策槽：槽 k 在 `t_k`
接纳 request；本槽物理执行的 C 是**上一个** request 的 U（`chunk_id=R_{k-1}`、
`chunk_index ∈ [n,2n)`）；本槽提交的 `U_k` 在 `[t_k+n, t_k+2n)` 生效。
`build_views()`（`harness/data_bridge.py:310`）给出 **td / bc / candidate / isolated** 四视图，
外加 `pending`（未定稿，不发布也不置零）。

| 规则 | 实现 |
| --- | --- |
| `γ_slot=γ^n` 只算一次并存下 | `SlotFacts.gamma_slot` |
| `R_k=Σγ^j r` 由旧 C 产生，覆盖 `[t_k, t_k+n)` | `slot_return()` |
| `y=R_k+γ^n·bootstrap_valid·Q_target(X_next,π_target(X_next))` | `td_target()` / `TrainingSample.target()` |
| Q 的动作梯度只经 E 段 `[n,2n)` | `e_segment_mask()` → `q_action_gradient_mask` |
| 终局 L≤n：无 bootstrap、保留原在途 U、不重新查询场景 | `_classify()` + `TERMINATED_KINDS` |
| 终局但 U 不可得：记 unknown，不伪造动作，终局事实保留 | `terminal_u_unknown` |
| 外部截断不冒充 `done=1` | `TRUNCATED_KINDS` + `truncated_without_next_snapshot` |
| 抢占槽隔离；只有边界快照不可确认才连前驱一起隔离，范围只限不可确认区间 | `build_views()` 的 `extra_reasons` |
| 下一槽被抢占不改写已成立的前一步（`C_next` 仍是当时的 U，逐值比对） | `next_queue_matches_u` |
| deadline miss / 换 goal 或 epoch 不相容 → 拒绝 | `deadline_miss` / `goal_epoch_mismatch` / `next_goal_switch` |
| C 段"发出去但无回执"不算普通样本 | `c_not_executed` |
| 观测超龄或缺决策时刻 → 隔离而不是猜 | `observation_stale` / `observation_age_unknown` |
| 一个视图混两个表征/归一化版本 → 冻结视图 | `stats["view_frozen"]` + `view_frozen_reasons` |
| 删失比例必须报告，不宣称自动无偏 | `compute_stats()["censoring_ratio"]` |
| 双向覆盖分别记账 | `compute_stats()["td_per_goal"]` |

`resolve_x()` 把样本的 `x_ref` 解析回原始观测数组；未接 `obs_store` 时 `x_ref` 退回旧的
`"<episode>#<frame>"` 口径，既有行为逐字不变。

### 1.4 `registry/release_bundle.py` —— 发布身份与原子换版

对应附录 01 §6（B5）。与既有 `registry/publish.py`（技能版本 + 门禁判定，写
`registry/<skill>/<version>/` 与 `current.json`）互不覆盖：本层写
`registry/<skill>/bundles/<bundle_id>/manifest.json` 与 `registry/<skill>/deployment/`。

- **内容身份而非路径身份**：`file_component()` / `inline_component()` 一律按 sha256 记身份；
  `verify_bundle()` 重新核对磁盘内容，抓"只换权重不换预处理"和文件被偷换。
- **必须绑定全部组件**：`REQUIRED_ROLES` 14 项（policy、q、q_target、optimizer、obs_pipeline、
  normalizer、action_contract、schedule_config、task_contract、harness_programs、gpt_rubric、
  reward_view、replay_index、eval_protocol）。缺就抛 `MissingComponent`；确实没有必须显式写进
  `waive_roles`，豁免会记进 manifest，不能静默省略。
- **同一 checkpoint 双向通过后整体发布**：缺方向、某方向未通过、方向间 `checkpoint_sha256`
  不一致（= 分方向各挑最优）、评测协议不一致，全部抛 `BidirectionalViolation`。
- **禁止 chunk 中途热换权重**：`activate_bundle(slot_boundary_confirmed=False)` 抛
  `MidChunkSwapRefused`；换版走临时文件 + `os.replace` 的整体边界替换，`generation` 递增、
  记 `previous_bundle_id` 与 `lease_generation`，历史追加进 `deployment/history.jsonl`。
- **回滚要有身份与原因**：`rollback()` 无原因直接拒；回滚同样过内容身份核对。
- **污染可暂停晋级**：`record_contamination()` 追加撤销记录并把 bundle 列入
  `deployment/paused.json`，之后 `activate_bundle()` 抛 `ContaminatedBundle`。

### 1.5 `harness/data_bridge.py::export_views / load_views` —— 视图分片（09-28 追加）

视图停在内存里等于没有：learner（RLinf / LeRobot）跑在另一个进程、另一套依赖里，它只应该
读到「已经定资格、定 mask、定 `label_version`」的行，而不是自己再 join 一次账本 ——
否则资格判定会在两处各写一遍并悄悄分叉。三条导出纪律：

1. **五个视图各自一个文件，永不合并**（`td/bc/candidate/isolated/pending`）。空视图也落
   0 行文件，让 learner 能分清「这一轮没有合格样本」和「忘了导」。
2. **只导 `x_ref`，不导表征**。需要数组时 learner 自己 `resolve_x()` 重算；把缓存好的表征
   导出去让别人当新表征用，正是附录 01 §5.1 禁止的那件事。每行带 `representation_version`，
   learner 可以据此拒绝混版本批次。
3. **带内容身份**。`manifest.json` 记每个分片的 sha256、行数与列序，`load_views(verify=True)`
   重新核对，对不上抛 `ViewExportTampered`；parquet 读回的 NaN 一律还原成 `None`，
   避免「`r_slot` 未知」被下游读成 0.0。

格式 `parquet`（默认）或 `jsonl`（无 pyarrow 时的兜底）；变长字段（动作块、四种 mask、
`isolation_reasons`、`source_seqs`）统一存 JSON 文本，schema 不随 `n`/`H` 变。

### 1.6 `harness/queue_td_learner.py` —— 参考 learner（09-28 追加）

分片导出后一直没有任何进程真读过它，附录 02 §3 的学习目标也就一直只有公式和合成自检。
这个模块是那条路径的**最小真实调用方**：

```
load_views(dir) → ShardBatch(张量) → td_targets() / train_steps() → 参数真的动了
```

**它不是能力主张，也不替代 RLinf / LeRobot。** 十几条 TD 样本 + 3 步更新 + 小 MLP，
跑出来的成功率没有任何意义；它验的是接线与数值语义。三条硬约束（违反即抛 `LearnerRefused`，
不静默降级）：

1. 只有 `td / bc` 两个视图能进梯度；`isolated / pending / candidate` 计数后丢弃 ——
   把「不确定」当「失败」训正是附录 02 §7 禁止的那件事。
2. Q 的动作梯度只经 E 段。C 段进网络前就是分片常量（`requires_grad=False`），
   H>2n 的 D 段补零；分片里的 `q_action_gradient_mask` 与 `e_segment_mask(H,n)` 不一致就拒绝启动。
3. 不重写公式。TD 目标逐行调 `data_bridge.td_target()`，`γ_slot` 用分片里的值（= γ^n，
   只乘一次，learner 侧不再自乘），终局槽 `bootstrap_valid=False` ⇒ 无 bootstrap。

首版明确不做：SAC 的 `log_pi`／熵温度／entropy backup（附录 01 T36：确定性完整头用本文
Q＋BC 目标，也不许填假概率去骗 worker 签名）；ξ 只有一位（决策时是否有承诺队列在生效）；
优先级采样、多步回报、分布式 critic、自适应 BC 权重（调研报告 §9.3）。

两个**已知近似**写在 `notes` 里随行带出，不藏在代码注释里：

- BC 行的 C 无法从分片重建（纠正帧没有前后槽链），首版按 `C=0, has_c=0` 处理。
  等 harness 纠正也走 request/commit 后可精确重建。
- 终局槽 `next_x_ref=None`（它没有下一帧）：不 bootstrap ⇒ Q̄ 项不进 `y`，所以 `next_state`
  用零占位。但**声明要 bootstrap 却缺 `next_x_ref`** 是另一回事，一律拒绝 ——
  拿零向量冒充 `h_{t_k+n}` 会凭空造出一个后继价值。

## 2. 验收

```bash
/root/venvs/rlrobot/bin/python scripts/selfcheck_ledger_views.py     # 83/83 PASS
/root/venvs/rlrobot/bin/python scripts/selfcheck_obs_store.py        # 30/30 PASS
/root/venvs/rlrobot/bin/python scripts/selfcheck_release_bundle.py   # 27/27 PASS
MUJOCO_GL=egl /root/venvs/rlrobot/bin/python scripts/c_contract_lift_smoke.py          # 14/14 PASS
MUJOCO_GL=egl /root/venvs/rlrobot/bin/python scripts/c_contract_lift_takeover_smoke.py # 28/28 PASS
MUJOCO_GL=egl /root/venvs/rlrobot/bin/python scripts/c_learner_shard_smoke.py          # 40/40 PASS
```

| 自检 | 覆盖 |
| --- | --- |
| `selfcheck_ledger_views.py` | 附录 02 §9 六个手核算例逐条落地（例1 三段与一槽 TD、例2 Q 对 C/D 段预测的导数为 0 **且探针可证伪**、例3 `0.9^2=0.81` 与前驱 `0.9^8` 传回、例4 影子建议 vs 真实接纳、例5 帧 108 抢占与边界不可确认变体、例6 晚到 miss deadline 与换向）+ 15 条资格回归（含撤销使视图失效）+ 19 条导出/读回往返（parquet 与 jsonl 两种格式）+ 1 条 RuntimeAdapter 集成 |
| `selfcheck_obs_store.py` | 内容寻址去重、拒绝重打时间戳、超龄/超同步容差拒绝、表征与 normalizer 混用冻结视图、`x_ref` 反查回原始数组、未接 store 时旧口径不变 |
| `selfcheck_release_bundle.py` | 内容身份 vs 路径身份、组件绑定与显式豁免、双向发布四条红线、manifest 幂等、槽边界拒绝热换、内容漂移拒绝激活、回滚代次与原因、污染暂停晋级、真实 `registry/` 未被写入 |
| `c_contract_lift_smoke.py` | **真实 robosuite Lift 帧**（scripted teacher 重放，46 帧）走完整契约层：`R_k` 手算复现零 mismatch、`C_next=U` 在非终局槽逐值成立、`x_ref` 反查回逐位相同的观测、普通 TD 里每一行 U 都是完整 n 段、尾槽 U 不完整时隔离而非补帧伪造、终局事实仍保留（`terminated/success` + 真实 `R_L`）、无接管时删失为 0、表征版本单一、观测超龄时 12/12 全隔离 |
| `c_contract_lift_takeover_smoke.py` | 同一局真实帧的三条通道：`clean` 基线 / `takeover`（帧 18 harness 兜底接管）/ `late_labels`（两帧 pending + 一帧 final 事后撤销）。验抢占槽与前驱双双隔离、租约代次变化、接管后不再接纳策略请求、28 条纠正帧**只**进 BC 且监督目标取自 `driver_command`、pending 不置零不进 TD、撤销使整槽退回 unknown；并把三通道的视图导出成分片后按内容身份读回 |
| `c_learner_shard_smoke.py` | **参考 learner 真读一次导出的分片**（§1.6）。三条通道：`clean` / `takeover`（真实帧，n=4/γ=0.99/H=2n）+ `terminal`（合成时间轴，n=6/γ=0.9/**H=3n**，让 D 段真实存在）。验：used 与视图行数一致、`isolated/pending/candidate` 零行进梯度、Q 的动作梯度只经 E 段（**含可证伪对照**）、`γ_slot=γ^n` 只乘一次、逐行 `y` 与手算一致、`C_{k+1}=U_k` 与 `C_k=U_{k-1}` 逐值成立、终局槽 `y=R_{k,L}=0.81` 无 bootstrap、BC 只落监督位且目标取自 `driver_command`、参数真的更新且损失有限、四条拒绝路径（篡改/`n` 不符/混表征/观测反查不到）+ 两条新增（短缺 U、谎称可 bootstrap）、全程 `torch.cuda` 未初始化 |

产物：`runs/infra/c_ledger_selfcheck.json`、`c_obs_selfcheck.json`、`c_release_selfcheck.json`、
`c_lift_contract_smoke.json`、`c_lift_takeover_smoke.json`、`c_learner_shard_smoke.json`；
可复查的账本/快照/临时 registry 在 `runs/infra/c_*/<时间戳>/`（账本 append-only，所以每次跑
用独立子目录，避免叠加旧事实）。

既有自检全部重跑未受影响：`selfcheck_harness_contracts.py` 6/6、`selfcheck_runtime_adapter.py` 6/6、
`selfcheck_stage3.py` 16 项全部通过。

真实帧 smoke 的可复现性：robosuite 升回 1.5.2 后连跑两次 `steps=46 / n_td=12` 完全一致
（1.5.1 时期同一脚本连跑四次是 47/46/51/48 帧，见 §8）。**`n_td` 现已按 §7 缺陷 5 变为 10**：
尾槽 R010/R011 的 U 拼不满 n 行，按契约隔离而不是补帧，见 §6.1。

## 3. 明确不算通过的部分

- 六算例跑在**合成时间轴**（n=6、H=12、mock driver）上；真实帧那一路已有
  `c_contract_lift_*_smoke.py` 覆盖（§6），但它是 **scripted teacher + 脚本兜底的重放注入**，
  不是 learned policy 的在线闭环，也没有真实推理延迟分布与真机时钟。措辞应为
  "真实帧重放通过"，仍不是"真机通过"。
- 接管 smoke 里的"兜底控制器"就是把同一段录制动作改标成 `source="harness"` 的**重放注入**，
  用来验契约层行为；真正的物理兜底（`harness/grasp_guard.py` 那条路）没有参与，
  接管是否真能救回漏抓，本 smoke 不作任何主张。
- 真 Gateway、带代次的独占租约、按物理资源上锁**未实现**；`lease_generation` 目前只是账本字段，
  没有真正的互斥语义。
- `goal_id` 已贯穿账本、视图与发布包，但**没有任何策略真把 goal 吃进网络**；v4 的共享 θ 双向
  目标条件 policy 仍未实现。
- `ReleaseBundle` 的 14 个 role 目前只有自检里的假组件；真实 ACT/SAC checkpoint、normalizer、
  动作契约、调度配置还没有被打包过，`registry/` 里已发布的 `reach_sac@v1` 等旧版本
  **没有**被迁移成 bundle。
- 视图分片已被一个**参考 learner** 真实消费过（§1.6 + §6.3）：装配成张量、算 target、
  走反向传播、参数确实更新。但这只是**回放级接线验证**，不等于学习路线打通 ——
  RLinf / LeRobot 侧的读取适配、`x_ref` → 表征重算（现在只重算 flat 状态向量，
  没有任何视觉表征）、真实 ACT/VLA 主干、以及多 worker 签名与 checkpoint 边界换版都还没做。
- `harness/queue_td_learner.py` 的 actor 是个 3 层 MLP、ξ 只有一位、动作域写死 `[-1,1]`；
  它**不在** §9.2 的冻结面里，随时可换。任何" learner 已就绪"的说法都不成立。
- `n` 与 `γ` 的单位需要 P0 实测依据（`templates/项目参数模板.json` 未填），当前只能标"假设值"。

## 4. 给 A / B 的接口（不需要改他们的文件）

1. 采集/评测脚本每帧把观测存进 `ObsStore.put(...)` 拿到 `obs_ref`，随帧写进账本；
   一局结束后调 `ingest_runtime_result(ledger, result, episode_id=...)`。
2. 训练前 `build_views(ledger, n=<实测槽预算>, gamma=<底层控制步折扣>, obs_store=store,
   max_age_ns=<新鲜度预算>)` 拿四个视图，再 `write_manifests(...)` 固定这一轮训练输入；
   learner 只读视图，不直接读 `runs/`。跨进程交给 learner 时用
   `export_views(bundle, dir, run_id=..., n=..., gamma=..., obs_store=store)` 落分片，
   learner 侧 `load_views(dir)`（默认核 sha256，被改过就抛 `ViewExportTampered`）；
   需要观测数组时用行里的 `x_ref` 回 `resolve_x(store, sample)` 重算，不要缓存表征当新表征。
3. 晋级时 `build_bundle(...)` → `write_bundle(...)` → `activate_bundle(...,
   slot_boundary_confirmed=True)`；出问题时 `rollback(..., reason=...)`，
   标签被撤销时 `record_contamination(...)`。
4. flick 口径要进发布包：`DirectionScore` 已预留 `flick_frac` 与 `controlled_success_rate`，
   建议直接把 `runs/infra/b_bc_retrain/flick_gate.json` 的 `controlled_success` 判据接过来，
   避免"弹起成功"进晋级。

## 5. 本次未做 / 未改

改动只落在 C 线自己的写权限内：`harness/ledger.py`、`harness/data_bridge.py`、
`harness/obs_store.py`、`harness/queue_td_learner.py`（本轮新增）、
`registry/release_bundle.py`、`scripts/c_*.py`、
`scripts/selfcheck_ledger_views.py`、`scripts/selfcheck_obs_store.py`、
`scripts/selfcheck_release_bundle.py` 与本文档。
没有改动 `harness/contracts.py`、`harness/runtime_adapter.py`、`harness/tree.py`、
`harness/env_factory.py`（B 线可复现性硬化）、`registry/publish.py`、`envs/`、`skills/`
与 A/B 的任何脚本或产物；没有启动训练；没有触碰 `RL_Harness_v4_20260924/`（保持只读）；
真实 `registry/` 未被写入（自检有断言守）。

## 6. 真实帧验收（09-28 追加）

两个 smoke 都用同一局 scripted teacher 的真实 Lift 帧（seed 5000、46 帧、`success=held=True`、
phases = approach/descend/grasp/lift），槽协议与 `scripts/act_chunk_replay_lift.py` 同构：
槽起点 `t_k=k·n`、`U_k=teacher[t_k+n : t_k+2n]`（E 段）、帧 `[t_k, t_k+n)` 归属
`chunk_id=R_{k-1}`、`chunk_index=n+(f-t_k)`，首槽是 prime/hold（无来源 chunk）。

### 6.1 `c_contract_lift_smoke.py`（14/14）

| 通道 | 结果 |
| --- | --- |
| `fresh`（观测新鲜） | `n_td=10 isolated=2 pending=0`，`c_next_equals_u=10/10`（终局槽按契约不要求 next 快照），回报手算 mismatch 0，观测逐位反查 10/10，删失 0，`reasons={'u_incomplete': 1, 'terminal_u_incomplete': 1}` |
| `stale`（人为把 `decided_at` 推迟 10× 预算） | `n_td=0 isolated=12 reasons={'observation_stale': 12, 'u_incomplete': 1, 'terminal_u_incomplete': 1}` —— 超龄观测整体隔离，不是重打时间戳照常用 |

尾槽隔离是本轮回查出来的**契约缺陷修复**（§7 缺陷 5），不是回归。46 帧、n=4 ⇒ 槽起点
0…44；`U_k = teacher[t_k+n : t_k+2n]`，于是 R010 只拼到 2 行、R011（终局槽，`L=2`）拼到 0 行：

| 槽 | `u_rows` | terminated | `r_slot` | 隔离原因 |
| --- | --- | --- | --- | --- |
| R010（起点 40） | 2 | 否 | 1.8548 | `u_incomplete` |
| R011（起点 44，终局） | 0 | 是（`success`） | 1.4607 | `terminal_u_incomplete` |

两条的**终局事实都完整保留**（`terminated/success`、真实 `R_L`、`bootstrap_valid=False`），
只是动作未知 —— 正是附录 02 §5.1 的「保留终局事实，但不给它伪造 U」。
真机上 U 是 `t_k` 一次前向的产物，终局槽照样有完整 U，不存在这个缺口；
它只出现在「录制到一半就停」的重放里，所以必须显式暴露成隔离原因，不能靠下游补帧掩盖。

### 6.2 `c_contract_lift_takeover_smoke.py`（28/28）

注入点：帧 18（= 槽 4 起点 16 + 偏移 2）harness 兜底接管；`late_labels` 通道另注入
帧 8/9 的 `pending` 标签与帧 21 的 final 标签事后撤销。

| 通道 | td | bc | isolated | pending | censoring | 隔离原因 |
| --- | --- | --- | --- | --- | --- | --- |
| `clean` | 10 | 0 | 2 | 0 | 0.0 | `u_incomplete:1`、`terminal_u_incomplete:1`（均为重放尾槽，见 §6.1） |
| `takeover` | 3 | 28 | 2 | 0 | 0.2（槽口径 0.2） | `c_next_not_equal_u:2`、`takeover_in_slot:1`、`lease_generation_changed:1` |
| `late_labels` | 8 | 0 | 3 | 1 | 0.0 | `reward_unknown:1`、`u_incomplete:1`、`terminal_u_incomplete:1` |

`takeover` 通道不受尾槽影响：接管后 `last_policy_start=20`，槽起点只到 16，
每个槽的 `[t_k+n, t_k+2n)` 都落在 46 帧录制范围内 ⇒ `td=3 / bc=28` 与修复前逐位相同。

关键读法：

- 被抢占槽 `R004` 同时暴露 `takeover_in_slot` 与 `lease_generation_changed`（槽内帧横跨
  代次 0/1）；前驱 `R003` 因承诺队列被兜底替换而 `c_next_not_equal_u`。两者都退出普通 TD，
  但**事实完整保留**（U 仍在账本里，可用于日志与 BC）。
- 接管后策略不再被询问：`request_admitted` 的最大起点停在 16，没有为兜底伪造决策槽
  （兜底 chunk **不发** `request_admitted`，否则 `build_slots` 会把兜底动作当学习器决策混进 TD）。
- 28 条纠正帧全部且只进 BC：`bc_action_field="driver_command"`、账本侧 `a_rl=None`、
  `u` 与 `driver_command` 逐值相同、与 `measured_state` 同长度切片不相等（防实测位移倒填）、
  `supervision_mask` 每帧恰好一位且落在 E 段 `[n,2n)`、`lease_generation=1`。
- `pending` 槽进 pending 桶且 `r_slot=None`（不置零、不发布）；撤销一帧 final 标签后
  整槽退回 `reward_unknown` 并退出 TD，`stats.revoked_labels=1`，原标签行仍在（append-only）。
- 三条通道的视图都导出成分片（`views_<通道>/{td,bc,candidate,isolated,pending}.parquet` +
  `manifest.json`，单通道产物约 1.5 MB 含账本与观测快照），再按 sha256 读回：行数与内存一致、
  BC 分片的 `bc_action_field` 全为 `driver_command`、td 分片里没有接管之后的帧、
  `representation_versions == ["lift-state-proprio50+obj10-v1"]`。

### 6.3 `c_learner_shard_smoke.py`（40/40）—— 参考 learner 真读一次分片

监管备忘录 §二C-1 的原话是：状态维持「已实现未验证」，**至少要有一个真实调用方接入**。
这个 smoke 就是那个调用方（§1.6）。三条通道：

| 通道 | 数据来源 | n / γ / H | td | bc | isolated |
| --- | --- | --- | --- | --- | --- |
| `clean` | 真实 Lift 帧，无接管 | 4 / 0.99 / 2n | 10 | 0 | 2 |
| `takeover` | 同一局，帧 18 兜底接管 | 4 / 0.99 / 2n | 3 | 28 | 2 |
| `terminal` | 合成时间轴（复用 `selfcheck_ledger_views.EpisodeBuilder`） | 6 / 0.9 / **3n** | 2 | 0 | 0 |

`terminal` 通道跑出来的 target，逐行可对附录 02 §5 手核：

```
RA: R=0.000000  γ_slot=0.531441 (=0.9^6)  bootstrap=True   q_next=0.144097  y=0.076579
RB: R=0.810000  γ_slot=0.531441           bootstrap=False  q_next=0.079249  y=0.810000
```

RB 是终局槽（第 3 步 `success`，`L=3 ≤ n=6`）：`y = R_{k,L} = γ²·1 = 0.81`，
`q_next` 算了但**没进目标**；它的 `next_x_ref=None`（终局后没有下一帧），
learner 用零占位而不是拒绝，因为不 bootstrap ⇒ 占位不可能进 `y`。
RA 作为前驱照常 bootstrap，`y = 0 + 0.9^6·q_next` —— 与 `selfcheck_ledger_views.case3`
的 `0.9^8` 传回是同一条规则，只是这里由真实 learner 进程算出来。

**梯度隔离的探针本轮被证明是假绿并重写**（§7 缺陷 6）。现在的构造是：对一个代表「完整头
整块 H 长预测」的 `full` 张量求导，按契约规则拼装（C 段取 `sg(C)` 常量、E 段取 `full[n:2n]`、
D 段取零常量），再按段切片看梯度。三通道实测：

```
clean/takeover (H=2n): actorE=1.309e-02 | probe C=0.0e+00 E=1.332e-02 D=0.0e+00 (d_width=0)
terminal       (H=3n): actorE=1.221e-02 | probe C=0.0e+00 E=1.429e-02 D=0.0e+00 (d_width=42)
```

并且**每条都配一个可证伪对照**：故意把拼装规则写错（C 段改用策略预测 / D 段改用策略预测），
对应段梯度必须亮起来。实测 `wrong_c=1.561e-02`（三通道均 >0）、
`wrong_d=1.219e-02`（只有 H=3n 的 terminal 通道有 D 段，H=2n 时记 0 并由 `d_width=0` 说明）。
没有这个对照，「C/D 梯度为 0」随时可能只是探针失灵。

拒绝路径共 6 条，全部实测触发：分片被改过（`ViewExportTampered`）、`n` 与配置不符、
混表征版本、`x_ref` 反查不到观测、U 短缺 n-1 行、以及**把终局槽谎称成可 bootstrap**
（连 sha256 一起改以绕过篡改检测，仍被 `next_x_ref` 缺失挡下 —— 拿零向量冒充 `h_{t_k+n}`
会凭空造出一个后继价值，是最危险的一种改法）。

产物：`runs/infra/c_learner_shard_smoke.json` +
`runs/infra/c_learner_shard_smoke/<时间戳>/`（三通道账本、观测快照、导出的 parquet 分片，
以及 `views_tampered` / `views_mixed_repr` / `views_forged_bootstrap` 三个反例目录，约 1.5 MB）。

## 7. 本轮修掉的实质缺陷（都在 C 线自己的文件里）

这四个都不是"测试没写"，是实现本身与契约不符，且在合成自检里**看不出来**：

| # | 缺陷 | 后果（若不修） | 修法 |
| --- | --- | --- | --- |
| 1 | `data_bridge` 从不查 `ledger.revoked_seqs()` | 被撤销的奖励/质量标签照样进视图：一次 rubric 误判复核改不掉任何东西，"撤销"只是账本上的装饰 | `build_slots` 与 BC 的 quality 读取都过滤撤销行；`stats.revoked_labels` 报数 |
| 2 | `reward_state` 优先级是 `pending > final > unknown` | 六帧里撤销/迟到一帧，整槽仍算 `final`，`R_k` 静默按 0 少算一项 —— 用一次误判悄悄改了学习目标 | 改成 `pending > unknown > final`：槽内任一帧无可用标签 ⇒ 整槽 unknown；`r_slot` 只在 final 时计算 |
| 3 | BC 视图一律取 `u=fr["a_rl"]` | 纠正帧按契约 `a_rl` 必须是 None ⇒ **所有 harness 纠正都进不了监督**，而 `n_bc` 照样非零；H1/H2 想验的"从纠正中学"会在数据层就落空 | 取 `a_rl`，为 None 时退回 `driver_command`，并记 `bc_action_field`；两者都无则不产样本（`stats.bc_skipped`），绝不填 0 |
| 4 | 纠正帧缺 `chunk_index` 时仍产出 `supervision_mask` 全零的样本 | `n_bc` 好看、梯度恒为 0 | 缺 index 直接跳过并计入 `bc_skipped.no_chunk_index`；纠正要可训必须带自己的 `chunk_id/chunk_index` |

另外两处是口径/结构问题：

- **帧与决策槽解耦**（`scripts/c_contract_lift_smoke.py::replay_into_contract`）：原来帧写入
  嵌在策略槽循环里，接管点之后的帧一条都不落账本 —— 46 帧的局只记下 2 条纠正帧，
  账本看着"干净"，实际把整段纠正数据丢了。现在物理事实与决策事件是两个独立循环。
- **删失给两个口径**（`compute_stats`）：`censoring_ratio` 的分母是被决策槽覆盖的帧，
  接管之后那段没有槽 ⇒ 既不进分子也不进分母，**接管越久这个比例反而可能越小**；
  新增 `censoring_slot_ratio`（接管槽/全部槽）不受此影响。报告删失时两个都要给。

### 7.1 learner 对接这一轮又挖出 5 个（09-28 晚）

把参考 learner 真接上分片之后立刻暴露出来的 —— 全都**在合成自检里看不出来**，
这正是「至少要有一个真实调用方」的价值：

| # | 缺陷 | 后果（若不修） | 修法 |
| --- | --- | --- | --- |
| 5 | `_classify` 只查 `u_available = u is not None`，不查长度 | 尾槽 U 只拼到 2 行甚至 0 行也进普通 TD。下游 learner 要么直接崩，要么补零/把短缺的行重复填成 n 段 —— 后者是附录 02 §4.3 明令禁止的**伪造动作**，且违反 §3.3 条件2「完整入队」 | `SlotFacts` 加 `u_complete = (u is not None and len(u)==n)`；不完整 ⇒ `u_incomplete`（终局槽记 `terminal_u_incomplete`）进隔离，短缺行数原样保留 |
| 6 | `gradient_isolation_report` 的探针是**假绿** | `0.0*c_probe` 让 `grad_c` 恒等于 0，与拼装规则无关 —— 把 C 段错接成策略预测也照样报通过；`d_probe` 直接进 chunk，量到的是 Q 对 D *输入*的敏感度（本该非 0），不是「策略的 D 预测有没有拿到梯度」。H=2n 时 D 段是空张量，把这个错掩盖成 0.0 | 改成对**单个** `full` 张量（代表完整头的整块预测）求导后按段切片；另加 `gradient_isolation_falsification()`：故意错用策略的 C/D 预测，对应段梯度必须非 0。同源的假绿构造在 `selfcheck_ledger_views.case2` 里也有一份，一并重写 |
| 7 | `absmax(grad, lo, hi=None)` 在 `hi=None` 时返回整条张量的 max | D 段读到的是 E 段梯度 ⇒ 「D 段有梯度」的假报警，把缺陷 6 的修复看起来像又坏了 | 始终 `grad[:, lo:hi]`（`hi=None` 即 `grad[:, lo:]`），并注释说明 |
| 8 | `load_shard_batch` 对每个 td 行无条件解析 `next_x_ref` | 终局槽 `next_x_ref=None`（它没有下一帧）⇒ learner 一读到终局槽就 `LearnerRefused`，§5 的 terminal TD 样本永远训不了 | 只在 `bootstrap_valid=True` 且缺 `next_x_ref` 时拒绝（那才是「拿零向量冒充后继状态」）；终局槽用零占位并写进 `notes`，因为不 bootstrap ⇒ 占位不可能进 `y` |
| 9 | smoke 里 `manual_bc_loss()` 在 `train_steps()` **之后**算，却和 `history[0]["loss_bc"]` 比 | 拿更新后的 actor 去比更新前的损失 ⇒ 必然不等，「BC 手算一致」这条断言永远失败，看起来像 learner 算错了 | 移到更新前算并存 `bc_manual`，更新后的值另存 `bc_manual_after` 只作记录不作断言 |

缺陷 6/7 合起来说明一件事：**「某个梯度为 0」这类断言，必须配一个能让它变非 0 的对照，
否则它什么都证明不了。** 现在三通道每条隔离断言都带 `falsify` 对照（§6.3）。

回归覆盖：`selfcheck_ledger_views.py` 54 → 61（撤销回归）→ 80（导出往返 + 篡改检测）→
**83**（例2 重写为可证伪构造，5 条断言变 8 条）；真实帧侧由 §6.1 的 12 条与 §6.2 的 28 条守；
learner 接线由 §6.3 的 40 条守。

## 8. 环境事故记录：robosuite 1.5.1 让两条 pin 静默失效（B 线已修）

C 线 smoke 连跑帧数不稳（47/46/51/48）顺出来的，**根因与修法归 B 线**（可复现性硬化写权限），
这里只留记录，避免以后有人再查一遍：

- `/root/venvs/rlrobot` 一度装的是 robosuite **1.5.1**（`requirements.txt:25` 钉的就是它），而
  `harness/env_factory.py` 的两条 pin 都打在 1.5.2 的新 API 上：
  - 出题：`seed_placement()` 设 `leaf.rng`，但 1.5.1 的 `UniformRandomSampler` 类里**没有**
    `rng`，`_sample_x/_sample_y/_sample_quat` 读**全局** `np.random.uniform` ⇒ no-op，
    `reset_contact(env, seed)` 的 seed 对出生点毫无作用（同 seed 连调两次给不同题）；
  - 物体几何：`pinned_object_rng()` 猴补丁 `np.random.default_rng`，但 1.5.1 的
    `mjcf_utils.get_size()` **没有 rng 参数**，直接 `np.random.uniform` ⇒ no-op，
    K11 那个"每个进程 cube 不同"的老 bug 复活（同进程两次构造给出不同 cube）。
- 旁证（只读引用）：`runs/infra/b_act_lift_mb_hist1_seed0/config.json` 的 cube size =
  `[0.0210976,0.0214304,0.0212055]`，同目录 `audit_truth20.json` = `[0.0219404,0.0207813,0.0204963]`，
  `b_act_lift_mb_hist4_seed0/audit_truth20.json` = `[0.0214015,0.0217598,0.0207618]` ——
  三者都写着 `pinned_object_seed=20260923`，却是三个物体。
- B 已定位并装回 **1.5.2**，门禁是 `scripts/b_selfcheck_reproducibility.py`（几何 ×3 / reset /
  策略前向 / 20 步开环动力学，含跨进程与 OMP 线程数敏感性）。C 线不再维护并行门禁：
  我临时写的 `scripts/c_probe_spawn_seeding.py` 已 `mv` 到
  `/workspace/mnt/sppro/yhzhang91/recycle_bin/rlrobot_c_20260928/`，1.5.1 期的证据产物留在
  `runs/infra/c_spawn_seeding_probe/20260928_1558*`。
- **遗留 flag 已由 B 关闭**（16:2x 复核）：`requirements.txt:25` 现为 `robosuite==1.5.2`，
  `scripts/setup_env.sh` 也加了实装版本断言（不是 1.5.2 就失败），并把 mujoco 钉在
  `>=3.3,<3.10`。C 线不再跟踪此项。

## 9. 状态措辞、接口冻结与备忘 ack（09-28 追加）

### 9.1 状态措辞（按 `guides/02_开发实施指南.md` 的五档 + 监管备忘录 §二C-1）

| 组件 | 状态 | 依据与不得越界的表述 |
| --- | --- | --- |
| `harness/ledger.py` | **已实现未验证** | selfcheck 83/83 + 真实帧回放通过 ≠ v4 P3 完成；改状态的前置是至少一个真实调用方（A 的评测器或 B 的门禁）接入 |
| `harness/data_bridge.py` | **已实现未验证** | 同上；真实帧那一路只能表述为「回放通过（scripted teacher 重放，非 learned policy、非真机）」 |
| `registry/release_bundle.py` | **已实现未验证** | 只被自检里的假组件打包过，真实 ACT/SAC checkpoint 从未进过 bundle |
| `harness/obs_store.py` | **已实现未验证** | 30/30 自检 + 真实帧反查逐位相同；参考 learner 只按 `x_ref` 重算过 flat 状态向量，**没有任何视觉表征被重算过** |
| `harness/queue_td_learner.py` | **已实现未验证**（参考实现） | §6.3 的 40 条只证明「附录 02 §3 的目标能被一个真实进程按分片算出来并更新参数」；**不是**学习路线打通，不含任何能力主张，且不在 §9.2 冻结面内 |

### 9.2 接口冻结 v1（B 可以据此写 `selfcheck_ledger_data_bridge.py`）

备忘录 §二B-3 说 B 的验收自检在等 C 宣布接口冻结：**现宣布冻结，生效于本轮全部改动之后**
（83/83 + 14/14 + 28/28 + 40/40 全绿的那一版，即冻结 v1.1）。冻结面如下，签名与语义不再变；
后续只允许「追加带默认值的字段 / 新增函数」，任何破坏性改动必须先升冻结版本号并说明理由。

v1 → v1.1 的两处变化都是**追加**，不破坏已按 v1 写的黄金期望值：
`SlotFacts` 新增 `u_complete` 字段；`isolation_reasons` 新增两个取值
`u_incomplete` / `terminal_u_incomplete`。`harness/queue_td_learner.py` 整个模块**不在**冻结面内。

- `harness/ledger.py`：`FactLedger`（`append_frame` / `append_event` / `append_label` /
  `revoke_label` / `append_proposal` / `record_view_manifest` / `frames` / `events` /
  `labels` / `proposals` / `manifests` / `revoked_seqs` / `revocation_impact` / `stats`）、
  `ingest_runtime_result()`、`Row`；枚举 `FRAME_SOURCES` / `EXECUTION_STATUS` /
  `LABEL_KINDS` / `REWARD_STATES` / `PROPOSAL_SOURCES`；四张事实表的 append-only 触发器。
- `harness/data_bridge.py`：`build_slots()` / `build_views()` / `write_manifests()` /
  `resolve_x()` / `compute_stats()` / `slot_return()` / `td_target()` / `e_segment_mask()` /
  `export_views()` / `load_views()` / `sample_to_row()` / `candidate_to_row()`；
  数据类 `SlotFacts` / `TrainingSample` / `ViewBundle`；枚举 `TERMINATED_KINDS` /
  `TRUNCATED_KINDS` / `ISOLATING_KINDS` / `VIEW_NAMES` / `SAMPLE_COLUMNS` /
  `CANDIDATE_COLUMNS` / `DEFAULT_QUALITY_THRESHOLD`；异常 `ViewExportTampered`。
- `registry/release_bundle.py`：`build_bundle` / `write_bundle` / `load_bundle` /
  `verify_bundle` / `activate_bundle` / `rollback` / `record_contamination` /
  `paused_bundles` / `load_active` / `activation_history` / `file_component` /
  `inline_component` / `content_sha256` / `inline_sha256`；数据类 `ComponentRef` /
  `DirectionScore` / `ReleaseBundle`；异常 5 个；常量 `REQUIRED_ROLES`（14 项）/
  `DEFAULT_DIRECTIONS` / `CONTRACT_VERSION`。

**B 的黄金期望值表必须按本轮的新口径写**（这四条是本轮改的，旧口径会算错）：

1. 撤销生效：被 `revoke_label` 的奖励/质量标签不再进任何视图（`stats.revoked_labels` 报数）。
2. `reward_state` 优先级 = `pending > unknown > final`：槽内任一帧无可用标签 ⇒ 整槽 unknown，
   且 `r_slot=None`（只有 final 才算 `R_k`）。
3. BC 目标 = `a_rl`，为 None 时退回 `driver_command`（`bc_action_field` 标明来源）；
   两者都无或缺 `chunk_index` ⇒ 不产样本，计入 `stats.bc_skipped`。
4. 删失两个口径：`censoring_ratio`（分母=被槽覆盖的帧）与 `censoring_slot_ratio`
   （分母=全部槽）；报告要同时给。
5. **U 完整性**（v1.1 新增）：`len(u) != n` 的槽不得进普通 TD，隔离原因记 `u_incomplete`
   （终局槽记 `terminal_u_incomplete`），且短缺行数**原样保留**、不补零不重复填充。
   按 v1 口径写的黄金期望值会在这里算错：真实帧重放 46 帧 / n=4 时 `n_td` 是 **10 不是 12**，
   尾槽 R010（2 行）与 R011（0 行，终局）都进 isolated。

### 9.3 备忘 ack（按 §三.3，回复记在本文档，未修改备忘录）

- **C-1（状态维持「已实现未验证」）**：ack，已按 §9.1 落表；本轮所有对外表述都带
  「scripted teacher 重放、非 learned policy、非真机」的限定。
- **C-2（`release_bundle` 不要假设 B 门禁字段）**：ack。`DirectionScore.flick_frac` 与
  `controlled_success_rate` 目前是**预留字段**，`release_bundle` 不读 B 的任何产物、
  不假设阈值或字段名。建议的接法是 B 先给出 gate JSON 的字段契约，C 侧加一个独立适配函数
  （例如 `direction_score_from_gate(gate_row)`）把 B 的判据翻成 `DirectionScore`，
  而不是让发布层直接耦合门禁产物 —— **待与 B 对齐后再实现，本轮未做**。
- **§三.1（两套 ACT 结论不得互借）**：ack。C 线本轮不涉及任何 ACT 能力主张，
  两个真实帧 smoke 的控制器都写明是 `scripted_teacher` + 脚本兜底重放注入。
- **增补一 §5-C（"C：不变，维持「已实现未验证」"）**：ack。§9.1 表格未上调任何状态；
  本轮新增的 `harness/queue_td_learner.py` 同样记「已实现未验证（参考实现）」，
  并显式写明它**不在** §9.2 冻结面内、不含任何能力主张（§1.6、§3）。
- **增补二 §4 / §5-C（核对账本与视图对 obs 维度/布局的假设）**：ack，已做完审计并落成守卫，
  见 §10。结论一句话：**库层零维度假设**，假设只在 C 线脚本的切分与 learner 的
  `LearnerConfig.state_dim` 两处，且两处都是显式拒绝而非静默截断。
- **增补二 §3（输入契约强制 / `norm_input_blown_frames_frac`）**：ack，已知悉这是 A 的评测器
  与 B 的门禁之间的字段。C 线不产出该字段，也不会去读它；若后续要把它写进账本，
  应按 §9.2 的追加规则先与 B 对齐字段名与口径，再决定它是帧事实（进 `frame_fact.payload`）
  还是标签（进 `label`）。

## 10. obs 维度与布局假设审计（09-28 晚，回应增补二 §4/§5-C）

D 线增补二要求：obs 布局变更（例如加入 `cube_z − z0`）时，须同步核对 C 线
`harness/data_bridge.py` / `ledger.py` 是否缓存了 60 维假设。逐文件核完的结论：

### 10.1 库层对维度**零假设**

| 文件 | 怎么处理观测 | 有无维度假设 |
| --- | --- | --- |
| `harness/ledger.py` | `measured_state` 是 opaque JSON、`obs_ref` 是 TEXT | 无（不校验长度，见 §10.3 风险 3） |
| `harness/data_bridge.py` | 只搬 `obs_ref` → `x_ref` / `next_x_ref`，从不解引用数组 | 无 |
| `harness/obs_store.py` | 内容寻址存整个数组字典，绑定 `representation_version`（非空强制） | 无 dim/shape 列，不校验维度 |
| `registry/release_bundle.py` | 组件身份用 sha256 | 无 |
| `harness/queue_td_learner.py` | `state_dim` / `action_dim` 由**调用方**经 `LearnerConfig` 传入 | 无硬编码；不匹配即 `LearnerRefused`（`:130`、`:150`） |

### 10.2 维度假设只存在于两处，且都已显式化

1. **切分**：`scripts/c_contract_lift_smoke.py` 的 `STATE_DIM=50` / `OBJ_DIM=10`，
   `flat[:50] → state`、`flat[50:60] → environment_state`。另两个 C 线 smoke 都从这里 import，
   不各自再写一份。
2. **learner 配置**：`scripts/c_learner_shard_smoke.py` 的 `state_dim=60` / `action_dim=7`，
   经 `LearnerConfig` 传入；`_obs_vector` 在宽度不符时拒绝装配，不截断、不补零。

本轮把第 1 处从"手写字符串"改成**由宽度拼出版本号**并加了逐帧守卫：

```python
REPR_VERSION = f"lift-state-proprio{STATE_DIM}+obj{OBJ_DIM}-v1"   # 布局变 ⇒ 版本号自动变

def assert_obs_layout(obs_flat) -> int:   # 宽度 != STATE_DIM+OBJ_DIM 就 AssertionError
```

当前布局下版本号仍是 `lift-state-proprio50+obj10-v1`（历史产物不变）。守卫由
`c_contract_lift_smoke.py` 的 2 条断言守着：正向核对本局每一帧宽度，反向确认宽度 +1 时真的会炸
—— 只测正向等于没测（§7.1 缺陷 6 的教训）。

### 10.3 obs 布局真变了会发生什么

假设 obj 段 10 → 11（加入 `cube_z − z0`）：

| 环节 | 行为 | 是否静默错训 |
| --- | --- | --- |
| `assert_obs_layout` | 第一帧就 `AssertionError`，提示必须改 `STATE_DIM/OBJ_DIM` | 否，直接停 |
| 改了 `OBJ_DIM` 之后 | `REPR_VERSION` 自动变成 `...obj11-v1` ⇒ 新表征族 | 否 |
| `ObsStore` | 新旧版本号不同 ⇒ `representation_version` 冲突检查生效，不会把两种布局合并去重 | 否 |
| `export_views` / `load_views` | `representation_versions` 出现两个值 ⇒ `load_shard_batch` 拒绝混版本批次 | 否 |
| learner `state_dim` 未同步 | `_obs_vector` 宽度不符 ⇒ `LearnerRefused` | 否 |

三个**残留风险**，都不在本轮修（记在这里避免以后重查）：

1. **只改布局不改版本号**（例如绕过守卫直接写库）：内容寻址 sha 会变 ⇒ 产生新 ref，
   旧 ref 仍在，`obs_store` 不会报冲突；要等 learner 侧宽度核对才炸。要彻底堵住需要给
   `obs` 表加 `shapes` 列并按 `representation_version` 做一致性校验 —— 那是 schema 迁移，
   建议**与真实的布局变更一起做**，好拿真数据验证，本轮不动。
2. `REPR_VERSION` 里没有归一化统计的身份。`obs_store` 有 `normalizer_hash` 列，
   C 线 smoke 一律传 `None`；真接 ACT/VLA 的 normalizer 时必须填，否则"同一表征、不同归一化"
   仍会被当成同一种。
3. `ledger.measured_state` 存的是 `flat[:STATE_DIM].tolist()`，账本**不校验长度**，
   所以横跨布局变更的同一个 `.db` 里可以混着 50 维和 51 维的 `measured_state` 而不报错。
   目前 `measured_state` 只用于人工核对与 BC 防倒填比对，不进张量装配；
   若将来 learner 要直接吃它，必须先在账本侧加长度校验或按 `contract_version` 分段。


---

## 11. P0-1：消费 B 的黄金值规格做独立复核（09-28 晚）

完整裁定、映射表与变异目录见 **`docs/c_golden_conformance_20260928.md`**；这里只记对本文件
前面章节（尤其 §1.3 数据桥、§9.2 接口冻结 v1）的**增量与变更**。

### 11.1 新增产物

| 项 | 路径 |
| --- | --- |
| 复核脚本 | `scripts/c_selfcheck_golden_conformance.py`（读 `docs/b_golden/async_td_golden_v1.json` 逐条断言 + 12 变异自检） |
| 判定产物 | `runs/infra/c_golden_conformance.json`（含 `spec_sha256` 与 5 个实现文件的 sha256，内容寻址） |
| 可复查账本 | `runs/infra/c_golden_conformance/<stamp>/*.db`（每次调用唯一文件名，避免 append-only 叠加） |
| 结果 | `PASS=171 FAIL=0 UNRESOLVED=0 NOT_ASSERTABLE=1`，`conformant=true` |

规格是 B 写的、实现是 C 写的，两边独立 ⇒ 这是 C 线核心语义**第一条**真正意义上的外部数值复核。
`selfcheck_ledger_views.py::case1–case6` 与 B 的 E1–E6 虽然逐条平行，但那是 C 自己写期望值，
本质上是「用实现验实现」，不能替代。

### 11.2 §1.3 数据桥的三处语义变更（都是实现错，不是规格错）

| 编号 | 变更 | 影响 |
| --- | --- | --- |
| F1 | `C_next=U` 的判定从「整个下一窗口逐值相等」改为「**边界帧归属** + 归属正确的**前缀**」 | 接管发生在边界之后时，前驱的一步转移**保留**（附录 §6.2）；旧行为会连带删掉合法数据 |
| F2 | `c_not_executed` 增加帧级 `chunk_id / chunk_index / a_rl` 归属核对 | §3.3-1「C 未全槽按学习动作边界执行」现在检得出来；顺带堵住「实测位移倒填成 a_rl」 |
| F3 | 新增宽口径删失统计 `censored_slots` / `censored_slot_ratio` / `censored_requests` / `censoring_by_reason` + `CENSORING_REASONS` | §5.3 的超时/掉线/日志缺失也计入删失；**旧窄口径 `censoring_ratio` / `censoring_slot_ratio` 语义不动**（A/B 的 smoke 在消费） |

`next_queue` 字段的**取值与语义不变**（仍是下一窗口实测 `a_rl` 元组，接管后含 `None` 行）；
变的只是它参与资格判定的方式。§9.2 冻结 v1 里 `next_queue` 的类型与含义仍然成立，
但**下游不要再用 `next_queue == u` 自行判定 `C_next=U`** —— 那是 F1 修掉的错误判据，
要判就读 `td_valid` / `isolation_reasons`，或由 learner 侧用 `next_c = u`。

### 11.3 两处既有断言被改强（不是放宽）

- `selfcheck_ledger_views.py::case_success_is_not_eligibility`：`c_override` 造出的账本自相矛盾
  （帧声称归属 R1、动作值却是别的），R2 本来就不是「正常槽」。新增 `c_not_executed` 断言，
  清白槽改用 R3。**83 → 84 项**。
- `c_contract_lift_takeover_smoke.py`：原「前驱槽因队列被替换而隔离」正是 F1 的错误行为；
  改为按 `--takeover-offset` 分支（`>0` 保留前驱 / `==0` 一并隔离 = E5-V2），并补 §3.3-1 断言。
  **28 → 29 项**。

### 11.4 γ / n 的单位冲突已收敛（P0-2）

规格一致性路径**只**用 B 的约定（γ=0.9、n=6、H=20，全部从 `spec["conventions"]` 读）；
真实帧路径的 γ=0.99 / n=4 / H=8 一律标 `n_assumed`，是**假设值**。两套约定不混用。
把 n/γ 升为实测值的立项与验收判据见 `docs/c_golden_conformance_20260928.md` §8.1
（需要 A 的延迟分布 + 位移增益；20 Hz 目前只有文档口径 —— `templates/项目参数模板.json` 的
`timing` 组八项仍全为 `null`，所以按**未定标**处理，见 §12）。

### 11.5 变异自检（本仓库第三次踩「假绿」之后的硬性要求）

12 个变异体，每个对应规格 `common_traps`/不变量点名的一条陷阱，monkey-patch 注入后要求对应算例
**真的转红**，12/12 全部被抓住（命中数 1–6 条）。其中 M10/M11 就是把 F1/F2 修复**之前**的行为
重新注入 —— 证明这两次修复是被测试钉住的，不是靠人记着。

变异框架自己第一版也假绿过（M8/M11 的 `apply` 返回了 lambda 而不是 undo，patch 从未生效），
是「变异被抓住」这条断言自己把它暴露的。教训：**变异测试必须断言「变异确实改变了被测量」**。

---

## 12. P0-2 落地：`export_views` 携带 γ/n 的定标状态（09-28 晚）

### 12.1 为什么标注必须进分片，而不是只进 smoke 报告

learner 是**另一个进程**，它读的是 `views_*/manifest.json` + 五个分片。定标状态只写在
`runs/infra/c_*_smoke.json` 里，换个消费者就丢了 —— 下游会默认「manifest 里的 γ=0.99、n=4
就是本项目的实测口径」。所以 `export_views` 增了一个**可选**参数：

```python
db.export_views(bundle, view_dir, run_id=..., n=n, gamma=gamma,
                unit_convention=unit_convention(gamma, n))          # status="assumed"
db.export_views(bundle, view_dir, run_id=..., n=TERM_N, gamma=TERM_GAMMA,
                unit_convention=unit_convention(TERM_GAMMA, TERM_N, status="spec"))
```

不传就与旧行为完全一致（manifest 里不出现该键），所以既有调用方与既有产物不受影响。

### 12.2 三条硬约束

1. **贴错约定直接抛**。`unit_convention` 的 `gamma` / `n` / `gamma_slot` 与本次导出的
   `gamma` / `n` / `gamma**n` 不一致 ⇒ `ValueError`，且校验在 `mkdir` **之前**，
   不会留下半成品目录。把 B 黄金值那套（γ=0.9, n=6）贴到真机分片（γ=0.99, n=4）上，
   正是这条要拦的事故；`c_learner_shard_smoke.py` 里有对应的反向用例
   （`refusals.wrong_unit_convention`）。
2. **`assumed` 与模板互锁**。`unit_convention()` 会读 `templates/项目参数模板.json` 的
   `timing` 组（`control_hz` / `slot_n` / `inference_latency_measurements` / `deadline`）：
   标 `measured` 而模板仍有 `null` ⇒ 抛；标 `assumed` 而模板已填满 ⇒ 断言失败。
   两侧都用**注入的模板状态**测过（`c_contract_lift_smoke.py` 的 `measured_guard`），
   否则一个无条件 `raise` 也能骗过正向断言。
3. **`γ_slot` 只算一次并落盘**。`unit_convention` 里算 `γ^n` 存进 manifest，下游直接读；
   终局通道另有断言钉住它等于 `0.531441`（=0.9^6）且远离 `0.9^36` —— 就是「把槽当折扣单位
   再幂一次」那个 bug（黄金值 `common_traps[3]`、变异体 M1）。

### 12.3 本轮**没有**做的

- 没有把 γ/n 改成实测值：等 §11.4 / 黄金值文档 §8.1 的 A 侧延迟分布与位移增益。
- 没有动 `write_manifests` 写进**账本**的 manifest 记录：那一层是固定列，加字段要改账本
  schema，与 P0-3「裁定身份与有效性」（`gate_build` / `measurement_valid` / `superseded_by`）
  一起做更合适，不在这轮塞。
- 没有改 B 的黄金值约定，也没有改 `docs/b_golden/*`。

### 12.4 断言数变化

| 脚本 | 变化 |
| --- | --- |
| `c_contract_lift_smoke.py` | 14 → **17**（模板互锁、γ/n 假设标注 + γ_slot、定标守卫双向） |
| `c_contract_lift_takeover_smoke.py` | 29 → **31**（report 标注、三通道 manifest 带约定） |
| `c_learner_shard_smoke.py` | 40 → **43**（两套约定分开、γ_slot 二次幂守卫、贴错约定被拒） |

全绿回归见 `docs/c_golden_conformance_20260928.md` §9 末段。
