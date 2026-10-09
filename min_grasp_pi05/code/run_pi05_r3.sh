#!/usr/bin/env bash
# π₀.₅ 小数据过拟合（第 3 轮）：拉长训练轮数。
# 依据：ACT 在 fixed10 上训到 70 个 epoch 才 100%；r1/r2 只给了 π₀.₅ 5 个 epoch 上下，
#       明显欠训练（r2 在 1.18 epoch 就到 25%，曲线还在往上走）。
# r3 = fixed30n / batch8 / 10000 步 = 11.8 epoch，lr 1e-4，cosine 跨满 10000 步，save_freq 1000。
set -euo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"
cd "$MG"
exec "$MG_PY" code/mg_train.py \
  --policy pi05 \
  --dataset "${DATASET:-fixed30n}" \
  --steps "${STEPS:-8000}" \
  --batch-size "${BS:-8}" \
  --num-workers 8 \
  --save-freq "${SAVE_FREQ:-1000}" \
  --job-name "pi05_${DATASET:-fixed30n}_r3" \
  --out "$MG/runs/pi05_${DATASET:-fixed30n}_r3" \
  --extra "policy.optimizer_lr=${LR:-1e-4}" \
  --extra "policy.scheduler_warmup_steps=200"
