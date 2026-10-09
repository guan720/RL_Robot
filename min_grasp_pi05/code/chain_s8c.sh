#!/usr/bin/env bash
# 档 8 · 8C(主实验) -> 判定 D1/D2 -> **条件发车** 8C-ctl(1:1 归因) -> 判定 D3
#       预注册：runs/S8_PREREG.md（§3 格 8C / 8C-ctl；阈值写死，看完数不许改）
#
# 8C 配方（与档 3r 的 seed2000 臂**同步数、同 batch、同 lr、同 seed**，唯一差 = 数据里多了纠正帧）：
#   数据集 data/mix60f120r_c1 **全集**（180+N 集）/ bs8 / 22000 步 / lr 1e-4 / seed 2000 / save_freq 2000（11 格）
# ⚠️ **等步数不等 epoch**（预注册写死的理由）：全集 52426 帧 ⇒ 22000 步 = 3.354 ep，
#   而对照臂只采样 180 集（46426 帧）⇒ 同步数 = 3.791 ep。等步数让两臂的墙钟与优化轨迹长度**完全相同**，
#   差值只可能来自「采样到哪些帧」；等 epoch 会让纠正臂多训 13%，把「数据变多」与「训练变长」绑在一起（坑 33 的形状）。
# ⚠️ `run_pi05_s2e.sh` 打印的「实际 X epoch」用的是**数据集总帧数**，对照臂（只用 0-179 集）那行数字
#   会偏大，那是打印口径不是训练口径 —— 两臂的 STEPS 都是 22000，这才是承重的那一条。
#
# 判据（`code/mg_verdict_s8.py`，机器可读行链里 grep）：
#   D1 主门 = TEST 反向放宽 ≥ 40/80 = 50%（与档 3r/7C/7G **完全同一条**使命门）
#   D2 护栏 = 正向未见 20 局掉幅 vs 193/300=64.3% ≤ 15 pp（D1✅∧D2🚫 ⇒ **不采信**）
#   D3 归因 = 8C vs 8C-ctl 在**同一批 (rep,seed)** 的 80 局上配对，净胜 ≥ +8 ∧ 单侧 p ≤ 0.05
# ⚠️ 关门读数一律 `last`（=022000），**不做 val 选点**（坑 27/38/42）；评测路径写**数字格**（坑 63）。
# ⚠️ 8C-ctl 只在 D1 ✅ ∧ D2 ✅ 时发车（预注册决策树）；D1 ❌ ⇒ 判定写明「数据侧杠杆不够」⇒ 转阶梯 7 / 收工。
#
# 房规：setsid 发车（坑 37）；标记 printf 写 + `[ -s ]` 自检（坑 43）；路径全绝对（坑 41）；
#   认产物不认进程表（坑 22(e)）；有产物就跳过 ⇒ 可断点续跑；不编辑运行中的 .sh；不碰冻结文件。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
NOISE='robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation'

DST="mix60f120r_c1"
SRC_DS="mix60f120r"
STEPS="${STEPS:-22000}"; SAVE_FREQ="${SAVE_FREQ:-2000}"; NCELLS="${NCELLS:-11}"
BS="${BS:-8}"; LR="${LR:-1e-4}"; SEED="${SEED:-2000}"
EP="${EP:-20}"; REPS="${REPS:-4}"; K="${K:-10}"
REV_SEED0="${REV_SEED0:-7000}"; FWD_SEED0="${FWD_SEED0:-2000}"; VAL_SEED0="${VAL_SEED0:-8000}"
MIN_FREE_EVAL="${MIN_FREE_EVAL:-9000}"
MIN_FREE_BS8="${MIN_FREE_BS8:-36000}"     # 7A 实测 bs8+gc1 峰值 33799 MiB（坑 64：按峰值取，不按预注册正文的 20000）
WAIT_H="${WAIT_H:-16}"                     # 8A+8B ≈ 3~5 h（采集）+ 合并 ~15 min

JOB_C="${JOB_C:-pi05_${DST}_s8c_seed${SEED}}"
JOB_CTL="${JOB_CTL:-pi05_${DST}_s8c_ctl_seed${SEED}}"
NPZ_R="$MG/data/${SRC_DS}_rev_raw.npz"
NPZ_F="$MG/data/${SRC_DS}_raw.npz"
VERD="$MG/runs/S8_VERDICT.md"
MARK="$MG/runs/s8c.done"
FAILED="$MG/runs/s8c.FAILED"

