#!/usr/bin/env bash
# 护栏 G2 的**加功效**补读（档 2c 主链跑完之后再发车，别跟训练抢 GPU）。
#
# 为什么要补（坑 32）：
#  1) 主链的 G2 用 `--seed 5000`（10 局 = seed 5000..5009），但反向训练 seed **不是连续的**
#     —— 采集时有重试，实测 60 个 seed 散在 [5000,5092]，**5002 根本不在训练集里**。
#     所以主链那 10 局只有 9 局是真训练 seed（偏差方向是**更保守**，即更不容易报出记忆）。
#  2) 更要紧的是 n=10 的功效：对 TEST 30/80 做 Fisher，训练 seed 要 **≥8/10** 才触发 p<0.05。
#     也就是说这道护栏只能抓「碾压式记忆」，20 pp 量级的记忆它**看不见**（5/10→p=0.50，7/10→p=0.085）。
#
# 补读口径：唯一一段完全落在训练集里的连续 10-seed 窗口是 **5062..5071**（已逐 seed 核对）。
# 跑 4 读 = 40 局真训练 seed，与 TEST 的 80 局做 Fisher，才有资格谈「有没有记忆」。
# 评测端没钉 torch RNG（坑 29），所以同 seed 重复读是**独立**的 4 次采样，可合并。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
JOB="${JOB:-pi05_rev60_s2c}"
CK="${CK:-$MG/runs/$JOB/checkpoints/last/pretrained_model}"
SEED="${SEED:-5062}"
REPS="${REPS:-4}"
NPZ_R="$MG/data/mix60f60r_rev_raw.npz"
NOISE='robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation'

[ -f "$CK/model.safetensors" ] || { echo "[g2supp] FATAL 没有检查点：$CK"; exit 3; }
# 发车前把 seed 窗口逐个核对进训练集（坑 32 的房规：别假设 seed 连续）
"$MG_PY" - "$SEED" "$NPZ_R" <<'PY' || exit 4
import sys, numpy as np
seed, npz = int(sys.argv[1]), sys.argv[2]
tr = set(np.load(npz, allow_pickle=True)["seeds"].tolist())
win = list(range(seed, seed + 10))
miss = [s for s in win if s not in tr]
if miss:
    print(f"[g2supp] FATAL seed 窗口 {seed}..{seed+9} 有 {len(miss)} 个不在训练集里：{miss}")
    print("        反向训练 seed 唯一干净的连续窗口是 5062..5071（坑 32）")
    sys.exit(4)
print(f"[g2supp] 预检 OK：{seed}..{seed+9} 全部是反向训练 seed")
PY

for i in $(seq 1 "$REPS"); do
  suffix=""; [ "$i" -gt 1 ] && suffix="_rep$i"
  out="runs/s2c_g2supp_rev_train10_k10${suffix}"
  [ -f "$MG/$out/eval_summary.json" ] && { echo "[g2supp] 跳过（已有产物）$out"; continue; }
  echo "[g2supp] === 真训练 seed $SEED..$((SEED+9)) rep$i === $(date +%H:%M:%S)"
  "$MG_PY" code/mg_eval.py --ckpt "$CK" --episodes 10 --seed-mode random --seed "$SEED" \
      --n-action-steps 10 --task-mode reverse --demo-npz "$NPZ_R" \
      --out "$MG/$out" 2>&1 | grep -vE "$NOISE" | grep -E "^  ep|成功率"
done

echo "[g2supp] === 合并 + Fisher === $(date +%H:%M:%S)"
"$MG_PY" - <<'PY'
import json, sys
from pathlib import Path
sys.path.insert(0, "code")
from mg_verdict_s2 import fisher_two_sided
RUNS = Path("runs")
def pool(pats):
    ns = ne = 0
    for d in sorted(RUNS.glob(pats)):
        f = d / "eval_summary.json"
        if f.exists():
            j = json.loads(f.read_text()); ns += j["n_success"]; ne += j["episodes"]
    return ns, ne
ts, tn = pool("s2c_g2supp_rev_train10_k10*")
es, en = pool("s2c_rev_test_rand20_k10*")
if not tn or not en:
    print(f"[g2supp] 产物不全：训练 seed {ts}/{tn}，TEST {es}/{en}"); sys.exit(1)
p = fisher_two_sided(ts, tn, es, en)
d = (ts / tn - es / en) * 100
print(f"[g2supp] 真训练 seed {ts}/{tn} = {ts/tn*100:.1f}%  vs  未见 TEST {es}/{en} = {es/en*100:.1f}%")
print(f"[g2supp] 差 {d:+.1f} pp，Fisher 双侧 p={p:.4f}")
print("[g2supp] ⇒ " + ("⚠️ **有记忆证据**（p<0.05 且差 >10 pp）：档 2c 的主读数里混了记忆成分，"
                        "R1/R2/R3 都要打折看" if (p < 0.05 and d > 10)
                        else "✅ 无记忆证据：主读数可以按未见初姿读"))
PY
date +"%Y-%m-%d %H:%M:%S seed=$SEED reps=$REPS" > "$MG/runs/g2supp.done"
echo "[g2supp] done $(date +%H:%M:%S)"
