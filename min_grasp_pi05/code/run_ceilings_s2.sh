#!/usr/bin/env bash
# 档 2 的「上界先测」：门是「正、反各 ≥50%（未见 seed ×20）」，但反向可行域小、
# 抓取是双稳态（夹爪开口 0.049 ≈ can 直径 0.050），专家自己都不是 100%。
# 所以在训练之前先把同一批 seed 的专家上界钉下来 —— 否则 50% 这个门没有解释力。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
NOISE='robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation'
run () {  # $1=mode $2=eps $3=seed $4=noise $5=out
  echo "[ceiling] === $1 eps=$2 seed=$3 sigma=$4 === $(date +%H:%M:%S)"
  "$MG_PY" code/mg_ceiling.py --task-mode "$1" --episodes "$2" --seed-mode random --seed "$3" \
      --noise "$4" --out "$MG/runs/$5" 2>&1 | grep -vE "$NOISE" | grep -E "^  ep|专家上界"
}
run reverse 20 7000 0.05 s2_ceiling_rev_test20_n05
run reverse 20 7000 0.00 s2_ceiling_rev_test20_n00
run forward 20 2000 0.05 s2_ceiling_fwd_test20_n05
run forward 20 2000 0.00 s2_ceiling_fwd_test20_n00
run reverse 10 8000 0.05 s2_ceiling_rev_val10_n05
run forward 10 3000 0.05 s2_ceiling_fwd_val10_n05
echo "[ceiling] all done $(date +%H:%M:%S)"
