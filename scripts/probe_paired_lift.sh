#!/usr/bin/env bash
# 阶段 4 探针：Lift 的「手写上限 vs 冻结 SAC」逐题配对（真值 grasp 口径）。
# 两档出生盒子：训练分布（±0.03）与 OOD（±0.12）。用法：
#   setsid nohup nice -n 15 bash scripts/probe_paired_lift.sh > runs/infra/probe_paired_lift_truth.log 2>&1 &
set -u
cd "$(dirname "$0")/.."
export MUJOCO_GL=egl OMP_NUM_THREADS=1
PY=/root/venvs/rlrobot/bin/python
CK=runs/20260923_164831_sac_lift_state_shaped_demo5k/model_final.zip

echo "########## A: 默认出生 ±0.03（训练分布） ##########"
$PY -u scripts/probe_contact_ceiling.py --task lift --episodes 12 --grid 3 \
    --sac-ckpt "$CK" --out runs/infra/paired_lift_default_spawn.json

echo "########## B: 宽出生 ±0.12（OOD） ##########"
$PY -u scripts/probe_contact_ceiling.py --task lift --episodes 12 --grid 3 \
    --spawn-range 0.12 --sac-ckpt "$CK" --out runs/infra/paired_lift_wide_spawn.json

echo "########## ALL DONE ##########"
