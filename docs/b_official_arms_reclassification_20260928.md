# B③ 官方臂重判与重分类表（44 臂，当前门禁构建）

指派来源：`rl_harness_supervision/supervisor_memo_20260928.md` 增补二 §5.B③
（「重分类结论写入发布说明」）与 §6 回流点
（「blowup 字段补齐 + 官方重判 + A 臂截断探针三者齐备后，重议改判 1 的证据等级」）。

工具：`scripts/b_official_arms_reclassification.py`（只读后处理，不改任何评测产物，
也不动 A 目录里的历史裁定）
产物：`runs/infra/b_official_arms/reclassification.json`
门禁：`gate_version=v1.2.1`，`gate_build=e4f5ec887788`，
`gate_spec_sha256=494d5f5babf9`（以产物内字段为准）

---

## 1. 一句话结论

**回流点的三个条件现已齐备，但结论与备忘预期不同：改判 1 引用的那个臂本身测量无效，
而真正强的臂是另一族（短 chunk），且 seed 间摆幅大到单臂数字不可引用。**

- 增补二 §2 要求「blowup 字段已记录且 <0.05 + 过官方重判」才可作为率证据。
  逐臂判定结果：**22 臂可引用（须附敏感带）、
  15 臂测量有效但受控成功为 0（无正率可主张）、
  7 臂测量无效（任何率都不得引用）**。
- 改判 1 引用的 `trimdone0_minmax_k2_lr1e-5_s20k_seed0` 属**测量无效**（输入契约 `violated`），
  它的 9/20 不满足生效条件，**不得**作为率证据引用。
- 与此同时，仓库里已经存在受控成功 **17/20、19/20、20/20** 的臂
  （`trimdone0_minmax_k2_lr1e-5_s20k` 的 seed3/seed4、`trimdone0_minmax_k1_lr1e-5_s20k` 的 seed0），
  全部 `verified_ok`、非复合、阈值稳定或近稳定。这是本项目第一次有过门禁的强结果。

---

## 2. 为什么此前无法回答「哪些数字可以引用」

因为仓库里**没有**一份覆盖全部官方臂、且带当前构建指纹的裁定产物：

| 已有产物 | 覆盖 | 问题 |
|---|---|---|
| `runs/infra/lerobot_act_env_20260928/gate_*.json`（43 份） | 逐臂零散 | 横跨 **6 个**不同 `gate_build`（`None`（无指纹）/ `800e1d08a174` / `6bf27fa39e83` / `369595c86a07` / `28290b9c1b25` / `22a7d92bec0a`），**没有一份是当前构建**；gate_version 混着 v1.1 与 v1.2。（6 这个数由 A 的 `regate_diff_current.json::n_old_builds` 独立枚举得出，B 初稿写「至少 5 个」是少数了一个，已更正） |
| `runs/infra/b_gate_sensitivity/report.json` | 12 臂 | 产物是阈值敏感性网格，不是裁定 |
| `runs/infra/b_normclip2/gate_all.json` | 11 臂 | 全是 B 自己的 clip 扫描臂，不含官方臂 |

所以「哪些臂现在可以引用」这个问题在本文之前无法机械回答。本轮把 44 份官方产物
全部用当前门禁重判了一遍（`n_judge_error=0`）。

### 3.1 与 A 的独立重判交叉核验：44/44 臂零差异

A 线在同一时间用 `scripts/a_regate_gate_current.py` 做了同一件事
（产物 `runs/infra/lerobot_act_env_20260928/regate_current/` 44 份 + `regate_diff_current.json`）。
两条产物**互不知情、各自独立生成**，但都 `import` B 的 `judge_file` 而不重实现判据。

逐格比对结果：

| 项 | A 侧 | B 侧 |
|---|---|---|
| `gate_build` / `gate_spec_sha256` | `e4f5ec887788` / `494d5f5babf9` | 同 |
| `rise_cap` / `final_rise_min` | 0.15 / 0.04 | 同 |
| 覆盖臂数 | 44 | 44 |
| 逐格差异（`controlled_success` / `provisional_pass` / `over_lift` / `flick` / `insufficient_lift` / `raw_success` / `measurement_valid` / `gate_pass`） | — | **0 处** |

这是本轮最干净的一条可复现性证据：**同一判据、同一构建，两条独立实现路径给出完全相同的裁定**。
它同时反证了「门禁口径含糊」不是问题来源 —— 分歧只可能来自构建漂移，不可能来自实现分歧。

A 侧还量出了漂移的**实际代价**（`regate_diff_current.json`）：
44 臂里 **35 臂的失效模式计数在旧构建下是错的**（`n_counts_changed=35`），
而 `gate_pass` 一个都没翻（`n_verdict_changed=0`）。
也就是说：陈旧裁定不会让一个该红的臂变绿，但会让 **80% 的臂**报出错误的
`flick` / `over_lift` / `insufficient_lift` 分布 —— 而失效模式分布正是决定「下一步修哪个旋钮」的依据。
这比「指纹不一致」这种形式问题严重得多，也是 §6 那个治理项必须收敛的原因。

