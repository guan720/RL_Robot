#!/usr/bin/env bash
# 档 7B · bs32 等 epoch 训练启动器（预注册出处 runs/S7_PREREG.md §3 格 7B）
#
# 与档 3r（batch8）**只动下面这组绑定项**，其余逐项照抄：
#   batch 8 -> 32（唯一被检验的变量）
#   steps 22000 -> 5500（等 epoch 3.79 的算术后果）
#   save_freq 2000 -> 500（保证 last==steps，且 11 格的 epoch 网格与 batch8 **逐格相同**）
#   log_freq 100 -> 25（保证 AverageMeter 窗 = 25×32 = 800 样本，与 batch8 的 100×8 同窗）
#   lr 1e-4 -> 2e-4（sqrt 缩放：Adam 每步位移量级 ≈ lr，步数少 4× 而 lr 不变会系统性欠拟合）
# 不动：数据集 mix60f120r / 基座 pi05_base_lr044 / warmup 200 / chunk_size 50 / bf16 /
#       grad-ckpt on（7A 实测关掉必 OOM）/ num_workers 8 / 评测口径 K=10。
#
# ⚠️ 步数不许照抄，必须由 mg_probe_batch.equal_epoch_plan 现算（坑 33）：
#    它是 7A 探针用的同一个函数 ⇒ 投影墙钟与实际发车步数同源，不会各说各话（坑 54）。
# ⚠️ 不带 STEPS 直接跑只打印换算过程就退出（与 run_pi05_s2e.sh 同一个习惯）。
set -euo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"
cd "$MG"
DATASET="${DATASET:-mix60f120r}"
BS="${BS:-32}"
SEED="${SEED:-2000}"
LR="${LR:-2e-4}"
TARGET_EPOCHS="${TARGET_EPOCHS:-3.79}"
N_CELLS="${N_CELLS:-11}"
JOB="${JOB:-pi05_${DATASET}_s7b_bs${BS}_seed${SEED}}"

INFO="$MG/data/$DATASET/meta/info.json"
[ -f "$INFO" ] || { echo "[s7b] FATAL 数据集还没收好：$INFO"; exit 3; }

plan=$("$MG_PY" - <<PY
import json, sys
sys.path.insert(0, "$MG/code")
from mg_probe_batch import equal_epoch_plan, lr_autoscale
fr = int(json.load(open("$INFO"))["total_frames"])
p = equal_epoch_plan(fr, $BS, $TARGET_EPOCHS, $N_CELLS)
a = lr_autoscale(p["steps"])
lf = max(1, round(800 / $BS))     # 800 = batch8 × log_freq100 的样本窗
print(f'{fr} {p["steps_per_epoch"]} {p["steps"]} {p["epochs"]} {p["save_freq"]} {p["n_cells"]} {p["cell_epoch"]} {lf} {a["actual_warmup"]} {a["warmup_frac_pct"]}')
PY
)
read -r FRAMES SPE STEPS_CALC EPOCHS SF CELLS CELLEP LOGF AW WFRAC <<< "$plan"
echo "[s7b] 出处 $INFO: total_frames=$FRAMES / batch=$BS => steps/epoch=$SPE"
echo "[s7b] 等 epoch 步数 = $SPE × $TARGET_EPOCHS ep = $STEPS_CALC（实际 $EPOCHS ep）"
echo "[s7b] save_freq=$SF => 格数=$CELLS、每格 $CELLEP epoch"
echo "[s7b] 网格对账：batch8 历史网格每格 2000/5803.25 = 0.3446 epoch；本档每格 $CELLEP epoch"
echo "[s7b] log_freq=$LOGF（= 800/$BS，样本窗与 batch8 的 log_freq=100 相同 ⇒ grdn/loss 可比）"
echo "[s7b] LR 自动缩放（lerobot/optim/schedulers.py:99-104）：warmup 200 -> $AW（占全程 $WFRAC%）"
echo "[s7b] 对账：batch8@22000 的 warmup 占 0.6636%、bs16@11000 占 0.6636%（真日志锚）⇒ 形状守恒"
if [ -z "${STEPS:-}" ]; then
  echo "[s7b] 没给 STEPS，不发车。要跑就：STEPS=$STEPS_CALC SAVE_FREQ=$SF LOG_FREQ=$LOGF bash code/run_pi05_s7b.sh"
  exit 0
fi
[ "$STEPS" = "$STEPS_CALC" ] || { echo "[s7b] FATAL 传入 STEPS=$STEPS ≠ 现算 $STEPS_CALC（坑 33：会悄悄改训练量）"; exit 3; }
[ "$SAVE_FREQ" = "$SF" ] || { echo "[s7b] FATAL 传入 SAVE_FREQ=$SAVE_FREQ ≠ 现算 $SF（last 会指错格，坑 38）"; exit 3; }
[ "$LOG_FREQ" = "$LOGF" ] || { echo "[s7b] FATAL 传入 LOG_FREQ=$LOG_FREQ ≠ 现算 $LOGF（样本窗不同 ⇒ grdn 不可比）"; exit 3; }
echo "[s7b] JOB=$JOB  SEED=$SEED  lr=$LR  grad_ckpt=on  投影墙钟见 runs/s7_probe/timing.md"

exec "$MG_PY" code/mg_train.py \
  --policy pi05 \
  --dataset "$DATASET" \
  --episodes-subset "" \
  --steps "$STEPS" \
  --batch-size "$BS" \
  --num-workers "${NUM_WORKERS:-8}" \
  --save-freq "$SAVE_FREQ" \
  --log-freq "$LOG_FREQ" \
  --job-name "$JOB" \
  --out "$MG/runs/$JOB" \
  --extra "policy.optimizer_lr=${LR}" \
  --extra "policy.scheduler_warmup_steps=200" \
  --seed "$SEED" \
  ${DRY_RUN:+--dry-run}
