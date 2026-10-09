#!/usr/bin/env bash
# 档 8 · 格 8D（**条件发车**：D1∧D2∧D3 全过）：新 seed 4000/5000 + **同一份纠正集** ⇒ D4 使命证据链
#   预注册：runs/S8_PREREG.md §3「格 8D」（阈值写死：**D4 = min(seed2000,4000,5000) 的反向 TEST 放宽 ≥ 40/80 = 50%**）
#   触发依据：runs/s8c.done（2026-10-05 19:53）的 S8_D1=PASS ∧ S8_D2=PASS ∧ runs/S8_VERDICT.md 的 S8_D3=PASS
#
# 配方（与格 8C **逐项相同**，唯一差 = 训练 seed）：数据集 data/mix60f120r_c1 **全集**（219 集 / 53638 帧）/
#   bs8 / 22000 步 / lr 1e-4 / save_freq 2000（11 格）/ seed **4000** 与 **5000**（串行，不抢卡）
# 读数：11 格反向 val 扫描（val seed 8000..8019，与 8C **同窗口同数据集同 stats** ⇒ 这一对是干净的配对）
#   + TEST 反向 4×20（seed 7000..7019）+ 正向 1×20（seed 2000..2019，**副读数、不是门** ——
#   预注册只把 D2 挂在 8C 那一发上，这里只为透明）
# ⚠️ 关门读数一律 `last`（=022000），**不做 val 选点**（坑 27/38/42）；评测路径写**数字格**（坑 63）。
# ⚠️ 纠正集是从 **seed2000** 的 rollout 采的 ⇒ 本格检验「一份纠正集能否跨 seed 通用」（预注册的诚实标注）。
# ⚠️ D4 ❌ 的处方已写在预注册里（每 seed 各采一份纠正集，另起预注册）⇒ **本链不自动降门、不自动重跑**。
# 房规：setsid 发车（坑 37）；标记 printf 写 + `[ -s ]` 自检（坑 43）；路径全绝对（坑 41）；
#   认产物不认进程表（坑 22(e)）；有产物就跳过 ⇒ 可断点续跑；不编辑运行中的 .sh；不碰冻结文件。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
NOISE='robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation'

DST="mix60f120r_c1"
SRC_DS="mix60f120r"
STEPS="${STEPS:-22000}"; SAVE_FREQ="${SAVE_FREQ:-2000}"; NCELLS="${NCELLS:-11}"
BS="${BS:-8}"; LR="${LR:-1e-4}"; SEEDS="${SEEDS:-4000 5000}"
EP="${EP:-20}"; REPS="${REPS:-4}"; K="${K:-10}"
REV_SEED0="${REV_SEED0:-7000}"; FWD_SEED0="${FWD_SEED0:-2000}"; VAL_SEED0="${VAL_SEED0:-8000}"
MIN_FREE_EVAL="${MIN_FREE_EVAL:-9000}"
MIN_FREE_BS8="${MIN_FREE_BS8:-36000}"     # 7A 实测 bs8+gc1 峰值 33799 MiB（坑 64：按峰值取）
NPZ_R="$MG/data/${SRC_DS}_rev_raw.npz"
NPZ_F="$MG/data/${SRC_DS}_raw.npz"
VERD="$MG/runs/S8_VERDICT.md"
MARK="$MG/runs/s8d.done"
FAILED="$MG/runs/s8d.FAILED"

die () { echo "[s8d] FATAL $*" | tee -a "$FAILED"; exit 4; }

wait_gpu () {
  local need="$1" f
  for _ in $(seq 1 240); do
    f=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
    [ "${f:-0}" -ge "$need" ] && return 0
    echo "[s8d] 显存 free=${f}MiB < ${need}MiB，等 30 s ... $(date '+%T')"; sleep 30
  done
  echo "[s8d] 等了 2 h 显存仍不足 ${need}MiB（不抢卡，继续尝试）"; return 0
}

info_get () { "$MG_PY" -c "import json,sys;print(json.load(open(sys.argv[1]))[sys.argv[2]])" "$1" "$2"; }

