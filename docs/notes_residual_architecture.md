# 接触任务分层实验

当前 Lift 接触实验固定为三路：

1. `base-only`：脚本/PD 状态机完成完整动作序列；
2. `SAC from scratch`：现有 `train_pickplace_sac.py` 的单一 SAC；
3. `base + bounded residual SAC`：`ResidualLiftEnv` 内先执行 base 动作，SAC 只输出 `scale * residual`，再限幅到执行器范围。

残差实验的动作记录同时保存 `base_action`、`residual_action`、`executed_action` 和当前 phase。成功只使用 Lift 真值判定；固定题集使用 pinned object seed 和 `reset_contact`。

当前 residual 版本先用 state observation 验证控制结构，`residual_scale=0.25`。后续再把 ACT 替换 base controller：ACT 负责动作段，residual SAC 只在 approach / grasp / lift 阶段启用。ACT 权重不会直接转换成 SAC 权重。

最小命令：

```bash
python scripts/eval_lift_base.py --episodes 20
python scripts/train_pickplace_sac.py --task lift --obs state --reward-shaping 1 --demo-steps 5000 --bc-steps 3000 --steps 60000
python scripts/train_residual_lift.py --steps 60000 --residual-scale 0.25
```
