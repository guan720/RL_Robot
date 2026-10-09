# 门禁阈值敏感性报告 + C5 阈值标定勘误（B 线，2026-09-28 晚）

对应监管指派：`rl_harness_supervision/supervisor_memo_20260928.md` §二.B.2
（「出门禁阈值敏感性报告（±0.005），并回应 A 提出的 `failed_checks` 口径问题」）
与 §二.A.3（「受控局 rise 0.0415–0.0466 贴着 0.04 门槛：与 B 共担门禁阈值 ±0.005 敏感性报告」）。

产物：`runs/infra/b_gate_sensitivity/report.json`
（**构建指纹见产物内 `gate_build` / `gate_spec_sha256` 字段**，本文不写死哈希 ——
门禁每改一次这个值就变，写死在文档里必然过期，本轮已实测到三个不同值并存）。
工具：`scripts/b_gate_threshold_sensitivity.py`（只读后处理，不改任何评测器）。
重生成入口：`scripts/b_regate_all.py`（一键重判三组臂集合 + 逐臂新旧 diff + 自动跑规格 §7 回归）。
本报告全部数字已在最新构建上重跑核对：**12 臂逐臂 0 处差异**（0 robust / 5 sensitive 结论不变，
`trimdone0_minmax_lr1e-5_s20k_seed0` 仍是 1→6）。

---

## 1. 结论速览（三条，第 3 条是勘误）

1. **12 个官方臂里 0 个 threshold_robust，5 个 threshold_sensitive。**
   监管 改判 1 引用的那个臂（`trimdone0_minmax_lr1e-5_s20k_seed0`，受控 2/20）
   在 ±0.005 m 网格上是 **1→6**；`seed0_replan1` 是 **2→6**；`train24_lr1e-5_actionminmax` 是 **0→2**。
   所以「受控成功 N/20」这个数**不能单独引用**，必须带阈值与敏感带。
2. **敏感性 100% 来自 C5（`final_rise ≥ 0.04`），C3（`max_rise ≤ 0.15`）一 contribution 都没有。**
   全部边界局都标 `靠近 C5`，没有一个 `靠近 C3` —— 因为这些臂的 rise 全在 0.035~0.045，
   离 0.15 很远。**问题被收窄成一个标量：抬起高度阈值。**
3. **勘误：C5=0.04 的原始理由是错的，但数值应当保留（换一个正确的理由）。**
   门禁里写的理由是「与 robosuite Lift 的成功高度阈值同量级」；实测 robosuite 的
   `_check_success` 等效**相对** rise 阈只有 **0.0082~0.0087 m**，即 C5 比它严 **约 4.7 倍**。
   0.04 这个数碰巧等于 **0.92 × 方块自身全高**（`2×0.0217050 = 0.04341`），
   这才是它该被保留的理由。详见 §4。

---

## 2. 敏感性实测

网格：`final_rise ∈ {0.035, 0.040, 0.045}` × `rise_cap ∈ {0.145, 0.150, 0.155}`（±0.005 m，9 格）。
每格用同一份评测产物重新调用 `judge_file`，取 `accounts.policy_independent.controlled_success`。

| 臂（`runs/infra/lerobot_act_env_20260928/official_act_truth20_*`） | base | min | max | spread | 裁定 |
|---|---|---|---|---|---|
| `trimdone0_minmax_lr1e-5_s20k_seed0` | **2** | 1 | **6** | 5 | threshold_sensitive |
| `trimdone0_minmax_lr1e-5_s20k_seed0_replan1` | **4** | 2 | **6** | 4 | threshold_sensitive |
| `trimdone0_minmax_lr1e-5_s20k_seed1_replan1`* | **2** | 1 | **6** | 5 | threshold_sensitive |
| `train24_lr1e-5_actionminmax_s20k_gatefields` | 0 | 0 | 2 | 2 | threshold_sensitive |
| `train24_lr1e-5_actionminmax_s20k_seed2_gatefields` | 1 | 0 | 1 | 1 | threshold_sensitive |
| `train24_lr1e-4_actionminmax_s20k_gatefields` | 0 | 0 | 0 | 0 | no_controlled_success |
| `train24_lr1e-4_s20k_gatefields` | 0 | 0 | 0 | 0 | no_controlled_success |
| `train24_lr1e-5_actionminmax_s20k_seed1_gatefields` | 0 | 0 | 0 | 0 | no_controlled_success |
| `train24_lr1e-5_actionminmax_s40k_gatefields` | 0 | 0 | 0 | 0 | no_controlled_success |
| `train24_lr1e-5_s20k_gatefields` | 0 | 0 | 0 | 0 | no_controlled_success |
| `trimdone0_minmax_lr1e-5_s20k_seed1` | 0 | 0 | 0 | 0 | no_controlled_success |
| `trimdone0_minmax_lr1e-5_s20k_seed1_replan1` | 0 | 0 | 0 | 0 | no_controlled_success |

