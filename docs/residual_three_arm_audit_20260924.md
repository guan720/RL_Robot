# Lift residual 三臂独立审计（2026-09-24）

## 审计范围与口径

三组结果均使用独立只读评测，任务为 Robosuite Lift，pinned object seed `20260923`，出生 seed `5000–5019`，horizon `300`。raw success 来自环境 success；`grasp_verified` 来自 robosuite `_check_grasp`；`success_grasp_verified = raw_success ∧ grasp_verified`；成功上升使用 `max_rise ≥ 0.04 m`。

## 三臂状态

| 手臂 | 定义 | 状态 | 证据 |
|---|---|---|---|
| 1 | scripted/base-only | 已完成、已审计 | `runs/20260924_142907_lift_base/audit_truth20.json` |
| 2 | from-scratch SAC | 已完成、已审计 | `runs/20260924_153014_sac_lift_from_scratch_seed0/audit_truth20.json` |
| 3 | bounded residual SAC | 已完成、已审计 | `runs/20260924_142702_sac_lift_residual_grasp_lift/audit_truth20.json` |

## 汇总

| 指标 | base-only | from-scratch SAC | residual SAC |
|---|---:|---:|---:|
| raw success | 20/20 | 0/20 | 20/20 |
| grasp_verified | 20/20 | 9/20 | 20/20 |
| success_grasp_verified | 20/20 | 0/20 | 20/20 |
| success_rise (max_rise ≥ 0.04 m) | 20/20 | 0/20 | 20/20 |
| mean max_rise (m) | 0.076330 | 0.000189 | 0.100136 |

## 按 seed 逐局配对

`Δ residual-base` 和 `Δ from-scratch-base` 仅作为辅助物理差异；主结论看 raw success、真实抓取成功和成功上升。from-scratch SAC 的 failure phase 均为 `unknown`，因为其评测信息未暴露可验证 phase。

| seed | base raw | SAC raw | residual raw | base grasp | SAC grasp | residual grasp | base rise↑ | SAC rise↑ | residual rise↑ | base max_rise | SAC max_rise | residual max_rise | SAC failure |
|---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|---:|---:|---:|---|
| 5000 | Y | N | Y | Y | N | Y | Y | N | Y | 0.077400 | 0.000000 | 0.108605 | unknown |
| 5001 | Y | N | Y | Y | N | Y | Y | N | Y | 0.079600 | 0.000000 | 0.106769 | unknown |
| 5002 | Y | N | Y | Y | N | Y | Y | N | Y | 0.077000 | 0.003774 | 0.108152 | unknown |
| 5003 | Y | N | Y | Y | Y | Y | Y | N | Y | 0.076000 | 0.000000 | 0.099647 | unknown |
| 5004 | Y | N | Y | Y | N | Y | Y | N | Y | 0.076000 | 0.000000 | 0.111046 | unknown |
| 5005 | Y | N | Y | Y | Y | Y | Y | N | Y | 0.076500 | 0.000000 | 0.111196 | unknown |
| 5006 | Y | N | Y | Y | Y | Y | Y | N | Y | 0.075600 | 0.000000 | 0.102606 | unknown |
| 5007 | Y | N | Y | Y | N | Y | Y | N | Y | 0.075800 | 0.000000 | 0.079818 | unknown |
| 5008 | Y | N | Y | Y | Y | Y | Y | N | Y | 0.075800 | 0.000000 | 0.107962 | unknown |
| 5009 | Y | N | Y | Y | Y | Y | Y | N | Y | 0.076100 | 0.000000 | 0.076571 | unknown |
| 5010 | Y | N | Y | Y | Y | Y | Y | N | Y | 0.075900 | 0.000000 | 0.105736 | unknown |
| 5011 | Y | N | Y | Y | Y | Y | Y | N | Y | 0.075800 | 0.000000 | 0.099367 | unknown |
| 5012 | Y | N | Y | Y | N | Y | Y | N | Y | 0.075600 | 0.000000 | 0.105851 | unknown |
| 5013 | Y | N | Y | Y | N | Y | Y | N | Y | 0.076000 | 0.000000 | 0.104982 | unknown |
| 5014 | Y | N | Y | Y | Y | Y | Y | N | Y | 0.075500 | 0.000000 | 0.103721 | unknown |
| 5015 | Y | N | Y | Y | N | Y | Y | N | Y | 0.077600 | 0.000000 | 0.109000 | unknown |
| 5016 | Y | N | Y | Y | N | Y | Y | N | Y | 0.075800 | 0.000000 | 0.098725 | unknown |
| 5017 | Y | N | Y | Y | Y | Y | Y | N | Y | 0.076200 | 0.000000 | 0.091809 | unknown |
| 5018 | Y | N | Y | Y | N | Y | Y | N | Y | 0.076400 | 0.000000 | 0.102333 | unknown |
| 5019 | Y | N | Y | Y | N | Y | Y | N | Y | 0.076000 | 0.000000 | 0.068827 | unknown |

## 结论

base-only 在 20 局中为 raw success 20/20、真实抓取成功 20/20、成功上升 20/20。from-scratch SAC 为 raw success 0/20、真实抓取成功 0/20、成功上升 0/20，平均 max_rise 仅 0.000189 m。bounded residual SAC 为 raw success 20/20、真实抓取成功 20/20、成功上升 20/20。

在当前固定 seed 配对中，residual 已验证可用，但相对 scripted/base-only 未证明任务成功率增益；`max_rise` 的均值更高只是辅助现象，不能替代主指标。from-scratch SAC 已完成审计且明显未达到任务成功，因此三臂结果现在可以完整报告，但不能把 residual 的成功归因于从零 SAC 学习能力。

## 复核命令

```bash
python3 scripts/audit_lift_sac_truth.py --ckpt runs/20260924_153014_sac_lift_from_scratch_seed0/model_final.zip --episodes 20 --seed0 5000 --horizon 300 --out runs/20260924_153014_sac_lift_from_scratch_seed0/audit_truth20.json
```
