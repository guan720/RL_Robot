#!/usr/bin/env bash
# π₀.₅ 小数据过拟合（第 1 轮）：全参数微调，10 条固定初态示范，同步 BC。
# lr 用 openpi 动作专家的 1e-4（默认 preset 是给 paligemma 的 2.5e-5）——本轮的成功判据就是「过拟合」，
# 所以宁可 lr 偏高；warmup 100 + grad_clip 1.0 兜底。
set -euo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"
cd "$MG"
exec "$MG_PY" code/mg_train.py \
  --policy pi05 \
  --dataset fixed10 \
  --steps "${STEPS:-3000}" \
  --batch-size "${BS:-4}" \
  --num-workers 8 \
  --save-freq "${SAVE_FREQ:-500}" \
  --job-name pi05_fixed10 \
  --out "$MG/runs/pi05_fixed10_r1" \
  --extra "policy.optimizer_lr=${LR:-1e-4}"
