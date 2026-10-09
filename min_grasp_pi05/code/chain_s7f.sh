#!/usr/bin/env bash
# 档 7F · 7B 失败归因 + 「epoch 预算」回溯诊断（预注册：runs/S7F_PREREG.md，2026-10-04 10:22 落盘）
#
# 顺序：发车闸(8 条) -> F1(坏 seed 2000 的 018000 上 TEST) -> F2(seed 1000/3000 同一格)
#       -> 早期触发读数(_diag) -> F3(bs8/5500 步，与 7B **同更新数**) -> 诊断汇编 runs/S7F_DIAG.md
#       -> 若 `7G_TRIGGER=NO` 再跑 F4(bs32/5500 步/**lr 1e-4**，与 7B **唯一差 lr**) -> 诊断重跑
#
# 三条设计红线（都出自预注册，不许在链里改）：
#   1) F1/F2 是**回溯**读数（018000 = epoch 3.102 是看着 val 峰挑的）⇒ 只用来决定「7G 的 22.4 h
#      值不值得花」，**不是**使命门通过的证据（坑 27/42）。触发规则写死：MIN3102 ≥ 40/80。
#   2) F3 与 7B **同时**差 batch 和 epoch ⇒ 只能**排除** H-B（步数），不给 batch 的效应量（坑 57）。
#   3) F3 在触发/不触发两个分支里**都跑**（2.5 h 买机理叙事的正确性）；F4 只在 NO 分支跑。
#
# ⚠️ 评测用的 ckpt 路径一律写**数字格**（`checkpoints/018000|005500/pretrained_model`），不用 `last`：
#   `mg_eval.py` 把传进去的路径原样记进 `eval_summary.json` 的 `policy_ckpt`，而
#   `mg_verdict_s7f.py` 的出身核对要求尾串是数字格（坑 38/42）。所以本链先按坑 38 核对
#   `readlink last == %06d(STEPS)`，**再**用数字格路径评测 —— 两道守卫都在，且判定工具读得到正确出身。
# ⚠️ 显存守卫的数字与预注册 §7 第 7 条有一处不一致（那里写 bs8 训练 ≥20000 MiB，
#   但同一句引用的实测峰值是 33799 MiB ⇒ 20000 必然 OOM）。本链按**实测峰值**取
#   bs8 ≥36000 / bs32 ≥45000 / 评测 ≥9000。这是资源守卫不是科学判据，故不改预注册正文。
#
# 房规：setsid 发车（坑 37）；done 标记 printf 写 + `[ -s ]` 自检（坑 43）；路径全绝对（坑 41）；
#   每个读数「有产物就跳过」⇒ 可断点续跑；不编辑运行中的 .sh（坑 22(d)）；
#   不碰冻结文件（mg_eval / mg_env* / mg_sweep_rev / mg_epoch_curve / mg_expert / mg_verdict_s3r / mg_verdict_s7）。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
NOISE='robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation'

DATASET="mix60f120r"
EP="${EP:-20}"                 # 每次评测 20 局（与档 3r/7B 逐项同口径）
REPS="${REPS:-4}"              # 反向 TEST 4×20 = 80 局
K="${K:-10}"                   # n_action_steps
EP_STEP="${EP_STEP:-18000}"    # F1/F2 读的格 = epoch 3.102
F3_JOB="${F3_JOB:-pi05_${DATASET}_s7f_bs8_5500_seed2000}"
F4_JOB="${F4_JOB:-pi05_${DATASET}_s7f_bs32_lr1e4_seed2000}"
F3_STEPS="${F3_STEPS:-5500}"; F3_BS="${F3_BS:-8}";  F3_SAVE="${F3_SAVE:-5500}"; F3_LR="${F3_LR:-1e-4}"; F3_SEED="${F3_SEED:-2000}"
F4_STEPS="${F4_STEPS:-5500}"; F4_BS="${F4_BS:-32}"; F4_SAVE="${F4_SAVE:-500}";  F4_LOG="${F4_LOG:-25}";  F4_LR="${F4_LR:-1e-4}"; F4_SEED="${F4_SEED:-2000}"
MIN_FREE_EVAL="${MIN_FREE_EVAL:-9000}"
MIN_FREE_BS8="${MIN_FREE_BS8:-36000}"      # 7A 实测 bs8+gc1 峰值 33799 MiB
MIN_FREE_BS32="${MIN_FREE_BS32:-45000}"    # 7A 实测 bs32+gc1 峰值 41671 MiB
REV_SEED0="${REV_SEED0:-7000}"             # TEST 反向窗口 7000..7019
FWD_SEED0="${FWD_SEED0:-2000}"             # 正向护栏窗口 2000..2019
VAL_SEED0="${VAL_SEED0:-8000}"             # F4 的 11 格 val 扫描窗口

