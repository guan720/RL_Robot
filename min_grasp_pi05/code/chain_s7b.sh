#!/usr/bin/env bash
# 档 7B · 「把 run 间方差压下去」的主实验链（预注册：runs/S7_PREREG.md，13:55 落盘）
#
# 顺序：发车闸(10 条) -> 格 7A-2 梯度噪声探针 -> 机理判据闸 -> bs32 等 epoch 训练(seed 2000)
#       -> `last` 软链核对 -> 11 格 val 扫描 -> TEST 关门(反向 4×20 + 正向护栏 1×20)
#       -> 配对符号检验(M1) + 噪声画像 -> 判定汇编
#
# 为什么先跑 7A-2：它只花 ~15 min，却能在烧 6h51m 之前**证伪** H7 的机理。
#   预注册判据（阈值写死在 runs/S7_PREREG.md §3）：η₈ < 0.15 ⇒ 机理不成立 ⇒ 本链在此停，
#   写 runs/s7b.HELD，等人看（不自动改路线，坑 40：判据不许看完数再改）。
#
# 房规：setsid 发车（坑 37）；done 标记 printf 写 + `[ -s ]` 自检（坑 43）；路径全绝对（坑 41）；
#   每个读数「有产物就跳过」⇒ 可断点续跑；不碰任何冻结文件（mg_eval/mg_env*/mg_sweep_rev/
#   mg_verdict_s3r/mg_epoch_curve/mg_expert）。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
NOISE='robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation'

DATASET="mix60f120r"
BS="${BS:-32}"
SEED="${SEED:-2000}"
LR="${LR:-2e-4}"
STEPS="${STEPS:-5500}"
SAVE_FREQ="${SAVE_FREQ:-500}"
LOG_FREQ="${LOG_FREQ:-25}"
EP="${EP:-20}"
REPS="${REPS:-4}"
K="${K:-10}"
MIN_FREE_TRAIN="${MIN_FREE_TRAIN:-45000}"   # 7A 实测 bs32 峰值 41671 MiB
MIN_FREE_EVAL="${MIN_FREE_EVAL:-9000}"

JOB="pi05_${DATASET}_s7b_bs${BS}_seed${SEED}"
RUN="$MG/runs/$JOB"
CK="$RUN/checkpoints/last/pretrained_model"
BASE8="$MG/runs/pi05_mix60f120r_s3r_seed2000"     # M1 的对照臂（同 seed 标签、batch8）
BASE8_1000="$MG/runs/pi05_mix60f120r_s2e"
BASE8_3000="$MG/runs/pi05_mix60f120r_s3r_seed3000"
NPZ_R="$MG/data/${DATASET}_rev_raw.npz"
NPZ_F="$MG/data/${DATASET}_raw.npz"
PROBE="$MG/runs/s7_probe"
MARK="$MG/runs/s7b.done"
FAILED="$MG/runs/s7b.FAILED"
HELD="$MG/runs/s7b.HELD"

die  () { echo "[s7b] FATAL $*" | tee -a "$FAILED"; exit 4; }
hold () { printf '%s 档7B 暂缓（预注册分支 %s）原因=%s 处置=见 runs/S7_PREREG.md §3 格7A-2\n' \
            "$(date '+%F %T')" "$1" "$2" > "$HELD"; [ -s "$HELD" ] || echo "[s7b] HELD 写空了";
          echo "[s7b] HOLD $1：$2"; exit 6; }

# ── 0. 发车闸（全部看盘上产物；预注册 §7 的 10 条）──────────────────────────
echo "[s7b] === 发车闸 === $(date '+%F %T')"
[ -s "$MG/runs/s7_probe.done" ]                       || die "闸1：7A 没收工（runs/s7_probe.done）"
grep -q '| `bs32_gc1` | 32 | on | OK |' "$PROBE/timing.md" 2>/dev/null \
                                                          || die "闸2：timing.md 里 bs32+ckpt 不是 OK（OOM 了就不能发 7B）"
