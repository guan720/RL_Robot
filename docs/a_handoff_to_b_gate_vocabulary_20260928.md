# A → B 移交：门禁「证据不足仍输出最重失效模式标签」的最小复现（2026-09-28 22:07）

移交方：智能体 A（官方 LeRobot ACT 线）。接收方：智能体 B（门禁 / 可复现）。
监管依据：增补四 §1 裁定 8、增补五 §1 **裁定 14**（`field_class != strict` 禁输出失效模式标签，DR-D09）、
增补五 §7（给 B 的现成回归算例）、增补五 §8 A-3。
立场：**A 不改门禁代码**（ADR-A-003 不变）。本文档只给最小复现 + 期望值 + 已跑出的实测证据。
所有 A 侧新产物落在 `runs/infra/lerobot_act_env_20260928/v13probe/`（**独立子目录**，
`arms_summary.json` 的 glob 不覆盖它，符合裁定 16「v1.3 局部结果不得与 v1.2.1 混表」）。

---

## 1. 结论先行（两条，一条已修、一条未修）

| # | 缺陷 | v1.2.1（`e4f5ec887788`） | **v1.3 工作树（`4f20b3ec9130`）实测** | 状态 |
|---|---|---|---|---|
| 1 | 裁定 8：`phase_at_end` 属状态机词表但产物没写 `phase_trace` → 20 局静默判 `flick` | residual 臂 `flick=20`、`controlled_success=0` | `unjudged=20`、`flick=0`、`gate_reason=phase_vocab_mismatch` | **已修** ✅（B 的 v1.3「裁定 1」分支，`scripts/b_gate_controlled_success.py:459-472`） |
| 2 | 裁定 14：`field_class=partial`（4 个关键字段全缺）→ 仍输出 `flick` | 5 盲臂合计 `flick=16`、`insufficient_lift=0` | **仍输出 `flick=11 / 3 / 2`，`unjudged=0`** | **未修** ❌（本文档的移交主体） |

第 2 条的影响面已经在权威表里量化过：16 局 `flick` 是假标签，补测后全部翻成 `insufficient_lift`，
另 1 局 `provisional_pass` 升级成 `controlled_success`（增补五 §1 表 / A §21.10）。
可引用的 `flick` 因此只剩 **2 局 / 920**（0.2%）→ B-7「连续性 / slew-limit」继续停车的依据（增补五 §7）。

## 2. 缺陷 2 的最小复现（一个臂、一份产物、11 局）

**臂**：`train24_lr1e-5_actionminmax_s20k`（train24 全量 7200 帧、MIN_MAX、lr 1e-5、20k 步、K=R=4）
**产物**：`runs/infra/lerobot_act_env_20260928/official_act_truth20_train24_lr1e-5_actionminmax_s20k.json`
（旧评测器产物：`field_presence` = `final_rise 0 / held_at_end 0 / terminal_kind 0 / phase_at_end 0 / max_rise 20 / grasp_verified 20`
⇒ `field_class="partial"`、`missing_fields=["final_rise","held_at_end","phase_at_end","terminal_kind"]`）

```bash
# 复现（只读；写出到 /tmp，不碰任何留档）
/root/venvs/lerobot_eval/bin/python scripts/b_gate_controlled_success.py \
  runs/infra/lerobot_act_env_20260928/official_act_truth20_train24_lr1e-5_actionminmax_s20k.json \
  --json-out /tmp/b_repro_partial.json
```

**实测（v1.3 / `4f20b3ec9130`，留档于 `v13probe/gate_partial_train24_lr1e-5_actionminmax_s20k.json`）**：
`field_class=partial`、`measurement_valid=False`、`accounts.policy_independent.flick=**11**`、
`insufficient_lift=0`、`n_unjudged=**0**`；逐局 verdict = `flick×11 + failure×9`。

**逐局证据（ep5000，v1.3 原文）**：

```json
{"seed": 5000, "verdict": "flick",
 "checks": {"grasped": true, "rise_cap": true, "end_phase": false,
            "final_rise": null, "held_at_end": null},
 "evidence": {"phase_field_kind": "per_frame", "end_phase": "grasp",
              "c4_basis": "end_phase=grasp（strict：仅认 hold）",
              "terminal_kind": null, "n_phase_trace": 300,
              "phase_vocab_status": "absent_field", "unjudged_reason": null}}
```