one_eval () {  # $1=mode $2=目录名 $3=seed $4=ckpt $5=说明
  local mode="$1" out="$2" sd="$3" ck="$4" what="$5" npz="$NPZ_F"
  [ "$mode" = "reverse" ] && npz="$NPZ_R"
  if [ -f "$MG/runs/$out/eval_summary.json" ]; then echo "[s8d] 跳过（已有产物）$out"; return 0; fi
  [ -f "$ck/model.safetensors" ] || die "权重不在：$ck/model.safetensors（$what）"
  wait_gpu "$MIN_FREE_EVAL"
  echo "[s8d] === $what（$mode K=$K eps=$EP seed=$sd）-> runs/$out === $(date '+%F %T')"
  echo "[s8d]     ckpt=$ck"   # 出处打进日志（坑 30）
  "$MG_PY" code/mg_eval.py --ckpt "$ck" --episodes "$EP" --seed-mode random --seed "$sd" \
      --n-action-steps "$K" --task-mode "$mode" --demo-npz "$npz" \
      --out "$MG/runs/$out" 2>&1 | grep -vE "$NOISE" | grep -E "^  ep|成功率|放宽口径|warn|Error|Traceback"
  [ -f "$MG/runs/$out/eval_summary.json" ] || die "评测没落盘：$out"
}

test_block () {  # $1=目录前缀 $2=ckpt（**数字格**，坑 63）$3=说明
  local pre="$1" ck="$2" what="$3" i suf
  for i in $(seq 1 "$REPS"); do
    suf=""; [ "$i" -gt 1 ] && suf="_rep$i"
    one_eval reverse "${pre}_rev_test_rand20_k10$suf" "$REV_SEED0" "$ck" "$what 反向 TEST rep$i"
  done
  one_eval forward "${pre}_fwd_test_rand20_k10" "$FWD_SEED0" "$ck" "$what 正向护栏（副读数、不是门）"
}

verdict_out () {
  echo "[s8d] === 判定汇编 -> ${VERD#$MG/} === $(date '+%F %T')"
  "$MG_PY" "$MG/code/mg_verdict_s8.py" > "$VERD" 2> "$MG/logs/verdict_s8.log"
  local rc=$?
  echo "[s8d] mg_verdict_s8 rc=$rc（3 = 出身核对不过 ⇒ 不采信）"
  [ -s "$VERD" ] || die "判定文件没生成（看 logs/verdict_s8.log）"
  grep -E '^S8_' "$VERD"
  return "$rc"
}

