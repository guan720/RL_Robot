# C 线登记（2026-09-29）：T17 goal 贯通落地 / ξ 锚覆盖面判定为实质缺口 / venv 丢失与重建

登记方：智能体 C（实体运行时·事实账本·训练视图线）。
依据：DR-001（`work/decisions/` 可写，**最小写入**：只放路线变更 / 口径裁定 / 作废与 ack 登记）、
DR-002 护栏 8 与 DR-003 决定 8（单写者纪律 ⇒ **C 不执行任何 git 写命令**，本线只读
`git log` / `git status`）、监管备忘 增补三 §9-C 与 增补五 §9-C、
`docs/b_handoff_to_c_20260928.md`（B→C 交接单）。
本文件是 C 线自己的登记，**不修改** D 的 DR 条目、A 的 `decisions_20260928_A.md`、
B 的 `decisions_20260928_B.md`，也**不修改**昨天的 `decisions_20260928_C.md`
（append-only：待办表的结案在新文件里登记，旧文件一字节未改）。
编号续用 `ADR-C-*`，不占 D 的 `DR-*` 与 B 的 `DR-00x` 序列。
推导记录见 `docs/c_t17_goal_conditioning_20260929.md`。

**上下文来源声明（必须写清）**：9/28 四线的 rollout（`/root/.codex/sessions/2026/09/28/`）
已被服务器检修一并清掉，本轮 C 的上下文是从**盘上产物**重建的
（`work/decisions/decisions_20260928_C.md`、`docs/c_*`、`docs/b_handoff_to_c_20260928.md`、
`rl_harness_supervision/supervisor_memo_20260928.md`、`daily_report.md`、`runs/infra/c_*`、
`tmp/agentD_review_20260929/`、`git log`）。凡本轮引用的数字都注明了产物路径与时间戳。

---

## ADR-C-005 T17 goal 贯通落地（交接单 C-1/C-2/C-3 + §4），待办 4 结案

- 时间：2026-09-29 10:35–11:10 实施并登记
- 依据：`docs/b_handoff_to_c_20260928.md` §1（三项改动）/ §2（断言形态）/ §3（两处精度更正）
  / §4（ξ 计数）/ §6（验收方式）；监管备忘 增补三 §9-C；v4 附录 02 §12
- **前置已解除的实测证据**（昨天登记「等 B 的参考实现落定再动」）：
  `scripts/b_selfcheck_goal_conditioning_t17.py`（21965 B，9/28 17:25）、
  `runs/infra/b_t17/t17_precheck.json`（9/28 22:42，`teeth_check.non_vacuous=true`、
  `n_broken_variants=6`、`n_runnable_broken_variants=5`、`n_blocked_variants=1`）、
  `runs/infra/b_t17/t17_mutation.json`（9/28 22:38）。
- 裁定与变更（全部在 C 的写入边界内）：
  1. **C-1** `LearnerConfig.goals` 缺省 `("lift",)` → `("lift_A_to_B", "lift_B_to_A")`。
     真帧通道的 `goal_id` 由 `scripts/c_contract_lift_smoke.py` 新增的 `GOAL_VOCAB` / `GOAL_ID`
     **单一事实源**供给，`c_learner_shard_smoke.py` import 而不自己写字面量。
  2. **C-2** `_goal_onehot` 在 `cfg.goal_dim < 2` 时抛 `LearnerRefused`（取 B 明写的
     「至少显式拒绝」那一支，**不改 embedding**：改 embedding 会变 `cfg.x_dim()`，
     扰动已与 B 规格逐条对账冻结的黄金值面 E1–E6，收益不抵风险）。
  3. **C-3** 新增 `scripts/c_selfcheck_goal_conditioning_t17.py`：T17-a/c/d/e 落在**真实**
     learner 上（链路 `FactLedger → ObsStore → build_views → export_views → load_shard_batch`），
     阈值原样取自交接单 §2（`atol=1e-9`、`abs().sum()>0`、`d_goal/d_state>0.05`、抛异常即通过），
     **一个都没调**。只依赖 torch+numpy，不被渲染栈/GPU 可用性阻塞。
     词表由 `LearnerConfig.__dataclass_fields__["goals"].default` 读出，不抄字面量
     （抄一份就会在缺省变更时对着不存在的词表绿着 = 恒真断言的另一形态）。
  4. **§4 ξ 普查落地**：`load_shard_batch` 逐 batch 计数 → `ShardBatch.xi_census`
     （`bc_rows_at_xi0 / bc_rows_total / td_rows_at_xi1 / td_rows_total / bc_anchor_covers_xi1`），
     无 BC 行时比例记 `None`（**不伪造 0/0**）；量化结论追加进 `notes`；
     `c_learner_shard_smoke` 报告新增 `bc_anchor_xi0_gap` 段。
- **口径裁定（回答 B §4 的提问，B §6.5 要求显式结论而非沉默）**：
  真帧实测 `takeover` 通道 `bc_rows_at_xi0 / bc_rows_total = 28 / 28 = **100%**`、
  同通道 `td_rows_at_xi1 = 3/4` ⇒ 按 B 给的判据这是**实质缺口（`substantive_gap`）**，
  不是「已知近似」：λ_BC 锚只在 ξ=0 的输入半空间施力，「有 BC 锚保护」这个主张
  **在部署区间（多数决策态 ξ=1）没有证据**。
  性质是**现状登记而非失败项**（首版无法从分片重建 BC 行的 C；修它要动导出列 = 冻结面变更，
  `docs/ledger_data_bridge_20260928.md` §9.2，属 v4 既定项，不在 learner 侧偷偷补），
  故不让 `pass` 变红。修法与自动闭合条件（`bc_anchor_covers_xi1` 转 `true`）已登记在推导文档 §6。
- **五组件覆盖按 ADR-C-004 三态处理**：`base(actor)` / `Q(critic)` / `actor_target` /
  `critic_target` 四个已实现组件 PASS；`editor` / `candidate_filter` / `predictor`
  首版未实现 ⇒ 记 **SKIP**（`ok=None`），汇总写 `44/50 PASS（6 SKIP）`。
  **必须明写：这三个组件本轮未被验证，不计入通过率**；实现后必须补测，
  不得因为「其余全绿」就当五组件全覆盖。
  两个 target 网络是 C 主动加的（B 的参考实现没有 target 网络 ⇒ 覆盖不到
  「在线网络全对但 bootstrap 不是 goal 条件的」这一类，见变异 M3）。
- **精度更正落地（交接单 §3.1）**：T17-e 断言 `LearnerRefused`（**不是** B 参考实现的
  `KeyError`），并额外钉「`LearnerRefused` 不是 `KeyError` 子类」+「拒绝时不返回任何向量」。
  §3.2（ξ 非恒零）复核确认与 C 实现一致，无需改动。
  §5 #6（E6 两个独立拒绝理由）复核确认**已满足**：`data_bridge.py` 的
  `goal_epoch_incompatible` 与 `deadline_miss` 是并排 append 的两条独立理由，
  都在 ADR-C-001 F3 的 `CENSORING_REASONS` 里，T17 没有把它们合并。
- **不变量**：不改判据、不调阈值、不改单位、不改 A/B 任何文件、不构成 baseline 重置。
  `c_selfcheck_golden_conformance` 的三处 `goals=("A_to_B",)` 不受 C-2 影响 ——
  该脚本从不调用 `load_shard_batch`，走的是 `build_nets` + 直接构造 goal 张量的路径。
- 回归验收方式：`scripts/c_run_all_selfchecks.sh` 全量 **13/13 全绿**（本轮实测）：
  `selfcheck_ledger_views 84/84`、`obs_store 30/30`、`release_bundle 27/27`、
  `harness_contracts 6/6`、`runtime_adapter 6/6`、`stage3 全过`、
  `golden_conformance PASS 171 / FAIL 0 / UNRESOLVED 0 / NOT_ASSERTABLE 1`（**与 9/28 逐项相同**）、
  `verdict_identity 84/84`、`goal_conditioning_t17 44/50（6 SKIP）`、
  `c_contract_lift_smoke PASS`、`c_contract_lift_takeover_smoke PASS`、
  `c_learner_shard_smoke PASS（43 → **46** 项，新增 3 条 ξ 普查断言）`、
  `verify_package errors: []`。
  变异自检 6 个（M1 actor 瞎 / M2 critic 瞎 / M3 `actor_target` 瞎 / M4 one-hot 无视 goal_id /
  M5 第一层冻结 / M6 单 goal 词表）逐个转红；**M5 证明 T17-c 有独立于 T17-a 的牙齿**
  （冻结后前向仍随 goal 变、只有梯度归零），C-2 另有「重注入修复前实现 ⇒ 静默返回 `[1.0]`」
  的可证伪反证。B 侧牙齿自检按 §6.3 复跑（`--json-out` 写 C 的目录，**不碰** `runs/infra/b_t17/`）
  仍 `non_vacuous=true`、6/6 坏实现被抓。
- 产物：`runs/infra/c_t17_goal_conditioning.json`（含 `impl_sha256` / 阈值 / 逐组件 delta /
  ξ 普查 / B 牙齿复跑结果）、`runs/infra/c_t17_goal_conditioning/<时间戳>/`、
  `runs/infra/c_learner_shard_smoke.json`。
- **待办 4 结案**；`decisions_20260928_C.md` 待办表第 4 项由此条取代（旧文件不改）。
- **仍需 A 侧到位才算真贯通**（交接单 §5，不在 C 边界内，C 不代做）：
  `scripts/run_act_lift_runtime_failure_audit.py:36,39` 的 `goal_id` 硬编码、
  policy 不接收 goal。C 侧现状是诚实的：真机若仍发 `goal_id='lift'`，learner 会
  `LearnerRefused`（词表外），**不会**静默当成已知 goal 训下去。

## ADR-C-006 环境事件：`/root/venvs/rlrobot` 被检修清掉 + 重建口径（附一条给 D/B 的建议）

- 时间：2026-09-29 10:40 发现，10:57 重建完成并登记
- 性质：基础设施事件登记 + 复现口径裁定。**不改任何判据、不改任何产物数字。**
- 事实：`/root/venvs/rlrobot` 整个目录消失（`ls /root/venvs/` 不存在），
  `~/.codex/sessions/2026/09/28/` 一并没了。`scripts/_venv.py` 的 docstring 早已预警
  「venv 在容器 overlay 上，重启会丢」。conda base 只有 torch 2.4.1 + numpy 1.26.4，
  缺 mujoco / robosuite / gymnasium / py_trees / pytest。
- 影响面（**四线同时**）：`c_run_all_selfchecks.sh` 硬编码 `PY=/root/venvs/rlrobot/bin/python`；
  A 的 GPU 训练与评测、B 的可复现性门禁同样失去运行环境。
- 处置：`runs/infra/c_env_rebuild_20260929/rebuild.sh`（日志 `rebuild.log` = 第一次失败、
  `rebuild2.log` = 成功）。与 `scripts/setup_env.sh` 同一套包，但**刻意不做**两件越界的事：
  ① 不覆写仓库根 `requirements.lock.txt`（候选清单写
  `runs/infra/c_env_rebuild_20260929/requirements.lock.candidate.txt`，由 B/D 决定是否采纳）；
  ② 不跑 `scripts/b_selfcheck_reproducibility.py`（那会写 `runs/infra/b_*`，属 B 的产物目录）。
