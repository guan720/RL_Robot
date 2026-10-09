#!/usr/bin/env bash
# 档 2e · 训练 + 关门链：60 正向 + **120** 反向（rev:fwd = 2:1）
#
# 发车条件（两个都要，缺一不可）：
#   1) runs/s2e_data.done  —— 数据三道闸已过（集数收满 / 正向逐比特复现 / 反向严格超集 + 不撞留出 seed）
#   2) runs/pi05_rev60_s2c/s2c.done —— 档 2c 的判定已落盘。**先读消融、再动数据**，
#      否则两条杠杆一起拉，赢了也不知道是谁的功劳（README 坑 33 尾条）。
#
# 唯一变量 = 数据（反向 60→120 条、采样占比 1:1→2:1）。lr / warmup / batch / chunk_size /
# 基座（pi05_base_lr044）/ seed / K=10 / TEST seed 窗口 / 门（≥50%）全部照抄档 2、档 2c。
#
# ⚠️ 等 epoch 而不是等步数：本档帧数与前两档都不同，STEPS 由 run_pi05_s2e.sh 从
#    data/mix60f120r/meta/info.json 的 total_frames 现算（× 3.79 ep，取整到 save_freq）。
#    照抄 7600 或 14400 = 悄悄改了训练量 = 第二个变量（README 坑 33）。
# ⚠️ 跨档绝对数值不可直接比：换数据集 ⇒ normalizer 重算。mg_verdict_s2e.py 的 GD 项
#    会把 mix60f60r 与 mix60f120r 的 stats 漂移量出来一起报。严格归因要 1:1 对照臂
#    （EPISODES_SUBSET=0-119，见 run_pi05_s2e.sh 头注释），**备而不用**。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"

DATASET="${DATASET:-mix60f120r}"
JOB="${JOB:-pi05_${DATASET}_s2e}"
RUN="$MG/runs/$JOB"
SAVE_FREQ="${SAVE_FREQ:-2000}"
TARGET_EPOCHS="${TARGET_EPOCHS:-3.79}"
VAL_EPS="${VAL_EPS:-20}"
NEED_FREE_MIB="${NEED_FREE_MIB:-40000}"
NPZ_F="$MG/data/${DATASET}_raw.npz"
NPZ_R="$MG/data/${DATASET}_rev_raw.npz"
NOISE='robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation'
MARK="$RUN/s2e.done"
DATA_MARK="$MG/runs/s2e_data.done"
S2C_MARK="$MG/runs/pi05_rev60_s2c/s2c.done"

# ── 0. 等两个前置条件（最多 12 h）───────────────────────────────────────────
for _ in $(seq 1 720); do [ -f "$DATA_MARK" ] && [ -f "$S2C_MARK" ] && break; sleep 60; done
[ -f "$DATA_MARK" ] || { echo "[s2e] FATAL 等了 12 h 还没有 $DATA_MARK（看 logs/chain_s2e_data.log / runs/s2e_data.FAILED）"; exit 4; }
[ -f "$S2C_MARK" ]  || { echo "[s2e] FATAL 等了 12 h 还没有 $S2C_MARK（看 logs/chain_s2c.log）"; exit 4; }
echo "[s2e] 前置齐了：$(cat "$DATA_MARK") | $(cat "$S2C_MARK")"
# ── 0b. 档 2c 的判定必须是「可用」的，否则**不自动发车**（10 h 的 GPU 不能押在作废的消融上）──
# 纪律：本链**不根据判定改自己的任何参数**（规则在 mg_verdict_s2e.py 里已预注册），
#       只用判定当**发车闸**：护栏作废 / 判定悬空 / 出现"反而更差"这种矛盾结果 ⇒ 停下来等人看。
VERD="$MG/runs/S2C_VERDICT.md"
[ -f "$VERD" ] || { echo "[s2e] FATAL 有 s2c.done 却没有 $VERD（主链末尾应当先写判定再写标记）"; exit 4; }
BRANCH=""
case "$(cat "$VERD")" in
  *"全部结论作废"*) echo "[s2e] FATAL 档 2c 护栏 G1 不成立、判定作废 ⇒ 不自动发车，先看 $VERD"; exit 6;;
  *"反而显著更差"*) echo "[s2e] FATAL 档 2c 出现矛盾结果（单任务反而更差）⇒ 先查子集过滤/等 epoch，不发车"; exit 6;;
  *"R1 干扰确认"*)  BRANCH="R1 干扰确认";;
  *"R3 干扰存在"*)  BRANCH="R3 干扰存在但不足以过门";;
  *"R2 不是干扰"*)  BRANCH="R2 不是干扰";;
  *) echo "[s2e] FATAL 判定里没认出 R1/R2/R3（可能还悬空）⇒ 不自动发车，先看 $VERD"; exit 6;;