\* 表内第三行对应报告里第二个 `seed0_replan1` 同名条目（两个 replan 臂），以 JSON 的 `file` 字段为准。

全部 12 臂 `ic_status = verified_ok`（A 已补 `--record-input-blowup`），
所以**没有一个臂能用「测量无效」解释掉**，敏感性是真实的判据敏感性。

边界局（决定敏感性的那几局，全部 `靠近 C5`）：

| 臂 | seed | base 判定 | final_rise | 距 0.04 |
|---|---|---|---|---|
| trimdone0 seed0 | 5015 | controlled_success | 0.0415 | +0.0015 |
| trimdone0 seed0 | 5000 / 5002 / 5011 / 5017 | insufficient_lift | 0.0360 / 0.0361 / 0.0365 / 0.0351 | −0.004 ~ −0.005 |
| trimdone0 seed0_replan1 | 5000 / 5015 | controlled_success | 0.0412 / 0.0442 | +0.0012 / +0.0042 |
| trimdone0 seed0_replan1 | 5002 / 5006 / 5011 | insufficient_lift | 0.0367 / 0.0350 / 0.0383 | −0.002 ~ −0.005 |
| train24 seed2 | 5001 | controlled_success | 0.0418 | +0.0018 |

读法：这些臂的抬起高度**密集分布在 0.035–0.045**，正好横跨 0.04。
所以「2/20」与「6/20」都不是策略能力的稳定度量，而是阈值切在哪里的函数。

---

## 3. 这不代表「受控成功不存在」

要说清两件事，避免被读成互相矛盾：

- 把阈值**降到 0.035**，受控成功从 2 涨到 6；把阈值**升到 0.045**，仍有 ≥1 局留下。
  所以在整个 ±0.005 带内，**「非零受控成功」这个定性结论是稳的**，
  不稳的是**率**。监管 改判 1「部分满足、非零但不可重复」的定性不受影响。
- 但敏感带这么窄本身就是一个**能力结论**：策略的抬起高度停在 3.5–4.5 cm，
  它不是「抬得很稳但刚好过线」，而是「抬到一半就不够了」。
  这与 A 的 §6 要点 2 独立吻合（`held_at_end` 三臂都是 20/20，卡点不是抓不住、
  不是中途掉落，**唯一卡点是抬起高度**），也与 B 的 L2 诊断（dz 幅度不足/条件均值）同源。

**建议的报告写法**（供 A 与监管采用）：

> 「官方 LeRobot ACT 在冻结测试集上取得非零受控成功：2/20（`final_rise ≥ 0.040`，
> 阈值 ±0.005 的敏感带为 1–6/20；全部边界局都卡在抬起高度 C5，
> 无一局卡在 `rise_cap`）。单训练 seed。」

---

## 4. 勘误：C5=0.04 的理由错了，数值该留

### 4.1 原理由不成立

`scripts/b_gate_controlled_success.py` 里 `FINAL_RISE_MIN = 0.04` 的注释写的是
「与 robosuite Lift 的成功高度阈值同量级」。实测**不成立**：

在 860 行同时带 `success_raw` 与 `max_rise` 的官方臂数据上，两个类别被一条极窄的带完全分开：

| | `max_rise` |
|---|---|
| `success_raw=True`（347 行） | 最小 **0.0087**，中位 0.0330 |
| `success_raw=False`（513 行） | 最大 **0.0082**，p99 0.0079 |

即 robosuite `_check_success`（`cube_height > table_offset[2] + 0.04`，从**桌面 body 原点**起算）
换算成项目用的**相对初始高度**口径后，等效阈值只有 **0.0082~0.0087 m ≈ 8.5 mm**。
原因是方块静止时其中心已高出 `table_offset[2]` 约 3.15 cm，那个 0.04 的绝对量被抵消掉大半。

所以：**C5 比环境自带的成功判据严约 4.7 倍**，二者不是「同量级」。
这也解释了长期困扰三线的落差——同一批臂 `success_raw` 11/20 而受控成功 0~2/20：
不是两套判据在测同一件事时打架，而是它们的**阈值差了 4.7 倍**。监管 改判 2
（`success_raw` 降为参考列）因此是对的，但它给出的原因是「差一个常量偏移」，
实测这个偏移让等效阈从 40 mm 变成 8.5 mm，量级差异比「常量偏移」这个说法更严重。

### 4.2 数值应当保留，换一个正确的锚

0.04 不该改，但理由要换成本项目自己的物理量：

```
方块 z 向半尺寸 = 0.0217050（runs/infra/b_reproducibility/selfcheck.json → geom_values.size[2]）
方块全高        = 2 × 0.0217050 = 0.04341 m
FINAL_RISE_MIN / 全高 = 0.04 / 0.04341 = 0.921
```

即 **C5 ≈「把方块抬起约 0.92 倍自身高度」**。这是一个与环境实现无关、
换物体尺寸会自动跟着变的**物理判据**，比「跟 robosuite 同量级」强得多，
也正好落在实测 rise 分布（0.035–0.045）之上、能把「抬了一半」挡在外面。

