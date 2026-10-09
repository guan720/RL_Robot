#!/usr/bin/env bash
# 档 11 哨兵：**不编辑在飞的 chain_watchdog.sh / chain_s9c.sh / chain_s10.sh**（坑 22(d)/78）⇒ 独立进程补监控缺口。
#
# 为什么要有它：档 11 要先**空等档 10 让卡 ~24 h**（9C 三 seed 训练 + 档 10 的 15 读），再跑 ~1.4 h 的 20 读评测；
#   它不在看门狗清单里（清单在飞的脚本不许改）⇒ 静默死亡不会自动报警，正是坑 22(e) 那次事故的形状。
# 本哨兵只**观测与报警**，绝不重启、绝不改任何产物、绝不碰 GPU。
#
# 判据（认产物不认进程表，坑 22(e)）：
#   DONE/FAILED/SKIPPED = 对应终态标记已在（进程退出是正常的）⇒ 打最后一行心跳后自行收工；
#   MISSING             = 进程没了 **且** 三个终态标记都没有 ⇒ 写 logs/ALERTS.log 报警（前缀 [s11-sentinel]）；
#   RUN                 = 进程还在 ⇒ 顺带把「已落盘几读 / 20」与显存打进心跳。
# 房规：setsid 发车并核 SID==PID（坑 37）；pgrep 模式用**字符类**打断自匹配（坑 75）；路径全绝对（坑 41）；
#   有界寿命（MAX_TICKS×TICK ≈ 48 h）⇒ 不会变成常驻僵尸；一次只 head 一个文件（坑 55）。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
cd "$MG"
TICK="${TICK:-600}"                 # 10 min，与 chain_watchdog.sh / 9C / 档10 哨兵同频
MAX_TICKS="${MAX_TICKS:-288}"       # 288×600 s = 48 h（空等档 10 ~24 h + 评测 ~1.4 h ⇒ 有余量、且有界）
LOG="$MG/logs/chain_s11_sentinel.log"
ALERT="$MG/logs/ALERTS.log"
PROC='code/chain_s1[1]\.sh'         # 字符类打断自匹配（坑 75）；本哨兵自己的 cmdline 匹配不上它
MARK="$MG/runs/s11.done"; FAILED="$MG/runs/s11.FAILED"; SKIPPED="$MG/runs/s11.SKIPPED"
NREADS="${NREADS:-20}"              # 6 句改写×3 臂 + 2 句负对照×1 臂

for i in $(seq 1 "$MAX_TICKS"); do
  st="MISSING"; mf=""
  [ -s "$MARK" ]    && st="DONE"
  [ -s "$FAILED" ]  && st="FAILED"
  [ -s "$SKIPPED" ] && st="SKIPPED"
  case "$st" in
    DONE)    mf="$MARK" ;;
    FAILED)  mf="$FAILED" ;;
    SKIPPED) mf="$SKIPPED" ;;
  esac
  if [ "$st" = "MISSING" ] && pgrep -f "$PROC" > /dev/null 2>&1; then st="RUN"; fi

  # 进度只从**盘上产物**读（认产物不认进程表，坑 22(e)）
  ne=$(find "$MG/runs" -maxdepth 2 -name eval_summary.json -path '*/s11_*' 2>/dev/null | wc -l)
  up="?"
  for m in "$MG/runs/s10.done" "$MG/runs/s10.FAILED" "$MG/runs/s10.SKIPPED"; do
    [ -s "$m" ] && { up=$(basename "$m"); break; }
  done
  gpu=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1)

  printf '[%s] tick=%s s11=%s 上游档10=%s reads=%s/%s gpu=%s MiB\n' \
    "$(date '+%F %T')" "$i" "$st" "$up" "$ne" "$NREADS" "${gpu:-?}" >> "$LOG"

  if [ "$st" = "MISSING" ]; then
    printf '[%s] [s11-sentinel] MISSING：chain_s11.sh 进程没了，而 runs/s11.{done,FAILED,SKIPPED} 一个都不在 ⇒ 静默死亡（坑 22(e) 的形状）。最后心跳看 logs/chain_s11.log；已落盘 %s/%s 读；上游档 10 终态=%s\n' \
      "$(date '+%F %T')" "$ne" "$NREADS" "$up" >> "$ALERT"
    echo "[s11-sentinel] 已报警并收工（MISSING）$(date '+%F %T')" >> "$LOG"
    exit 1
  fi
  case "$st" in
    DONE|FAILED|SKIPPED)
      printf '[%s] [s11-sentinel] 终态=%s：%s ⇒ 哨兵收工\n' "$(date '+%F %T')" "$st" "$(head -c 300 "$mf" 2>/dev/null)" >> "$LOG"
      exit 0 ;;
  esac
  sleep "$TICK"
done
printf '[%s] [s11-sentinel] 到 %s tick 上限（%s h）仍在 RUN ⇒ 哨兵收工，改由人工巡检\n' \
  "$(date '+%F %T')" "$MAX_TICKS" "$((MAX_TICKS * TICK / 3600))" >> "$LOG"
exit 0
