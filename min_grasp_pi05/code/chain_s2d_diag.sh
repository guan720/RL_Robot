#!/usr/bin/env bash
# 档 2c 判定落地**之后**的两个补读。两个都要 GPU，所以必须等主链跑完再发车 ——
# 跟训练抢卡会把 1.36 s/步拖到 1.9 s/步（实测），把判定时间往后推一小时。
#
# 为什么是这两件事（都不是「锦上添花」，是补主链的已知短板）：
#  1) 护栏 G2 加功效：主链的 G2 是 n=10 且 seed 5000..5009 里 **5002 不是训练 seed**（坑 32）。
#     n=10 对 TEST 30/80 做 Fisher 要 ≥8/10 才触发 p<0.05 ⇒ 只能抓「碾压式记忆」。
#     这里用唯一干净的连续窗口 5062..5071 跑 4 读 = 40 局真训练 seed。
#  2) A 类抓空的几何定位：`runs/_diag/lift_profile.md` 量出 A 类（占失败 **44%**、最大的盘子）
#     是 **21/31 局一次都没夹住**、空合率 74%（专家 0/60）。但「为什么抓空」还没分辨：
#     H1 横向偏 / H2 深度偏 / H3 时机偏 —— 三者的处方完全不同。`code/mg_diag_miss.py` 就是干这个的。
#     ⚠️ 它原来的合爪高度参照是**硬编码的正向值 0.880**，直接拿去判反向的 H2 会安静地给错结论；
#        本轮已修成「按 task_mode 用 --demo-npz 的实测中位数覆盖，并打印出处」，所以这里必须带
#        `--demo-npz data/mix60f60r_rev_raw.npz`。
#     同时拿档 2 联合模型的反向 TEST 两读做**对照**：若两边的 H1/H2/H3 分布一样，
#     说明抓空是**任务/数据**层面的，不是多任务干扰造出来的 —— 这直接决定档 2c 判 R1 时该修什么。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
S2C_MARK="$MG/runs/pi05_rev60_s2c/s2c.done"
MARK="$MG/runs/s2d_diag.done"
NPZ_R="$MG/data/mix60f60r_rev_raw.npz"
JOB="${JOB:-pi05_rev60_s2c}"
NEED_FREE_MIB="${NEED_FREE_MIB:-40000}"
[ -f "$MARK" ] && { echo "[s2d] 已完成（$MARK 存在），退出"; exit 0; }

# ── 0. 等档 2c 主链落地（最多 8 h）───────────────────────────────────────────
for _ in $(seq 1 480); do [ -f "$S2C_MARK" ] && break; sleep 60; done
if [ ! -f "$S2C_MARK" ]; then
  echo "[s2d] FATAL 等了 8 h，档 2c 主链的 $S2C_MARK 还没出现 —— 先看 logs/chain_s2c.log"; exit 4
fi
echo "[s2d] 主链已落地：$(cat "$S2C_MARK")  -> 开始补读 $(date +%H:%M:%S)"

# ── 0b. 等 GPU 空出来（主链的评测进程都退了再上，避免三方抢卡）────────────────
for _ in $(seq 1 120); do
  free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
  [ "${free:-0}" -ge "$NEED_FREE_MIB" ] && break
  echo "[s2d] 显存 free=${free}MiB < ${NEED_FREE_MIB}MiB，等 30 s ... $(date +%H:%M:%S)"; sleep 30
done

# ── 1. 护栏 G2 加功效（40 局真训练 seed）─────────────────────────────────────
echo "[s2d] === 1/2 护栏 G2 加功效 === $(date +%H:%M:%S)"
JOB="$JOB" bash code/mg_g2_supp.sh 2>&1 | tail -25

# ── 2. A 类抓空的几何定位（档 2c 单任务 4 读 + 档 2 联合 2 读做对照）───────────
echo "[s2d] === 2/2 A 类抓空几何定位 === $(date +%H:%M:%S)"
DIRS=()
for d in s2c_rev_test_rand20_k10 s2c_rev_test_rand20_k10_rep2 \
         s2c_rev_test_rand20_k10_rep3 s2c_rev_test_rand20_k10_rep4 \
         s2_gate_rev_test_rand20_k10 s2_gate_rev_test_rand20_k10_rep2; do
  if [ -f "$MG/runs/$d/rollout_actions.npz" ]; then DIRS+=("$MG/runs/$d")
  else echo "[s2d] 跳过（缺 rollout_actions.npz）$d"; fi
done
if [ "${#DIRS[@]}" -eq 0 ]; then
  echo "[s2d] FATAL 一个 rollout 都没有，做不了几何定位"; exit 3
fi
echo "[s2d] 读 ${#DIRS[@]} 个产物目录（前 4 = 档 2c 单任务，后 2 = 档 2 联合作对照）"
"$MG_PY" code/mg_diag_miss.py "${DIRS[@]}" \
    --demo-npz "$NPZ_R" \
    --out "$MG/runs/_diag/diag_miss_s2c_rev.json" 2>&1 | tail -60

date +"%Y-%m-%d %H:%M:%S job=$JOB dirs=${#DIRS[@]}" > "$MARK"
echo "[s2d] done $(date +%H:%M:%S)  标记 -> $MARK"
