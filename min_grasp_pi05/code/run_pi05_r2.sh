#!/usr/bin/env bash
# π₀.₅ 小数据过拟合（第 2 轮）：加大 batch，看同样 wall-clock 下能不能把成功率从 20% 顶上去。
# r1 结论：batch4 × 3000 步 = 12000 样本(5.2 epoch) -> 20% 成功，loss 0.015，动作分布已收敛到示范量级；
#          K=50 与 K=10 同为 20% -> 残差不是 chunk 开环误差，是欠拟合/采样方差，所以杠杆是「更多样本」。
# r2 用 batch8 × 4000 步 = 32000 样本(14 epoch)，lr 仍 1e-4（openpi 动作专家量级），save_freq 250 便于看曲线。
set -euo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"
cd "$MG"
exec "$MG_PY" code/mg_train.py \
  --policy pi05 \
  --dataset "${DATASET:-fixed10}" \
  --steps "${STEPS:-4000}" \
  --batch-size "${BS:-8}" \
  --num-workers 8 \
  --save-freq "${SAVE_FREQ:-250}" \
  --job-name "pi05_${DATASET:-fixed10}_r2" \
  --out "$MG/runs/pi05_${DATASET:-fixed10}_r2" \
  --extra "policy.optimizer_lr=${LR:-1e-4}"
