#!/usr/bin/env bash
# 档 7G · **条件发车**链：把 epoch 预算固定在 3.102、用**新 seed** 前瞻验证 seed 稳健性
#         （预注册：runs/S7F_PREREG.md §3 格 7G，2026-10-04 10:22 落盘，早于任何 7G 读数）
#
# 为什么必须新 seed（4000/5000/6000）：3.102 ep 这个预算是**看着 seed1000/2000 的 val 峰挑的**
#   （回溯），用同一批 seed 去验证无法消除选择偏差（坑 27/42）⇒ 只有新 seed 上的前瞻结果才算数。
# 为什么是条件发车：F1/F2 是零训练的回溯诊断，`MIN3102 ≥ 40/80 = 50%` 才值得花这 22.4 h。
#   不满足 ⇒ 写 `runs/s7g.SKIPPED` 并 exit 0 —— 这是**预注册的分支，不是失败**（坑 62 的形状）。
#
# 每个 seed 的读数与档 3r **逐项同口径**（只换 epoch 预算与 seed）：
#   bs8 / 18000 步（=3.1017 ep）/ lr 1e-4 / save_freq 2000（9 格 + `last`==018000）/ warmup 200
#   -> 9 格反向 val 扫描（每格 20 局、K=10、val seed 8000..8019）
#   -> TEST 关门：反向 4×20（seed 7000..7019）+ 正向护栏 1×20（seed 2000..2019）
# 判据（`code/mg_verdict_s7f.py --mode g`，全部出自预注册）：
#   G1 主门 = 最差 seed 的反向放宽 ≥ 50%（与档 3r/7C **完全同一条**使命门）；
#   G2 护栏 = 三个 seed 的正向掉幅 vs 193/300=64.3% 都 ≤15 pp；G3 副 = 极差 vs 38.8 pp（只读方向）。
# ⚠️ 关门读数一律 `last`（=018000），**不做 val 选点**；评测路径写数字格以便出身核对（见 chain_s7f.sh 头注）。
#
# 房规：setsid 发车（坑 37）；done/SKIPPED 标记 printf 写 + `[ -s ]` 自检（坑 43）；路径全绝对（坑 41）；
#   完成与否一律看**磁盘产物**、不看进程表（坑 22(e)）；有产物就跳过 ⇒ 可断点续跑；不碰冻结文件。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
NOISE='robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation'

DATASET="mix60f120r"
STEPS="${STEPS:-18000}"          # = round(5803.25 × 3.102 / 2000) × 2000（本链在闸里现算对账）
SAVE_FREQ="${SAVE_FREQ:-2000}"   # 9 格 + 终点格
TARGET_EPOCHS="${TARGET_EPOCHS:-3.102}"
LR="${LR:-1e-4}"
BS="${BS:-8}"
NCELLS="${NCELLS:-9}"
SEEDS=(4000 5000 6000)           # 预注册写死：必须是**新** seed
EP="${EP:-20}"; REPS="${REPS:-4}"; K="${K:-10}"
REV_SEED0="${REV_SEED0:-7000}"; FWD_SEED0="${FWD_SEED0:-2000}"; VAL_SEED0="${VAL_SEED0:-8000}"
MIN_FREE_EVAL="${MIN_FREE_EVAL:-9000}"
MIN_FREE_TRAIN="${MIN_FREE_TRAIN:-36000}"   # 7A 实测 bs8+gc1 峰值 33799 MiB
WAIT_H="${WAIT_H:-30}"                      # 档 7F 最长分支 ≈12.7 h（F1+F2+F3+F4）

NPZ_R="$MG/data/${DATASET}_rev_raw.npz"
NPZ_F="$MG/data/${DATASET}_raw.npz"
DIAG="$MG/runs/S7F_DIAG.md"
VERD="$MG/runs/S7G_VERDICT.md"
MARK="$MG/runs/s7g.done"
FAILED="$MG/runs/s7g.FAILED"
SKIPPED="$MG/runs/s7g.SKIPPED"