die () { echo "[s8c] FATAL $*" | tee -a "$FAILED"; exit 4; }

wait_gpu () {
  local need="$1" f
  for _ in $(seq 1 240); do
    f=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
    [ "${f:-0}" -ge "$need" ] && return 0
    echo "[s8c] 显存 free=${f}MiB < ${need}MiB，等 30 s ... $(date '+%T')"; sleep 30
  done
  echo "[s8c] 等了 2 h 显存仍不足 ${need}MiB（不抢卡，继续尝试）"; return 0
}

info_get () { "$MG_PY" -c "import json,sys;print(json.load(open(sys.argv[1]))[sys.argv[2]])" "$1" "$2"; }

one_eval () {  # $1=mode $2=目录名 $3=seed $4=ckpt $5=说明
  local mode="$1" out="$2" sd="$3" ck="$4" what="$5" npz="$NPZ_F"
  [ "$mode" = "reverse" ] && npz="$NPZ_R"
  if [ -f "$MG/runs/$out/eval_summary.json" ]; then echo "[s8c] 跳过（已有产物）$out"; return 0; fi
  [ -f "$ck/model.safetensors" ] || die "权重不在：$ck/model.safetensors（$what）"
  wait_gpu "$MIN_FREE_EVAL"
  echo "[s8c] === $what（$mode K=$K eps=$EP seed=$sd）-> runs/$out === $(date '+%F %T')"
  echo "[s8c]     ckpt=$ck"   # 出处打进日志（坑 30）
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
  one_eval forward "${pre}_fwd_test_rand20_k10" "$FWD_SEED0" "$ck" "$what 正向护栏（未见）"
}

verdict_out () {
  echo "[s8c] === 判定汇编 -> ${VERD#$MG/} === $(date '+%F %T')"
  "$MG_PY" "$MG/code/mg_verdict_s8.py" > "$VERD" 2> "$MG/logs/verdict_s8.log"
  local rc=$?
  echo "[s8c] mg_verdict_s8 rc=$rc（3 = 出身核对不过 ⇒ 不采信）"
  [ -s "$VERD" ] || die "判定文件没生成（看 logs/verdict_s8.log）"
  grep -E '^S8_' "$VERD"
  return "$rc"
}

train_arm () {  # $1=JOB $2=EPISODES_SUBSET（空=全集）$3=说明
  local job="$1" sub="$2" what="$3" run ck want rl rc missing s
  run="$MG/runs/$job"
  ck="$run/checkpoints/$(printf '%06d' "$STEPS")/pretrained_model"
  echo "[s8c] ########## $what · $job（bs$BS / $STEPS 步 / lr$LR / seed$SEED / subset='${sub:-全集}'）########## $(date '+%F %T')"
  if [ -f "$ck/model.safetensors" ]; then
    echo "[s8c] 跳过训练（已有产物）：$ck"
  else
    [ -d "$run" ] && die "$what 的 run 目录已存在但终点格权重不在：$run（需人工看 ${run}_meta/train.log）"
    wait_gpu "$MIN_FREE_BS8"
    DATASET="$DST" EPISODES_SUBSET="$sub" BS="$BS" SEED="$SEED" LR="$LR" JOB="$job" \
      STEPS="$STEPS" SAVE_FREQ="$SAVE_FREQ" \
      bash "$MG/code/run_pi05_s2e.sh" > "$MG/logs/train_${job}.log" 2>&1
    rc=$?; echo "[s8c] $what 训练 rc=$rc $(date '+%F %T') 日志 -> logs/train_${job}.log（进度看 ${run}_meta/train.log）"
    [ "$rc" -eq 0 ] || die "$what 训练非 0 退出（rc=$rc）"
  fi
  # 坑 38：`last` 每次 save 都重指，必须核对它指向终点格
  want=$(printf "%06d" "$STEPS"); rl=$(readlink "$run/checkpoints/last" 2>/dev/null || echo "")
  echo "[s8c] $what last -> ${rl:-无}（期望 $want）"
  [ "$rl" = "$want" ] || die "$what 的 last 指向 '$rl' 而不是 $want ⇒ 读数会读错权重（坑 38）"
  [ -f "$ck/model.safetensors" ] || die "$what 终点格权重不在：$ck/model.safetensors"
  missing=""
  for s in $(seq "$SAVE_FREQ" "$SAVE_FREQ" "$STEPS"); do
    [ -f "$run/checkpoints/$(printf '%06d' "$s")/pretrained_model/model.safetensors" ] || missing="$missing $s"
  done
  [ -z "$missing" ] || die "$what 缺检查点格：$missing ⇒ 11 格 val 曲线会断头"
  # 11 格反向 val 扫描（**按 step 对齐**，不按 epoch —— 两臂步数相同，这才是可比的口径）
  local nd
  nd=$(ls -1d "$run"/sweep_rev/step_*_rev 2>/dev/null | wc -l)
  if [ "$nd" -ge "$NCELLS" ]; then
    echo "[s8c] 跳过 $what 的 val 扫描（已有 $nd/$NCELLS 格）"
  else
    echo "[s8c] === $what ${NCELLS} 格反向 val 扫描（每格 $EP 局、K=$K、val seed $VAL_SEED0..）=== $(date '+%F %T')"
    wait_gpu "$MIN_FREE_EVAL"
    RUN="$run" STEPS_TOTAL="$STEPS" SAVE_FREQ="$SAVE_FREQ" SUB=sweep_rev EPISODES="$EP" K="$K" \
      REV_SEED="$VAL_SEED0" DEMO_REV="$NPZ_R" MIN_FREE_MIB="$MIN_FREE_EVAL" \
      bash "$MG/code/mg_sweep_rev.sh" "$run" > "$MG/logs/sweep_${job}.log" 2>&1
    rc=$?; echo "[s8c] $what 扫描 rc=$rc $(date '+%F %T') 日志 -> logs/sweep_${job}.log"
    [ "$rc" -eq 0 ] || die "$what 的 mg_sweep_rev.sh 退出码 $rc"
    nd=$(ls -1d "$run"/sweep_rev/step_*_rev 2>/dev/null | wc -l)
    [ "$nd" -ge "$NCELLS" ] || die "$what 只扫出 $nd 格（应 $NCELLS）⇒ 与对照臂的逐格配对做不出来"
  fi
  test_block "${job#pi05_${DST}_}" "$ck" "$what"
}

