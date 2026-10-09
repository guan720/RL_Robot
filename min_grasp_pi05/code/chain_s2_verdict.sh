#!/usr/bin/env bash
# 档 2 判定落盘：等门 + 两个 TEST 组的复跑都收完，自动跑 mg_verdict_s2.py，
# 把判定表写成 runs/S2_VERDICT.md。这样「过没过门」这件事不依赖任何人凌晨爬起来手抄日志。
#
# 为什么判定要用脚本而不是人看：门是「正向≥50% ∧ 反向≥50% ∧ 正向相对档 1 回退≤15pp」三条同时成立，
# 反向还得同时报绝对值和相对上界（上界只有 70%），而且单读 20 局 1σ≈10 pp、贴门必须复跑。
# 这么多条件人工同时握住极易漏一条；mg_verdict_s2.py 有 --selftest 覆盖 5 个场景（含「贴门单读拒绝下结论」）。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
CONFIRM_LAST="$MG/runs/s2_gate_rev_test_rand20_k10_rep2/eval_summary.json"
S2B="$MG/runs/s2_crossinstr/crossinstr_summary.json"
OUT="$MG/runs/S2_VERDICT.md"

# 只看产物，不看进程状态翻转（README 坑 22(e)）
for _ in $(seq 1 "${MAX_WAIT_TRIES:-960}"); do [ -f "$CONFIRM_LAST" ] && break; sleep 30; done
[ -f "$CONFIRM_LAST" ] || { echo "[s2-verdict] FATAL 等不到复跑产物 $CONFIRM_LAST"; exit 3; }
# 档 2b 是选做项：给它 40 分钟，等不到也照样出判定（不能因为选做项拖住门的结论）
for _ in $(seq 1 80); do [ -f "$S2B" ] && break; sleep 30; done
[ -f "$S2B" ] && echo "[s2-verdict] 档 2b 产物已到" || echo "[s2-verdict] 档 2b 40 min 未到，先出门的判定"
sleep 10
echo "[s2-verdict] 生成判定 $(date +%H:%M:%S)"
{
  echo "<!-- 本文件由 code/chain_s2_verdict.sh 自动生成，源数据是 runs/s2_gate_*/eval_summary.json -->"
  echo "<!-- 重新生成：bash -c 'source code/env.sh && \$MG_PY code/mg_verdict_s2.py > runs/S2_VERDICT.md' -->"
  echo
  "$MG_PY" code/mg_verdict_s2.py
} > "$OUT" 2>&1
rc=$?
echo "[s2-verdict] 已写 $OUT (rc=$rc) $(date +%H:%M:%S)"
grep -E "^## 总判定|PASS|FAIL|NEEDS_RERUN" "$OUT" | head -12
exit $rc
