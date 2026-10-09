#!/usr/bin/env bash
# 档 2 · 正反向联合微调：在 mix60f60r（正向 60 = rand60 逐比特同源 + 反向 60）上微调 π₀.₅。
# 与档 1 的唯一差别 = 数据里多了第二个 task；超参、batch、lr、warmup、K 口径全部不动。
# 步数按**等 epoch** 配：档 1 = 7200 步 / 14415 帧 = 4.0 epoch；
# 档 2 混合集约 30k 帧，等 epoch 就是 ~14400 步。save_freq 1000（检查点多 = 可以提前收）。
set -euo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"
cd "$MG"
DATASET="${DATASET:-mix60f60r}"
exec "$MG_PY" code/mg_train.py \
  --policy pi05 \
  --dataset "$DATASET" \
  --steps "${STEPS:-14400}" \
  --batch-size "${BS:-8}" \
  --num-workers 8 \
  --save-freq "${SAVE_FREQ:-1000}" \
  --job-name "pi05_${DATASET}_s2" \
  --out "$MG/runs/pi05_${DATASET}_s2" \
  --extra "policy.optimizer_lr=${LR:-1e-4}" \
  --extra "policy.scheduler_warmup_steps=200" \
  --seed "${SEED:-1000}" \
  ${DRY_RUN:+--dry-run}
