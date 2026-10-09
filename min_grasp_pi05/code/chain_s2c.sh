#!/usr/bin/env bash
# 档 2c 全链：预检 -> 反向单任务训练（7600 步，等 epoch）+ 反向 val 扫描（并发）
#           -> 关门读数（主读数用 `last`）-> 失败分类账 -> 判定落盘。
#
# 主读数为什么是 `last` 而不是 val 选点：见 mg_sweep_rev.sh 头注释（档 2 的 val n=10 选点
# 在 TEST 上**反序**，等于在噪声里挑峰）。`last` 与档 2 原门同规则、且等 epoch，可直接对账。
# val 选点只作**并列读数**，两个都报，避免「换规则换到好看为止」。
#
# 预注册的判定规则（跑之前就写死，跑完不许改）：
#   设 P_rev = 反向单任务 @last 在 TEST 7000..7019 上的合并成功率（**4 读 80 局**），
#      P_joint = 档 2 联合模型 @last 在**同一批** TEST seed 上的合并成功率（**4 读 80 局**，
#                = 档 2 门那两读 40 局 + code/chain_s2c_jointbase.sh 补的两读 40 局）。
#   两边都 80 局，才有功效把「32.5% → 50%」判成显著（40 vs 60 局时只有 ~50% 把握）。
#   R1 P_rev ≥ 50% 且 Fisher(P_rev vs P_joint) p<0.05  ⇒ **干扰确认**：反向本身学得会，
#      是被正向挤掉的 ⇒ 处方 = 改数据配比/采样，**不**是「任务不可能」也不是无脑加数据。
#   R2 |P_rev − P_joint| 不显著（p≥0.05）              ⇒ **不是干扰**：去掉正向也没变好，
#      瓶颈在反向任务本身（bin 内抓取 + 侧躺判据）⇒ 处方 = 加反向数据/改示范/改口径。
#   R3 P_rev 显著更高但 < 50%                          ⇒ 干扰存在但不足以过门 ⇒ 两者都要做。
#   护栏（任一不成立 ⇒ 本档结论作废，重跑）：
#   G1 正向零样本对照必须 ≈0%（≤2/20）。它证明 `--dataset.episodes` 真的把正向帧挡在外面了；
#      若正向也能成，说明子集过滤没生效，那这一发训的还是联合模型，结论全废。
#   G2 反向训练 seed 对照不得显著高于 TEST（Fisher p<0.05 且差 >10 pp 才算记忆）。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
JOB="${JOB:-pi05_rev60_s2c}"
RUN="$MG/runs/$JOB"
STEPS="${STEPS:-7600}"
SAVE_FREQ="${SAVE_FREQ:-1000}"
VAL_EPS="${VAL_EPS:-20}"
NEED_FREE_MIB="${NEED_FREE_MIB:-40000}"
NPZ_F="$MG/data/mix60f60r_raw.npz"
NPZ_R="$MG/data/mix60f60r_rev_raw.npz"
NOISE='robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation'
MARK="$RUN/s2c.done"

# ── 0. 等 GPU 空出来（档 2 修正关门那条链还在跑就别抢）─────────────────────
for _ in $(seq 1 240); do
  free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
  [ "${free:-0}" -ge "$NEED_FREE_MIB" ] && break
  echo "[s2c] 显存 free=${free}MiB < ${NEED_FREE_MIB}MiB，等 30 s ... $(date +%H:%M:%S)"
  sleep 30
done

# ── 1. 发车预检（坑 24：命令行必须逐项核对，`bash -n` 查不出丢参数）────────────
if [ -e "$RUN" ]; then
  stale="${RUN}.stale_$(date +%Y%m%d_%H%M%S)"
  echo "[s2c] $RUN 已存在（残留）-> 改名让路：$stale"; mv "$RUN" "$stale"
fi
for m in "$MG/runs/${JOB}_meta"; do
  [ -e "$m" ] && mv "$m" "${m}.stale_$(date +%Y%m%d_%H%M%S)"
