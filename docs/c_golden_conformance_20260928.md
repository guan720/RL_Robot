# C 线 P0-1：消费 B 黄金值规格的一致性复核（`b_golden_async_td_v1`）

- 规格（只读，B 交付）：`docs/b_golden/async_td_golden_v1.json`（`spec_sha256` 记在产物里）+ `docs/b_golden/README.md`
- C 侧复核脚本：`scripts/c_selfcheck_golden_conformance.py`
- 产物：`runs/infra/c_golden_conformance.json`（逐条判定 + 证据 + 内容身份）、`runs/infra/c_golden_conformance/<stamp>/*.db`
- 契约出处：`RL_Harness_v4_20260924/materials/06_.../appendices/02_异步动作时间轴与学习目标.md` §9 例 1–6、§3.3、§4.1、§5、§6.2
- 分工：本文档只记 **C 线**的裁定与映射；不改 B 的 `docs/b_*`、不改 A 的 `scripts/a_*`；`docs/b_golden/` 是只读规格。

本文档**先于**实现修改落地（`docs/b_golden/README.md` 第 6 条：任何一条不过，先记录是**规格错**
还是**实现错**，再改，不得静默调阈值）。

---

## 1. 裁定摘要

| 编号 | 触发算例 | 现象 | 裁定 | 处置 |
| --- | --- | --- | --- | --- |
| F1 | E5-V1 | 前驱槽 `rq100` 被隔离，理由 `c_next_not_equal_u` | **实现错**（过度删失） | `build_slots` 的 `C_next=U` 判定改为「边界帧 + 归属正确的前缀」 |
| F2 | E5 slot_k1 | 规格点名的 §3.3-1 违反（C 未全槽按学习动作边界执行）**没有**被检出 | **实现错**（漏检） | `c_not_executed` 增加帧级 chunk 归属核对 |
| F3 | E6 | 「晚到被拒」没有计入删失比例（`censoring_ratio` 只统计接管） | **实现错**（口径缺项） | 新增宽口径 `censored_slots` / `censored_slot_ratio` / `censoring_by_reason`，旧窄口径语义不动 |
| M1–M4 | E3/E5/E6 | 规格理由名与 C 侧实现名不同 | **命名差异，非缺陷** | 只登记别名表，断言语义；不改实现命名 |
| N1 | E3 | `gradient_of_ideal_Q_wrt_U_at_deterministic_terminal=0.0` | **不可断言** | 记 `NOT_ASSERTABLE`，不计入 PASS/FAIL |
| T1/T2 | — | 两个 C 侧既有断言编码了 F1/F2 的错误行为 | **测试构造错** | 改强断言（见 §2.3、§3.2），不放宽实现 |

结论：**规格侧未发现错误**。三条实现缺陷都在 C 自己的写入边界内（`harness/data_bridge.py`），
按裁定修改后全套 C 线回归仍全绿，且 E1–E6 转为符合规格。

---

## 2. F1：E5-V1 前驱槽被过度删失（实现错）

### 2.1 复现（物理诚实账本）

规格 E5 的时间轴：帧 100 槽 k 起点、帧 106 `rq100` 的 U 准时提交并成为槽 k+1 的 C、
帧 106/107 正常执行 C、**帧 108 Harness 强制改队列（抢占）**。按这个时间轴如实写账本：

```
帧 106,107 : source=policy,  chunk_id=rq100, chunk_index=6,7, a_rl=U_rq100[0,1], activated
帧 108..111: source=harness, chunk_id=HC1,   chunk_index=8..11, a_rl=None, driver_command=<纠正>, lease=1
事件: takeover @108 (rq106), lease_generation=1
```

修改前 `build_views(n=6, gamma=0.9, chunk_len=20)` 的结果：

```
rq100  td=False iso=True reasons=('c_next_not_equal_u',)   ← 违反规格
rq106  td=False iso=True reasons=('takeover_in_slot', ...)  ← 符合规格
```