NPZ_R="$MG/data/${DATASET}_rev_raw.npz"
NPZ_F="$MG/data/${DATASET}_raw.npz"
DIAG="$MG/runs/S7F_DIAG.md"
INTERIM="$MG/runs/_diag/s7f_trigger_interim.md"
MARK="$MG/runs/s7f.done"
FAILED="$MG/runs/s7f.FAILED"

die () { echo "[s7f] FATAL $*" | tee -a "$FAILED"; exit 4; }

wait_gpu () {  # $1 = 需要的 free MiB
  local need="$1" f
  for _ in $(seq 1 240); do
    f=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
    [ "${f:-0}" -ge "$need" ] && return 0
    echo "[s7f] 显存 free=${f}MiB < ${need}MiB，等 30 s ... $(date '+%T')"; sleep 30
  done
  echo "[s7f] 等了 2 h 显存仍不足 ${need}MiB（不抢卡，继续尝试）"; return 0
}

# ── 0. 发车闸（预注册 §7 的 8 条，全部看盘上产物）───────────────────────────
echo "[s7f] === 发车闸 === $(date '+%F %T')"
[ -s "$MARK" ]        && die "闸8：runs/s7f.done 已在 ⇒ 本档已收工，不重复跑"
[ -s "$MG/runs/s7b.done" ]     || die "闸1：runs/s7b.done 不在（上游 7B 没收工）"
[ -s "$MG/runs/S7_VERDICT.md" ] || die "闸1：runs/S7_VERDICT.md 不在"
grep -q '不采信' "$MG/runs/S7_VERDICT.md" || die "闸2：S7_VERDICT.md 里没有「不采信」⇒ 本档前提（7B 判退化）不成立"
for SD in 1000 2000 3000; do
  case "$SD" in
    1000) R8="pi05_${DATASET}_s2e" ;;
    2000) R8="pi05_${DATASET}_s3r_seed2000" ;;
    3000) R8="pi05_${DATASET}_s3r_seed3000" ;;
  esac
  [ -f "$MG/runs/$R8/checkpoints/$(printf '%06d' "$EP_STEP")/pretrained_model/model.safetensors" ] \
    || die "闸3：seed$SD 的 epoch3.102 权重不在（$R8/checkpoints/$(printf '%06d' "$EP_STEP")）"
done
FR=$("$MG_PY" -c "import json;print(json.load(open('$MG/data/$DATASET/meta/info.json'))['total_frames'])")
[ "$FR" = "46426" ] || die "闸4：total_frames=$FR ≠ 46426 ⇒ 等 epoch 步数的分母变了（坑 33）"
[ -f "$NPZ_R" ] || die "闸5：反向示范 npz 不在：$NPZ_R"
[ -f "$NPZ_F" ] || die "闸5：正向示范 npz 不在：$NPZ_F"
"$MG_PY" "$MG/code/mg_verdict_s7f.py" --selftest > "$MG/logs/verdict_s7f_selftest.log" 2>&1 \
  || die "闸6：mg_verdict_s7f 自测不过（看 logs/verdict_s7f_selftest.log）"
free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
[ "${free:-0}" -ge "$MIN_FREE_EVAL" ] || die "闸7：GPU free=${free}MiB < ${MIN_FREE_EVAL}MiB（别的实验在跑，不抢卡）"
echo "[s7f] 闸 1-8 全过（GPU free=${free}MiB，selftest 见 logs/verdict_s7f_selftest.log）$(date '+%T')"

