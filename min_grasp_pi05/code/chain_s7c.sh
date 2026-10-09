#!/usr/bin/env bash
# 档 7C · **条件发车**链：新配方（bs32 等 epoch）补 seed 1000 / 3000，把 n 凑到 3 关 C2 使命门
#
# 出处（判据全部写死在 `runs/S7_PREREG.md` §3 格 7C，2026-10-03 13:52 落盘，**早于任何 7B 读数**）：
#   档 3r 的唯一缺口是 seed 稳健性：三个训练 seed 的反向 TEST 放宽口径 = 68.8 / **41.2** / 80.0%，
#   极差 38.8 pp、最差 seed 打穿 50% 的门 ⇒ FAIL。档 7B 用「batch 8→32 + sqrt 缩放 lr + 等 epoch」
#   这一组绑定项去压 run 间方差（机理读数 η₈ = 54.2%，见 `runs/s7_probe/gradnoise.md`）。
#   但 7B 只有 n=1 ⇒ 按坑 57 **不能**说「新配方更好」；7C 就是把 n 补到 3，
#   用与档 3r **完全同一条门**（C2：最差 seed 的放宽口径 ≥ 50%）判「seed 稳健性缺口是否关闭」。
#
# 为什么是「条件发车」而不是排死队：
#   * 预注册写明 **7B 的 M1∧M2∧M3 全过才发 7C**。M4（使命门）过不过都发 —— M4❌ 只说明这一发没达标，
#     仍然需要 n=3 才能区分「配方没用」与「这一发运气差」（预注册判定表第 2 行就是这么写的）。
#   * M5（正向护栏）**不在**预注册的发车条件里 ⇒ 本链只把它抄进 `runs/S7C_GATE.md` 记录，不拿它当闸
#     （坑 40：判据不许看完数再改；要改也得先落盘新的预注册）。
#   * 条件不满足 ⇒ 写 `runs/s7c.SKIPPED` 并 exit 0。这是预注册的分支，**不是失败**。
#
# 每个 seed 的读数与档 7B **逐项同口径**（只换 seed）：
#   训练 bs32 / 5500 步（等 epoch 3.79）/ save_freq 500 / log_freq 25 / lr 2e-4 / grad-ckpt on
#   -> `last` 软链核对（坑 38）-> 11 格反向 val 扫描（每格 20 局、K=10、val seed 8000..8019）
#   -> TEST 关门：反向 4×20（seed 7000..7019）+ 正向护栏 1×20（seed 2000..2019）
# 收尾（零 GPU）：6 条曲线总览（batch8×3 + bs32×3，同一组 epoch 格、全体 15 对配对符号检验 + 早筛回溯）
#   -> `runs/_diag/seedcurve_s7c.md`（严格）与 `…_relaxed.md`（放宽）；判定 -> `runs/S7C_VERDICT.md`（C1~C3）。
#
# ⚠️ 评测目录名与 `code/mg_verdict_s7c.py` 里写死的 `test_dirs()/fwd_dirs()` 一致，**不许改**：
#    `s7b_bs32_seed<SD>_rev_test_rand20_k10{,_rep2,_rep3,_rep4}` / `s7b_bs32_seed<SD>_fwd_test_rand20_k10`
#    （run 目录沿用 7B 的命名 `pi05_mix60f120r_s7b_bs32_seed<SD>`，因为配方就是 7B 那一个。）
# ⚠️ 步数不照抄：`code/run_pi05_s7b.sh` 会用 `mg_probe_batch.equal_epoch_plan` 现算并逐条断言（坑 33）。
#
# 房规：setsid 发车（坑 37）；done 标记 printf 写 + `[ -s ]` 自检（坑 43）；路径全绝对（坑 41）；
#   每个读数「有产物就跳过」⇒ 可断点续跑；不碰任何冻结文件（mg_eval / mg_env* / mg_sweep_rev /
#   mg_verdict_s3r / mg_epoch_curve / mg_expert / mg_verdict_s7）。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
NOISE='robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation'

DATASET="mix60f120r"
BS="${BS:-32}"
STEPS="${STEPS:-5500}"
SAVE_FREQ="${SAVE_FREQ:-500}"
LOG_FREQ="${LOG_FREQ:-25}"
LR="${LR:-2e-4}"
EP="${EP:-20}"
REPS="${REPS:-4}"
K="${K:-10}"
SEEDS=(1000 3000)                       # 2000 已由档 7B 跑完（预注册 §3 格 7C）
MIN_FREE_TRAIN="${MIN_FREE_TRAIN:-45000}"   # 7A/7B 实测 bs32+ckpt 峰值 41671 MiB
MIN_FREE_EVAL="${MIN_FREE_EVAL:-9000}"
WAIT_H="${WAIT_H:-14}"                  # 7B 从 14:19 起跑，训练+扫描+关门 ≈ 8.9 h

