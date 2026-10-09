#!/usr/bin/env bash
# run7 决定性臂：fullstate + **关掉提前停止**，把 40k 预算跑满。
#
# 为什么需要它：uniform_s0 在 round6 被 `harness/loop.py:293` 的提前停止截断
# （判据是「8 局采集成功率 >= 0.95」，实测 1.000），而**报告口径**是 50 局冻结评测，
# 当时只有 0.860 且仍在陡升（0.08 -> 0.54 -> 0.86），预算只用了 22496/40000。
# 也就是说 §6.12-E 预登记的那条「fullstate >= 0.9」既没被证实也没被证伪。
# 这一臂用 --target-success 1.01（1.0 >= 1.01 恒假）把提前停止关掉，跑满 10 轮。
#
# 等 run7_DONE 出现再启动，避免和 s1/s2 抢 CPU（机器 load 1200+，第三方 ffmpeg 作业）。
set -u
cd /workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot
PY=/root/venvs/rlrobot/bin/python

while [ ! -f runs/ab_stage3/run7_DONE ]; do sleep 60; done

"$PY" -u scripts/run_harness_loop.py --mode uniform --seed 0 \
  --budget-steps 40000 --steps-per-round 4000 --episodes 8 --rounds 10 \
  --target-success 1.01 --init random --deploy latest --eval-episodes 50 \
  --config configs/reach_fullstate.yaml --device cpu --threads 1 \
  --skill-name harness_reach_fullstate_noearly_s0 \
  --out runs/ab_stage3/run7_fullstate/noearly_s0 \
  > runs/ab_stage3/run7_fullstate/noearly_s0.log 2>&1
echo "DECISIVE_DONE" > runs/ab_stage3/run7_DECISIVE_DONE
