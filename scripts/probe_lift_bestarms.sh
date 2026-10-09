#!/usr/bin/env bash
# 对方 Lift 课程阶梯「当前最好臂」的独立复测（阶段 4 / §12.11-S）。
#
# 为什么要复测，而不是直接采信对方的数字
# ------------------------------------------------------------------
# runs/20260924_095928_sac_lift_demo5k_bc3k_savebest/result.json 里同时写着两个互相矛盾的数：
#   · curve[60000]      : episode_success 0.4 (2/5), mean_reward 92.5
#   · eval_final        : episode_success 1.0 (5/5), mean_reward 88.7
#   · eval_best         : key_success 0.4 (2/5)  ← model_best.zip 是按这个选的
# 同一个 ckpt 家族、同一套评测代码，5 局口径给出 0.4 和 1.0 两个答案。三种解释互斥：
#   ① 5 局太少，0.4 与 1.0 都只是二项噪声（p=0.5 时 5 局的 MDE≈±44 点）；
#   ② eval_final 与 curve 的出题不同（placement_initializer 未播种，§12.11 已实测）；
#   ③ model_best/model_final 不是同一份权重（save-best 在 40k 点存的）。
# 这三条对「Lift 到底学会没有」给出的下一步完全不同：①要把评测局数抬上去，
# ②要把出题钉死，③要说清 save-best 选的是噪声。冻结探针一次跑完能把三条分开：
# 同 seed、同 horizon、物体钉死、播种自校验，并同时报 success_rate 与
# success_rate_grasp_verified（flick 检查，Lift 的 _check_success 只看 cube 高度）。
#
# 口径：episodes=32（与 PickPlace 四臂诊断一致，可跨任务比）；两 ckpt 用同一批 seed ⇒
#       可逐题配对；手写参照臂照跑，用于 rise 阈值标定（否则失败标签退兜底值）。
# 纪律：串行，nice -n 15，不碰对方 run 目录，产物落 runs/infra/。
set -u
cd /workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot
PY=/root/venvs/rlrobot/bin/python
RUN=runs/20260924_095928_sac_lift_demo5k_bc3k_savebest
LOG=runs/infra/probe_lift_bestarms.log
: > "$LOG"

for CKPT in model_final model_best; do
  echo "==================== lift 32 局 · ${CKPT}.zip ====================" >> "$LOG"
  date -Is >> "$LOG"
  MUJOCO_GL=egl OMP_NUM_THREADS=1 nice -n 15 "$PY" -u scripts/probe_contact_ceiling.py \
      --task lift --episodes 32 --horizon 300 --grid 3 \
      --sac-ckpt "${RUN}/${CKPT}.zip" \
      --out "runs/infra/diag_lift_savebest_${CKPT}32.json" >> "$LOG" 2>&1
  echo "  -> exit=$?" >> "$LOG"
done
echo "ALL DONE $(date -Is)" >> "$LOG"