esac
case "$(cat "$VERD")" in
  *"悬空"*|*"无法判"*) echo "[s2e] FATAL 判定仍悬空（护栏产物没齐）⇒ 不自动发车"; exit 6;;
esac
echo "[s2e] 档 2c 判定分支 = **$BRANCH**（出处 $VERD）"
echo "[s2e] 注意：三个分支的处方**都**包含「反向数据翻倍 + 2:1 配比」，所以本链的动作不随分支改变；"
echo "[s2e]       分支只改变**判读**（见 mg_verdict_s2e.py 的 P1/P2/P3 与 GD 归一化漂移项）。"

for _ in $(seq 1 240); do
  free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
  [ "${free:-0}" -ge "$NEED_FREE_MIB" ] && break
  echo "[s2e] 显存 free=${free}MiB < ${NEED_FREE_MIB}MiB，等 30 s ... $(date +%H:%M:%S)"; sleep 30
done

# ── 1. 等 epoch 步数（由 run_pi05_s2e.sh 现算，不在这里硬写）────────────────────
STEPS=$(DATASET="$DATASET" SAVE_FREQ="$SAVE_FREQ" TARGET_EPOCHS="$TARGET_EPOCHS" \
        bash code/run_pi05_s2e.sh 2>&1 | grep -oE "取整到 save_freq\([0-9]+\) = [0-9]+" | grep -oE "[0-9]+$")
[ -n "${STEPS:-}" ] || { echo "[s2e] FATAL 算不出 STEPS"; exit 5; }
echo "[s2e] STEPS=$STEPS（save_freq=$SAVE_FREQ，目标 $TARGET_EPOCHS epoch）"

# ── 2. 发车预检（坑 24：命令行必须逐项核对，`bash -n` 查不出丢参数）──────────────
if [ -e "$RUN" ]; then
  stale="${RUN}.stale_$(date +%Y%m%d_%H%M%S)"
  echo "[s2e] $RUN 已存在（残留）-> 改名让路：$stale"; mv "$RUN" "$stale"
fi
for m in "$MG/runs/${JOB}_meta"; do
  [ -e "$m" ] && mv "$m" "${m}.stale_$(date +%Y%m%d_%H%M%S)"
done
# dry-run 会写 <out>_meta/，用一次性 JOB 名，别把真 meta 提前占了
dry=$(DRY_RUN=1 DATASET="$DATASET" JOB="${JOB}_dryrun" STEPS="$STEPS" SAVE_FREQ="$SAVE_FREQ" \
      TARGET_EPOCHS="$TARGET_EPOCHS" bash code/run_pi05_s2e.sh 2>&1)
miss=0
MUST_HAVE=(
  "--steps=$STEPS"
  "--save_freq=$SAVE_FREQ"
  "--job_name=$JOB"
  "--output_dir=$RUN"
  "--dataset.root=$MG/data/$DATASET"
  "--policy.optimizer_lr=1e-4"
  "--policy.scheduler_warmup_steps=200"
  "--policy.chunk_size=50"
  "--policy.path=$MG/weights/pi05_base_lr044"
  "--seed=1000"
)
for need in "${MUST_HAVE[@]}"; do
  case "$dry" in
    *"$need"*) echo "[s2e][预检] OK   $need" ;;
    *)         echo "[s2e][预检] MISS $need"; miss=$((miss + 1));;
  esac
done
# 2:1 臂必须**用全部 180 集** ⇒ 命令行里绝不能出现 --dataset.episodes（出现了就是在筛子集）
case "$dry" in
  *"--dataset.episodes"*) echo "[s2e][预检] MISS 出现了 --dataset.episodes（2:1 臂应当用全集）"; miss=$((miss + 1));;
  *) echo "[s2e][预检] OK   没有 --dataset.episodes（= 全 180 集，rev:fwd=2:1）";;
esac
# 家底必须由 info.json 证明：180 集 / 2 个 task
INFO="$MG/data/$DATASET/meta/info.json"
read -r TEP TTK TFR <<< "$("$MG_PY" -c "
import json; j=json.load(open('$INFO'))
print(j['total_episodes'], j.get('total_tasks',-1), j['total_frames'])")"
echo "[s2e][预检] 出处 $INFO: total_episodes=$TEP total_tasks=$TTK total_frames=$TFR"
[ "$TEP" = "180" ] || { echo "[s2e][预检] MISS total_episodes=$TEP != 180"; miss=$((miss + 1)); }
[ "$TTK" = "2" ]   || { echo "[s2e][预检] MISS total_tasks=$TTK != 2"; miss=$((miss + 1)); }
if [ "$miss" -ne 0 ]; then
  echo "[s2e] FATAL 预检未通过（缺 $miss 项），**不发车**。dry-run 输出："; echo "$dry"; exit 4
