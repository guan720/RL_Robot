#!/usr/bin/env bash
# 档 3 · 三个训练 seed：验证「档 1 的 80% 不依赖单次训练的运气」。
# 设计（STAGE_PLAN 档 3）：同数据（rand60）同超参（7200 步 / bs8 / lr1e-4 / warmup200），
# 只改**训练随机种子** seed ∈ {1000, 2000, 3000}。seed=1000 就是已完成的 `pi05_rand60_s1`
# （K=10 未见 20 局 = 16/20 = 80%），所以本链只需再跑 2000 与 3000 两个。
#
# ⚠️ 术语撞车警告：这里的 1000/2000/3000 是**训练随机种子**（`mg_train.py --seed`，
#    影响初始化/数据洗牌），与**环境初态 seed**（评测用的 2000..2019）完全无关。
#    评测口径一律不变：未见 env seed 2000..2019、20 局、K=10 主指标 + K=50 并列。
#
# 门：三个训练 seed 的 K=10 未见成功率**最差的那个也 ≥ 50%**；报均值 ± std。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
NOISE='robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation'
NEED_FREE_MIB="${NEED_FREE_MIB:-40000}"
STEPS="${STEPS:-7200}"
SAVE_FREQ="${SAVE_FREQ:-500}"
SEEDS="${SEEDS:-2000 3000}"

# 等档 2 训练结束再发车（两个训练进程 = 70 GB，加评测必炸；一张卡只能串行）
JOBPAT="job_name=pi05_mix60f60r[_]s2"
for _ in $(seq 1 960); do pgrep -f "$JOBPAT" > /dev/null 2>&1 && break; sleep 30; done
echo "[s3] 档 2 训练已出现，等它退出 ... $(date +%H:%M:%S)"
while pgrep -f "$JOBPAT" > /dev/null 2>&1; do sleep 30; done
echo "[s3] 档 2 训练已退出 $(date +%H:%M:%S)"

for s in $SEEDS; do
  job="pi05_rand60_s3_seed${s}"
  run="$MG/runs/$job"
  if [ -e "$run" ]; then mv "$run" "${run}.stale_$(date +%Y%m%d_%H%M%S)"; fi
  free=0
  for _ in $(seq 1 180); do
    free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
    [ "${free:-0}" -ge "$NEED_FREE_MIB" ] && break
    sleep 15
  done
  # 发车前预检（README 坑 24：漏一个续行反斜杠就会静默改掉超参）
  dry=$(DRY_RUN=1 DATASET=rand60 JOB="$job" STEPS="$STEPS" SAVE_FREQ="$SAVE_FREQ" SEED="$s" \
        bash code/run_pi05_s1.sh 2>&1 | grep '^\[cmd\]')
  miss=0
  for need in "--steps=$STEPS" "--save_freq=$SAVE_FREQ" "--job_name=$job" "--output_dir=$run" \
              "--policy.optimizer_lr=1e-4" "--seed=$s" "--dataset.root=$MG/data/rand60"; do
    case "$dry" in *"$need"*) ;; *) echo "[s3][预检] MISS $need"; miss=$((miss+1));; esac
  done
  if [ "$miss" -ne 0 ] || [ -z "$dry" ]; then
    echo "[s3] FATAL 预检未通过（缺 $miss 项），跳过 seed=$s。实际命令：$dry"; continue
  fi
  echo "[s3] 预检通过 -> 训练 seed=$s 发车（free=${free}MiB）$(date +%H:%M:%S)"
  DATASET=rand60 JOB="$job" STEPS="$STEPS" SAVE_FREQ="$SAVE_FREQ" SEED="$s" \
    bash code/run_pi05_s1.sh > "$MG/logs/train_${job}.log" 2>&1
  rc=$?
  echo "[s3] 训练 seed=$s 退出 rc=$rc $(date +%H:%M:%S)"
  [ "$rc" -ne 0 ] && { echo "[s3] seed=$s 训练失败，跳过它的评测"; continue; }
  ck="$run/checkpoints/last/pretrained_model"
  for k in 10 50; do
    out="runs/${job}_test_rand20_k${k}"
    echo "[s3] === seed=$s 未见 2000..2019 ×20 K=$k === $(date +%H:%M:%S)"
    "$MG_PY" code/mg_eval.py --ckpt "$ck" --episodes 20 --seed-mode random --seed 2000 \
        --n-action-steps "$k" --demo-npz "$MG/data/rand60_raw.npz" \
        $([ "$k" = "10" ] && echo "--video --max-videos 3") \
        --out "$MG/$out" 2>&1 | grep -vE "$NOISE" | grep -E "成功率|\[saved\]"
  done
done
echo "[s3] 全部完成 $(date +%H:%M:%S)"
