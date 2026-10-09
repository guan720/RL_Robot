#!/usr/bin/env bash
# 档 2c · 反向单任务 val 扫描：每出一个检查点，评 EPISODES 局反向 val（默认 seed 8000..，20 局）。
#
# ⚠️ val 从档 2 的 10 局加到 **20 局**，这是档 2 交出来的学费：
#   档 2 用 10 局 val 选点，选出 011000（val rev 5/10 = 50%），TEST 实测只有 **26.7%**（3 读 60 局）；
#   而 `last` 的 val rev 只有 2/10 = 20%，TEST 却有 32.5%（2 读 40 局）。
#   val 与 TEST **反序** ⇒ n=10 在 p≈0.3 时 1σ≈15 pp，「挑 val 最大值」= 在纯噪声里挑峰。
#   n=20 把 1σ 压到 ~10 pp；仍然不够精 ⇒ 档 2c 的**主读数改用 `last`**（与档 2 原门同规则、
#   等 epoch），val 曲线只当「学习趋势」看，不当选点依据。选点读数只作并列参考。
#
# 不改 mg_sweep_bidir.sh（它服务的是双向联合模型，口径写死在注释里），单独一个文件互不干扰。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
RUN="${1:-$MG/runs/pi05_rev60_s2c}"
EPISODES="${EPISODES:-20}"
K="${K:-10}"
STEPS_TOTAL="${STEPS_TOTAL:-7600}"
SAVE_FREQ="${SAVE_FREQ:-1000}"
REV_SEED="${REV_SEED:-8000}"
DEMO_REV="${DEMO_REV:-$MG/data/mix60f60r_rev_raw.npz}"
SUB="${SUB:-sweep_rev}"
source "$MG/code/env.sh"; cd "$MG"
mkdir -p "$RUN/$SUB"
DONE="$RUN/$SUB/.done"; touch "$DONE"
NOISE='robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation'
MIN_FREE_MIB="${MIN_FREE_MIB:-14000}"

wait_gpu () {
  local free
  for _ in $(seq 1 240); do
    free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
    [ "${free:-0}" -ge "$MIN_FREE_MIB" ] && return 0
    echo "[sweepR] 显存只有 ${free}MiB（< ${MIN_FREE_MIB}MiB），等 15 s ..."
    sleep 15
  done
  return 0
}

# 坑 38（2026-10-02 档 2e 实测吃到）：`last` **不是**「训练结束才出现的软链」，而是 lerobot
# 每次 save 都重指的软链。原实现只检查 `$ck/model.safetensors` 存在，于是在训练还没到终点时
# `last -> 020000` 就已经存在 ⇒ 拿 020000 的权重冒充 step 22000，还把 22000 写进 .done
# 让它永远不被重测。档 2e 就是这么把同一份权重读成 6/20 和 10/20 两格曲线的。
# 修法：终点格必须**先核对软链指向 == %06d(STEPS_TOTAL)**，再认权重文件；核对不上就继续等。
# 另：STEPS_TOTAL 不是 SAVE_FREQ 整数倍时（档 2 的 14400、档 2c 的 7600）循环根本走不到终点格，
# 所以那两档的历史曲线没有终点格 —— 这是「没测」，不是「测错了」，别混为一谈。
wait_ckpt () {
  local ck want
  want=$(printf "%06d" "$1")
  ck=$(printf "%s/checkpoints/%s/pretrained_model" "$RUN" "$want")
  for _ in $(seq 1 300); do
    [ -f "$ck/model.safetensors" ] && { echo "$ck"; return 0; }
    sleep 15
  done
  echo ""
}

# 终点格单独等：既接受 %06d 目录，也接受 `last`——但**必须**证明 last 指向的就是它。
wait_last_ckpt () {
  local want ck rl
  want=$(printf "%06d" "$1")
  for _ in $(seq 1 300); do
    ck=$(printf "%s/checkpoints/%s/pretrained_model" "$RUN" "$want")
    if [ -f "$ck/model.safetensors" ]; then echo "$ck"; return 0; fi
    rl=$(readlink "$RUN/checkpoints/last" 2>/dev/null || echo "")
    if [ "$rl" = "$want" ] && [ -f "$RUN/checkpoints/last/pretrained_model/model.safetensors" ]; then
      echo "[sweepR] last -> $want 已就位（坑 38 守卫通过）" >&2
      echo "$RUN/checkpoints/last/pretrained_model"; return 0
    fi
    echo "[sweepR] 等终点格 $want（当前 last -> ${rl:-无}）... $(date +%H:%M:%S)" >&2
    sleep 15
  done
  echo ""
}

for ((s=SAVE_FREQ; s<=STEPS_TOTAL; s+=SAVE_FREQ)); do
  grep -qx "$s" "$DONE" && continue
  if [ "$s" -eq "$STEPS_TOTAL" ]; then ck=$(wait_last_ckpt "$s"); else ck=$(wait_ckpt "$s"); fi
  [ -z "$ck" ] && { echo "[sweepR] step $s 超时未见检查点"; continue; }
  sleep 20
  wait_gpu
  # 出处必须打到日志里（坑 30）：这一格到底读的哪个权重目录，事后要能查
  echo "[sweepR] === step $s REVERSE val K=$K eps=$EPISODES seeds ${REV_SEED}.. -> ckpt=$ck === $(date +%H:%M:%S)"
  "$MG_PY" code/mg_eval.py --ckpt "$ck" --episodes "$EPISODES" --n-action-steps "$K" \
      --seed-mode random --seed "$REV_SEED" --task-mode reverse --demo-npz "$DEMO_REV" \
      --out "$RUN/$SUB/step_${s}_rev" 2>&1 | grep -vE "$NOISE" | grep -E "^  ep|成功率"
  echo "$s" >> "$DONE"
done
echo "[sweepR] 全部完成"