规格 `expect.masks.slot_k_starting_100.V1.td_eligible = true`，并把
「V1 里连前驱也一起隔离（过度删失，白扔合法数据）」列为 `common_traps`。⇒ **实现不过规格**。

### 2.2 为什么是实现错而不是规格错

- 附录 §6.2 原文：*此前转移若拥有准确的槽边界 next state 与 next queue，可按原一步目标保留；
  后续抢占不改变已经发生的这一步。* 需要被证实的是 **边界（帧 106）** 上的 `C_{k+1}=U_k`，
  不是「U_k 在整个下一窗口 [106,112) 都没被替换」。
- 后者恰恰是**下一槽自己的**准入失败条件（§3.3-1 / §3.3-4），规格把它记在
  `slot_k1_starting_106.violated_admission_conditions` 上，而不是记在 slot_k 上。
- 修改前的实现用「整个 upcoming 窗口的 `a_rl` 逐值等于 U」当 `C_next=U` 的判据，
  把「下一槽中途被抢占」误判成「本槽的 next queue 从来不等于 U」，
  于是一次接管会连带删掉一条**已经合法成立**的一步转移。接管越频繁，白扔的合法数据越多
  —— 这正是 §6.2 要求报告删失比例、并强调「不沿整个 episode 无限制删除」的原因。

### 2.3 修改内容与顺带暴露的既有测试弱点

`C_{k+1}=U_k` 的判据从「整窗口逐值相等」改为两条：

1. **边界成立**：`next_row`（帧 `t_k+n`）存在且 `chunk_id == 本 request`；
2. **归属正确的前缀**：从 `t_k+n` 起、连续归属本 request 的那些帧，逐帧满足
   `chunk_index == n + i` 且 `a_rl == U[i]`。前缀之后被**别的**来源（harness 纠正 / 其它
   request / hold）替换，不再否定本槽的 `C_next=U`。

`next_queue` 字段的语义与取值**不变**（仍是下一窗口的实测 `a_rl` 元组，作为证据留存与人工核对）；
变的只是资格判定。若前缀在边界处就断（帧 `t_k+n` 归属别人 / hold），`c_next_not_equal_u` 照旧触发
—— E6 的「晚到 U 不得被采纳 ⇒ 不伪造 next queue」仍被抓得住（E6 全绿即为证）。

**T1**：`scripts/selfcheck_ledger_views.py::case5_mid_slot_takeover`（83/83 基线里一直是绿的）
构造的账本是**物理不自洽**的：帧 106–111 全部写成 `chunk_id=R1 / activated / a_rl=U_R1`，
同时又记了一个 `takeover @108` 事件。帧事实说「R1 的 U 一直执行到 111」，事件说「108 就被接管了」。
在这种账本下 `next_queue == u` 天然成立，F1 被掩盖了。处置：**不改**该用例（它验的是
「事件层接管 ⇒ 抢占槽隔离」，语义仍成立），但记为弱构造；物理诚实的构造由
`c_selfcheck_golden_conformance.py::E5` 承担，两份并存、各测一件事：

| 脚本 | 账本构造 | 断言重点 |
| --- | --- | --- |
| `selfcheck_ledger_views.py::case5` | 帧全归属 R1 + takeover 事件 | 事件层接管 ⇒ 抢占槽隔离、删失比例被报告 |
| `c_selfcheck_golden_conformance.py::E5` | 帧 108+ 归属 harness 纠正 | 帧层归属 + 边界快照 ⇒ 前驱保留、§3.3-1/§3.3-4 被点名 |

**T2**：`scripts/c_contract_lift_takeover_smoke.py` 原断言「前驱槽因队列被替换而隔离（C_next≠U）」
正是 F1 的错误行为。该 smoke 的 `--takeover-offset` 默认 2（接管帧 18，槽起点 16）⇒ 接管在边界
**之后**，前驱 R003 的边界快照是准的，按 §6.2 必须保留。已改成按 offset 分支断言：
`offset > 0` ⇒ 前驱保留；`offset == 0`（接管压在边界上、先后不可判）⇒ 前驱一并隔离（= E5-V2）。
并补一条「被抢占槽同时暴露 §3.3-1」。