**同一局的补测（strict）版本**（`blindfix/official_act_truth20_train24_lr1e-5_actionminmax_s20k.json`，
留档裁定 `blindfix/regate_current/gate_train24_lr1e-5_actionminmax_s20k.json`）：

```json
{"seed": 5000, "verdict": "insufficient_lift",
 "evidence": {"phase_field_kind": "per_frame", "end_phase": "grasp",
              "c4_basis": "held_at_end=True & end_phase=grasp",
              "terminal_kind": "horizon_exhausted", "n_phase_trace": 300}}
```

**两份产物在物理上是同一次评测**：`blindfix/blindfix_vs_archived.json` 记
`n_identical_on_common_fields=5`、`n_differing=0`（唯一允许差异 `rows[].elapsed_sec`）。
差别只有：`held_at_end` / `final_rise` / `terminal_kind` / `phase_at_end` **在不在**。

⇒ 同一个 `"grasp"` 标签，在 `held_at_end` 存在时被 `HOLD_PHASES_WITH_EVIDENCE={"hold","grasp"}` 接受
（`scripts/b_gate_controlled_success.py:480`），在 `held_at_end` 与 `final_rise` 双缺时被
`HOLD_PHASES_STRICT={"hold"}` 拒绝（`:488`）→ `c4=False` → `:192` 一路返回**最重的失效模式 `flick`**。
**「证据不足」被解析成「判成脱手弹射」，而不是弃权。**

## 3. v1.3 已经知道该弃权，只是没用这个信息

v1.3 新加的 `phase_vocab_status` 在这一局上算出的值是 **`"absent_field"`**（见 §2 的 evidence），
而 `:467` 的弃权条件只覆盖 `vstat.startswith("mismatch")` 与 `vstat == "unknown_vocab"`：

```python
vstat, vnote = phase_vocab_status(row, kind, end_phase)
if vstat.startswith("mismatch") or vstat == "unknown_vocab":
    return "unjudged", ...
```

`"absent_field"` 落空 → 继续走 C4 分支 → 输出 `flick`。
同时文件级 `field_class` 已经算出 `"partial"`（`:670-671`），也没有被用来拦住标签输出。
**弃权所需的两条信息（`phase_vocab_status="absent_field"`、`field_class="partial"`）都已在同一份裁定 JSON 里。**

给 B 的两个可选落地点（A 不代改，任选其一即可满足裁定 14）：
- **文件级**（更贴近裁定 14 原文）：`field_class != "strict"` ⇒ 所有局的失效模式标签改判
  `unjudged_evidence_missing`、计入 `n_unjudged`、`measurement_valid=False`、`gate_reason` 列出 `missing_fields`；
- **局级**（更贴近 v1.3 现有结构）：把 `:467` 的弃权条件扩到 `vstat == "absent_field"`
  （即 `held_at_end` 与 `final_rise` 双缺、per-frame 词表只有 `grasp` 时不猜）。

**不动的东西**（增补五 §1 明确）：`provisional_pass` 通道是 v1.1 有意设计的「待补测」档，
它**正确地**没把 `seed2 ep5001` 算成受控成功；裁定 14 只禁**失效模式**标签。

## 4. 完整回归算例集（A 已在 v1.3 上跑完，实测值即期望值）

留档目录：`runs/infra/lerobot_act_env_20260928/v13probe/`（构建 `4f20b3ec9130`，逐份 JSON 都带 `gate_build`）。

### 4.1 方向一：`partial` 必须弃权（**当前失败，裁定 14 落地后应变成 `unjudged`**）

| 产物（留档 partial） | v1.3 实测 `flick` | v1.3 实测 `unjudged` | 裁定 14 后期望 |
|---|---|---|---|
| `train24_lr1e-5_actionminmax_s20k` | **11** | 0 | `flick=0`、`unjudged=11`、`insufficient_lift=0` |
| `train24_lr1e-5_actionminmax_s20k_seed2` | **3**（+`provisional_pass=1`） | 0 | `flick=0`、`unjudged=3`、`provisional_pass` 通道**不动** |
| `train24_lr1e-5_s20k` | **2** | 0 | `flick=0`、`unjudged=2` |
| `train24_lr1e-4_s20k` | 0 | 0 | 全 0（本来就无标签，**不得**因改动而新增） |
| `train24_lr1e-5_actionminmax_s20k_seed1` | 0 | 0 | 全 0（同上） |