done
MUST_HAVE=(
  "--steps=$STEPS"
  "--save_freq=$SAVE_FREQ"
  "--job_name=$JOB"
  "--output_dir=$RUN"
  "--policy.optimizer_lr=1e-4"
  "--policy.scheduler_warmup_steps=200"
  "--policy.chunk_size=50"
  "--dataset.root=$MG/data/mix60f60r"
  "--dataset.episodes=[60,61,62"
  "118,119]"
)
dry=$(DRY_RUN=1 JOB="$JOB" STEPS="$STEPS" SAVE_FREQ="$SAVE_FREQ" bash code/run_pi05_s2c.sh 2>&1)
miss=0
for need in "${MUST_HAVE[@]}"; do
  case "$dry" in
    *"$need"*) echo "[s2c][预检] OK   $need" ;;
    *)         echo "[s2c][预检] MISS $need"; miss=$((miss + 1)) ;;
  esac
done
# 子集家底（帧数/task 字符串）必须由 mg_train.py 的预检行证明，不能只看命令行
for need in "60/120 集，16032/30447 帧" "Take the can out of the bin"; do
  case "$dry" in
    *"$need"*) echo "[s2c][预检] OK   $need" ;;
    *)         echo "[s2c][预检] MISS $need"; miss=$((miss + 1)) ;;
  esac
done
if [ "$miss" -ne 0 ]; then
  echo "[s2c] FATAL 预检未通过（缺 $miss 项），**不发车**。dry-run 输出："; echo "$dry"; exit 4
fi
echo "[s2c] 预检全通过 -> 发车 $(date +%H:%M:%S)"

# ── 2. 训练 + val 扫描（并发；实测并发下 1.9 s/步，单独跑 1.36 s/步）────────────
JOB="$JOB" STEPS="$STEPS" SAVE_FREQ="$SAVE_FREQ" bash code/run_pi05_s2c.sh \
    > "$MG/logs/train_pi05_s2c.log" 2>&1 &
TRAIN_PID=$!
sleep 60
RUN="$RUN" STEPS_TOTAL="$STEPS" SAVE_FREQ="$SAVE_FREQ" EPISODES="$VAL_EPS" \
    bash code/mg_sweep_rev.sh "$RUN" > "$MG/logs/sweep_pi05_s2c.log" 2>&1 &
SWEEP_PID=$!
echo "[s2c] train_pid=$TRAIN_PID sweep_pid=$SWEEP_PID"
wait "$TRAIN_PID"; rc=$?
echo "[s2c] 训练退出 rc=$rc $(date +%H:%M:%S)"
wait "$SWEEP_PID" 2>/dev/null
echo "[s2c] val 扫描结束 $(date +%H:%M:%S)"
[ "$rc" = "0" ] || { echo "[s2c] FATAL 训练非 0 退出，不做关门读数"; exit "$rc"; }

CK="$RUN/checkpoints/last/pretrained_model"
[ -f "$CK/model.safetensors" ] || { echo "[s2c] FATAL 没有 last 检查点：$CK"; exit 3; }
echo "[s2c] last -> $(readlink -f "$RUN/checkpoints/last")"

run_eval () {  # $1=task-mode $2=eps $3=seed-mode $4=seed $5=out $6=tag $7=ckpt $8=video
  local out="$5"
  [ -f "$MG/runs/$out/eval_summary.json" ] && { echo "[s2c] 跳过（已有产物）$out"; return 0; }
  echo "[s2c] === $6 ($1 K=10 eps=$2 seeds=$3/$4) -> runs/$out === $(date +%H:%M:%S)"
  local extra=() npz="$NPZ_F"
  [ "$1" = "reverse" ] && npz="$NPZ_R"
  [ "$8" = "1" ] && extra=(--video --max-videos 3)
  "$MG_PY" code/mg_eval.py --ckpt "$7" --episodes "$2" --seed-mode "$3" --seed "$4" \
      --n-action-steps 10 --task-mode "$1" --demo-npz "$npz" "${extra[@]}" \
      --out "$MG/runs/$out" 2>&1 | grep -vE "$NOISE" | grep -E "^  ep|成功率|policy mean"
}

