#!/usr/bin/env bash
# 档 1 训练一结束，按 STAGE_PLAN.md 的口径做三组定版评测（各取 checkpoints/last）：
#   1) 测试：未见 seed 2000..2019，20 局   <- 判定门主指标
#   2) 回归：固定 seed 0，20 局            <- 确认没把档 0 的能力训丢
#   3) 对照：训练 seed 1000..1009，10 局    <- 区分「记住训练位姿」与「泛化」
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
while pgrep -f "job_name=pi05_rand60_s1" > /dev/null 2>&1; do sleep 20; done
sleep 15
CK="$MG/runs/pi05_rand60_s1/checkpoints/last/pretrained_model"

echo "[s1-gate] === TEST unseen 2000..2019, 20 eps === $(date +%H:%M:%S)"
"$MG_PY" code/mg_eval.py --ckpt "$CK" --episodes 20 --seed-mode random --seed 2000 \
    --n-action-steps 50 --video --max-videos 3 --demo-npz "$MG/data/rand60_raw.npz" \
    --out "$MG/runs/s1_gate_test_rand20" 2>&1 | grep -vE "robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation"

echo "[s1-gate] === REGRESSION fixed seed 0, 20 eps === $(date +%H:%M:%S)"
"$MG_PY" code/mg_eval.py --ckpt "$CK" --episodes 20 --seed-mode fixed --seed 0 \
    --n-action-steps 50 --demo-npz "$MG/data/rand60_raw.npz" \
    --out "$MG/runs/s1_gate_regression_fixed20" 2>&1 | grep -vE "robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation"

echo "[s1-gate] === CONTROL train seeds 1000..1009, 10 eps === $(date +%H:%M:%S)"
"$MG_PY" code/mg_eval.py --ckpt "$CK" --episodes 10 --seed-mode random --seed 1000 \
    --n-action-steps 50 --demo-npz "$MG/data/rand60_raw.npz" \
    --out "$MG/runs/s1_gate_control_train10" 2>&1 | grep -vE "robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation"

echo "[s1-gate] done $(date +%H:%M:%S)"