- **口径裁定（值得留档，下次换机器一定还会撞）**：按 `setup_env.sh` 的**范围 pin** 装会被
  解析器判死 —— `robosuite 1.5.2 → mink==0.0.5 → numpy<2.0.0`，与 `numpy>=2` 冲突
  （`ResolutionImpossible`）；venv 原装 pip 24.0，升到 26.2.1 后解析器更严、会回溯到 `mink 0.0.5`。
  而 `requirements.lock.txt` 是 9/28 那次**实际装成并跑通全量回归**的 freeze
  （`mink==1.2.0` + `numpy==2.4.6` + `robosuite==1.5.2` 三者共存）。
  ⇒ 复现口径改为**按 lock 精确安装 + `--no-deps` 跳过解析**。
  裁定表述：**解析器到不了某个组合，不代表那个组合不可用**；lock 是「实际装成什么」的事实源，
  范围 pin 是「意图」，两者冲突时以 lock 复现、并把冲突报给 D，而不是就地放宽 pin。
- 重建后实测：numpy 2.4.6 / mujoco 3.9.0 / **robosuite 1.5.2** / gymnasium 1.2.3 / py_trees /
  stable_baselines3 2.7.1 / torch 2.4.1+cu124 / pandas 3.0.3 / pyarrow 24.0.0 / scipy 1.17.1 /
  pytest 9.1.1 / numba 0.67.0 全 OK。robosuite 版本 = 1.5.2 ⇒ **改判 3 的可复现性前提
  （robosuite 1.5.2 + `harness/env_factory.py` 的物体 pin）未被破坏**；
  本轮 C 的全量回归 13/13 全绿即为旁证。
- **给 D/B 的建议（C 不代做，`scripts/setup_env.sh` 不在 C 的写入边界）**：
  `setup_env.sh` 的范围 pin 与 `requirements.lock.txt` 已不一致，在任何一台新机器上按它装
  都会撞同一个 `ResolutionImpossible`。建议改成「优先 `-r requirements.lock.txt --no-deps`，
  lock 缺失才回退范围 pin」，并把 pip 版本一并记进 lock（本轮实测 pip 24.0 → 26.2.1
  的解析器差异是本次失败的直接触发条件）。
- **另一条给 D 的提示**：venv 与 `~/.codex/sessions/` 同在 overlay 上 ⇒ 每次检修都会同时
  丢掉「运行环境」和「四线对话历史」。前者可用 lock 复现，后者**不可复现**，
  只能靠盘上产物重建。这正是待办 2（`work/decisions/` 正式登记处）与待办 3
  （逐臂内容寻址 run manifest）的价值所在，建议 D 在下一轮点验时把它们的优先级往前提。

---

## ADR-C-007 增补六 §8-C 三条 P1 落地（解释器探测 / env manifest 与断点 / `PENDING_IMPL` 第六档）

- 时间：2026-09-29 11:25–12:00 实施并登记
- 依据：监管备忘 增补六 §0.2 第 2、3 条、§8-C 第 1/2/3 条、裁定 17.7（过渡期专用标签）、
  裁定 18（stdfloor 的门禁免罪是**对的**）、裁定 26（v1.5 复签通过）；ADR-C-004（SKIP≠PASS）
- 推导记录见 `docs/c_env_manifest_and_pending_impl_20260929.md`（本条只记裁定与实测结论）。
- **接手现场（必须记，否则数字无从对照）**：`registry/verdict_identity.py` 上一轮已改到一半，
  而 `scripts/c_selfcheck_verdict_identity.py` 未跟上 ⇒ 接手时实测 `82/84 PASS，2 FAIL`
  （两条 FAIL 不是回归红点，是自检里那套「独立重写的分级规则」还停在五档）。本轮修完并加断言。
- 三项裁定与变更（全部在 C 的写入边界内）：
  1. **§8-C3（第六档）** `usable_for` 由五档扩为六档，新增 `pending_impl_ruling_approved`
     + 过渡期标签 `PENDING_IMPL_probe_exonerated`（**沿用 D 的原字**，C 不另造词）。
     判据 `is_pending_impl_exoneration()` **只认正向**（权威表 `VALID_probe_exonerated`
     且门禁 `input_contract.status != probe_exonerated`）；反向按裁定 18 **只计数不改分级**
     （进 `exoneration_disagreement.gate_exonerated_authority_not`）。
     优先级：不是裁定 > 身份/有效性声明缺失 > **终局语义怀疑** > **本档** > 测量无效 > 旧构建 > 事实。
     两处排序都有理由：排在 suspect **之后**，否则免罪变「万能牌」（连终局语义造假都能被抬出
     `invalid_measurement`）；排在 `measurement_valid` **之前**，否则这一档永远轮不到
     （它要处理的正是「门禁判 False + 监管已会签」的冲突本身）。
     实测：192 条裁定命中 **5 条**（全部是目标臂 `trimdone0_minmax_k2_lr1e-5_s20k_seed0`：
     4 条出自 `migration_gate/exoneration_path_probe/`@`b9379fdb1089`、1 条出自
     `regate_current/`@`e4f5ec887788`）；同臂另有 1 条顶层留档裁定 `gate_build` 缺失
     ⇒ 如实停在 `unidentified_build`（身份先于免罪，不给它抬档）。
     自检 `125/126 PASS（1 SKIP）`：文件级真值表 8 格 + `classify()` 纯函数 7 格 +
     变异 6（拿掉本档 ⇒ 5 条全被埋进 `invalid_measurement`）/ 变异 7（免罪万能牌 ⇒
     `physical_fact` 被吞，但 suspect/身份/聚合三格仍不被盖过）/ 变异 8（只认反方向 ⇒
     误伤 stdfloor，违反裁定 18）**各自实测转红**。
     新增诊断：`scope_note` + `per_arm_current_build` —— 本档是**逐份裁定**口径，
     不得被读成「v1.5 还没落地」（裁定 26 已复签通过）。
  2. **§8-C1（解释器探测）** `scripts/c_run_all_selfchecks.sh` 的 `PY` 改为
     「候选探测（显式 `PY` → `/root/venvs/rlrobot/bin/python` → `python3`）+ 依赖探测
     （`numpy torch pandas pyarrow robosuite gymnasium py_trees mujoco stable_baselines3`）」。
     退出码分三种含义：`0` 全绿 / `1` 回归红点 / **`2` 没有可用解释器**（环境问题，不是回归失败）
     —— 检修那种「解释器不存在」再也不会长得像「回归全红」。显式 `PY` 探测不过时**仍放行**
     （保留 D §0.2 第 3 条给过的临时做法）但绝不静默：当场打印缺哪些模块，
     并在汇总里声明「本次不构成一次可信的全量回归」。四条路径实测通过（T1/T2/T3/T4，
     见推导记录 §3）。
  3. **§8-C2（env manifest 与断点）** 新增 `scripts/c_env_manifest.py` →
     `runs/infra/c_env_manifest_20260929.json`，口径同
     `docs/lerobot_official_env_manifest_20260924.md`（环境路径 / 记录版本 / 版本冲突 / 入口验证）。
     断点 `BP-20260929-venv-rebuild` 记成**窗口** `[10:45:56, 10:57:19]`
     （`bin/python` 链接自身 ctime → `rebuild2.log` 落盘），产物据此分
     `before / during_rebuild / after` 三值。分类规则抽成纯函数并用 **6 个合成时刻自测**
     （含两端边界）—— 真数据里 9 份产物全在断点之后，`before/during` 两支属**空过**，
     空过的规则等于没有规则。lock 一致性 **28/28 精确命中**、13 项 import 全 OK；
     `--check` 闸带反证（坏 lock ⇒ `exit 3` 实测，逐条列出 mismatch/missing）。
     `known_conflicts` 按 0924 口径登记 `mink 0.0.5 → numpy<2` 的 `ResolutionImpossible`
     与「按 lock + `--no-deps` 复现」的处置；并单列 `inherited_packages`
     （lock 是 `freeze --local`，torch 等从 base 继承、**不在 lock 里**，否则「lock 全中」是假安心）。
     manifest **不创建 CUDA/EGL 上下文**（A 在用卡），只读 `nvidia-smi` 查询接口。
- **两处自查自纠（登记以免重犯，详见推导记录 §4.5）**：
  ① `bin/python.stat()` 跟穿符号链接 ⇒ venv 创建时刻读成 `2025-09-22`（比检修早一年，
  会让**所有**产物都被判成「断点后」⇒ 断点登记形同虚设），改 `os.lstat()`；
  ② `os.path.realpath(sys.executable)` 判不出「在不在这个 venv 里」（符号链接 +
  `--system-site-packages`），改看 `sys.prefix`（附 `is_venv` 与 `site_packages`）。
- **给 B/D 的观测（C 不代做，只报事实）**：
  1. 裁定 26 三前提之**第 2 条已满足**：`runs/infra/b_official_arms/reclassification.json`
     已重出为 `v1.5 / f19f61341cbe`、`ic_status 45/2/1`、`citable 25/22/1`（11:22 实测）。
  2. **但被扫目录里还没有 v1.5 的逐臂裁定产物**：`lerobot_act_env_20260928/` 下 188 份
     `gate_*.json` 的 build 分布中**没有** `f19f61341cbe` ⇒ C 的清单 `physical_fact`
     由今早的 **15 → 0**（那 15 条出自 `ckptseq/v14_crosscheck`，随构建移动降级为
     `stale_build_evidence`，属内容寻址身份层**该有的行为**，不是红点）。
  3. A 的权威表未重出：`arms_summary.json` 仍是 `v1.2.1 / e4f5ec887788`（9/28 21:45），
     `validity_class` 分布 `valid 51 / invalid 1 / VALID_probe_exonerated 1`。
  4. 连带影响：**C 待办 1（P0-3 第二层）仍接不了线** —— `ingest_runtime_result` 只吃
     `physical_fact`，此刻接线等于零输入（与 ADR-C-005 的判断一致，但理由更新了：
     不再是「权威表没有 physical_fact」，而是「没有任何产物出自当前构建」）。
     等 B 的 v1.5 逐臂重判产物落进 `regate_current/`，C 的第六档会自动清零、目标臂转
     `physical_fact`、§2.6 那条 SKIP 自动转实测，**无需改 C 的任何代码**
     （真值表第 2 格 `authority_exo_gate_exonerated ⇒ physical_fact` 就是这个性质）。
- **文档漂移登记（C 不代改，`registry/README.md` 不在 C 的写入边界）**：
  该文件 §「裁定身份与有效性（`verdict_identity`）」的分级表仍是**五档**，与本轮改完的代码不一致；
  末尾「自检 60 项（含 3 个变异体）」也已过期（现为 **126 项 / 12 个 case / 8 个变异体**，
  其中 1 项 SKIP）。按现状读那张表，会把 `pending_impl_ruling_approved` 的记录误读成
  `invalid_measurement`（正是裁定 17.7 禁止的第二种表述）。建议补的一行（口径照 §8-C3 原文）：
  `| pending_impl_ruling_approved | 权威表 validity_class=VALID_probe_exonerated 而门禁 input_contract.status != probe_exonerated | 不能；带过渡期标签 PENDING_IMPL_probe_exonerated，实现承载后自动让位 |`，
  并把它排在 `invalid_measurement` **之前**（表格顺序即优先级）。
  归属请 D 判：若判给 C，C 下一轮改；C 本轮**未动**该文件（`git status` 可核）。
