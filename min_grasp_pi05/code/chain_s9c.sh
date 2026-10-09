#!/usr/bin/env bash
# 档 9C · **配方收口**：2×2 因子设计唯一缺的那格 = 便宜配方（bs32/5500）× **纠正数据**（mix60f120r_c1）
#   预注册：runs/S9_PREREG.md **增补 2**（无条件接续）+ **增补 4**（9B 在设计阶段关闭 ⇒ 本档接续；
#           C4 的配对臂**事前写死** = 8D seed4000）。两者都**早于本档任何读数**（坑 40）。
#
# 2×2 因子表（唯一变量 = batch/步数 与 纠正帧在不在；四格**等采样预算 176000**）：
#              | 无纠正 mix60f120r        | 有纠正 mix60f120r_c1
#   bs8/22000  | 档 3r：min 33/80 ❌      | 档 8（8C/8D）：min 64/80 ✅
#   bs32/5500  | 档 7H：min 67/80 ✅      | **档 9C（本档）= 唯一缺格**
#
# 判据（code/mg_verdict_s9c.py，机器行 S9C_C1= / S9C_C2= / S9C_TRUST=）：
#   C1 主门 = 3 个新训练 seed（21000/22000/23000）的 TEST 反向**放宽** min ≥ 40/80 = 50%（与档 3r/7C/7G/8D/7H **同一条**使命门）
#   C2 护栏 = 每个 seed 的正向未见 20 局掉幅 vs 193/300 = 64.3% **都 ≤ 15 pp**
#   C3/C4 副 = 极差、与 8D seed4000 的 11 格**epoch 网格**逐格配对符号检验 ⇒ **只读方向、不是门**
# ⚠️ 与 8C/8D **同数据集同 normalizer** ⇒ 可以并列比高低；与 7H/档 3r **不同数据集** ⇒ 只比形状、不比高低（坑 33/57）。
# ⚠️ 关门读数一律 `last`（=005500），**不做 val 选点**（坑 27/38/42）；评测路径写**数字格**（坑 63）。
# ⚠️ 示范 npz 与 8C/8D **逐项同口径**：`data/mix60f120r_rev_raw.npz`（反向）/ `mix60f120r_raw.npz`（正向）
#    ——**不是** `_c1_` 的（已核 runs/s8d_seed4000_*/eval_summary.json 的 demo_npz 字段）。
# ⚠️ 步数不许照抄：`code/run_pi05_s7b.sh` 自己用 mg_probe_batch.equal_epoch_plan **现算并对账** STEPS/SAVE_FREQ/LOG_FREQ（坑 33/54）。
# 房规：setsid 发车并核 SID==PID（坑 37）；标记 printf 写 + `[ -s ]` 自检（坑 43）；路径全绝对（坑 41）；
#   认产物不认进程表（坑 22(e)）；有产物就跳过 ⇒ 可断点续跑；不编辑在飞的 .sh（坑 22(d)）；不碰冻结文件；
#   **退出码先存变量、再做任何 `$(...)`**（坑 80）；**本链不进 chain_watchdog.sh 清单**（坑 78：不编辑在飞的看门狗）
#   ⇒ 由本链自身终态标记（s9c.done / s9c.FAILED / s9c.SKIPPED）+ 人工巡检覆盖。
# **不抢卡**：等 runs/s7h.{done,FAILED,SKIPPED} 任一 + `chain_s7h.sh` 进程消失（上限 48 h）；训练需 free ≥ 44000 MiB。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
NOISE='robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation'