[ -s "$MG/runs/S3R_VERDICT.md" ]                      || die "闸3：档 3r 判定不在"
grep -q "FAIL" "$MG/runs/S3R_VERDICT.md"              || die "闸3：档 3r 不是 FAIL ⇒ 本档前提不成立"
[ -s "$MG/runs/S6_VERDICT.md" ]                       || die "闸4：档 6 判定不在（几何解释没关掉，归因会串）"
FR=$("$MG_PY" -c "import json;print(json.load(open('$MG/data/$DATASET/meta/info.json'))['total_frames'])")
[ "$FR" = "46426" ]                                   || die "闸5：total_frames=$FR ≠ 46426 ⇒ 等 epoch 步数的分母变了"
[ -f "$NPZ_R" ]                                       || die "闸6：反向示范 npz 不在"
[ -f "$NPZ_F" ]                                       || die "闸6：正向示范 npz 不在"
N8=$(ls -1d "$BASE8"/sweep_rev/step_*_rev 2>/dev/null | wc -l)
[ "$N8" -ge 11 ]                                      || die "闸7：M1 对照臂 $BASE8 只有 $N8/11 格"
"$MG_PY" "$MG/code/mg_probe_gradnoise.py" --selftest >/dev/null || die "闸8：mg_probe_gradnoise 自测不过"
"$MG_PY" "$MG/code/mg_seedcurve.py"     --selftest >/dev/null || die "闸8：mg_seedcurve 自测不过"
"$MG_PY" "$MG/code/mg_probe_batch.py"   --selftest >/dev/null || die "闸8：mg_probe_batch 自测不过"
free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
[ "${free:-0}" -ge "$MIN_FREE_TRAIN" ]                || die "闸9：GPU free=${free}MiB < ${MIN_FREE_TRAIN}MiB（别的实验在跑，不抢卡）"
echo "[s7b] 闸 1-9 全过（GPU free=${free}MiB）$(date '+%T')"

# ── 1. 格 7A-2：逐步梯度噪声探针 ────────────────────────────────────────────
if [ -s "$PROBE/gradnoise.json" ]; then
  echo "[s7b] 跳过 7A-2（已有产物 $PROBE/gradnoise.json）"
else
  echo "[s7b] === 格 7A-2 梯度噪声探针（bs 8/32 各 120 步，log_freq=1，lr=1e-6）=== $(date '+%T')"
  "$MG_PY" "$MG/code/mg_probe_gradnoise.py" > "$MG/logs/s7_gradnoise.log" 2>&1
  rc=$?; echo "[s7b] 7A-2 rc=$rc $(date '+%T') 日志 -> logs/s7_gradnoise.log"
  [ "$rc" -eq 0 ] || die "7A-2 探针退出码 $rc"
  [ -s "$PROBE/gradnoise.md" ] || die "7A-2 报告写空了"
fi
# 闸 10：机理判据（阈值来自预注册，不来自本脚本）
BR=$("$MG_PY" -c "import json;print(json.load(open('$PROBE/gradnoise.json')).get('branch','NA'))")
ETA=$("$MG_PY" -c "
import json; f=json.load(open('$PROBE/gradnoise.json')).get('fit',{})
e=(f.get('eta') or {}).get('8') or (f.get('eta') or {}).get(8)
print('%.4f' % e if isinstance(e,(int,float)) else 'NA')")
echo "[s7b] 闸10：机理分支 = $BR（η₈ = $ETA）"
case "$BR" in
  MECH_NO)  hold "$BR" "η₈=$ETA < 0.15 ⇒ 梯度噪声不是主导项，烧 7 h 训 bs32 的机理论证不成立" ;;
  NA)       die  "闸10：7A-2 拟合不可用（branch=NA）⇒ 判据不适用，先看 runs/s7_probe/gradnoise.md" ;;
  MECH_YES) echo "[s7b] η₈ ≥ 0.40 ⇒ H7 机理成立，照发" ;;
  MECH_PART) echo "[s7b] 0.15 ≤ η₈ < 0.40 ⇒ 方向对但不主导；照发，判定里必须写明不能把功劳全归给梯度噪声" ;;
  *)        die  "闸10：未知分支 '$BR'" ;;
esac

# ── 2. 训练 ────────────────────────────────────────────────────────────────
if [ -f "$CK/model.safetensors" ]; then
  echo "[s7b] 跳过训练（已有产物）：$CK"
else
  echo "[s7b] === 训练 bs$BS / seed$SEED / lr$LR / $STEPS 步（等 epoch 3.79）=== $(date '+%F %T')"
  DATASET="$DATASET" BS="$BS" SEED="$SEED" LR="$LR" JOB="$JOB" \
    STEPS="$STEPS" SAVE_FREQ="$SAVE_FREQ" LOG_FREQ="$LOG_FREQ" \
    bash "$MG/code/run_pi05_s7b.sh" > "$MG/logs/train_${JOB}.log" 2>&1
  rc=$?; echo "[s7b] 训练 rc=$rc $(date '+%F %T') 日志 -> logs/train_${JOB}.log"
  [ "$rc" -eq 0 ] || die "训练非 0 退出（进度看 $RUN/train.log，不是 logs/train_${JOB}.log —— 后者被缓冲）"
