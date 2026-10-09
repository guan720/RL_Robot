#!/usr/bin/env bash
# 档 2 自动发车：等档 1 训练进程退出 + 显存腾出来 -> 起 mix60f60r 微调 + 双向检查点扫描。
# 为什么要有闸门（两道）：
#   1) 档 1 训练一退出，chain_s1_eval / chain_s1_k / chain_s1_kcurve 会接着起评测进程，
#      每个吃 ~8GB 显存。档 2 训练自己吃 ~35GB。A800 80GB 装得下「1 训练 + 3 评测」，
#      但装不下「2 训练 + 3 评测」——所以必须等档 1 训练真的退出，不能按时间猜。
#   2) 数据集必须**收完并落盘**（info.json + 正/反两个 raw.npz），否则 sweep_bidir 的动作分布对照没得比。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
RUN="$MG/runs/pi05_mix60f60r_s2"
# 实测：档 2 训练进程吃 34.8 GB，每个 mg_eval 进程吃 8.1 GB（nvidia-smi compute-apps）。
# 门槛 40 GB = 训练 35 GB + 5 GB 余量；A800 80 GB 装得下「1 训练 + 4 评测」= 67 GB。
NEED_FREE_MIB="${NEED_FREE_MIB:-40000}"

echo "[s2-train] 等档 1 训练退出 ... $(date +%H:%M:%S)"
while pgrep -f "job_name=pi05_rand60_s1" > /dev/null 2>&1; do sleep 20; done
echo "[s2-train] 档 1 训练已退出 $(date +%H:%M:%S)"

for f in "$MG/data/mix60f60r/meta/info.json" "$MG/data/mix60f60r_raw.npz" "$MG/data/mix60f60r_rev_raw.npz"; do
  for _ in $(seq 1 240); do [ -f "$f" ] && break; sleep 15; done
  if [ ! -f "$f" ]; then echo "[s2-train] FATAL 等不到 $f，不发车"; exit 3; fi
done
echo "[s2-train] 数据集就绪 $(date +%H:%M:%S)"

free=0
for _ in $(seq 1 180); do                       # 最多等 45 分钟
  free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
  [ "${free:-0}" -ge "$NEED_FREE_MIB" ] && break
  sleep 15
done
echo "[s2-train] 显存 free=${free}MiB（门槛 ${NEED_FREE_MIB}MiB）-> 准备发车 $(date +%H:%M:%S)"

# ── 发车前预检（2026-10-01 事故换来的）──────────────────────────────────────────
# 事故：run_pi05_s2.sh 里一行续行反斜杠漏写，`exec` 在该行截断，结果训练**悄悄**用了
#       默认 save_freq=2000、默认 job_name、自动时间戳 output_dir，并且**丢掉了 lr=1e-4**
#       （退回配置默认 2.5e-5）。bash -n 查不出来（语法合法），进程也正常跑，
#       只有对比「实际命令行 vs 期望」才能发现 —— 那就是这道预检干的事。
# 规则：dry-run 打印的 [cmd] 里，下面每一项都必须出现；缺任何一项 => 拒绝发车，exit 4。
# 幂等护栏：lerobot-train 见到已存在的 output_dir 会直接 FileExistsError 退出。
# 而 mg_sweep_bidir.sh 一上来就 `mkdir -p "$RUN/sweep_bidir"` —— 所以**上一次失败/被杀的
# 运行会留下一个空 $RUN，把下一次发车堵死**（2026-10-01 01:36 实测吃到）。
# 处理：存在就改名让路，绝不静默复用（复用会让 .done 与检查点步数对不上）。
if [ -e "$RUN" ]; then
  stale="${RUN}.stale_$(date +%Y%m%d_%H%M%S)"
  echo "[s2-train] $RUN 已存在（上次运行的残留）-> 改名让路：$stale"
  mv "$RUN" "$stale"
fi
for stale_meta in "$MG"/runs/pi05_mix60f60r_s2_meta; do
  [ -e "$stale_meta" ] && mv "$stale_meta" "${stale_meta}.stale_$(date +%Y%m%d_%H%M%S)"
done

MUST_HAVE=(
  "--steps=14400"
  "--save_freq=1000"
  "--job_name=pi05_mix60f60r_s2"
  "--output_dir=$RUN"
  "--policy.optimizer_lr=1e-4"
  "--policy.chunk_size=50"
  "--dataset.root=$MG/data/mix60f60r"
)
dry=$(DRY_RUN=1 DATASET=mix60f60r bash code/run_pi05_s2.sh 2>&1 | grep '^\[cmd\]')
miss=0
for need in "${MUST_HAVE[@]}"; do
  case "$dry" in
    *"$need"*) echo "[s2-train][预检] OK   $need" ;;
    *)         echo "[s2-train][预检] MISS $need"; miss=$((miss + 1)) ;;
  esac
done
if [ "$miss" -ne 0 ] || [ -z "$dry" ]; then
  echo "[s2-train] FATAL 预检未通过（缺 $miss 项），**不发车**。实际命令：$dry"
  exit 4
fi
echo "[s2-train] 预检通过 -> 发车 $(date +%H:%M:%S)"

DATASET=mix60f60r bash code/run_pi05_s2.sh > "$MG/logs/train_pi05_s2.log" 2>&1 &
TRAIN_PID=$!
sleep 60
bash code/mg_sweep_bidir.sh "$RUN" > "$MG/logs/sweep_pi05_s2.log" 2>&1 &
SWEEP_PID=$!
echo "[s2-train] train_pid=$TRAIN_PID sweep_pid=$SWEEP_PID"
wait "$TRAIN_PID"; rc=$?
echo "[s2-train] 训练退出 rc=$rc $(date +%H:%M:%S)"
wait "$SWEEP_PID" 2>/dev/null
echo "[s2-train] 全部结束 $(date +%H:%M:%S)"
exit $rc
