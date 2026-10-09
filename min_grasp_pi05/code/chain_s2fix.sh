#!/usr/bin/env bash
# 档 2 修正关门：把**关门检查点**从 `last`(=014400) 换成 **val 选出来的 011000**，重读一次 TEST。
#
# 为什么这一发是合法的、不是「挑到好看为止」：
#   1) 选点只看 val（正向 seed 3000..3009 / 反向 seed 8000..8009），规则在 code/mg_select_ckpt.py
#      里写死并落盘成 runs/pi05_mix60f60r_s2/ckpt_selection.json；
#   2) 双向 val **同时**在 11000 达峰（fwd 8/10 + rev 5/10 = 13，次高 11），不是靠单支噪声挑出来的；
#   3) TEST（正向 2000..2019 / 反向 7000..7019）在本次修正前**只被 last 读过**，011000 的 TEST
#      读数本链跑完即为唯一一次，跑完不再换规则重选。
#   4) 协议改动写进 STAGE_PLAN 档 2：以后所有档关门一律用 val 选点，不用 last。
#
# 局数：反向 3 次读数 × 20 = 60 局（1σ≈6.5 pp）。原来 2 次读数把 30%/35% 合成 32.5%，
#       门是 50%；若修正后真值在 45~55%，2 次读数判不了，所以反向多跑一次。
# 正向 2 次读数 × 20 = 40 局（与门 3 的档 1 基线同口径：3 次读数合并 70%）。
# 对照组同检查点各 10 局：判「换成 011000 后是否出现训练 seed 记忆」（Fisher，不是拍脑袋 10 pp）。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
RUN="$MG/runs/pi05_mix60f60r_s2"
NPZ_F="$MG/data/mix60f60r_raw.npz"
NPZ_R="$MG/data/mix60f60r_rev_raw.npz"
NOISE='robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation'
K="${K:-10}"
MIN_FREE_MIB="${MIN_FREE_MIB:-14000}"
MARK="$RUN/s2fix.done"

# ── 选点（只读 val，落盘可审计）──────────────────────────────────────────
"$MG_PY" code/mg_select_ckpt.py --run "$RUN" --sweep sweep_bidir --direction both || {
  echo "[s2fix] FATAL 选点失败，不猜检查点"; exit 3; }
SEL=$("$MG_PY" -c "import json;print(json.load(open('$RUN/ckpt_selection.json'))['selected_step'])")
CK=$(printf "%s/checkpoints/%06d/pretrained_model" "$RUN" "$SEL")
[ -f "$CK/model.safetensors" ] || { echo "[s2fix] FATAL 选出的检查点不存在：$CK"; exit 3; }
echo "[s2fix] val 选点 = step $SEL -> $CK   $(date +%H:%M:%S)"

wait_gpu () {
  local free
  for _ in $(seq 1 240); do
    free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
    [ "${free:-0}" -ge "$MIN_FREE_MIB" ] && return 0
    echo "[s2fix] 显存只有 ${free}MiB（< ${MIN_FREE_MIB}MiB），等 15 s ..."
    sleep 15
  done
  return 0
}

run_eval () {  # $1=task-mode $2=eps $3=seed-mode $4=seed $5=out $6=tag $7=video(0/1)
  local out="$5"
  [ -f "$MG/runs/$out/eval_summary.json" ] && { echo "[s2fix] 跳过（已有产物）$out"; return 0; }
  echo "[s2fix] === $6 ($1 K=$K eps=$2 seeds=$3/$4) -> runs/$out === $(date +%H:%M:%S)"
  wait_gpu
  local extra=() npz="$NPZ_F"
  [ "$1" = "reverse" ] && npz="$NPZ_R"
  [ "$7" = "1" ] && extra=(--video --max-videos 3)
  "$MG_PY" code/mg_eval.py --ckpt "$CK" --episodes "$2" --seed-mode "$3" --seed "$4" \
      --n-action-steps "$K" --task-mode "$1" --demo-npz "$npz" "${extra[@]}" \
      --out "$MG/runs/$out" 2>&1 | grep -vE "$NOISE" | grep -E "^  ep|成功率|policy mean"
}

# 主读数：反向未见 3 次（门 2 就是这一格）
run_eval reverse 20 random 7000 s2fix_rev_test_rand20_k10      "TEST 反向 未见 rep1" 1
run_eval reverse 20 random 7000 s2fix_rev_test_rand20_k10_rep2 "TEST 反向 未见 rep2" 0
run_eval reverse 20 random 7000 s2fix_rev_test_rand20_k10_rep3 "TEST 反向 未见 rep3" 0
# 门 3 的同检查点正向读数
run_eval forward 20 random 2000 s2fix_fwd_test_rand20_k10      "TEST 正向 未见 rep1" 1
run_eval forward 20 random 2000 s2fix_fwd_test_rand20_k10_rep2 "TEST 正向 未见 rep2" 0
# 记忆对照（同检查点，Fisher 判显著性）
run_eval reverse 10 random 5000 s2fix_rev_control_train10_k10 "CTRL 反向 训练 seed" 0
run_eval forward 10 random 1000 s2fix_fwd_control_train10_k10 "CTRL 正向 训练 seed" 0

# 失败几何：011000 的反向失败局还是不是「空合爪」（与 last 的 48% 对比）
echo "[s2fix] === 反向失败几何 (rep1) === $(date +%H:%M:%S)"
"$MG_PY" code/mg_diag_miss.py "$MG/runs/s2fix_rev_test_rand20_k10" --demo-npz "$NPZ_R" \
    --out "$MG/runs/_diag/miss_s2fix_rev_test" 2>&1 | grep -vE "$NOISE" | tail -40

echo "[s2fix] === 重出判定 === $(date +%H:%M:%S)"
"$MG_PY" code/mg_verdict_s2.py > "$MG/runs/S2_VERDICT.md" 2>&1
date +"%Y-%m-%d %H:%M:%S step=$SEL" > "$MARK"
echo "[s2fix] done $(date +%H:%M:%S)  标记 -> $MARK"