NPZ_R="$MG/data/${DATASET}_rev_raw.npz"
NPZ_F="$MG/data/${DATASET}_raw.npz"
V7="$MG/runs/S7_VERDICT.md"
GATEMD="$MG/runs/S7C_GATE.md"
MARK="$MG/runs/s7c.done"
FAILED="$MG/runs/s7c.FAILED"
SKIPPED="$MG/runs/s7c.SKIPPED"

die  () { echo "[s7c] FATAL $*" | tee -a "$FAILED"; exit 4; }
skip () { printf '%s 档7C 不发车（预注册分支）原因=%s 依据=runs/S7_PREREG.md §3 格7C「M1∧M2∧M3 全过才发」\n' \
            "$(date '+%F %T')" "$1" > "$SKIPPED"
          [ -s "$SKIPPED" ] || echo "[s7c] SKIPPED 写空了（坑 43 复发）"
          echo "[s7c] SKIP：$1"; exit 0; }

# ── 0. 等档 7B 收工（三种终态都认，绝不用进程表判完成 —— 坑 22(e)）─────────────
echo "[s7c] === 等档 7B 收工（上限 ${WAIT_H} h）=== $(date '+%F %T')"
got=""
for _ in $(seq 1 $((WAIT_H * 60))); do
  [ -s "$MG/runs/s7b.done" ]   && { got="done";   break; }
  [ -s "$MG/runs/s7b.FAILED" ] && { got="FAILED"; break; }
  [ -s "$MG/runs/s7b.HELD" ]   && { got="HELD";   break; }
  sleep 60
done
case "$got" in
  done)   echo "[s7c] 7B 收工：$(head -1 "$MG/runs/s7b.done")" ;;
  FAILED) skip "档7B 写了 runs/s7b.FAILED：$(head -1 "$MG/runs/s7b.FAILED")" ;;
  HELD)   skip "档7B 写了 runs/s7b.HELD（预注册暂缓分支）：$(head -1 "$MG/runs/s7b.HELD")" ;;
  "")     die "等 ${WAIT_H} h 仍没有 runs/s7b.done（FAILED/HELD 也没有）⇒ 7B 可能静默死亡，看 logs/ALERTS.log" ;;
esac

# ── 1. 预注册闸（全部看盘上产物）────────────────────────────────────────────
[ -s "$V7" ] || die "有 s7b.done 却没有 runs/S7_VERDICT.md ⇒ 先手工跑 code/mg_verdict_s7.py"
ROW=""
grep -q 'M1✅ M2✅ M3✅ M4✅' "$V7" && ROW='M1✅ M2✅ M3✅ M4✅'
[ -n "$ROW" ] || { grep -q 'M1✅ M2✅ M3✅ M4❌' "$V7" && ROW='M1✅ M2✅ M3✅ M4❌'; }
BAD=""
grep -q '不采信'   "$V7" && BAD="$BAD 不采信"
grep -q '无法判定' "$V7" && BAD="$BAD 无法判定"
FR=$("$MG_PY" -c "import json;print(json.load(open('$MG/data/$DATASET/meta/info.json'))['total_frames'])")
[ "$FR" = "46426" ] || die "total_frames=$FR ≠ 46426 ⇒ 等 epoch 步数的分母变了（坑 33）"
[ -f "$NPZ_R" ] && [ -f "$NPZ_F" ] || die "示范 npz 不在：$NPZ_R / $NPZ_F"
N7B=$(ls -1d "$MG/runs/pi05_mix60f120r_s7b_bs${BS}_seed2000"/sweep_rev/step_*_rev 2>/dev/null | wc -l)
[ "$N7B" -ge 11 ] || die "7B（seed2000）只有 $N7B/11 格 val ⇒ 6 条曲线总览与 C3 都做不出来"
"$MG_PY" "$MG/code/mg_seedcurve.py"   --selftest >/dev/null || die "mg_seedcurve 自测不过"
"$MG_PY" "$MG/code/mg_verdict_s7c.py" --selftest >/dev/null || die "mg_verdict_s7c 自测不过"
echo "[s7c] 闸：命中行='${ROW:-无}'  禁用词='${BAD:-无}'  7B val 格=$N7B/11  $(date '+%T')"

