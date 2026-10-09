#!/usr/bin/env bash
# ACT 训练一结束就按两个标准口径各评 10 局：K=1（全闭环逐步重规划）与 K=chunk_size（标准 chunk 执行）。
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
CK="$MG/runs/act_fixed10_r1/checkpoints/last/pretrained_model"
source "$MG/code/env.sh"; cd "$MG"
while pgrep -f "job_name=act_fixed10 " > /dev/null 2>&1; do sleep 20; done
sleep 15
for K in 1 100; do
  echo "[act-eval] === K=$K === $(date +%H:%M:%S)"
  "$MG_PY" code/mg_eval.py --ckpt "$CK" --episodes 10 --video --max-videos 2 \
      --demo-npz "$MG/data/fixed10_raw.npz" --n-action-steps "$K" \
      --out "$MG/runs/eval_act20000_k$K" 2>&1 \
    | grep -vE "robosuite|WARNING:robosuite|INFO:robosuite"
done
echo "[act-eval] done $(date +%H:%M:%S)"
