#!/usr/bin/env bash
# 档 7H · 「便宜配方」的前瞻验证：**bs32 / 5500 步（=3.791 ep）/ lr 1e-4 / 3 个新训练 seed**
#   预注册：runs/S7H_PREREG.md（2026-10-05 21:0x 落盘，**早于本档任何读数**，也早于 8D 的 D4）
#   动机（**回溯、n=1**，不计入判定）：runs/S7F_DIAG.md §三 的 F4 = 60/80 = 75.0%（在标准配方最差的 seed2000 上）
#
# 判据（`code/mg_verdict_s7h.py`，机器可读行链里 grep）：
#   H1 主门 = 3 个新 seed 的 TEST 反向**放宽** min ≥ 40/80 = 50%（与档 3r/7C/7G/8D **完全同一条**使命门）
#   H2 护栏 = 三个 seed 的正向未见 20 局掉幅 vs 193/300 = 64.3% **都 ≤ 15 pp**
#   H3/H4 = 副读数（极差、与 F4 的 11 格配对符号检验）⇒ **只读方向、不是门**
# ⚠️ 配方**逐字照抄 F4**（`code/run_pi05_s7b.sh`，它自己会现算并对账 STEPS/SAVE_FREQ/LOG_FREQ，坑 33）；
#   一个参数都不动 —— 7B 的教训就是「同时动 batch 和 lr」把归因搞混（H-A）。
# ⚠️ 关门读数一律 `last`（=005500），**不做 val 选点**（坑 27/38/42）；评测路径写**数字格**（坑 63）。
# ⚠️ 数据集是 `mix60f120r`（**不含**纠正帧）⇒ normalizer 与档 8 的 `_c1` 不同 ⇒ **禁止**与 8C/8D 比高低（坑 33/57）。
# 房规：setsid 发车并核 SID==PID（坑 37）；标记 printf 写 + `[ -s ]` 自检（坑 43）；路径全绝对（坑 41）；
#   认产物不认进程表（坑 22(e)）；有产物就跳过 ⇒ 可断点续跑；不编辑运行中的 .sh（坑 22(d)）；不碰冻结文件；
#   **不抢卡**：等 runs/s8d.done（上限 48 h）；上游写 s8d.FAILED ⇒ 写 runs/s7h.SKIPPED 并 exit 0（预注册 §7）。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
NOISE='robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation'

DATASET="mix60f120r"
WANT_EPS="${WANT_EPS:-180}"; WANT_FRAMES="${WANT_FRAMES:-46426}"
BS="${BS:-32}"; LR="${LR:-1e-4}"; STEPS="${STEPS:-5500}"; SAVE_FREQ="${SAVE_FREQ:-500}"
LOG_FREQ="${LOG_FREQ:-25}"; NCELLS="${NCELLS:-11}"; TARGET_EPOCHS="${TARGET_EPOCHS:-3.79}"
SEEDS="${SEEDS:-11000 12000 13000}"
EP="${EP:-20}"; REPS="${REPS:-4}"; K="${K:-10}"
REV_SEED0="${REV_SEED0:-7000}"; FWD_SEED0="${FWD_SEED0:-2000}"; VAL_SEED0="${VAL_SEED0:-8000}"
MIN_FREE_EVAL="${MIN_FREE_EVAL:-9000}"
MIN_FREE_TRAIN="${MIN_FREE_TRAIN:-44000}"   # 7A 实测 bs32+gc1 峰值 41671 MiB（坑 64：按峰值取）
WAIT_H="${WAIT_H:-48}"
UP_DONE="$MG/runs/s8d.done"; UP_FAIL="$MG/runs/s8d.FAILED"
F4_RUN="$MG/runs/pi05_mix60f120r_s7f_bs32_lr1e4_seed2000"
NPZ_R="$MG/data/${DATASET}_rev_raw.npz"
NPZ_F="$MG/data/${DATASET}_raw.npz"
VERD="$MG/runs/S7H_VERDICT.md"
MARK="$MG/runs/s7h.done"; FAILED="$MG/runs/s7h.FAILED"; SKIPPED="$MG/runs/s7h.SKIPPED"