- **全量回归（在最终代码上重跑）**：13/13 全绿，日志 `runs/infra/c_full_regression_20260929_pm2.log`
  （golden `171 PASS / 0 FAIL / 1 NOT_ASSERTABLE`、`conformant=true`；身份层 `125/126`；
  T17 `44/50 + 6 SKIP`；ledger 84、obs 30、release 27；三个真帧 smoke 与 `verify_package` 全 PASS）。
  本轮回归是**通过探测路径**跑起来的（未显式给 `PY`），即 §8-C1 的改动已被实跑验证。

---

## ADR-C-008 增补七落地：裁定 28「撤标注、留机制」/ 裁定 29.4 两条 P0 / 待办 1、2 改判

- 时间：2026-09-29 12:00–12:25 实施并登记（本轮 C 的实施期间，D 连发增补七 §12–§19、
  B 落了 v1.5 逐臂重判、A 把迁移闸扩到 24 判据 —— 三条线同时在动，故本条以**实测时刻**标注每个数字）
- 依据：增补七 §13（裁定 28）、§17（裁定 29.4）、§18（裁定 29.5）、§19（对 C 的四条）
- 推导记录：`docs/c_env_manifest_and_pending_impl_20260929.md` **§7**（append-only 追加在
  ADR-C-007 那份推导记录之后，被超越的原文保留不回改，只加前向指针）
- 五项处置：
  1. **裁定 28（`PENDING_IMPL` 标注作废、全部撤下）⇒ C 的处置是「撤标注、留机制」**，
     与裁定 28.4 对护栏① 的处理同型（*本轮成 moot，机制仍建议保留*）。落地三条，全部可核：
     `LABEL_RETIRED=True` + `LABEL_RETIRED_BY`；命中记录的 `reasons` **逐条**追加作废声明
     （不是只在文档里说一句 —— 单条记录被摘出去引用时自带「这不是臂的现状态」的警告）；
     清单单列 `exoneration_disagreement.pending_impl_ruling`（`label_retired` / `retired_by` /
     `grade_mechanism_retired=false` / 现状态**转引**裁定 28.1 并明写「C 未独立复核」/
     `citation_rule`=裁定 28.5 / `evidence_for_open_question` 实测字段）。
     **C 未自行改分级**（不替 D 裁口径），改为提请三选一：(a) 留 `pending_impl_ruling_approved`；
     (b) 随裁定 28.2 转 `stale_build_evidence`（**C 倾向此项**）；(c) 给「故意被拒的探针 /
     冻结锚点」另立一档。提请的**实测依据**：命中的 5 条现在全部出自历史构建
     （`b9379fdb1089` 4 条 + `e4f5ec887788` 1 条），其中 4 条是 A 在
     `migration_gate/exoneration_path_probe/` 里**故意造出来被拒**的写法探针
     （`gate_P0_baseline`/`P1_scope_arm`/`P2_scope_artifact`/`P3_band_widened`，`violated`
     是探针的**预期结果**），1 条是 `regate_v121_pinned/main/` 的 v1.2.1 **冻结锚点**
     （预登记 §6）⇒「实现待落地」这个名字对它们已不成立。若判 (b)，C 的实施已设计好：
     激活条件收窄为「该臂在**当前构建**下没有任何承载免罪的产物」（跨记录条件放 `inventory()`，
     `parse_verdict` 仍是记录级纯函数），被改判记录留 `regraded_from` 以便审计。
  2. **裁定 29.4 C①（`probe_modules` 加 `lerobot` + 回显来源与 commit pin）已做**，
     并附**一条比 D 口径更严重的实测**：lerobot 从来就**不在** `rlrobot` 这个 venv 里 ——
     项目口径是另建两个 venv（`docs/lerobot_act_env_setup_20260928.md`：`/root/venvs/lerobot_act`
     训练/离线审计、`/root/venvs/lerobot_eval` 闭环真值评测，后者须在同一解释器里既能 import
     lerobot 又能 import robosuite）。实测 `/root/venvs/` 下**只有 `rlrobot`**
     ⇒ 这两个环境**也被同批检修清掉、至今未重建**。所以补救不是往 rlrobot 里 pip install，
     而是跑 `scripts/install_lerobot_act_env.sh`。pin 从该脚本**解析**回显（不抄写）：
     `LEROBOT=0.4.4`、`TORCH=2.6.0`、`TORCHVISION=0.21.0`、`INDEX=mirrors.aliyun.com`、
     `BASE_PY=/opt/conda/bin/python3.11`；两份 lock 各有一行 `lerobot==0.4.4`
     ⇒ **本项目的 pin 是 PyPI 版本号、不是 git commit**。D 点名的三份盘上副本实测 commit 已回显
     （zptang `0cf86487…`、gaoyuxuan `4606785…`、clzhang25/LIBERO 无可用 HEAD），
     按裁定 29.4 **均不得当 pin**，C 不推断它们与 PyPI 0.4.4 是否同源。
     另加**防误读装置**（正是裁定 29.4 点名的风险）：探针分 `required_for_c_regression`（13 个，
     进 `--check` 闸）与 `blocking_for_reproduction`（lerobot，不进闸但每次都喊出来），
     顶层单列 `env_fully_restored=false` 与 `reproduction_claims_blocked.missing=
     [lerobot, /root/venvs/lerobot_act, /root/venvs/lerobot_eval]`。
     **重装陷阱已预防**：installer 的 [5/7]、[7/7] 步会 `pip freeze >` **就地覆盖**
     `runs/infra/lerobot_act_env_20260928/requirements{,.eval}.lock.txt`（0928 环境的唯一证据）
     ⇒ C 已逐字节备份到 `runs/infra/c_lerobot_env_locks_backup_20260928/`
     （sha256 `68a38731c5b5…` / `b6db07e2e31c…`，与原件一致，已写进 manifest）。
  3. **裁定 29.4 C②（GPU reason 改成可核事实）已做**：原句「A 线正在用 GPU 训练」与同一份
     manifest 里 `nvidia-smi` 实测 `0 MiB / 0 %` 自相矛盾 ⇒ 改为「本次不探测；占用以同份
     manifest 的 `gpu.nvidia_smi` 实测为准」+ 附裁定引用。同理把 `c_run_all_selfchecks.sh`
     头部「A 在用 GPU 训练，C 不抢卡」的注释也改成不断言他线状态的写法（口径同样适用于注释）。
  4. **两处新的自查自纠**（接 ADR-C-007 的 ①②）：③ 解析 installer pin 的正则里 `$` **未转义**
     ⇒ `pin.values` 是**空 dict**（空值比错值更难发现：结构看着完整，只是那一栏没内容）；
     ④ 取 git 失败原因时取了 stderr **最后一行** ⇒ 报出来的是 git 用法提示而不是 `fatal:` 那行。
  5. **上游在 C 实施期间移动两次（实测，故 ADR-C-007 的部分数字已被超越）**：
     11:29 → 192 条 / `physical_fact` **0**；12:0x B 的 v1.5 逐臂重判落进 `regate_current/`
     （含 `blindfix/`、`reblown/`）→ **246 条 / `physical_fact` 48**，目标臂在当前构建那份
     = `input_contract.status=probe_exonerated` + `measurement_valid=true` ⇒ `physical_fact`。
     ADR-C-007 §2.6 那条 SKIP（「实现落地 ⇒ 过渡档自动让位」）**已转实测 PASS**，
     C 侧**一行代码未改**就跟随了上游（内容寻址 + 只读上游该有的行为）。
- **最终实测（本条所有结论的证据）**：身份层自检 **129/129 PASS（0 FAIL / 0 SKIP；12 case、
  8 个变异体）**；全量回归 **13/13 全绿**（`runs/infra/c_full_regression_20260929_pm3.log`，
  golden `171 PASS / 0 FAIL / 1 NOT_ASSERTABLE`）；env manifest `lock 28/28 match` +
  `required 13/13 import OK` + 断点分类自测 `6/6` + `env_fully_restored=false`。
- **本轮未开工的两项（D 在 §19 新给，属新开工程，不半途开工）**：待办 1（`physical_fact` 接线，
  要动 `harness/ledger.py`）与待办 2（登记处机制）——前置与验收见下面待办表第 1、2 行。

---

## ADR-C-009 env manifest 的**同源纪律**：C-F1 / C-F2 的修法、三条断点、import 面实测

**依据**：裁定 31.2（`import` 成功不算过）、裁定 33.4（D 在验证里撞出两处 C 侧判据缺陷，都是真红）、
裁定 34.1（豁免按包按链路授）、**裁定 37.1（P0-3 + C-F1 + C-F2 全部验收通过）**、
裁定 37.3（豁免边界收窄 + 「import 面主张必须给运行时证据」的一般化要求）、
裁定 37.4 第 2 条（覆写自己的 manifest 前必须留档）。
**判据不在本条里**（裁定 21）：实现在 `scripts/c_env_manifest.py`，
自检在同文件的 `--selftest`（产物 `runs/infra/c_env_manifest_selftest/`）。

**决定 1（C-F1，P0）**：模块探针的判据从「能不能 `import`」改成**语义探针**——版本号 + 安装来源。
`import lerobot` 是**恒真判据**（装上任何版本的 lerobot 都过，装错了也过），
于是 `probe_modules.lerobot` 改为 `probe_kind=semantic`，并要求回显
`install_source`（`kind` / `installer` / `wheel_tag` / `dist_info` / `commit` / `derived_by`）。
实测：`lerobot_act` 与 `lerobot_eval` 两个解释器都是 `version=0.4.4`、
`install_source.kind=index_wheel`、`installer=uv`（没有 `direct_url.json` ⇒ 从索引装的 wheel，
不是本地目录/VCS 安装；`derived_by` 把这条推理链写在产物里，不留给读者猜）。

**决定 2（C-F1 的作用域，D 点名认可的部分）**：`rlrobot` 里没有 lerobot 是**设计如此**，
处置是**改判据的作用域**，不是改观测：`rlrobot.modules.lerobot` 仍如实记
`importable=false` + `ModuleNotFoundError`，另用
`lerobot_missing_here_is_by_design=true` + `missing_required=[]` + `design_note`
表达「不计入缺口」。**把观测改成想要的值、或删掉那一行，都是造假**；
三值化的正确做法是让判据知道自己**不适用于**这个对象（`not_applicable`），
而不是让它在这里恒过或恒红。

**决定 3（C-F2，P0）**：断点是一个**窗口**，不是一个时刻；窗口必须**同源**。
`_venv_window` 只取「被描述的那个 venv」的证据，窗口带
`subject_venv` + `source_kind="archived_manifest_of_that_venv"` + `source=[…]` +
`applies_to_described_venv` + `not_the_described_venv_because`。
根因是本轮真实发生过的跨 venv 混算：拿 overlay 上那份已进回收站的 manifest
去描述 clean venv ⇒ 窗口对不上对象。