DATASET="mix60f120r_c1"          # 训练集 = 档 8 的合并集（demo 180 集 + 纠正 39 集）
SRC_DS="mix60f120r"              # 示范 npz 的出身（与 8C/8D 逐项同口径，见文件头）
WANT_EPS="${WANT_EPS:-219}"; WANT_FRAMES="${WANT_FRAMES:-53638}"
BS="${BS:-32}"; LR="${LR:-1e-4}"; STEPS="${STEPS:-5500}"; SAVE_FREQ="${SAVE_FREQ:-500}"
LOG_FREQ="${LOG_FREQ:-25}"; NCELLS="${NCELLS:-11}"; TARGET_EPOCHS="${TARGET_EPOCHS:-3.28}"
SEEDS="${SEEDS:-21000 22000 23000}"
EP="${EP:-20}"; REPS="${REPS:-4}"; K="${K:-10}"
REV_SEED0="${REV_SEED0:-7000}"; FWD_SEED0="${FWD_SEED0:-2000}"; VAL_SEED0="${VAL_SEED0:-8000}"
MIN_FREE_EVAL="${MIN_FREE_EVAL:-9000}"
MIN_FREE_TRAIN="${MIN_FREE_TRAIN:-44000}"   # 7A 实测 bs32+gc1 峰值 41671 MiB（坑 64：按峰值取）
WAIT_H="${WAIT_H:-48}"
UP_MARKS=("$MG/runs/s7h.done" "$MG/runs/s7h.FAILED" "$MG/runs/s7h.SKIPPED")
UP_PROC='code/chain_s7h\.sh'
S9B_MARKS=("$MG/runs/s9b.SKIPPED" "$MG/runs/s9b.done" "$MG/runs/s9b.FAILED")
PAIR_RUN="$MG/runs/pi05_mix60f120r_c1_s8d_seed4000"   # C4 的配对臂（增补 4 事前写死，不许事后挑）
NPZ_R="$MG/data/${SRC_DS}_rev_raw.npz"
NPZ_F="$MG/data/${SRC_DS}_raw.npz"
VERD="$MG/runs/S9C_VERDICT.md"
MARK="$MG/runs/s9c.done"; FAILED="$MG/runs/s9c.FAILED"; SKIPPED="$MG/runs/s9c.SKIPPED"

die  () { echo "[s9c] FATAL $*" | tee -a "$FAILED"; exit 4; }
skip () { printf '%s 档9C 不发车（预注册 增补2/增补4 的合法终态）原因=%s\n' "$(date '+%F %T')" "$1" > "$SKIPPED"
          [ -s "$SKIPPED" ] || echo "[s9c] SKIPPED 写空了（坑 43 复发）"
          echo "[s9c] SKIP：$1"; exit 0; }
info_get () { "$MG_PY" -c "import json,sys;print(json.load(open(sys.argv[1]))[sys.argv[2]])" "$1" "$2"; }

wait_gpu () {
  local need="$1" f
  for _ in $(seq 1 240); do
    f=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
    [ "${f:-0}" -ge "$need" ] && return 0
    echo "[s9c] 显存 free=${f}MiB < ${need}MiB，等 30 s ... $(date '+%T')"; sleep 30
  done
  echo "[s9c] 等了 2 h 显存仍不足 ${need}MiB（不抢卡，继续尝试）"; return 0
}

one_eval () {  # $1=mode $2=目录名 $3=seed $4=ckpt $5=说明
  local mode="$1" out="$2" sd="$3" ck="$4" what="$5" npz="$NPZ_F"
  [ "$mode" = "reverse" ] && npz="$NPZ_R"
  if [ -f "$MG/runs/$out/eval_summary.json" ]; then echo "[s9c] 跳过（已有产物）$out"; return 0; fi
  [ -f "$ck/model.safetensors" ] || die "权重不在：$ck/model.safetensors（$what）"
  wait_gpu "$MIN_FREE_EVAL"
  echo "[s9c] === $what（$mode K=$K eps=$EP seed=$sd）-> runs/$out === $(date '+%F %T')"
  echo "[s9c]     ckpt=$ck"   # 出处打进日志（坑 30）
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
  one_eval forward "${pre}_fwd_test_rand20_k10" "$FWD_SEED0" "$ck" "$what 正向护栏（C2）"
}

verdict_out () {
  echo "[s9c] === 判定汇编 -> ${VERD#$MG/} === $(date '+%F %T')"
  "$MG_PY" "$MG/code/mg_verdict_s9c.py" > "$VERD" 2> "$MG/logs/verdict_s9c.log"
  local rc=$?                                   # 坑 80：先存退出码，再做任何 $(...)
  echo "[s9c] mg_verdict_s9c rc=$rc（2 = 读数不齐；3 = 出身核对不过 ⇒ 不采信）"
  [ -s "$VERD" ] || die "判定文件没生成（看 logs/verdict_s9c.log）"
  grep -E '^S9C_' "$VERD"
  return "$rc"
}