fi
echo "[s2e] 预检全通过 -> 发车 $(date +%H:%M:%S)"

# ── 3. 训练 + 反向 val 扫描（并发）──────────────────────────────────────────
DATASET="$DATASET" JOB="$JOB" STEPS="$STEPS" SAVE_FREQ="$SAVE_FREQ" \
    TARGET_EPOCHS="$TARGET_EPOCHS" bash code/run_pi05_s2e.sh \
    > "$MG/logs/train_${JOB}.log" 2>&1 &
TRAIN_PID=$!
sleep 60
RUN="$RUN" STEPS_TOTAL="$STEPS" SAVE_FREQ="$SAVE_FREQ" EPISODES="$VAL_EPS" \
    SUB="sweep_rev" DEMO_REV="$NPZ_R" \
    bash code/mg_sweep_rev.sh "$RUN" > "$MG/logs/sweep_${JOB}.log" 2>&1 &
SWEEP_PID=$!
echo "[s2e] train_pid=$TRAIN_PID sweep_pid=$SWEEP_PID"
wait "$TRAIN_PID"; rc=$?
echo "[s2e] 训练退出 rc=$rc $(date +%H:%M:%S)"
wait "$SWEEP_PID" 2>/dev/null
echo "[s2e] val 扫描结束 $(date +%H:%M:%S)"
[ "$rc" = "0" ] || { echo "[s2e] FATAL 训练非 0 退出，不做关门读数"; exit "$rc"; }

CK="$RUN/checkpoints/last/pretrained_model"
[ -f "$CK/model.safetensors" ] || { echo "[s2e] FATAL 没有 last 检查点：$CK"; exit 3; }
echo "[s2e] last -> $(readlink -f "$RUN/checkpoints/last")"

run_eval () {  # $1=task-mode $2=eps $3=seed $4=out $5=tag $6=ckpt $7=video
  local out="$4"
  [ -f "$MG/runs/$out/eval_summary.json" ] && { echo "[s2e] 跳过（已有产物）$out"; return 0; }
  echo "[s2e] === $5 ($1 K=10 eps=$2 seed=$3) -> runs/$out === $(date +%H:%M:%S)"
  local extra=() npz="$NPZ_F"
  [ "$1" = "reverse" ] && npz="$NPZ_R"
  [ "$7" = "1" ] && extra=(--video --max-videos 3)
  "$MG_PY" code/mg_eval.py --ckpt "$6" --episodes "$2" --seed-mode random --seed "$3" \
      --n-action-steps 10 --task-mode "$1" --demo-npz "$npz" "${extra[@]}" \
      --out "$MG/runs/$out" 2>&1 | grep -vE "$NOISE" | grep -E "^  ep|成功率|policy mean"
}

# 主读数：反向 TEST 4 读 80 局（与档 2 / 档 2c 同 seed、同 K、同局数）
run_eval reverse 20 7000 s2e_rev_test_rand20_k10      "TEST 反向 @last rep1" "$CK" 1
run_eval reverse 20 7000 s2e_rev_test_rand20_k10_rep2 "TEST 反向 @last rep2" "$CK" 0
run_eval reverse 20 7000 s2e_rev_test_rand20_k10_rep3 "TEST 反向 @last rep3" "$CK" 0
run_eval reverse 20 7000 s2e_rev_test_rand20_k10_rep4 "TEST 反向 @last rep4" "$CK" 0
# 护栏 GA：正向未见（2:1 把正向占比压到 1/3，必须证明没拆东墙补西墙）
run_eval forward 20 2000 s2e_fwd_test_rand20_k10      "护栏GA 正向未见 @last rep1" "$CK" 0
run_eval forward 20 2000 s2e_fwd_test_rand20_k10_rep2 "护栏GA 正向未见 @last rep2" "$CK" 0

