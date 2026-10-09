# registry/

阶段 3 放这里：**通过评测才发布**的技能版本，只增不覆盖。

    registry/<skill_name>/<version>/
        model.zip          # 或技能代码
        meta.json          # 训练配置 hash、评测 seed、评测条件、分数
        result.json        # 独立评测结果

发布门槛（最小 CI）：

    train.py -> eval.py(独立 seed + 严酷探针) -> 旧任务回归不掉点 -> 才写入这里

- 同时保留两种指标：**累计覆盖**（历史上解决过多少任务）和**冻结版本单次成功率**。
  只看前者会用「累计覆盖提高」掩盖旧任务退化。

## 两套判定口径（`gate_stats`）

| 口径 | 函数 | 输出 | 什么时候用 |
| --- | --- | --- | --- |
| `legacy`（默认） | `decide()` | 二态：过 / 不过 | 与历史 run 可比；评测局数的噪声地板 MDE **小于** `min_gain` 时 |
| `paired_v1` | `decide_paired()` | 三态：`publish` / `reject` / `inconclusive` | 接触任务（50 局 MDE≈0.26 而 `min_gain=0.02`）必须用 |

三态的动作含义：`publish` = 换现任；`reject` = **能判定**且不发布（硬失败 / 显著掉点超容忍 /
提升真实但不足 `min_gain`，此时 `direction` 仍是 `better`）；`inconclusive` = **测量分辨不出**
⇒ 下一步是加局数或改配对，**不要**判这个技能方向失败。
显著性优先用逐题配对的 McNemar 精确检验（两臂同一批 seed，零额外成本），
缺逐局记录时回退到未配对口径并用 MDE 判"分辨不分辨得出"。

**配对的数据链**：`score_skill()` 必须把逐局结果精简成 `standard.episode_outcomes`
（`seed` + `success`）留在 scores 里 —— 少了它，`harness/loop.py::resolution_audit`
的配对分支会静默退化成「无法配对」（这个 bug 真发生过，自检第 15 项 (13) 守它）。

背景与实测对照：`docs/notes_stage3.md` §12.11-G / L / Q，§7 第 26 条。

## 接触任务的两个成功口径（`SUCCESS_KEYS`）

| 口径 | 常量 | 含义 |
| --- | --- | --- |
| `success_rate` | `SUCCESS_RATE` | 环境 `_check_success()` 的原样结果。**可以被"弹一下"满足**：Lift 臂 a 实测 `flick_frac=0.500`（22 个成功局里 11 局 `_check_grasp` 全程为假），真抓起来只有 0.037 |
| `success_rate_grasp_verified` | `SUCCESS_RATE_GRASP` | 成功 **且** 抓取真值为真。接触任务的门禁应该用这一个 |

- `contact_bundle_from_probe(rows, success_key=...)`：把 `scripts/probe_contact_ceiling.py` 的
  逐局记录打成门禁要的 bundle。两个口径都算；`episode_outcomes[i]["success"]` 跟着 `success_key` 走，
  `success_raw` **永远留档** ⇒ 事后还能复算 flick。
- `decide_paired(..., success_key=, require_grasp_verified=)` 的三条硬拒绝，都走
  `hard=True` + `direction="unknown"`（语义是**不能比**，既不是"测不准"也不是"技能差"）：
  · `metric_flick_contaminated` —— `flick_frac ≥ FLICK_REJECT_ABOVE`(=0.5)，指标被弹起污染；
  · `missing_grasp_verified` —— 要求 grasp 口径但有一侧没报；
  · `missing_metric` —— 任一侧缺**被判口径**，不许静默按 0.0 判（两侧口径不一致同样拒）。
- legacy 行为逐字不变：不传新参数 == `success_key=SUCCESS_RATE`（自检第 16 项 (6)(7)(8) 守着）。
- 背景与实测：`docs/notes_stage3.md` §12.11-N / R，§7 第 24 条。