# 闸读数留档（M5 只记录、不当闸；理由写在文件里，免得后人以为漏了）
DEC="发车"; WHY="M1∧M2∧M3 全过（预注册条件满足）"
if [ -z "$ROW" ]; then DEC="不发车"; WHY="runs/S7_VERDICT.md 的命中行不是 M1✅M2✅M3✅M4{✅,❌}"; fi
if [ -n "$BAD" ]; then DEC="不发车"; WHY="runs/S7_VERDICT.md 里出现$BAD"; fi
{
  echo "# 档 7C 发车闸读数（自动生成 $(date '+%F %T')，链 code/chain_s7c.sh）"
  echo
  echo "* 上游 7B：$(head -1 "$MG/runs/s7b.done")"
  echo "* 判定文件：\`runs/S7_VERDICT.md\`；命中行：**${ROW:-（没匹配到任何一行）}**"
  echo "* 预注册发车条件（\`runs/S7_PREREG.md\` §3 格 7C）：**M1∧M2∧M3 全过**；M4 过不过都发"
  echo "* M5（正向护栏）**不在**预注册的发车条件里 ⇒ 只记录不当闸（坑 40：判据不许看完数再改）"
  echo
  echo "| 判据 | 7B 读数（抄自 S7_VERDICT.md 第一节） |"
  echo "|:--|:--|"
  grep -E '^\| \*\*M[1-5]\*\*' "$V7"
  echo
  echo "* **决定：$DEC** —— $WHY"
  echo "* 若发车：seed ${SEEDS[*]} 各一发（每发 ≈ 6h51m 训练 + 1.2h 扫描 + 0.6h 关门），串行 ≈ 17.4 h"
} > "$GATEMD"
[ -s "$GATEMD" ] || die "闸读数写空了：$GATEMD"
[ "$DEC" = "发车" ] || skip "$WHY"

# ── 2. 两个 seed 串行：训练 -> last 核对 -> 11 格扫描 -> TEST 关门 ──────────────
wait_gpu () {  # $1 = 需要的 free MiB
  local need="$1" f
  for _ in $(seq 1 240); do
    f=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
    [ "${f:-0}" -ge "$need" ] && return 0
    echo "[s7c] 显存 free=${f}MiB < ${need}MiB，等 30 s ... $(date '+%T')"; sleep 30
  done
  return 0
}

one_eval () {  # $1=mode $2=目录名 $3=seed $4=说明 $5=ckpt
  local mode="$1" out="$2" sd="$3" what="$4" ck="$5" npz="$NPZ_F"
  [ "$mode" = "reverse" ] && npz="$NPZ_R"
  [ -f "$MG/runs/$out/eval_summary.json" ] && { echo "[s7c] 跳过（已有产物）$out"; return 0; }
  wait_gpu "$MIN_FREE_EVAL"
  echo "[s7c] === $what（$mode K=$K eps=$EP seed=$sd）-> runs/$out === $(date '+%F %T')"
  "$MG_PY" code/mg_eval.py --ckpt "$ck" --episodes "$EP" --seed-mode random --seed "$sd" \
      --n-action-steps "$K" --task-mode "$mode" --demo-npz "$npz" \
      --out "$MG/runs/$out" 2>&1 | grep -vE "$NOISE" | grep -E "^  ep|成功率|放宽口径|warn|Error|Traceback"
  [ -f "$MG/runs/$out/eval_summary.json" ] || die "评测没落盘：$out"
}