B 的建议（**不自行改阈值**，因为改它会直接放大所有历史臂的成功率，属监管裁决范围）：

1. **保留 0.04**，把代码与规格里的理由改成「≈0.92×物体全高」，删掉 robosuite 那句错误依据。
2. **把 C5 改成随物体几何缩放**：`FINAL_RISE_MIN = 0.92 × 2 × size_z`，
   这样换 cube / 换 pickplace 物体时判据自动跟随，不需要人工重标定。
   （需读 `object_geom`，评测产物里已有该字段。）
3. **强制随率一起报敏感带**：任何「受控成功 N/M」都必须附 `±0.005` 的 min–max，
   B 的敏感性脚本已可直接产出。
4. 若监管认为 8.5 mm 才是「与环境一致」的口径，那需要**显式新建一档判据**
   （例如 `rise_min_env_equiv = 0.0085`）并与 C5 并列报告，
   **不得**用替换 C5 的方式引入——那会让 09-24 以来所有受控成功数字失去可比性。

---

## 5. 回应 A 的 `failed_checks` 口径问题：门禁升 v1.2，新增 `insufficient_lift`

A 的问题（`docs/lerobot_act_env_setup_20260928.md` §6 要点 3）：
`raw_success ∧ ¬C5` 被一律标成 `flick`，但那 14 局 `max_rise` 全 ≤0.042（远低于 `rise_cap` 0.15）、
`held_at_end` 20/20，根本不是「把方块弹射出去」，只有翻 `failed_checks` 才能区分。

**A 的判断成立，已采纳。** v1.2 的判定顺序：

| 条件 | verdict | 根因指向 |
|---|---|---|
| 局末已不夹持（`held_at_end=False`），或无 `held_at_end` 证据且 `final_rise<min` | `flick` | 真脱手/弹射：对齐前闭爪、夹到边角 |
| 抓住且未超 `rise_cap`，但 `held_at_end=True ∧ final_rise<min` | **`insufficient_lift`（新）** | 抬起幅度不足：dz 增益/条件均值，与 `over_lift` 是同一变量的相反方向 |
| `max_rise > rise_cap` 且仍夹持 | `over_lift` | 抬起停不下来：hold/done 段 dz 正泄漏 |
| C1–C5 全过 | `controlled_success` | — |

三类现在互斥且各自指向不同修复动作，汇总行不再需要翻 `failed_checks`。

实测效果（v1.2 重判，当前构建 v1.2.1 下计数不变；`gate_build` 见产物内字段）：

| 产物 | raw | ctrl | flick | over_lift | **insufficient_lift** |
|---|---|---|---|---|---|
| `official_act_truth20_train24_lr1e-5_actionminmax_s20k_gatefields` | 11 | 0 | **0** | 0 | **11** |
| `official_act_truth20_train24_lr1e-5_actionminmax_s20k_seed2_gatefields` | 4 | 1 | **0** | 0 | **3** |
| `runs/infra/b_normclip/clip3.json`（B 的截断探针臂） | 15 | 1 | 2→**1** | 12 | **1** |

即 A 那 14 局里，**没有一局是弹射**，全部是抬起不足 —— 这直接支持 A 的
「唯一卡点是抬起高度、问题收窄成一个变量 dz」的结论。

兼容性说明（引用旧数字时注意）：

- `controlled_success` 计数**不变**（v1.2 只重新标注非成功局，没有放宽任何判据），
  所以 §2 的 base 列与历史 `controlled_success` 可直接比较。
- `flick` 计数**会变小**（一部分转成 `insufficient_lift`）。
- `flick_frac_of_raw_success` 这个键名是历史遗留，它算的一直是「raw 成功里不受控的比例」
  （含 `over_lift`，v1.2 起也含 `insufficient_lift`），CLI 表头因此写 `unctrl%`；
  数值对 clip3 仍是 93%（1+12+1 / 15），未因分类细化而变。
  需要**纯弹射**比例时用新增的 `flick_frac_strict`。

---

## 6. 复现

```bash
cd /workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot

# 阈值敏感性（本报告 §2）
python3 scripts/b_gate_threshold_sensitivity.py \
  --glob 'runs/infra/lerobot_act_env_20260928/official_act_truth20_*gatefields*.json' \
  --glob 'runs/infra/lerobot_act_env_20260928/official_act_truth20_trimdone0_minmax_lr1e-5_s20k_seed*.json' \
  --json-out runs/infra/b_gate_sensitivity/report.json

# v1.2 分类（本报告 §5）
python3 scripts/b_gate_controlled_success.py \
  runs/infra/lerobot_act_env_20260928/official_act_truth20_train24_lr1e-5_actionminmax_s20k_gatefields.json

# robosuite 等效阈（本报告 §4.1）：对 official_act_truth20_* 的
# success_raw × max_rise 做两侧极值，见 docs 中给出的 0.0082 / 0.0087 分界
```
