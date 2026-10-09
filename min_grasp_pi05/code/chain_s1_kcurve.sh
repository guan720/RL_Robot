#!/usr/bin/env bash
# 档 1 学习曲线（**修正后的口径 K=10**）。
# 为什么要有它：K=50 的 sweep 在 step 1500..3000 读数是 1/10、0/10、1/10、0/10 —— 看着像没在学；
# 同一批 seed 在 K=10 下 step3000 = 5/10。所以「学没学会」必须在能让策略闭环纠偏的 K 下看。
# 口径：seed 3000..3009（与 K=50 sweep 同一批）、10 局、K=10；step3000 已单独测过（5/10），不重复。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
NOISE='robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation'
for s in ${STEPS_LIST:-2000 4000 5000 6000 7200}; do
  # 一律用**显式步数目录**，绝不用 checkpoints/last —— last 是指向最新检查点的**符号链接**，
  # 训练途中会被反复改写（实测 00:54 时 last -> 006000）。原先这里对 step 7200 用了 last，
  # 结果在 00:59 拿到的是 step6000 的检查点，那条「7200 = 6/10」是 6000 的重复读数（已作废）。
  ck=$(printf "%s/runs/pi05_rand60_s1/checkpoints/%06d/pretrained_model" "$MG" "$s")
  for _ in $(seq 1 300); do [ -f "$ck/model.safetensors" ] && break; sleep 20; done
  [ -f "$ck/model.safetensors" ] || { echo "[kcurve] step $s 等不到检查点，跳过"; continue; }
  sleep 20
  echo "[kcurve] === step $s (K=10, seeds 3000..3009, 10 eps) === $(date +%H:%M:%S)"
  "$MG_PY" code/mg_eval.py --ckpt "$ck" --episodes 10 --seed-mode random --seed 3000 \
      --n-action-steps 10 --demo-npz "$MG/data/rand60_raw.npz" \
      --out "$MG/runs/s1_kcurve/step_${s}" 2>&1 | grep -vE "$NOISE" | grep -E "^  ep|成功率|action"
done
echo "[kcurve] done $(date +%H:%M:%S)"