fi
# 坑 38：`last` 是每次 save 都重指的软链，必须核对指向终点格
want=$(printf "%06d" "$STEPS")
rl=$(readlink "$RUN/checkpoints/last" 2>/dev/null || echo "")
echo "[s7b] last -> ${rl:-无}（期望 $want）"
[ "$rl" = "$want" ] || die "last 指向 '$rl' 而不是 $want ⇒ 读数会读错权重（坑 38）"
[ -f "$CK/model.safetensors" ] || die "终点格权重不在：$CK/model.safetensors"
missing=""
for s in $(seq "$SAVE_FREQ" "$SAVE_FREQ" "$STEPS"); do
  [ -f "$RUN/checkpoints/$(printf '%06d' "$s")/pretrained_model/model.safetensors" ] || missing="$missing $s"
done
[ -z "$missing" ] || die "缺检查点格：$missing ⇒ 扫出来会是断头曲线"

# ── 3. 11 格 val 扫描（K=10、20 局、val seed 8000..，与档 3r 补充完全同口径）──
wait_gpu_eval () {
  for _ in $(seq 1 240); do
    f=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
    [ "${f:-0}" -ge "$MIN_FREE_EVAL" ] && return 0
    echo "[s7b] 显存 free=${f}MiB < ${MIN_FREE_EVAL}MiB，等 30 s ... $(date '+%T')"; sleep 30
  done
  return 0
}
ND=$(ls -1d "$RUN"/sweep_rev/step_*_rev 2>/dev/null | wc -l)
if [ "$ND" -ge 11 ]; then
  echo "[s7b] 跳过 val 扫描（已有 $ND/11 格）"
else
  echo "[s7b] === 11 格反向 val 扫描（每格 $EP 局，K=$K，seed 8000..）=== $(date '+%F %T')"
  wait_gpu_eval
  RUN="$RUN" STEPS_TOTAL="$STEPS" SAVE_FREQ="$SAVE_FREQ" SUB=sweep_rev EPISODES="$EP" K="$K" \
    REV_SEED=8000 DEMO_REV="$NPZ_R" MIN_FREE_MIB="$MIN_FREE_EVAL" \
    bash "$MG/code/mg_sweep_rev.sh" "$RUN" > "$MG/logs/sweep_${JOB}.log" 2>&1
  rc=$?; echo "[s7b] 扫描 rc=$rc $(date '+%F %T') 日志 -> logs/sweep_${JOB}.log"
  [ "$rc" -eq 0 ] || die "mg_sweep_rev.sh 退出码 $rc"
  ND=$(ls -1d "$RUN"/sweep_rev/step_*_rev 2>/dev/null | wc -l)
  [ "$ND" -ge 11 ] || die "只扫出 $ND 格（应 11）⇒ 曲线不完整，M1 做不出来"
fi

# ── 4. TEST 关门读数 + 正向护栏（与档 3r 同 seed 窗口、同 K、两口径并行输出）──
run_eval () {  # $1=mode $2=eps $3=seed $4=out $5=tag
  local out="$4"
  [ -f "$MG/runs/$out/eval_summary.json" ] && { echo "[s7b] 跳过（已有产物）$out"; return 0; }
  wait_gpu_eval
  echo "[s7b] === $5 ($1 K=$K eps=$2 seed=$3) -> runs/$out === $(date '+%F %T')"
  local npz="$NPZ_F"; [ "$1" = "reverse" ] && npz="$NPZ_R"
  "$MG_PY" code/mg_eval.py --ckpt "$CK" --episodes "$2" --seed-mode random --seed "$3" \
      --n-action-steps "$K" --task-mode "$1" --demo-npz "$npz" \
      --out "$MG/runs/$out" 2>&1 | grep -vE "$NOISE" | grep -E "^  ep|成功率|放宽口径|warn|Error|Traceback"
  [ -f "$MG/runs/$out/eval_summary.json" ] || die "评测没落盘：$out"
}
for i in $(seq 1 "$REPS"); do
  suf=""; [ "$i" -gt 1 ] && suf="_rep$i"
  run_eval reverse "$EP" 7000 "s7b_bs${BS}_seed${SEED}_rev_test_rand20_k10$suf" "7B 反向 TEST rep$i"