---

## 3. F2：§3.3-1「C 未全槽按学习动作边界执行」漏检（实现错）

规格 E5 要求抢占槽记下两条被违反的准入条件：

- `§3.3-1 C 未在整个槽内按学习动作边界执行`
- `§3.3-4 存在未建模的中途队列替换`

### 3.1 修改内容

修改前 `c_not_executed` 只看 `execution_status ∈ {activated, partially_executed}`。
接管帧是**真的执行了**（harness 的纠正在动），只是执行的不是学习动作 C，
所以 `execution_status="activated"` ⇒ `c_not_executed=False` ⇒ §3.3-1 检不出来。
「命令执行了」与「执行的是本槽承诺的 C」是两件事（附录 01 §2.1：四种动作量分开存）。

修改：在原有 `execution_status` 判据之外，增加**帧级 chunk 归属核对** —— 本槽窗口内任何一帧的
`chunk_id / chunk_index / a_rl` 与「上一个已提交 request 的 U」不一致，即判 C 未按学习动作边界执行。
两处豁免：

- 首槽（`c_chunk_id is None`，prime/hold，ξ 的 `has_c=0`）不受此约束；
- U 短缺（partial）时只核对已承诺的那几行 —— 短缺本身已由 `u_incomplete` /
  `terminal_u_incomplete` 单独记账，不在这里重复计一条 `c_not_executed`
  （否则真机 smoke 的隔离原因集合会被污染，`clean` 通道的
  `isolation_reasons ⊆ {u_incomplete, terminal_u_incomplete}` 会假红）。

这条同时堵住了一个更隐蔽的陷阱：E1 `common_traps` 里的「用实测位移反填成策略发出的动作」。
如果哪一帧的 `a_rl` 与承诺的 U 不同值，现在会直接暴露成 `c_not_executed`。

### 3.2 T1 的另一半：`case_success_is_not_eligibility` 的构造自相矛盾

该用例用 `c_override=action(9.9, n)` 制造「C_next≠U」，写出来的帧是
`chunk_id=R1 / chunk_index=6..11 / a_rl=9.9 系列` —— 声称在跑 R1 的 chunk，跑的却不是 R1 承诺的 U。
F2 修好后，这一槽（R2）被正确判为 `c_not_executed`，于是旧断言「同一批数据里正常槽仍进 TD」
指着 R2 就红了。**R2 本来就不是正常槽**。处置：改强，不回退 ——

- 新增断言：「C 被值级替换 ⇒ 该槽也不是正常槽（§3.3-1 `c_not_executed`）」；
- 「正常槽仍进 TD」改用真正的清白槽 R3（其 C 由 R2 的完整 U 提供、下一窗口可确认）。

基线从 83 项变 84 项（净增 1 条断言），全绿。

---

## 4. 名称与索引映射（M1–M4：语义相同，不改实现命名）

规格的 `expect` 用附录原文措辞；C 侧 `isolation_reasons` / `terminal_kind` 用已冻结的实现命名
（`docs/ledger_data_bridge_20260928.md` §9.2 接口冻结 v1）。断言按**语义**对齐，别名表同时写在
本文档和脚本里（`REASON_ALIASES` / `KIND_ALIASES`），不做中文字符串匹配。