die  () { echo "[s7h] FATAL $*" | tee -a "$FAILED"; exit 4; }
skip () { printf '%s 档7H 不发车（预注册 §7 的合法终态）原因=%s\n' "$(date '+%F %T')" "$1" > "$SKIPPED"
          [ -s "$SKIPPED" ] || echo "[s7h] SKIPPED 写空了（坑 43 复发）"
          echo "[s7h] SKIP：$1"; exit 0; }
info_get () { "$MG_PY" -c "import json,sys;print(json.load(open(sys.argv[1]))[sys.argv[2]])" "$1" "$2"; }

wait_gpu () {
  local need="$1" f
  for _ in $(seq 1 240); do
    f=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
    [ "${f:-0}" -ge "$need" ] && return 0
    echo "[s7h] 显存 free=${f}MiB < ${need}MiB，等 30 s ... $(date '+%T')"; sleep 30
  done
  echo "[s7h] 等了 2 h 显存仍不足 ${need}MiB（不抢卡，继续尝试）"; return 0
}

one_eval () {  # $1=mode $2=目录名 $3=seed $4=ckpt $5=说明
  local mode="$1" out="$2" sd="$3" ck="$4" what="$5" npz="$NPZ_F"
  [ "$mode" = "reverse" ] && npz="$NPZ_R"
  if [ -f "$MG/runs/$out/eval_summary.json" ]; then echo "[s7h] 跳过（已有产物）$out"; return 0; fi
  [ -f "$ck/model.safetensors" ] || die "权重不在：$ck/model.safetensors（$what）"
  wait_gpu "$MIN_FREE_EVAL"
  echo "[s7h] === $what（$mode K=$K eps=$EP seed=$sd）-> runs/$out === $(date '+%F %T')"
  echo "[s7h]     ckpt=$ck"   # 出处打进日志（坑 30）
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
  one_eval forward "${pre}_fwd_test_rand20_k10" "$FWD_SEED0" "$ck" "$what 正向护栏（H2）"
}

verdict_out () {
  echo "[s7h] === 判定汇编 -> ${VERD#$MG/} === $(date '+%F %T')"
  "$MG_PY" "$MG/code/mg_verdict_s7h.py" > "$VERD" 2> "$MG/logs/verdict_s7h.log"
  local rc=$?
  echo "[s7h] mg_verdict_s7h rc=$rc（2 = 读数不齐；3 = 出身核对不过 ⇒ 不采信）"
  [ -s "$VERD" ] || die "判定文件没生成（看 logs/verdict_s7h.log）"
  grep -E '^S7H_' "$VERD"
  return "$rc"
}

