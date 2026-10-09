#!/usr/bin/env bash
# 档 3r · 反向任务的**训练 seed 稳健性**（用户阶梯第 3 步在反向侧的补做）
#
# 为什么要这一档：正向已有档 3（seed 1000/2000/3000，70.0%/63.3%/70.0%，最差 ≥50% ⇒ PASS）。
# 反向到现在为止**只有一个训练 seed（1000）**：档 2(1:1) 37.5% → 档 2c(单任务) 45.0% →
# 档 2e(2:1) 严格 52.5% / 放宽 68.8%。三档同 seed、不同数据，方向一致，但
# 「换个 seed 还成立吗」没人答过 ⇒ 反向的过门有可能是 seed 运气。
#
# 唯一变量 = 训练 seed。数据集（mix60f120r，180 集 46426 帧）/ 等 epoch 步数（22000 = 3.79 ep）/
# lr 1e-4 / warmup 200 / batch 8 / chunk_size 50 / 基座 pi05_base_lr044 / K=10 /
# TEST seed 窗口 7000..7019 / 局数 4×20 —— **全部照抄档 2e**，一个都不动。
#
# 预注册门（跑前写死，看完数不许改）：
#   主口径 = **放宽 R**（用户 2026-10-02 定的首要条件：送到目标区；侧躺算送到并打标）。
#   门 = **最差的那个 seed 放宽口径 ≥ 50%**（与正向档 3 同一条规则，只是口径换成主口径）。
#   严格口径 4×20 并列报（同一次评测并行输出，不额外花 GPU），不参与门。
#   ✅ PASS  ⇒ 反向能力对训练 seed 稳健，可以进档 4r（chunk 执行）/ 档 5（Harness）。
#   ❌ FAIL  ⇒ 反向过门含 seed 运气成分；处方 = 多 seed 集成 / 加数据 / 查是不是某个 seed 训崩了
#              （先看它的 val 曲线再下结论，别急着加数据）。
#
# 发车闸（等盘上产物，不看进程表）：
#   1) runs/pi05_mix60f120r_s2e/s2e.done 存在 —— 档 2e 关门读数跑完；
#   2) runs/S2E_VERDICT.md 里**不含** "P3 FAIL" —— P3 的处方是「停止往反向加数据、转修 A 类抓空」，
#      那就该停下来改路线，而不是再烧 18 h GPU；
#   3) runs/S2E_VERDICT.md 里**不含** "全部结论作废"（护栏作废）。
#   出现 2) 或 3) ⇒ exit 6，等人看。
#
# ⚠️ 不跑全量 val 扫描：档 2e 的 val 曲线已经证明 `last` 是更好的工作点（val 选点 36.7% < @last），
#   且 11 格 × 20 局 × 2 个 seed ≈ 3 h GPU，性价比低。只读 `last`。若某个 seed 明显崩，
#   再单独补它的 val 曲线（补的命令写在下面 note 里）。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
NOISE='robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation'
DATASET="mix60f120r"
STEPS="${STEPS:-22000}"          # 等 epoch：46426 帧 / bs8 = 5803.25 steps/ep × 3.79 = 21994 -> 取整 22000
SAVE_FREQ="${SAVE_FREQ:-2000}"
SEEDS="${SEEDS:-2000 3000}"
EP="${EP:-20}"
REPS="${REPS:-4}"
S2E_DONE="$MG/runs/pi05_mix60f120r_s2e/s2e.done"
S2E_VERD="$MG/runs/S2E_VERDICT.md"
NPZ_R="$MG/data/mix60f120r_rev_raw.npz"
NPZ_F="$MG/data/mix60f120r_raw.npz"
MIN_FREE_MIB="${MIN_FREE_MIB:-40000}"
MARK="$MG/runs/s3r.done"
FAILED="$MG/runs/s3r.FAILED"

die () { echo "[s3r] FATAL $1" | tee -a "$FAILED"; exit 4; }

# ── 0. 发车闸 ───────────────────────────────────────────────────────────────
for _ in $(seq 1 720); do [ -f "$S2E_DONE" ] && break; sleep 60; done
[ -f "$S2E_DONE" ] || { echo "[s3r] FATAL 等 12 h 还没有 $S2E_DONE"; exit 4; }
echo "[s3r] 档 2e 已关门：$(cat "$S2E_DONE")"
[ -f "$S2E_VERD" ] || die "有 s2e.done 却没有 $S2E_VERD"
case "$(cat "$S2E_VERD")" in
  *"全部结论作废"*) echo "[s3r] FATAL 档 2e 护栏作废 ⇒ 不自动发车，先看 $S2E_VERD"; exit 6;;
  *"P3 FAIL"*)      echo "[s3r] FATAL 档 2e 判定是 P3（数据量不是杠杆，处方是停止加数据）";
                    echo "[s3r]       ⇒ 再烧 18 h 训两个 seed 与处方冲突，停下来等人改路线"; exit 6;;
esac
echo "[s3r] 档 2e 判定可用（非 P3、护栏未作废）⇒ 发车 $(date +%H:%M:%S)"
grep -oE "P[123] (PASS|FAIL)[^）]*" "$S2E_VERD" | head -2

# ── 1. 显存闸（训练要 ~35 GB）───────────────────────────────────────────────
wait_gpu () {
  local free
  for _ in $(seq 1 240); do
    free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
    [ "${free:-0}" -ge "$MIN_FREE_MIB" ] && return 0
    echo "[s3r] 显存 free=${free}MiB < ${MIN_FREE_MIB}MiB，等 30 s ... $(date +%H:%M:%S)"; sleep 30
  done
  echo "[s3r] 等了 2 h 显存还不够，硬上"; return 0
}

