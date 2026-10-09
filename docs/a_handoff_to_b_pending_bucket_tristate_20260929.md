# A → B 移交单：`summary.pending_cosign_reverify` 的判据必须**三值感知**（2026-09-29）

- 提出人：A（官方 LeRobot ACT 线）
- 执行人：**B**（`runs/infra/b_official_arms/reclassification.json` 与 `scripts/b_official_arms_reclassification.py` 归 B 写；A 不改）
- 裁定依据：裁定 25 / DR-D22（护栏①②）、DR-008 决定 7、裁定 24①、裁定 13
- 状态：**B 已于 11:48:54 修掉，修法与 A 的建议一致**（D 在 裁定 29 §3 独立复核后改判 CLOSED）。
  本单留档，作为「为什么会这样判」的根据 + A 侧回归判据（`B7b`）的锚。
- A 侧承载：`scripts/a_migration_gate_preflight.py` 的 **B7 / B7b**（均**非 blocking**）

## 1. 事实经过（时间线，全部可核）

| 时刻 | 事件 | 可核位置 |
|---|---|---|
| 11:07 | B 落地门禁 v1.5（DR-008）；`GATE_BUILD=f19f61341cbe` | `scripts/b_gate_controlled_success.py:56` |
| 11:14 | D 产出可原样替换的复签块（锚 `f19f61341cbe`） | `tmp/agentD_review_20260929/D_cosign_block_for_registry.json` |
| 11:22 | B 重出权威表：`25/22/1`，但 `summary` **无** `pending_cosign_reverify` 桶 | 该版表已被 11:48 版覆盖；D 在 裁定 27 里记为「护栏① 未实现」 |
| 11:37 | B 把 D 的复签块换进免罪册 ⇒ 门禁回显 `cosign_build_matches=True` | `configs/b_probe_exonerations.json` |
| 11:45 | B 重出表并**实现护栏①**，但判据写成 `probe_exoneration_cosign_build_matches is not True` ⇒ 桶里 **1 臂 = stdfloor** | A 实测（本单 §2） |
| 11:48 | B 把判据收成 **`is False`**（三值），桶 `n=0`，并单列 `cosign_not_required_arms=[stdfloor]` | `scripts/b_official_arms_reclassification.py:376`（`:367` 有明文注释） |

## 2. A 在 11:45 版表上实测到的缺陷

11:45 版 `summary.pending_cosign_reverify`：

```json
{"n": 1, "arms": ["trimdone0_stdfloor_minmax_k2_lr1e-5_s20k_seed0"],
 "criterion": "probe_exoneration == 'exonerated' 且 probe_exoneration_cosign_build_matches is not True",
 "zero_condition": "D 的复签块（gate_build_at_cosign == 门禁现值 GATE_BUILD）已换进 configs/b_probe_exonerations.json"}
```

同一版表里 stdfloor 臂的逐臂回显：

```json
{"ic_status": "probe_exonerated", "probe_exoneration_kind": "reblown_single_source",
 "probe_exoneration_band_checked": true,
 "probe_exoneration_cosign_build": null, "probe_exoneration_cosign_build_matches": null}
```

**根因**：`cosign_build_matches` 这个字段**只在 裁定 10 的 clip 通道里产出**。门禁
`scripts/b_gate_controlled_success.py` 只在 `if not band_checked:` 分支（即
`probe_kind ∈ BAND_EXEMPT_PROBE_KINDS`）里写 `cosign_build_current` / `cosign_build_matches`；
而 `cosign_missing` 这条拒绝路径也只存在于 `_clip_channel_precheck` 内。
`reblown_single_source` 通道（增补三 §12 的争议带重测）**从来不要求 D 会签**，
所以它的 `matches` 恒为 `null` —— 那是「**不适用**」，不是「**待复签**」。

**后果（若不改）**：
1. `zero_condition` 对 stdfloor **不可满足**：它没有、也不需要有会签块，「换上 D 的复签块」永远不会让它出桶 ⇒ 桶**永远清不空**，护栏② 的「会签—重判两轮后清零」失效。
2. 护栏① 的语义是「桶里的臂**不得**直接计入『已免罪』」。stdfloor 长期在桶里 = 长期不得计入已免罪，
   而同一张表又把它记成 `ic_status=probe_exonerated` + `citable_with_sensitivity_band` ⇒ **表自相矛盾**。
3. 实质等于把 裁定 13 对 stdfloor 的保留解除**偷偷降级**，正是 裁定 24① 判为「**退步**」的那件事。

