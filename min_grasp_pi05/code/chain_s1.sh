#!/usr/bin/env bash
# 采集一结束就起档 1 训练 + 扫描（验证 seed 3000 起，10 局/检查点）。
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
while pgrep -f "mg_collec[t].py --episodes 60" > /dev/null 2>&1; do sleep 20; done
sleep 10
setsid nohup bash "$MG/code/run_pi05_s1.sh" > "$MG/logs/train_pi05_s1.log" 2>&1 < /dev/null &
sleep 30
RUN="$MG/runs/pi05_rand60_s1" EPISODES=10 K=50 STEPS_TOTAL=7200 SAVE_FREQ=500 \
  EVAL_SEED_MODE=random EVAL_SEED=3000 DEMO_NPZ="$MG/data/rand60_raw.npz" \
  setsid nohup bash "$MG/code/mg_sweep.sh" "$MG/runs/pi05_rand60_s1" > "$MG/logs/sweep_pi05_s1.log" 2>&1 < /dev/null &
echo "[chain] s1 train + sweep launched at $(date +%H:%M:%S)"