# ── 0. 等 8A/8B 收工（认产物 —— 坑 22(e)）───────────────────────────────────
if [ -s "$MARK" ]; then echo "[s8c] 已收工（$MARK 在）：$(head -1 "$MARK")"; exit 0; fi
echo "[s8c] === 等档 8A/8B 收工（上限 ${WAIT_H} h）=== $(date '+%F %T')"
got=""
for _ in $(seq 1 $((WAIT_H * 60))); do
  [ -s "$MG/runs/s8a.done" ]    && { got="done";   break; }
  [ -s "$MG/runs/s8a.HELD" ]    && { got="HELD";   break; }
  [ -s "$MG/runs/s8a.FAILED" ]  && { got="FAILED"; break; }
  sleep 60
done
case "$got" in
  done)   echo "[s8c] 8A/8B 收工：$(head -1 "$MG/runs/s8a.done")" ;;
  HELD)   printf '%s 档8C 不发车（预注册分支）原因=8A 写了 runs/s8a.HELD：%s 依据=runs/S8_PREREG.md §3「不过 ⇒ 停下等人」\n' \
              "$(date '+%F %T')" "$(head -1 "$MG/runs/s8a.HELD")" > "$MG/runs/s8c.SKIPPED"
          [ -s "$MG/runs/s8c.SKIPPED" ] || echo "[s8c] SKIPPED 写空了（坑 43 复发）"
          echo "[s8c] SKIP：8A 暂缓 ⇒ 8C 不发车"; exit 0 ;;
  FAILED) die "8A 写了 runs/s8a.FAILED：$(head -1 "$MG/runs/s8a.FAILED")" ;;
  "")     die "等 ${WAIT_H} h 仍没有 runs/s8a.done ⇒ 8A 可能静默死亡，看 logs/ALERTS.log" ;;
esac

