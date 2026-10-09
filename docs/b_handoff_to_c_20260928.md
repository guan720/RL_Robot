# B → C 交接单：T17 goal 贯通的 C 侧 3 项（+ 2 处精度更正 + 1 个待确认约定）

交接人：智能体 B（验收门禁与可复现性线）。时间：2026-09-28 深夜。
接收人：智能体 C（`harness/ledger.py`、`harness/data_bridge.py`、`harness/queue_td_learner.py`）。

**边界声明**：B 不改 `harness/` 下任何文件。本单只给规格、断言形态与验收方式；
实现与单元测试归 C。B 侧的证据是 `scripts/b_selfcheck_goal_conditioning_t17.py`
（1 个参考实现 + 6 个故意写坏的实现）与 `runs/infra/b_t17/t17_precheck.json`。

**为什么现在交**：C 的 learner 刚过黄金值对账（`docs/c_golden_conformance_20260928.md`），
接口可以接了；此前 B 的 `scripts/selfcheck_ledger_data_bridge.py` 暂缓，就是为了不对着移动靶写测试。

---

## 1. 三项 C 侧改动（原样来自 `t17_precheck.json::to_wire_goal_for_real`）

| # | 位置 | 改动 | 阻塞 |
|---|---|---|---|
| C-1 | `harness/queue_td_learner.py:65` | `cfg.goals` 从 `("lift",)` 扩成双向词表（如 `("lift_A_to_B","lift_B_to_A")`）。**单 goal 词表下 T17 连测试都构造不出来** | 是 |
| C-2 | `harness/queue_td_learner.py:135` | `_goal_onehot` 在 `goal_dim == 1` 时输出恒为 `[1.0]`，等于给第一层加常量偏置 → 建议改 embedding；**或至少在 `goal_dim == 1` 时显式拒绝声称已 goal-conditioned** | 是 |
| C-3 | `harness/queue_td_learner.py:290` | `forward` 里 `cat([state, goal, c, xi])` 只保证了维度；需把 §2 的 T17-a/c/d/e 断言落成单元测试 | 否 |

C-2 的最小可接受形态（若暂不改 embedding）：

```python
@property
def goal_dim(self) -> int:
    return len(self.goals)

def _goal_onehot(goal_id, cfg, *, kind):
    if goal_id not in cfg.goals:
        raise LearnerRefused(f"{kind}: goal_id={goal_id!r} 不在配置词表 {cfg.goals} 里")
    if cfg.goal_dim < 2:          # ← 新增：单 goal 词表下 one-hot 恒为 [1.0]，不构成 goal 条件
        raise LearnerRefused(f"{kind}: goals 词表只有 {cfg.goal_dim} 项，one-hot 恒为常量，"
                             "不能声称 goal-conditioned（T17 无法构造）")
    ...
```

这条的价值在于：它把「无法验证」变成「显式拒绝」，而不是让一个恒真维度检查冒充验收。
现状**不是 C 的 bug**（`_goal_onehot` 对词表外 goal 会 `LearnerRefused`，是诚实的），
但它让 T17 目前无法被验证。

---

## 2. T17 的断言形态（B 已证明「有牙」，C 直接照抄即可）

来自 `scripts/b_selfcheck_goal_conditioning_t17.py:167` `t17_checks()`。
`teeth_check` 实测：参考实现全过；6 个坏实现**全部被 T17 抓住**，其中 5 个
（B2–B6 类）常规「维度 / concat / forward 不报错」检查**全过**、只有 T17 能抓，
1 个（B1 类 = 单 goal 词表）连测试都构造不出来、被 T17 明确挡下。
所以**只用维度检查验收 goal 贯通是不充分的**。

| 断言 | 内容 | 阈值 |
|---|---|---|
| **T17-a** | 同状态换 goal，输出必须变；**actor / critic / editor / candidate_filter / predictor 五个组件各自查** | `not allclose(out_g0, out_g1, atol=1e-9)` |
| **T17-c** | goal 表征的梯度非零（抓 `detach` 与零门）。embedding 走 `goal_table.weight.grad`；one-hot 走第一层在 goal 列切片上的权重梯度 | `abs().sum() > 0` |
| **T17-d** | goal 的影响不能只是常量偏置：换 goal 造成的输出差，量级要可比于换状态造成的差 | `d_goal / d_state > 0.05`，其中 `d_state` 用 `h + 0.1 * randn` |
| **T17-e** | 词表外 goal 必须被拒绝，不能静默当成某个已知 goal | 抛异常即通过（**注意异常类型**，见 §3.1） |

T17-a 的「五个组件各自查」直接来自附录 02 §12「全包 goal 与时间条件」：
base / editor / Q / 候选筛选 / 预测器要**分别**验，不能只验一个标量输出 ——
B6 变体就是「只验标量会漏掉」的那种。

---

## 3. 两处精度更正（B 自己的参考实现与 C 的实际代码不一致，按 C 的为准）

### 3.1 T17-e 的异常类型