5 臂合计 **16 局假 `flick`**，与增补五 §1 的 D 独立复算一致。

### 4.2 方向二：`strict` 不得误伤（**当前已通过，改动后必须仍然通过**）

| 产物（blindfix 补测，strict） | v1.3 实测 | 期望（不变） |
|---|---|---|
| `train24_lr1e-5_actionminmax_s20k` | `ctrl=0`、`insufficient_lift=**11**`、`flick=0`、`mv=True` | 同 |
| `train24_lr1e-5_actionminmax_s20k_seed2` | `ctrl=**1**`、`insufficient_lift=**3**`、`flick=0`、`gate_pass=True (pass)` | 同（含 ep5001 由 `provisional_pass` 升级） |
| `train24_lr1e-5_s20k` | `ctrl=0`、`insufficient_lift=**2**`、`flick=0` | 同 |
| `train24_lr1e-4_s20k` / `..._seed1` | 全 0、`mv=True`、`gate_reason=no_controlled_success` | 同 |

### 4.3 方向三：裁定 8 已修，改动不得回退

| 产物 | v1.2.1 | **v1.3 实测** | 期望（不变） |
|---|---|---|---|
| residual `audit_truth20_gatefields_pre_phase_trace.json`（`phase_at_end="done"`、无 `phase_trace`） | `flick=20`、`ctrl=0` | `unjudged=**20**`、`flick=0`、`phase_vocab_status=mismatch_no_trace` | 同 v1.3 |
| residual `audit_truth20_gatefields.json`（同一物理 run，**有** `phase_trace`，6 段） | `ctrl=20`、`flick=0` | `ctrl=**20**`、`flick=0` | 同（两份 `final_rise=0.096724`、`held_at_end=True`、`raw=20/20` 完全相同） |

这一对是「**只加一个日志字段，20 局从 `flick` 变 `controlled_success`**」的取证：
说明失效模式标签曾经依赖**字段可得性**而不是证据本身。v1.3 已把它改成弃权，A 确认无回退。

### 4.4 建议进 `scripts/b_selfcheck_gate_regression.py`

上面 12 份产物（5 partial + 5 strict + 2 residual）都是**有真值、零算力**的算例：
不改门禁时跑一遍应全绿；裁定 14 落地后 4.1 的 5 行期望值改变、4.2 / 4.3 必须一字不变。

## 5. A 侧已经做的（不改门禁，只在汇总层执行裁定 8 推广）

`scripts/summarize_lerobot_act_arms.py`（`arms_summary.json` 的唯一生产者，`schema_version=2`）：
- 每行加 `labels_reportable = (field_class == "strict" and validity_class != "invalid")`；
- `labels_reportable=False` 的行，`insufficient_lift / over_lift / flick` 一律置 `null`（表里显示 `-`），
  **不进任何合计**；原始值保留在 `*_raw` 字段备查（不销毁证据）；
- 合计只给带 scope 标签的四个口径（见 §21.10(3)），不再输出「48 臂合计 134/219/23」这类混口径总数；
- `validity_class` 三取值 + `probe_exoneration` 的 5 条准入**在代码里断言**（裁定 10），
  `blowup_threshold_source` 逐行带阈值来源（裁定 11）。

⇒ 即使 B 侧 v1.3 暂未落地裁定 14，A 的权威表也**不会**把 `partial` 产物的假 `flick` 传下去。
但**门禁自身**仍会对任何新的 `partial` 产物输出假标签（含 C 线账本，见增补五 §7 给 C 的连带项：
裁定身份必须含 `field_class` / `validity_class` / `blowup_threshold_source` 三键），所以裁定 14 仍需 B 落地。

## 6. 边界（A 不做的事）

- 不改 `scripts/b_*.py`、不改 `docs/b_*.md`、不改 B 的留档裁定；
- 不把 `v13probe/` 的结果写进 48 臂权威表或任何跨 build 合计（裁定 16）；
- 不代 B 决定 `unjudged_evidence_missing` 的具体字段名与 `n_unjudged` 语义；
- 不重跑任何评测来「补」partial 产物 —— 补测已在 `blindfix/` 完成并证明共有字段逐位相同。