| 规格名 | C 侧实现名 | 说明 |
| --- | --- | --- |
| `late_past_deadline` | `deadline_miss` | 结果晚于 deadline 到达 ⇒ 拒绝原槽采纳 |
| `goal_epoch_incompatible` | `goal_epoch_incompatible` | 同名（为 E6 新增：到达时 in-force goal/epoch 已换） |
| `§3.3-1 C 未在整个槽内按学习动作边界执行` | `c_not_executed` | F2 修好后才真的对得上 |
| `§3.3-4 存在未建模的中途队列替换` | `takeover_in_slot` | 抢占事件落在本槽窗口内 |
| `true_goal_termination` | `goal_reached` | ∈ `TERMINATED_KINDS`；与外部截断 `timeout` 严格分开 |
| `physical_execution_mask_for_steps_after_L: [3,6)` | 前驱样本 chunk 索引 `[n+3,2n)=[9,12)` | 规格给的是**槽内步号**，映射到 chunk 索引要 `+n`；同时在终局样本上断言 `sum(execution_mask)==0`，两种读法都覆盖 |
| `q_gradient_span: [6,12)` | `q_action_gradient_mask == e_segment_mask(H=20,n=6)` | 规格是 chunk **步**索引；learner 探针在展平维度上工作，映射为 `[lo*d_a, hi*d_a)`，脚本对 `d_a=1` 与 `d_a=3` 都显式断言这个映射 |
| `next_observation`（事件） | 帧 `t_k+n` 的 `obs_ref` + chunk 归属 | C 侧账本没有这个事件种类；配对关系由帧事实承载 |
| `predecessor_next_queue_after_preemption: "A"` | 边界帧归属 + `queue_matches` 前缀判定 + learner `next_c=u` | `TrainingSample.next_queue` 是**实测窗口证据**，接管后只覆盖已验证前缀（含 `None` 行），不等于 A 的全长。这不是事后改写：账本 append-only，帧 106/107 仍归属 A |
| `isolation.B = "N/A"` | B 在 `bundle.candidate`、不在 `bundle.isolated` | 「不进 TD 视图」与「被隔离/删失」分开记 |
| B 的 `bc_eligible: true` | candidate 视图带动作标签 + `supervision_mask` | C 侧把「未进 request 的可信纠正」长期存在 candidate 视图，不是 bc 视图 |

---

## 5. 断言纪律（照 `docs/b_golden/README.md`）

1. `expect` 的**每个子键各自成一类**断言、分别计数，绝不合并成一个 bool。实际用了 16 个类别：
   `targets / masks / isolation / gradients / invariance / next_state / actor_sampling /
   explicit_non_claim / variant_expectations / logging / reward_semantics / isolation_scope /
   terminal_semantics / forbidden_attributions`，外加 C 侧自增的 `mapping / invariant / mutation`。
2. `targets` 用 1e-9 相对容差；`atol=1e-12` 只兜期望值本身为 0 的情形（E3 的 `R_k=0`）。
3. `gradients` 用 `== 0.0` / `!= 0.0` **严判**（规格 `strict: true`），不设容差；并跑
   `wrong_c` / `wrong_d` 两个故意写错的对照分支 —— 它们必须非 0，否则那些 0 只是探针失灵。
4. `Q̄` 是符号名：对 `y(q)` 在 `q=1,2` 两点做**线性识别**得 `(intercept, slope)`，断言
   `intercept == R_k`、`slope == γ_slot`；终局槽断言 `slope == 0.0`（严判），
   这一条本身就是「无 bootstrap」的证明。全程不断言任何编出来的浮点常数。
5. `γ_slot = 0.531441` 从规格读入并显式核对：`sample.gamma_slot == γ^n` 且 `!= γ^(n*n)`。
6. 索引段只读 `conventions.action_index_segments_numeric`（半开区间），不碰中文说明字段。
7. 不过 ⇒ 该项 `FAIL`、整体 `conformant=false`；判为规格问题则记 `UNRESOLVED` 停下等人工裁定。
   **不调容差、不放宽断言、不改规格。**
8. `NOT_ASSERTABLE` 单独计数（当前 1 项，见 N1），既不算通过也不算失败，逐条给理由。

**N1（唯一一项不可断言）**：E3 `actor_sampling.gradient_of_ideal_Q_wrt_U_at_deterministic_terminal=0.0`
是**收敛后理想 Q** 在确定性终局处的性质（Q̄ 恒为 0.81、与 U 无关），不是一个未训练网络可测的量。
C 侧不用假数值冒充断言；其可断言的等价部分（终局样本 `slope==0`、U 被保留、仍有值学习路径）已覆盖。