# ── 通用评测（口径与档 3r/7B 逐项相同：K=10、20 局、random seed 窗口）────────
one_eval () {  # $1=mode $2=目录名 $3=seed $4=ckpt $5=说明
  local mode="$1" out="$2" sd="$3" ck="$4" what="$5" npz="$NPZ_F"
  [ "$mode" = "reverse" ] && npz="$NPZ_R"
  if [ -f "$MG/runs/$out/eval_summary.json" ]; then echo "[s7f] 跳过（已有产物）$out"; return 0; fi
  [ -f "$ck/model.safetensors" ] || die "权重不在：$ck/model.safetensors（$what）"
  wait_gpu "$MIN_FREE_EVAL"
  echo "[s7f] === $what（$mode K=$K eps=$EP seed=$sd）-> runs/$out === $(date '+%F %T')"
  echo "[s7f]     ckpt=$ck"   # 出处打进日志（坑 30）
  "$MG_PY" code/mg_eval.py --ckpt "$ck" --episodes "$EP" --seed-mode random --seed "$sd" \
      --n-action-steps "$K" --task-mode "$mode" --demo-npz "$npz" \
      --out "$MG/runs/$out" 2>&1 | grep -vE "$NOISE" | grep -E "^  ep|成功率|放宽口径|warn|Error|Traceback"
  [ -f "$MG/runs/$out/eval_summary.json" ] || die "评测没落盘：$out"
}

test_block () {  # $1=目录前缀 $2=ckpt $3=说明（反向 4×20 + 正向 1×20）
  local pre="$1" ck="$2" what="$3" i suf
  for i in $(seq 1 "$REPS"); do
    suf=""; [ "$i" -gt 1 ] && suf="_rep$i"
    one_eval reverse "${pre}_rev_test_rand20_k10$suf" "$REV_SEED0" "$ck" "$what 反向 TEST rep$i"
  done
  one_eval forward "${pre}_fwd_test_rand20_k10" "$FWD_SEED0" "$ck" "$what 正向护栏（未见）"
}

diag_out () {  # $1=目标文件 $2=说明；rc≠0 一律 die（判定工具自己会把出身问题写成 rc=3）
  local out="$1" what="$2" rc
  echo "[s7f] === 诊断汇编（$what）=== $(date '+%F %T')"
  "$MG_PY" "$MG/code/mg_verdict_s7f.py" --mode f > "$out" 2> "$MG/logs/verdict_s7f.log"
  rc=$?; echo "[s7f] --mode f rc=$rc -> ${out#$MG/}"
  { [ "$rc" -eq 0 ] && [ -s "$out" ]; } || die "诊断没生成或出身核对不过（rc=$rc，看 $out 与 logs/verdict_s7f.log）"
}

# ── 1. F1 + F2：三个 batch8 seed 的 epoch3.102 检查点在 TEST 上（**零训练**）──
for SD in 2000 1000 3000; do
  case "$SD" in
    1000) R8="pi05_${DATASET}_s2e";            TAG="F2" ;;
    2000) R8="pi05_${DATASET}_s3r_seed2000";   TAG="F1" ;;
    3000) R8="pi05_${DATASET}_s3r_seed3000";   TAG="F2" ;;
  esac
  CK8="$MG/runs/$R8/checkpoints/$(printf '%06d' "$EP_STEP")/pretrained_model"
  echo "[s7f] ########## $TAG · seed$SD · epoch3.102（$R8）########## $(date '+%F %T')"
  test_block "s7f_seed${SD}_ep3102" "$CK8" "$TAG seed$SD@3.102ep"
done

# 早期触发读数：F1/F2 一齐就能算 MIN3102（比等 F3 早 ~2.5 h 知道 7G 值不值得花 22.4 h）。
# 落在 _diag/ 下，**不覆盖**正式判定文件 runs/S7F_DIAG.md（后者要等 F3 归因读数）。
mkdir -p "$MG/runs/_diag"
"$MG_PY" "$MG/code/mg_verdict_s7f.py" --mode f > "$INTERIM" 2> "$MG/logs/verdict_s7f_interim.log"
rc=$?
if [ "$rc" -eq 0 ]; then
  echo "[s7f] 早期触发读数（F1/F2，回溯）：$(grep -m1 '7G_TRIGGER=' "$INTERIM")  -> ${INTERIM#$MG/}"
else
  echo "[s7f] 注意：早期触发读数 rc=$rc（不阻塞，正式诊断在 F3 之后）：logs/verdict_s7f_interim.log"
fi

