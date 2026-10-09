#!/usr/bin/env bash
# 档 9C 哨兵：**不编辑在飞的 chain_watchdog.sh**（坑 22(d)/78）⇒ 用一个独立进程补上 9C 的监控缺口。
#
# 为什么要有它：9C ≈ 26 h、跨两夜，而它**不在**看门狗清单里（清单在飞的脚本不许改）⇒ 静默死亡不会自动报警，
#   正是坑 22(e) 那次事故的形状（凌晨自杀、门没人收）。本哨兵只**观测与报警**，绝不重启、绝不改任何产物。
#
# 判据（认产物不认进程表，坑 22(e)）：
#   DONE/FAILED/SKIPPED = 对应终态标记已在（进程退出是正常的）⇒ 打最后一行心跳后自行收工；
#   MISSING             = 进程没了 **且** 三个终态标记都没有 ⇒ 写 logs/ALERTS.log 报警（带 [s9c-sentinel] 前缀）；
#   RUN                 = 进程还在 ⇒ 顺带把训练进度/显存打进心跳（进度只从 meta/train.log 读，绝不 pgrep 训练 pattern，坑 22(b)）。
# 房规：setsid 发车并核 SID==PID（坑 37）；pgrep 模式用**字符类**打断自匹配（坑 75）；路径全绝对（坑 41）；
#   有界寿命（MAX_TICKS×TICK ≈ 40 h）⇒ 不会变成常驻僵尸；退出码先存变量再做 $(...)（坑 80）。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
cd "$MG"
TICK="${TICK:-600}"                 # 10 min，与 chain_watchdog.sh 同频
MAX_TICKS="${MAX_TICKS:-240}"       # 240×600 s = 40 h（9C 预算 ~26 h ⇒ 有余量、且有界）
LOG="$MG/logs/chain_s9c_sentinel.log"
ALERT="$MG/logs/ALERTS.log"
PROC='code/chain_s9[c]\.sh'         # 字符类打断自匹配（坑 75）；⚠️ 本脚本自己的 cmdline 匹配不上它
MARK="$MG/runs/s9c.done"; FAILED="$MG/runs/s9c.FAILED"; SKIPPED="$MG/runs/s9c.SKIPPED"

for i in $(seq 1 "$MAX_TICKS"); do
  st="MISSING"
  mf=""
  [ -s "$MARK" ]    && st="DONE"
  [ -s "$FAILED" ]  && st="FAILED"
  [ -s "$SKIPPED" ] && st="SKIPPED"
  case "$st" in
    DONE)    mf="$MARK" ;;
    FAILED)  mf="$FAILED" ;;
    SKIPPED) mf="$SKIPPED" ;;
  esac
  if [ "$st" = "MISSING" ] && pgrep -f "$PROC" > /dev/null 2>&1; then st="RUN"; fi

  prog=""; cur=""
  for sd in 21000 22000 23000; do
    t="$MG/runs/pi05_mix60f120r_c1_s9c_seed${sd}_meta/train.log"
    if [ -f "$t" ]; then
      cur=$(grep -o 'step:[0-9]*' "$t" 2>/dev/null | tail -1)
      prog="seed${sd}=${cur:-?}"
      break
    fi
  done
  nd=$(ls -1d "$MG"/runs/pi05_mix60f120r_c1_s9c_seed*/sweep_rev/step_*_rev 2>/dev/null | wc -l)
  ne=$(ls -1d "$MG"/runs/s9c_seed*_test_rand20_k10* 2>/dev/null | wc -l)
  gpu=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1)

  printf '[%s] tick=%s s9c=%s %s sweep_cells=%s/33 test_evals=%s/15 gpu=%s MiB\n' \
    "$(date '+%F %T')" "$i" "$st" "${prog:-（还没开训）}" "$nd" "$ne" "${gpu:-?}" >> "$LOG"

  if [ "$st" = "MISSING" ]; then
    printf '[%s] [s9c-sentinel] MISSING：chain_s9c.sh 进程没了，而 runs/s9c.{done,FAILED,SKIPPED} 一个都不在 ⇒ 静默死亡（坑 22(e) 的形状）。最后心跳看 logs/chain_s9c.log；进度 %s sweep=%s/33 evals=%s/15\n' \
      "$(date '+%F %T')" "${prog:-NA}" "$nd" "$ne" >> "$ALERT"
    echo "[s9c-sentinel] 已报警并收工（MISSING）$(date '+%F %T')" >> "$LOG"
    exit 1
  fi
  case "$st" in
    DONE|FAILED|SKIPPED)
      # ⚠️ 一次只 `head` **一个**文件：多文件时 head 会打 `==> 文件 <==` 头，`| head -1` 就只捞到文件名（坑 55 家族：引用走样）
      printf '[%s] [s9c-sentinel] 终态=%s：%s ⇒ 哨兵收工\n' "$(date '+%F %T')" "$st" "$(head -c 300 "$mf" 2>/dev/null)" >> "$LOG"
      exit 0 ;;
  esac
  sleep "$TICK"
done
printf '[%s] [s9c-sentinel] 到 %s tick 上限（%s h）仍在 RUN ⇒ 哨兵收工，改由人工巡检\n' \
  "$(date '+%F %T')" "$MAX_TICKS" "$((MAX_TICKS * TICK / 3600))" >> "$LOG"
exit 0