die  () { echo "[s7g] FATAL $*" | tee -a "$FAILED"; exit 4; }
skip () { printf '%s 档7G 不发车（预注册分支）原因=%s 依据=runs/S7F_PREREG.md §3 决策树「MIN3102 < 40/80 ⇒ 不触发 7G」\n' \
            "$(date '+%F %T')" "$1" > "$SKIPPED"
          [ -s "$SKIPPED" ] || echo "[s7g] SKIPPED 写空了（坑 43 复发）"
          echo "[s7g] SKIP：$1"; exit 0; }

# ── 0. 等档 7F 收工（认产物，不认进程表 —— 坑 22(e)）─────────────────────────
if [ -s "$MARK" ]; then echo "[s7g] 已收工（$MARK 在）：$(head -1 "$MARK")"; exit 0; fi
echo "[s7g] === 等档 7F 收工（上限 ${WAIT_H} h）=== $(date '+%F %T')"
got=""
for _ in $(seq 1 $((WAIT_H * 60))); do
  [ -s "$MG/runs/s7f.done" ]   && { got="done";   break; }
  [ -s "$MG/runs/s7f.FAILED" ] && { got="FAILED"; break; }
  sleep 60
done
case "$got" in
  done)   echo "[s7g] 7F 收工：$(head -1 "$MG/runs/s7f.done")" ;;
  FAILED) skip "档7F 写了 runs/s7f.FAILED：$(head -1 "$MG/runs/s7f.FAILED")" ;;
  "")     die "等 ${WAIT_H} h 仍没有 runs/s7f.done（FAILED 也没有）⇒ 7F 可能静默死亡，看 logs/ALERTS.log" ;;
esac

# ── 1. 预注册闸（全部看盘上产物）────────────────────────────────────────────
[ -s "$DIAG" ] || die "有 s7f.done 却没有 runs/S7F_DIAG.md ⇒ 先手工跑 code/mg_verdict_s7f.py --mode f"
grep -q '不采信' "$MG/runs/S7_VERDICT.md" 2>/dev/null || die "runs/S7_VERDICT.md 里没有「不采信」⇒ 上游前提变了"
TRIG=$(grep -m1 -o '7G_TRIGGER=[A-Z]*' "$DIAG" | head -1)
FR=$("$MG_PY" -c "import json;print(json.load(open('$MG/data/$DATASET/meta/info.json'))['total_frames'])")
[ "$FR" = "46426" ] || die "total_frames=$FR ≠ 46426 ⇒ 等 epoch 步数的分母变了（坑 33）"
[ -f "$NPZ_R" ] && [ -f "$NPZ_F" ] || die "示范 npz 不在：$NPZ_R / $NPZ_F"
# 步数现算对账（不照抄 18000；公式与 run_pi05_s2e.sh 同一个）
CALC=$("$MG_PY" -c "print(int(round($FR/$BS*$TARGET_EPOCHS/$SAVE_FREQ)*$SAVE_FREQ))")
ACT_EP=$("$MG_PY" -c "print(round($STEPS/($FR/$BS),4))")
echo "[s7g] 闸：触发=${TRIG:-无}  steps/epoch=$("$MG_PY" -c "print($FR/$BS)")  现算($TARGET_EPOCHS ep)=$CALC  本链 STEPS=$STEPS（=$ACT_EP ep）"
[ "$CALC" = "$STEPS" ] || die "现算等 epoch 步数 $CALC ≠ 传入 STEPS=$STEPS（坑 33：会悄悄改训练量）"
for SD in "${SEEDS[@]}"; do
  [ -d "$MG/runs/pi05_${DATASET}_s7g_seed${SD}" ] && [ ! -f "$MG/runs/pi05_${DATASET}_s7g_seed${SD}/checkpoints/$(printf '%06d' "$STEPS")/pretrained_model/model.safetensors" ] \
    && die "seed$SD 的 run 目录已存在但终点格不在（lerobot 拒绝已存在的 output_dir ⇒ 需人工处理）"
done
"$MG_PY" "$MG/code/mg_verdict_s7f.py" --selftest > "$MG/logs/verdict_s7f_selftest.log" 2>&1 \
  || die "mg_verdict_s7f 自测不过（看 logs/verdict_s7f_selftest.log）"