# ── 2. F3：bs8 / 5500 步 / lr1e-4 / seed2000（与 7B **同更新数**，只排除 H-B）──
RUN3="$MG/runs/$F3_JOB"
CK3="$RUN3/checkpoints/$(printf '%06d' "$F3_STEPS")/pretrained_model"
echo "[s7f] ########## F3 · $F3_JOB（bs$F3_BS / $F3_STEPS 步 = 0.948 ep / lr$F3_LR）########## $(date '+%F %T')"
if [ -f "$CK3/model.safetensors" ]; then
  echo "[s7f] 跳过 F3 训练（已有产物）：$CK3"
else
  # run_pi05_s2e.sh 只打印换算、不断言 STEPS（本臂是**有意不等 epoch** 的对照，
  # 它的 SUGGEST=22000 与本臂的 5500 不同是设计如此，不是坑 33）。
  [ -d "$RUN3" ] && die "F3 的 run 目录已存在但终点格权重不在：$RUN3（lerobot 拒绝已存在的 output_dir ⇒ 需人工看 ${RUN3}_meta/train.log）"
  wait_gpu "$MIN_FREE_BS8"
  DATASET="$DATASET" BS="$F3_BS" SEED="$F3_SEED" LR="$F3_LR" JOB="$F3_JOB" \
    STEPS="$F3_STEPS" SAVE_FREQ="$F3_SAVE" \
    bash "$MG/code/run_pi05_s2e.sh" > "$MG/logs/train_${F3_JOB}.log" 2>&1
  rc=$?; echo "[s7f] F3 训练 rc=$rc $(date '+%F %T') 日志 -> logs/train_${F3_JOB}.log（进度看 ${RUN3}_meta/train.log）"
  [ "$rc" -eq 0 ] || die "F3 训练非 0 退出（rc=$rc）"
fi
# 坑 38：`last` 是每次 save 都重指的软链，必须核对它指向终点格
want=$(printf "%06d" "$F3_STEPS")
rl=$(readlink "$RUN3/checkpoints/last" 2>/dev/null || echo "")
echo "[s7f] F3 last -> ${rl:-无}（期望 $want）"
[ "$rl" = "$want" ] || die "F3 的 last 指向 '$rl' 而不是 $want ⇒ 读数会读错权重（坑 38）"
[ -f "$CK3/model.safetensors" ] || die "F3 终点格权重不在：$CK3/model.safetensors"
test_block "s7f_bs8_5500_seed2000" "$CK3" "F3 bs8@5500步"

# ── 3. 正式诊断（F1/F2/F3 齐）+ 7G 触发决定 ────────────────────────────────
diag_out "$DIAG" "F1/F2/F3"
TRIG=$(grep -m1 -o '7G_TRIGGER=[A-Z]*' "$DIAG" | head -1)
echo "[s7f] 触发决定：${TRIG:-（没读到 7G_TRIGGER 行）}  $(date '+%T')"
case "$TRIG" in
  7G_TRIGGER=YES) echo "[s7f] MIN3102 ≥ 50% ⇒ 触发 7G（chain_s7g.sh 会自己等 s7f.done 后发车），F4 **不跑**" ;;
  7G_TRIGGER=NO)  echo "[s7f] MIN3102 < 50% ⇒ 不触发 7G（chain_s7g.sh 会写 runs/s7g.SKIPPED），改跑 F4" ;;
  *)              die "runs/S7F_DIAG.md 里没有 7G_TRIGGER=YES|NO（只有 UNKNOWN？）⇒ 触发规则不适用，等人看" ;;
esac
grep -E '^\| [0-9]{4} \|' "$DIAG" | head -6

