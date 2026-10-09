#!/usr/bin/env bash
# 档 2b · 交叉指令探针（STAGE_PLAN「档 2b」）。排在档 2 关门评测**之后**跑，不抢门的算力。
#
# 只跑两个**交叉格** `fr,rf`（场景+指令），不跑基线格 `ff,rr`：
#   基线格的行为就是「正向场景+正向指令」「反向场景+反向指令」，与 chain_s2_eval 的
#   TEST 正向未见 / TEST 反向未见 两组**完全同口径同 seed 区间**，门里已经有了，再跑一遍是纯浪费。
#   交叉格才是唯一能区分「真语言条件化」与「视觉捷径」的证据：
#     fr = 正向场景 + 反向指令；rf = 反向场景 + 正向指令。
#   两格的预测相反 ⇒ 结果可判（见 mg_probe_crossinstr.py 头注释的 2×2 表）。
#   指纹用 fwd_like / rev_like / no_transport / other，与成功判据解耦 —— 交叉格本来就不该「成功」。
# 为什么这一测值得做：它决定档 5 之后 Harness 能不能用**语言**接管。若策略吃的是
# 「can 在哪 / 幽灵 can 在不在」的视觉捷径，语言接管从根上就不成立。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
CK="$MG/runs/pi05_mix60f60r_s2/checkpoints/last/pretrained_model"
# 门跑完的唯一证据 = 门最后一组（CADENCE 反向 K=50）的产物落盘。不看进程（README 坑 22(e)）。
GATE_LAST="$MG/runs/s2_gate_rev_test_rand20_k50/eval_summary.json"
NOISE='robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation'

for _ in $(seq 1 "${MAX_WAIT_TRIES:-960}"); do          # 960×30 s = 8 h 上限
  [ -f "$GATE_LAST" ] && break
  sleep 30
done
[ -f "$GATE_LAST" ] || { echo "[s2b] FATAL 等不到门的产物 $GATE_LAST，不跑"; exit 3; }
[ -f "$CK/model.safetensors" ] || { echo "[s2b] FATAL 没有检查点 $CK"; exit 3; }
sleep 10
echo "[s2b] 门已收完 -> 开跑交叉指令探针 $(date +%H:%M:%S)"
echo "[s2b] ckpt -> $(readlink -f "$MG/runs/pi05_mix60f60r_s2/checkpoints/last")"
"$MG_PY" code/mg_probe_crossinstr.py --ckpt "$CK" --episodes 20 --n-action-steps 10 \
    --cells fr,rf --fwd-seed 2000 --rev-seed 7000 \
    --out "$MG/runs/s2_crossinstr" 2>&1 | grep -vE "$NOISE"
echo "[s2b] done $(date +%H:%M:%S)"