train_arm () {  # $1=seed
  local sd="$1" job="pi05_${DATASET}_s7h_seed$1" what="7H seed$1" run ck want rl rc missing s nd
  run="$MG/runs/$job"
  ck="$run/checkpoints/$(printf '%06d' "$STEPS")/pretrained_model"
  echo "[s7h] ########## $what · $job（bs$BS / $STEPS 步 = 3.791 ep / lr$LR / save_freq$SAVE_FREQ / log_freq$LOG_FREQ）########## $(date '+%F %T')"
  if [ -f "$ck/model.safetensors" ]; then
    echo "[s7h] 跳过训练（已有产物）：$ck"
  else
    [ -d "$run" ] && die "$what 的 run 目录已存在但终点格权重不在：$run（需人工看 ${run}_meta/train.log）"
    wait_gpu "$MIN_FREE_TRAIN"
    DATASET="$DATASET" BS="$BS" SEED="$sd" LR="$LR" JOB="$job" STEPS="$STEPS" \
      SAVE_FREQ="$SAVE_FREQ" LOG_FREQ="$LOG_FREQ" TARGET_EPOCHS="$TARGET_EPOCHS" N_CELLS="$NCELLS" \
      bash "$MG/code/run_pi05_s7b.sh" > "$MG/logs/train_${job}.log" 2>&1
    rc=$?; echo "[s7h] $what 训练 rc=$rc $(date '+%F %T') 日志 -> logs/train_${job}.log（进度看 ${run}_meta/train.log）"
    [ "$rc" -eq 0 ] || die "$what 训练非 0 退出（rc=$rc）"
  fi
  # 坑 38：`last` 每次 save 都重指，必须核对它指向终点格
  want=$(printf "%06d" "$STEPS"); rl=$(readlink "$run/checkpoints/last" 2>/dev/null || echo "")
  echo "[s7h] $what last -> ${rl:-无}（期望 $want）"
  [ "$rl" = "$want" ] || die "$what 的 last 指向 '$rl' 而不是 $want ⇒ 读数会读错权重（坑 38）"
  [ -f "$ck/model.safetensors" ] || die "$what 终点格权重不在：$ck/model.safetensors"
  missing=""
  for s in $(seq "$SAVE_FREQ" "$SAVE_FREQ" "$STEPS"); do
    [ -f "$run/checkpoints/$(printf '%06d' "$s")/pretrained_model/model.safetensors" ] || missing="$missing $s"
  done
  [ -z "$missing" ] || die "$what 缺检查点格：$missing ⇒ ${NCELLS} 格 val 曲线会断头（H4 的配对也就残了）"
  # 11 格反向 val 扫描（每格 20 局、K=10、val seed 8000..8019）
  nd=$(ls -1d "$run"/sweep_rev/step_*_rev 2>/dev/null | wc -l)
  if [ "$nd" -ge "$NCELLS" ]; then
    echo "[s7h] 跳过 $what 的 val 扫描（已有 $nd/$NCELLS 格）"
  else
    echo "[s7h] === $what ${NCELLS} 格反向 val 扫描（每格 $EP 局、K=$K、val seed $VAL_SEED0..）=== $(date '+%F %T')"
    wait_gpu "$MIN_FREE_EVAL"
    RUN="$run" STEPS_TOTAL="$STEPS" SAVE_FREQ="$SAVE_FREQ" SUB=sweep_rev EPISODES="$EP" K="$K" \
      REV_SEED="$VAL_SEED0" DEMO_REV="$NPZ_R" MIN_FREE_MIB="$MIN_FREE_EVAL" \
      bash "$MG/code/mg_sweep_rev.sh" "$run" > "$MG/logs/sweep_${job}.log" 2>&1
    rc=$?; echo "[s7h] $what 扫描 rc=$rc $(date '+%F %T') 日志 -> logs/sweep_${job}.log"
    [ "$rc" -eq 0 ] || die "$what 的 mg_sweep_rev.sh 退出码 $rc"
    nd=$(ls -1d "$run"/sweep_rev/step_*_rev 2>/dev/null | wc -l)
    [ "$nd" -ge "$NCELLS" ] || die "$what 只扫出 $nd 格（应 $NCELLS）⇒ 与 F4 的逐格配对（H4）做不出来"
  fi
  test_block "s7h_seed${sd}" "$ck" "$what"
}

# ── 0. 已收工/已合法跳过就别重跑（认产物 —— 坑 22(e)）────────────────────────
if [ -s "$MARK" ]; then echo "[s7h] 已收工（$MARK 在）：$(head -1 "$MARK")"; exit 0; fi
if [ -s "$SKIPPED" ]; then echo "[s7h] 已跳过（$SKIPPED 在）：$(head -1 "$SKIPPED")"; exit 0; fi

# ── 1. 等上游 8D 收工（**不抢卡**；认产物不认进程表）──────────────────────────
echo "[s7h] === 等档 8D 收工（上限 ${WAIT_H} h）=== $(date '+%F %T')"
got=""
for _ in $(seq 1 $((WAIT_H * 60))); do
  [ -s "$UP_DONE" ] && { got="done";   break; }
  [ -s "$UP_FAIL" ] && { got="FAILED"; break; }
  sleep 60
done
case "$got" in
  done)   echo "[s7h] 8D 收工：$(head -1 "$UP_DONE")" ;;
  FAILED) skip "上游 8D 写了 s8d.FAILED（$(head -c 200 "$UP_FAIL")）⇒ 需要人工分诊，此时烧 26 h 跑旁支会拖慢主线修复" ;;
  *)      skip "等 ${WAIT_H} h 仍没等到 runs/s8d.done（8D 可能没发车或还在飞）⇒ 不抢卡、不发车" ;;
esac

