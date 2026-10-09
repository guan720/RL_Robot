#!/usr/bin/env bash
# 档 2 两个 TEST 组的**复跑**（门跑完后自动接上）。
#
# 为什么档 2 必须有复跑，而档 0/档 1 当初没有：
#   档 1 的三次读数实测 80% / 65% / 65%（均值 70%，样本 std 8.7 pp，与单读二项 1σ≈10.2 pp 一致）
#   ⇒ **单读 20 局的噪声就有 ±10 pp**。档 2 正向门 ≥50%、预期 ~70%，距门 2σ，单读够判；
#   但**反向专家上界只有 70%、门是 50%**，若真值在 55~65%，单读完全可能落到 45% 或 75% ——
#   一次读数就能把「通过」判成「不通过」，或反过来。这种错判会直接触发错误的预案
#   （白采 60 条反向数据 + 10 小时重训）。
#   ⇒ 房规：读数落在门 ±10 pp 内必须复跑。这里干脆**无条件**复跑，省得事后回头补。
#
# 只复跑两个 TEST 组（正向未见 / 反向未见）。CONTROL / REGRESSION / CADENCE 三组不复跑：
#   它们不是阈值判定，是对照读数，噪声不影响结论方向。
# 不带 --video：门那两组已经各存了 3 段视频，复跑只要数字，省一半墙钟。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
RUN="$MG/runs/pi05_mix60f60r_s2"
CK="$RUN/checkpoints/last/pretrained_model"
NPZ_F="$MG/data/mix60f60r_raw.npz"
NPZ_R="$MG/data/mix60f60r_rev_raw.npz"
NOISE='robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation'
# 门跑完的唯一证据 = 门最后一组的产物落盘。不看进程状态翻转（README 坑 22(e)）。
GATE_LAST="$MG/runs/s2_gate_rev_test_rand20_k50/eval_summary.json"

for _ in $(seq 1 "${MAX_WAIT_TRIES:-960}"); do          # 960×30 s = 8 h 上限
  [ -f "$GATE_LAST" ] && break
  sleep 30
done
[ -f "$GATE_LAST" ] || { echo "[s2-confirm] FATAL 等不到门的产物 $GATE_LAST，不跑"; exit 3; }
[ -f "$CK/model.safetensors" ] || { echo "[s2-confirm] FATAL 没有检查点 $CK"; exit 3; }
sleep 10
echo "[s2-confirm] 门已收完 -> 开始复跑两个 TEST 组 $(date +%H:%M:%S)"
echo "[s2-confirm] ckpt -> $(readlink -f "$RUN/checkpoints/last")"

run_rep () {  # $1=task-mode $2=seed $3=npz $4=rep $5=产物目录名
  # 目录名**显式传**，不用 ${1:0:3} 之类的前缀截取：那样 "forward" 会截成 "for"，
  # 与门里的 `s2_gate_fwd_*` 命名对不上，后面汇总脚本按 glob 找就会漏。
  local out="$5"
  echo "[s2-confirm] === $1 未见 20 局 K=10 rep#$4 (seed $2..) -> runs/$out === $(date +%H:%M:%S)"
  "$MG_PY" code/mg_eval.py --ckpt "$CK" --episodes 20 --seed-mode random --seed "$2" \
      --n-action-steps 10 --task-mode "$1" --demo-npz "$3" \
      --out "$MG/runs/$out" 2>&1 | grep -vE "$NOISE" | grep -E "^  ep|成功率|\[saved\]"
}

run_rep forward 2000 "$NPZ_F" 2 s2_gate_fwd_test_rand20_k10_rep2
run_rep reverse 7000 "$NPZ_R" 2 s2_gate_rev_test_rand20_k10_rep2
echo "[s2-confirm] done $(date +%H:%M:%S)"