---

## 6. 结果与变异自检

```
按算例：E1 22 | E2 26 | E3 25(+1 NOT_ASSERTABLE) | E4 15 | E5 21 | E6 19 | INV 24 | MUT 13 | SPEC 6
结论：符合规格  PASS=171 FAIL=0 UNRESOLVED=0 NOT_ASSERTABLE=1
```

`INV` 是**对本脚本自身**的元检查：`cross_case_invariants` 的 I1–I8 逐条标了适用算例
（共 24 个 (不变量, 算例) 组合），反过来核对每个组合是否真的被至少一条断言覆盖 —— 漏测会让覆盖率虚高。

### 6.1 为什么必须有变异自检

171 条全绿本身不说明任何问题：如果断言恒真，全绿比失败更危险。本仓库已经踩过两次
（`case2` 的 `0.0*probe` 假绿、`c_lift_contract_smoke` 只测正向的 obs 宽度守卫），
所以这里内置 12 个变异体，每个对应规格 `common_traps` / 不变量里点名的**一条具体陷阱**，
用 monkey-patch 注入（`finally` 里还原，不改仓库实现文件），要求对应算例**真的转红**。

| 变异 | 注入的陷阱 | 出处 | 抓住它的断言（首条） | 命中数 |
| --- | --- | --- | --- | --- |
| M1 | 对 γ_slot 再做一次 n 次幂（0.9^36） | E1 traps[3] / I4 | y_k 的 Q̄ 系数 == γ_slot | 4 |
| M2 | next state 写成帧 112、仍累计 100-105 的奖励 | 附录 §9 例 1 | next state 的 h 是帧 106 | 1 |
| M3 | 把 106-111 的奖励挪进当前样本 | 附录 §3.1 末段 | R_k = Σ γ^j r | 5 |
| M4 | 给终局样本加 bootstrap | E3 traps[0] | 终局 y == 0.81（Q̄ 系数恒 0） | 2 |
| M5 | 用后来的成功给前驱回填较长回报 | 附录 §5.2 | 前驱 R_k == 0 | 4 |
| M6 | 把删失当零价值（`target()` 返 0.0 而非 None） | E5 traps[1] / I3 | treated_as_zero_value == false | 4 |
| M7 | 给未进 request 的影子建议伪 TD | 附录 02:63 | B：td_eligible == false | 3 |
| M8 | 只查晚到、不查 goal/epoch | E6 traps[1] | 两个拒绝理由分别记录 | 1 |
| M9 | 把 C 当可优化输出送进 critic（不加 sg） | E2 traps[2] / I5 | ∂L_Q/∂chunk[0,6) == 0.0 | 4 |
| M10 | 接管时连前驱一起隔离（F1 的旧行为） | E5 traps[2] / §6.2 | V1 slot_k td_eligible == true | 6 |
| M11 | §3.3-1 C 未按学习动作边界执行检不出来（F2 的旧行为） | E5 violated_admission_conditions | 两条被违反准入条件都被检出 | 1 |
| M12 | 把拒绝当失败样本喂 TD 并给零奖励 | E6 traps[2] / I3 | adoption_for_original_slot == REJECT | 6 |

另加 1 条：变异全部还原后重跑 E1 无任何 FAIL（证明 monkey-patch 没有残留污染）。

M10 / M11 特别重要：它们把 F1 / F2 修复**之前**的行为重新注入，确认新断言确实能抓住旧 bug
—— 也就是「这次的修复是被测试钉住的，不是靠人记着」。

### 6.2 变异自检自己也曾假绿（教训）

第一版 M8 / M11 的 `apply` 写成了 `return lambda: patch_views(...)()` —— 返回的是**又一个 lambda**
而不是 undo 函数，于是 `undo = mut["apply"]()` 拿到的东西从未执行 patch，变异根本没注入，
子报告全绿、`caught=[]`。是「变异被抓住」这条断言自己把它暴露出来的（`caught` 为空 ⇒ FAIL）。

