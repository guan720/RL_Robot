#!/usr/bin/env bash
# 档 1 主判定门的**复跑**：同一检查点、同一批未见 seed、同一 K，再跑 20 局。
# 为什么必须复跑：README 坑 20 —— 评测端没钉 RNG，π₀.₅ 的 flow-matching 每局从噪声采样，
# 实测同一 (ckpt, seed, K) 两次跑逐局结果会变（seed2000@K=10 一次失败一次成功）。
# 所以「16/20 = 80%」这个头条数字需要第二个独立读数来界定重跑噪声；
# 两次读数一起报，比单次读数诚实得多。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
NOISE='robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation'
CK="$MG/runs/pi05_rand60_s1/checkpoints/last/pretrained_model"
while pgrep -f "code/chain_s1_k\.sh" > /dev/null 2>&1; do sleep 20; done
sleep 10
for rep in 2 3; do
  echo "[s1-confirm] === 复跑 #$rep：未见 2000..2019 ×20 K=10 === $(date +%H:%M:%S)"
  "$MG_PY" code/mg_eval.py --ckpt "$CK" --episodes 20 --seed-mode random --seed 2000 \
      --n-action-steps 10 --demo-npz "$MG/data/rand60_raw.npz" \
      --out "$MG/runs/s1_gate_test_rand20_k10_rep${rep}" 2>&1 | grep -vE "$NOISE" | grep -E "^  ep|成功率"
done
echo "[s1-confirm] done $(date +%H:%M:%S)"
