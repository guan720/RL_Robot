#!/usr/bin/env bash
# 档 2 双向检查点扫描：每出一个新检查点，正向 / 反向各评一次。
# 口径（与 STAGE_PLAN 档 2 一致）：K=10 为主（档 1 实测：K=50 会把会做的策略测成 0%），
# 正向 val seed 3000..3009、反向 val seed 8000..8009，各 10 局，都与训练 seed 区间不相交。
# 不改 mg_sweep.sh（它正在为档 1 跑），单独一个文件，互不干扰。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
RUN="${1:-$MG/runs/pi05_mix60f60r_s2}"
EPISODES="${EPISODES:-10}"
K="${K:-10}"
STEPS_TOTAL="${STEPS_TOTAL:-14400}"
SAVE_FREQ="${SAVE_FREQ:-1000}"
FWD_SEED="${FWD_SEED:-3000}"
REV_SEED="${REV_SEED:-8000}"
DEMO_FWD="${DEMO_FWD:-$MG/data/mix60f60r_raw.npz}"
DEMO_REV="${DEMO_REV:-$MG/data/mix60f60r_rev_raw.npz}"
source "$MG/code/env.sh"; cd "$MG"
mkdir -p "$RUN/sweep_bidir"
DONE="$RUN/sweep_bidir/.done"; touch "$DONE"
NOISE='robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation'

# 显存闸门：档 1 的三条评测链可能同时在跑（每个 mg_eval ≈8.1 GB），
# 再叠一个就是 4×8+35=67 GB。低于 MIN_FREE_MIB 就先等，别把别人的评测挤 OOM。
MIN_FREE_MIB="${MIN_FREE_MIB:-14000}"
wait_gpu () {
  local free
  for _ in $(seq 1 240); do                       # 最多等 60 分钟
    free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
    [ "${free:-0}" -ge "$MIN_FREE_MIB" ] && return 0
    echo "[sweep2] 显存只有 ${free}MiB（< ${MIN_FREE_MIB}MiB），等 15 s ..."
    sleep 15
  done
  return 0
}

# 坑 38（2026-10-02 档 2e 实测吃到，本文件同一处 bug 一并修）：lerobot 的 `checkpoints/last`
# 是**每次 save 都重指的软链**，不是「训练结束才出现」。原实现只检查权重文件存在，于是训练没到
# 终点时 `last` 已指向上一个检查点 ⇒ 拿上一个检查点的权重冒充终点格，还把它写进 .done 永不重测。
# 修法：终点格先核对 `readlink last` == %06d(STEPS_TOTAL) 才认；核对不上就继续等。
wait_ckpt () {
  local ck
  ck=$(printf "%s/checkpoints/%06d/pretrained_model" "$RUN" "$1")
  for _ in $(seq 1 300); do [ -f "$ck/model.safetensors" ] && { echo "$ck"; return 0; }; sleep 15; done
  echo ""
}

wait_last_ckpt () {
  local want ck rl
  want=$(printf "%06d" "$1")
  for _ in $(seq 1 300); do
    ck=$(printf "%s/checkpoints/%s/pretrained_model" "$RUN" "$want")
    if [ -f "$ck/model.safetensors" ]; then echo "$ck"; return 0; fi
    rl=$(readlink "$RUN/checkpoints/last" 2>/dev/null || echo "")
    if [ "$rl" = "$want" ] && [ -f "$RUN/checkpoints/last/pretrained_model/model.safetensors" ]; then
      echo "[sweep2] last -> $want 已就位（坑 38 守卫通过）" >&2
      echo "$RUN/checkpoints/last/pretrained_model"; return 0
    fi
    echo "[sweep2] 等终点格 $want（当前 last -> ${rl:-无}）... $(date +%H:%M:%S)" >&2
    sleep 15
  done
  echo ""
}

for ((s=SAVE_FREQ; s<=STEPS_TOTAL; s+=SAVE_FREQ)); do
  grep -qx "$s" "$DONE" && continue
  if [ "$s" -eq "$STEPS_TOTAL" ]; then ck=$(wait_last_ckpt "$s"); else ck=$(wait_ckpt "$s"); fi
  [ -z "$ck" ] && { echo "[sweep2] step $s 超时未见检查点"; continue; }
  sleep 20
  wait_gpu
  # 出处打进日志（坑 30）：这一格读的到底是哪个权重目录，事后必须能查
  echo "[sweep2] === step $s FORWARD K=$K seeds ${FWD_SEED}.. ckpt=$ck === $(date +%H:%M:%S)"
  "$MG_PY" code/mg_eval.py --ckpt "$ck" --episodes "$EPISODES" --n-action-steps "$K" \
      --seed-mode random --seed "$FWD_SEED" --task-mode forward --demo-npz "$DEMO_FWD" \
      --out "$RUN/sweep_bidir/step_${s}_fwd" 2>&1 | grep -vE "$NOISE" | grep -E "^  ep|成功率"
  echo "[sweep2] === step $s REVERSE K=$K seeds ${REV_SEED}.. === $(date +%H:%M:%S)"
  "$MG_PY" code/mg_eval.py --ckpt "$ck" --episodes "$EPISODES" --n-action-steps "$K" \
      --seed-mode random --seed "$REV_SEED" --task-mode reverse --demo-npz "$DEMO_REV" \
      --out "$RUN/sweep_bidir/step_${s}_rev" 2>&1 | grep -vE "$NOISE" | grep -E "^  ep|成功率"
  echo "$s" >> "$DONE"
done
echo "[sweep2] 全部完成"
