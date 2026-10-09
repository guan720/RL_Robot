# Residual Lift 独立真值审计

审计对象：`runs/20260924_142702_sac_lift_residual_grasp_lift/model_final.zip`

审计命令使用 `/root/venvs/rlrobot/bin/python`，因为系统 `python3` 未安装 `stable_baselines3`。参数为 20 局、pinned seeds `5000–5019`、horizon `300`、residual scale `0.25`，residual phases 为 `grasp,lift`。

## 汇总

| 指标 | 结果 |
|---|---:|
| raw success | 20/20 = 100% |
| grasp verified | 20/20 = 100% |
| success_grasp_verified | 20/20 = 100% |
| mean max_rise | 0.10013615 |
| residual active steps | 平均 26.7 |
| harness / recovery 救场 | 0 局；审计脚本未启用 guard |
| failure phase | 无失败局 |

逐局结果已保存在：`runs/20260924_142702_sac_lift_residual_grasp_lift/audit_truth20.json`。

## 逐局结果

| seed | raw | grasp_verified | success_grasp_verified | max_rise | residual active steps | phase trace |
|---:|---:|---:|---:|---:|---:|---|
| 5000 | 1 | 1 | 1 | 0.108605 | 26 | approach→descend→grasp→lift→hold→done |
| 5001 | 1 | 1 | 1 | 0.106769 | 26 | approach→descend→grasp→lift→hold→done |
| 5002 | 1 | 1 | 1 | 0.108152 | 26 | approach→descend→grasp→lift→hold→done |
| 5003 | 1 | 1 | 1 | 0.099647 | 26 | approach→descend→grasp→lift→hold→done |
| 5004 | 1 | 1 | 1 | 0.111046 | 26 | approach→descend→grasp→lift→hold→done |
| 5005 | 1 | 1 | 1 | 0.111196 | 26 | approach→descend→grasp→lift→hold→done |
| 5006 | 1 | 1 | 1 | 0.102606 | 26 | approach→descend→grasp→lift→hold→done |
| 5007 | 1 | 1 | 1 | 0.079818 | 31 | approach→descend→grasp→lift→hold→done |
| 5008 | 1 | 1 | 1 | 0.107962 | 26 | approach→descend→grasp→lift→hold→done |
| 5009 | 1 | 1 | 1 | 0.076571 | 33 | approach→descend→grasp→lift→hold→done |
| 5010 | 1 | 1 | 1 | 0.105736 | 26 | approach→descend→grasp→lift→hold→done |
| 5011 | 1 | 1 | 1 | 0.099367 | 26 | approach→descend→grasp→lift→hold→done |
| 5012 | 1 | 1 | 1 | 0.105851 | 26 | approach→descend→grasp→lift→hold→done |
| 5013 | 1 | 1 | 1 | 0.104982 | 26 | approach→descend→grasp→lift→hold→done |
| 5014 | 1 | 1 | 1 | 0.103721 | 26 | approach→descend→grasp→lift→hold→done |
| 5015 | 1 | 1 | 1 | 0.109000 | 26 | approach→descend→grasp→lift→hold→done |
| 5016 | 1 | 1 | 1 | 0.098725 | 26 | approach→descend→grasp→lift→hold→done |
| 5017 | 1 | 1 | 1 | 0.091809 | 26 | approach→descend→grasp→lift→hold→done |
| 5018 | 1 | 1 | 1 | 0.102333 | 26 | approach→descend→grasp→lift→hold→done |
| 5019 | 1 | 1 | 1 | 0.068827 | 28 | approach→descend→grasp→lift→hold→done |

## 监管判定

该 checkpoint 通过 residual 自身的独立真值审计，但这只证明它在该 pinned 测试集上完成了真实抓取。现有 `base-only` 结果为 raw `20/20`，尚未以同一审计脚本提供 `grasp_verified` 和 `max_rise`，因此不能宣称 residual 相对 base-only 有增益，也不能把本结果归因于 harness 救场。

按监管指令，当前不启动 ACT 或 from-scratch SAC；三臂正式对照仍未完成。