**决定 4（C-F2 的自测形态）**：**「规则有牙」与「数据自洽」各证各的，不互相冒充**。
分类规则自测用 **synthetic 窗口**（真窗口可能不可得、或恰好倒过来 ⇒ 规则就永远没被反向验证过），
真窗口另列 `real_window={consistent, usable_for_attribution}`。
`snapshot_consistency` 只比身份字段、显式排除易变字段 `at` 并回显排除理由
（14:52 实测过 `changed_fields=['at']` 那个恒红）。

**决定 5**：三条断点**并列不合并**（`invalidates` 范围不同）：
`BP-20260929-venv-rebuild`（废 rlrobot/robosuite 侧复现）、
`BP-20260929-lerobot-envs-wiped`（废**官方 ACT 训练与真值评测**，含 48 臂权威表所依据的那批评测）、
`BP-20260929-rlrobot-persistent`（`invalidates=无`，附三条理由：28 个 pin 逐格相同 /
env_check 与 B 的 12/12 全过 / 初始 obs 与渲染平均像素 108.5 与历史同值）。

**决定 6**：发行版探针一律**走子进程**。在同一个进程里探多个解释器的发行版会跨对象混装
（`importlib.metadata` 的搜索路径是进程级状态），本轮已按此修正。

**决定 7（裁定 37.4 第 2 条纪律，已实现）**：覆写自己的 manifest 前 `copy2` 留档，
新产物带 `previous_manifest={path, sha256, generated_at, archived_to}` 与
`changed_fields`（`n_watched` / `n_changed` / 逐字段 before-after）。
理由与裁定 35.1 同源：**「修完就绿」和「判据本来就不会红」在覆写之后长得一模一样**，
只有留档能区分。15:47 那一版实测 `n_watched=31 / n_changed=3`。

**决定 8（裁定 37.3 的一般化要求，C 侧已落地为工具）**：
「某包不在某链路的 import 面上」这类主张**必须给运行时证据**（`sys.modules` 或等价动态追踪），
静态 grep 不足以独立支撑——它扫不到传递依赖。
C 的实测（`runs/infra/c_ruling_34_1_import_surface_20260929.json`，每模块一个子进程）：
本仓 ACT/48 臂链路的 **8 个脚本全部 `hit=[]`**（与 A 的静态 grep 同向，且是更强证据）；
上游 `lerobot.scripts.lerobot_train` 的 import 闭包里**确有 imageio（18 个子模块）**，
**分开报**（`why_upstream_separate`：不在本仓 48 臂链路上）⇒ 这次分开报触发了裁定 37.3 的边界收窄。
现成工具：`scripts/c_env_manifest.py --measure-import-surface`（A/B 可只读调用，产物写自己目录）。

**产物**：`runs/infra/c_env_manifest_20260929.json`（15:47:03，494,876 B，sha256_12 `8c6a4ec366fc`；
`env_fully_restored=true`、`reproduction_claims_blocked.blocked=false`、
`verification.gate_current_at_manifest_time = v1.5 / f19f61341cbe`）、
`runs/infra/c_env_manifest_probe_lerobot_act.json`、
`runs/infra/c_env_manifest_20260929_pre_lerobot_rebuild.json`（12:14 归档，**C-F1/C-F2 曾经是真红**的证据）、
`runs/infra/c_ruling_34_1_import_surface_20260929.json`。
**下游效果（D 只读实测，裁定 37.2）**：A 线解封，`a_env_readiness_gate.py` E1..E7 全 PASS、
`A_NEW_REPRO_CLAIMS=ALLOWED`、`blocking_fail=0`；E6 的五个 term 全部从本 manifest 取值。

---

## ADR-C-010 `work/decisions/` 正式登记处：设计与四条验收（待办 2 / 执行单 P0-4）

**依据**：增补五 §9-C④、**裁定 29.5 第 1 条（P1 → P0）**、执行单 P0-4、裁定 21（判据单一来源）。
**动机是本轮实测的损失**：0929 检修把 `/root/venvs/` 与 `~/.codex/sessions/` 一起清掉，
环境靠 lock 复现了、**对话历史不可复现**（ADR-C-006 与裁定 29.5 独立得出同一结论）；
而「同一条裁定在三个地方有三种措辞、没人能说出哪份是权威」这件事 D 自己在本轮撞上了。
**实现**：`scripts/c_decisions_registry.py`；**判据**：`scripts/c_selfcheck_decisions_registry.py`
（53 条，全部双向）；**口径**：`work/decisions/registry/README.md`。本条不抄判据。

**决定 1**：原子单位 = **一条决定一文件、内容寻址、只追加、撤销靠新事件指向旧条目**
（与 `supersedes` 同型）。目录：`entries/<id>__<sha256_12>.json`（权威）、
`events/<seq>-<kind>-<sha256_12>.json`（权威）、`index.json`（**派生**，可随时 `rebuild-index`）。
`status`（`active`/`retired`/`superseded`）由事件流**派生**，从不被改写出来。

**决定 2（本轮修的真 bug 之一）**：条目要分**两层哈希**。
payload（决定了什么）与簿记（`version_seq`/`registered_at`/`registered_by`）必须分开：
① `registered_at` 若算进判重分母，「同内容重复登记 ⇒ 拒绝」就只在两次调用**落在同一秒**时成立，
跨秒静默多出一版 ⇒ 靠运气的判据；② `version_seq` 若算进判重分母，重复登记会因版本号 +1
而哈希不同 ⇒ 去重护栏被完全打穿（本轮实测到过）。判重按 `payload_sha256`，
文件名哈希按全量 ⇒ 两层各有牙（`tampered` / `payload_sha256_mismatch`）。

**决定 3（本轮修的真 bug 之二）**：`version_seq` 是**版本顺序的权威键**。
此前版本顺序按文件名排，而文件名尾是内容哈希 ⇒ **字典序与写入时间无关** ⇒
「最新版」随机落错 ⇒ 旧 ack 永远显示 `matches_current_content=true`（判据没有牙）。
不用 mtime（文件系统状态，可被碰）。同 id 多版本**全部保留**（append-only）。

**决定 4（本轮修的真 bug 之三）**：撤销的牙必须**分两类判**，合并判会恒红。
`authority_pointers`=「我拿它当权威」⇒ 权威已死而引用方仍 `active` = `dangling_authority`（真红）；
`supersedes`=「我取代它」⇒ 被取代者**非 active 才是传导成功**，仍 `active` 才是
`supersede_not_propagated`（取代只写了一半，缺事件）。
此前把两者并成一个集合判 ⇒ 「传导完成」也报红 ⇒ 判据恒红 ⇒ **永不报警等于没有报警**
（与裁定 31.3 对 `exoneration_disagreement` 的要求同型）。
**验收 2 的硬要求已满足**：造一条撤销 ⇒ 被撤条目 `status` 真的变 `retired`，
**且原文件逐字节不变**（自检同时比 sha256 与 mtime）。

**决定 5**：并号扫描面**宁宽勿漏**，期望值**不得硬编码**。
下一号 = 「`work/decisions/` 全量 markdown ∪ 登记处」里该号段最大序号 + 1；
扫描面不写死成固定清单（今天实测到 `decisions_20260928_B.md:822` 补发 `DR-014`，
写死就扫不到 ⇒ 撞号）。自检里期望值由**第二份独立最小实现**现场重算，
不钉常数 —— 钉死 `DR-014` 那条今天就过期了一次（别线一发新号它就腐烂），
而它腐烂的样子是「测试红」，看起来像实现错 ⇒ 会诱导人去改对的实现。
`DR-D<n>`(D) 与 `DR-0<n>`(B) 共享 `DR-` 前缀但**不共享号段**；号段与线不符 ⇒ `add()` 拒。

**决定 6（验收 4）**：登记处**不重造口径**。摄取历史条目一律 `statement_kind="pointer_only"`
（标题 + 源文件锚点 + 源文件 sha256_12 + 行号，**不抄正文**）；
任何 `full_text` + `criteria` 的条目 ⇒ `criteria_duplicated` 红。
判据的唯一来源仍是门禁/自检脚本本身。

**决定 7（验收 3）**：`requires_ack_from` 三态——`None`=由 `affects` 推；
`()`=**显式**不设 ack 义务（摄取历史条目用它：ack 纪律从登记处生效那天起算，
**不追溯**给 73 条老裁定补 ack）；非空=指定哪几线必须 ack。
**作者线不给自己 ack**；ack 事件记下**当时条目的内容哈希**，条目换版本后旧 ack 自动 `stale`；
未 ack 的**可见**（`list --missing-acks` / `index.json.n_missing_acks`），不靠人记。

**现状（2026-09-29 16:2x 实测）**：已摄取 **73** 条历史决定（A=17 / B=14 / C=8 / D=34），
全部 `pointer_only`，`verify` **0 red / 0 warn**，`index.json` 可由 entries+events 重算，
自检 **53/53 PASS**（产物 `runs/infra/c_decisions_registry_selfcheck.json`）。
73 条老格式条目已重摄取以补齐 `version_seq`/`payload_sha256`（当时 **0 条事件** ⇒
没有任何事件引用条目哈希 ⇒ 无损）；旧字节整目录归档在
`/workspace/mnt/sppro/yhzhang91/recycle_bin/c_decisions_registry_pre_payload_sha_20260929_161643/`
（含 `WHY_RECYCLED.md`），**未用 `rm`**。
**本条与 ADR-C-009 自己也在登记处里**（`requires_ack_from=A,B,D`）⇒ 谁还没 ack 可查。

---

## ADR-C-011 P1-5：`physical_fact` 接线（准入闸 / 账本 fail-closed / 发布包身份红线）

**依据**：增补五 §9-C③、**裁定 29.1（引用锚在 build 轴）**、执行单 P1-5、
以及执行单「与 B §5 的交点」（v1.6 落地会升 `GATE_BUILD`）。
**判据不在本条里**（裁定 21）：准入规则在 `registry/verdict_identity.py::admit_as_physical_fact`
（规则原文 = 该模块的 `ADMISSION_RULE`），接线自检在 `scripts/c_selfcheck_verdict_wiring.py`（48 条）。

**决定 1（准入闸，单一来源）**：**只有 `usable_for == physical_fact` 且 `gate_build` 等于
「调用时」的门禁现值**才准入；其余一律**拒收并回显理由**（不是 warn、不是静默降级）。
比的是**调用时**的现值（`current_gate_identity()`），不是记录被解析时存下的那份 `gate_current`
—— 判据在脚下移动过就必须重新对表，这正是 v1.6 那一刀能落下来的原因。
闸**返回判定**而不抛错：这样「拒收」本身可以留档（账本写成事件），
需要硬拒的调用方（账本、发布包）自己按 `admitted` 抛。

**决定 2（账本 fail-closed）**：`ingest_runtime_result` 必须**显式声明本次入账的依据**，二选一——
`verdict=<裁定身份>` 走准入闸，或 `observation_only=True` 声明「这是 env 直接产出的原始观测、
不是被门禁分级的裁定」。两者都不给 ⇒ 抛 `VerdictAdmissionError`，且**一行都不写**。
默认拒绝的理由：不声明就入账，等于把「没有身份」和「忘了闸」在账本里混成同一种行，
而下游会把它当数字用（增补五 §9-C③ 点名的事故形状）。
`observation_only` 那条也不是白走的：账本记一条 `verdict_identity_absent` 事件，
写明「没有 `gate_build` ⇒ 不得被翻成 `DirectionScore` 进发布包」。