# 主读数：反向 TEST @last ×4（80 局，1σ≈5 pp）—— 与联合基线同局数，才能做 Fisher
run_eval reverse 20 random 7000 s2c_rev_test_rand20_k10      "TEST 反向 @last rep1" "$CK" 1
run_eval reverse 20 random 7000 s2c_rev_test_rand20_k10_rep2 "TEST 反向 @last rep2" "$CK" 0
run_eval reverse 20 random 7000 s2c_rev_test_rand20_k10_rep3 "TEST 反向 @last rep3" "$CK" 0
run_eval reverse 20 random 7000 s2c_rev_test_rand20_k10_rep4 "TEST 反向 @last rep4" "$CK" 0
# 联合基线的第 3、4 读（同一批 TEST seed，同一个 mix60f60r 的 last 检查点）
# 正常情况已由 code/chain_s2c_jointbase.sh 在训练期间跑完；这里只是**兜底**，缺了就补。
JB="$MG/runs/pi05_mix60f60r_s2/checkpoints/last/pretrained_model"
run_eval reverse 20 random 7000 s2c_jointbase_rev_test_rand20_k10_rep3 "基线补读 联合@last rep3" "$JB" 0
run_eval reverse 20 random 7000 s2c_jointbase_rev_test_rand20_k10_rep4 "基线补读 联合@last rep4" "$JB" 0
# 护栏 G1：正向零样本（证明子集过滤真的生效）
run_eval forward 20 random 2000 s2c_fwd_zeroshot_rand20_k10  "护栏G1 正向零样本 @last" "$CK" 0
# 护栏 G2：反向训练 seed 对照
run_eval reverse 10 random 5000 s2c_rev_control_train10_k10  "护栏G2 反向训练 seed @last" "$CK" 0

# 并列读数：val 选点（若与 last 不同才跑，避免重复烧 GPU）
"$MG_PY" code/mg_select_ckpt.py --run "$RUN" --sweep sweep_rev --direction rev || true
SEL=$("$MG_PY" -c "import json,os;p='$RUN/ckpt_selection.json';print(json.load(open(p))['selected_step'] if os.path.exists(p) else '')" 2>/dev/null || echo "")
if [ -n "$SEL" ] && [ "$SEL" != "$STEPS" ]; then
  CKS=$(printf "%s/checkpoints/%06d/pretrained_model" "$RUN" "$SEL")
  if [ -f "$CKS/model.safetensors" ]; then
    echo "[s2c] val 选点 = step $SEL（≠ last=$STEPS）-> 并列读数"
    run_eval reverse 20 random 7000 s2c_revsel_test_rand20_k10      "TEST 反向 @val选点 rep1" "$CKS" 0
    run_eval reverse 20 random 7000 s2c_revsel_test_rand20_k10_rep2 "TEST 反向 @val选点 rep2" "$CKS" 0
    run_eval reverse 20 random 7000 s2c_revsel_test_rand20_k10_rep3 "TEST 反向 @val选点 rep3" "$CKS" 0
  fi
else
  echo "[s2c] val 选点 = last（或选点失败），不重复跑并列读数"
fi

# 失败分类账（同一份口径，可与档 2 的 runs/_diag/tax_rev_test.md 直接对表）
"$MG_PY" code/mg_tax_fail.py \
    "$MG/runs/s2c_rev_test_rand20_k10" "$MG/runs/s2c_rev_test_rand20_k10_rep2" \
    "$MG/runs/s2c_rev_test_rand20_k10_rep3" "$MG/runs/s2c_rev_test_rand20_k10_rep4" \
    --ceiling "$MG/runs/s2_ceiling_rev_test20_n05" \
    --tag "档 2c 反向单任务 @last（TEST 4 读 80 局）" \
    --out "$MG/runs/_diag/tax_s2c_rev.md" 2>&1 | tail -20

echo "[s2c] === 判定 === $(date +%H:%M:%S)"
"$MG_PY" code/mg_verdict_s2c.py > "$MG/runs/S2C_VERDICT.md" 2>&1
date +"%Y-%m-%d %H:%M:%S job=$JOB steps=$STEPS" > "$MARK"
echo "[s2c] done $(date +%H:%M:%S)  标记 -> $MARK"
