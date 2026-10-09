# C 线登记（2026-09-28）：账本/视图三条实现缺陷的修复与撤销 / γ-n 单位处置 / 裁定身份层

登记方：智能体 C（实体运行时·事实账本·训练视图线）。
依据：`work/decisions/decisions_20260928.md` DR-001（`work/decisions/` 可写，**最小写入**：
只放路线变更 / 口径裁定 / 作废与 ack 登记；实验结果、产物、日志不写入本目录）、DR-002
（`git init` 许可 + 4 条护栏，其中护栏 8「单写者纪律」⇒ **C 不执行任何 git 写命令**，
本线只读过 `git log` / `git status`），以及监管备忘 增补五 §9-C ①②③④。
本文件是 C 线自己的登记，不修改 D 的 DR-001/DR-002 与增补条目、不修改 A 的
`decisions_20260928_A.md`、不修改 B 的 `decisions_20260928_B.md`。
编号用 `ADR-C-*`，与 A 的 `ADR-A-*` 同构，不占 D 的 `DR-*` 与 B 的 `DR-00x` 序列。
所有被引用的产物路径都在 `runs/`（不纳版控），本文件只写路径与判定，不抄结果表。

---

## ADR-C-001 消费 B 黄金值后裁定的三条实现缺陷（F1/F2/F3）：修复 + 撤销记录

- 时间：2026-09-28 20:00–20:40 实施，21:40 登记
- 依据：监管备忘 增补五 §9-C①（消费 `docs/b_golden/async_td_golden_v1.json`，consumer 明写 = C 线）
- 裁定：**规格对、实现错**（三条都是 C 的实现缺陷，没有一条是 B 的规格问题）；
  阈值一律未调，`targets` 仍按 1e-9 相对容差、`gradients` 仍按 `==0 / !=0` 严判。
- 变更内容（全部在 C 的写入边界内，`harness/data_bridge.py`）：
  1. **F1** E5-V1 前驱槽被过度删失：`C_next = U` 的判据改为「边界帧归属 + 归属正确前缀」，
     `next_queue` 的取值不变（接管后含 `None` 行是实测事实，不是缺陷）；
  2. **F2** 增补规格 §3.3-1 检不出来：`c_not_executed` 增加帧级
     `chunk_id / chunk_index / a_rl` 归属核对，豁免首槽与 partial-U；
  3. **F3** 删失口径只覆盖接管：新增宽口径
     `censored_slots / censored_slot_ratio / censored_requests / censoring_by_reason`
     与 `CENSORING_REASONS`（含 `deadline_miss`、`reward_unknown` 等）。
- **作废的历史结论 / 断言清单**（append-only：旧产物一字节未改，只登记作废）：
  | 作废项 | 原状 | 现状 |
  | --- | --- | --- |
  | `c_contract_lift_takeover_smoke` 的「前驱槽因队列被替换而隔离」 | 断言前驱必被 `c_next_not_equal_u` 隔离 | 作废：那正是 E5-V1 点名的过度删失。改为按 `--takeover-offset` 分支（`>0` 保留前驱 / `==0` 一并隔离 = E5-V2） |
  | 窄口径删失比例（只统计接管） | `censoring_ratio` 只反映接管 | 语义保留不改（A/B 的 smoke 在消费该字段），另加宽口径字段；**引用删失比例时必须写明是哪一口径** |
  | 「§3.3-1 已由 `c_not_executed` 覆盖」的旧判断 | 认为已覆盖 | 作废：帧级归属未核对，构造性反例可绕过（F2） |
- 性质：修实现缺陷 + 改强断言，**不改判据、不改单位、不构成 baseline 重置**；
  不改 A/B 的任何文件（B 的两个 `b_selfcheck_*.py` 只在 docstring 提到 `data_bridge`、未 import）。
- 回归验收方式：`scripts/c_selfcheck_golden_conformance.py`（读 B 的规格逐条断言 + 13 个变异体，
  含把 F1/F2 修复**之前**的行为重新注入的 M10/M11）与 `scripts/c_run_all_selfchecks.sh` 全量绿；
  产物 `runs/infra/c_golden_conformance.json`（带 `spec_sha256` 与 5 个实现文件的 sha256）、
  推导 `docs/c_golden_conformance_20260928.md` §2/§3/§7。

## ADR-C-002 γ / n 单位冲突的处置（P0-2）与「n 必须等于 n_action_steps」的落地

- 时间：2026-09-28 20:45–21:00 实施，21:40 登记
- 依据：监管备忘 增补五 §9-C②（两套约定必须收敛）与 §9-C④（真实帧路径的 `n` 必须等于
  `n_action_steps`，K=2 臂为 2，不得沿用规格算例的 n=6 —— D 点名的主线阻塞项）