train_arm () {  # $1=seed
  local sd="$1" job="pi05_${DATASET}_s9c_seed$1" what="9C seed$1" run ck want rl rc missing s nd
  run="$MG/runs/$job"
  ck="$run/checkpoints/$(printf '%06d' "$STEPS")/pretrained_model"
  echo "[s9c] ########## $what · $job（bs$BS / $STEPS 步 = 3.2813 ep / lr$LR / save_freq$SAVE_FREQ / log_freq$LOG_FREQ / 全集 219 集）########## $(date '+%F %T')"
  if [ -f "$ck/model.safetensors" ]; then
    echo "[s9c] 跳过训练（已有产物）：$ck"
  else
    [ -d "$run" ] && die "$what 的 run 目录已存在但终点格权重不在：$run（需人工看 ${run}_meta/train.log）"
    wait_gpu "$MIN_FREE_TRAIN"
    DATASET="$DATASET" BS="$BS" SEED="$sd" LR="$LR" JOB="$job" STEPS="$STEPS" \
      SAVE_FREQ="$SAVE_FREQ" LOG_FREQ="$LOG_FREQ" TARGET_EPOCHS="$TARGET_EPOCHS" N_CELLS="$NCELLS" \
      bash "$MG/code/run_pi05_s7b.sh" > "$MG/logs/train_${job}.log" 2>&1
    rc=$?; echo "[s9c] $what 训练 rc=$rc $(date '+%F %T') 日志 -> logs/train_${job}.log（进度看 ${run}_meta/train.log）"
    [ "$rc" -eq 0 ] || die "$what 训练非 0 退出（rc=$rc）"
  fi
  # 坑 38：`last` 每次 save 都重指，必须核对它指向终点格
  want=$(printf "%06d" "$STEPS"); rl=$(readlink "$run/checkpoints/last" 2>/dev/null || echo "")
  echo "[s9c] $what last -> ${rl:-无}（期望 $want）"
  [ "$rl" = "$want" ] || die "$what 的 last 指向 '$rl' 而不是 $want ⇒ 读数会读错权重（坑 38）"
  [ -f "$ck/model.safetensors" ] || die "$what 终点格权重不在：$ck/model.safetensors"
  missing=""
  for s in $(seq "$SAVE_FREQ" "$SAVE_FREQ" "$STEPS"); do
    [ -f "$run/checkpoints/$(printf '%06d' "$s")/pretrained_model/model.safetensors" ] || missing="$missing $s"
  done
  [ -z "$missing" ] || die "$what 缺检查点格：$missing ⇒ ${NCELLS} 格 val 曲线会断头（C4 的配对也就残了）"
  # 11 格反向 val 扫描（每格 20 局、K=10、val seed 8000..8019；与 8D seed4000 **同一张 epoch 网格**）
  nd=$(ls -1d "$run"/sweep_rev/step_*_rev 2>/dev/null | wc -l)
  if [ "$nd" -ge "$NCELLS" ]; then
    echo "[s9c] 跳过 $what 的 val 扫描（已有 $nd/$NCELLS 格）"
  else
    echo "[s9c] === $what ${NCELLS} 格反向 val 扫描（每格 $EP 局、K=$K、val seed $VAL_SEED0..）=== $(date '+%F %T')"
    wait_gpu "$MIN_FREE_EVAL"
    RUN="$run" STEPS_TOTAL="$STEPS" SAVE_FREQ="$SAVE_FREQ" SUB=sweep_rev EPISODES="$EP" K="$K" \
      REV_SEED="$VAL_SEED0" DEMO_REV="$NPZ_R" MIN_FREE_MIB="$MIN_FREE_EVAL" \
      bash "$MG/code/mg_sweep_rev.sh" "$run" > "$MG/logs/sweep_${job}.log" 2>&1
    rc=$?; echo "[s9c] $what 扫描 rc=$rc $(date '+%F %T') 日志 -> logs/sweep_${job}.log"
    [ "$rc" -eq 0 ] || die "$what 的 mg_sweep_rev.sh 退出码 $rc"
    nd=$(ls -1d "$run"/sweep_rev/step_*_rev 2>/dev/null | wc -l)
    [ "$nd" -ge "$NCELLS" ] || die "$what 只扫出 $nd 格（应 $NCELLS）⇒ 与 8D seed4000 的逐格配对（C4）做不出来"
  fi
  test_block "s9c_seed${sd}" "$ck" "$what"
}

