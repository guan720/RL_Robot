#!/usr/bin/env bash
# 对方 PickPlace 四个臂全程 0% 成功的**只读**诊断（§11 第 14 条第 3 项）。
#
# 目的：分清三种互斥解释，它们给出的下一步完全相反 ——
#   ① 任务太难 / 手写上限本身低        -> 换任务或加拐杖
#   ② 能力没学会（从没把 can 放进篮）  -> 改放置段的学习信号（奖励/示范/采样）
#   ③ 成功判据第二半在挡（放进去了但末端没退开 r_reach<0.6） -> 真实能力被系统性低估，
#                                                              此时开 A/B 比的是噪声
# 判据来自 place_funnel（用 robosuite 自己的 not_in_bin / r_reach，不自己发明阈值）。
#
# 纪律：串行（避免并发污染 sec_per_episode）；只读对方 ckpt；产物全落 runs/infra/。
set -u
cd /workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot
PY=/root/venvs/rlrobot/bin/python
EP=${EP:-32}
LOG=runs/infra/probe_pickplace_diagnosis.log
: > "$LOG"

CKPTS=(
  "sparse100k|runs/20260923_135619_sac_pickplace_state/model_final.zip"
  "shaped100k|runs/20260923_143354_sac_pickplace_state_shaped/model_final.zip"
  "shaped_demo|runs/20260923_152519_sac_pickplace_state_shaped_demo/model_final.zip"
  "shaped_demo10k_bc3k|runs/20260923_203643_sac_pickplace_state_shaped_demo10k_bc3k/model_final.zip"
)

for entry in "${CKPTS[@]}"; do
  tag="${entry%%|*}"; ck="${entry##*|}"
  if [ ! -f "$ck" ]; then echo "[SKIP] 缺 ckpt: $ck" >> "$LOG"; continue; fi
  echo "==================== $tag :: $ck ====================" >> "$LOG"
  date -Is >> "$LOG"
  MUJOCO_GL=egl OMP_NUM_THREADS=1 nice -n 15 "$PY" -u scripts/probe_contact_ceiling.py \
      --task pickplace --episodes "$EP" --horizon 400 --grid 3 \
      --sac-ckpt "$ck" \
      --train-sec-per-round 80 --eval-episodes 120 --min-gain 0.20 \
      --regression-tol 0.20 --eval-every 5 \
      --out "runs/infra/diag_pickplace_${tag}.json" >> "$LOG" 2>&1
  echo "  -> exit=$? out=runs/infra/diag_pickplace_${tag}.json" >> "$LOG"
done
echo "ALL DONE $(date -Is)" >> "$LOG"
