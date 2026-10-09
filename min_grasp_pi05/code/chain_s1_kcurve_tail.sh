#!/usr/bin/env bash
# 档 1 学习曲线的**尾巴**：补 6500 / 7000 / 7200 三个点（K=10，val seed 3000..3009，10 局）。
# 为什么单独一条链：chain_s1_kcurve.sh 里 step7200 那格错用了 checkpoints/last（符号链接，
# 训练途中指向 006000），所以「7200 = 6/10」是 6000 的重复读数，作废。
# 这三个点回答的是**预案选择**问题：K=10 的 val 曲线 5000→6000 都是 6/10，看着像平台；
# 若 6500/7000/7200 仍平 => 「继续训练」这条预案收益低，应该直接走「数据翻倍到 120 条」。
# 排在 chain_s1_k（定版门）之后跑，不跟门抢显存/算力。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
NOISE='robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation'
while pgrep -f "job_name=pi05_rand60_s1" > /dev/null 2>&1; do sleep 30; done
while pgrep -f "code/chain_s1_k.sh" > /dev/null 2>&1; do sleep 30; done
while pgrep -f "code/chain_s1_eval" > /dev/null 2>&1; do sleep 30; done
sleep 10
for s in 6500 7000 7200; do
  ck=$(printf "%s/runs/pi05_rand60_s1/checkpoints/%06d/pretrained_model" "$MG" "$s")
  [ -f "$ck/model.safetensors" ] || { echo "[ktail] step $s 没有检查点，跳过"; continue; }
  echo "[ktail] === step $s (K=10, val seeds 3000..3009, 10 eps) === $(date +%H:%M:%S)"
  "$MG_PY" code/mg_eval.py --ckpt "$ck" --episodes 10 --seed-mode random --seed 3000 \
      --n-action-steps 10 --demo-npz "$MG/data/rand60_raw.npz" \
      --out "$MG/runs/s1_kcurve/step_${s}" 2>&1 | grep -vE "$NOISE" | grep -E "^  ep|成功率"
done
echo "[ktail] done $(date +%H:%M:%S)"
