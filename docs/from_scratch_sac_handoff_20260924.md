# From-scratch SAC 对照实验交接

实验已完成，未启用 ACT、视觉、示范、BC、guard 或 DAgger。

运行配置：

- task: `lift`
- observation: `state`
- steps: `60000`
- horizon: `300`
- seed: `0`
- eval seeds: 训练脚本默认评测集
- pinned object: enabled，`pinned_object_seed=20260923`
- reward shaping: enabled
- device: CUDA

产物目录：`runs/20260924_153014_sac_lift_from_scratch_seed0/`

- `config.json`
- `eval_curve.json`
- `result.json`
- `model_best.zip`
- `model_final.zip`

训练曲线的 5 局 raw 评测：

| step | raw success | tasks | mean reward |
|---:|---:|---:|---:|
| 10000 | 0/5 | 0 | 1.3290 |
| 20000 | 0/5 | 0 | 9.4510 |
| 30000 | 0/5 | 0 | 15.6584 |
| 40000 | 0/5 | 0 | 39.9894 |
| 50000 | 0/5 | 0 | 105.4967 |
| 60000 | 0/5 | 0 | 112.7765 |

最终冻结 raw 评测也是 `0/5`，平均 reward `114.8183`。这只是训练脚本 raw 指标，不能替代真实抓取判定。

下一步由 B 使用与 residual 相同的 pinned seeds `5000–5019`、horizon `300`，对 `model_final.zip`（必要时同时记录 `model_best.zip`）执行 `grasp_verified` 真值审计，并报告 `success_raw`、`grasp_verified`、`success_grasp_verified`、`max_rise`、失败阶段和 residual/救场字段。完成该审计前，不对三臂结果下结论。