---

## 3. 可引用性三分类（判据逐条来自增补二 §2）

| 输入契约 status | 臂数 | 含义 |
|---|---|---|
| `verified_ok` | 37 | blowup 字段齐全且均值 ≤0.05 |
| `unverified` | 5 | 缺/不全 blowup 字段 → 按增补二 §3 同样判 INVALID |
| `violated` | 2 | 有字段但超阈 → INVALID |

**测量无效的 7 个臂（任何率都不得引用）：**

| 臂 | 原因 | raw | 备注 |
|---|---|---|---|
| `trimdone0_minmax_k2_lr1e-5_s20k_seed0` | 输入契约 `violated` | 11 | **改判 1 引用族** |
| `trimdone0_minmax_k2_lr1e-5_s20k_seed0_replan1` | 输入契约 `violated` | 4 | **改判 1 引用族** |
| `train24_lr1e-4_s20k` | 缺 blowup 字段（`unverified`） | 0 | 早期产物，A 补字段前的版本 |
| `train24_lr1e-5_actionminmax_s20k` | 缺 blowup 字段（`unverified`） | 11 | 早期产物，A 补字段前的版本 |
| `train24_lr1e-5_actionminmax_s20k_seed1` | 缺 blowup 字段（`unverified`） | 0 | 早期产物，A 补字段前的版本 |
| `train24_lr1e-5_actionminmax_s20k_seed2` | 缺 blowup 字段（`unverified`） | 4 | 早期产物，A 补字段前的版本 |
| `train24_lr1e-5_s20k` | 缺 blowup 字段（`unverified`） | 2 | 早期产物，A 补字段前的版本 |

注意最后一类里一个很有说服力的对照：`train24_lr1e-5_actionminmax_s20k`（缺字段）被判
**11 局 `flick`**，
而同一 checkpoint 补齐字段后的 `..._gatefields` 版本被判
**11 局 `insufficient_lift`、0 局 flick**。
同一个策略、同一批 seeds，只因缺 `final_rise`/`held_at_end` 就被归成完全相反的失效模式
（弹射 vs 抬起不足）—— 这就是增补二 §3 那条「缺字段同样判 INVALID」的价值实证。

---

## 4. 可引用的单位是「配置族 × 重规划口径」，不是单个臂

实测 44 个官方臂横跨 **8 种** `(chunk_size, n_action_steps, replan_every)` 组合，
且同一配置族跨 seed 的受控成功数摆幅极大。因此汇总必须按族做，且分母只排除
**测量无效**的臂（把「有效但受控为 0」的臂排除会系统性高估 —— 本脚本第一版就犯了这个错，
k1 族曾报成 20.0/20，算上 seed1=0 才是真实的 10.0/20）。

| 配置族 | 口径 chunk/n_act/replan | 臂数 | 受控 min~max | **族均值（测量有效臂）** | 计入均值的臂数 | 有正受控的臂数 |
|---|---|---|---|---|---|---|
| `trimdone0_minmax_k1_lr1e-5_s20k` | 1/1/1 | 2 | 0~20 | 10.0/20 | 2 | 1 |
| `trimdone0_minmax_k2_lr1e-5_s20k` | 2/2/2 | 6 | 0~19 | 7.8/20 | 5 | 4 |
| `trimdone0_stdfloor_minmax_k2_lr1e-5_s20k` | 2/2/2 | 4 | 0~16 | 7.8/20 | 4 | 3 |
| `train120_trimdone0_minmax_k2_lr1e-5_s20k` | 2/2/2 | 1 | 9~9 | 9.0/20 | 1 | 1 |
| `trimdone0_minmax_lr1e-5_s20k@replan1` | 4/4/1 | 2 | 0~4 | 2.0/20 | 2 | 1 |
| `train24_minmax_k2_lr1e-5_s20k` | 2/2/2 | 2 | 1~3 | 2.0/20 | 2 | 2 |
| `trimdone0_minmax_lr1e-5_s6k` | 4/4/4 | 1 | 3~3 | 3.0/20 | 1 | 1 |
| `trimdone0_minmax_kl1_s20k` | 4/4/4 | 1 | 2~2 | 2.0/20 | 1 | 1 |
| `trimdone0_minmax_lr1e-5_s20k` | 4/4/4 | 2 | 0~2 | 1.0/20 | 2 | 1 |
| `trimdone0_minmax_lr1e-5_s20k@replan2` | 4/4/2 | 1 | 2~2 | 2.0/20 | 1 | 1 |

最大 seed 间摆幅：**20 局**
（`trimdone0_minmax_k1_lr1e-5_s20k`，口径 `1/1/1`）。

由此得到本轮最硬的一条表述纪律：

> **任何「某臂受控成功 N/20」的单独引用都属于挑 seed。**
> 对外只能报「族 × 口径」的均值 + seed 摆幅 + 计入均值的臂数。
> 例：`trimdone0_minmax_k2_lr1e-5_s20k`（口径 2/2/2）应报
> 「受控成功 7.8/20，seed 摆幅 0~19，n=5 个有效臂」，
> 而不是「19/20」。