教训写在这里：**变异测试必须断言「变异确实改变了被测量」**，不能只断言「测试没崩」。
M8/M11 现在各由 1 条断言精确抓住，说明检出路径是唯一的、也是有效的。

---

## 7. F3：删失口径只覆盖接管，未覆盖超时/日志缺失（实现错）

规格 E6 `isolation.counted_toward_censoring_ratio = true`：晚到被拒的槽要计入删失比例。
修改前 `compute_stats` 的 `censoring_ratio` / `censoring_slot_ratio` 分子只数 `takeover_in_slot`，
而 E6 的槽没有接管事件 ⇒ 比例为 0 ⇒ 不过规格。

附录 §5.3 的删失其实包含「Harness 抢占、超时、云服务掉线、日志缺失」四类。处置采用**加法**，
不重定义旧口径（`c_contract_lift_*_smoke.py` 已在消费它，静默改语义比缺一项更糟）：

| 口径 | 键 | 分子 | 状态 |
| --- | --- | --- | --- |
| 窄（帧） | `censoring_ratio` | 接管槽覆盖到的帧数 | 语义不动 |
| 窄（槽） | `censoring_slot_ratio` | `takeover_in_slot` 槽数 | 语义不动 |
| **宽（槽）** | `censored_slots` / `censored_slot_ratio` / `censored_requests` / `censoring_by_reason` | 隔离理由命中 `CENSORING_REASONS` 的槽数 | **本轮新增** |

`CENSORING_REASONS` 的取舍（写在 `harness/data_bridge.py` 的注释里）：

- **算删失**（= 我们不知道后续价值）：接管族（`takeover_in_slot`、`lease_generation_changed`、
  `boundary_unverifiable_before_takeover`）、超时/掉线族（`deadline_miss`、`result_not_committed`、
  `u_unavailable`）、日志缺失族（`next_snapshot_unverifiable`、`frame_facts_incomplete`、
  `reward_unknown`、`observation_stale`、`observation_age_unknown`、`u_incomplete`、
  `terminal_u_incomplete`、`terminal_u_unknown`）、以及对应的 `terminal_kind:*`。
- **不算删失**：换向族（`goal_epoch_mismatch` / `goal_epoch_incompatible` / `next_goal_switch`）
  —— §5.5 的合法边界，不是信息缺失；契约违反族（`c_next_not_equal_u` / `c_not_executed` /
  `post_terminal_queue_replaced`）—— 数据本身不合法，不是「没观测到」。
- `reward_pending` 不算：它有独立的 pending 视图与计数，混进删失会重复计。

顺带解释了 E5-V2 的一个现象：帧口径 `censoring_ratio` 在 V2 恒为 0，因为不可确认窗口**本来就没有
帧事实**，分子分母同时缺失。这正是 `compute_stats` 要求「两个口径都报」的原因，已写进断言的 note。

---

## 8. P0-2：γ / n 单位冲突的处置（同一对象两套约定，必须收敛）

| 用途 | γ | n | H | 地位 |
| --- | --- | --- | --- | --- |
| 规格一致性复核（本脚本） | 0.9 | 6 | 20 | **B 黄金值约定**，只用于核对语义，不代表真机 |
| 真实帧路径（`runs/infra/c_learner_shard_smoke.json` 的 clean/takeover 通道） | 0.99 | 4 | 8 | **假设值**，尚未实测 |
| 真实帧路径的 terminal 通道 | 0.9 | 6 | — | 与黄金值同约定（`γ_slot=0.531441`、`0.9^2=0.81`） |

收敛规则（本轮落地）：

1. 本脚本**只**跑 B 的数（γ=0.9、n=6、H=20），一律从 `spec["conventions"]` 读，
   不从真机 smoke 里读 γ/n；两套约定不混用。
2. 真实帧路径的 γ/n 在产物里显式标为假设值（`c_learner_shard_smoke.json` 的 `n_assumed`），
   不得写成实测值。