# ── 0. 已收工/已合法跳过就别重跑（认产物 —— 坑 22(e)）────────────────────────
if [ -s "$MARK" ]; then echo "[s9c] 已收工（$MARK 在）：$(head -1 "$MARK")"; exit 0; fi
if [ -s "$SKIPPED" ]; then echo "[s9c] 已跳过（$SKIPPED 在）：$(head -1 "$SKIPPED")"; exit 0; fi

# ── 1. 等上游 7H 让卡（**不抢卡**；认产物 + 进程消失，坑 22(e)）────────────────
echo "[s9c] === 等档 7H 收工并让卡（上限 ${WAIT_H} h）=== $(date '+%F %T')"
got=""
for _ in $(seq 1 $((WAIT_H * 60))); do
  for m in "${UP_MARKS[@]}"; do [ -s "$m" ] && { got="$m"; break 2; }; done
  sleep 60
done
[ -n "$got" ] || skip "等 ${WAIT_H} h 仍没等到 runs/s7h.{done,FAILED,SKIPPED}（7H 可能还在飞）⇒ 不抢卡、不发车"
echo "[s9c] 7H 终态标记：$got -> $(head -c 200 "$got")"
# 标记在 ≠ 卡已让出（评测可能还在收尾）⇒ 再等进程消失（上限 2 h），不看进程表判完成、只用它判「卡空没空」
for _ in $(seq 1 240); do
  pgrep -f "$UP_PROC" > /dev/null 2>&1 || break
  echo "[s9c] chain_s7h.sh 还在（收尾中），等 30 s ... $(date '+%T')"; sleep 30
done
pgrep -f "$UP_PROC" > /dev/null 2>&1 \
  && echo "[s9c] ⚠️ 等了 2 h chain_s7h.sh 仍在 ⇒ 靠显存闸把关，不硬抢"

# ── 2. 发车闸（预注册 增补 2/增补 4，全部只读盘上产物）────────────────────────
echo "[s9c] === 发车闸 === $(date '+%F %T')"
s9b=""
for m in "${S9B_MARKS[@]}"; do [ -s "$m" ] && { s9b="$m"; break; }; done
[ -n "$s9b" ] || die "闸0：9B 没有任何终态标记（s9b.SKIPPED/done/FAILED）⇒ 上游状态不明，不许接续（增补 4 ③）"
echo "[s9c] 闸0：9B 终态 = $(basename "$s9b")（$(head -c 120 "$s9b")）"
[ -f "$MG/data/$DATASET/meta/info.json" ] || die "闸1：合并集不在：data/$DATASET"
G_EPS=$(info_get "$MG/data/$DATASET/meta/info.json" total_episodes)
G_FR=$(info_get "$MG/data/$DATASET/meta/info.json" total_frames)
[ "$G_EPS" = "$WANT_EPS" ] && [ "$G_FR" = "$WANT_FRAMES" ] \
  || die "闸1：$DATASET 是 $G_EPS 集 / $G_FR 帧 ≠ $WANT_EPS / $WANT_FRAMES ⇒ epoch 换算的分母变了（坑 33）"
[ -f "$MG/data/$DATASET/MG_DATASET_CARD.json" ] || die "闸1：合并集没有数据卡片（出身不可查）"
"$MG_PY" -c "import json,sys;d=json.load(open(sys.argv[1]));sys.exit(0 if d['all_pass'] else 1)" \
  "$MG/runs/s8b_merge/merge_report.json" || die "闸1：B1/B2/B3 对账不过 ⇒ 合并集不可用"
[ -f "$NPZ_R" ] && [ -f "$NPZ_F" ] || die "闸2：示范 npz 不在：$NPZ_R / $NPZ_F"
"$MG_PY" "$MG/code/mg_verdict_s9c.py" --selftest > "$MG/logs/verdict_s9c_selftest.log" 2>&1 \
  || die "闸3：mg_verdict_s9c 自测不过（看 logs/verdict_s9c_selftest.log）"