[ "$TRIG" = "7G_TRIGGER=YES" ] || skip "runs/S7F_DIAG.md 的触发行是 '${TRIG:-无}'（不是 YES）"
echo "[s7g] 闸全过 ⇒ 发车：3 个新 seed（${SEEDS[*]}）各 ≈6.9 h 训练 + 0.9 h 扫描 + 0.4 h 关门，串行 ≈22.4 h"

# ── 2. 三个 seed 串行 ──────────────────────────────────────────────────────
wait_gpu () {
  local need="$1" f
  for _ in $(seq 1 240); do
    f=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
    [ "${f:-0}" -ge "$need" ] && return 0
    echo "[s7g] 显存 free=${f}MiB < ${need}MiB，等 30 s ... $(date '+%T')"; sleep 30
  done
  return 0
}
one_eval () {  # $1=mode $2=目录名 $3=seed $4=ckpt $5=说明
  local mode="$1" out="$2" sd="$3" ck="$4" what="$5" npz="$NPZ_F"
  [ "$mode" = "reverse" ] && npz="$NPZ_R"
  if [ -f "$MG/runs/$out/eval_summary.json" ]; then echo "[s7g] 跳过（已有产物）$out"; return 0; fi
  [ -f "$ck/model.safetensors" ] || die "权重不在：$ck/model.safetensors（$what）"
  wait_gpu "$MIN_FREE_EVAL"
  echo "[s7g] === $what（$mode K=$K eps=$EP seed=$sd）-> runs/$out === $(date '+%F %T')"
  echo "[s7g]     ckpt=$ck"
  "$MG_PY" code/mg_eval.py --ckpt "$ck" --episodes "$EP" --seed-mode random --seed "$sd" \
      --n-action-steps "$K" --task-mode "$mode" --demo-npz "$npz" \
      --out "$MG/runs/$out" 2>&1 | grep -vE "$NOISE" | grep -E "^  ep|成功率|放宽口径|warn|Error|Traceback"
  [ -f "$MG/runs/$out/eval_summary.json" ] || die "评测没落盘：$out"
}