3. 「把 n / γ 从假设值升为实测值」单独立项（§8.1）；未完成前，任何跨线比较都必须先声明用的是哪一套。

### 8.1 立项：n / γ 升为实测值

- 控制频率 20 Hz 有文档口径（`docs/lerobot_official_act_lock_20260924.md:22`、
  `docs/lerobot_act_env_setup_20260928.md:375`），但**尚未登记为实测值**：
  `RL_Harness_v4_20260924/templates/项目参数模板.json` 的 `timing` 组八项仍全为 `null`
  （`control_hz` / `slot_n` / `inference_latency_measurements` / `deadline` 都是）。
  「有文档口径」不等于「已定标」，所以本轮一律按未定标处理。
- `n` 的反推路径：A 已测 `0.011 m/(dz·帧)` 的位移增益 + teacher 的 7 帧爆发长度
  ⇒ 一个决策槽要覆盖的帧数下界；再与推理延迟分布（p50/p95/max）一起定 `n` 与 `H ≥ 2n`。
- `γ` 的定法：先定「一个槽代表多少物理时间」（`n / 20 Hz`），再按任务时长定折扣半衰期，
  反解每控制步 γ，最后 `γ_slot = γ^n` **只算一次并存下来**。
- 归属：`n` 需要 A 的延迟/位移实测 + C 的调度契约一起定；`work/decisions/`（P1-4）建好后登记，
  在此之前先记本文档。
- 验收判据：`templates/项目参数模板.json` 的 `timing` 与 `action_contract` 两组参数从 `null`
  变成实测值，且 `n` 的取值能由延迟分布复算出来。

### 8.2 本轮把「假设值」写进了产物与分片（收敛规则 2 的落地）

只在 C 线文件里做加法，不动 B 的规格、不改任何已有字段的语义：

| 位置 | 加了什么 |
| --- | --- |
| `scripts/c_contract_lift_smoke.py` | 新增 `GOLDEN_SPEC_CONVENTION` / `CONTROL_HZ_CLAIM` / `template_timing_status()` / `unit_convention(gamma, n, status=...)`；report 加 `gamma_assumed` + `unit_convention`；两条新断言 |
| `scripts/c_contract_lift_takeover_smoke.py` | report 加 `gamma_assumed` + `unit_convention`；三个通道的导出 manifest 各带一份约定；两条新断言 |
| `scripts/c_learner_shard_smoke.py` | report 加 `n_assumed` / `gamma_assumed` / `unit_convention`；`report["channels"][*]["unit_convention"]`；三条新断言 + 一条拒绝记录 `refusals.wrong_unit_convention` |
| `harness/data_bridge.py` | `export_views(..., unit_convention=None)`：给了就写进 `manifest.json`，且 γ/n/γ_slot 与本次导出不一致**直接抛 `ValueError`** |

四条设计约束（都是为了不让「假设值」被下游误读成实测口径）：

1. **定标状态跟着分片走**。learner 是另一个进程，只读 `views_*/manifest.json`；
   标注只留在 smoke 报告里等于换进程就丢。所以约定进 manifest，而不是只进 report。
2. **状态与模板互锁**。`unit_convention` 会去读模板 `timing` 组：
   `status="measured"` 而模板仍有 `null` ⇒ 抛；`status="assumed"` 而模板已填满 ⇒ 断言失败。
   这是一条**双向绊线**：等 A 的延迟实测定标完成，这两处会主动报错，逼人把假设值改成实测值，
   而不是让旧标注悄悄过期。
   守卫本身也做了**两侧**测试（`c_contract_lift_smoke.py`）：注入「模板未填」⇒ 标 `measured`
   必须抛 `ValueError`；注入「模板已填」⇒ 标 `measured` 必须放行。只测一侧的话，
   一个无条件 `raise` 也能骗过断言 —— 这正是 §6.2 记过的那类假绿。用注入状态而不是真模板，
   是为了将来模板真被填上时，这条守卫测试不会变成定时炸弹。
