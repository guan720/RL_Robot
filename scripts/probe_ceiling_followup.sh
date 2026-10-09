#!/usr/bin/env bash
# 修完 `calibrate_rise` 口径之后的两个**便宜**收尾实验（都只跑手写参照臂，不碰对方 ckpt）。
#
# F1) Lift 4 局回归：确认改 `calibrate_rise(rows, task)` 没有动到 Lift 路径。
#     参照物是 runs/infra/smoke_probe_lift_regress_4ep.json（改之前那次的产物）：
#     出生点、成功局数、`rise_calibration`（含字段名 `rise_at_success_min_max`）必须逐位相同。
#
# F2) PickPlace 手写上限是不是被 horizon 卡住的？四臂诊断里手写参照臂 0.719，
#     9 个失败局**全部跑满 400 步**，而成功局只用 141~236 步（中位 173）。
#     这有两种互斥解释，指向完全不同的结论：
#       ① 控制器太慢/预算太短  -> 0.719 是 horizon 的函数，不是任务难度；
#                                  gate 的 ceiling 规则和 min_gain 都得按放宽预算的那个数重定
#       ② 卡住了（极限环/工作空间到顶） -> 0.719 就是 400 步预算下的真实上限
#     判据：把 horizon 放到 800（2 倍）重跑同一批 seed。失败局的 `final_rise`/`min_bin_dist`
#     若还是原地不动（0.0648 / 0.376），就是 ②；若继续推进并成功，就是 ①。
#     注意口径：SAC 臂只有 400 步，所以**策略可比的那个上限仍然是 400 步那个数**；
#     800 步这一跑回答的是"0.719 该不该被读成任务难度"。
#
# 纪律：串行（避免并发污染 sec_per_episode）；产物落 runs/infra/。
set -u
cd /workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot
PY=/root/venvs/rlrobot/bin/python
LOG=runs/infra/probe_ceiling_followup.log
: > "$LOG"

echo "==================== F1 lift 4 局回归（口径改动后） ====================" >> "$LOG"
date -Is >> "$LOG"
MUJOCO_GL=egl OMP_NUM_THREADS=1 nice -n 15 "$PY" -u scripts/probe_contact_ceiling.py \
    --task lift --episodes 4 --horizon 300 --skip-sac \
    --out runs/infra/smoke_probe_lift_regress_4ep.postfix.json >> "$LOG" 2>&1
echo "  -> exit=$?" >> "$LOG"

echo "==================== F2 pickplace 手写臂 horizon 800 ====================" >> "$LOG"
date -Is >> "$LOG"
MUJOCO_GL=egl OMP_NUM_THREADS=1 nice -n 15 "$PY" -u scripts/probe_contact_ceiling.py \
    --task pickplace --episodes 32 --horizon 800 --skip-sac --grid 3 \
    --out runs/infra/probe_pickplace_scripted_h800.json >> "$LOG" 2>&1
echo "  -> exit=$?" >> "$LOG"
echo "ALL DONE $(date -Is)" >> "$LOG"