run_one_seed () {  # $1 = 训练 seed
  local SD="$1"
  local JOB="pi05_${DATASET}_s7b_bs${BS}_seed${SD}"
  local RUN="$MG/runs/$JOB"
  local CK="$RUN/checkpoints/last/pretrained_model"
  local rc want rl missing s ND i suf

  if [ -f "$CK/model.safetensors" ]; then
    echo "[s7c] 跳过训练（已有产物）：$CK"
  else
    wait_gpu "$MIN_FREE_TRAIN"
    echo "[s7c] === 训练 seed$SD：bs$BS / lr$LR / $STEPS 步（等 epoch 3.79）=== $(date '+%F %T')"
    DATASET="$DATASET" BS="$BS" SEED="$SD" LR="$LR" JOB="$JOB" \
      STEPS="$STEPS" SAVE_FREQ="$SAVE_FREQ" LOG_FREQ="$LOG_FREQ" \
      bash "$MG/code/run_pi05_s7b.sh" > "$MG/logs/train_${JOB}.log" 2>&1
    rc=$?
    echo "[s7c] 训练 rc=$rc $(date '+%F %T') 日志 -> logs/train_${JOB}.log（进度看 ${RUN}_meta/train.log）"
    [ "$rc" -eq 0 ] || die "seed$SD 训练非 0 退出（rc=$rc）"
  fi
  # 坑 38：`last` 是每次 save 都重指的软链，必须核对它指向终点格，否则读数会读错权重
  want=$(printf "%06d" "$STEPS")
  rl=$(readlink "$RUN/checkpoints/last" 2>/dev/null || echo "")
  echo "[s7c] seed$SD last -> ${rl:-无}（期望 $want）"
  [ "$rl" = "$want" ] || die "seed$SD 的 last 指向 '$rl' 而不是 $want ⇒ 读数会读错权重（坑 38）"
  [ -f "$CK/model.safetensors" ] || die "seed$SD 终点格权重不在：$CK/model.safetensors"
  missing=""
  for s in $(seq "$SAVE_FREQ" "$SAVE_FREQ" "$STEPS"); do
    [ -f "$RUN/checkpoints/$(printf '%06d' "$s")/pretrained_model/model.safetensors" ] || missing="$missing $s"
  done
  [ -z "$missing" ] || die "seed$SD 缺检查点格：$missing ⇒ 扫出来会是断头曲线"

  ND=$(ls -1d "$RUN"/sweep_rev/step_*_rev 2>/dev/null | wc -l)
  if [ "$ND" -ge 11 ]; then
    echo "[s7c] 跳过 seed$SD 的 val 扫描（已有 $ND/11 格）"
  else
    echo "[s7c] === seed$SD 11 格反向 val 扫描（每格 $EP 局、K=$K、val seed 8000..）=== $(date '+%F %T')"
    wait_gpu "$MIN_FREE_EVAL"
    RUN="$RUN" STEPS_TOTAL="$STEPS" SAVE_FREQ="$SAVE_FREQ" SUB=sweep_rev EPISODES="$EP" K="$K" \
      REV_SEED=8000 DEMO_REV="$NPZ_R" MIN_FREE_MIB="$MIN_FREE_EVAL" \
      bash "$MG/code/mg_sweep_rev.sh" "$RUN" > "$MG/logs/sweep_${JOB}.log" 2>&1
    rc=$?; echo "[s7c] 扫描 rc=$rc $(date '+%F %T') 日志 -> logs/sweep_${JOB}.log"
    [ "$rc" -eq 0 ] || die "seed$SD 的 mg_sweep_rev.sh 退出码 $rc"
    ND=$(ls -1d "$RUN"/sweep_rev/step_*_rev 2>/dev/null | wc -l)
    [ "$ND" -ge 11 ] || die "seed$SD 只扫出 $ND 格（应 11）⇒ C3 的前瞻验证做不出来"
  fi

  for i in $(seq 1 "$REPS"); do
    suf=""; [ "$i" -gt 1 ] && suf="_rep$i"
    one_eval reverse "s7b_bs${BS}_seed${SD}_rev_test_rand20_k10$suf" 7000 "seed$SD 反向 TEST rep$i" "$CK"
  done
  one_eval forward "s7b_bs${BS}_seed${SD}_fwd_test_rand20_k10" 2000 "seed$SD 正向护栏（未见）" "$CK"
}

for SD in "${SEEDS[@]}"; do
  echo "[s7c] ########## seed $SD ########## $(date '+%F %T')"
  run_one_seed "$SD"
done

