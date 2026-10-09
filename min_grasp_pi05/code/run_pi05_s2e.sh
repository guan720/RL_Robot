#!/usr/bin/env bash
# 档 2e · 反向数据翻倍 + 2:1 配比（R1/R2/R3 三个分支的公共处方）
#
# 与档 2 / 档 2c 的关系（一句话：**只动数据，别的一律不动**）：
#   档 2  = mix60f60r 全 120 集（rev:fwd = 1:1）      -> 反向 TEST 30/80 = 37.5% FAIL
#   档 2c = mix60f60r 只 ep 60..119（纯反向）          -> 判定「干扰 vs 任务难」
#   档 2e = mix60f120r（60 正向 + **120** 反向 = 2:1） -> 这一发
#   lr / warmup / batch / chunk_size / seed / 基座（pi05_base_lr044）/ K 口径全部照抄，
#   唯一变量是「反向示范的数量与采样占比」。
#
# ⚠️ 为什么**不能**直接拿 37.5% 跟本档比高低：换数据集 = normalizer 重算。
#   已实测（STAGE_PLAN 档 2e 节，md5 对账）：`--dataset.episodes` 只筛帧、**不重算 stats**，
#   所以同一个数据集内部的两臂 normalizer 逐比特相同；但 mix60f120r 与 mix60f60r 之间**不同**。
#   ⇒ 严格归因需要 1:1 对照臂：`EPISODES_SUBSET=0-119`（60 正向 + 前 60 条反向，
#     由 mg_check_superset.py 保证这 60 条与 mix60f60r 的反向逐比特相同）。
#     该臂**备而不用**：2:1 臂过门就不需要它；2:1 臂不过门它也救不了，直接转去修 A 类抓空。
#
# ⚠️ STEPS 必须由调用方按**等 epoch**算好传进来（frames/batch × 目标 epoch），不要照抄 7600/14400：
#   本档帧数与前两档都不同，照抄步数 = 悄悄改了训练量，那就是第二个变量（README 坑 33）。
#   `bash code/run_pi05_s2e.sh` 不带 STEPS 时会打印按 3.79 epoch 换算出来的建议步数并退出。
set -euo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"
cd "$MG"
DATASET="${DATASET:-mix60f120r}"
JOB="${JOB:-pi05_${DATASET}_s2e}"
# 注意用 `${VAR-default}` 而不是 `${VAR:-default}`：空字符串是**合法值**（= 全 180 集，不加
# --dataset.episodes 这个 flag），用 `:-` 会把"我要全集"悄悄改成"我要 60-119"。
EPISODES_SUBSET="${EPISODES_SUBSET-}"
TARGET_EPOCHS="${TARGET_EPOCHS:-3.79}"     # 与档 2 / 档 2c 同一个 epoch 预算
BS="${BS:-8}"

INFO="$MG/data/$DATASET/meta/info.json"
[ -f "$INFO" ] || { echo "[s2e] FATAL 数据集还没收好：$INFO"; exit 3; }
FRAMES=$("$MG_PY" -c "import json;print(json.load(open('$INFO'))['total_frames'])")
SPE=$("$MG_PY" -c "print($FRAMES/$BS)")
SF="${SAVE_FREQ:-2000}"
# 取整到 SAVE_FREQ 的整数倍：lerobot 的 `last` 是最后一次 save 的软链，若总步数不是
# save_freq 的整数倍，`last` 指向的步数就与 STEPS 不符 —— 档 1 的 kcurve 就因为
# 「把 006000 的读数当成 7200」作废过一格，别在档 2e 重演。
SUGGEST=$("$MG_PY" -c "print(int(round($SPE*$TARGET_EPOCHS/$SF)*$SF))")
echo "[s2e] 出处 $INFO: total_frames=$FRAMES / batch=$BS => steps/epoch=$SPE"
EXACT=$("$MG_PY" -c "print(round($SPE*$TARGET_EPOCHS,1))")
echo "[s2e] 等 epoch 步数 = $SPE × $TARGET_EPOCHS ep = $EXACT -> 取整到 save_freq($SF) = $SUGGEST"
# 公式对账（不是自检通过就完事，要把差多少写出来）：同一公式套 mix60f60r（30447 帧/bs8）
# 给 3805.875 × 3.79 = 14424.3，而档 2 实际用的是 **14400**（差 0.17%）⇒ 公式与历史口径一致。
echo "[s2e] 公式对账：套 mix60f60r 得 3805.875×3.79=14424.3，档 2 实际用 14400（差 0.17%，一致）"
if [ -z "${STEPS:-}" ]; then
  echo "[s2e] 没给 STEPS，不发车。要跑就：STEPS=$SUGGEST bash code/run_pi05_s2e.sh"
  exit 0
fi
echo "[s2e] STEPS=$STEPS => 实际 $( "$MG_PY" -c "print(round($STEPS/$SPE,3))" ) epoch"
echo "[s2e] EPISODES_SUBSET='${EPISODES_SUBSET}'（空 = 全 180 集 = 2:1 臂）"

exec "$MG_PY" code/mg_train.py \
  --policy pi05 \
  --dataset "$DATASET" \
  --episodes-subset "$EPISODES_SUBSET" \
  --steps "$STEPS" \
  --batch-size "$BS" \
  --num-workers "${NUM_WORKERS:-8}" \
  --save-freq "$SF" \
  --job-name "$JOB" \
  --out "$MG/runs/$JOB" \
  --extra "policy.optimizer_lr=${LR:-1e-4}" \
  --extra "policy.scheduler_warmup_steps=200" \
  --seed "${SEED:-1000}" \
  ${DRY_RUN:+--dry-run}
