# Residual Lift 监管口径状态

监管复核要求 residual 三臂对照必须使用同一预算、固定 seed 和 `grasp_verified` 真值。

当前已有产物不能直接进入结论表：

- `runs/20260924_140627_residual_smoke/result.json` 报告 `success=5031`、`episodes=20`，违反计数上界，判为无效产物；
- `runs/20260924_141014_residual_smoke2/` 与 `runs/20260924_141844_residual_phase_smoke/` 只有 1000 training steps，属于接口 smoke，不是学习有效性证据；
- `runs/20260924_142907_lift_base/` 的脚本 base 在 pinned seeds 5000–5019 上为 20/20，但只作为 base 能力基线，不能推出 residual 增益。

当前有一条 60k residual 训练正在运行：

```text
scripts/train_residual_lift.py
--steps 60000 --eval-freq 10000 --eval-episodes 5
--residual-scale 0.25 --residual-phases grasp,lift --seed 0
```

训练完成后，必须用 `scripts/audit_residual_lift.py` 重新评估。该脚本会在 `ResidualLiftEnv` 内加载 checkpoint，记录 raw success、真实 `_check_grasp`、success_grasp_verified、max_rise、phase 和 residual 激活步数，避免把 residual action 错送到普通 Lift 环境。

状态：

- 已实现：独立审计脚本；
- 已验证：脚本可编译；
- 待验证：60k residual checkpoint 的固定 20 seed 真值评估；
- 未实施：base-only / from-scratch / residual 的正式同预算三臂结论。
