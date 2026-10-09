#!/usr/bin/env bash
# 档 3r 补充 · seed **3000** 的反向 val 曲线（11 格 × 20 局）+ 与 seed 1000 / seed 2000 的 epoch 对齐对表
#
# 为什么要补这一条（`runs/S3R_VERDICT.md` 05:39 判 ❌ FAIL 之后的第 2 步）：
#   档 3r 三 seed 的反向放宽口径 = seed1000 **68.8%** / seed2000 **41.2%** / seed3000 **80.0%**，
#   门（最差 seed ≥50%）被 seed2000 打穿 ⇒ FAIL。第 1 步（seed2000 的 val 曲线，06:52 收）已经给出答案：
#   **整条曲线都低**（5→35%，全程压在 seed1000 下面，10000/14000 步差 −35/−30 pp）⇒ 不是「终点掉坑」，
#   处方落在「加数据 / 查配比 / 多 seed」而不是「选点 / 早停」。
#   本条补第 2 步：**好 seed 是不是全程都好**。这决定了「能不能用一个便宜的早期 val 探针把坏 seed 筛掉」——
#   如果 seed3000 在 0.3~1 epoch 就已经明显高于 seed2000，那么重训时可以早停筛 seed，不必等 3.79 epoch。
#
# ⚠️ 与 `code/mg_sweep_rev.sh` 头注释同一条纪律：**不选点、不改门**。val n=20 在 p≈0.3 时 1σ≈10 pp，
#   坑 27 / 坑 42 都实测过「挑 val 最大值 = 在噪声里挑峰」。曲线只当「学习趋势」读。
#
# 发车闸（全部看盘上产物，不看进程表）：
#   1) runs/S3R_VERDICT.md 已落盘且判了 FAIL（处方前提）；
#   2) seed3000 的 11 个检查点在盘上（缺格就 die，别扫出断头曲线）；
#   3) seed1000（runs/pi05_mix60f120r_s2e/sweep_rev）与 seed2000 的 11 格都在（否则对表做不出来）；
#   4) data/mix60f120r_rev_raw.npz 在；5) GPU 余量 ≥ MIN_FREE_MIB。
# 房规：setsid 发车（坑 37）；done 标记 printf 写 + `[ -s ]` 自检（坑 43）；路径全绝对（坑 41）；
#       每个读数「有产物就跳过」⇒ 可断点续跑。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
JOB="pi05_mix60f120r_s3r_seed3000"
RUN="$MG/runs/$JOB"
BASE1000="$MG/runs/pi05_mix60f120r_s2e"
BASE2000="$MG/runs/pi05_mix60f120r_s3r_seed2000"
OUT1="$MG/runs/_diag/epoch_curve_s3r_seed3000_vs_seed1000.md"
OUT2="$MG/runs/_diag/epoch_curve_s3r_seed3000_vs_seed2000.md"
MARK="$MG/runs/s3r_sweep_seed3000.done"
LOG="$MG/logs/sweep_$JOB.log"
die () { echo "[s3rsweep3000] FATAL $*" >&2; exit 4; }

[ -s "$MG/runs/S3R_VERDICT.md" ] || die "档 3r 判定没落盘：runs/S3R_VERDICT.md"
grep -q "FAIL" "$MG/runs/S3R_VERDICT.md" || echo "[s3rsweep3000] 注意：判定里没出现 FAIL 字样（仍按趋势补曲线，只读不判）"
grep -q "80.0%" "$MG/runs/S3R_VERDICT.md" || die "判定里没有 seed3000 的 80.0% ⇒ 出身可疑，先核 runs/S3R_VERDICT.md"
missing=""
for s in 002000 004000 006000 008000 010000 012000 014000 016000 018000 020000 022000; do
  [ -f "$RUN/checkpoints/$s/pretrained_model/model.safetensors" ] || missing="$missing $s"
done
[ -z "$missing" ] || die "seed3000 缺检查点格：$missing ⇒ 扫出来会是断头曲线"
for d in "$BASE1000" "$BASE2000"; do
  nd=$(ls -1d "$d"/sweep_rev/step_*_rev 2>/dev/null | wc -l)
  [ "$nd" -ge 11 ] || die "对表用的 $d 只有 $nd/11 格 ⇒ 先补它"
done
[ -f "$MG/data/mix60f120r_rev_raw.npz" ] || die "反向示范 npz 不在：data/mix60f120r_rev_raw.npz"
echo "[s3rsweep3000] 发车闸全过 $(date '+%F %T')  run=$RUN"

nd=$(ls -1d "$RUN"/sweep_rev/step_*_rev 2>/dev/null | wc -l)
if [ "$nd" -ge 11 ]; then
  echo "[s3rsweep3000] 跳过扫描（已有 $nd/11 格）"
else
  echo "[s3rsweep3000] === 开扫 seed3000 反向 val 11 格 × 20 局（K=10, val seed 8000..）=== $(date '+%F %T')"
  RUN="$RUN" STEPS_TOTAL=22000 SAVE_FREQ=2000 SUB=sweep_rev EPISODES="${EPISODES:-20}" K="${K:-10}" \
    REV_SEED="${REV_SEED:-8000}" DEMO_REV="$MG/data/mix60f120r_rev_raw.npz" MIN_FREE_MIB="${MIN_FREE_MIB:-20000}" \
    bash "$MG/code/mg_sweep_rev.sh" "$RUN" > "$LOG" 2>&1
  rc=$?
  echo "[s3rsweep3000] 扫描 rc=$rc  $(date '+%F %T')  日志 -> $LOG"
  [ "$rc" -eq 0 ] || die "mg_sweep_rev.sh 退出码 $rc（看 $LOG）"
  nd=$(ls -1d "$RUN"/sweep_rev/step_*_rev 2>/dev/null | wc -l)
  [ "$nd" -ge 11 ] || die "只扫出 $nd 格（应 11）⇒ 曲线不完整，不生成对表"
fi

echo "[s3rsweep3000] === epoch 对齐对表（seed3000 vs seed1000 / vs seed2000）=== $(date '+%F %T')"
"$MG_PY" "$MG/code/mg_epoch_curve.py" \
    --run "s3r_seed3000:$RUN" --run "s2e_seed1000:$BASE1000" \
    --direction rev --align --out "$OUT1" > "$MG/logs/epoch_curve_s3r_seed3000_vs_seed1000.log" 2>&1 \
  || die "对表失败（seed1000）：logs/epoch_curve_s3r_seed3000_vs_seed1000.log"
[ -s "$OUT1" ] || die "对表 md 写空了：$OUT1"
"$MG_PY" "$MG/code/mg_epoch_curve.py" \
    --run "s3r_seed3000:$RUN" --run "s3r_seed2000:$BASE2000" \
    --direction rev --align --out "$OUT2" > "$MG/logs/epoch_curve_s3r_seed3000_vs_seed2000.log" 2>&1 \
  || die "对表失败（seed2000）：logs/epoch_curve_s3r_seed3000_vs_seed2000.log"
[ -s "$OUT2" ] || die "对表 md 写空了：$OUT2"

printf '%s 档3r 补充完成 job=%s cells=%s 对表=%s,%s 用途=只看趋势不选点(坑27/42)\n' \
  "$(date '+%F %T')" "$JOB" "$nd" "runs/_diag/epoch_curve_s3r_seed3000_vs_seed1000.md" \
  "runs/_diag/epoch_curve_s3r_seed3000_vs_seed2000.md" > "$MARK"
[ -s "$MARK" ] || die "done 标记写空了（坑 43 复发）"
echo "[s3rsweep3000] done $(date '+%F %T')  标记 -> $MARK"
