#!/usr/bin/env bash
# 最小抓取链路 · 阶段 1 一键跑通（固定物体 + 固定初姿 -> 脚本专家示范 -> 小数据过拟合 -> 闭环执行）
#
# 顺序是刻意的：每一步都是下一步的前置闸，任何一步 FAIL 就停下来修，不带着疑问往下跑。
#   1. 契约探针（确定性 / 动作轴向与步长 / 夹爪语义 / 图像 / 计时）
#   2. 脚本专家自证（链路上界：专家不 100% 成功就不采数据）
#   3. 采集示范 -> LeRobotDataset + 原始 npz
#   4. 重放对齐验证（数据集里的动作喂回环境，必须仍然成功）
#   5. ACT 小数据过拟合训练（同步 BC，出第一个 policy 指标）
#   6. 闭环评测（从示范初态出发，成功 = 环境真值 latch）
#
# 用法：
#   bash code/run_stage1.sh                # 全流程（ACT 默认 20000 步）
#   STEPS=3000 EPISODES=5 bash code/run_stage1.sh   # 冒烟
#   SKIP_TRAIN=1 bash code/run_stage1.sh   # 只到第 4 步
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 2
source code/env.sh

EPISODES="${EPISODES:-10}"
NAME="${NAME:-fixed${EPISODES}}"
STEPS="${STEPS:-20000}"
BATCH="${BATCH:-8}"
EVAL_EPS="${EVAL_EPS:-10}"
SKIP_TRAIN="${SKIP_TRAIN:-0}"
RUN_DIR="runs/act_${NAME}_$(date +%Y%m%d_%H%M%S)"

step() { printf '\n========== [%s] %s ==========\n' "$1" "$2"; }

step 1 "契约探针"
$MG_PY code/mg_probe.py --determinism --axes --gripper --images --timing || exit 1

step 2 "脚本专家自证（3 局，必须全成功）"
$MG_PY code/mg_probe.py --expert --episodes 3 || exit 1

step 3 "采集 $EPISODES 条示范 -> data/$NAME"
$MG_PY code/mg_collect.py --episodes "$EPISODES" --name "$NAME" --video || exit 1

step 4 "重放对齐验证（数据集动作 -> 环境）"
$MG_PY code/mg_probe.py --replay "data/${NAME}_raw.npz" || exit 1

if [ "$SKIP_TRAIN" = "1" ]; then
  echo "SKIP_TRAIN=1：链路已验到第 4 步（数据侧全通），未训练。"
  exit 0
fi

step 5 "ACT 过拟合训练（$STEPS 步）-> $RUN_DIR"
$MG_PY code/mg_train.py --policy act --dataset "$NAME" --steps "$STEPS" --batch-size "$BATCH" \
    --save-freq 1000 --out "$RUN_DIR" || exit 1

step 6 "闭环评测（从示范初态出发，$EVAL_EPS 局）"
$MG_PY code/mg_eval.py --ckpt "$RUN_DIR/checkpoints/last/pretrained_model" \
    --episodes "$EVAL_EPS" --video --demo-npz "data/${NAME}_raw.npz" || exit 1

echo
echo "阶段 1 完成。下一步（π₀.₅ 微调）："
echo "  \$MG_PY code/mg_train.py --policy pi05 --dataset $NAME --steps 4000 --batch-size 2 --save-freq 500"