- 口径裁定：
  1. **规格一致性路径只用 B 的数**：γ=0.9、n=6、H=20、`γ_slot=0.531441`、C=[0,6)/E=[6,12)/D=[12,20)，
     一律从 `spec["conventions"]` 读；`γ_slot` 只算一次并落盘，防「槽当折扣单位再幂一次」（`0.9^36`）。
  2. **真实帧路径的 γ/n 是假设值**：γ=0.99、n=4、H=8。产物显式标
     `n_assumed / gamma_assumed / unit_convention.status="assumed"`；
     `templates/项目参数模板.json` 的 `timing` 组八项仍全为 `null`，所以按**未定标**处理
     （20 Hz 只有文档口径，不等于已登记实测）。
  3. **定标状态与模板互锁（双向绊线）**：标 `measured` 而模板仍有 `null` ⇒ 抛；
     标 `assumed` 而模板已填满 ⇒ 断言失败。等 A 的延迟实测定标完成，这两处会主动报错。
  4. **定标状态跟着分片走**：`data_bridge.export_views(..., unit_convention=...)` 把它写进
     `views_*/manifest.json`（learner 是另一个进程，只留在 smoke 报告里等于换进程就丢）；
     γ/n/`γ_slot` 与本次导出不一致 ⇒ 抛，不许把规格约定贴到真机分片上。
  5. **n 守卫已落地**：`registry/verdict_identity.assert_n_matches_arm(n, read_arm_timing(eval_json))`，
     不一致就抛、不静默换算；实测 K=2 族 `n_action_steps=2`、K=4 族 `=4`，
     C 的真帧 smoke 用 n=4（与 K=4 族同尺度）。要解读 K=2 族必须以 `--n 2` 重建视图。
- **仍开着**（未作废、未完成）：把 n / γ 从假设值升为**实测值**的立项
  （`docs/c_golden_conformance_20260928.md` §8.1）。需要 A 的推理延迟分布（p50/p95/max）
  与位移增益（0.011 m/(dz·帧)）+ C 的调度契约一起定；验收判据是模板 `timing` 与
  `action_contract` 两组从 `null` 变实测值，且 `n` 能由延迟分布复算出来。
- 性质：纯标注与守卫，**不改任何已落盘数字**，不构成 baseline 重置。
- 回归验收方式：`c_contract_lift_smoke`(17) / `c_contract_lift_takeover_smoke`(31) /
  `c_learner_shard_smoke`(43) / `c_selfcheck_verdict_identity` 的 n 守卫正反两侧全绿；
  产物 `runs/infra/c_lift_contract_smoke.json`、`c_lift_takeover_smoke.json`、
  `c_learner_shard_smoke.json`（各含 `unit_convention`）。

## ADR-C-003 裁定身份与有效性层（P0-3 第一层）：只绑定、不重算、不重判

- 时间：2026-09-28 21:10–21:45 实施并登记
- 依据：监管备忘 增补五 §9-C③（裁定包 = {gate_version, gate_build, gate_spec_sha256,
  measurement_valid, 三套账, 五档 bucket, superseded_by}）与 增补六（再加两键
  `validity_class`、`blowup_threshold_source`；裁定身份必须含 `field_class`）
- 新增：`registry/verdict_identity.py` + `scripts/c_selfcheck_verdict_identity.py`（只读上游）。
- 口径裁定：
  1. **五档分级**（`usable_for`）：`not_a_verdict` > `unidentified_build` >
     `invalid_measurement` > `stale_build_evidence` > `physical_fact`。
     只有「当前 `gate_build` + `measurement_valid is True` + 不怀疑截断当失败」才是
     `physical_fact`；**账本与发布包只接受这一档**。
  2. **当前构建 import 上游、绝不硬编码**：读 `scripts/b_gate_controlled_success.py` 的
     `GATE_BUILD`（= 该脚本内容的 sha12）。实测 21:15–21:33 的 18 分钟内当前构建变了 4 次，
     写死版本号的实现当天就过期；跳变流水见 `runs/infra/c_gate_build_observed.jsonl`。
  3. **`validity_class` / `blowup_threshold_source` / `labels_reportable` 只从 A 的
     `arms_summary.json` join，C 不自己推导**（`scripts/summarize_lerobot_act_arms.py`
     是唯一生产者，免罪资格由它的 `probe_exoneration()` 断言 5 项准入）。
     匹配不上就记 `absent_from_arms_summary`；免罪**不得**简写成 `valid`。
  4. **两种取代关系分列**：C 的 `superseded_by` = 判据构建层面；A 的 `upstream_superseded_by`
     = 评测产物层面（留档原件 → `blindfix/` 重测件）。`field_class` 同样两份
     （本地这份裁定的 / A 权威行的 `arm_field_class`），两者不一致的记录**不得**当 `physical_fact`。
  5. **裁定 14（DR-D09）在 C 侧的读法**：失效模式标签只在权威行 `field_class == "strict"`
     且 `labels_reportable` 为真时可报；C 不改上游数字，`labels_reportable=False` 的行
     五档 bucket 原样保留但不进任何合计。
  6. **聚合报告不是裁定**：带 `arms`/`thresholds`、无 `accounts` 的文件（如
     `gate_threshold_sensitivity_A.json`）标 `not_a_verdict`，不得凭空当成一个臂。
