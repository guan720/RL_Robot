#!/usr/bin/env bash
# 档 8D 的**独立出身核对**旁链（零 GPU、**不是门**、不改任何判定文件）
#
# 为什么要有它：`code/mg_verdict_s8.py` 的 `prov()` 只覆盖 **8C / 8C-ctl**（它成文时 8D 还没发车）⇒
#   D4（关使命门的那一条：三个训练 seed 的反向 TEST 放宽 min ≥ 40/80）的**输入出身**原本只靠
#   `code/chain_s8d.sh` 自己核（链里核 `readlink last == 022000`、评测路径写数字格）。
#   链在飞时不许编辑（坑 22(d)）⇒ 用**另一条**链在 `s8d.done` 之后独立复核：
#   `code/mg_prov_s8d.py`（自测 19/19；正对照 = 已知good 的 8C 臂 5/5 + 11/11 全对；
#   三条负对照 = 关门格尾串错、权重出自隔壁臂、val 格号与权重错配（坑 38 原形）**全部被抓**）。
#
# 终态：`runs/s8d_prov.done`（含 `PROV_RC=`，0 = D4 输入可采信 / 3 = 🚫 不采信，人来查）
#       `runs/s8d_prov.SKIPPED`（上游 8D 写了 FAILED ⇒ 停下等人；这是合法终态，坑 62 家族）
# 房规：setsid 发车并核 SID==PID（坑 37）；标记 printf 写 + `[ -s ]` 自检（坑 43）；路径全绝对（坑 41）；
#   认产物不认进程表（坑 22(e)）；**不编辑运行中的 .sh**；不碰冻结文件；不改 `runs/S8_VERDICT.md` 一个字。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
WAIT_H="${WAIT_H:-48}"
UP_DONE="$MG/runs/s8d.done"; UP_FAIL="$MG/runs/s8d.FAILED"
OUT="$MG/runs/s8d_prov.md"
MARK="$MG/runs/s8d_prov.done"; SKIPM="$MG/runs/s8d_prov.SKIPPED"
die () { echo "[s8dprov] FATAL $*" | tee -a "$MG/runs/s8d_prov.FAILED"; exit 4; }
skip () { printf '%s 8D 出身核对不发车（合法终态）原因=%s\n' "$(date '+%F %T')" "$1" > "$SKIPM"
          [ -s "$SKIPM" ] || echo "[s8dprov] SKIPPED 写空了（坑 43 复发）"; echo "[s8dprov] SKIP：$1"; exit 0; }

if [ -s "$MARK" ]; then echo "[s8dprov] 已收工（$MARK 在）：$(head -1 "$MARK")"; exit 0; fi
if [ -s "$SKIPM" ]; then echo "[s8dprov] 已跳过（$SKIPM 在）：$(head -1 "$SKIPM")"; exit 0; fi

echo "[s8dprov] === 等档 8D 收工（上限 ${WAIT_H} h）=== $(date '+%F %T')"
got=""
for _ in $(seq 1 $((WAIT_H * 60))); do
  [ -s "$UP_DONE" ] && { got="done";   break; }
  [ -s "$UP_FAIL" ] && { got="FAILED"; break; }
  sleep 60
done
case "$got" in
  done)   echo "[s8dprov] 8D 收工：$(head -1 "$UP_DONE")" ;;
  FAILED) skip "上游 8D 写了 s8d.FAILED（$(head -c 200 "$UP_FAIL")）⇒ 需要人工分诊" ;;
  *)      skip "等 ${WAIT_H} h 仍没等到 runs/s8d.done" ;;
esac

"$MG_PY" "$MG/code/mg_prov_s8d.py" --selftest > "$MG/logs/s8d_prov_selftest.log" 2>&1 \
  || die "mg_prov_s8d 自测不过（看 logs/s8d_prov_selftest.log）⇒ 核对器本身不可信"
echo "[s8dprov] === 出身核对 -> ${OUT#$MG/} === $(date '+%F %T')"
"$MG_PY" "$MG/code/mg_prov_s8d.py" > "$OUT" 2>&1
RC=$?
[ -s "$OUT" ] || die "核对报告没生成"
cat "$OUT"
case "$RC" in
  0) RES="✅ 全对 ⇒ **D4 的输入可采信**（两个新 seed 的 5 个 TEST 读 + 11 格 val 的 ckpt 尾串/权重出身/K/seed 窗口/局数/口径不变量都核过）" ;;
  2) RES="⏳ 读数不齐 ⇒ 8D 说收工了但产物缺（🚨 与 s8d.done 矛盾，人来查）" ;;
  3) RES="🚫 有出身问题 ⇒ **D4 的输入不采信**；`runs/S8_VERDICT.md` 的 D1/D2/D3 不受影响，但 D4 那一行**不许**当结论用" ;;
  *) RES="核对器退出码 $RC（未定义）⇒ 人来查" ;;
esac
printf '%s 8D 出身核对完成 PROV_RC=%s 报告=runs/s8d_prov.md 结论=%s\n' \
  "$(date '+%F %T')" "$RC" "$RES" > "$MARK"
[ -s "$MARK" ] || die "done 标记写空了（坑 43 复发）"
echo "[s8dprov] 收工 $(date '+%F %T')  标记 -> $MARK"
echo "[s8dprov] 结论：$RES"