B 的参考实现 `catch KeyError`；C 的实际实现抛的是
`LearnerRefused`（`harness/queue_td_learner.py:53`，继承 `RuntimeError`）。
C 落单元测试时断言应写成 `pytest.raises((LearnerRefused, KeyError))` 或直接 `LearnerRefused`，
**不要**照抄 B 的 `except KeyError` —— 照抄会让 C-1/C-2 改完之后测试假失败。

### 3.2 ξ 不是恒零（B 前一版口头描述有误，此处更正）

实测：TD 视图里 `xi = [1.0 if contiguous else 0.0]`（`harness/queue_td_learner.py:201`），
即 **ξ 是「承诺队列 C 是否有效」的标志位**；不连续时 `C = 0` 且 `ξ = 0`，
并在 `notes` 里写明「与上一 td 行不连续 ⇒ C=0, has_c=0」（`:199`），
注释里还明确了理由「绝不能拿不相干的旧动作冒充承诺队列」（`:191`）。
`next_xi` 恒 `[1.0]`（`:222`，「提交之后必然有队列在生效」）。这个约定是自洽的，B 无异议。

---

## 4. 一个已声明的近似：请把它变成**可量化可见**（不是指控）

`harness/queue_td_learner.py:257-258` 的 **BC 视图**恒在 `(C = 0, ξ = 0)` 上计算：

```python
b_c.append(np.zeros(cfg.n * cfg.action_dim, dtype=np.float32))
b_xi.append(np.zeros(XI_DIM, dtype=np.float32))
```

**C 已经诚实声明了这件事**，B 复核确认，不算缺陷：模块 docstring `:29`
「BC 行的 C 无法从分片重建（BC 行没有前后槽链），首版按 `C=0, has_c=0` 处理并写进 `notes`」，
以及 `:269` 的 `notes.append("BC 行的 C 无法从分片重建 ⇒ 首版按 C=0/has_c=0（已知近似）")`。

B 的请求只有一条：把这个**已知近似从「写在 notes 里」升级为「每 batch 可量化」** ——
报告 `bc_rows_at_xi0 / bc_rows_total`（或等价计数）。

理由：v4 的 `L_actor = −E[Q] + λ_BC·L_BC + λ_cont·L_continuity` 里，`λ_BC` 是防 RL 破坏已有能力的锚。
若 BC 行恒在 `ξ=0`，则锚只在 `ξ=0` 的输入半空间上施力，而 TD 视图与部署时的决策状态多数在 `ξ=1`
（`:201`、`:222`）—— 那么「有 BC 锚保护」这个主张在部署区间是**没有证据**的。
比例是 100% 还是 12%，决定了这句话是「已知近似」还是「实质缺口」，而这只有计数能回答。
这与 DR-005 停车的是同一个 `λ_cont`/`λ_BC` 家族，属 v4 既定项而非 B 的工程扩展，所以 B 只提问不改。

---

## 5. 非阻塞的两项（同表 #6 / #7，一并交给你）

- **#6 `docs/b_golden/async_td_golden_v1.json`（E6）**：`goal/epoch` 不相容必须与「晚到」
  作为**两个独立拒绝理由**分别记录。T17 只管计算图，不管这条时间语义 —— 别让 goal 贯通
  顺手把 E6 的两个理由合并成一个。
- **#7 附录 02 §12**：base / editor / Q / 候选筛选 / 预测器**分别**验 goal 与时间条件
  （= §2 的 T17-a 五组件）。归属：B 出规格（本文档），C 实现。

A 侧另有 2 项阻塞（`scripts/run_act_lift_runtime_failure_audit.py:36,39` 的 `goal_id` 硬编码、
以及 policy 不接收 goal），已在 `docs/b_handoff_to_a_20260928.md` 交接单 3，不需要 C 处理，
但**真贯通需要 A、C 两侧同时到位**：C 扩了词表而 A 仍发 `'lift'`，T17 依然构造不出来。

---

## 6. C 侧验收方式（B 会按这个判，不另外加要求）

1. `cfg.goals` 至少 2 项，且 `_goal_onehot` 在 `goal_dim < 2` 时显式拒绝；
2. §2 的 T17-a/c/d/e 落成单元测试并全过（异常类型按 §3.1）；
3. `scripts/b_selfcheck_goal_conditioning_t17.py` 的 `teeth_check.non_vacuous` 仍为 `true`
   （B 侧自证不受 C 改动影响，但重跑一次可确认没有共因失效）；
4. `scripts/b_selfcheck_golden_values.py` 仍 **47/47**、`scripts/b_selfcheck_t17_mutation.py` 仍 **6/6**；
5. §4 的 `bc_rows_at_xi0 / bc_rows_total` 计数落地（docstring 与 `notes` 声明已满足，不必重做）；
   或 C 明确判定「现有 `notes` 声明已足够」并给出理由 —— 两种都接受，B 要的是**显式**结论而非沉默。

B 侧不需要 C 通知即可复核 3/4；1/2/5 由 C 自证后告知路径，B 只读复核，不改 `harness/`。
