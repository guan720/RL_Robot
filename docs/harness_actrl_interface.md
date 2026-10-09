# Harness 与分层 ACT-RL 接口对齐

2026-09-24

阶段 2 的分层策略可以直接接入现有 harness，但必须保持职责边界：harness 只调度、记录和门禁，phase policy、ACT action chunk 和 residual learner 留在 `skills/` / `policies/`。

本次接口调整有三点：

1. `Skill` 增加可选 `act_with_context(obs, context)`。旧技能继续实现 `act(obs)`；分层策略可以读取当前 `phase`、步号、上一帧 verifier `info`、方向和目标。这样行为树不需要知道 ACT 的 chunk 或低层 residual 实现。
2. `EpisodeRecord` 增加可选 `phase_trace`、`failure_phase`、`success_raw`、`success_grasp_verified`、`max_rise`、`held_steps`、`regrasp_count`。旧 Reach 记录仍然有效；接触任务只在环境通过 `info` 提供字段时记录，不用诊断字段改写成功判定。
3. `skills/layered.py` 提供 `PhaseSkill` 和 `ResidualSkill`：前者按环境报告的 phase 分发子技能，后者执行 `clip(base + scale * residual)`。两者都保持单一 `Skill` 元数据和 reset 生命周期，适合接入 registry 与独立评测。

诊断汇总额外输出 `phase_counts`、`failure_phases`、`success_raw_rate`、`success_grasp_verified_rate` 和 `mean_max_rise`。这些字段用于区分“ACT 高层选错阶段”“低层接触失败”和“成功口径被弹起污染”，不参与环境 success 的替代判定。

阶段 2 实现侧需要遵守以下契约：

- 环境 `info["phase"]` 使用稳定字符串；阶段切换时仍由环境 verifier 或技能状态机决定。
- 若能计算接触真值，提供 `success_grasp_verified` 或 `grasp_verified`；缺失时门禁不得把它静默当成真。
- residual 的输出范围固定为 `[-1, 1]`，缩放和裁剪由 `ResidualSkill` 或环境唯一完成一次，避免重复缩放。
- action chunk 的异步接纳、执行和物理生效仍需在策略内部记账；harness 每个环境 tick 只记录实际执行后的 `info`。
- 训练 checkpoint 的 `SkillMeta.config_hash` 应包含 phase 集合、chunk 长度和 residual scale；改变这些参数必须产生新的版本线或被 registry 拦截。

验证：`/root/venvs/rlrobot/bin/python scripts/selfcheck_stage3.py` 全部 16 项通过；新增适配器通过 Python 编译检查。