# ── 2. 发车闸（预注册 §7 第 2 条，全部只读盘上产物）──────────────────────────
echo "[s7h] === 发车闸 === $(date '+%F %T')"
[ -f "$MG/data/$DATASET/meta/info.json" ] || die "闸1：数据集不在：data/$DATASET"
G_EPS=$(info_get "$MG/data/$DATASET/meta/info.json" total_episodes)
G_FR=$(info_get "$MG/data/$DATASET/meta/info.json" total_frames)
[ "$G_EPS" = "$WANT_EPS" ] && [ "$G_FR" = "$WANT_FRAMES" ] \
  || die "闸1：$DATASET 是 $G_EPS 集 / $G_FR 帧 ≠ $WANT_EPS / $WANT_FRAMES ⇒ epoch 换算的分母变了（坑 33）"
[ -f "$NPZ_R" ] && [ -f "$NPZ_F" ] || die "闸2：示范 npz 不在：$NPZ_R / $NPZ_F"
"$MG_PY" "$MG/code/mg_verdict_s7h.py" --selftest > "$MG/logs/verdict_s7h_selftest.log" 2>&1 \
  || die "闸3：mg_verdict_s7h 自测不过（看 logs/verdict_s7h_selftest.log）"
NF4=$(ls -1d "$F4_RUN"/sweep_rev/step_*_rev 2>/dev/null | wc -l)
[ "$NF4" -ge "$NCELLS" ] || die "闸4：F4 只有 $NF4/$NCELLS 格 val 产物（$F4_RUN/sweep_rev）⇒ H4 的配对对象不全"
free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
[ "${free:-0}" -ge "$MIN_FREE_TRAIN" ] || die "闸5：GPU free=${free}MiB < ${MIN_FREE_TRAIN}MiB（bs32 峰值 41671，坑 64；不抢卡）"
echo "[s7h] 闸 1-5 全过（$DATASET $G_EPS 集 / $G_FR 帧；F4 $NF4 格；GPU free=${free}MiB；seeds=$SEEDS）$(date '+%T')"

# ── 3. 三个新 seed 串行（同配方，唯一差 = seed）──────────────────────────────
for sd in $SEEDS; do
  train_arm "$sd"
done

# ── 4. 判定（H1 = 三个新 seed 的反向 TEST 放宽 min ≥ 40/80）──────────────────
verdict_out; V_RC=$?
H1=$(grep -m1 -o 'S7H_H1=[A-Z]*' "$VERD" | head -1)
H2=$(grep -m1 -o 'S7H_H2=[A-Z]*' "$VERD" | head -1)
echo "[s7h] 判定：${H1:-（没读到）} / ${H2:-（没读到）} $(date '+%F %T')"
case "$H1|$H2" in
  S7H_H1=PASS\|S7H_H2=PASS) RES="H1✅∧H2✅ ⇒ 「等 epoch 下换 batch/lr」这条杠杆**前瞻成立** ⇒ seed 稳健性缺口有第二条独立关闭路线（第一条=档8纠正数据）⇒ 下一步按 STAGE_PLAN 排档 9（TILT/侧躺 can 的抓取几何）" ;;
  S7H_H1=PASS\|*)           RES="H1✅∧H2❌ ⇒ 反向过门但**拆东墙** ⇒ 标「不可作为部署配方」，只记录；处方=重做正反向配比（另起预注册）" ;;
  S7H_H1=FAIL\|*)           RES="H1❌ ⇒ F4 的 75% 是 n=1 的幸运/seed2000 特异 ⇒ 便宜配方不能替代纠正数据 ⇒ 唯一已证路线=「demo+纠正」（档8），处方按 8D 的 D4 走" ;;
  *)                        RES="H1 读数不齐（$H1）⇒ 看 runs/S7H_VERDICT.md 的 missing 行" ;;
esac
[ "${V_RC:-0}" -eq 3 ] && RES="$RES ｜ ⚠️ 出身核对不过 ⇒ 本判定不采信"

printf '%s 档7H 完成 seeds=%s(%s/%s步=3.791ep/bs%s/lr%s/save%s/log%s) 判定=runs/S7H_VERDICT.md %s %s 结论=%s\n' \
  "$(date '+%F %T')" "$SEEDS" "$DATASET" "$STEPS" "$BS" "$LR" "$SAVE_FREQ" "$LOG_FREQ" \
  "${H1:-NA}" "${H2:-NA}" "$RES" > "$MARK"
[ -s "$MARK" ] || die "done 标记写空了（坑 43 复发）"
echo "[s7h] 收工 $(date '+%F %T')  标记 -> $MARK"
echo "[s7h] 结论：$RES"
