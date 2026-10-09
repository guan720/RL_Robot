# 受控成功判据 v1.5（B 线门禁规格）

日期：2026-09-28　　负责线：B（门禁与可复现性）
可执行实现：`scripts/b_gate_controlled_success.py`（只读后处理，不改任何评测器）
本文件是**规格**；改判据必须升版本号（v2…）并在 §6 登记，不得原地改语义。

**构建冻结声明（裁定 26 前提①，D 要求 B 明文声明）**：本版 v1.5 的可执行实现
`scripts/b_gate_controlled_success.py` 冻结在 **`GATE_BUILD = f19f61341cbe`**。
D 的复签（`configs/b_probe_exonerations.json` 里 `85c46dfb…` 条目的 `cosign` 块，
`gate_build_at_cosign = f19f61341cbe`）锚在这个 build 上；**B 在此之后不再改该脚本**。
下一批判据变更（裁定 23 的六项，见 §2.18）已预登记为 **v1.6**，落地即升 build，
届时 D 须重跑 `scripts/d_verify_exoneration_cosign.py` 复签（裁定 25 / DR-008 决定 7）。
规格文档哈希（`GATE_SPEC_SHA`）是**另一根轴**：本次收尾的文档编辑会使其从 `154b3636056f`
前移，属文字/登记变更、**无判据变更**，不影响 build 轴上的会签效力；两轴现值一律以
`runs/infra/b_official_arms/reclassification.json` 的 `gate_build` / `gate_spec_sha256` 为准。

## 1. 裁定

监管 P0 要求 Lift 成功「可重复的非零 `grasp_verified`，且不是 flick」，但仓库里三个评测器
对 flick 的可见度不一致，导致「成功率」这一主指标目前**不可比**：

| 评测器 | `max_rise` | `final_rise` | 局末 `held` | `phase_at_end` | `rise_at_success` | `terminal_kind` | 能否自证非 flick |
|---|:--:|:--:|:--:|:--:|:--:|:--:|---|
| `scripts/audit_lift_base_truth.py` | 有 | 有 | 有(`held`) | 有 | 有 | 无 | **能**（参考实现） |
| `scripts/eval_act_lift_truth.py:38` | 有 | 无 | 无（只有 ever-held） | 无（可由 `phase_trace[-1]` 兜底） | 无 | 无 | **不能** |
| `scripts/eval_lerobot_act_runtime.py:187` | 有 | 无 | 无 | 无（可由 `phase_trace[-1]` 兜底） | 无 | 无 | **不能** |

**重要**：v1 门禁首次实现时对 residual 臂产生过**假阳性 FAIL**（因缺 `final_rise` 就整条否决），
已修正为「C5 缺字段 ⇒ 不适用、不判失败、标注偏松」。这条教训写进 §2：
门禁本身必须有反例自检，否则它会否掉真实结果、比没有门禁更危险。

裁定：**自 v1 起，任何 Lift 接触任务的「成功」主张必须同时报 `success_raw` 与
`controlled_success`；只有 `controlled_success` 能用于监管 P1 晋级条件第 1 条。**
`success_raw` / `mean_max_rise` 降为诊断量。缺 `final_rise` 的评测产物可以被本门禁事后判定，
但必须在报告里标注「判定偏松（C3 由 `phase_trace` 兜底）」。

已经受影响的既有结论（需按 v1 重算后才能进研究结论表）：

| 产物 | 原报 | v1 门禁复核 |
|---|---|---|
| `runs/infra/b_env_rebuild/base_truth20.json`（scripted base，B 复现） | 20/20 | **20/20 受控，PASS**（`final_rise≈0.065`，全部 end=`done`） |
| `runs/infra/b_act_lift_mb_hist1_seed0/audit_truth20.json`（B minibatch 臂） | raw 10/20, sgv 10/20 | **整条作废**（robosuite 1.5.1、obs_dim=53，见 `docs/b_reproducibility_incident_20260928.md` §5）。重训钉死几何后同一策略只有 raw 3/20 |
| `runs/infra/b_act_lift_mb_hist4_seed0/audit_truth20.json` | raw 4/20 | **整条作废**（同上） |
| `runs/infra/act_lift_k4_state_hist1_seed0/audit_truth20.json`（A baseline） | raw 1/20, sgv 0/20 | 受控 0/20，FAIL；**且 v1.1 判 `INVALID`**（输入契约违例，见 `docs/b_normalization_incident_20260928.md` §9） |
| `runs/20260924_142702_sac_lift_residual_grasp_lift/audit_truth20.json`（residual 臂） | raw 20/20 | ~~受控 20/20 PASS~~ → **v1.1：20 局 `provisional_pass`，gate FAIL**（缺 `final_rise` 与 `held_at_end`；`phase_trace` 只有 6 元素状态机日志，而 `hold→done` 是纯计时转移，不能证明局末仍夹持）。按 §4 补 2 个字段即可恢复裁定 |
| `runs/20260924_142907_lift_base/audit_truth20.json`（A 的 base 臂） | raw 20/20 | **受控 20/20，PASS** |
| `runs/20260924_153014_sac_lift_from_scratch_seed0/audit_truth20.json` | raw 0/20 | 受控 0/20，FAIL（结论不变） |

## 2. 判据（五条，全过才算 `controlled_success`）

| 编号 | 判据 | 默认阈值 | 依据 |
|---|---|---|---|
| C1 | `success_raw == true` | — | robosuite 环境自身成功判定 |
| C2 | `grasp_verified == true` | — | `robosuite._check_grasp` 真值，非宽度启发式 |
| C3 | `max_rise <= rise_cap` | **0.15 m** | scripted base 实测 `mean 0.0764 / max 0.078`，取约 2 倍；方块初始 z≈0.83 m，Panda 工作空间不可能受控举到 2 m，超过即接触爆炸式弹射 |
| C4 | 局末仍处夹持。**v1.1 起按 `phase` 字段的语义分别取证据**，见 §2.1 | — | 弹射后方块落回桌面、机械臂离开，局末必然回到 `approach` |
| C5 | `final_rise >= final_rise_min` | **0.04 m** | 与 Lift 成功高度阈值同量级；base 实测 `final_rise≈0.065`。**字段缺失时不判失败，但报告必须标注偏松** |

### 2.1 v1.1 对 C4 的收紧（修一个真实的假阳性通道）

v1 把 C4 写成 `phase_at_end ∈ {hold, done, grasp}`，这里有三个当时没查清的问题：

**(1) `phase_of()` 的 `grasp` 意思是「两指张开超过 1.2cm」，不是「夹住了」。**
判据是 `max|robot0_gripper_qpos| > 0.012`（`scripts/b_eval_act_lift_v1.py:38`）。
方块宽 4.4cm，夹住它时单指 qpos≈0.022；**空爪全开时≈0.042**。两者都 > 0.012，
拿到同一个标签。所以 `grasp` 单独**不能**证明局末仍夹持。
v1 里它配合「C5 缺字段 ⇒ 不判失败」的偏松通道会产生假阳性 PASS：
夹起 → 升到 0.10m（`success_raw=True`、`held_ever=True`）→ 滑落回桌面 → 爪重新张开
→ `max_rise=0.10 ≤ 0.15`、`end_phase="grasp"` → **v1 判 controlled_success**。
`runs/infra/b_flick_sweep/mb_none.json` 的 seed 5018 就是这个形状
（`max_rise=0.043`、`final_rise=-0.0101`、`end=approach`），只因它有 `final_rise` 才被拦下。

**(2) `done` 在逐帧 `phase_of()` 的词表里根本不存在。**
`phase_of()` 只可能返回 `{hold, grasp, descend, approach}`。`done` / `lift` 只出现在
**状态机日志**里。v1 把两套词表塞进同一个集合，等于没定义。

**(3) `phase_trace` 是同名字段、两套不兼容语义**（实测）：