done
run_eval forward "$EP" 2000 "s7b_bs${BS}_seed${SEED}_fwd_test_rand20_k10" "7B 护栏 正向未见"

# ── 5. 配对分析（M1 的统计量）+ 五条曲线总览（7D，零 GPU）─────────────────────
echo "[s7b] === 配对符号检验 M1（7B vs batch8-seed2000，放宽口径，epoch≥1.03）=== $(date '+%T')"
"$MG_PY" "$MG/code/mg_seedcurve.py" \
  --run "s7b_bs${BS}_seed${SEED}:$RUN" --run "b8_seed2000:$BASE8" \
  --log "s7b_bs${BS}_seed${SEED}:$RUN/train.log" --log "b8_seed2000:$BASE8/train.log" \
  --test "b8_seed2000:33:80" --metric relaxed --min-epoch 1.03 --gate 0.50 \
  --thresholds 0.05,0.10,0.15,0.20,0.25,0.30,0.35,0.40 \
  --out "$MG/runs/_diag/seedcurve_s7b_m1.md" > "$MG/logs/seedcurve_s7b_m1.log" 2>&1 \
  || die "M1 配对分析失败：logs/seedcurve_s7b_m1.log"
[ -s "$MG/runs/_diag/seedcurve_s7b_m1.md" ] || die "M1 报告写空了"
grep -E "^\[seedcurve\]" "$MG/logs/seedcurve_s7b_m1.log" | head -6

echo "[s7b] === 五条曲线总览（7D：batch8×3 + bs32×1，同 epoch 网格）=== $(date '+%T')"
"$MG_PY" "$MG/code/mg_seedcurve.py" \
  --run "b8_seed1000:$BASE8_1000" --run "b8_seed2000:$BASE8" --run "b8_seed3000:$BASE8_3000" \
  --run "s7b_bs${BS}_seed${SEED}:$RUN" \
  --log "b8_seed1000:$BASE8_1000/train.log" --log "b8_seed2000:$BASE8/train.log" \
  --log "b8_seed3000:$BASE8_3000/train.log" --log "s7b_bs${BS}_seed${SEED}:$RUN/train.log" \
  --test "b8_seed1000:55:80" --test "b8_seed2000:33:80" --test "b8_seed3000:64:80" \
  --metric strict --min-epoch 1.03 --gate 0.50 \
  --thresholds 0.05,0.10,0.15,0.20,0.25,0.30,0.35,0.40 \
  --out "$MG/runs/_diag/seedcurve_s7.md" > "$MG/logs/seedcurve_s7.log" 2>&1 \
  || echo "[s7b] 注意：五条曲线总览失败（不阻塞判定）：logs/seedcurve_s7.log"

# ── 6. 判定汇编 ────────────────────────────────────────────────────────────
if [ -f "$MG/code/mg_verdict_s7.py" ]; then
  echo "[s7b] === 判定汇编 === $(date '+%F %T')"
  "$MG_PY" "$MG/code/mg_verdict_s7.py" --selftest > "$MG/logs/verdict_s7_selftest.log" 2>&1 \
    || die "mg_verdict_s7 自测不过：logs/verdict_s7_selftest.log"
  "$MG_PY" "$MG/code/mg_verdict_s7.py" > "$MG/runs/S7_VERDICT.md" 2> "$MG/logs/verdict_s7.log"
  rc=$?; echo "[s7b] 判定 rc=$rc -> runs/S7_VERDICT.md"
  [ "$rc" -eq 0 ] && [ -s "$MG/runs/S7_VERDICT.md" ] || die "判定没生成（rc=$rc，看 logs/verdict_s7.log）"
  tail -30 "$MG/runs/S7_VERDICT.md"
else
  echo "[s7b] 注意：code/mg_verdict_s7.py 还不在 ⇒ 读数已全部落盘，判定需手工跑"
fi

printf '%s 档7B 完成 job=%s bs=%s seed=%s steps=%s lr=%s 机理分支=%s eta8=%s cells=%s 判定=runs/S7_VERDICT.md\n' \
  "$(date '+%F %T')" "$JOB" "$BS" "$SEED" "$STEPS" "$LR" "$BR" "$ETA" "$ND" > "$MARK"
[ -s "$MARK" ] || die "done 标记写空了（坑 43 复发）"
echo "[s7b] done $(date '+%F %T')  标记 -> $MARK"
