#!/usr/bin/env bash
# 档 7A · batch / gradient-checkpointing 计时探针的发车链（只做代价测量，不出判定）
#
# 为什么排这一档：档 3r 三个 seed 同数据同超参等 epoch，反向放宽口径 41.2/68.8/80.0 ⇒
# run 间极差 38.8 pp（坑 57）。任何 n=1 的配方比较在这个方差下都出不了结论，
# 所以第一件事是**把方差压下去**；头号嫌疑 = batch 8 太小。
# 但「抬 batch」的代价（墙钟 / 显存 / 是否要关 gradient-checkpointing）此前只有估算，
# 没有实测 ⇒ 先用 50 步的真训练量出来，再决定档 7B 烧几个 seed。
#
# 房规：setsid 发车（坑 37）；done 标记 printf 写 + `[ -s ]` 自检（坑 43）；路径全绝对（坑 41）；
#       产物只落在 runs/s7_probe/ 下，不碰任何历史 run。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
LOG="$MG/logs/s7_probe.log"
MARK="$MG/runs/s7_probe.done"
die () { echo "[s7a] FATAL $*" >&2; exit 4; }

free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
[ "${free:-0}" -ge 60000 ] || die "GPU 余量只有 ${free}MiB ⇒ 别的实验还在跑，不抢卡"
echo "[s7a] GPU free=${free}MiB，发车 $(date '+%F %T')"

"$MG_PY" "$MG/code/mg_probe_batch.py" --selftest || die "探针自测不过"
"$MG_PY" "$MG/code/mg_probe_batch.py" > "$LOG" 2>&1
rc=$?
echo "[s7a] 探针 rc=$rc  $(date '+%F %T')  日志 -> $LOG"
[ -s "$MG/runs/s7_probe/timing.md" ] || die "timing.md 写空了"
[ "$rc" -eq 0 ] || die "探针退出码 $rc（看 $LOG）"

printf '%s 档7A batch探针完成 rc=%s 配置=%s 产物=runs/s7_probe/timing.md 用途=只出常数不出判定\n' \
  "$(date '+%F %T')" "$rc" "${CONFIGS:-8:1,16:0,32:0,64:0,32:1}" > "$MARK"
[ -s "$MARK" ] || die "done 标记写空了（坑 43 复发）"
echo "[s7a] done $(date '+%F %T')  标记 -> $MARK"
