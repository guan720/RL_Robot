#!/usr/bin/env bash
# 档 3r FAIL 处方第 1 步 · seed 2000 的 **val 曲线**（预注册写死：先看曲线，别急着加数据）
#
# 为什么要这一条：seed 2000 反向 4×20 放宽 33/80 = 41.2%（门 ≥50% FAIL）、正向护栏 4/20 = 20.0%
# （基线 64.3%，掉 44.3 pp）。但它的训练 loss 与 seed 1000 逐点相差 ≤0.0012 ⇒ **不是训崩**。
# 那就只剩两种可能，而它们处方完全不同，必须靠 val 曲线分辨：
#   (a) @022000 恰好是它的坏点（曲线整体正常，终点掉坑）⇒ 处方 = 选点/早停，不是加数据；
#   (b) 整条曲线都低（学习本身就没起来）        ⇒ 处方 = 多 seed 集成 / 加数据 / 查配比。
# ⚠️ 本条**不选点、不改门**：val n=20 选不出点（坑 27 + 坑 42 实测），曲线只当「学习趋势」读，
#   与档 2c / 2e 的既有口径一致（`code/mg_sweep_rev.sh` 头注释）。
#
# 发车闸（全部看盘上产物）：
#   1) runs/S3R_VERDICT.md  档 3r 的正式判定已落盘（FAIL 是被**判**出来的，不是我口头说的）；
#   2) runs/s3r.done        档 3r 链收工（坑 43 会把它写成 0 字节 ⇒ 只判 -f）；
#   3) runs/s5_timing.done  档 5 的**隔离**实时性读数已跑完（那一格要求 GPU 独占，不能和它抢）；
#   4) seed 2000 的 11 个检查点在盘上（缺格就 die，别静默扫出一条断头曲线）。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
JOB="pi05_mix60f120r_s3r_seed2000"
RUN="$MG/runs/$JOB"
BASE="$MG/runs/pi05_mix60f120r_s2e"          # seed 1000（档 2e），同数据同步数，只差训练 seed
OUTMD="$MG/runs/_diag/epoch_curve_s3r_seed2000.md"
MARK="$MG/runs/s3r_sweep_seed2000.done"
LOG="$MG/logs/sweep_$JOB.log"
die () { echo "[s3rsweep] FATAL $*" >&2; exit 4; }

wait_file () {  # $1=路径 $2=小时上限 $3=说明
  local f="$1" h="$2" what="$3"
  for _ in $(seq 1 $((h * 60))); do
    [ -f "$f" ] && { echo "[s3rsweep] 等到 $what：$f  $(date '+%F %T')"; return 0; }
    sleep 60
  done
  die "等 ${h} h 还没等到 $what：$f"
}

wait_file "$MG/runs/S3R_VERDICT.md" 16 "档 3r 正式判定"
wait_file "$MG/runs/s3r.done"       16 "档 3r 收工"
wait_file "$MG/runs/s5_timing.done"  4 "档 5 隔离实时性读数"
grep -qi "FAIL" "$MG/runs/S3R_VERDICT.md" || {
  echo "[s3rsweep] 注意：S3R_VERDICT.md 里没出现 FAIL 字样 ⇒ 处方前提可能不成立，仍按预注册把曲线补上（只读不判）"
}

missing=""
for s in 002000 004000 006000 008000 010000 012000 014000 016000 018000 020000 022000; do
  [ -f "$RUN/checkpoints/$s/pretrained_model/model.safetensors" ] || missing="$missing $s"
done
[ -z "$missing" ] || die "seed 2000 缺检查点格：$missing ⇒ 扫出来会是断头曲线，先查训练"
[ -f "$MG/data/mix60f120r_rev_raw.npz" ] || die "反向示范 npz 不在：data/mix60f120r_rev_raw.npz"

echo "[s3rsweep] === 开扫 seed 2000 反向 val 11 格 × 20 局（K=10, val seed 8000..）=== $(date '+%F %T')"
RUN="$RUN" STEPS_TOTAL=22000 SAVE_FREQ=2000 SUB=sweep_rev EPISODES="${EPISODES:-20}" K="${K:-10}" \
  REV_SEED="${REV_SEED:-8000}" DEMO_REV="$MG/data/mix60f120r_rev_raw.npz" MIN_FREE_MIB="${MIN_FREE_MIB:-20000}" \
  bash "$MG/code/mg_sweep_rev.sh" "$RUN" > "$LOG" 2>&1
rc=$?
echo "[s3rsweep] 扫描 rc=$rc  $(date '+%F %T')  日志 -> $LOG"
[ "$rc" -eq 0 ] || die "mg_sweep_rev.sh 退出码 $rc（看 $LOG）"
nd=$(ls -1d "$RUN"/sweep_rev/step_*_rev 2>/dev/null | wc -l)
echo "[s3rsweep] 落盘格数 = $nd / 11"
[ "$nd" -ge 11 ] || die "只扫出 $nd 格（应 11）⇒ 曲线不完整，不生成对表"

echo "[s3rsweep] === epoch 对齐对表（seed 2000 vs seed 1000/档 2e）=== $(date '+%F %T')"
"$MG_PY" "$MG/code/mg_epoch_curve.py" \
    --run "s3r_seed2000:$RUN" --run "s2e_seed1000:$BASE" \
    --direction rev --align --out "$OUTMD" > "$MG/logs/epoch_curve_s3r_seed2000.log" 2>&1 \
  || die "epoch 对表失败（看 logs/epoch_curve_s3r_seed2000.log）"
[ -s "$OUTMD" ] || die "对表 md 写空了：$OUTMD"

printf '%s 档3r FAIL 处方第1步完成 job=%s cells=%s 对表=%s\n' \
  "$(date '+%F %T')" "$JOB" "$nd" "runs/_diag/epoch_curve_s3r_seed2000.md" > "$MARK"
[ -s "$MARK" ] || die "done 标记写空了（坑 43 复发）"
echo "[s3rsweep] done $(date '+%F %T')  标记 -> $MARK"