**决定 3（拒收留档，但不进事实表）**：新增三个事件种类
`verdict_admitted` / `verdict_refused` / `verdict_identity_absent`（都在账本的**封闭词表**
`EVENT_KINDS` 里，不是绕过校验塞进去的）。拒收事件的 payload 自带
身份 + 拒收理由 + 当时的门禁现值 + `frames_written=false`，且**帧 0 / 标签 0**。
`on_refusal="raise"` 也**先写事件再抛** ⇒ 抛错不等于丢证据。
**重判是追加**：旧事件序列必须是新事件序列的**前缀**（自检按前缀判定，不按「多了几条」——
后者抓不到「改写中间一条」，而前者能）。

**决定 4（发布包身份红线）**：`DirectionScore` 的身份是**字段，不是注释**
（`gate_version` / `gate_build` / `gate_spec_sha256` / `verdict_sha256` / `measurement_valid` /
`usable_for` / `provenance_kind` / `is_current_build` / `superseded_by` / `regraded_from`）。
`build_bundle` 默认 `require_verdict_identity=True`：缺身份 / 档位不是 `physical_fact` /
自称非现构建 ⇒ 抛 `VerdictIdentityViolation`（与「双向同 checkpoint」红线同级，同属 `BundleError`）。
给了 `gate_current` 就再逐方向比 `gate_build`，不符 ⇒ **拒收，不是 warn**。
**两条红线互相独立**：关掉 `require_verdict_identity` **也**拦得住构建不符；
逃生口（`require_verdict_identity=False` 且不给 `gate_current`）是**显式**的，不是默认。

**决定 5（不抄词汇表）**：`release_bundle` 里的 `physical_fact` 这个词**import** 自
`registry/verdict_identity.py`，不在本模块抄一份常量。抄一份就有了第二份口径，
两边一旦漂移，「发布包只收 physical_fact」会变成一句**看不出错**的话。
延迟 import：不让发布包模块在导入期就拉起裁定层（它又会去加载上游门禁模块）。

**决定 6（预先写明后果，不靠人记）**：B 的 v1.6 落地会升 `GATE_BUILD` ⇒ 现存 48 条
`physical_fact` 会整批变成「与门禁现值不符」⇒ 准入闸全部拒收、`physical_fact` **48 → 0**。
**那是正确行为，不是回归红点**；正确动作是在 v1.6 上重新出裁定，不是把闸放宽。
这句话写进了**三处代码内的规则原文**（`ADMISSION_RULE`、`ingest_runtime_result` docstring、
`_require_verdict_identity` docstring），并且自检里有一条断言专门核它还在。

**边界申报（请 D 核）**：本轮动了 `registry/release_bundle.py`。它不在交接摘要列的
C 写入边界清单里，但 **D 在增补五 §9-C③ 点名了 `registry/release_bundle.py:102` 的
`DirectionScore` 要补身份字段**（`supervisor_memo_20260928.md:334`），且执行单 P1-5 的验收
（「`DirectionScore` 自带 `gate_build` + `usable_for`」）不改它就无法满足 ⇒ C 按派工执行。
同时改了两个**无 `c_` 前缀但属 C 线**的自检（`selfcheck_release_bundle.py` /
`selfcheck_ledger_views.py`，两者 docstring 自述「C 线自检」，且都在 C 的回归套里）：
前者补 fixture 身份 + 放行 `gate_current`/`require_verdict_identity`，后者补 `observation_only=True`。
**未改** `harness/contracts.py`、`harness/runtime_adapter.py`、`configs/` 与 A/B/D 的产物。

**实测**：新自检 `c_selfcheck_verdict_wiring.py` **48/48 PASS**；既有三套未回归——
身份层 156/157 PASS + 1 SKIP、账本视图 **84/84**、发布包 **27/27**。

---

## ADR-C-012 P1-6：逐臂内容寻址 run manifest（与 git **互校**，三字段同源同义）

**依据**：增补五 §9-C⑤、执行单 P1-6（新增「三字段与 P0-2 同源同义，不要各写一套」）。
**实现** `scripts/c_run_manifest.py`；**判据** 同文件 `--selftest`（15 条，含反面牙）。
git 已 init ⇒ manifest 不是**替代** git，而是与 git **互校**：git 管代码版本，
manifest 管「这一臂的这次评测由哪些内容组成」。

**决定 1（同源同义，可核不靠注释）**：每臂的 `gate_build` / `sha256` / `is_current_build`
一律取自 `vi.artifact_identity()`，本文件**不重算**。三件事一起保证它：
① `build_manifest` 里**当场核对**三字段与嵌入的 `artifact_identity` 逐值相同，不同源就抛错；
② 来源映射（`sha256` ← `artifact_identity.source_sha256` 等）**写进产物**，读者可核不必读代码；
③ 自检逐字段造反例（三个字各试一次）。

**决定 2（自检设计的一般教训：变异体要造**真分歧**）**：最初那版反面牙是改
`artifact_identity` 本身 —— **无效**：三字段与嵌入的身份同出一次调用，一起变就永远相等，
判据**恒过**。要模拟的是「取值路径被换掉」，所以变异点必须是 `arm_entry`
（让顶层三字段与嵌入身份真的分家）。**变异体若不能造出分歧，那条判据就是装饰。**

**决定 3（绑定项按 owner 分两类，绝不代填）**：C 能自己算的（`requirements.lock.txt`、
门禁模块、`verdict_identity.py`、`ledger.py`、`release_bundle.py`、本脚本）就地取 sha256；
**只有 A 能给的**（`model_safetensors_sha256` / `dataset_sha256` / `pinned_object_seed` /
`eval_seeds` / `probe_build`）**不代填、不猜测** —— 填了就是把 A 的产物身份写成 C 的口径。
没给就如实记 `run_bindings_availability="not_bound"` + 点名缺哪几项 + 为什么。
**git 归属由 B 提供**（护栏 8：C 不执行 git 写命令，也不代 B 认定 commit 归属），
没给记 `status="not_available"`，不编。

**决定 4（内容寻址）**：分母 = `run_id` + `gate_current` + `arms`（规范化 JSON 的 sha256）。
改任何一臂的任何绑定都换哈希；同输入必同哈希（自检双向都验）。

**决定 5（manifest 必须**现算**，不能读旧清单）**：三字段要反映**调用时**的门禁现值，
否则门禁升版后 manifest 会**假装**还是当前构建。为此给 `inventory()` / `scan_dir()`
加了 `collect=` **出参**：活对象不能塞进返回值 —— 那个返回值是要 `json.dumps` 的
（`c_verdict_identity_inventory.json` 就是它），塞进去会写不出来。
`collect` 交回的是**改判之后**（`regrade_pending_impl` 之后）的记录，与清单同一批对象。

**实测**：`runs/infra/c_run_manifest_20260929.json`，**246 臂**，
`manifest_sha256=9d41d6917b15f73edd26b9eeb5afc16ecd9e5a917e1b7e3168fc62f9162a3eb1`，
`is_current_build` **54 true / 192 false**，`usable_for` 分档与清单逐项吻合
（`physical_fact 48 / stale_build_evidence 150 / unidentified_build 24 / invalid_measurement 23 /
not_a_verdict 1`），`distinct_gate_builds=16`，
A 侧绑定 **246 臂全部如实记 `not_bound`**（A 未提供，C 未代填）。

---

## C 线待办（原表 12:25 现状保留为历史；**16:2x 结案增量见下表**）

### 结案增量（2026-09-29 16:2x，依据 = 产物 mtime / D 的裁定，不是自述）

| 原表 # | 事项 | 16:2x 状态 |
| --- | --- | --- |
| 2 | `work/decisions/` 正式登记处（P0-4） | **结案**（ADR-C-010）：73 条摄取、`verify` 0 red/0 warn、自检 53/53；四条验收逐条有牙且配反面用例 |
| 9 | 第六档 5 条历史构建记录的归属（提请裁定） | **结案**：D 判 (b) + `provenance_kind` 子标签（裁定 31.4），C 按批准的实施方式落地，**裁定 37.1 验收通过** |
| 10 | `lerobot_act` / `lerobot_eval` 两个环境重建 | **C 侧结案**：B/A 重建后，**同一支探针**验出两个 venv 都是 `0.4.4` + `index_wheel/uv`（未改探针，符合 P0-3 验收）；`env_fully_restored=true`。装环境本身不在 C 的写入边界 |
| — | P0-1 / P0-2 / P0-3 + C-F1 / C-F2 | **全部结案**（裁定 37.1，15:3x）：`registry/verdict_identity.py` 的 `provenance_kind`/regrade/`artifact_identity`/`reconcile_exonerations`（对账只在 `is_current_build==true` 子集上做，跨构建改报 `stale_side_not_comparable`）；自检 156/157 PASS + 1 条诚实 SKIP |
| 1 | P1-5：`physical_fact` 接线 | **结案**（ADR-C-011）：准入闸只吃 `physical_fact` + 构建不符**拒收**（不是 warn）；账本 fail-closed；`DirectionScore` 10 个身份**字段** + `build_bundle` 两条独立红线；重判 append-only（前缀判定）。新自检 48/48，既有 156/157+1 SKIP、84/84、27/27 未回归 |
| 3 | P1-6：逐臂内容寻址 run manifest | **结案**（ADR-C-012）：246 臂、三字段与 P0-2 **同源同义**（当场核对 + 来源写进产物 + 逐字段反面牙）；A 侧绑定如实 `not_bound`、git 归属 `not_available`（都不代填）；自检 15/15 |
| 5 | T17 真帧版本 | **不动**（等 A 侧 2 项；B 已实测当前 2 项阻塞都在 A 侧） |
| 6 | ξ 锚 / 导出列变更（冻结面） | **不动**（D 不批准，裁定 29.5 第 3 条；等 P1-5 落定后一并看） |

### 原表（12:25 现状，保留为历史）

