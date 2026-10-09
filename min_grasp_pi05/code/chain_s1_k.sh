#!/usr/bin/env bash
# 档 1 补充链：**执行节奏 K 的一等公民扫描**（2026-09-30 实测触发）。
# 触发原因：同一个 step-3000 检查点、同一批未见 seed 3000..3009，
#           K=50 -> 0/10，K=10 -> 5/10。K 不是「档 4 的细节」，是决定成败的一等变量。
# 顺序：等训练退出 -> 等 K=50 定版链退出 -> 等 sweep 退出（避免 3 个评测同时压显存）->
#       K=10 测试 -> K=10 回归 -> K=25 测试 -> K=1 测试（最慢，放最后）。
# 口径：局数 20（房规：≥20 才有定论），seed 区间与 chain_s1_eval.sh 完全一致，只改 K。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
while pgrep -f "job_name=pi05_rand60_s1" > /dev/null 2>&1; do sleep 20; done
while pgrep -f "code/chain_s1_eval" > /dev/null 2>&1; do sleep 20; done
# 守卫必须写**完整脚本名**：原先是 pgrep -f "mg_sweep"，它同样匹配 mg_sweep_bidir.sh
# （档 2 的双向扫描，要跑 8 小时）=> 本链会被一个不相干的进程永久堵死（2026-10-01 01:41 实测）。
while pgrep -f "code/mg_sweep\\.sh" > /dev/null 2>&1; do sleep 15; done
sleep 10
CK="$MG/runs/pi05_rand60_s1/checkpoints/last/pretrained_model"
NOISE='robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation'

run_eval () {  # $1=K $2=episodes $3=seed-mode $4=seed $5=out $6=tag
  echo "[s1-k] === $6 K=$1 eps=$2 seeds=$3/$4 === $(date +%H:%M:%S)"
  "$MG_PY" code/mg_eval.py --ckpt "$CK" --episodes "$2" --seed-mode "$3" --seed "$4" \
      --n-action-steps "$1" --demo-npz "$MG/data/rand60_raw.npz" \
      --out "$MG/runs/$5" 2>&1 | grep -vE "$NOISE"
}

run_eval 10 20 random 2000 s1_gate_test_rand20_k10       "TEST unseen 2000..2019"
run_eval 10 20 fixed  0    s1_gate_regression_fixed20_k10 "REGRESSION fixed seed 0"
run_eval 25 20 random 2000 s1_k25_test_rand20            "TEST unseen (K sweep)"
run_eval 1  20 random 2000 s1_k1_test_rand20             "TEST unseen (K sweep, 退化对照)"
echo "[s1-k] done $(date +%H:%M:%S)"