# 护栏 GB：反向**训练 seed** 对照。mg_eval 只能给连续窗口（seed = args.seed + ep），
# 而反向采集带重试 ⇒ seed 不连续（坑 32）。所以这里**现算**覆盖率最高的 10-seed 窗口，
# 并把「10 局里有几局真是训练局」打印出来 —— 不许默认全是。
CTRL_SEED=$("$MG_PY" - "$NPZ_R" <<'PY'
import sys, numpy as np
seeds = sorted(int(x) for x in np.load(sys.argv[1])["seeds"])
S = set(seeds)
lo, hi = min(seeds), max(seeds)
best, best_cov = None, (-1, 10**9)
for st in range(lo, hi - 9 + 1):
    cov = sum(1 for k in range(st, st + 10) if k in S)
    if (cov, -st) > (best_cov[0], -best_cov[1]):
        best, best_cov = st, (cov, st)
st, cov = best, best_cov[0]
win = list(range(st, st + 10))
print(st, file=sys.stdout)
print("[s2e][GB 窗口] 出处 %s：反向训练 seed %d 个，区间 [%d,%d]" % (sys.argv[1], len(seeds), lo, hi), file=sys.stderr)
print("[s2e][GB 窗口] 选中 %d..%d，其中 %d/10 真在训练集里；不在的是 %s"
      % (st, st + 9, cov, [k for k in win if k not in S]), file=sys.stderr)
if cov < 8:
    print("[s2e][GB 窗口] WARN 覆盖 <8/10 ⇒ 这道护栏的功效更低，判定里必须照实写", file=sys.stderr)
PY
)
echo "[s2e] 护栏 GB 训练 seed 窗口起点 = $CTRL_SEED"
for i in "" _rep2 _rep3 _rep4; do
  run_eval reverse 10 "$CTRL_SEED" "s2e_rev_control_train10_k10$i" "护栏GB 反向训练 seed @last$i" "$CK" 0
done

# ── 并列读数：val 选点（与档 2c 同规则，**只是并列、不是门**）──────────────────
# 为什么要有它：档 2 的联合模型反向 val 在 2.89 ep 见顶 50%、3.42 ep 崩到 0%，而两边的 `last`
# 都在 3.79 ep ⇒ **主读数有可能落在下降尾巴上**。若 2:1 臂也这样，只看 `last` 会把
# 「训过头」误读成「数据没用」，白烧 10 h。
# ⚠️ 但坑 27 已经证明 val 选不出点（val 50% 的检查点 TEST 只有 26.7%，与 `last` 反序）
# ⇒ 门**始终**是 `last`；val 选点这一读只并列报告，任何情况下都不许拿它改判定。
"$MG_PY" code/mg_select_ckpt.py --run "$RUN" --sweep sweep_rev --direction rev || true
SEL=$("$MG_PY" -c "import json,os;p='$RUN/ckpt_selection.json';print(json.load(open(p))['selected_step'] if os.path.exists(p) else '')" 2>/dev/null || echo "")
if [ -n "$SEL" ] && [ "$SEL" != "$STEPS" ]; then
  CKS=$(printf "%s/checkpoints/%06d/pretrained_model" "$RUN" "$SEL")
  if [ -f "$CKS/model.safetensors" ]; then
    echo "[s2e] val 选点 = step $SEL（≠ last=$STEPS）-> 并列读数（不是门）"
    for i in "" _rep2 _rep3; do
      run_eval reverse 20 7000 "s2e_revsel_test_rand20_k10$i" "TEST 反向 @val选点$i" "$CKS" 0
    done
  fi
else
  echo "[s2e] val 选点 = last（或选点失败），不重复跑并列读数"
fi

# 失败分类账（与档 2 / 档 2c 同一口径，可直接对表）
"$MG_PY" code/mg_tax_fail.py \
    "$MG/runs/s2e_rev_test_rand20_k10" "$MG/runs/s2e_rev_test_rand20_k10_rep2" \
    "$MG/runs/s2e_rev_test_rand20_k10_rep3" "$MG/runs/s2e_rev_test_rand20_k10_rep4" \
    --ceiling "$MG/runs/s2_ceiling_rev_test20_n05" \
    --tag "档 2e 2:1 配比 @last（TEST 4 读 80 局）" \
    --out "$MG/runs/_diag/tax_s2e_rev.md" 2>&1 | tail -20

# epoch 对齐的 val 曲线（本档 vs 档 2c 单任务 vs 档 2 联合），只报趋势
"$MG_PY" code/mg_epoch_curve.py \
    --run "s2e_2to1:runs/$JOB:sweep_rev" \
    --run "s2c_revonly:runs/pi05_rev60_s2c:sweep_rev" \
    --run "s2_joint:runs/pi05_mix60f60r_s2:sweep_bidir" \
    --direction rev --out "$MG/runs/_diag/epoch_curve_s2e.md" 2>&1 | tail -5 || true

echo "[s2e] === 判定 === $(date +%H:%M:%S)"
"$MG_PY" code/mg_verdict_s2e.py > "$MG/runs/S2E_VERDICT.md" 2>&1
date +"%Y-%m-%d %H:%M:%S job=$JOB steps=$STEPS dataset=$DATASET s2c_branch=$BRANCH" > "$MARK"
echo "[s2e] done $(date +%H:%M:%S)  标记 -> $MARK"