| # | 事项 | 依据 | 现状与阻塞 |
| --- | --- | --- | --- |
| 1 | P0-3 第二层：`DirectionScore` 增身份字段 + `ingest_runtime_result` 只吃 `physical_fact` + 重判走 append-only/撤销 | 增补五 §9-C③ | **部分解除，本轮仍不动**。实测 `runs/infra/c_verdict_identity_inventory.json`（9/29 09:39，当前构建 v1.4 / `b9379fdb1089`）：`physical_fact` 由 0 → **15**，但 15 条**全部**出自 `ckptseq/v14_crosscheck`；48 臂权威表所在的 `regate_current` 仍是 `stale_build_evidence 41 / invalid_measurement 7` ⇒ **48 臂表在当前构建下 `physical_fact` 仍为 0**。且 A/B 的免罪册分歧仍开着（`docs/a_handoff_to_b_probe_exoneration_gap_20260928.md`：25/22/1 vs 24/22/2），D 上午的 48 臂重判只在 `tmp/agentD_review_20260929/`（scratch，非权威产物）。按裁定 16 顺序纪律，此刻接线仍会在权威表刷新时重做一次。**ADR-C-007 更新（12:00 实测）**：门禁已升 `v1.5 / f19f61341cbe`（裁定 26 复签通过），B 的 `reclassification.json` 已重出为 `citable 25/22/1`，但被扫目录里 188 份 `gate_*.json` **没有一份出自当前构建** ⇒ `physical_fact` 由 15 → **0**，接线等于零输入；A 的 `arms_summary.json` 仍是 9/28 的 `v1.2.1 / e4f5ec887788`。**ADR-C-008 改判（12:25 实测）：阻塞解除 ⇒ 升 P0，可以接。**依据：裁定 28 免罪链路闭环 + B 的 v1.5 逐臂重判已落盘（清单 `physical_fact` **48**、目标臂当前构建那份 = `probe_exonerated` + `mv=true`）+ A 的迁移闸 D 实测 OPEN。**前置（§19 C④）**：读 **11:45 版**权威表，不要用 11:22 版（后者缺 `terminal_kind_coverage` 等三处字段）。**验收**：`ingest_runtime_result` 只吃 `physical_fact`、`DirectionScore` 自带 `gate_build` + `usable_for`、重判走 append-only/撤销 |
| 2 | ~~P1~~ → **P0**：`work/decisions/` 正式登记处（内容寻址 / append-only / 可撤销 / ack），摄取 DR-001/002 与增补裁定 8–28 | 增补五 §9-C④、**裁定 29.5 第 1 条** | **改判为 P0，且并号规则已给 ⇒ 无阻塞，可开工**：`DR-D<n>`=D 线裁定序号（本轮到 DR-D28）、`DR-00<n>`=B 线门禁/流程、`ADR-A-<n>`/`ADR-C-<n>`=A/C 线架构决定；原子单位 = **一条决定一文件、内容寻址、只追加、撤销靠新条目指向旧条目**（与 `supersedes` 同型）。依据是本轮实测的损失：venv 与 `~/.codex/sessions/` 同在 overlay 上，环境靠 lock 复现了、**对话历史不可复现**（ADR-C-006 与裁定 29.5 独立得出同一结论） |
| 3 | P1-5：逐臂内容寻址 run manifest | 增补五 §9-C⑤ | git 已 init（7 个 commit）⇒ manifest 从「替代 git」变成「与 git 互校」；仍需要 B 提供 commit 归属（C 不执行 git 写命令，护栏 8） |
| 4 | ~~T17 goal 贯通的 C 侧 3 项~~ | 增补三 §9-C、B 交接单 | **已结案（ADR-C-005）** |
| 5 | （新）真贯通的 A 侧 2 项到位后，重跑 T17 的**真帧**版本 | B 交接单 §5 | 等 A：`run_act_lift_runtime_failure_audit.py:36,39` 的 `goal_id` 硬编码 + policy 接收 goal。C 侧已就绪，A 到位后只需把真帧通道的 `goal_id` 换成方向性标签即可复测（无需改 learner） |
| 6 | （新）ξ 锚缺口闭合：BC 行的 C 可重建后，`bc_anchor_covers_xi1` 应转 `true` | B 交接单 §4、ADR-C-005 | 需 harness 纠正也走 request/commit（导出列变更 = 冻结面变更，§9.2），属 v4 既定项，需 D 批准动冻结面 |
| 7 | ~~增补六 §8-C 三条 P1（解释器探测 / env manifest 与断点 / `PENDING_IMPL` 第六档）~~ | 增补六 §0.2 第 2、3 条、§8-C1/2/3 | **已结案（ADR-C-007）** |
| 8 | ~~B 的 v1.5 逐臂重判产物落盘后复跑身份层自检~~ | ADR-C-007 §2.6、裁定 26 | **已结案（ADR-C-008 第 5 项）**：12:0x 产物落盘，复跑后 SKIP 转实测 PASS、`physical_fact` 0 → **48**、自检 129/129。注：第六档**未**清零（仍 5 条），因为那 5 条是历史构建的探针/锚点产物 ⇒ 转待办 9 |
| 9 | （新）提请 D 裁定：第六档现存 5 条**历史构建**记录（4 条 A 的故意被拒探针 + 1 条 v1.2.1 冻结锚点）的归属 —— (a) 留本档 / (b) 转 `stale_build_evidence`（C 倾向）/ (c) 另立一档 | 裁定 28.1/28.2、ADR-C-008 第 1 项 | 等 D 裁定。C **未自行改分级**；(b) 的实施已设计好（激活条件收窄为「该臂当前构建下无承载免罪的产物」，跨记录条件放 `inventory()`，留 `regraded_from`）。实测证据已写进清单的 `evidence_for_open_question` |
| 10 | （新）`/root/venvs/lerobot_act` 与 `lerobot_eval` **两个环境重建**（0929 检修同批清掉，C 实测 `/root/venvs/` 下只剩 rlrobot） | 裁定 29.4、ADR-C-008 第 2 项 | 属 **A/B 的环境责任线**（C 不代装）。C 已做的准备：pin 从 installer 解析回显（`lerobot==0.4.4`/`torch==2.6.0`/aliyun index）、三份盘上副本的 commit 已实测回显（均**不得**当 pin）、两份 0928 lock 已逐字节备份到 `runs/infra/c_lerobot_env_locks_backup_20260928/`（installer 会就地覆盖原件）。重建后**必须**重出 env manifest 并登记断点（裁定 29.4 对 A 的要求）；在此之前 A 不得声称任何新训练/新评测复现 |

## 卫生声明

- 全程未用 `rm`；新目录一律 `mkdir -p`，重建脚本与日志写在 C 自己的
  `runs/infra/c_env_rebuild_20260929/`。
- 未执行任何 git 写命令（DR-002 护栏 8 / DR-003 决定 8 单写者纪律）；
  本轮改动待 B 代提交。改动清单（ADR-C-005）：`harness/queue_td_learner.py`、
  `scripts/c_selfcheck_goal_conditioning_t17.py`（新增）、`scripts/c_contract_lift_smoke.py`、
  `scripts/c_learner_shard_smoke.py`、`scripts/c_run_all_selfchecks.sh`、
  `docs/c_t17_goal_conditioning_20260929.md`（新增）、
  `docs/c_handoff_to_b_t17_landed_20260929.md`（新增）、本文件（新增）。
- 追加改动清单（ADR-C-007）：`registry/verdict_identity.py`、
  `scripts/c_selfcheck_verdict_identity.py`、`scripts/c_run_all_selfchecks.sh`（再改）、
  `scripts/c_env_manifest.py`（新增）、
  `docs/c_env_manifest_and_pending_impl_20260929.md`（新增）、本文件（追加）。
  新产物：`runs/infra/c_env_manifest_20260929.json`、
  `runs/infra/c_full_regression_20260929_pm{,2}.log`、
  `runs/infra/c_verdict_selfcheck/<时间戳>/pending_impl/`（8 份合成裁定，数字无物理意义）、
  `tmp/agentC_probe_test_20260929/`（探测四路径副本 + 坏 lock 反证）。
  仍**未改** `requirements.lock.txt`、`scripts/setup_env.sh`、`configs/`、`daily_report.md`
  与 A/B/D 的任何产物目录。
- 追加改动清单（ADR-C-008）：`registry/verdict_identity.py`（裁定 28 的 retired 标注与
  `pending_impl_ruling` 诊断块）、`scripts/c_selfcheck_verdict_identity.py`（+3 条断言）、
  `scripts/c_env_manifest.py`（lerobot 探针分类 / `env_fully_restored` / GPU reason /
  两处 bug 修正）、`scripts/c_run_all_selfchecks.sh`（注释口径）、
  `docs/c_env_manifest_and_pending_impl_20260929.md`（追加 §7）、本文件（追加）。
  新产物：`runs/infra/c_lerobot_env_locks_backup_20260928/`（两份 lock 的逐字节备份）、
  `runs/infra/c_full_regression_20260929_pm3.log`。
  仍**未改** `configs/`、`daily_report.md`、`scripts/setup_env.sh`、
  `scripts/install_lerobot_act_env.sh`、`registry/README.md`（见 ADR-C-007 的文档漂移登记）
  与 A/B/D 的任何产物目录；未执行任何 git 写命令；未用 `rm`。
- **工作区 AGENTS.md 合规复核**（`/workspace/mnt/sppro/yhzhang91/AGENTS.md`，位于本仓之上、
  不会随 developer message 自动带入，本轮显式读过）：① 全程未用 `rm`／`find -delete`／`unlink`；
  ② 未触碰 `datasets/` 与 `platform.db*`；③ 中间产物按第 5 条放在**来源可识别**的子目录
  （`runs/infra/c_*`、`tmp/agentC_probe_test_20260929/`）。
  关于「临时工作统一放 `scripts/lomoon_claude/tmp/`」那一节：C 沿用 D 在 增补六 §0.2 第 4 条
  已登记的做法（留在仓内 `tmp/agentC_*/`，来源可识别），**不迁移** —— 迁移会打断
  `docs/c_env_manifest_and_pending_impl_20260929.md` 与 ADR-C-007 里已落盘的路径引用；
  `tmp/` 是否纳管或忽略属 DR-003 范围，仍由 B 决定，C 只登记。
- **未改** `daily_report.md`：该文件当前有 A 线在途改动（`git status` 显示 M），
  且四个智能体本轮并发运行，对同一个 144 KB 共享文件并发写正是 ADR-C-004 记录过的
  假红/竞态来源。C 的 9/29 条目请日报整理线从 `docs/c_t17_goal_conditioning_20260929.md`
  与本文件取。
- 未写 A/B/D 的任何产物目录；复跑 B 的牙齿自检时用 `--json-out` 把输出改到 C 的目录。
- 追加改动清单（ADR-C-009 / ADR-C-010，16:2x）：`scripts/c_decisions_registry.py`
  （两层哈希 `payload_sha256` + `version_seq`、`verify` 分判 `dangling_authority` 与
  `supersede_not_propagated`、`source_docs()` 全量扫描面、`next_id(sources=)` 可隔离、
  `_resolve_ref()` 确定性解析）、`scripts/c_selfcheck_decisions_registry.py`
  （编号期望值改为第二份独立实现现场重算、+5 条双向断言 ⇒ 48 → **53** 条、
  修 `_unreadable` 按键过滤那处恒真）、`work/decisions/registry/README.md`（新增，口径）、
  `work/decisions/registry/entries/`（73 条重摄取，旧字节已归档）、
  `work/decisions/registry/index.json`（派生，`rebuild-index`）、本文件（追加）。
  仍**未改** `configs/`、`daily_report.md`、`scripts/setup_env.sh`、任何 `requirements*.lock.txt`
  与 A/B/D 的产物目录；未执行任何 git 写命令；未用 `rm`
  （重摄取前把旧 `entries/` 整目录 `mv` 到
  `/workspace/mnt/sppro/yhzhang91/recycle_bin/c_decisions_registry_pre_payload_sha_20260929_161643/`
  并写了 `WHY_RECYCLED.md`）。