## 裁定身份与有效性（`verdict_identity`）

上游门禁裁定（`runs/infra/lerobot_act_env_20260928/gate_*.json`）在进账本 / 进发布包之前，
必须先绑定「谁判的、用哪一版判据、这次测量本身可不可信」。`registry/verdict_identity.py`
只做这件事：**只读上游、不重算判据、不重判**。

| 档（`usable_for`） | 触发 | 能不能当物理事实 |
| --- | --- | --- |
| `not_a_verdict` | 带 `arms`/`thresholds`、无 `accounts`（聚合/敏感度报告） | 不能：它**关于**裁定，本身不是一次测量 |
| `unidentified_build` | `gate_build` 缺失，或 `measurement_valid` 字段不存在 | 不能；也**不得**读成 INVALID（那是替上游下结论） |
| `invalid_measurement` | 上游明确 `measurement_valid=False`，或怀疑把截断标成失败 | 不能；留档 + 归因 |
| `stale_build_evidence` | 构建 ≠ 当前构建 | 不能；重判后才可用 |
| `physical_fact` | 当前构建 + `measurement_valid is True` + 不怀疑截断 | 可以 |

- **当前构建 import 上游、绝不硬编码**：`current_gate_identity()` 读
  `scripts/b_gate_controlled_success.py` 的 `GATE_BUILD`（= 该脚本内容的 sha12）。
  实测 2026-09-28 21:15–21:23 之间当前构建变了三次（v1.2.1 → v1.3 的两个 build），
  写死版本号的实现当天就过期。
- **取代关系**：同一被判决的评测文件（`eval_file`）同时有旧构建与当前构建的裁定 ⇒
  当前那份 `superseded_by` 指向它；只有旧构建 ⇒ `superseded_by=None`，含义是「尚未重判」，
  **不是**「仍然有效」。
- **三键齐备**（监管备忘 增补六）：`field_class`（裁定 14 的前提量）、`validity_class`、
  `blowup_threshold_source`。后两键**只从 A 的 `arms_summary.json` join**，C 不自己推导 ——
  `scripts/summarize_lerobot_act_arms.py` 是它的唯一生产者，免罪资格由 `probe_exoneration()`
  在代码里断言 5 项准入；C 再写一遍就是第二套判据。匹配不上就记 `absent_from_arms_summary`。
- **两种取代关系分列**：C 的 `superseded_by` = 判据构建层面的取代；
  A 的 `upstream_superseded_by` = 评测产物层面的取代（留档原件 → `blindfix/` 重测件）。
  `field_class` 同样两份（本地这份裁定的 / A 权威行的 `arm_field_class`），
  两者不一致的记录**不得**当 `physical_fact`。
- **n 守卫**（增补五 §9-C④）：`assert_n_matches_arm(n, read_arm_timing(eval_json))` ——
  真实帧路径的槽长 `n` 必须等于该臂的 `n_action_steps`（实测 K=2 族为 2、K=4 族为 4），
  不得沿用规格算例的 `n=6`，不一致就抛、不静默换算。
- **内容寻址**：每条记录带裁定文件与被判决评测文件的 sha256。git 已按 DR-002 初始化
  （commit `0137b33`），但 `.gitignore` 排除 `runs/` ⇒ 产物身份仍只能靠内容指纹。
- 实测规模与来源分层：`runs/infra/c_verdict_identity_inventory.json`；
  构建跳变流水：`runs/infra/c_gate_build_observed.jsonl`；
  自检 60 项（含 3 个变异体）：`scripts/c_selfcheck_verdict_identity.py`；
  设计与两处被自检抓出的真 bug：`docs/c_verdict_identity_20260928.md`。

**尚未接线**（P0-3 第二层）：`DirectionScore` 还没有身份字段，`harness/ledger.py`
的 `ingest_runtime_result` 还不吃裁定。在接上之前，任何跨臂数字都必须自带
`gate_build` + `usable_for`，否则无从判断它是不是旧口径。