| 产出方 | `phase_trace` 是什么 | 长度 | 词表 |
|---|---|---|---|
| `scripts/audit_lift_base_truth.py`、residual audit | 脚本控制器的**状态机日志** | 6 | approach/descend/grasp/lift/hold/**done** |
| `scripts/b_eval_act_lift_v1.py`、`eval_act_lift_truth.py`、`eval_lerobot_act_runtime.py` | **逐帧** `phase_of()` 分类 | ≤ horizon(300) | hold/grasp/descend/approach |

v1 的 `phase_at_end or phase_trace[-1]` 兜底把两者混用——用 A 的语义去满足 B 的判据。

**v1.1 的裁定规则**（`classify_phase_field()` 先分流，再取证据）：

| 可用证据 | C4 判据 |
|---|---|
| `phase_trace` 是状态机日志 | 末元素 ∈ `{hold, done}`。**注意**：`LiftStateMachine` 的 `hold→done` 是**纯计时**（`phase_step >= HOLD_STEPS=30`，不复查抓取），所以日志到达 `done` **只证明控制器走完了流程，不证明方块还在爪里**，必须与 `final_rise` 或 `held_at_end` 合用 |
| 有 `held_at_end` | `held_at_end == True` **且** `end_phase ∈ {hold, grasp}` |
| 无 `held_at_end`、有 `final_rise` | `end_phase ∈ {hold, grasp}`，由 C5 承担夹持证明 |
| 两者都缺 | `end_phase` **只认 `hold`**；若判成 `grasp` 则降级为 `provisional_pass` |

### 2.2 v1.1 新增裁定：`over_lift` 与 `flick` 必须分开

两者都过不了 C3（`rise_cap`），但指向完全不同的旋钮，混为一谈会让人去修错的东西：

| 裁定 | 条件 | 含义 | 该动哪个旋钮 |
|---|---|---|---|
| `over_lift` | raw ∧ grasped ∧ 局末仍夹持 ∧ `max_rise > cap` | 抓住了、方块没掉，只是**上升停不下来** | 训练侧的 dz 正偏；见 `docs/b_normalization_incident_20260928.md` §5 |
| `flick` | raw ∧（`held_at_end=False` 或 `final_rise < min`） | 方块**脱离夹爪** | 对齐前闭爪 / 夹到边角弹射，deadband 修不了 |

实测依据：`runs/infra/b_flick_sweep/mb_none.json` 的 seed 5002/5015，
`max_rise=0.376/0.634` 但 `final_rise=0.3592/0.6233`、`held_at_end=True`、`end=hold`
——方块全程在爪里。v1 把它和真弹射一起叫 `flick`，导致「flick_frac=100%」这个
被引用过的数字**掩盖了「抓取其实成功、只是抬太高」**这一关键区别。
输入截断修复后（`runs/infra/b_normclip/clip3.json`）失效几乎全是 `over_lift`（12/15），
正是这个区分让下一步该修什么变得明确。

### 2.3 v1.1 新增：策略输入契约 → `INVALID`（测量无效 ≠ 策略失败）

评测产物若带 `norm_input_blown_frames_frac`（由
`scripts/b_eval_act_lift_v1.py --record-input-blowup` 写出），且超过
`INPUT_BLOWUP_TOL = 0.05`，门禁判 **`INVALID`（`gate_reason=measurement_invalid`）**，
不是 `FAIL`。

理由见 `docs/b_normalization_incident_20260928.md`：`(x-mean)/(std+1e-6)` 对近常量维
无下限保护，闭环里归一化输入实测最大到 **20402.6**（训练上界 23.7），
**94% 的帧**超出训练分布。此时「成功率」测的是数值事故，不是策略能力。
把它判成 `FAIL` 会让人得出「ACT 学不会抓取」的错误结论——这正是过去几天发生的事。

容差设 5% 是因为实测健康臂为 0%、事故臂为 89~97%，中间没有灰区。

### 2.4 v1.1 新增：`terminal_kind` 语义自检

`envs/robosuite_pickplace.py:135` 的 `step()` **恒返回 `terminated=False`**，
`trunc` 来自 robosuite 的 `done`；实测 Lift 全部 20 局都跑满 `horizon=300`
（`steps` 全为 300），**成功也不提前终止**。
所以 `b_eval_act_lift_v1.py` 里 `terminated_failure` 这个标签其实是 `truncated_horizon`。

裁定不变（任务确实没成功），但门禁会报 `suspect_truncation_labeled_as_failure`：
该标签**不得进训练视图**——v4 要求终局与外部截断分开，两者 bootstrap 语义不同
（终局不 bootstrap，外部截断要 bootstrap）。

补充不变量（v4 对齐）：

- `terminal_kind ∈ {unknown, preempted, takeover}` 的局 **既不算成功也不算失败**，移出所有分母，
  单独报 `n_unjudged` 与 seed 列表。unknown ≠ 失败、≠ 零奖励。
- C3 的上限是**任务相关**的：Lift 用 0.15 m。将来 PickPlace / Transport 必须各自标定，
  不得沿用；标定方法 = 先跑 scripted base 20 局取 `max_rise` 分布，上限取 ~2 倍。

### 2.5 v1.2 新增：`insufficient_lift` 从 `flick` 里分出来

v1/v1.1 把 `raw_success ∧ ¬C5` 一律标 `flick`。A 线指出这 14 局 `max_rise` 全 ≤0.042
（远低于 `rise_cap` 0.15）、`held_at_end` 20/20，**不是弹射**，只有翻 `failed_checks` 才能区分。
A 的判断成立，v1.2 采纳。判定顺序（四类互斥）：

| 条件 | verdict | 根因指向 |
|---|---|---|
| 局末已不夹持（`held_at_end=False`），或无 `held_at_end` 证据且 `final_rise<min` | `flick` | 真脱手/弹射：对齐前闭爪、夹到边角 |
| 抓住且未超 `rise_cap`，但 `held_at_end=True ∧ final_rise<min` | **`insufficient_lift`** | 抬起幅度不足：dz 增益/条件均值；与 `over_lift` 是同一变量的相反方向 |
| `max_rise > rise_cap` 且仍夹持 | `over_lift` | 抬起停不下来：hold/done 段 dz 正泄漏 |
| C1–C5 全过 | `controlled_success` | — |

兼容性：`controlled_success` 计数**不变**（只重新标注非成功局，未放宽任何判据）；
`flick` 计数会变小；`flick_frac_of_raw_success` 是历史遗留键名，算的一直是
「raw 成功里不受控的比例」（含 `over_lift`，v1.2 起含 `insufficient_lift`），
CLI 表头写 `unctrl%`；要纯弹射比例用新增的 `flick_frac_strict`。
实测：`train24_lr1e-5_actionminmax_s20k` 臂 raw 11 → **11 insufficient_lift / 0 flick**；
B 的 `clip3` 臂 flick 2→1、新增 1 insufficient_lift，`unctrl%` 仍 93%。

### 2.6 v1.2 收紧：缺输入契约字段 = `INVALID`（不是「通过」）

v1.1 只在「有 `norm_input_blown_frames_frac` **且**超阈」时判 INVALID，
于是缺字段的产物拿到 `measurement_valid=true` —— 等于把「没测过输入契约」记成「输入契约通过」。
这正是 L1 数值炸穿能伪装成「能力不足」好几天的制度原因。
按监管 增补二 §3，v1.2 起 `input_contract.status` 有四态：

| status | 含义 | measurement_valid |
|---|---|---|
| `verified_ok` | 全部局有字段且均值 ≤ 0.05 | true |
| `violated` | 有字段但均值 > 0.05 | false → INVALID |
| `unverified` | 0 局有字段 | false → INVALID |
| `partial` | 只有部分局有字段（覆盖不全，无法主张整轮干净） | false → INVALID |

### 2.7 v1.2 勘误：C5=0.04 的标定依据错了，数值保留但换锚

原依据「与 robosuite Lift 的成功高度阈值同量级」**不成立**。实测（860 行官方臂数据）：
`success_raw=True` 的 `max_rise` 最小 **0.0087**、`success_raw=False` 的最大 **0.0082**，
两侧被一条极窄的带完全分开 —— robosuite `_check_success`（从桌面 body 原点起算的绝对 0.04）
换算成本项目的**相对初始高度**口径后等效阈只有 **≈0.0085 m**。
**C5 比环境自带判据严约 4.7 倍**，这也是 `success_raw` 11/20 与受控成功 0~2/20 落差的真正来源。

保留 0.04 的正确锚：方块 z 半尺寸 0.0217050 → 全高 0.04341，`0.04 = 0.92 × 物体全高`，
即「抬起约自身高度」，与环境实现无关。**改这个值会放大所有历史臂的成功率，属监管裁决范围，
B 不自行改。** 建议后续改成随 `object_geom` 缩放（`0.92 × 2 × size_z`）。

**强制配套**：C5 是硬阈值且实测受控局的 rise 密集分布在 0.035–0.045（正好横跨 0.04），
所以任何「受控成功 N/M」都**必须**附 ±0.005 敏感带。实测 12 个官方臂
**0 个 threshold_robust、5 个 threshold_sensitive**，监管 改判 1 引用的臂敏感带为 **1→6**，
且全部边界局卡在 C5、无一卡 `rise_cap`。工具：`scripts/b_gate_threshold_sensitivity.py`，
报告：`docs/b_gate_threshold_sensitivity_20260928.md`。

### 2.8 v1.2.1 修正：输入侧约束也必须计入 `composite_policy`

`composite_policy` 的用途是阻止一类**具体**的过度主张：某个臂的受控成功率是在
执行/推理侧加了约束才拿到的，因此它描述的对象是 `policy + 约束`，不是底模。

v1.2 及之前的实现只读 `execution_constraints`，于是漏掉了「推理期对归一化输入截断」
这一介入。实测后果就在本仓自己的产物里：

| 产物 | 实际开着的约束 | v1.2 的标注 | v1.2.1 的标注 |
|---|---|---|---|
| `runs/infra/b_normclip/clip3.json` | `--clip-norm-input 3` | `composite_policy=false`，`active_constraints=[]` | `true`，`[clip_norm_input]`（side=`input`） |
| `runs/infra/b_normclip2/clip1.5.json` | `--clip-norm-input 1.5` | 同上（false） | `true`，`[clip_norm_input]` |
| `runs/infra/b_normclip2/clip3_dzdb0.1.json` | 截断 + dz 死区 | `true`，`[dz_deadband]`（**只认出一半**） | `true`，`[clip_norm_input, dz_deadband]` |
| `runs/infra/b_normclip/noclip.json` | 无 | `false`，`[]` | `false`，`[]`（负对照，不得凭空标注） |

危害是**不对称标注**：`scripts/eval_lerobot_act_runtime.py:516` 把同一介入写进
`execution_constraints.norm_input_clip`（会被正确标成复合），
`scripts/b_eval_act_lift_v1.py:224` 写进 `input_constraints.clip_norm_input`（不会）。
于是跨线比较变成在比两类不同对象，而「clip1.5 受控口径最优 4/20」这类数字
会在没有任何警示的情况下被当成底模能力引用 —— 门禁那句
「裁定对象是 policy+约束，不是底模」的 warn 对这些臂一次都没打印过。

实现要点：`input_constraints` 里混着 `train_time_norm_absmax` / `note` 等**元数据**，
所以只按白名单 `INPUT_CONSTRAINT_KEYS = ("clip_norm_input", "norm_input_clip")` 取键，
不做「全量取非 None」。变异验证：把白名单放宽到全部键，负对照 `noclip.json`
会被标成 `composite_policy=true`（约束清单变成 `[note, train_time_norm_absmax]`）——
白名单是必要的，不是随手写的。

裁定影响：`gate_pass` / 四类失效计数**一律不变**（本项只改标注，不改判据）；
变的是 `composite_policy`、`active_constraints`，以及新增的
`input_constraints` / `constraint_sides` 两个字段。

### 2.9 v1.3 新增（D 裁定 1）：phase 词表矛盾 = `INVALID`，不再静默判 `flick`

v1.2.1 的兜底是 `end_phase = phase_at_end or phase_trace[-1]`。当产物**只写** `phase_at_end`
而它的值属状态机词表（`lift` / `done`）时，`classify_phase_field` 拿不到 `phase_trace`
→ 退回 per-frame 规则 → `HOLD_PHASES_STRICT = {"hold"}` 不认 `done` → C4 判失败 → 整局记 `flick`。

实测假阴性（`daily_report.md` §4「交接单 2」）：residual 臂
`runs/20260924_142702_sac_lift_residual_grasp_lift/audit_truth20_gatefields_pre_phase_trace.json`
只写 `phases`（6 元素状态机日志）不写 `phase_trace`，**20 局全被判 `flick`**，
而实质判据全过：`held_at_end=True` 20/20、`final_rise` 0.0563–0.1007（全 ≥0.04）、
`max_rise` ≤0.111（<0.15）、`success_raw` 20/20。补 `phase_trace` 后同臂 **20/20 受控成功**。
这是 v1.1 修掉假阳性之后的**第一个假阴性**，且它把一个 20/20 的臂报成「20 局全脱手」。

v1.3 起，词表**互相矛盾**即判本局 `unjudged`（移出分母，v4 不变量：unknown 既非成功也非失败），
并在文件级判 `measurement_invalid`：

| `phase_vocab_status` | 触发条件 | 处理 |
|---|---|---|
| `mismatch_no_trace` | `phase_at_end ∈ {lift,done}` 而无 `phase_trace` | 本局 unjudged + 文件 INVALID |
| `mismatch_per_frame` | `phase_at_end ∈ {lift,done}` 而 `phase_trace` 是逐帧分类（永不产出 lift/done） | 同上 |
| `unknown_vocab` | `phase_at_end` 不属任何已知词表 | 同上 |
| `consistent` / `absent_field` / `unknown_value` | 无矛盾 | 沿用 v1.1 的分级取证据逻辑 |

**为什么不在「佐证较弱」时也报矛盾**（控制爆炸半径）：`PER_FRAME_VOCAB ⊂ CONTROLLER_LOG_VOCAB`，
`phase_at_end='hold'` 且无 trace 并不矛盾，只是佐证弱，此时 v1.1 的 strict 分支已经足够保守。
实测 48 个官方臂：`phase_at_end` 取值只有 `{hold 135, grasp 651, descend 19, approach 55}`、
`phase_trace` 覆盖 48/48、**词表矛盾 0 局** —— 裁定 1 对官方臂零影响，只咬 residual 那类产物。

**被否决的替代方案（记录以备 D 复议）**：也可以把裸 `phase_at_end='done'` 直接当状态机强证据接受
（`done` 意味着 hold 满 `HOLD_STEPS=30` 帧），那样该臂立即变 20/20 受控。D 裁定选 INVALID，
理由是门禁无法核验这个词表值的来源；代价是把一个可能有能力的臂判为「测不了」而不是「做到了」。

### 2.10 v1.3 新增（D 裁定 2）：无归一化策略的 `not_applicable` 声明路径（带牙）

缺口：SAC 直接吃 raw 60 维 obs（`scripts/train_residual_lift.py` 未用 VecNormalize），
不存在「归一化输入」，`norm_input_blown_frames_frac` 没有对应量，训练期 obs 范围也没落盘
→ 按 §2.6 判 `unverified`→INVALID，即使该臂 raw 20/20、受控 20/20。
A 线明确**不自行绕过**（不删 `ckpt` 字段、不伪造 0.0），把两个选项交回 B/D（ADR-A-005 #2）；
D 裁定走 (ii)：显式 `not_applicable` 声明路径 + **原始 obs 区间检查**。

产物需写：

```json
"input_contract": {"not_applicable": {
  "reason": "为什么不存在归一化输入（必填，空白即拒）",
  "obs_space": "raw_state",
  "train_time_obs_absmax": 5.0,
  "closed_loop_obs_absmax": 4.8
}}
```

闭环区间也可逐局写 `rows[].raw_obs_absmax`（有逐局值时以逐局为准，块级字段可省）。
门禁按 `train_time_obs_absmax × (1 + RAW_OOB_TOL=0.05)` 做上界，
越界局占比 > `INPUT_BLOWUP_TOL=0.05` 即判 `violated_out_of_range`。

**牙在哪里**（声明不等于豁免）：

| `not_applicable_declaration.status` | 含义 | `ic_status` |
|---|---|---|
| `verified_in_range` | 声明 + 训练期区间 + 闭环区间齐备且不越界 | `not_applicable_verified`（有效） |
| `declared_no_reason` | 声明了但 reason 空白 | `not_applicable_unverified`（无效） |
| `declared_no_train_range` | 缺可信的 `train_time_obs_absmax` | `not_applicable_unverified`（无效） |
| `declared_no_closed_loop_range` | 有训练期区间但没有闭环区间 → 检查做不了 | `not_applicable_unverified`（无效） |
| `violated_out_of_range` | 闭环 raw obs 超训练期区间 | `not_applicable_unverified`（无效） |
| `contradicted_by_blown_field` | 既有 blown 字段又声明「无归一化」 | 声明被忽略，按 blown 正常裁定（warn） |

scripted base-only 的自动 `not_applicable`（§2.3 例外）保持不变，它靠的是
「完全没有学习策略引用字段」，与本条的显式声明是两条独立路径。

### 2.11 v1.3 新增（D 裁定 3）：`probe_exonerated` —— 争议带保留只能由**可校验的探针**解除

监管 §12 曾裁定：`mean_blown_frames_frac ∈ [0.03, 0.08]` 的臂，其 `measurement_valid`
**暂不可采信**，必须用对账后的实现重测。v1.3 把「重测已完成」变成一个正式分类，
而不是靠人在文档里口头解除：

- `ic_status = probe_exonerated`（属 `measurement_valid=true`），只在四条全过时给出：
  ①`mean_blown` 落在争议带 `[0.03, 0.08]`；②`configs/b_probe_exonerations.json` 有登记；
  ③登记的证据产物真实存在；④证据 sha256 与登记一致。
- 带外（`>0.08`）一律 `out_of_band_refused`，**不改** `ic_status`：§12 原文
  「两条路径都远超 0.05 的臂，INVALID 维持」不能被豁免册翻案。
- 证据缺失或 sha256 不匹配 → `probe_exoneration_invalid`（`measurement_valid=false`），
  不是静默忽略。豁免必须有可校验证据，不能只有一句话。
- **作用域防连带**：`scope=arm` 的条目只对**自带已知 `blown_metric_impl` 指纹**的产物生效
  （否则 `scope_requires_known_impl`，不受理）。没有这条，同臂的旧留档产物
  （`official_act_truth20_<arm>.json`，缺指纹、非单一来源口径）会被一次重测连带洗白。

首条登记：`trimdone0_stdfloor_minmax_k2_lr1e-5_s20k_seed0`（`mean_blown=0.0400`，余量仅 0.010），
证据 = `runs/infra/lerobot_act_env_20260928/reblown/reblown_vs_archived_stdfloor_seed0.json`
（`verdict=PASS`，old impl `null` → new impl `52eae25ee2d7`，仅 `rows[].elapsed_sec` 20 处不同 + 2 新增键）。
引用该臂仍须带 ±0.005 敏感带；本条只解除**测量可采信**保留，
不构成对「std 下限有效」的正面主张（§17.12 的否证结论不依赖本臂）。

### 2.12 v1.3 新增（监管 §12 分派）：`blown_metric_impl` 指纹进裁定 JSON，新产物缺指纹**拒判**

为什么必须拒判而不是 warn：§12 实测同一条轨迹、同一帧数口径（150 帧/局）下，
两条代码路径算出 `0.2120` 与 `0.1180` 两个 `blown_frac`（差 1.8 倍，逐局最大差 6.8 倍）。
没有指纹就无法判断某份产物是哪把尺子量的，边缘臂（余量 0.010 那种）的裁定因此不可采信。

裁定 JSON 新增 `blown_metric` 块，`status` 四态：

| status | 含义 | 后果 |
|---|---|---|
| `known` | 指纹在 `KNOWN_BLOWN_IMPLS`（当前 `52eae25ee2d7` = A 线 ADR-A-001 单一来源实现） | 正常裁定 |
| `unknown_impl` | 有指纹但不在清单 | 正常裁定 + warn，**不得**当作可引用数字，须 D 确认后加进清单 |
| `missing_legacy_grandfathered` | 缺指纹，但 sha256 命中存量豁免册 | 正常裁定 + warn；重测后必须换带指纹的新产物 |
| `missing_new_reject` | 缺指纹且不在豁免册 | **拒判**：`ic_status=missing_new_reject`，`measurement_valid=false` |

存量豁免册 `configs/b_blown_impl_grandfathered.json`（受版控，DR-002 护栏 1 的登记模型）
由 `scripts/b_blown_impl_registry.py` 维护，**cutoff 写死在册子里**：`--scan` 拒绝登记任何
mtime 晚于 cutoff 的产物，所以这个册子在时间上只能往回长，不能用来给新产物开脱；
`--verify` 重算每条 sha256，产物被改写即报 drift（豁免失效）；`--revoke` 不删条目，搬进 `revoked` 段。
首次登记：69 条存量产物，cutoff `2026-09-28T21:27:24+08:00`，`--verify` 69/69 一致、0 漂移。

### 2.13 v1.3 新增（ADR-A-005 #4）：blowup 阈值来源必须写进裁定

A 按 ckpt 现算阈值（写 `input_contract.blowup_threshold`），B 线评测器写
`input_constraints.train_time_norm_absmax`，两者同族数值一致但**规则不同**：
`trimdone0` 族是 `12.469445`，`train24_lr1e-5_actionminmax` 族是 `23.845039`，
另有 `18.037877` / `16.407488`。跨族引用时，同一个 `0.05` 容差**不是同一把尺子**。

v1.3 两个键都读（旧实现只读 `input_constraints`，而 48 个官方臂该键全为空 →
INVALID 的文案一律打印「`|x|>0.0`」，看起来像阈值是 0），并把
`threshold_provenance` / `artifact_gate_tolerance` / `gate_tolerance_matches` 写进裁定。
`threshold_provenance=unstated` 时打印 warn。**引用任何 blown 数字必须连同阈值来源一起引用。**

### 2.14 v1.3 新增（B-3）：`insufficient_lift` 必须报「差多少」

`insufficient_lift` 是当前主失效模式（A 线 21 臂合计 **219 局**），且 `final_rise` 密集分布在
0.035–0.045，正好横跨 C5=0.04。只有计数无法回答「差一点点还是差很多」，也就无法判断
该修策略还是该由 D 重定阈值（ADR-A-005 #3）。裁定 JSON 新增 `insuff_diagnostic`：
`n / final_rise_{min,median,p10,p90,max} / gap_median / gap_p90_worst / gap_min_best /
n_within_0p005 / frac_within_0p005 / histogram`。

判读规则：`frac_within_0p005` 高 → 主要卡在阈值上，属 D 的裁决范围，不能靠训练解决；
低 → 是真的抬不起来，属策略/teacher 问题。

### 2.15 v1.3 新增（DR-002 / DR-003）：裁定 JSON 带 `git_commit`

`gate_build` 只是**门禁脚本自己**的内容哈希，覆盖不了产出被裁定产物的评测器
（A 的 `scripts/eval_lerobot_act_runtime.py`）与 C 的实现文件。git init 之后
（`work/decisions/decisions_20260928_B.md` DR-003），裁定 JSON 同时带
`git_commit` 与 `git_dirty_files`，监管 P0 第一项「实验记录的代码版本」才可填。
缺 `git_commit` 的旧裁定**不因此作废**（只有缺 `blown_metric_impl` 指纹才拒判）。

### 2.16 v1.4 新增（裁定 14 / DR-D09，A 移交）：证据不足 ⇒ 禁止输出失效模式标签

**缺陷**（A 的最小复现：`docs/a_handoff_to_b_gate_vocabulary_20260928.md` §2）：
`held_at_end` 与 `final_rise` 双缺时，C4 落到 `HOLD_PHASES_STRICT={"hold"}` 分支（`:488`）
拒绝 `end_phase="grasp"`，而字段齐时走 `HOLD_PHASES_WITH_EVIDENCE={"hold","grasp"}`（`:480`）接受它
→ `c4=False` → 一路返回**最重的失效模式 `flick`**。同一个 `"grasp"` 标签是否算 C4 证据，
取决于一个**不相关字段在不在**。同一份裁定里其实已写明 `field_class="partial"` 与 `missing_fields`，
只是没用这个信息。

**实测影响面**：5 臂 **16 局假 `flick`**（11 + 3 + 2），补测后全部翻成 `insufficient_lift`，
另 1 局 `provisional_pass` 升级成 `controlled_success`；可引用 `flick` 因此只剩 **2 局 / 920 局**（0.2%）。

**裁定**：失效模式标签（`flick` / `insufficient_lift` / `over_lift`）**只在证据充分时输出**，
否则本局改判 `unjudged`（`unjudged_reason="evidence_missing_label_critical"`）、计入 `n_unjudged`、
`measurement_valid=False`、`gate_reason` 点名缺失字段。裁定 JSON 新增四个字段：
`labels_reportable` / `missing_label_critical` / `n_labels_abstained` / `label_scope_note`
（`labels_reportable` 字段名与 A 的 `scripts/summarize_lerobot_act_arms.py`（`schema_version=2`）对齐）。
原标签**不销毁**，保留在 `per_episode[].evidence.label_before_abstain`，改判后仍能回答「它本来被判成了什么」。

**不动的**：`provisional_pass` 是 v1.1 有意设计的「待补测」档（它正确地没把 `seed2 ep5001`
算成受控成功），裁定 14 只禁**失效模式**标签；`failure` 是通用裁定，不动；
`controlled_success` 由 C1–C5 全过得出，不在本条范围。

#### 2.16.1 「证据充分」的口径：`LABEL_CRITICAL_FIELDS`，不是 `field_class == "strict"`（DR-007 → **裁定 22 已认可本收窄**）

DR-D09 的字面口径是 `field_class != "strict"` 即弃权。**B 落地时收窄了它**，理由是可测的：

> **DR-D19 护栏③ 要求的明文登记**：**DR-D09 的字面表述已被 裁定 22（DR-D19）更正** ——
> 触发条件是 **`LABEL_CRITICAL_FIELDS` 缺失**，不是 `field_class != "strict"`；
> `field_class` 只作展示。D 在 裁定 22 里同时认定自己的原文「拿代理量替代真实依赖」因而**过宽**
> （`field_class` 也被 `terminal_kind` 这类与标签无关的字段影响），并**认可 B 的收窄为
> 裁定 14 的正确实现**。两条护栏随本条生效：① `LABEL_CRITICAL_FIELDS` 升为**受裁定常量**，
> 增删须先由 D 裁定并登记本规格；② 变异用例 **`M7`**（把 `terminal_kind` 加回该集合）
> **必须长期保留并保持红色** —— D 认可本收窄的主要理由就是「偏离被机器记住了，不靠散文」。

| 字段 | 三个失效模式标签是否读取 | 缺失时后果 |
|---|---|---|
| `final_rise` | 是（C5） | 无从判断抬起够不够 → 必须弃权 |
| `held_at_end` | 是（C4 证据分支选择） | `"grasp"` 是否算夹持无法定 → 必须弃权 |
| `phase_at_end` | 是（C4） | 同上 → 必须弃权 |
| `terminal_kind` | **否** | 它走的是 §2.4 终局语义那条**独立**弃权路径，不影响 C4/C5 |

`field_class` 把 `terminal_kind` 也算进关键字段，于是按字面实现会命中一个自伤：
**base-only 标定产物本身就缺 `terminal_kind`**（实测
`runs/infra/b_env_rebuild/base_truth20.json` 与
`runs/act_chunk_replay_20260924_k4_base_truth20.json` 的 `terminal_kind` 覆盖率都是 `0/20`，
`field_class` 都是 `partial`），它们正是 `rise_cap=0.15` 的标定基准与 20/20 受控成功的参考上界。
按字面实现，门禁会把自己 §2.3 注释里专门保护过的标定基准判成 `INVALID`。

所以弃权只由 `LABEL_CRITICAL_FIELDS = ("final_rise", "held_at_end", "phase_at_end")` 触发：
`missing_label_critical = missing ∩ LABEL_CRITICAL_FIELDS`，非空才弃权 + `measurement_valid=False`。

这不是「放宽裁定」，而是把裁定对准它要修的那个通道。两条方向都有回归护栏：

- **用例 22**（partial，缺 4 个字段）：`flick=0`、`unjudged=6`、`n_labels_abstained=6`、`INVALID`，
  且 `label_before_abstain="flick"` 可追溯 —— 复现 A 的 16 局假标签并证明已弃权；
- **用例 23**（strict，同一次物理评测补齐字段）：`insufficient_lift=6`、`flick=0`、`n_labels_abstained=0`、
  `measurement_valid=True` —— 证明改动**不误伤** strict；
- **用例 24**（只缺 `terminal_kind`）：`field_class=partial` 但 `labels_reportable=True`、
  `n_labels_abstained=0`、`measurement_valid=True` —— 证明 DR-007 的收窄生效；
- **用例 1**（真实 base-only 产物）追加两条断言：`labels_reportable=True`、`n_labels_abstained=0`。

变异自检加了**两个方向**（§7 末表）：`M6` 清空 `LABEL_CRITICAL_FIELDS`（= 静默移除裁定 14）应红用例 22；
`M7` 把 `terminal_kind` 加进该集合（= 按 DR-D09 字面实现）应红用例 1 与 24。
`M7` 存在的意义是把 DR-007 的收窄理由变成**可执行证据**而不是注释：
将来谁想「按裁定原文改回来」，这条会立刻红给他看。

同时更正 v1.1 的一条设计注释：原文写「`field_blind` 不算 `measurement_invalid`（CLI 显示 FAIL 而不是 INVALID），
所以它单独一支」。该分支已被裁定 14 推翻 —— 关键字段缺失是「没测到」，不是「策略失败」，
判 FAIL 会把测量缺口说成能力结论。现在 `blind` 也走 `invalid_reasons`，屏幕显示与文案一致。

**v1.4 的实测附带损伤（对 48 臂官方集）**：**零**。48/48 全 `strict`，重分类逐项与 v1.3 一致
（`ic_status` 45/2/1、可引用三分类 24/22/2、`arms_with_controlled_success` 25、
`threshold_sensitive` 24、`insuff` 235 局 / 34 臂 / 中位差 0.0164、族均值 `k1=3.667 (n=6)`）；
`b_regate_all.py` 对 16 份留档产物报「裁定变化 0 处」。裁定 14 改变的是**历史 partial 产物**的标签，
不是当前权威表。

### 2.17 v1.5 新增（裁定 10 / 裁定 16.4 / DR-008，A 移交 + D 会签核验）：豁免册按 `probe_kind` 分通道

§2.11 的争议带牙是为 `reblown_single_source`（增补三 §12：blown 口径两条代码路径给出 0.2120 / 0.1180
两个值，重测一次消除**尺子**的不确定）设计的，它的适用前提就是「值在带内、只是尺子不确定」。
而 裁定 10 是**另一条**通道：clip-at-train-absmax 因果探针，要解除的不是「尺子不确定」，
而是「这次测量的输入越界**有没有改变逐局裁定**」。它的目标臂 `mean_blown=0.212`
**必然**在争议带外 —— 把两条通道写成一条，等于让 裁定 16.4 明文要求登记的条目永远无法受理，
增补五 §3 的 `47/1`、`25/22/1` 也永远达不到（A 移交单 §4 的根因分析）。

D 的会签前独立核验（`scripts/d_verify_exoneration_cosign.py`）实测命中**三处代码级阻塞**，
其中第三处 A 的移交单没有提到：

| # | 位置（v1.4 行号） | 现象 | 状态字 |
|---|---|---|---|
| 1 | `:381` 带内判定 | 争议带对**所有** `probe_kind` 生效 | `out_of_band_refused` |
| 2 | `:358` 臂级豁免前置 | `scope="arm"` 要求 `impl_status=="known"`，而目标臂 plain 产物 `blown_metric_impl=null` | `scope_requires_known_impl` |
| 3 | `:806` 晋级闸 | 只认 `verified_ok` / `not_applicable_verified`，目标臂是 `violated` ⇒ **即使豁免受理也不晋级** | `promotion_possible_without_code_change=false` |

v1.5 的修法（逐条对应 DR-008 决定 1–5）：

- **分通道，白名单语义**：`BAND_EXEMPT_PROBE_KINDS = (clip_at_train_absmax,)`。
  **只有**白名单内的 kind 免争议带检查；未知 kind 一律按带内处理（新增通道必须显式进白名单
  并配自己的牙）。`reblown_single_source` 的行为**逐字不变**（回归用例 20 / 37 双向钉住）。
- **只受理 `scope="artifact"`**（键 = 被判 plain 产物的 sha256）：免罪的对象是「某 ckpt × 某 plain 产物」
  这**一次**测量，不是整条臂；artifact scope 天然「重跑即失效」，必须重新探针。
  这条同时**绕开**阻塞 2 而**不放松**它 —— `:358` 的臂级防连带护栏原样保留（用例 26 钉住）。
- **用自己的牙替代争议带牙**，四条准入 + 一条证据侧核验，全部可执行：
  ①`scope=artifact`；②登记的 `clip_C` 必须等于**被判产物自己**声明的训练期 absmax
  （`input_constraints.train_time_norm_absmax` 或 `input_contract.blowup_threshold`，容差 `1e-6`）——
  不能拿册子里抄来的数替产物主张，否则写个 12.469445 就能给任意臂免罪；
  ③条目必须带 `ruling10_conditions` 五条准入且五键全 `true`（漏项与写 `false` 同样拒绝）；
  ④条目必须带 `cosign`（`by` 非空 + `fact_basis is True`，注意是 `is True` 不是 truthiness）——
  裁定 16.4 原文「由 B 写、**D 会签**」，B 不能自签；
  ⑤探针产物**自己**记录的截断值（`execution_constraints.norm_input_clip`）必须等于登记的 `clip_C`。
  条件 ② 的判别力证据：同臂 `C=5.0` 探针**不满足**准入 ②（seed 5007 的 verdict 翻转、
  `insufficient_lift` 1→0）⇒「截得越紧越安全」被证伪，C 必须钉死在 train-absmax。
- **晋级闸按 kind 分路**：`EXONERATION_PROMOTION_SOURCES = {reblown_single_source:
  (verified_ok, not_applicable_verified), clip_at_train_absmax: (violated,)}`。
  **精确**放开而不是宽口径：带内重测通道**不能**把 `violated` 晋级（用例 39 钉住）——
  否则「换把尺子重测一次」就能推翻一个**真的**超阈，裁定 12 被架空。
- **假证据并入既有的 invalid 家族**：`EXONERATION_EVIDENCE_FAILURES` 增加
  `probe_clip_unstated` / `probe_clip_mismatch`，命中即 `probe_exoneration_invalid`
  （`measurement_valid=false`）。登记了不支持自己的证据，比没登记更糟。
- **会签 build 不匹配不拒判但必须回显**（DR-008 决定 7）：裁定 JSON 带
  `cosign_build_current` / `cosign_build_matches`。否则会死锁 —— 条目只能在代码改完之后写，
  写的那一刻 D 的会签必然锚在旧 build 上；D 须重跑 verifier 复签。

**首条登记**：`trimdone0_minmax_k2_lr1e-5_s20k_seed0`（`mean_blown=0.212`、受控 **9/20**），
键 = plain 产物 sha256 `85c46dfb…c3429`，`clip_C=12.469445`，
证据 = `runs/infra/lerobot_act_env_20260928/clipprobe/official_act_truth20_…_clipC12p469445.json`
（sha256 `142bd2cc…db2fb`），支撑产物含 C=5.0 的判别力反证与探针逐局裁定。
**引用纪律**：引用的数字取自 **plain** 产物；探针产物 `composite_policy=true`
（`active_constraints=["norm_input_clip"]`）**不得**当官方臂数字引用。固定写法：
「9/20 @ `final_rise`=0.040，`VALID_probe_exonerated`（C=12.469445=train-absmax，探针逐局裁定不变）」。
同族 `…_seed0_replan1`（blown 0.1692、**无探针**）**不在**覆盖范围内，维持 INVALID。

**v1.5 的实测影响面（48 臂官方集）**：`ic_status` 由 `verified_ok 45 / violated 2 / probe_exonerated 1`
变为 `verified_ok 45 / probe_exonerated 2 / violated 1`；可引用三分类 **24/22/2 → 25/22/1**；
`measurement_valid` **46/2 → 47/1**；`NOT_CITABLE_measurement_invalid` 只剩 `…_seed0_replan1` 一臂。
**计数层一格未动**（`controlled_success 135` / `insufficient_lift 235` / `flick 7` / `over_lift 0` /
`provisional_pass 0` / `raw_success 377` / 分母 960）—— 与 A 的 v1.2.1 表逐格相同，
即 A 移交单 §6.1 的「计数层可互换、分类层不可互换」在 v1.5 后**分类层也可互换**了。
`b_regate_all.py` 对 16 份留档产物报「裁定变化 **0** 处」（仅指纹更新）。

**一并修掉的一处汇总漏计**（`scripts/b_official_arms_reclassification.py`）：`summary.probe_exoneration`
与 CLI 的豁免统计原先按 `in_disputed_band` 过滤 —— 在只有带内一条通道时是对的，v1.5 起
带外免罪的臂会被漏掉（实测报 `{"exonerated": 1}` 而真实是 2 臂），属权威表里的假陈述。
现按**全通道**统计，并新增 `probe_exoneration_by_kind` 与 `exonerated_in_disputed_band` 两个可分开的口径，
行级新增 `probe_exoneration_kind` / `probe_exoneration_band_checked` 两列。

**DR-008 提请 1 已结案（裁定 24 / DR-D21）**：`probe_exonerated` 的标签语义 —— **不降级 stdfloor**。
D 现场实测两份产物后认定 B 的前提「stdfloor 本来就 `verified_ok`」只对**主目录旧产物**成立；
权威表判的是 `reblown/` **`supersedes` 链末端**产物（带指纹 `52eae25ee2d7`、blown **0.04 ∈ 争议带**），
裁定 13 的解除**确实在做事**，降级它等于撤销 裁定 13（与 A 迁移闸 B5 的 `required="verified_ok"` 同一个错误，
DR-D15 已驳回）。真正的修法是 裁定 19（DR-D16）：臂级回显 `probe_kind`、`summary` 按 kind 分桶 ——
**v1.5 已落地**（`probe_exoneration_kind` / `probe_exoneration_band_checked` / `probe_exoneration_by_kind`），
D 在 裁定 27 §12.2 确认「裁定 24 ⑤ 的『1 对 2』前瞻问题已被 B 的 kind 分桶解决」。

### 2.18 v1.6 预登记（裁定 23 / DR-D20，P1）：`terminal_kind` 覆盖不足 ⇒ 终局语义自检必须报「不可判定」

**这一节是预登记，不是已实现的判据。** 按 DR-001（改门禁前先登记）与 v1.5 冻结声明，
裁定 23 的六项**不在** `f19f61341cbe` 里；它们构成 **v1.6** 批次，落地即升 `GATE_BUILD`，
D 须重跑 `scripts/d_verify_exoneration_cosign.py` 复签（第三轮），A 的 48 臂表须在新 build 上重出 meta。

缺陷（D 现场实测，非引用 B）：`runs/infra/b_env_rebuild/base_truth20.json` 的 `terminal_kind` 覆盖 **0/20**，
其裁定 JSON 却是 `terminal_semantics = {horizon:300, rows_at_full_horizon:20,
rows_labeled_terminated_failure:0, suspect_truncation_labeled_as_failure: **false**, note: **""**}`。
根因 `:888-893`：`n_termfail` 由 `terminal_kind` 前缀匹配算出，字段全缺 ⇒ `n_termfail=0` ⇒ 该标志**恒 `false`**、
`note` **恒空**。即「截断被伪装成失败」这条自检**在根本无法执行的产物上报告为『没有问题』**；
而 `rows_at_full_horizon=20` 由 `steps>=horizon` 算出、与 `terminal_kind` 无关，看上去还挺健康。
与本仓已发生两次的事故同型（DR-003 验收判据 3 恒真；D 第五次自我纠错「裁定成立但无代码承载」）。

v1.6 必须落地的六项（裁定 23 原文，逐条可验）：

| # | 要求 | 验收判据（预登记，v1.6 落地时逐条填实测值） |
|---|---|---|
| 1 | **不降级** `measurement_valid`（采纳 B 的倾向） | 48 臂 `measurement_valid` 仍 **47/1**；计数层 135/235/7/0/0 一格不动 |
| 2 | `suspect_truncation_labeled_as_failure` 改**三值**：覆盖不足 ⇒ **`null`**；`false` 只表示「跑过了且没发现」 | `base_truth20.json` 该字段 == `null`；`official_act_truth20_*`（覆盖 20/20）仍为 `false` |
| 3 | `note` 覆盖不足时**必须非空** + 回显 `terminal_kind_coverage`（n/N） | `base_truth20.json` 的 `note` 含「覆盖 0/20 ⇒ 终局语义自检不可用」；新字段 `terminal_kind_coverage == [0,20]` |
| 4 | **可聚合**：`summary` 层新增臂清单（与 `phase_vocab_mismatch_arms` 同型） | 权威表 `summary.terminal_semantics_unavailable.n` 与逐臂覆盖率一致 |
| 5 | **标定基准须显式声明**：被当 `RISE_CAP` 基准 / 20-20 参考上界 / DR-004 锚点的产物，须在受版控登记册里声明「`terminal_kind` 缺失已被接受 + 理由」 | 登记册里能查到 `base_truth20.json` 的接受声明；否则引用该基准的结论必须带标注 |
| 6 | 变异自检加反例：覆盖率改 0 而断言仍 `false` ⇒ **必须变红** | `scripts/b_selfcheck_gate_mutation.py` 新增 **M16**，`baseline_all_green=true` 且 M16 被抓 |

**第 4 项已在报表侧先行落地**（不改门禁、不升 build）：`scripts/b_official_arms_reclassification.py`
新增行级 `terminal_kind_coverage` 与汇总 `summary.terminal_semantics_unavailable`，
并新增顶层 `known_vacuous_fields_pending_v16` 显式声明「v1.6 之前该字段在覆盖不足的产物上是空转的 `false`，
**不得**读成清洁保证」。先行只做**聚合**（覆盖率取门禁已回报的 `field_presence`），
**不重算任何判定** —— 避免出现「同一判据两个实现」（裁定 21 / DR-D17 的教训）。
判定侧的三值化只能在门禁里做，属 v1.6。

**排序提请（B → D，见 DR-010）**：D 的 裁定 25「执行承诺」写的是「B 的 v1.5 落地（**含 裁定 23 的六项**）后，
D 跑 verifier」，而实际落地的 v1.5 不含 裁定 23；D 的 裁定 26 复签与 裁定 27 §12.4 收尾清单也**未核这一项**
（只列了 build 冻结声明 / 权威表重出 / cosign 换块 / 护栏① 四项）。B 不擅自决定顺序，提请 D 二选一：
**(a)** v1.5 冻结生效、A 先按 裁定 27 迁表，裁定 23 作为 v1.6 紧随其后（B 推荐：裁定 23 不改任何计数，
迁表结果不受影响，且避免让 A 的迁移在半途换 build）；
**(b)** 立即升 v1.6 再迁表（一次 build、一次复签、一次迁表，但 A 正在按 裁定 27 修 L5/G2/S10，
此时换 build 会让 A 的 `a_gate_build_drift_check.py` 默认指纹再次过期）。
**在 D 裁定之前，引用纪律**：任何引用 `suspect_truncation_labeled_as_failure=false` 的结论，
必须同时注明「该产物 `terminal_kind` 覆盖 n/N；覆盖不足时此值为空转，见 §2.18 / 裁定 23」。

## 3. 三套账（分母互不相同，禁止混用）

| 账 | 分母 | 分子 | 用途 |
|---|---|---|---|
| `policy_independent` | `guard_interventions == 0 且 recovery_events == 0` 的可判定局 | 其中 `controlled_success` 数 | **唯一**可用于「policy 自身能力」主张与 P1 晋级 |
| `system_assisted` | 全部可判定局 | 其中 `controlled_success` 数 | 系统整体可用性；**救场成功不得归因给 policy** |
| `autonomous_learning` | 关闭动作辅助后重跑的局（输入文件需带 `--assist-off` 声明） | 同上 | 持续学习窗口内的自主能力 |

报告格式（三行都必须出现，没有就写 `n/a` 并说明原因，不得省略）：

```
policy_independent   : controlled_success / denominator   (flick = k)
system_assisted      : controlled_success / denominator   (flick = k, interventions = m)
autonomous_learning  : controlled_success / denominator   或 n/a（未跑关闭辅助的评测）
n_unjudged           : u  (seeds: ...)
```

### 3.1 v1.3 新增：可引用单位 = **配置族 × 重规划口径**，跨口径不可比

本节是 B③（44→48 官方臂全量重分类）的直接产物，写进规格以免每次靠人记忆。

**规则 1：引用单位是族，不是单臂。** 同一配置族跨 seed 的受控成功数摆幅实测可达 **20 局**
（`trimdone0_minmax_k1_lr1e-5_s20k`：seed0=20、seed1=0；补测后 6 个 seed 为 20/0/0/2/0/0）。
因此任何「某臂 N/20」的单独引用都等价于**挑 seed**，只能以
「族均值 + seed 摆幅 + n」的形式出现。

**规则 2：族均值的分母只排除 `measurement_valid=false` 的臂，绝不排除「测量有效但受控为 0」的臂。**
排除后者会系统性高估。实测踩过的坑：`k1` 族按错误分母算出 20.0/20，按正确分母是 10.0/20（n=2），
补测到 6 个 seed 后是 **3.67/20**。

**规则 3：跨重规划口径（`replan_every` / `chunk_size` / `n_action_steps`）禁止直接比较，
因为算力不是常量。** 实测 48 个官方臂里并存 **8 种口径**：
`(4,4,4)`、`(2,2,2)`、`(1,1,1)`、`(4,4,1)`、`(4,4,2)`、`(2,2,1)`、`(8,8,8)`、以及口径不可解析的 `4/4/None`。
`(1,1,1)` 每局推理次数是 `(4,4,4)` 的 **4 倍**，把两者的成功率放在同一张表里排序，
比的是「谁的推理预算多」，不是「谁的策略好」。汇总必须按 `family × cadence_key` 分组，
且口径不可解析的臂（缺字段）**不进均值分母**，单独列为 `cadence_unresolved`。

**规则 4：`composite_policy=true` 的臂，其受控成功率描述的对象是 `policy + 约束`，不是底模。**
不得与 `composite_policy=false` 的臂混在同一张能力表里（§2.8）。

## 4. 给 A 的交接单：补 5 个字段（B 不改 A 的文件）

在 `scripts/eval_act_lift_truth.py` 与 `scripts/eval_lerobot_act_runtime.py` 的 per-row dict 里补：

| 字段 | 类型 | 计算方式 | 参考实现 |
|---|---|---|---|
| `final_rise` | float | episode 结束那一帧的 `cube_pos[2] - z0` | `scripts/audit_lift_base_truth.py` |
| `held_at_end` | bool | 结束帧再调一次 `grasp_truth_fn(env,'lift')` | 同上（`held` 是 ever-held，语义不同，**不要复用同一个变量名**） |
| `phase_at_end` | str | 结束帧的 `phase(raw, z0, step)` | 同上 |
| `rise_at_success` | float | `info['success']` 首次为真那一帧的 rise | 同上 |
| `terminal_kind` | str | `terminated_success` / `terminated_failure` / `truncated_horizon` / `unknown` / `preempted` | v4 附录 02 §5 |

约束：

1. 五个字段只**追加**，不改现有字段语义；`grasp_verified` 继续表示 ever-held。
2. `success_raw` / `success_grasp_verified` 的计算**不要改**——门禁是后处理，改了就无法与 09-24 的产物对比。
3. 补完后跑一次 `python3 scripts/b_gate_controlled_success.py <新产物> --json-out <...>`，
   把 `field_blindness` 从 `MISSING_final_rise` 变成 `null` 即为完成。
4. 在此之前 B 的门禁继续用 `phase_trace[-1]` 兜底，结论标注「偏松」。

`scripts/eval_lerobot_act_runtime.py` 已有的 `clip_events` / `max_preclip_abs_action` /
`guard_interventions` / `recovery_events` 正好被 §3 的分母规则直接消费，无需改动。

## 5. 用法

```bash
# 单文件裁定（退出码 0=PASS, 1=FAIL，可直接接 CI / 发布门禁）
python3 scripts/b_gate_controlled_success.py runs/infra/b_env_rebuild/base_truth20.json

# 多臂对比 + 机器可读产物
python3 scripts/b_gate_controlled_success.py \
    runs/infra/b_env_rebuild/base_truth20.json \
    runs/infra/b_act_lift_mb_hist1_seed0/audit_truth20.json \
    --json-out runs/infra/b_bc_retrain/gate_v1.json

# 关闭辅助后重跑的评测，填 autonomous_learning 账
python3 scripts/b_gate_controlled_success.py <assist_off_result.json> --assist-off
```

阈值可调但必须在报告里写明：`--rise-cap` / `--final-rise` / `--no-strict-final-rise`。
`--hold-phases` 自 v1.1 起**废弃**（保留参数位以免旧命令报错，但不再生效）：
C4 的证据规则见 §2.1，不再是一个可自由填写的集合。

退出码：`0` = 全部 PASS；`1` = 存在 FAIL 或 INVALID。CI 里两者都必须拦。

## 6. 版本与变更登记

| 版本 | 日期 | 变更 | 被推翻的假设 |
|---|---|---|---|
| v1 | 2026-09-28 | 首次定义 C1–C5、三套账、`terminal_kind` 隔离；`rise_cap=0.15`、`final_rise_min=0.04` 由 scripted base 实测标定 | 「`success_raw` / `mean_max_rise` 可作为主指标」——B minibatch 臂 raw 10/20 但 flick 10/10，证明这两个量会把弹射当成能力 |
| v1.0.1 | 2026-09-28 | 修正 C5 缺字段时的假阳性否决（residual 臂 20/20 曾被误判 FAIL）；输出增加 `not_evaluated` / `lenient_c5` / `controlled_success_lenient_c5` | 「缺字段就按不通过处理更保守」——实际是更危险，会否掉真实结果 |
| **v1.1** | 2026-09-28 | ①C4 按 `phase` 字段语义分流取证据（§2.1），`grasp` 不再单独算夹持；新增 `provisional_pass` 裁定 ②拆出 `over_lift`（§2.2）③新增策略输入契约与 `INVALID`（§2.3）④新增 `terminal_kind` 语义自检（§2.4）⑤`--hold-phases` 废弃 | 三条被推翻：①「`phase_at_end ∈ {hold,done,grasp}` 就等于局末夹持」——`grasp` 的判据是两指张开>1.2cm，空爪与夹着方块同标签；②「`phase_trace` 是一个定义明确的字段」——同名两套语义（6 元素状态机日志 vs ≤300 元素逐帧分类），v1 的兜底把它们混用了；③「过不了 rise_cap 的都叫 flick」——其中一大类是方块全程在爪里的 `over_lift`，指向完全不同的修复动作 |
| v1.1.1 | 2026-09-28 | 每份裁定 JSON 增加 `gate_build` / `gate_spec_sha256`（门禁脚本与规格文档的内容哈希），CLI 页脚同步打印；版本号收敛到单一常量 `GATE_VERSION` | 「留档的裁定自带口径」——仓库不是 git repo，实测 `runs/infra/b_normclip/gate_v11.json` 里的 clip24 条目出自加入输入契约检查**之前**的构建，用当前脚本重判会从 FAIL 翻成 INVALID，而 JSON 里没有任何字段能暴露这件事 |
| **v1.2.1** | 2026-09-28 | ①输入侧约束计入 `composite_policy`（§2.8），新增 `input_constraints` / `constraint_sides` 字段与 `INPUT_CONSTRAINT_KEYS` 白名单 ②规格 §7 反例自检变为可执行：`scripts/b_selfcheck_gate_regression.py`（8 用例 / 30 断言）③新增一键重判入口 `scripts/b_regate_all.py`（快照 + 逐臂新旧 diff + 空比对护栏 + 自动跑 §7 回归） | 一条被推翻：「`composite_policy` 只看 `execution_constraints` 就够了」——本仓 9 个 clip 臂因此全被标成非复合，而 A 的评测器写另一个键就会被标上，同一介入两套标注；且「留档产物自带口径」再次被推翻：三份产物曾同时停在三个不同 `gate_build` 上，根因是没有统一重生成入口 |
| **v1.2** | 2026-09-28 | ①新增 `insufficient_lift` 裁定，从 `flick` 里分出「局末仍夹持但抬得不够高」（§2.5）②`input_contract.status` 四态，**缺字段/覆盖不全同样判 INVALID**（§2.6）③新增 `flick_frac_strict`；`unctrl%` 分子纳入 `insufficient_lift` ④C5=0.04 的标定依据勘误并换锚为「0.92×物体全高」，数值不变（§2.7）⑤新增阈值 ±0.005 敏感性工具与「报率必须附敏感带」的强制要求 | 两条被推翻：①「`raw_success ∧ ¬C5` 就是 flick」——A 的 14 局 `max_rise` 全 ≤0.042、`held_at_end` 20/20，没有一局是弹射，全是抬起不足，两者指向**相反**的修复方向；②「C5=0.04 与 robosuite 成功阈值同量级」——实测 robosuite 等效相对阈仅 ≈0.0085，C5 严约 4.7 倍，这才是 `success_raw` 11/20 与受控 0~2/20 落差的真正来源 |

| **v1.3** | 2026-09-28 | 执行 D 的三条裁定与监管 §12 分派：①phase 词表矛盾 → 本局 `unjudged` + 文件 `INVALID`（§2.9）②无归一化策略的 `not_applicable` 声明路径 + 原始 obs 区间检查，声明不等于豁免（§2.10）③`probe_exonerated` 分类：争议带保留只能由 sha256 可校验的探针证据解除，带外一律不受理，`scope=arm` 只对带已知指纹的产物生效（§2.11）④`blown_metric_impl` 指纹写进裁定 JSON，新产物缺指纹**拒判**，存量走带 cutoff 的受版控豁免册（§2.12）⑤blowup 阈值来源 `threshold_provenance` 进裁定（§2.13，ADR-A-005 #4）⑥`insuff_diagnostic` 报「差多少」（§2.14，B-3）⑦裁定 JSON 带 `git_commit`（§2.15，DR-002/DR-003）⑧§3.1 把「可引用单位=族×口径」写进规格 ⑨§7 回归扩到 21 用例/85 断言，并新增变异自检 `scripts/b_selfcheck_gate_mutation.py`（5 变异体全被抓） | 三条被推翻：①「`phase_at_end or phase_trace[-1]` 的兜底是安全的」——它对状态机词表的 `done` 静默降级成 per-frame strict，把一个 20/20 的臂报成 20 局全脱手（v1.1 修假阳性之后的第一个假阴性）；②「缺 blown 字段一律 INVALID 就够严了」——它对**不做归一化**的策略是错判（raw 20/20 也 INVALID），严得没有区分力，等于逼人绕过门禁；③「`not_applicable` 可以靠门禁自己推断」——推断出来的豁免没有牙，必须显式声明 + 区间证据，否则「无归一化」会变成新的万能豁免口 |

| **v1.4** | 2026-09-28 | 执行裁定 14（DR-D09，A 移交 `docs/a_handoff_to_b_gate_vocabulary_20260928.md`）：①证据不足 ⇒ 三个失效模式标签改判 `unjudged`，原标签保留在 `evidence.label_before_abstain`（§2.16）②裁定 JSON 新增 `labels_reportable` / `missing_label_critical` / `n_labels_abstained` / `label_scope_note`，字段名与 A 的 `summarize_lerobot_act_arms.py`（`schema_version=2`）对齐 ③`measurement_valid` 增加 `labels_reportable` 一项；`blind` 从「单独一支 FAIL」并入 `invalid_reasons`（推翻 v1.1 的设计注释）④**DR-007 收窄**：弃权只由 `LABEL_CRITICAL_FIELDS=(final_rise, held_at_end, phase_at_end)` 触发，不含 `terminal_kind`（§2.16.1，已升级 D 复核）⑤§7 回归扩到 **24 用例 / 108 断言**，变异自检扩到 **7 变异体**（M6 正向、M7 反向） | 两条被推翻：①「`field_class` / `missing_fields` 只是元信息，不影响裁定」——v1.3 明明算出了 `field_class="partial"` 与 `phase_vocab_status="absent_field"`，却仍一路返回最重的 `flick`，把「证据不足」解析成「判成脱手弹射」；②「DR-D09 可以按字面实现」——字面口径（`field_class != strict` 即弃权）会把只缺 `terminal_kind` 的 base-only 标定件判 INVALID，即门禁作废自己的 `rise_cap=0.15` 锚点（本规格 §2.3 早有注释警告这种自伤），故 B 收窄并用 M7 把理由钉成可执行证据 |

| **v1.5** | 2026-09-29 | 执行裁定 10 / 裁定 16.4（A 移交 `docs/a_handoff_to_b_probe_exoneration_gap_20260928.md` + D 会签前核验 `scripts/d_verify_exoneration_cosign.py`，DR-008）：①豁免册按 `probe_kind` **分通道**，`BAND_EXEMPT_PROBE_KINDS` 白名单语义，未知 kind 一律按带内处理（§2.17）②新增 `clip_at_train_absmax` 通道，只受理 `scope=artifact`，四条准入 + 一条证据侧核验（`clip_C` 必须等于被判产物**自报**的训练期 absmax；`ruling10_conditions` 五键全 true；`cosign.fact_basis is True`；探针产物自报截断值必须等于 `clip_C`）③晋级闸按 kind 分路 `EXONERATION_PROMOTION_SOURCES`，只有 裁定 10 通道能把 `violated` 升为 `probe_exonerated` ④`EXONERATION_EVIDENCE_FAILURES` 并入 `probe_clip_unstated` / `probe_clip_mismatch` ⑤会签 build 不匹配不拒判但回显 `cosign_build_matches` ⑥登记首条 裁定 10 条目（`trimdone0_minmax_k2_lr1e-5_s20k_seed0`）⑦修 `b_official_arms_reclassification.py` 的豁免汇总**漏计**（原按 `in_disputed_band` 过滤）⑧§7 回归扩到 **39 用例 / 157 断言**，变异自检扩到 **15 变异体**（M8–M15） | 两条被推翻：①「豁免册的『带外一律不受理』是一条全局规则」——它其实只是 `reblown_single_source` 通道的规则，写成全局就等于让 裁定 16.4 明文要求登记的条目永远无法受理（A 移交单 §4）；②「补上登记册条目就够了」——D 实测 `registry_alone_is_sufficient=false`，晋级闸只认 `verified_ok` / `not_applicable_verified`，`violated` 臂即使豁免受理也升不上去，这处 A 的移交单没提到 |

待办（不属 v1.5）：`flick_frac` / `over_lift_frac` 进 `registry/publish.py` 的发布门禁；
PickPlace / Transport 各自标定 `rise_cap`；`provisional_pass` 的补测流程自动化。

## 7. 反例自检（门禁自己必须先过这一关）

v1.0.1 的教训是「门禁产生假阴性比没有门禁更危险」，v1.1 的教训是反过来的
「门禁产生假阳性同样危险」。所以每次改判据都要跑这三条已知答案的回归：

| # | 输入 | 期望 | 实测（v1.5；构建指纹以产物内 `gate_build` 为准，本表产出时为 `f19f61341cbe`） |
|---|---|---|---|
| 1 | `runs/infra/b_env_rebuild/base_truth20.json`（scripted base，无学习策略） | 20/20 `controlled_success`，PASS；输入契约判 `not_applicable` 而**不是** `unverified` | ✅ 20/20 PASS，`not_applicable` |
| 2 | `runs/20260924_142702_sac_lift_residual_grasp_lift/audit_truth20.json` | **不得**给 `controlled_success`（缺 `final_rise`/`held_at_end`）；且缺输入契约字段 → `INVALID` | ✅ 20 局 `provisional_pass`，`INVALID`（status=unverified） |
| 3 | `runs/infra/b_normclip/noclip.json`（输入契约违例） | `INVALID`，不是 `FAIL` | ✅ `measurement_invalid`（violated），94% 帧超界 |
| 4 | `runs/infra/b_normclip/clip3.json` | 有 `controlled_success`，PASS，且三类失效分开计数 | ✅ 1 `controlled_success` / 12 `over_lift` / 1 `flick` / 1 `insufficient_lift`，PASS |
| 5 | `runs/infra/lerobot_act_env_20260928/official_act_truth20_train24_lr1e-5_actionminmax_s20k_gatefields.json` | raw 11 局全部是抬起不足、**零弹射** | ✅ 11 `insufficient_lift` / 0 `flick` / 0 `over_lift` |
| 6 | `runs/infra/b_normclip/clip3.json`（开了输入截断） | `composite_policy=true`，约束清单含 `clip_norm_input` 且 side=`input` | ✅ |
| 7 | `runs/infra/b_normclip2/clip3_dzdb0.1.json`（截断 + dz 死区） | 两侧约束都在清单里，side 各自标对 | ✅ `[clip_norm(input), dz_deadband(exec)]` |
| 8 | `runs/infra/b_normclip/noclip.json`（无任何约束） | **负对照**：`composite_policy=false`，清单为空 | ✅ 未被凭空标注 |

| 9 | 合成夹具 `phase_mismatch_no_trace.json`（`phase_at_end='done'`，无 `phase_trace`） | 20 局 `unjudged` 移出分母、**0 局 flick**、文件 `INVALID` | ✅ 20 unjudged / flick=0 / INVALID |
| 10 | 合成夹具 `phase_mismatch_per_frame.json`（`done` + 逐帧 trace） | 同上（两字段词表互相矛盾） | ✅ |
| 11 | 合成夹具 `phase_ok_controller_log.json`（`done` + 6 元素状态机 trace） | **正对照**：20/20 `controlled_success`、PASS、`phase_field_kinds=[controller_log]` | ✅ 裁定 1 没有把合法状态机日志一起毙掉 |
| 12 | 合成夹具 `phase_ok_per_frame.json`（`hold` + 逐帧 trace，48 个官方臂就是这种） | **正对照**：矛盾 0 局、20/20、PASS | ✅ 证明裁定 1 对官方臂零影响 |
| 13 | 合成夹具 `na_verified.json`（无归一化 + 声明 + 区间齐备） | `not_applicable_verified`、测量有效、20/20、PASS | ✅ 裁定 2 解开 residual 臂的口径缺口 |
| 14 | 合成夹具 `na_no_reason.json`（reason 空白） | `not_applicable_unverified`、INVALID | ✅ 牙 1：声明不等于豁免 |
| 15 | 合成夹具 `na_no_closed_loop.json`（缺闭环区间） | `declared_no_closed_loop_range`、INVALID，但逐局仍 20/20 | ✅ 牙 2：INVALID 是**测量**问题不是策略失败 |
| 16 | 合成夹具 `na_out_of_range.json`（闭环 9.0 > 训练期 5.0×1.05） | `violated_out_of_range`、INVALID | ✅ 牙 3 |
| 17 | 合成夹具 `impl_known.json` | 指纹写进裁定 JSON、正常放行 | ✅ `blown_metric_impl=52eae25ee2d7` |
| 18 | 合成夹具 `impl_missing_new.json`（有 blown 字段、无指纹、不在豁免册） | **拒判**：`missing_new_reject`、INVALID | ✅ §12 分派的核心牙 |
| 19 | 合成夹具 `impl_unknown.json`（指纹不在已知清单） | `unknown_impl` + warn，但**不**判 INVALID | ✅ 「缺指纹拒判」≠「未知指纹拒判」 |
| 20 | 合成夹具，文件名命中豁免册臂名但 `mean_blown=0.5` | 豁免 `out_of_band_refused`、`ic_status` 维持 `violated`、INVALID | ✅ 豁免册不是翻案万能钥匙 |
| 21 | 合成夹具 `insuff_diag.json`（7 局 insuff，`final_rise` 手算） | `n=7`、中位 0.036、`gap_median=0.004`、`gap_min_best=0.0005`、`n_within_0p005=5`、`frac=0.714`、同夹具 5 局真受控 | ✅ B-3 |
| 22 | 合成夹具 `label_abstain_partial.json`（缺 `final_rise`/`held_at_end`/`phase_at_end`/`terminal_kind`） | `flick=0`、`insufficient_lift=0`、`unjudged=6`、`n_labels_abstained=6`、`labels_reportable=False`、`INVALID` 理由点名 `evidence_missing`、原标签留在 `label_before_abstain` | ✅ 裁定 14（复现 A 的 16 局假 `flick`） |
| 23 | 合成夹具 `label_strict_reportable.json`（同一次物理评测，字段补齐） | `insufficient_lift=6`、`flick=0`、`n_labels_abstained=0`、`measurement_valid=True` | ✅ strict 不被误伤（A §4.2） |
| 24 | 合成夹具 `label_terminal_kind_only.json`（**只**缺 `terminal_kind`） | `field_class=partial` 但 `labels_reportable=True`、`n_labels_abstained=0`、`measurement_valid=True`、`gate_pass=False` | ✅ DR-007 收窄护栏（防门禁作废自己的标定基准） |
| 25 | 合成夹具 `official_act_truth20_synthetic_clip_arm.json`（blown=0.212 带外）+ 候选册 `exo_clip_ok.json` | 豁免 `exonerated`、`band_checked=False`、`ic_status` 由 `violated` 升 `probe_exonerated`、`measurement_valid=True`、`gate_pass=True`、三套账不变 | ✅ 裁定 10 通道的**受理**路径（DR-008 决定 1/2/3/5） |
| 26 | 同夹具 + `exo_clip_scope_arm.json`（`scope=arm`） | `clip_channel_requires_artifact_scope`、维持 `violated`、INVALID | ✅ 决定 2 的牙；本夹具 impl 指纹是 `known`，命中的是**新增**的 scope 牙而不是既有的 `scope_requires_known_impl` |
| 27 | 同夹具 + `exo_clip_wrong_C.json`（登记 `clip_C=5.0`） | `clip_c_not_train_absmax`、回显产物自报 `12.469445`、维持 `violated` | ✅ 条件 ② 的牙：C 必须钉死在 train-absmax |
| 28 | 同夹具 + `exo_clip_no_clipC.json`（没写 `clip_C`） | `clip_c_undeclared`、维持 `violated` | ✅ 缺 C 不能当成 0 或跳过 |
| 29 | 同夹具 + `exo_clip_no_cosign.json`（`by` 为空） | `cosign_missing`、维持 `violated` | ✅ 裁定 16.4「B 写、D 会签」：B 不能自签 |
| 30 | 同夹具 + `exo_clip_cosign_nottrue.json`（`fact_basis="yes"`） | `cosign_missing`、维持 `violated` | ✅ 真值判断是 `is True`，不是 truthiness |
| 31 | 同夹具 + `exo_clip_cond_false.json`（cond2=false） | `entry_conditions_incomplete`、维持 `violated` | ✅ 五条准入有一条不成立即拒绝 |
| 32 | 同夹具 + `exo_clip_cond_missing.json`（缺 cond5） | `entry_conditions_incomplete`、维持 `violated` | ✅ 漏项与写 false 同样对待，否则漏项被读成通过 |
| 33 | 同夹具 + `exo_clip_probe_wrongclip.json`（证据实为 C=5.0 探针） | `probe_clip_mismatch`、`ic_status=probe_exoneration_invalid` | ✅ 条件 ⑤ 的牙：只看册子不看探针自报值就会放过 |
| 34 | 同夹具 + `exo_clip_probe_unstated.json`（探针没记录截断值） | `probe_clip_unstated`、`probe_exoneration_invalid` | ✅ 无法核验即判证据失效 |
| 35 | 同夹具 + `exo_clip_probe_sha_bad.json`（登记 sha 全 0） | `evidence_sha_mismatch`、`probe_exoneration_invalid` | ✅ 既有的 sha 牙在新通道上同样生效 |
| 36 | 同夹具 + `exo_clip_evidence_missing.json`（探针路径不存在） | `evidence_missing`、`probe_exoneration_invalid` | ✅ 既有的存在性牙在新通道上同样生效 |
| 37 | 同夹具（blown=0.212）+ `exo_reblown_outofband.json`（改按带内通道登记） | `out_of_band_refused`、`band_checked=True`、维持 `violated` | ✅ **决定 1 的保守性护栏**：分通道不是给旧通道开口子 |
| 38 | 同夹具 + `exo_unknown_kind.json`（`probe_kind=brand_new_channel`） | `out_of_band_refused`、`band_checked=True` | ✅ 白名单语义：未知 kind 一律按带内处理，不能靠写个新 kind 名绕过争议带 |
| 39 | 合成夹具 `…_synthetic_band_violated.json`（blown=0.06，**带内但超阈**）+ `exo_reblown_inband_violated.json` | 豁免状态是 `exonerated`，但 `ic_status` **维持 `violated`**、`measurement_valid=False` | ✅ **决定 5 的牙（晋级闸按 kind 分路）**：带内重测通道不能推翻一个真的超阈 |

第 1 条防假阴性（含 v1.2 新增的「门禁不得作废自己的标定基准」），第 2、3 条防假阳性，
第 4、5 条防「把不同失效混成一类」，第 6–8 条防「复合 policy 标注不对称 / 凭空标注」，
第 9–12 条防「裁定 1 过宽或过窄」（两条矛盾 + 两条正对照成对出现，只测一边等于没测），
第 13–16 条防「裁定 2 变成万能豁免口」，第 17–19 条防「指纹规则一刀切」，
第 20 条防「豁免册被用来翻带外的案」，第 21 条防「诊断字段恒报零」，
第 22–24 条防「裁定 14 过宽或过窄」（弃权与不误伤成对出现），
第 25–39 条防「裁定 10 通道变成新的翻案万能钥匙」——1 条受理 + 14 条拒绝成对出现：
第 26–32 条逐条钉住四条准入（scope / `clip_C` / 缺 `clip_C` / 会签两种写法 / 五条准入两种写法），
第 33–36 条钉住证据侧（探针自报截断值不符、未记录、sha 不符、文件不存在），
第 37–38 条是**保守性**护栏（同一带外臂改走旧通道、以及未知 kind，都必须仍被拒绝），
第 39 条钉住晋级闸的 kind 分路（豁免受理 ≠ 自动晋级）。
改判据后必须逐条重跑；期望值随版本变化时要同步改本表，
**不得**留着旧期望值让门禁长期红。

**本表已是可执行的**（v1.2.1 起，不再靠人肉核对）：

```bash
python3 scripts/b_selfcheck_gate_regression.py            # 39 用例 / 157 断言，退出码即裁定
python3 scripts/b_selfcheck_gate_mutation.py              # 15 个变异体必须全部被抓住（证明断言有牙）
python3 scripts/b_regate_all.py --allow-failing-arms      # 一键重判全部留档产物 + 自动跑本表
```

两条防「检查本身恒真」的护栏（本仓已有恒真断言导致 pin 漂移全绿通过的先例）：
夹具缺失按 **FAIL** 不按 skip；一条断言都没评上时强制 `ok=false`。
变异验证有牙：`--rise-cap 0.30` → 19/21 红；`--final-rise 0.08` → 19/21 红；
把 `INPUT_CONSTRAINT_KEYS` 清空（退回 v1.2 行为）→ 第 6、7 条红；
把它放宽到全部键 → 第 8 条负对照红。

v1.3 起变异验证**也是可执行的**（`scripts/b_selfcheck_gate_mutation.py`，不改盘上门禁源码，
在内存里替换函数后对同一批夹具重跑断言）：

| 变异体 | 模拟的退化 | 应变红的用例 | 实测 |
|---|---|---|---|
| `M1_裁定1_词表矛盾不再拦` | `phase_vocab_status` 恒返回 `consistent`（退回 v1.2.1 兜底） | 9、10 | ✅ CAUGHT |
| `M2_裁定2_声明无条件放行` | `not_applicable_check` 恒返回 `verified_in_range` | 14、15、16 | ✅ CAUGHT |
| `M3_§12_缺指纹不再拒判` | `blown_impl_check` 恒返回 `known` | 18 | ✅ CAUGHT |
| `M4_裁定3_带外也受理豁免` | `probe_exoneration_check` 去掉争议带护栏 | 20 | ✅ CAUGHT |
| `M5_B3_诊断恒报零` | `insuff_diagnostic` 恒返回 `n=0` | 21 | ✅ CAUGHT |
| `M6_裁定14_弃权被关掉` | `LABEL_CRITICAL_FIELDS = ()` → `labels_reportable` 恒 True（= 静默移除裁定 14，退回 v1.3 的 16 局假 `flick`） | 22 | ✅ CAUGHT |
| `M7_裁定14_按DR-D09字面实现` | `LABEL_CRITICAL_FIELDS` 加上 `terminal_kind`（= 裁定的字面口径） → base-only 标定件被判 `measurement_valid=False` | 1、24 | ✅ CAUGHT |
| `M8_DR008_分通道被撤掉` | `BAND_EXEMPT_PROBE_KINDS = ()` → 所有 kind 都要过争议带（= 静默撤销 DR-008 决定 1） | 25 | ✅ CAUGHT |
| `M9_DR008_晋级闸被放宽` | 带内重测通道也允许从 `violated` 晋级（= 有人图省事写成「exonerated 即晋级」） | 39 | ✅ CAUGHT |
| `M10_DR008_C不必等于train_absmax` | `CLIP_C_TOL = 1e9` → 不再核对登记的 C 与产物自报的训练期 absmax | 27 | ✅ CAUGHT |
| `M11_DR008_会签不再核验` | `_clip_channel_precheck` 不再真读 `cosign` 字段 → B 可以自签 | 29、30 | ✅ CAUGHT |
| `M12_DR008_五条准入不再核验` | `_clip_channel_precheck` 不再要求 `ruling10_conditions` 逐条 true | 31、32 | ✅ CAUGHT |
| `M13_DR008_臂级也受理` | `_clip_channel_precheck` 去掉 `scope=artifact` 要求 → 豁免随臂迁移 | 26 | ✅ CAUGHT |
| `M14_DR008_探针自报截断值不再核验` | `_clip_evidence_check` 恒返回通过 → 只看册子不看探针 | 33、34 | ✅ CAUGHT |
| `M15_DR008_假证据不再判invalid` | `EXONERATION_EVIDENCE_FAILURES` 去掉两个新成员（保留核验、**不接线**到后果） | 33、34 | ✅ CAUGHT |

`M6` / `M7` 是一对**方向相反**的变异体：M6 抓「把裁定 14 删掉」，M7 抓「把裁定 14 实现得比裁定本身更宽」。
`M8` / `M9` 是 v1.5 的同一对：M8 抓「把 DR-008 删掉」（分通道撤回，裁定 16.4 的条目重新永远无法受理），
M9 抓「把 DR-008 实现得比裁定本身更宽」（晋级闸放宽成 `exonerated` 即可升 `violated`，
于是一次「换把尺子重测」就能推翻一个真的超阈，裁定 12 被架空）。
`M14` / `M15` 也是一对：M14 抓「核验被删掉」，M15 抓「核验留着但后果没接线」——
后者更隐蔽，因为状态字照样算出来了，只是没人读。
后者同样危险 —— 它会让门禁作废自己的 `rise_cap` 标定基准（§2.16.1）。

基线（未变异）必须 **39/39** 全绿，否则「变红」没有参照 —— 这条也写进了脚本的判定里
（`baseline_all_green=false` 时整体判 FAIL）。