# ── 1. 发车闸 ──────────────────────────────────────────────────────────────
echo "[s8c] === 发车闸 === $(date '+%F %T')"
[ -f "$MG/data/$DST/meta/info.json" ] || die "闸1：合并集不在：data/$DST"
EP_DST=$(info_get "$MG/data/$DST/meta/info.json" total_episodes)
FR_DST=$(info_get "$MG/data/$DST/meta/info.json" total_frames)
[ "$EP_DST" -gt 180 ] || die "闸1：合并集只有 $EP_DST 集（应 > 180）⇒ 纠正帧没进去"
[ "$FR_DST" -gt 46426 ] || die "闸1：合并集只有 $FR_DST 帧（应 > 46426）"
[ -f "$MG/runs/s8b_merge/merge_report.json" ] || die "闸2：合并对账报告不在（runs/s8b_merge/merge_report.json）"
"$MG_PY" -c "import json,sys;d=json.load(open(sys.argv[1]));sys.exit(0 if d['all_pass'] else 1)" \
  "$MG/runs/s8b_merge/merge_report.json" || die "闸2：B1/B2/B3 对账不过 ⇒ 合并集不可用"
[ -f "$MG/data/$DST/MG_DATASET_CARD.json" ] || die "闸3：合并集没有数据卡片（出身不可查）"
"$MG_PY" "$MG/code/mg_verdict_s8.py" --selftest > "$MG/logs/verdict_s8_selftest.log" 2>&1 \
  || die "闸4：mg_verdict_s8 自测不过（看 logs/verdict_s8_selftest.log）"
[ -f "$NPZ_R" ] && [ -f "$NPZ_F" ] || die "闸5：示范 npz 不在：$NPZ_R / $NPZ_F"
free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
[ "${free:-0}" -ge "$MIN_FREE_EVAL" ] || die "闸6：GPU free=${free}MiB < ${MIN_FREE_EVAL}MiB（不抢卡）"
echo "[s8c] 闸全过（合并集 $EP_DST 集 / $FR_DST 帧 = 纠正帧 $((FR_DST - 46426))；GPU free=${free}MiB）$(date '+%T')"

# ── 2. 格 8C：主实验 ───────────────────────────────────────────────────────
train_arm "$JOB_C" "" "8C 主实验"
verdict_out; V_RC=$?
D1=$(grep -m1 -o 'S8_D1=[A-Z]*' "$VERD" | head -1)
D2=$(grep -m1 -o 'S8_D2=[A-Z]*' "$VERD" | head -1)
echo "[s8c] 8C 判定：${D1:-（没读到）} ${D2:-（没读到）} $(date '+%T')"

# ── 3. 格 8C-ctl：**条件发车**（D1 ✅ ∧ D2 ✅）──────────────────────────────
if [ "$D1" = "S8_D1=PASS" ] && [ "$D2" = "S8_D2=PASS" ]; then
  echo "[s8c] D1∧D2 全过 ⇒ 触发 8C-ctl（1:1 归因，同数据集 --dataset.episodes=0-179）"
  train_arm "$JOB_CTL" "0-179" "8C-ctl 归因臂"
  verdict_out; V_RC=$?
  D3=$(grep -m1 -o 'S8_D3=[A-Z]*' "$VERD" | head -1)
  echo "[s8c] 归因判定：${D3:-（没读到）}"
  case "$(grep -m1 -o 'S8_D3=[A-Z]*' "$VERD")" in
    S8_D3=PASS) RES="D1∧D2∧D3 全过 ⇒ 触发 8D（新 seed 4000/5000，另起链）" ;;
    *)          RES="D1∧D2 过但 D3 归因不成立 ⇒ 使命门**不算**关闭（坑 57）" ;;
  esac
elif [ "$D1" = "S8_D1=FAIL" ]; then
  RES="D1 ❌ ⇒ 判定写明「纠正数据在本产出率/占比下抬不动坏 seed」⇒ 转阶梯 7（RL）或收工；8C-ctl 不发车（预注册决策树）"
else
  RES="D1 ✅ 但 D2 🚫 ⇒ **不采信**（拆东墙补西墙，与档 7B 的 M5 同纪律）；8C-ctl 不发车"
fi
[ "${V_RC:-0}" -eq 3 ] && RES="$RES ｜ ⚠️ 出身核对不过 ⇒ 本判定不采信"

printf '%s 档8C 完成 8C=%s(全集/%s步/bs%s/lr%s/seed%s) 判定=runs/S8_VERDICT.md %s %s 结论=%s\n' \
  "$(date '+%F %T')" "$JOB_C" "$STEPS" "$BS" "$LR" "$SEED" "${D1:-NA}" "${D2:-NA}" "$RES" > "$MARK"
[ -s "$MARK" ] || die "done 标记写空了（坑 43 复发）"
echo "[s8c] 收工 $(date '+%F %T')  标记 -> $MARK"
echo "[s8c] 结论：$RES"