# ── 4. F4（**仅 NO 分支**）：bs32 / 5500 步 / lr1e-4 / seed2000（与 7B 唯一差 lr）──
if [ "$TRIG" = "7G_TRIGGER=NO" ]; then
  RUN4="$MG/runs/$F4_JOB"
  CK4="$RUN4/checkpoints/$(printf '%06d' "$F4_STEPS")/pretrained_model"
  echo "[s7f] ########## F4 · $F4_JOB（bs$F4_BS / $F4_STEPS 步 / lr$F4_LR，与 7B 唯一差 lr）########## $(date '+%F %T')"
  if [ -f "$CK4/model.safetensors" ]; then
    echo "[s7f] 跳过 F4 训练（已有产物）：$CK4"
  else
    [ -d "$RUN4" ] && die "F4 的 run 目录已存在但终点格权重不在：$RUN4（需人工看 ${RUN4}_meta/train.log）"
    wait_gpu "$MIN_FREE_BS32"
    DATASET="$DATASET" BS="$F4_BS" SEED="$F4_SEED" LR="$F4_LR" JOB="$F4_JOB" STEPS="$F4_STEPS" \
      SAVE_FREQ="$F4_SAVE" LOG_FREQ="$F4_LOG" \
      bash "$MG/code/run_pi05_s7b.sh" > "$MG/logs/train_${F4_JOB}.log" 2>&1
    rc=$?; echo "[s7f] F4 训练 rc=$rc $(date '+%F %T') 日志 -> logs/train_${F4_JOB}.log（进度看 ${RUN4}_meta/train.log）"
    [ "$rc" -eq 0 ] || die "F4 训练非 0 退出（rc=$rc）"
  fi
  want=$(printf "%06d" "$F4_STEPS"); rl=$(readlink "$RUN4/checkpoints/last" 2>/dev/null || echo "")
  echo "[s7f] F4 last -> ${rl:-无}（期望 $want）"
  [ "$rl" = "$want" ] || die "F4 的 last 指向 '$rl' 而不是 $want（坑 38）"
  [ -f "$CK4/model.safetensors" ] || die "F4 终点格权重不在：$CK4/model.safetensors"
  missing=""
  for s in $(seq "$F4_SAVE" "$F4_SAVE" "$F4_STEPS"); do
    [ -f "$RUN4/checkpoints/$(printf '%06d' "$s")/pretrained_model/model.safetensors" ] || missing="$missing $s"
  done
  [ -z "$missing" ] || die "F4 缺检查点格：$missing ⇒ 与 7B 的逐格配对会断头"

  ND=$(ls -1d "$RUN4"/sweep_rev/step_*_rev 2>/dev/null | wc -l)
  if [ "$ND" -ge 11 ]; then
    echo "[s7f] 跳过 F4 的 val 扫描（已有 $ND/11 格）"
  else
    echo "[s7f] === F4 11 格反向 val 扫描（每格 $EP 局、K=$K、val seed $VAL_SEED0..，与 7B 逐格同 epoch）=== $(date '+%F %T')"
    wait_gpu "$MIN_FREE_EVAL"
    RUN="$RUN4" STEPS_TOTAL="$F4_STEPS" SAVE_FREQ="$F4_SAVE" SUB=sweep_rev EPISODES="$EP" K="$K" \
      REV_SEED="$VAL_SEED0" DEMO_REV="$NPZ_R" MIN_FREE_MIB="$MIN_FREE_EVAL" \
      bash "$MG/code/mg_sweep_rev.sh" "$RUN4" > "$MG/logs/sweep_${F4_JOB}.log" 2>&1
    rc=$?; echo "[s7f] F4 扫描 rc=$rc $(date '+%F %T') 日志 -> logs/sweep_${F4_JOB}.log"
    [ "$rc" -eq 0 ] || die "F4 的 mg_sweep_rev.sh 退出码 $rc"
    ND=$(ls -1d "$RUN4"/sweep_rev/step_*_rev 2>/dev/null | wc -l)
    [ "$ND" -ge 11 ] || die "F4 只扫出 $ND 格（应 11）⇒ 与 7B 的逐格配对做不出来"
  fi
  test_block "s7f_bs32_lr1e4_seed2000" "$CK4" "F4 bs32/lr1e-4@5500步"
  diag_out "$DIAG" "F1/F2/F3/F4（F4 分支）"
else
  echo "[s7f] F4 不跑（预注册 §3：仅当 7G 未触发时才跑；GPU 让给能关门使命的 7G）"
fi

printf '%s 档7F 完成 F1F2=三个batch8 seed@018000(回溯) F3=%s(bs%s/%s步/lr%s) F4=%s 触发=%s 诊断=runs/S7F_DIAG.md 早期触发=runs/_diag/s7f_trigger_interim.md\n' \
  "$(date '+%F %T')" "$F3_JOB" "$F3_BS" "$F3_STEPS" "$F3_LR" \
  "$([ "$TRIG" = "7G_TRIGGER=NO" ] && echo "$F4_JOB(已跑)" || echo '未跑(7G 触发)')" "${TRIG#7G_TRIGGER=}" > "$MARK"
[ -s "$MARK" ] || die "done 标记写空了（坑 43 复发）"
echo "[s7f] 收工 $(date '+%F %T')  标记 -> $MARK"
