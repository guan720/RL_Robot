#!/usr/bin/env bash
# 检查点扫描：每出现一个新检查点就用统一口径评一次，把成功率写进 results.jsonl。
# 目的：在训练还没跑完时就看到「过拟合曲线」，而不是等 3000 步之后一次性开奖。
# 口径固定：固定示范初态（seed=0）+ K=50（π₀.₅ 原生 chunk 执行）+ N 局。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
RUN="${1:-$MG/runs/pi05_fixed10_r1}"
EPISODES="${EPISODES:-5}"
K="${K:-50}"
STEPS_TOTAL="${STEPS_TOTAL:-3000}"
SAVE_FREQ="${SAVE_FREQ:-500}"
DEMO_NPZ="${DEMO_NPZ:-$MG/data/fixed10_raw.npz}"
EVAL_SEED_MODE="${EVAL_SEED_MODE:-fixed}"   # 档 1 起用 random：评测未见位姿
EVAL_SEED="${EVAL_SEED:-0}"                  # 随机模式下的起始 seed（与训练 seed 区间 disjoint）
source "$MG/code/env.sh"
cd "$MG"
mkdir -p "$RUN/sweep"
done_list=("$RUN/sweep/.done")
touch "${done_list[0]}"

wait_ckpt () {  # $1 = step
  local ck
  if [ "$1" -eq "$STEPS_TOTAL" ]; then ck="$RUN/checkpoints/last/pretrained_model"
  else ck=$(printf "%s/checkpoints/%06d/pretrained_model" "$RUN" "$1"); fi
  for _ in $(seq 1 240); do
    [ -f "$ck/model.safetensors" ] && { echo "$ck"; return 0; }
    sleep 15
  done
  echo ""
}

for ((s=SAVE_FREQ; s<=STEPS_TOTAL; s+=SAVE_FREQ)); do
  grep -qx "$s" "${done_list[0]}" && continue
  ck=$(wait_ckpt "$s")
  if [ -z "$ck" ]; then echo "[sweep] step $s 超时未见检查点"; continue; fi
  sleep 20   # 等 safetensors 写完
  out="$RUN/sweep/step_${s}"
  echo "[sweep] === step $s -> $ck ==="
  "$MG_PY" code/mg_eval.py --ckpt "$ck" --episodes "$EPISODES" --n-action-steps "$K" \
      --seed-mode "$EVAL_SEED_MODE" --seed "$EVAL_SEED" \
      --demo-npz "$DEMO_NPZ" --out "$out" 2>&1 \
    | grep -vE "robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation"
  echo "$s" >> "${done_list[0]}"
done
echo "[sweep] 全部完成"
