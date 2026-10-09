#!/usr/bin/env bash
# 档 2c 的**基线补读**：把档 2 联合模型 @last 的反向 TEST 读数从 40 局加到 80 局。
#
# 为什么补：档 2c 要和这个基线做 Fisher 显著性比较。40 局 vs 60 局时，
# 「32.5% → 50%」这种正是我们要判的差距只有 ~50% 的把握达到 p<0.05 ——
# 判不出显著就等于白跑 4 小时的消融。两边都到 80 局才谈得上「显著/不显著」。
# 用的是**同一个** `last` 检查点、**同一批** TEST seed（7000..7019），所以这四读可以合并。
# 目录名用 s2c_jointbase_* 前缀：mg_verdict_s2.py 的档 2 门组只认显式列出的目录，不会误收。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
CK="$MG/runs/pi05_mix60f60r_s2/checkpoints/last/pretrained_model"
NPZ_R="$MG/data/mix60f60r_rev_raw.npz"
NPZ_F="$MG/data/mix60f60r_raw.npz"
NOISE='robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation'
[ -f "$CK/model.safetensors" ] || { echo "[s2c-jb] FATAL 没有联合检查点 $CK"; exit 3; }
for rep in rep3 rep4; do
  out="s2c_jointbase_rev_test_rand20_k10_$rep"
  [ -f "$MG/runs/$out/eval_summary.json" ] && { echo "[s2c-jb] 跳过（已有产物）$out"; continue; }
  echo "[s2c-jb] === 联合 @last 反向 TEST $rep === $(date +%H:%M:%S)"
  "$MG_PY" code/mg_eval.py --ckpt "$CK" --episodes 20 --seed-mode random --seed 7000 \
      --n-action-steps 10 --task-mode reverse --demo-npz "$NPZ_R" \
      --out "$MG/runs/$out" 2>&1 | grep -vE "$NOISE" | grep -E "成功率"
done
# 正向也补两读（同一个检查点、同一批 TEST seed 2000..2019）。
# 为什么：坑 29 定下的房规是「判 50% 的门至少 60~80 局」。反向已经补到 80 局，
# 正向若还停在 40 局，就是**对失败的那个方向用更严的尺子** —— 那门就不公平了。
# 正向原读数 60%（n=40，95% CI 45~75%）其实也压着门，必须补到同局数再说。
for rep in rep3 rep4; do
  out="s2c_jointbase_fwd_test_rand20_k10_$rep"
  [ -f "$MG/runs/$out/eval_summary.json" ] && { echo "[s2c-jb] 跳过（已有产物）$out"; continue; }
  echo "[s2c-jb] === 联合 @last 正向 TEST $rep === $(date +%H:%M:%S)"
  "$MG_PY" code/mg_eval.py --ckpt "$CK" --episodes 20 --seed-mode random --seed 2000 \
      --n-action-steps 10 --task-mode forward --demo-npz "$NPZ_F" \
      --out "$MG/runs/$out" 2>&1 | grep -vE "$NOISE" | grep -E "成功率"
done
date +"%Y-%m-%d %H:%M:%S" > "$MG/runs/pi05_mix60f60r_s2/jointbase.done"
echo "[s2c-jb] done $(date +%H:%M:%S)"