---

## 5. 跨口径不可比（算力不是常量）

`(1,1,1)` 口径每帧都重新推理，推理次数是 `(4,4,4)` 组的 **4 倍**。
所以 `trimdone0_minmax_k1_lr1e-5_s20k` 的 20/20 与 chunk-4 族的 0~2/20
**不是同等算力下的比较**。目前可以说的只有：

- 同口径内部（2/2/2 组，13 臂）：`trimdone0_minmax_k2` 族均值 7.8/20、
  `trimdone0_stdfloor_minmax_k2` 族均值 7.75/20，两者在噪声内不可区分；
  而同口径的 `train24_minmax_k2` 只有 2.0/20 —— **`trimdone0`（去掉完成后空转帧）
  与 `train120`（加数据量）这两个杠杆看起来是真的**，但都还只有 1~5 个有效臂支撑。
- 跨口径的结论（k1 vs k2 vs k4）需要匹配推理预算后才能下，本文不下。

---

## 6. 治理项：43 份历史裁定漂移（B 未触碰）

`runs/infra/lerobot_act_env_20260928/gate_*.json` 有 43 份历史裁定，
横跨至少 5 个不同 `gate_build`，其中若干份连指纹字段都没有（v1.1.1 之前的构建）。
该目录属 **A 的写入范围**，本轮 B 一律未改写，只在此登记事实。

**本项在本文写就时已部分自行解决**：A 的 `scripts/a_regate_gate_current.py` 已把 44 臂重判到当前构建
（`regate_current/` 44 份 + `regate_diff_current.json`），且遵守「不覆盖、不移动、不删除旧裁定」。
B 与 A 的现行产物已交叉核验为逐格一致（§3.1），所以**不存在数字冲突**。

剩下的只是分工，建议 D 确认（B 不自行宣布权威）：

| 用途 | 建议以哪份为准 | 理由 |
|---|---|---|
| 逐臂现行裁定、新旧构建 diff | A 的 `regate_current/` + `regate_diff_current.json` | 在 A 的写入范围内，含逐臂旧值比对 |
| **可引用性判定**（能否作为率证据）、**族 × 口径汇总**、seed 摆幅 | B 的 `runs/infra/b_official_arms/reclassification.json` | 这两层是增补二 §2 的生效条件与本文 §4 的表述纪律，A 侧产物没有 |
| 那 43 份旧 `gate_*.json` | 一律视为**历史留档**，禁止再被引用为现行裁定 | 横跨 6 个构建，35/44 臂计数已证伪 |

---

## 7. 对回流点的建议（提交 D 裁决）

增补二 §6 的三个条件现状：

| 条件 | 状态 | 依据 |
|---|---|---|
| blowup 字段补齐 | **部分**：37/44 已记录；5 臂缺字段（均为早期产物） | 本文 §3 |
| 官方门禁重判 | **已完成**（44 臂，当前构建） | `runs/infra/b_official_arms/reclassification.json` |
| A 臂截断探针 | **已完成**（弱臂 + 强臂各一次） | `docs/b_truncation_probe_official_20260928.md` |

B 的建议：**改判 1 可以上调，但依据必须换成 k2/k1 族，且必须带 seed 摆幅**。
理由：
1. 原来支撑「部分满足」的 `trimdone0 k2 seed0 = 9/20` 测量无效，不能再用；
2. 但存在同族、测量有效、阈值稳定的 `k2 seed4 = 19/20`、`seed3 = 17/20`，
   以及 `k1 seed0 = 20/20`（敏感带 20→19）；
3. 截断探针（含 19/20 强臂的双向可观测那次）显示 L1 在这些臂上**零咬合**，
   所以「L1 暴露」不再是压低这些数字的理由。

同时必须写进上调的附加条件：族均值 7.8/20 与单臂 19/20 相差 2.4 倍，
**任何对外表述只能用族均值 + 摆幅**；且强结果全部来自仿真 Lift 单任务、
pinned 物体 seed、20 个固定 seeds，v4 的 5 条晋级条件里其余各条不受本文影响。

---

## 8. 边界（不做的主张）

- 只重判**已有产物**，没有新跑任何评测（除了截断探针那 4 臂）。
  族均值背后的 n 只有 1~5，**不构成统计意义上的能力估计**，只是当前可引用口径。
- 不判定「哪个配置族最好」：跨口径算力不匹配（§5），且 seed 数不足。
- 不改任何判据。C5=0.04 比 robosuite 等效阈严约 4.7 倍这一事实仍在 D 的裁决队列里
  （`docs/b_gate_threshold_sensitivity_20260928.md` §4.2）；若 D 决定放宽 C5，
  本文所有受控成功数都会上升，须整表重判。
- 21/23 个「有受控成功」的臂是阈值敏感的，
  所以本文表格里每个正数都必须与其 `ctrl_lo→ctrl_hi` 敏感带一起引用
  （逐臂数值在 JSON 的 `arms[].ctrl_lo/ctrl_hi`）。
