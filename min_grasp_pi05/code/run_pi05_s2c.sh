#!/usr/bin/env bash
# 档 2c · 反向单任务消融：同一份 mix60f60r，**只喂反向那 60 集**（ep 60..119），其余与档 2 逐字对齐。
#
# 为什么这一发是必要的（档 2 反向 FAIL 之后只剩两个互斥解释）：
#   H-A 干扰：反向被正向挤掉了 —— 联合训练里正向更容易，优化会往正向漂。
#         证据：同一模型正向 val 到 14000 步还有 5~8/10，反向 val 从 11000 的 5/10 掉到 13000 的 0/10。
#   H-B 任务本身难：反向要伸进有墙的 bin2 抓（运动学极限）、horizon 312 步（正向 240）、
#         成功还要求 can「立着」保持 10 步（专家自己也只有 70%，6 局失败**全是侧躺**）。
#   两者的处方完全相反：H-A 要改**数据配比/采样**，H-B 要改**数据本身或任务口径**。
#   这一发就是把 H-A 单独隔离出来 —— 唯一的变量是「批次里有没有正向帧」。
#
# 严格控制变量（都已实测核对，见 chain_s2c.sh 的发车预检）：
#   * 数据集**同一份** data/mix60f60r，用 lerobot 的 `--dataset.episodes=[60..119]` 过滤；
#   * lerobot 的 DatasetConfig.episodes 只过滤 hf_dataset，**不重算 meta.stats** ⇒
#     normalizer（policy_preprocessor_step_2_normalizer）与档 2 **逐比特相同**，不构成第二个变量；
#   * 已实测：子集 60 集 / 16032 帧，与全集后半段 action **逐比特相同**；
#   * 等 epoch：档 2 = 14400 步 × bs8 / 30447 帧 = 3.79 epoch；
#     本档 = 7600 步 × bs8 / 16032 帧 = **3.79 epoch**（同 epoch，不同帧数）；
#   * lr / warmup / chunk_size / n_action_steps / seed / K 口径全部不动。
set -euo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"
cd "$MG"
DATASET="${DATASET:-mix60f60r}"
JOB="${JOB:-pi05_rev60_s2c}"
exec "$MG_PY" code/mg_train.py \
  --policy pi05 \
  --dataset "$DATASET" \
  --episodes-subset "${EPISODES_SUBSET:-60-119}" \
  --steps "${STEPS:-7600}" \
  --batch-size "${BS:-8}" \
  --num-workers 8 \
  --save-freq "${SAVE_FREQ:-1000}" \
  --job-name "$JOB" \
  --out "$MG/runs/$JOB" \
  --extra "policy.optimizer_lr=${LR:-1e-4}" \
  --extra "policy.scheduler_warmup_steps=200" \
  --seed "${SEED:-1000}" \
  ${DRY_RUN:+--dry-run}