# ── 2. 逐 seed：训练 -> 关门读数 ────────────────────────────────────────────
for SD in $SEEDS; do
  JOB="pi05_${DATASET}_s3r_seed${SD}"
  RUN="$MG/runs/$JOB"
  CK="$RUN/checkpoints/last/pretrained_model"
  echo "[s3r] ================= seed $SD -> $JOB ================= $(date +%H:%M:%S)"
  if [ -f "$CK/model.safetensors" ]; then
    echo "[s3r] 训练产物已在（跳过训练）：$CK"
  else
    wait_gpu
    # 等 epoch 步数由 run_pi05_s2e.sh 现算并打印，这里核对它算出来的确实是 STEPS（坑 33）
    calc=$(DATASET="$DATASET" SAVE_FREQ="$SAVE_FREQ" bash code/run_pi05_s2e.sh 2>&1 \
           | grep -oE "取整到 save_freq\([0-9]+\) = [0-9]+" | grep -oE "[0-9]+$")
    echo "[s3r] 等 epoch 步数核对：现算=$calc  本档用=$STEPS（出处 run_pi05_s2e.sh，3.79 ep）"
    [ "$calc" = "$STEPS" ] || die "等 epoch 步数对不上（现算 $calc ≠ $STEPS）⇒ 会悄悄改训练量"
    DATASET="$DATASET" JOB="$JOB" STEPS="$STEPS" SAVE_FREQ="$SAVE_FREQ" SEED="$SD" \
        bash code/run_pi05_s2e.sh > "$MG/logs/train_${JOB}.log" 2>&1
    rc=$?
    echo "[s3r] seed $SD 训练退出 rc=$rc $(date +%H:%M:%S)"
    [ "$rc" = "0" ] || die "seed $SD 训练非 0 退出（看 logs/train_${JOB}.log）"
  fi
  # 坑 38：`last` 是每次 save 都重指的软链，必须核对它指向终点格再用
  want=$(printf "%06d" "$STEPS")
  rl=$(readlink "$RUN/checkpoints/last" 2>/dev/null || echo "")
  echo "[s3r] last -> ${rl:-无}（期望 $want）"
  [ "$rl" = "$want" ] || die "last 指向 $rl 而不是 $want ⇒ 终点格不对，读数会读错权重（坑 38）"

  wait_gpu_eval () {
    local free
    for _ in $(seq 1 120); do
      free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
      [ "${free:-0}" -ge 9000 ] && return 0
      sleep 15
    done
    return 0
  }

  run_eval () {  # $1=mode $2=eps $3=seed $4=out $5=tag $6=K
    local out="$4"
    [ -f "$MG/runs/$out/eval_summary.json" ] && { echo "[s3r] 跳过（已有产物）$out"; return 0; }
    wait_gpu_eval
    echo "[s3r] === $5 ($1 K=$6 eps=$2 seed=$3) -> runs/$out === $(date +%H:%M:%S)"
    local npz="$NPZ_F"; [ "$1" = "reverse" ] && npz="$NPZ_R"
    "$MG_PY" code/mg_eval.py --ckpt "$CK" --episodes "$2" --seed-mode random --seed "$3" \
        --n-action-steps "$6" --task-mode "$1" --demo-npz "$npz" \
        --out "$MG/runs/$out" 2>&1 | grep -vE "$NOISE" | grep -E "^  ep|成功率|放宽口径|warn|Error|Traceback"
    [ -f "$MG/runs/$out/eval_summary.json" ] || die "评测没落盘：$out"
  }

  # 主读数：反向 TEST 4×20（与档 2/2c/2e 同 seed 窗口同 K，两口径并行输出）
  for i in $(seq 1 "$REPS"); do
    suf=""; [ "$i" -gt 1 ] && suf="_rep$i"
    run_eval reverse "$EP" 7000 "s3r_seed${SD}_rev_test_rand20_k10$suf" "seed$SD 反向 TEST rep$i" 10
  done
  # 护栏：正向未见 1×20（2:1 把正向压到 1/3，必须证明没拆东墙补西墙；门 ≤ 掉 15 pp）
  run_eval forward "$EP" 2000 "s3r_seed${SD}_fwd_test_rand20_k10" "seed$SD 护栏 正向未见" 10
  # note: 若某 seed 明显崩，补它的 val 曲线用：
  #   RUN=runs/<JOB> STEPS_TOTAL=22000 SAVE_FREQ=2000 SUB=sweep_rev \
  #   DEMO_REV=data/mix60f120r_rev_raw.npz bash code/mg_sweep_rev.sh runs/<JOB>
done

echo "[s3r] === 判定汇编 === $(date +%H:%M:%S)"
"$MG_PY" code/mg_verdict_s3r.py > "$MG/runs/S3R_VERDICT.md" 2>&1
tail -40 "$MG/runs/S3R_VERDICT.md"
date +"%Y-%m-%d %H:%M:%S 档3r 反向 seed 稳健性完成 seeds=%s steps=%s dataset=%s" \
     "$(echo "$SEEDS" | tr ' ' ',')" "$STEPS" "$DATASET" > "$MARK"
echo "[s3r] done $(date +%H:%M:%S)  标记 -> $MARK"
