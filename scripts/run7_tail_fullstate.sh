#!/usr/bin/env bash
# run7 负载分诊后的接力脚本（只保留 fullstate 三 seed；stack3 三臂已按
# 「朴素堆叠在数学上恢复不了在途指令」的分析结论砍掉，见 docs/notes_stage3.md §6.12）。
# 先等 s0 (PID $1) 跑完，再顺序跑 s1 / s2，最后写 DONE 标记。
set -u
cd /workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot
WAIT_PID="${1:-550263}"
PY=/root/venvs/rlrobot/bin/python

while kill -0 "$WAIT_PID" 2>/dev/null; do sleep 60; done

for s in 1 2; do
  "$PY" -u scripts/run_harness_loop.py --mode uniform --seed "$s" \
    --budget-steps 40000 --steps-per-round 4000 --episodes 8 --rounds 10 \
    --target-success 0.95 --init random --deploy latest --eval-episodes 50 \
    --config configs/reach_fullstate.yaml --device cpu --threads 1 \
    --skill-name "harness_reach_fullstate_uniform_s$s" \
    --out "runs/ab_stage3/run7_fullstate/uniform_s$s" \
    > "runs/ab_stage3/run7_fullstate/uniform_s$s.log" 2>&1
done
echo "ALL_DONE (fullstate x3 only)" > runs/ab_stage3/run7_DONE