# ── 3. 收尾（零 GPU）：6 条曲线总览 + 判定汇编 ────────────────────────────────
# `--test` 的 k/n 一律从盘上的 eval_summary.json 现算（两个口径各一套），不写死历史数字：
#   写死就会与判定文件各说各话（坑 54）。
curve_args () {  # $1 = n_success | n_success_relaxed
  "$MG_PY" - "$1" <<'PY'
import json, sys
from pathlib import Path
MG = Path("/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05")
key = sys.argv[1]
REPS = ["", "_rep2", "_rep3", "_rep4"]
ARMS = [(f"b8_seed{sd}", f"pi05_mix60f120r_{run}", [f"{pre}_rev_test_rand20_k10{s}" for s in REPS])
        for sd, run, pre in ((1000, "s2e", "s2e"), (2000, "s3r_seed2000", "s3r_seed2000"),
                             (3000, "s3r_seed3000", "s3r_seed3000"))]
ARMS += [(f"b32_seed{sd}", f"pi05_mix60f120r_s7b_bs32_seed{sd}",
          [f"s7b_bs32_seed{sd}_rev_test_rand20_k10{s}" for s in REPS]) for sd in (2000, 1000, 3000)]
for lab, run, dirs in ARMS:
    rp = MG / "runs" / run
    lg = rp / "train.log"
    if not rp.is_dir() or not lg.is_file():
        continue
    print("--run"); print(f"{lab}:{rp}")
    print("--log"); print(f"{lab}:{lg}")
    k = n = 0
    for d in dirs:
        f = MG / "runs" / d / "eval_summary.json"
        if not f.is_file():
            continue
        j = json.load(open(f))
        k += int(j.get(key, 0)); n += int(j.get("episodes", 0))
    if n:
        print("--test"); print(f"{lab}:{k}:{n}")
PY
}
mapfile -t SC_STRICT < <(curve_args n_success)
mapfile -t SC_REL   < <(curve_args n_success_relaxed)
# 断言必须**点名**六条臂：只数总行数的话，少一条 b32 臂也能过（那就是静默降级成 n=2 的方差读数）。
check_arms () {  # $1=数组名 $2=口径说明
  local -n A="$1"; local nr nb
  nr=$(printf '%s\n' "${A[@]}" | grep -c '^--run$')
  nb=$(printf '%s\n' "${A[@]}" | grep -cE '^b32_seed(1000|2000|3000):[0-9]+:[0-9]+$')
  [ "$nr" -eq 6 ] || die "曲线 --run 只有 $nr 条（应 6：batch8×3 + bs32×3）⇒ $2 口径的总览会缺臂"
  [ "$nb" -eq 3 ] || die "bs32 的 --test 只凑出 $nb/3 条 ⇒ $2 口径缺 TEST 读数，C1 的极差会算错"
}
check_arms SC_STRICT 严格
check_arms SC_REL   放宽

echo "[s7c] === 6 条曲线总览 · 严格口径（7D）=== $(date '+%F %T')"
"$MG_PY" "$MG/code/mg_seedcurve.py" "${SC_STRICT[@]}" \
  --metric strict --min-epoch 1.03 --gate 0.50 \
  --thresholds 0.05,0.10,0.15,0.20,0.25,0.30,0.35,0.40 \
  --out "$MG/runs/_diag/seedcurve_s7c.md" > "$MG/logs/seedcurve_s7c.log" 2>&1 \
  || echo "[s7c] 注意：严格口径总览失败（不阻塞判定）：logs/seedcurve_s7c.log"
echo "[s7c] === 6 条曲线总览 · 放宽口径（主口径）=== $(date '+%F %T')"
"$MG_PY" "$MG/code/mg_seedcurve.py" "${SC_REL[@]}" \
  --metric relaxed --min-epoch 1.03 --gate 0.50 \
  --thresholds 0.05,0.10,0.15,0.20,0.25,0.30,0.35,0.40 \
  --out "$MG/runs/_diag/seedcurve_s7c_relaxed.md" > "$MG/logs/seedcurve_s7c_relaxed.log" 2>&1 \
  || die "放宽口径总览失败（C1/C3 的原料）：logs/seedcurve_s7c_relaxed.log"
grep -E "^\[seedcurve\]" "$MG/logs/seedcurve_s7c_relaxed.log" | head -20

echo "[s7c] === 判定汇编（C1~C3）=== $(date '+%F %T')"
"$MG_PY" "$MG/code/mg_verdict_s7c.py" > "$MG/runs/S7C_VERDICT.md" 2> "$MG/logs/verdict_s7c.log"
rc=$?; echo "[s7c] 判定 rc=$rc -> runs/S7C_VERDICT.md"
{ [ "$rc" -eq 0 ] && [ -s "$MG/runs/S7C_VERDICT.md" ]; } || die "7C 判定没生成（rc=$rc，看 logs/verdict_s7c.log）"
tail -30 "$MG/runs/S7C_VERDICT.md"

printf '%s 档7C 完成 seeds=%s(+7B的2000) 配方=bs%s/%s步/lr%s/save%s/log%s 闸=runs/S7C_GATE.md 判定=runs/S7C_VERDICT.md 曲线=runs/_diag/seedcurve_s7c.md,runs/_diag/seedcurve_s7c_relaxed.md\n' \
  "$(date '+%F %T')" "${SEEDS[*]}" "$BS" "$STEPS" "$LR" "$SAVE_FREQ" "$LOG_FREQ" > "$MARK"
[ -s "$MARK" ] || die "done 标记写空了（坑 43 复发）"
echo "[s7c] 收工 $(date '+%F %T')"
