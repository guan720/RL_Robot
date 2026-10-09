# harness/

阶段 3 放这里：任务编排、调度、恢复、接管。

- 行为树用 py_trees；可运行的最小示例先看 `scripts/demo_harness_tree.py`。
- 这里只放**流程**（现在跑哪个任务、失败了走哪条路、什么时候停）。
- 能力（怎么抓、怎么动）属于 `skills/` 和 `policies/`，不要写在这里。
- 状态通过 Blackboard 共享，节点之间不直接互相调用。

## 抓取监护 `grasp_guard.py`（干预，不是能力替换）

策略"已经到了能抓的位置却迟迟不合爪"时，由一段有特权的脚本原语接管一次
（对齐 → 合爪 → 提起 → 交还控制权；每局 ≤2 次、有冷却）。它对应 HIL-SERL 里
"人类干预"的位置，只是干预者换成了脚本。三种用法，别混：

- **测量**：`scripts/eval_pickplace_ckpt.py --guard` 做同 seed 配对评测，输出
  `rescue_delta` / `held_delta` / `intervention_rate`。只报"带监护"的成绩 = 把脚本的功劳
  记到策略头上（与 RoboRSI 报告里"累计覆盖掩盖退化"是同一类错误）。
- **诊断**：监护**一次都没出手**本身就是结论 —— 失败不在合爪这一环，在它的上游
  （接近/对齐/下降）。2026-09-24 的 PickPlace 就是这样（漏斗 `held 0/12`）。
- **数据**：`train_pickplace_sac.py --guard-rounds/--guard-inject` 把"策略卡住那一小段"的
  出手记录当干预示范，聚合进 BC 集并注入 SAC 回放池（比 DAgger 少 1–2 个量级数据）。

纪律：成功只认环境真值（`env._env._check_success()`），监护器不自己宣布成功；
环境与出题一律走 `env_factory`（钉死物体尺寸 + 按叶子播种），否则配对评测配的是两个不同物体。

## 闭环里的判定口径

- `LoopConfig.gate_stats`：`legacy`（二态，默认，保历史可比）/ `paired_v1`
  （三态 `publish`/`reject`/`inconclusive`，见 `registry/README.md`）。CLI 是 `--gate-stats`。
- `resolution_audit()` 每轮记账：评测局数的噪声地板 MDE、`min_gain`/`regression_tol`
  是否分辨得起、以及逐题配对的 McNemar 结果。`gate_stats=paired_v1` 时它**参与判定**，
  `legacy` 时只作参考（但一样打进日志：它与二态结论矛盾时，矛盾本身就是"这轮在量噪声"的证据）。
- 判定所需的逐局记录由 `registry.score_skill()` 的 `standard.episode_outcomes` 提供，别剥掉。
- `loop_result.json` 里 `n_inconclusive` = 有多少轮是"测不出来"而不是"判定了"，
  这是分辨率欠账的账本。
- 背景：`docs/notes_stage3.md` §12.11-G / Q。

## 接触任务（Lift / PickPlace）的唯一入口：`env_factory`

接触任务的环境构造与**出题**都走 `harness/env_factory.py`，别在脚本里各自 `gym.make` 再手设
`placement_initializer.rng` —— 那条路在 PickPlace 上静默无效（`docs/notes_stage3.md` §7 第 28 条）。

- `make_contact_env(task, ...)` / `contact_env_bundle(task, ...)`：构造期套 `pinned_object_rng()`。
  物体尺寸是 robosuite 构造期用未播种 RNG 抽的，不钉死 ⇒ **每个进程评的是不同物体**。
- `contact_object()` / `contact_object_geom()`：取真实操作物体（robosuite 1.5 的 PickPlace
  **没有** `.can`，物体在 `.objects[.object_id]`）与其几何/质量/篮位，写进产物供跨 run 核对。
- `placement_leaves()` / `seed_placement()` / `set_spawn_half_range()`：**按叶子** sampler 操作。
  PickPlace 的 initializer 是 `SequentialCompositeSampler`（`sample()` 只遍历子 sampler）。
- `reset_contact(env, seed)`：可复现 reset；Lift 的单叶子路径与历史产物**逐位一致**。
- `place_truth_fn(env, task)`：放置段真值（`in_bin` / `above_bin` / `dist_target` / `r_reach`），
  用 robosuite 自己判成功的那两个条件，不另立阈值。Lift 返回 `None`。

## 判定口径（`LoopConfig`）

- `success_metric`（默认 `success_rate`，可选 `success_rate_grasp_verified`）与
  `require_grasp_verified`（默认 `False`）；CLI 是 `--success-metric` / `--require-grasp-verified`。
- `resolution_audit()` 按**被判口径**记账（`cfg.success_metric`），日志同时露两个口径 ——
  两者差得多时，差值本身就是"指标被弹起污染"的证据。
- 默认值是 legacy：历史 run 的 `n_published` 仍然可比（自检第 16 项 (8)）。
