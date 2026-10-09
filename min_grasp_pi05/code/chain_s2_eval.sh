#!/usr/bin/env bash
# 档 2 关门评测（训练退出后自动跑，取 checkpoints/last）。
# 口径：K=10 为主 —— 档 1 实测同一检查点 K=50 -> 0/10、K=10 -> 5/10（README 坑 17），
#       所以「会不会」必须在能让策略闭环纠偏的 K 下判；K=50 只作为「标准 chunk 执行」的对照读数。
# 局数：≥20（房规）。seed 区间：正向 test 2000..2019 / 反向 test 7000..7019 /
#       正向 train 对照 1000..1009 / 反向 train 对照 5000..5009 / 正向固定初态回归 seed 0。
# 上界：不在本链里测 —— 已由 code/run_ceilings_s2.sh 提前钉在 runs/s2_ceiling_*（训练前就测，
#       免得事后拿「专家也做不到」当挡箭牌）。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
RUN="$MG/runs/pi05_mix60f60r_s2"
NOISE='robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation'
NPZ_F="$MG/data/mix60f60r_raw.npz"
NPZ_R="$MG/data/mix60f60r_rev_raw.npz"

# 完成判据 = **last 检查点已落盘** ∧ 训练进程与双向扫描都已退出。三者缺一就回去继续等，
# 等满 MAX_WAIT_TRIES 轮（960×30 s = 8 h）才 FATAL。
# 为什么不再用「等出现 -> 等消失」的单次 pgrep 翻转：
#   2026-10-01 01:30 吃过一次（pgrep 永不匹配 -> 循环立刻退出 -> 提前醒来 FATAL），
#   01:36 又吃了第二次，而且更隐蔽 —— 一个**同名残留训练进程**（run_pi05_s2.sh 断行事故那一发）
#   被匹配到、几秒后自己退出，本链于是判「训练已退出」-> 没有 last 检查点 -> FATAL 自杀。
#   后果是「训练 01:39 正常在跑，但档 2 的关门评测没人收」：等 6.6 小时跑完，门是空的。
#   单次 pgrep 翻转证明不了任何事；磁盘上的检查点 + 生产者全静默才是证据。
JOBPAT="job_name=pi05_mix60f60r[_]s2"
CK="$RUN/checkpoints/last/pretrained_model"
ok=0
for _ in $(seq 1 "${MAX_WAIT_TRIES:-960}"); do
  if [ -f "$CK/model.safetensors" ] \
     && ! pgrep -f "$JOBPAT" > /dev/null 2>&1 \
     && ! pgrep -f "mg_sweep_bidir" > /dev/null 2>&1; then ok=1; break; fi
  sleep 30
done
[ "$ok" = "1" ] || { echo "[s2-gate] FATAL 等满 ${MAX_WAIT_TRIES:-960} 轮仍没有 last 检查点：$CK"; exit 3; }
sleep 15
echo "[s2-gate] 训练/扫描已静默，开始关门评测 $(date +%H:%M:%S)"
# last 是符号链接，训练途中随每次 save 前移；把**实际指向的步数**打进日志，免得读数张冠李戴
# （档 1 的 chain_s1_kcurve.sh 就因此把 006000 的读数当成了 7200，那一格作废重跑）。
echo "[s2-gate] last 检查点 -> $(readlink -f "$RUN/checkpoints/last")"

run_eval () {  # $1=task-mode $2=K $3=eps $4=seed-mode $5=seed $6=out $7=tag $8=video(0/1)
  echo "[s2-gate] === $7 ($1 K=$2 eps=$3 seeds=$4/$5) === $(date +%H:%M:%S)"
  local extra=()
  [ "$8" = "1" ] && extra=(--video --max-videos 3)
  local npz="$NPZ_F"; [ "$1" = "reverse" ] && npz="$NPZ_R"
  "$MG_PY" code/mg_eval.py --ckpt "$CK" --episodes "$3" --seed-mode "$4" --seed "$5" \
      --n-action-steps "$2" --task-mode "$1" --demo-npz "$npz" "${extra[@]}" \
      --out "$MG/runs/$6" 2>&1 | grep -vE "$NOISE" | grep -E "^  ep|成功率|policy mean|\[policy\]"
}

run_eval forward 10 20 random 2000 s2_gate_fwd_test_rand20_k10  "TEST 正向 未见" 1
run_eval reverse 10 20 random 7000 s2_gate_rev_test_rand20_k10  "TEST 反向 未见" 1
run_eval forward 10 10 random 1000 s2_gate_fwd_control_train10_k10 "CONTROL 正向 训练 seed" 0
run_eval reverse 10 10 random 5000 s2_gate_rev_control_train10_k10 "CONTROL 反向 训练 seed" 0
run_eval forward 10 20 fixed  0    s2_gate_fwd_regression_fixed20_k10 "REGRESSION 正向 档 0 固定初态" 0
run_eval forward 50 20 random 2000 s2_gate_fwd_test_rand20_k50 "CADENCE 正向 K=50 对照" 0
run_eval reverse 50 20 random 7000 s2_gate_rev_test_rand20_k50 "CADENCE 反向 K=50 对照" 0
echo "[s2-gate] done $(date +%H:%M:%S)"