- **申报（D 附记 2 §5 / 备忘 §54 台账要求）：`runs/infra/maniskill_state_probe_20260929/`
  不是 C 的，C 从未创建、从未写入该目录。** 依据（只读实测，不采信自述）：
  ① 该目录的写入面自述（其 `README.md` §0，mtime **16:09**）包含
  `docs/infra-gpu-render.md`、`runs/infra/robosuite_throughput_probe_20260929/`、
  新建 `.codex-persist/envs/maniskill_probe/` venv、`.codex-persist/sapien-cache/`
  —— **这四项没有一项在 C 的写入边界内**；
  ② 主题是 ManiSkill3 state 档可行性 + Vulkan/PhysX，与 C 的台账/数据桥/env manifest 三线无关；
  ③ C 本轮全部产物都在 `runs/infra/c_*` 与 `runs/infra/c_env_manifest_selftest/` 下（带前缀）。
  该目录的作者已在自己的 `README.md` §0 完成归属申报（含「保持原名不重命名，
  因为 D 已按此路径点名，改名会让引用失效」的理由）⇒ **D 台账上那一项可以由 D 直接销账**。
  C 按 D 的「如果不是你的：不用管」执行：**未改其名、未改其内容、未引用其结论**
  （D 也已明示现在不批准把它的结论当口径引用）。
- 追加改动清单（ADR-C-011 / ADR-C-012，17:0x）：`registry/verdict_identity.py`
  （新增 `admit_as_physical_fact` / `direction_identity` / `ADMISSION_RULE` /
  `DIRECTION_IDENTITY_FIELDS` / `_field`；`inventory()` 与 `scan_dir()` 加 `collect=` **出参**）、
  `harness/ledger.py`（`VerdictAdmissionError`、`_admit_verdict`、`ingest_runtime_result` 的
  fail-closed 准入闸、`EVENT_KINDS` 加 3 个种类）、`registry/release_bundle.py`
  （`VerdictIdentityViolation`、`DirectionScore` 10 个身份字段、`_physical_fact_token`、
  `_require_verdict_identity`、`build_bundle` 的 `gate_current` / `require_verdict_identity`）、
  `scripts/c_selfcheck_verdict_wiring.py`（**新增**，48 条）、`scripts/c_run_manifest.py`
  （**新增**，真 manifest + 15 条 `--selftest`）、`scripts/selfcheck_release_bundle.py`
  （fixture 补合法身份 + `build_ok` 放行两个新参数）、`scripts/selfcheck_ledger_views.py`
  （调用点补 `observation_only=True`）、`scripts/c_run_all_selfchecks.sh`（14 → 16 项 +
  `SCRIPT_ARGS` 让「默认产出真产物」的脚本在回归里跑自检模式）、
  `work/decisions/registry/`（ADR-C-009…012 四条新条目 + 派生索引）、本文件与
  `docs/c_env_manifest_and_pending_impl_20260929.md`（追加）。
  新产物：`runs/infra/c_verdict_wiring_selfcheck.json` 与其合成账本目录、
  `runs/infra/c_run_manifest_20260929.json`、`runs/infra/c_run_manifest_selftest.json`、
  `runs/infra/c_env_manifest_regression.json`（回归专用，**不覆写** A 线 E6 在读的权威快照）。
- **边界申报（请 D 核，不静默扩权）**：本轮动了 `registry/release_bundle.py`。
  交接摘要列的 C 写入边界里只有 `registry/verdict_identity.py`，**没有** `release_bundle.py`；
  但 D 在 **增补五 §9-C③ 点名了 `registry/release_bundle.py:102` 的 `DirectionScore`**
  要补裁定身份与有效性字段（`supervisor_memo_20260928.md:334`），0928 备忘「C（账本/数据桥线）」
  一节也把该文件列在 C 名下，且执行单 P1-5 的验收（「`DirectionScore` 自带 `gate_build` +
  `usable_for`」）不改它就无法满足 ⇒ C 按派工执行，并在此显式申报，而不是当作默认权限。
  改动是**加法式**的：新字段全部带默认值（向后兼容），新红线默认开但留**显式**逃生口。
  同型申报：改了 `scripts/selfcheck_release_bundle.py` 与 `scripts/selfcheck_ledger_views.py`
  —— 两者**无 `c_` 前缀**，但 docstring 自述「C 线自检」、测的是 C 的模块、且都在 C 的回归套里
  （前缀约定晚于这两个文件）。**未改** `harness/contracts.py`、`harness/runtime_adapter.py`、
  `configs/`、`daily_report.md`、`scripts/setup_env.sh`、任何 `requirements*.lock.txt`
  与 A/B/D 的产物目录；未执行任何 git 写命令（本轮 B 已在 16:26 / 16:31 代提交 C 线增量，
  HEAD `4f5d378`）；未用 `rm`。

---

## ADR-C-013 冻结收尾（裁定 38.4 / 39.2）：时序诚实登记 + 待办 5/6 终局 + 两份移交交付物

> 本条**追加在「卫生声明」之后**，是为了不就地改写既有小节（append-only 纪律同样适用于 C 自己的
> 决定文档）。编号接续 ADR-C-012。

**依据**：`rl_harness_supervision/d_freeze_abc_20260929.md`（16:58）§0 / §3-C1…C5 / §4 / §5.3；
`supervisor_memo_20260929.md` §58（裁定 38.4）、§59 台账与「仍未裁的项」、增补十六 §60–§62（裁定 39.1 / 39.2）；
C 的 17:08 回流单 `docs/c_handoff_to_d_p1_landed_20260929.md`。
**判据不在本条里**（裁定 21）：本条是**状态登记与移交**，不新增任何判据。

**决定 1（时序诚实登记，P0）**：冻结单 §3-C3 说「P1-5 / P1-6：登记为冻结时状态，**不追做**」，
而事实是 C **在读到冻结单之前**（16:40–17:06）已经把它们做完了（冻结单 16:58 落盘）。
处置三条：① **不自行回滚**（回滚要动三个模块、会制造新红点，且"回滚"不是 C 的权限）；
② **不声称合规**（"不追做"与"已做完"不能混为一谈）；③ 请 D **二选一**：追认，或令回滚并指定范围。
**在 D 处置之前，C 不再对 `harness/ledger.py` / `registry/release_bundle.py` / `registry/verdict_identity.py`
做任何进一步改动。** 时序用 mtime 说话（`docs/c_env_manifest_and_pending_impl_20260929.md` §9.0 有逐时刻表），不用自述。

**决定 2（待办 6 终局 = 不批准）**：D 已在 §59 明写「**C 待办 6（冻结面变更）不批准**」，
并把它列入「仍未裁的项（冻结后不再推进，登记为冻结时状态）」。⇒ **结案为不批准**。
C **从未**动过 ξ 锚 / 导出列（冻结面一处未破）；这也**回答了** C 在 17:08 回流单 §2.2 的提问 ——
那个问题不再悬着，不需要 D 再答一次。

**决定 3（待办 5 终局 = 冻结期内不可能推进）**：待办 5（T17 真帧版本）需要 `lift_B_to_A` 的真帧
teacher 数据（现 **0 行**）；A 的 (乙) 48 臂跨断点重跑已被**取消**（冻结单 §1.1：它只服务被
`01_开发技术方案.md:5` 排除的 ACT 线，跑完反而增加误读成本）。⇒ 前置在冻结期内不会产生，
登记为**冻结时状态**，**不追做**。C 线待办表由此**清空**（1/2/3/4/7/8/9/10 结案，5/6 冻结时状态）。

**决定 4（主交付物 = A2/B2 复用清单，并补一条新发现的**失败形态**）**：
`docs/c_reuse_manifest_for_a2_b2_20260929.md`（8 模块 × 三档「可直接接 / 必须改 / 已知缺口」，
每条带行号或可复跑命令；**没有行号的判断不进表**）。D 要求点明的「视觉表征缺失 P2 → P0」在 §2，
并附三条实测：① C 交付面里视觉通道 **0 处代码**（词边界 grep，命令原样贴出）；
② `harness/obs_store.py` 能存 uint8 图像但 `np.savez` **不压缩**（容量数字标注为**推算**，非实测）；
③ 同内容不同采样时刻**硬拒**（`:157`）⇒ 真相机重复帧的触发面**未实测**，C **不主张它一定发生**，
只要求 A2 接真帧前先实测。
**新发现（本轮只读分析，此前未登记）**：`harness/queue_td_learner.py:134`–`:135` 的 `_obs_vector`
只挑 `state` / `environment_state` 两个键 ⇒ **混快照（状态 + 图像，正是 π₀.₅ 的形态）下图像键被静默丢弃，
宽度检查还会通过**。此前只登记了"视觉表征缺失"（**能力**缺口），现在补上它的**失败形态**：
三种情形里只有这一种是静默的（另两种都 `LearnerRefused`，`:137`/`:139`），而**静默失败不会让人停下**。
⇒ 给 A2/B2 的硬要求：obs 键消费必须**白名单 + 断言全覆盖**（存进去的键集合与消费掉的键集合逐键比对，
有剩余就拒）。**C 未改 `_obs_vector`**（冻结单 §3-C3；且它属"不追做"）。

**决定 5（`registry/` 维护权移交 B2，附四条已知限制）**：`docs/c_handoff_to_b2_registry_20260929.md`。
移交的是**机制**（两层内容寻址 / append-only / 撤销有牙 / ack 可核 / `pointer_only` 不重造口径）与工具、自检。
四条限制**逐条写明，不粉饰**：① `index.json` **非原子写**且 `verify` 不核它（`:507`–`:510`，
无 `flock`/`os.replace`）⇒ 四会话并发下会撕，但它是**派生**的，撕了 `rebuild-index`；
② **撤销的牙在真登记簿上从未被真实触发过**（`events/` = 0 个文件、`retired=0`）⇒ 现有证据来自
`selfcheck` 的**隔离沙箱合成用例**（数字**无物理意义**），B2 第一次真 `revoke` 前先用
`--registry <临时目录>` 演练；③ `acks/` 与 `revocations/` 是**早期设计残留空目录**，代码只 mkdir
`entries/`+`events/`（`:196`–`:197`）⇒ 不是权威、别往里写、C 未 `rm`；
④ **A2/B2 没有号段，且 `--line` 是 `choices=A/B/C/D`**（`:81`/`:702`/`:714`/`:739`）⇒
**B2 无法用自己的名字 `ack`**，而 `requires_ack_from` 是自由文本（`:310`/`:771`）⇒ 把 `B2` 填进 ack 义务
会造出**永远 `missing`** 的假红点（看着像"有人没认"，其实是"没人能认"）。**请 D 裁号段**；
裁之前 B2 只用 `annotate` / `verify` / `list`。
**本条（ADR-C-013）的 ack 义务只设 `D`**：不设 A/B（两线已冻结，设了就是永久假红点）、
不设 B2（工具无法记录它的 ack）—— 这是**按决定 5④ 的口径自我适用**，不是省事。

**决定 6（边界例外申报：`daily_report.md`）**：冻结单 §3-C1 要求「C 自查后**在日报里**点名『已登记』
并给出对应小节号」，而 C 的写入边界明写**不改 `daily_report.md`**（`d_handoff_to_c_20260929.md:173`）。
处置：按 D 的**新指令**执行（新指令覆盖旧边界），但**显式申报为边界例外、不当默认权限**；
执行方式受限三条 —— **只追加一节**（`>>`，不改写任何既有行）、追加前先 `git status` + `tail`
（裁定 39.2：四会话并发，追加共享文件前必须先看）、追加后立即核 `wc -l` 与文件尾。
**同型申报**：本轮仍改了 `registry/release_bundle.py`（P1-5，17:08 回流单 §2.1 已申报，**D 尚未追认**）。

