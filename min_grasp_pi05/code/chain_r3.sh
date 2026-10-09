#!/usr/bin/env bash
# r2 一结束：先做「定版」20 局评测（n=8 的扫描噪声太大，±15%），再起 r3 长训练。
# 定版口径：固定示范初态 + K=50（π₀.₅ 原生 chunk 执行）+ 20 局 + 视频。
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
while pgrep -f "job_name=pi05_fixed30n_r2" > /dev/null 2>&1; do sleep 20; done
sleep 15

for CK in 002500 last; do
  echo "[final] === r2 @$CK (fixed30n) 20 eps K=50 === $(date +%H:%M:%S)"
  "$MG_PY" code/mg_eval.py --ckpt "$MG/runs/pi05_fixed30n_r2/checkpoints/$CK/pretrained_model" \
      --episodes 20 --n-action-steps 50 --video --max-videos 3 \
      --demo-npz "$MG/data/fixed30n_raw.npz" --out "$MG/runs/final_pi05_r2_${CK}_k50" 2>&1 \
    | grep -vE "robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation"
done

setsid nohup bash "$MG/code/run_pi05_r3.sh" > "$MG/logs/train_pi05_r3.log" 2>&1 < /dev/null &
sleep 30
RUN="$MG/runs/pi05_fixed30n_r3" EPISODES=10 K=50 STEPS_TOTAL=8000 SAVE_FREQ=500 \
  DEMO_NPZ="$MG/data/fixed30n_raw.npz" \
  setsid nohup bash "$MG/code/mg_sweep.sh" "$MG/runs/pi05_fixed30n_r3" > "$MG/logs/sweep_pi05_r3.log" 2>&1 < /dev/null &
echo "[chain] r3 + sweep launched at $(date +%H:%M:%S)"