train_arm () {  # $1=JOB $2=说明
  local job="$1" what="$2" run ck want rl rc missing s nd
  run="$MG/runs/$job"
  ck="$run/checkpoints/$(printf '%06d' "$STEPS")/pretrained_model"
  echo "[s8d] ########## $what · $job（bs$BS / $STEPS 步 / lr$LR / save_freq$SAVE_FREQ / 全集）########## $(date '+%F %T')"
  if [ -f "$ck/model.safetensors" ]; then
    echo "[s8d] 跳过训练（已有产物）：$ck"
  else
    [ -d "$run" ] && die "$what 的 run 目录已存在但终点格权重不在：$run（需人工看 ${run}_meta/train.log）"
    wait_gpu "$MIN_FREE_BS8"
    DATASET="$DST" EPISODES_SUBSET="" BS="$BS" SEED="${job##*seed}" LR="$LR" JOB="$job" \
      STEPS="$STEPS" SAVE_FREQ="$SAVE_FREQ" \
      bash "$MG/code/run_pi05_s2e.sh" > "$MG/logs/train_${job}.log" 2>&1
    rc=$?; echo "[s8d] $what 训练 rc=$rc $(date '+%F %T') 日志 -> logs/train_${job}.log（进度看 ${run}_meta/train.log）"
    [ "$rc" -eq 0 ] || die "$what 训练非 0 退出（rc=$rc）"
  fi
  # 坑 38：`last` 每次 save 都重指，必须核对它指向终点格
  want=$(printf "%06d" "$STEPS"); rl=$(readlink "$run/checkpoints/last" 2>/dev/null || echo "")
  echo "[s8d] $what last -> ${rl:-无}（期望 $want）"
  [ "$rl" = "$want" ] || die "$what 的 last 指向 '$rl' 而不是 $want ⇒ 读数会读错权重（坑 38）"
  [ -f "$ck/model.safetensors" ] || die "$what 终点格权重不在：$ck/model.safetensors"
  missing=""
  for s in $(seq "$SAVE_FREQ" "$SAVE_FREQ" "$STEPS"); do
    [ -f "$run/checkpoints/$(printf '%06d' "$s")/pretrained_model/model.safetensors" ] || missing="$missing $s"
  done
  [ -z "$missing" ] || die "$what 缺检查点格：$missing ⇒ ${NCELLS} 格 val 曲线会断头"
  # 11 格反向 val 扫描（按 step 对齐；与 8C 同数据集同 stats ⇒ 这一对是干净配对）
  nd=$(ls -1d "$run"/sweep_rev/step_*_rev 2>/dev/null | wc -l)
  if [ "$nd" -ge "$NCELLS" ]; then
    echo "[s8d] 跳过 $what 的 val 扫描（已有 $nd/$NCELLS 格）"
  else
    echo "[s8d] === $what ${NCELLS} 格反向 val 扫描（每格 $EP 局、K=$K、val seed $VAL_SEED0..）=== $(date '+%F %T')"
    wait_gpu "$MIN_FREE_EVAL"
    RUN="$run" STEPS_TOTAL="$STEPS" SAVE_FREQ="$SAVE_FREQ" SUB=sweep_rev EPISODES="$EP" K="$K" \
      REV_SEED="$VAL_SEED0" DEMO_REV="$NPZ_R" MIN_FREE_MIB="$MIN_FREE_EVAL" \
      bash "$MG/code/mg_sweep_rev.sh" "$run" > "$MG/logs/sweep_${job}.log" 2>&1
    rc=$?; echo "[s8d] $what 扫描 rc=$rc $(date '+%F %T') 日志 -> logs/sweep_${job}.log"
    [ "$rc" -eq 0 ] || die "$what 的 mg_sweep_rev.sh 退出码 $rc"
    nd=$(ls -1d "$run"/sweep_rev/step_*_rev 2>/dev/null | wc -l)
    [ "$nd" -ge "$NCELLS" ] || die "$what 只扫出 $nd 格（应 $NCELLS）⇒ 与 8C 的逐格配对做不出来"
  fi
  test_block "${job#pi05_${DST}_}" "$ck" "$what"
}

# ── 0. 已收工就别重跑（认产物 —— 坑 22(e)）──────────────────────────────────
if [ -s "$MARK" ]; then echo "[s8d] 已收工（$MARK 在）：$(head -1 "$MARK")"; exit 0; fi

# ── 1. 发车闸（预注册 §3「格 8D」的条件发车 + 出身核对，全部看盘上产物）──────────
echo "[s8d] === 发车闸 === $(date '+%F %T')"
[ -s "$MG/runs/s8c.done" ] || die "闸1：runs/s8c.done 不在 ⇒ 8C 没干净收工，8D 不许发车"
grep -q 'S8_D1=PASS' "$MG/runs/s8c.done" || die "闸1：runs/s8c.done 里没有 S8_D1=PASS"
grep -q 'S8_D2=PASS' "$MG/runs/s8c.done" || die "闸1：runs/s8c.done 里没有 S8_D2=PASS"
grep -q '^S8_D3=PASS' "$VERD" || die "闸2：$VERD 里没有 S8_D3=PASS ⇒ 归因不成立，预注册的 8D 条件不满足"
[ -f "$MG/data/$DST/meta/info.json" ] || die "闸3：合并集不在：data/$DST"
EP_DST=$(info_get "$MG/data/$DST/meta/info.json" total_episodes)
FR_DST=$(info_get "$MG/data/$DST/meta/info.json" total_frames)
[ "$EP_DST" = "219" ] && [ "$FR_DST" = "53638" ] \
  || die "闸3：合并集是 $EP_DST 集 / $FR_DST 帧 ≠ 219 / 53638（8A/8B 实收 39 集 7212 帧）⇒ 分母变了（坑 33）"
