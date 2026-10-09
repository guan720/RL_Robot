# 异步 TD 六算例黄金期望值（B-3 交付，v1）

- 规格：`async_td_golden_v1.json`（implementation-agnostic，不含任何 B/C 的实现假设）
- 自校验：`python3 scripts/b_selfcheck_golden_values.py` → **47 项全过**
  （数值全部由 γ/n/L 重推导，不是照抄手算结果；另含 7 组结构性不变量 S1–S7）
- 出处：`RL_Harness_v4_20260924/materials/06_三轮递进调研与方案复审_20260923/appendices/02_异步动作时间轴与学习目标.md` §9 例 1–6（:286 起）

## 为什么是「B 出规格、C 自证」

附录 §9 原文写明这六例是**待实现的验收算例，不是已跑过的实验结果**。B 不实现、不测试
`harness/ledger.py` 与 `harness/data_bridge.py`（那是 C 的写入边界），所以这里只交可断言的期望值。
这样 C 不必等 B 的测试，B 也不必对着还在动的接口写测试——两边都不阻塞。

## C 怎么用

1. 把 `cases[*].input.event_log` / `timeline` / `variants` 按顺序喂给 ledger（或它的 mock 驱动）。
   **不要为了过测试改 ledger 的字段语义。**
2. 调 data_bridge 生成训练视图，断言 `cases[*].expect`。expect 分四类，必须**分别**断言，
   不能合并成一个 bool：`targets` / `masks` / `isolation` / `gradients`。
3. 容差：`targets` 用 1e-9 相对容差（都是 γ 的整数次幂，应逐位可复现）；
   `gradients` 用 `== 0` 与 `!= 0` 的严格判定。
4. 模型相关的量（`Q̄(...)`）在 JSON 里是**符号名**（如 `Q2_bar`）。断言应当是
   「`target == R + gamma_slot * <同一个 Q̄ 调用的返回值>`」，而不是断言一个编出来的浮点数。
5. 索引段一律读 `conventions.action_index_segments_numeric`（半开区间 `[lo, hi)`），
   不要对中文说明字段做字符串匹配——B 的第一版自校验就是这么错的。
6. 任何一条不过：先在 `work/decisions/`（或授权前先在 `docs/`）记录你认为是**规格错**还是**实现错**，
   再改。不要静默调阈值。

## 六例各自要抓住的一件事

| 例 | 一句话 | 最容易写错的地方 |
|---|---|---|
| E1 | 决策时刻 / 回报区间 / next state / 折扣 四者的时间对应 | next state 写成帧 112 却仍累计 100–105 的奖励（附录点名不通过） |
| E2 | actor 的 Q 动作梯度只经 E 段 | 把断言扩到整个 `L_actor`，顺手把 BC 标签也禁掉了（附录明确禁止） |
| E3 | 终局样本无 bootstrap，正奖励沿同一递推传回 | 给终局加 bootstrap；或按未来终止事件给前驱回填较长回报（0.5 会变成 0.75） |
| E4 | 「已提交未激活」≠「离线建议」 | 因为 U 尚未物理执行就把它误删成建议；或给建议编造 request ID 与 next queue |
| E5 | 被打断槽隔离，**不是**零价值 | 把删失当零价值；或 V1/V2 的隔离范围搞反（快照准不准决定要不要连前驱一起隔离） |
| E6 | 晚到 + 换向是两个独立拒绝理由 | 只查晚到不查 goal/epoch；或把拒绝当失败样本喂 TD 并给零奖励 |

## 跨例不变量

JSON 的 `cross_case_invariants`（I1–I8）逐条标了适用算例，可直接当 checklist：
四种 mask 分离 / request-commit-activate 三事件 / unknown≠失败≠零奖励 /
`γ_slot=γ^n` 只折扣一次 / C 读真实承诺队列而非自己预测的前 n 步 /
**这是本项目自拟的一决策步队列增广目标，不是原版 SmoothRL 的 2n chunk-skip** /
终局信息不作为 actor 在线拿不到的 critic 特征 / 边界按实际发生顺序裁定。