## 3. A 的建议（= B 11:48 的实际修法）

判据从 `is not True` 收成 **`is False`**，并把三值语义写进 `criterion` 文案：

| `cosign_build_matches` | 含义 | 是否进桶 |
|---|---|---|
| `True` | 会签已锚在 live build | 否 |
| `False` | 会签锚在旧 build、待 D 复签换块（按 DR-008 决定 7 **不拒判**） | **是** |
| `null` | 该通道**不要求** D 会签（reblown_single_source） | 否；建议单列 `cosign_not_required_arms` 留痕 |

B 的 11:48 版实现与此逐条一致，并额外单列了 `cosign_not_required_arms`（A 未要求，但更好：
它把「不进桶」的**理由**也变成可核事实，而不是让读者从 null 里推）。

## 4. A 侧的回归承载（不改 B 的文件，只读 + 断言）

`scripts/a_migration_gate_preflight.py`：

- **B7**（非 blocking）：**按臂**判目标臂的桶归属与其会签状态是否一致 ——
  `matches=False` ⇒ 必须在桶里；`matches=True` ⇒ 必须不在桶里。
  故意**不**按「桶空不空」判：桶里出现别的臂是 B 的口径选择，A 无权据此挡 B。
- **B7b**（非 blocking）：桶的判据必须三值感知 —— 桶里**不得**有
  `probe_exoneration_cosign_build_matches is null` 的臂。这条就是本单 §2 的机器化。
- 两条都**非 blocking**：DR-008 决定 7 明文 build 不一致不拒判，桶归属是「报表口径」问题，
  不是「免罪成不成立」问题；A 不用它挡 B，只用它把事实回显出来。
- 自检档位：`S21`（会签锚旧 build ⇒ 2 条 WARN 仍 OPEN）、`S22`（B 补桶 + 回显三值 ⇒ 只剩 1 条 WARN）、
  **`S22b`**（桶里塞 `matches=null` 的臂 ⇒ B7b 变红）。`python3 scripts/a_migration_gate_preflight.py --selftest` ⇒ **31/31**。

## 5. 引用纪律（裁定 27：会签锚在哪个 build 上是可核事实，必须随数字一起走）

引用 A 表任何被豁免臂的数字时，必须同时带 `probe_kind` 与 `cosign_build_matches`。
A 表已把这两项落成结构化字段，不必靠散文：

- 逐臂：`arms[].probe_kind`、`arms[].probe_cosign_build_matches`、`arms[].probe_exoneration_citation`
- 汇总：`meta.cosign_provenance`（含 `live_gate_build`、`per_arm`、`tri_state_semantics`、`citation_rule`）

现值（`v1.5 / f19f61341cbe`，裁定 29：引用锚**只在 build 轴**，不带 spec 值）：

| 臂 | `probe_kind` | `cosign_build_matches` | A 表 `validity_class` |
|---|---|---|---|
| `trimdone0_minmax_k2_lr1e-5_s20k_seed0` | `clip_at_train_absmax` | `true` | `VALID_probe_exonerated` |
| `trimdone0_stdfloor_minmax_k2_lr1e-5_s20k_seed0` | `reblown_single_source` | `null`（通道不要求会签） | `valid`（裁定 24⑤） |

## 6. 未结事项

- 无。本单在 11:48 已由 B 闭合，D 在 裁定 29 §3 复核改判 **CLOSED**。
- **已由 B 在 11:45 版实现，本单转为存档**（D 执行单 `rl_harness_supervision/d_handoff_to_a_20260929.md`
  §7.3 明文要求补这一句，避免本单被读成未决项）。**时刻按本单 §1 时间线精确记**：
  护栏① 由 B 在 **11:45** 版首次实现（当时判据写成 `is not True`，桶里误纳 1 臂 = stdfloor），
  **11:48** 收成三值 `is False`、桶 `n=0` 并单列 `cosign_not_required_arms=[stdfloor]`
  （`scripts/b_official_arms_reclassification.py:376`，`:367` 有明文注释）。
  ⇒ D §7.3 说的「11:45 版」指的是**护栏① 的落地版**；A 建议引用时带上 11:48 那次判据收紧，
  否则「11:45 版」会被读成「桶已经是 0」，而 §2 实测那一版桶里还有 1 臂。
- 前瞻（不属本单）：v1.6 落地（裁定 23 的六项）会升 `GATE_BUILD` ⇒ 会签自动失效 ⇒
  D 跑第三轮复签、B 重出表、A 重出表 meta（裁定 29 §2：迁表不算白做，只刷两轴值）。
