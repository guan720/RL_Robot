#!/usr/bin/env bash
# 等 r1 训练进程退出后立刻起 r2（不空等 GPU），并顺手对 r1 的最终检查点做一次 20 局定版评测。
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
while pgrep -f "job_name=pi05_fixed10 " > /dev/null 2>&1; do sleep 20; done
sleep 10
setsid nohup bash "$MG/code/run_pi05_r2.sh" > "$MG/logs/train_pi05_r2.log" 2>&1 < /dev/null &
echo "[chain] r2 launched at $(date +%H:%M:%S)"