NP=$(ls -1d "$PAIR_RUN"/sweep_rev/step_*_rev 2>/dev/null | wc -l)
[ "$NP" -ge "$NCELLS" ] || die "闸4：C4 的配对臂只有 $NP/$NCELLS 格 val 产物（$PAIR_RUN/sweep_rev）⇒ 配对做不出来"
# 闸5：8D 三臂的关门读数必须在（C1/C3 的对照常数出处 = runs/S8_VERDICT.md）
grep -q '^S8_D4=PASS' "$MG/runs/S8_VERDICT.md" \
  || die "闸5：runs/S8_VERDICT.md 里没有 S8_D4=PASS ⇒ 同数据集的对照臂本身没关门，2×2 表缺一角"
wait_gpu "$MIN_FREE_TRAIN"
free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
[ "${free:-0}" -ge "$MIN_FREE_TRAIN" ] || die "闸6：GPU free=${free}MiB < ${MIN_FREE_TRAIN}MiB（bs32 峰值 41671，坑 64；不抢卡）"
echo "[s9c] 闸 0-6 全过（$DATASET $G_EPS 集 / $G_FR 帧；配对臂 $NP 格；GPU free=${free}MiB；seeds=$SEEDS）$(date '+%T')"

# ── 3. 三个新 seed 串行（同配方，唯一差 = seed）──────────────────────────────
for sd in $SEEDS; do
  train_arm "$sd"
done

# ── 4. 判定（C1 = 三个新 seed 的反向 TEST 放宽 min ≥ 40/80）──────────────────
verdict_out; V_RC=$?
C1=$(grep -m1 -o 'S9C_C1=[A-Z]*' "$VERD" | head -1)
C2=$(grep -m1 -o 'S9C_C2=[A-Z]*' "$VERD" | head -1)
TR=$(grep -m1 -o 'S9C_TRUST=[A-Z]*' "$VERD" | head -1)
echo "[s9c] 判定：${C1:-（没读到）} / ${C2:-（没读到）} / ${TR:-（没读到）} $(date '+%F %T')"
case "$C1|$C2" in
  S9C_C1=PASS\|S9C_C2=PASS) RES="C1✅∧C2✅ ⇒ 2×2 四格全部收口：**便宜配方（bs32/5500，≈6.9 h）+ 纠正数据**也能过同一条使命门 ⇒ 部署配方多一条 3× 更便宜的选项，且 seed 稳健性在两种 batch 下都成立" ;;
  S9C_C1=PASS\|*)           RES="C1✅∧C2❌ ⇒ 反向过门但**拆东墙**（正向掉幅 > 15 pp）⇒ 标「不可作为部署配方」，只记录；处方=重做正反向配比（另起预注册）" ;;
  S9C_C1=FAIL\|*)           RES="C1❌ ⇒ 便宜配方**只在无纠正数据时成立**（7H ✅ / 9C ❌）⇒ 纠正数据与 bs32 存在交互 ⇒ 部署配方锁定档 8 的 bs8/22000+纠正；处方=按 8D 的 D4 走，**不自动降门**" ;;
  *)                        RES="C1 读数不齐（$C1）⇒ 看 runs/S9C_VERDICT.md 的 missing 行（缺字段≠0，坑 40③）" ;;
esac
[ "${V_RC:-0}" -eq 3 ] && RES="$RES ｜ ⚠️ 出身核对不过 ⇒ 本判定不采信"

printf '%s 档9C 完成 seeds=%s(%s/%s步=3.2813ep/bs%s/lr%s/save%s/log%s) 判定=runs/S9C_VERDICT.md %s %s %s 结论=%s\n' \
  "$(date '+%F %T')" "$SEEDS" "$DATASET" "$STEPS" "$BS" "$LR" "$SAVE_FREQ" "$LOG_FREQ" \
  "${C1:-NA}" "${C2:-NA}" "${TR:-NA}" "$RES" > "$MARK"
[ -s "$MARK" ] || die "done 标记写空了（坑 43 复发）"
echo "[s9c] 收工 $(date '+%F %T')  标记 -> $MARK"
echo "[s9c] 结论：$RES"