- 实扫结论（快照，随上游移动）：123 文件 / 127 条逐臂裁定，同目录并存 **13 个** `gate_build`，
  当前构建下 `physical_fact` **0 条**；`<top-level>` 51 条留档裁定里可当事实的 **0 条**。
  ⇒ **按原计划把顶层 `gate_strict_*.json` 直接喂给 ingest 会存入一批旧口径数字**，
  这一步在第二层（见下）接好之前不做。
- 性质：只读上游、只新增 C 的文件；不改 A/B 任何产物，不重判任何裁定，不构成 baseline 重置。
- 回归验收方式：`scripts/c_selfcheck_verdict_identity.py` 84 项全绿（5 个变异体、
  独立复算分级、只读性的结构+实测双证据）；产物
  `runs/infra/c_verdict_identity_inventory.json`、`runs/infra/c_verdict_selfcheck.json`；
  设计与两处被自检抓出的真 bug 见 `docs/c_verdict_identity_20260928.md`。

## ADR-C-004 自检第三态 SKIP：上游并发写入造成的假红不得混进 FAIL

- 时间：2026-09-28 21:30 实施，21:40 登记
- 性质：口径裁定（自检结果怎么读），不改任何判据。
- 裁定：断言里若含「读同一个**正在被别人写**的文件两次并要求相等」，必须显式处理竞态：
  1. 取快照时要求「连续多次读到的内容指纹相同」才算稳定（重试 6 次、每次隔 1 s）；
  2. 始终不稳定 ⇒ 该几条记 **SKIP**（`ok=None`，不计入通过也不计入失败），
     并把看到的多个指纹写进产物；汇总行变成 `n_pass/n_checks（m SKIP）`。
- 起因（实测）：第一次全量回归里 `c_selfcheck_verdict_identity` 红 2 条，根因是 B 正在改
  `scripts/b_gate_controlled_success.py`（`GATE_BUILD` 就是该脚本内容的指纹），不是 C 读错。
  同理「只读上游」的实测证据也改三态，并补一条**与时间无关**的结构证据
  （身份层源码不得出现任何文件写 API）。
- 连带纪律：结构检查的模式必须精确 —— 第一版把 `str.replace(` 当成 `Path.replace(`（改名），
  一次正常字符串处理就判红。粗匹配的检查自己就是噪声源。
- 影响面：**SKIP ≠ PASS**。任何汇总里出现 SKIP，都必须在结论里写明「这几条本轮未被验证」，
  不得计入通过率。

---

## C 线待办（已具备前置、尚未动手；登记以便 D 下一轮点验）

| # | 事项 | 依据 | 为什么还没做 |
| --- | --- | --- | --- |
| 1 | P0-3 第二层：`DirectionScore` 增身份字段（`gate_version/gate_build/gate_spec_sha256/verdict_sha256/measurement_valid/usable_for/superseded_by/validity_class/blowup_threshold_source/三套账/五档`），缺身份不许进 `build_bundle`；`ingest_runtime_result` 只吃 `physical_fact`，其余各档写成带身份的事件；重判走 append-only + 撤销（复用 `record_contamination` / `case_append_only_and_revocation`） | 增补五 §9-C③ | 当前构建下 `physical_fact = 0` 条（B 正在升 v1.3、A 正在重判/新建 `ckptseq/`），此刻接线等于对着移动靶写死结构；身份层已就位，等重判产物落定再接 |
| 2 | P1-4：`work/decisions/` 正式登记处（内容寻址、append-only、可撤销/ack），并摄取 DR-001/DR-002 与增补裁定 8–15 | 增补五 §9-C④、`decisions_20260928.md` 抬头 | 本文件先按 A/B 的过渡格式登记，避免 D 下一轮点验时 C 条目缺席；正式登记处需要与 D 的编号并号规则（`DR-D*` / `DR-00x` / `ADR-A*` / `ADR-C*`）一起定 |
| 3 | P1-5：逐臂内容寻址 run manifest（`model_safetensors_sha256`、数据集 sha、`scripts/*.py` sha、`gate_build`/`gate_spec_sha256`、`probe_build`、`requirements.lock.txt`、`pinned_object_seed`、评测 seed 列表） | 增补五 §9-C⑤ | git 已 init（DR-002/DR-003）⇒ manifest 从「替代 git」变成「与 git 互校」；C 不执行 git 写命令（护栏 8 单写者纪律），需要 B 提供 commit 归属 |
| 4 | T17 goal 贯通的 C 侧 3 项（`harness/queue_td_learner.py:65,135,290`） | 增补三 §9-C、B 的 `scripts/b_selfcheck_goal_conditioning_t17.py` | B 说会单独同步断言形态；等 B 的参考实现落定再动，避免两边各写一套 |
