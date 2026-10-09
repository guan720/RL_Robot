#!/usr/bin/env bash
# 档 3 复跑：把 seed2000 / seed3000 的正向未见读数从 20 局补到 **60 局**。
#
# 为什么必须补：档 3 的门是「最差的那个 seed 也要 ≥50%」。seed2000 单读 **11/20 = 55%**，
# 只比门高 5 pp —— 而坑 29 实测「同检查点同 seed 三读 30%/35%/55%」，n=20 的 1σ≈11 pp。
# 也就是说 55% 这个读数的 95% CI 是 34~75%，**它自己就跨在门上**。
# 用这种读数判「最差 seed 也过门」= 用一次抛硬币判一枚硬币是否公平。
# seed1000 当初就是补到 3 读 60 局（80/65/65 → 70%）才敢下结论的，档 3 的两个新 seed 同样要补。
#
# 口径与档 1/档 3 完全一致：正向、未见 seed 2000..2019、K=10、`last` 检查点、同一份 rand60 数据训出来的。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
NPZ="$MG/data/rand60_raw.npz"
NOISE='robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation'
MARK="$MG/runs/s3_confirm.done"

for seed in 2000 3000; do
  RUN="$MG/runs/pi05_rand60_s3_seed${seed}"
  CK="$RUN/checkpoints/last/pretrained_model"
  if [ ! -f "$CK/model.safetensors" ]; then
    echo "[s3-confirm] 跳过 seed${seed}：没有检查点 $CK"; continue
  fi
  echo "[s3-confirm] seed${seed} last -> $(readlink -f "$RUN/checkpoints/last")"
  for rep in rep2 rep3; do
    out="pi05_rand60_s3_seed${seed}_test_rand20_k10_${rep}"
    [ -f "$MG/runs/$out/eval_summary.json" ] && { echo "[s3-confirm] 跳过（已有产物）$out"; continue; }
    echo "[s3-confirm] === seed${seed} 正向未见 K=10 $rep === $(date +%H:%M:%S)"
    "$MG_PY" code/mg_eval.py --ckpt "$CK" --episodes 20 --seed-mode random --seed 2000 \
        --n-action-steps 10 --task-mode forward --demo-npz "$NPZ" \
        --out "$MG/runs/$out" 2>&1 | grep -vE "$NOISE" | grep -E "成功率"
  done
done

# 汇总：三个 seed 各 3 读，报「最差 seed 的合并值」——这才是档 3 的门要的那个数
"$MG_PY" - <<'PY'
import json
from pathlib import Path
runs = Path("runs")
rows = []
for seed in (1000, 2000, 3000):
    dirs = (["s1_gate_test_rand20_k10", "s1_gate_test_rand20_k10_rep2", "s1_gate_test_rand20_k10_rep3"]
            if seed == 1000 else
            [f"pi05_rand60_s3_seed{seed}_test_rand20_k10"] +
            [f"pi05_rand60_s3_seed{seed}_test_rand20_k10_rep{i}" for i in (2, 3)])
    reads, ns, ne = [], 0, 0
    for d in dirs:
        f = runs / d / "eval_summary.json"
        if not f.exists():
            reads.append("MISS"); continue
        j = json.loads(f.read_text())
        ns += j["n_success"]; ne += j["episodes"]
        reads.append(f"{j['n_success']}/{j['episodes']}={j['pc_success']*100:.0f}%")
    rows.append((seed, reads, ns, ne))
print("| seed | 逐次读数 | 合并 |")
print("| --- | --- | --- |")
for seed, reads, ns, ne in rows:
    print(f"| {seed} | {'  '.join(reads)} | **{ns}/{ne}"
          f"{'' if not ne else f' = {ns/ne*100:.1f}%'}** |")
ok = [r for r in rows if r[3] > 0]
if ok:
    worst = min(ok, key=lambda r: r[2] / r[3])
    print(f"\n* 最差 seed = {worst[0]}，合并 {worst[2]}/{worst[3]} = {worst[2]/worst[3]*100:.1f}%"
          f"（门 ≥50%）⇒ {'✅ PASS' if worst[2]/worst[3] >= 0.50 else '❌ FAIL'}")
    if any(r[3] < 60 for r in ok):
        print("* ⚠️ 有 seed 的读数还不足 60 局，按坑 29 的房规这个判定还不算定稿。")
PY
date +"%Y-%m-%d %H:%M:%S" > "$MARK"
echo "[s3-confirm] done $(date +%H:%M:%S)"