**决定 7（冻结后 C 线的行为约束）**：不新开任务、不改复用清单里那 8 个模块、
不主动重跑探针（含 `--measure-import-surface`）、**不自行复活**（须 D 登记 + 用户确认，冻结单 §0 第 3 条）；
仅在 D 或 B2 明确要求时提供**只读**复核。仍开着的两处**都在 D 手上**：
① `registry/release_bundle.py` 写入边界追认；② 决定 1 的时序处置（追认或令回滚）。

**可复用的一般规则（从本条抽出）**：**「已做完」与「不该做」必须分开登记。**
并发下最省事、也最坏的做法是把两者混成一句"已完成派工"——它让监管方失去处置窗口
（追认还是回滚，是两个不同的后果）。时序一律用 **mtime / sha256 / rc** 说话，不用自述。

---

## ADR-C-014 登记处 CLI 的 `ack` / `annotate` **崩溃**：自检走 API、用户走 CLI ⇒ 两条路径不同源

> 追加在 ADR-C-013 之后（append-only，不就地改写既有小节）。**这是 C 在执行冻结单 §3-C5
> （把 `registry/` 移交 B2）时自己撞出来的真红**，不是 D 或 B2 报的。

**依据**：冻结单 §3-C5（移交 `registry/` 维护权）、裁定 3 与裁定 31.3（恒真判据家族）、
裁定 37.4（旁挂散文与判据不同源）。**判据不在本条里**（裁定 21）：实现在
`scripts/c_decisions_registry.py`，牙在 `scripts/c_selfcheck_decisions_registry.py` 的第 9 案。

### 事实（实测，命令与 traceback 原样）

```console
$ python scripts/c_decisions_registry.py annotate --id ADR-C-013 --by C --reason "..."
Traceback (most recent call last):
  File ".../scripts/c_decisions_registry.py", line 783, in main
    kind = {"ack": "ack", "revoke": args.kind, "annotate": "annotate"}[args.cmd]
AttributeError: 'Namespace' object has no attribute 'kind'
```

`ack` **同型崩溃**（同一条语句）。`revoke` 正常（因为它**有** `--kind`）。
⇒ 移交给 B2 的登记处，**验收 3（ack 可核）与批注路径在 CLI 上是死的**：
`list --missing-acks` 能看，但**没有任何一条线能通过命令行 ack**。

### 根因（一句话）

字典字面量的**三个值会先全部求值**，再按键取 —— 而 `--kind` 只挂在 `revoke` 子命令上
（`:725`）⇒ `ack` / `annotate` 也会去读 `args.kind`，`Namespace` 上没这个属性 ⇒ `AttributeError`。

### 为什么 53/53 全绿的自检一条都没抓到

前 8 案**全部在进程内调 API**（`reg.append_event("ack", ...)`、`reg.add(...)`、`reg.verify()`），
**没有一条经过 argparse / CLI**；`verify` 也不跑 CLI。
⇒ 缺陷类 = **「被测对象与用户使用的对象不是同一个」**。它与"恒真判据"同族但**方向相反**：
不是判据不看东西，而是判据**看的是另一个东西**（库），而用户用的是命令。
**库能用不等于命令能用**，而自检只证明了前者，报告里写的却是"53/53 全过"。

### 决定 1：修**根因**，不打表面补丁

`scripts/c_decisions_registry.py:783`（**修前**行号，即 traceback 里那一行；修后为 `:786`）改成惰性取值：

```python
kind = getattr(args, "kind", None) or args.cmd          # 没有 --kind 就用子命令名
by=getattr(args, "by", None) or getattr(args, "line", None)
```

第二处一并修：原来写的是 `... or args.line`，而 `annotate` / `revoke` **没有** `--line`
⇒ 它没崩只是因为这两个子命令的 `--by` 都是 `required=True`（`or` 短路了）。
**那是运气，不是设计**；`--by` 一旦变成可选就会以同型方式崩。

### 决定 2：给判据**加牙**，而不是只修 bug（否则下一次同型缺陷照样漏）

新增第 9 案 `case_cli_surface`（**15 条检查**，自检 53/53 → **68/68**）：

- **子进程真跑 CLI**（`subprocess.run([sys.executable, scripts/c_decisions_registry.py, ...])`）：
  `add` / `ack` / `annotate` / `revoke` / `revoke --kind supersede` 全部 rc=0，
  且**逐条核后果**（事件真的落盘、`missing_acks` 真的少一个、`status` 真的由事件派生成
  `retired` / `superseded`、跑完 `verify` 仍 PASS）—— rc=0 但没写盘也算失败。
- **变异体（牙）**：把 eager 字典**塞回源码副本**（`runs/infra/c_decisions_registry_selfcheck/cli_surface/mutated_cli.py`），
  断言变异体上 `ack` 与 `annotate` **必须**失败且报 `AttributeError`；
  同时断言 `revoke`（本来就带 `--kind`）**仍然走通** ⇒ **牙不是恒红**。
- **变异生效本身也有一条断言**（`mutated_src != src and CLI_KIND_BUGGY in mutated_src`）：
  否则日后有人重构掉那一行，变异会静默失效、判据退化成恒真 —— 这正是 C 本轮
  自查出的缺陷 ⑥（标签与断言不同源）的同型防护。

### 决定 3：移交文档的数字**就地更新**，并把一句话改精确

`docs/c_handoff_to_b2_registry_20260929.md` §6.2 原文写「`events/` = **0** 个文件」。
本条追记产生了登记处的**第一条真实事件**（`events/0001-annotate-8dfe36a532f7.json`）⇒
现 **1 条（annotate）**。但「**撤销的牙在真登记簿上从未被真实触发过**」这句**仍然成立**
（`revoke` / `supersede` 事件仍为 **0**，`retired=0` / `superseded=0`）——
**annotate 不是 revoke**，不能拿它冒充"撤销已被真实用过"。数字与表述都已按此更新，不留旧值。

### 一般规则（可复用，交给 A2/B2 与 B2 建闸时用）

**被测对象必须与用户使用的对象是同一个。** 凡是"带 CLI 的工具"，自检里至少要有一条
**走子进程**的用例，并配一个「把 bug 塞回去」的变异体证明它能红。
反过来说：**「库的自检全绿」不得被写成「工具可用」**——这两个主张的对象不同。

### 边界

改的是 `scripts/c_decisions_registry.py` 与 `scripts/c_selfcheck_decisions_registry.py`
（都在 C 的 `scripts/c_*` 边界内）；**未改** `harness/`、`registry/*.py`
⇒ ADR-C-013 决定 1 里"处置前不再改那三个模块"的承诺**仍然有效**。
这**不是新开任务**（冻结规则 1）：C 是在执行 §3-C5 的移交时发现**要交出去的工具本身会崩**；
交一个 `ack` 命令会崩的登记处给 B2，等于没交。

### 冻结时状态表（2026-09-29 17:2x；原 16:2x 表与 12:25 原表都保留为历史，不就地改写）

| # | 事项 | 冻结时状态 | 依据 |
| --- | --- | --- | --- |
| 1 | P1-5 `physical_fact` 接线 | **已落地**（ADR-C-011），自检 48/48；**冻结后不再演进**；时序见决定 1 | §9.3 |
| 2 | P0-4 `work/decisions/` 登记处 | **已落地**（ADR-C-010），77 条 / `verify` 0 red 0 warn / 自检 53/53；**维护权移交 B2** | ADR-C-013 决定 5 |
| 3 | P1-6 逐臂 run manifest | **已落地**（ADR-C-012），246 臂 / 自检 15/15；**冻结后不再演进** | §9.3 |
| 4 | T17 goal 贯通 | **已结案**（ADR-C-005，裁定 37.x 验收） | — |
| 5 | T17 真帧版本 | **冻结时状态 = 不动**（冻结期内前置不会产生） | ADR-C-013 决定 3 |
| 6 | ξ 锚 / 导出列变更（冻结面） | **结案 = D 不批准**；C 从未动 | ADR-C-013 决定 2 |
| 7 | 增补六 §8-C 三条 P1 | **已结案**（ADR-C-007） | — |
| 8 | v1.5 逐臂重判后复跑身份层 | **已结案**（ADR-C-008 第 5 项） | — |
| 9 | 第六档 5 条历史构建记录归属 | **已结案**（D 判 (b)+`provenance_kind`，裁定 37.1 验收） | ADR-C-009 |
| 10 | 两个 lerobot venv 重建 | **C 侧已结案**（同一支探针验出 `0.4.4` + `index_wheel/uv`）；装环境不在 C 边界 | ADR-C-009 决定 1 |
| — | **A2/B2 复用清单** | **已交付**（冻结单 §3-C4，C 收尾里最有价值的一件） | `docs/c_reuse_manifest_for_a2_b2_20260929.md` |
| — | 两个探针目录补申报 | **已由作者自行闭合**（裁定 38.7④，17:03）；C 只读复核，未写入 | §9.2 |
| — | 冻结时点全量回归 | **17/17 项 exit=0**，`sha256=cd997d7afaaa1190…`（17:16） | §9.5 |

## 卫生声明（ADR-C-013 追加）

- 本轮（17:1x–17:2x）**只写**：`docs/c_reuse_manifest_for_a2_b2_20260929.md`（新增）、
  `docs/c_handoff_to_b2_registry_20260929.md`（新增）、
  `docs/c_env_manifest_and_pending_impl_20260929.md`（追加 §9）、本文件（追加 ADR-C-013）、
  `work/decisions/registry/`（`add` 一条 ADR-C-013）、
  `runs/infra/c_full_regression_20260929_freeze_171x.log`（新回归日志）、
  `daily_report.md`（**只追加一节**，见 ADR-C-013 决定 6 的边界例外申报）。
- **未改**：`harness/*.py`、`registry/*.py`、`configs/`、`scripts/setup_env.sh`、任何 `requirements*.lock.txt`、
  A/B/D 与 A2/B2 的任何产物目录、两个无前缀探针目录。
- 未用 `rm`（含 `work/decisions/registry/` 那两个残留空目录）；未执行任何 git 写命令
  （B/B2 是单写者，DR-003 决定 8）；未装任何环境、未下载任何权重
  （裁定 39.1 的三条红线一条未碰：torch 栈未动、未复用 `maniskill_probe`、未改 `lerobot_act`/`lerobot_eval`）；
  全程 CPU-only（`CUDA_VISIBLE_DEVICES="" MUJOCO_GL=egl OMP_NUM_THREADS=2`）；
  未对 `rlrobot` site-packages 做页缓存逐出（裁定 36.4）；未引用两个探针目录的**能力结论**（裁定 38.7②）。
- 本轮**无合成数字**；复用清单 §2.3 的容量数字是**算术推算**并已逐处标注「推算」；
  §2.4 的重复帧触发面**明确不主张一定发生**，只要求 A2 实测。
