#!/usr/bin/env bash
# 档 1 · 多初始位姿：在 rand60（seed 1000..1059 随机初姿 + 专家噪声 0.05）上微调 π₀.₅。
# 评测口径见 STAGE_PLAN.md：验证 seed 3000..（扫描用），测试 seed 2000..2019（定版 20 局），
# 固定 seed 0 作回归。训练/验证/测试三个 seed 区间互不相交。
#
# PRETRAINED=<dir> 可以**热启动续训**（STAGE_PLAN 档 1 的失败预案）：默认从 π₀.₅ 基座起，
# 给了目录就从那个检查点起、配一套全新的 lr 调度（warmup 200）。
# 实测可用：`runs/pi05_rand60_s1/checkpoints/last/pretrained_model` 的 config.json 里
# output_features.action.shape 已经是 [7]、optimizer_lr/dtype/gradient_checkpointing 都在，
# lerobot-train 能当 `--policy.path` 直接吃（与基座目录结构同构，只多 train_config.json）。
# 注意这是**热启动不是 resume**：优化器动量与旧 lr 调度不继承，所以续训段要单独记一条曲线，
# 不要和前一段拼成一条（否则「训练步数 vs 成功率」的横轴是假的）。
set -euo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"
cd "$MG"
PRE_ARGS=()
if [ -n "${PRETRAINED:-}" ]; then PRE_ARGS=(--pretrained "$PRETRAINED"); fi
exec "$MG_PY" code/mg_train.py \
  --policy pi05 \
  --dataset "${DATASET:-rand60}" \
  --steps "${STEPS:-7200}" \
  --batch-size "${BS:-8}" \
  --num-workers 8 \
  --save-freq "${SAVE_FREQ:-500}" \
  --job-name "${JOB:-pi05_${DATASET:-rand60}_s1}" \
  --out "$MG/runs/${JOB:-pi05_${DATASET:-rand60}_s1}" \
  "${PRE_ARGS[@]}" \
  --extra "policy.optimizer_lr=${LR:-1e-4}" \
  --extra "policy.scheduler_warmup_steps=200" \
  --seed "${SEED:-1000}" \
  ${DRY_RUN:+--dry-run}