[ -f "$MG/data/$DST/MG_DATASET_CARD.json" ] || die "闸3：合并集没有数据卡片（出身不可查）"
"$MG_PY" -c "import json,sys;d=json.load(open(sys.argv[1]));sys.exit(0 if d['all_pass'] else 1)" \
  "$MG/runs/s8b_merge/merge_report.json" || die "闸3：B1/B2/B3 对账不过 ⇒ 合并集不可用"
[ -f "$NPZ_R" ] && [ -f "$NPZ_F" ] || die "闸4：示范 npz 不在：$NPZ_R / $NPZ_F"
"$MG_PY" "$MG/code/mg_verdict_s8.py" --selftest > "$MG/logs/verdict_s8_selftest.log" 2>&1 \
  || die "闸5：mg_verdict_s8 自测不过（看 logs/verdict_s8_selftest.log）"
# 闸6：8C 那一发（seed2000）的 D4 分母必须齐（4×20 反向），否则 min 无从算起
for i in "" _rep2 _rep3 _rep4; do
  [ -f "$MG/runs/s8c_seed2000_rev_test_rand20_k10$i/eval_summary.json" ] \
    || die "闸6：8C 的反向 TEST 缺产物 s8c_seed2000_rev_test_rand20_k10$i ⇒ D4 的 min 算不出来"
done
free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
[ "${free:-0}" -ge "$MIN_FREE_BS8" ] || die "闸7：GPU free=${free}MiB < ${MIN_FREE_BS8}MiB（不抢卡）"
echo "[s8d] 闸 1-7 全过（合并集 $EP_DST 集 / $FR_DST 帧；GPU free=${free}MiB；seeds=$SEEDS）$(date '+%T')"

# ── 2. 两个新 seed 串行（同配方，唯一差 = seed）──────────────────────────────
for sd in $SEEDS; do
  train_arm "pi05_${DST}_s8d_seed${sd}" "8D seed${sd}"
done

# ── 3. 判定（D4 = 三个 seed 的反向 TEST 放宽 min ≥ 40/80）────────────────────
verdict_out; V_RC=$?
D4=$(grep -m1 -o 'S8_D4=[A-Z]*' "$VERD" | head -1)
echo "[s8d] D4 判定：${D4:-（没读到）} $(date '+%F %T')"
case "$D4" in
  S8_D4=PASS) RES="D4 ✅ ⇒ 「demo + 纠正」配方下三个训练 seed 全过使命门 ⇒ 档 3r 的 seed 稳健性缺口关闭、使命证据链补齐" ;;
  S8_D4=FAIL) RES="D4 ❌ ⇒ 纠正数据只在采它的那个 seed 上有效（on-policy 特异性）⇒ 处方=每 seed 各采一份（另起预注册），**不自动降门**" ;;
  *)          RES="D4 读数不齐（$D4）⇒ 看 runs/S8_VERDICT.md 的 missing 行" ;;
esac
[ "${V_RC:-0}" -eq 3 ] && RES="$RES ｜ ⚠️ 出身核对不过 ⇒ 本判定不采信"

printf '%s 档8D 完成 seeds=%s(全集/%s步/bs%s/lr%s/save%s) 判定=runs/S8_VERDICT.md %s 结论=%s\n' \
  "$(date '+%F %T')" "$SEEDS" "$STEPS" "$BS" "$LR" "$SAVE_FREQ" "${D4:-NA}" "$RES" > "$MARK"
[ -s "$MARK" ] || die "done 标记写空了（坑 43 复发）"
echo "[s8d] 收工 $(date '+%F %T')  标记 -> $MARK"
echo "[s8d] 结论：$RES"