run_one_seed () {  # $1 = 训练 seed
  local SD="$1"
  local JOB="pi05_${DATASET}_s7g_seed${SD}"
  local RUN="$MG/runs/$JOB"
  local CK="$RUN/checkpoints/$(printf '%06d' "$STEPS")/pretrained_model"
  local rc want rl missing s ND i suf

  if [ -f "$CK/model.safetensors" ]; then
    echo "[s7g] 跳过 seed$SD 训练（已有产物）：$CK"
  else
    wait_gpu "$MIN_FREE_TRAIN"
    echo "[s7g] === 训练 seed$SD：bs$BS / lr$LR / $STEPS 步（=$TARGET_EPOCHS ep）=== $(date '+%F %T')"
    DATASET="$DATASET" BS="$BS" SEED="$SD" LR="$LR" JOB="$JOB" STEPS="$STEPS" \
      SAVE_FREQ="$SAVE_FREQ" TARGET_EPOCHS="$TARGET_EPOCHS" \
      bash "$MG/code/run_pi05_s2e.sh" > "$MG/logs/train_${JOB}.log" 2>&1
    rc=$?; echo "[s7g] seed$SD 训练 rc=$rc $(date '+%F %T') 日志 -> logs/train_${JOB}.log（进度看 ${RUN}_meta/train.log）"
    [ "$rc" -eq 0 ] || die "seed$SD 训练非 0 退出（rc=$rc）"
  fi
  want=$(printf "%06d" "$STEPS"); rl=$(readlink "$RUN/checkpoints/last" 2>/dev/null || echo "")
  echo "[s7g] seed$SD last -> ${rl:-无}（期望 $want）"
  [ "$rl" = "$want" ] || die "seed$SD 的 last 指向 '$rl' 而不是 $want ⇒ 读数会读错权重（坑 38）"
  [ -f "$CK/model.safetensors" ] || die "seed$SD 终点格权重不在：$CK/model.safetensors"
  missing=""
  for s in $(seq "$SAVE_FREQ" "$SAVE_FREQ" "$STEPS"); do
    [ -f "$RUN/checkpoints/$(printf '%06d' "$s")/pretrained_model/model.safetensors" ] || missing="$missing $s"
  done
  [ -z "$missing" ] || die "seed$SD 缺检查点格：$missing ⇒ 扫出来会是断头曲线"

  ND=$(ls -1d "$RUN"/sweep_rev/step_*_rev 2>/dev/null | wc -l)
  if [ "$ND" -ge "$NCELLS" ]; then
    echo "[s7g] 跳过 seed$SD 的 val 扫描（已有 $ND/$NCELLS 格）"
  else
    echo "[s7g] === seed$SD ${NCELLS} 格反向 val 扫描（每格 $EP 局、K=$K、val seed $VAL_SEED0..）=== $(date '+%F %T')"
    wait_gpu "$MIN_FREE_EVAL"
    RUN="$RUN" STEPS_TOTAL="$STEPS" SAVE_FREQ="$SAVE_FREQ" SUB=sweep_rev EPISODES="$EP" K="$K" \
      REV_SEED="$VAL_SEED0" DEMO_REV="$NPZ_R" MIN_FREE_MIB="$MIN_FREE_EVAL" \
      bash "$MG/code/mg_sweep_rev.sh" "$RUN" > "$MG/logs/sweep_${JOB}.log" 2>&1
    rc=$?; echo "[s7g] seed$SD 扫描 rc=$rc $(date '+%F %T') 日志 -> logs/sweep_${JOB}.log"
    [ "$rc" -eq 0 ] || die "seed$SD 的 mg_sweep_rev.sh 退出码 $rc"
    ND=$(ls -1d "$RUN"/sweep_rev/step_*_rev 2>/dev/null | wc -l)
    [ "$ND" -ge "$NCELLS" ] || die "seed$SD 只扫出 $ND 格（应 $NCELLS）⇒ G3 的方向读数做不出来"
  fi

  for i in $(seq 1 "$REPS"); do
    suf=""; [ "$i" -gt 1 ] && suf="_rep$i"
    one_eval reverse "s7g_seed${SD}_rev_test_rand20_k10$suf" "$REV_SEED0" "$CK" "seed$SD 反向 TEST rep$i"
  done
  one_eval forward "s7g_seed${SD}_fwd_test_rand20_k10" "$FWD_SEED0" "$CK" "seed$SD 正向护栏（未见）"
}

for SD in "${SEEDS[@]}"; do
  echo "[s7g] ########## seed $SD ########## $(date '+%F %T')"
  run_one_seed "$SD"
done

# ── 3. 判定汇编（G1/G2/G3，零 GPU）─────────────────────────────────────────
echo "[s7g] === 判定汇编（G1 主门 / G2 护栏 / G3 极差）=== $(date '+%F %T')"
"$MG_PY" "$MG/code/mg_verdict_s7f.py" --mode g > "$VERD" 2> "$MG/logs/verdict_s7g.log"
rc=$?; echo "[s7g] --mode g rc=$rc -> runs/S7G_VERDICT.md"
{ [ "$rc" -eq 0 ] && [ -s "$VERD" ]; } || die "7G 判定没生成或出身核对不过（rc=$rc，看 $VERD 与 logs/verdict_s7g.log）"
G1=$(grep -m1 -o 'G1=[A-Z]*' "$VERD" | head -1)
tail -24 "$VERD"

printf '%s 档7G 完成 seeds=%s 配方=bs%s/%s步(%s ep)/lr%s/save%s 主门=%s 判定=runs/S7G_VERDICT.md 下一步=%s\n' \
  "$(date '+%F %T')" "${SEEDS[*]}" "$BS" "$STEPS" "$ACT_EP" "$LR" "$SAVE_FREQ" "${G1:-未知}" \
  "$([ "${G1:-}" = "G1=PASS" ] && echo '使命证据链补齐->回用户阶梯第6步(纠正数据)' || echo 'epoch预算杠杆也死->转档8(纠正数据),不再烧配方实验')" > "$MARK"
[ -s "$MARK" ] || die "done 标记写空了（坑 43 复发）"
echo "[s7g] 收工 $(date '+%F %T')  标记 -> $MARK"