3. **两套约定不许互相贴**。`export_views` 校验 `unit_convention` 的 γ/n/γ_slot 与本次导出一致，
   所以把黄金值的 γ=0.9/n=6 贴到 γ=0.99/n=4 的真机分片上会被拒（smoke 里作为反向用例钉住）。
4. **`γ_slot` 只算一次**。`unit_convention` 里算出 `γ^n` 并落盘；终局通道额外断言它等于
   `0.531441`（=0.9^6）且**远离** `0.9^36`，防「槽当折扣单位再幂一次」那个二次幂 bug。

本轮**没有**做的事：没有把 γ/n 改成实测值（等 §8.1 的 A 侧延迟分布），没有改
`write_manifests` 写进账本的 manifest 记录（那一层只有 γ/n 数值列，加字段要动账本 schema，
留给 P0-3 的「裁定身份与有效性」一起做），也没有动 B 的黄金值约定。

---

## 9. 本轮改动的文件（全部在 C 线写入边界内）

| 文件 | 改动 | 依据 |
| --- | --- | --- |
| `harness/data_bridge.py` | F1 边界+前缀判定；F2 帧级 chunk 归属核对；F3 宽口径删失统计 + `CENSORING_REASONS`；`export_views` 增 `unit_convention`（P0-2） | §2、§3、§7、§8.2 |
| `scripts/c_selfcheck_golden_conformance.py` | **新增**：读规格逐条断言 + 变异自检 | 全文 |
| `scripts/selfcheck_ledger_views.py` | T1：`case_success_is_not_eligibility` 改强（83 → 84 项） | §3.2 |
| `scripts/c_contract_lift_smoke.py` | P0-2：`unit_convention()` / `template_timing_status()` / `GOLDEN_SPEC_CONVENTION`；report 加 `gamma_assumed` + `measured_guard`（14 → 17 项） | §8.2 |
| `scripts/c_contract_lift_takeover_smoke.py` | T2：前驱槽断言改为按 `--takeover-offset` 分支；补 §3.3-1 断言（28 → 29 项）；P0-2：γ/n 假设标注 + 三通道分片 manifest 带约定（29 → 31 项） | §2.3、§8.2 |
| `scripts/c_learner_shard_smoke.py` | P0-2：`n_assumed` / `gamma_assumed` / `unit_convention` + 逐通道约定；两套约定不混、γ_slot 二次幂守卫、反向拒绝用例（40 → 43 项） | §8.2 |
| `docs/c_golden_conformance_20260928.md` | 本文档 | — |
| `docs/ledger_data_bridge_20260928.md` | 追加 §11 | — |

回归（P0-1 + P0-2 之后全绿，CPU-only）：`c_selfcheck_golden_conformance` 171 PASS / 0 FAIL /
1 NOT_ASSERTABLE、`selfcheck_ledger_views` 84/84、`c_contract_lift_smoke` 17/17、
`c_contract_lift_takeover_smoke` 31/31、`c_learner_shard_smoke` 43/43，
其余 C 线自检（obs_store 30/30、release_bundle 27/27、harness_contracts 6/6、
runtime_adapter 6/6、stage3 全通过）与 `RL_Harness_v4_20260924/tools/verify_package.py`
（`errors: []`）同样全绿。逐项产物落在 `runs/infra/c_*.json`。
一次跑完全量：`setsid bash scripts/c_run_all_selfchecks.sh > /tmp/c_reg.log 2>&1 < /dev/null &`
（CPU-only，不抢 A 的卡；单个脚本失败不中断，末尾统一汇总）。

**没有改**：`docs/b_golden/*`（B 的只读规格）、`scripts/b_*`、`docs/b_*`、`scripts/a_*`、
`RL_Harness_v4_20260924/**`（`tools/verify_package.py` 保持 `errors: []`）、监管备忘录。

状态措辞仍为**已实现未验证**：本轮验的是「账本 → 训练视图 → 学习目标」这一段的**语义一致性**，
不是真机/真策略的效果。真机侧要等 A 的 `n`/延迟实测与 B 的门禁裁定接进来。
