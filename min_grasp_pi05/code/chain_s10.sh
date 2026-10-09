#!/usr/bin/env bash
# 档 10 · 关门配方在**标准 chunk 执行（K = chunk_size = 50）**下，还过不过**同一条使命门**
#   预注册：runs/S10_PREREG.md（2026-10-07 17:37 落盘，**早于本档任何读数**；看完数不许改门，坑 40）
#
# 唯一变量 = **K**（10 → 50）。检查点/数据集/task 串/TEST seed 窗/局数/判据与档 8 的 D4 **逐字相同**：
#   三臂 = pi05_mix60f120r_c1_{s8c_seed2000, s8d_seed4000, s8d_seed5000} 的 checkpoints/022000（**数字格**，不用 last，坑 38/42/63）
#   反向 TEST seed 7000..7019 × 4 rep = 80 局/臂；正向护栏 seed 2000..2019 × 1 = 20 局/臂 ⇒ 15 次评测
#   K=10 的参照读数**从盘上并入、不重跑**（坑 40①），由判定工具与 runs/S8_VERDICT.md:16 的 65/65/64 逐臂对账
#
# ⚠️ **为什么必须独占空卡、绝不与 9C 训练并发**：E4 是**墙钟门**（ms/控制步 ≤ 50 ms，坑 36）。
#   与训练抢卡会把 ms/step 抬高几倍 ⇒ 一个本来能过的部署门被判不过（或反之），而这不是模型的性质、是排班的性质。
#   所以本档排在 9C 之后（预注册 §7.2），且每格评测前都要 free ≥ 44000 MiB（bs32 峰值 41671，坑 64）。
#
# 房规：setsid 发车并核 SID==PID（坑 37）；标记 printf 写 + `[ -s ]` 自检（坑 43）；路径全绝对（坑 41）；
#   认产物不认进程表（坑 22(e)）；有产物就跳过 ⇒ 可断点续跑；退出码先 rc=$? 再 $(...)（坑 80）；
#   pgrep 模式用字符类防自匹配（坑 75）；不编辑在飞的 .sh（chain_s7h/s9c/watchdog 一律不碰）；
#   本链**不进**看门狗清单（坑 78）⇒ 自带终态标记 + 独立哨兵 chain_s10_sentinel.sh。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
NOISE='robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation'

K="${K:-50}"                       # = chunk_size，模型原生 chunk（预注册 §2；改它等于换问题）
CK_STEP="${CK_STEP:-022000}"       # 关门读数（= last 指向的编号格，坑 38）
EP="${EP:-20}"; REPS="${REPS:-4}"
REV_SEED0="${REV_SEED0:-7000}"; FWD_SEED0="${FWD_SEED0:-2000}"
ARMS="${ARMS:-s8c_seed2000 s8d_seed4000 s8d_seed5000}"
DST="mix60f120r_c1"; SRC_DS="mix60f120r"
NPZ_R="$MG/data/${SRC_DS}_rev_raw.npz"
NPZ_F="$MG/data/${SRC_DS}_raw.npz"
PREREG="$MG/runs/S10_PREREG.md"
S8V="$MG/runs/S8_VERDICT.md"
VERD="${VERD:-$MG/runs/S10_VERDICT.md}"
MARK="${MARK:-$MG/runs/s10.done}"; FAILED="${FAILED:-$MG/runs/s10.FAILED}"; SKIPPED="${SKIPPED:-$MG/runs/s10.SKIPPED}"
MIN_FREE_EVAL="${MIN_FREE_EVAL:-44000}"   # 独占空卡才许评测（E4 是墙钟门，见文件头）
WAIT_H="${WAIT_H:-48}"
UP_PROC="${UP_PROC:-code/chain_s9[c]\.sh}"
DRY_RUN="${DRY_RUN:-0}"                   # 1 = 只验闸 + 打印命令，不跑评测、不写 runs/（预注册 §7.6）
if [ -n "${UP_MARK:-}" ]; then UP_MARKS=("$UP_MARK")
else UP_MARKS=("$MG/runs/s9c.done" "$MG/runs/s9c.FAILED" "$MG/runs/s9c.SKIPPED"); fi

die  () { echo "[s10] FATAL $*" | tee -a "$FAILED"; exit 4; }
skip () { printf '%s 档10 不发车（合法终态）原因=%s\n' "$(date '+%F %T')" "$1" > "$SKIPPED"
          [ -s "$SKIPPED" ] || echo "[s10] SKIPPED 写空了（坑 43 复发）"
          echo "[s10] SKIP：$1"; exit 0; }

wait_gpu () {
  local need="$1" f
  for _ in $(seq 1 240); do
    f=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
    [ "${f:-0}" -ge "$need" ] && return 0
    echo "[s10] 显存 free=${f}MiB < ${need}MiB，等 30 s ... $(date '+%T')"; sleep 30
  done
  echo "[s10] 等了 2 h 显存仍不足 ${need}MiB（不抢卡，交给下面的硬闸把关）"; return 0
}

one_eval () {  # $1=mode $2=目录名 $3=seed $4=ckpt $5=说明
  local mode="$1" out="$2" sd="$3" ck="$4" what="$5" npz="$NPZ_F" rc
  local log="$MG/logs/eval_s10_${out}.log"
  [ "$mode" = "reverse" ] && npz="$NPZ_R"
  if [ -f "$MG/runs/$out/eval_summary.json" ]; then echo "[s10] 跳过（已有产物）$out"; return 0; fi
  [ -f "$ck/model.safetensors" ] || die "权重不在：$ck/model.safetensors（$what）"
  wait_gpu "$MIN_FREE_EVAL"
  echo "[s10] === $what（$mode K=$K eps=$EP seed=$sd）-> runs/$out === $(date '+%F %T')"
  echo "[s10]     ckpt=$ck"                       # 出处打进日志（坑 30）
  echo "[s10]     全量日志 -> $log"
  if [ "$DRY_RUN" = "1" ]; then
    echo "[s10]     DRY_RUN=1 ⇒ 只打印命令不执行：$MG_PY code/mg_eval.py --ckpt $ck --episodes $EP --seed-mode random --seed $sd --n-action-steps $K --task-mode $mode --demo-npz $npz --out $MG/runs/$out"
    return 0
  fi
  "$MG_PY" code/mg_eval.py --ckpt "$ck" --episodes "$EP" --seed-mode random --seed "$sd" \
      --n-action-steps "$K" --task-mode "$mode" --demo-npz "$npz" \
      --out "$MG/runs/$out" > "$log" 2>&1
  rc=$?                                           # 坑 80：先存 rc，再做任何 $(...)
  grep -vE "$NOISE" "$log" | grep -E "^  ep|成功率|放宽口径|chunk_size|warn|Error|Traceback" | tail -25
  [ "$rc" = "0" ] || die "评测退出码 $rc：$out（日志 $log）"
  [ -f "$MG/runs/$out/eval_summary.json" ] || die "评测没落盘：$out（日志 $log）"
}

# ── 0. 已收工/已合法跳过就别重跑（认产物 —— 坑 22(e)）────────────────────────
if [ -s "$MARK" ]; then echo "[s10] 已收工（$MARK 在）：$(head -1 "$MARK")"; exit 0; fi
if [ -s "$SKIPPED" ]; then echo "[s10] 已跳过（$SKIPPED 在）：$(head -1 "$SKIPPED")"; exit 0; fi

# ── 1. 等上游 9C 让卡（**不抢卡**；认产物 + 进程消失，坑 22(e)）────────────────
# 9C 是 FAILED / SKIPPED 也照常跑：本档不依赖 9C 的**结论**，只依赖它的**卡**（预注册 §7.2）。
echo "[s10] === 等档 9C 收工并让卡（上限 ${WAIT_H} h）=== $(date '+%F %T')"
got=""
for _ in $(seq 1 $((WAIT_H * 60))); do
  for m in "${UP_MARKS[@]}"; do [ -s "$m" ] && { got="$m"; break 2; }; done
  sleep 60
done
[ -n "$got" ] || skip "等 ${WAIT_H} h 仍没等到上游终态标记 ⇒ 不抢卡、不发车"
echo "[s10] 上游终态标记：$got -> $(head -c 200 "$got")"
# 标记在 ≠ 卡已让出（收尾评测可能还在跑）⇒ 再等进程消失（上限 2 h）；进程表只用来判「卡空没空」，不判完成
for _ in $(seq 1 240); do
  pgrep -f "$UP_PROC" > /dev/null 2>&1 || break
  echo "[s10] 上游链还在（收尾中），等 30 s ... $(date '+%T')"; sleep 30
done
pgrep -f "$UP_PROC" > /dev/null 2>&1 \
  && echo "[s10] ⚠️ 等了 2 h 上游链仍在 ⇒ 靠显存硬闸把关，不硬抢"

# ── 2. 发车闸（预注册 §7；全部只读盘上产物）──────────────────────────────────
echo "[s10] === 发车闸 === $(date '+%F %T')"
[ -f "$PREREG" ] || die "闸0：预注册不在（$PREREG）⇒ 没有事前判据，不许跑（坑 40）"
# 闸0b：任何 s10_* 产物都**必须晚于**预注册（否则就是「看完数才写门」或来路不明的产物）
early=$(find "$MG/runs" -maxdepth 1 -name 's10_*' ! -newer "$PREREG" 2>/dev/null | head -5)
[ -z "$early" ] || die "闸0b：有 s10_* 产物早于预注册落盘时间 ⇒ 时序不对（坑 40）：$early"
echo "[s10] 闸0：预注册在（$(date -r "$PREREG" '+%F %T') 落盘），且没有早于它的 s10_* 产物"
grep -q '^S8_D4=PASS' "$S8V" \
  || die "闸1：$S8V 里没有 S8_D4=PASS ⇒ K=10 参照（65/65/64）的出处不成立，Δ 就没有分母"
nref=0
for arm in $ARMS; do
  run="pi05_${DST}_${arm}"
  ck="$MG/runs/$run/checkpoints/$CK_STEP/pretrained_model"
  [ -f "$ck/model.safetensors" ] || die "闸2：权重不在 $ck/model.safetensors（$arm）"
  rl=$(readlink "$MG/runs/$run/checkpoints/last" 2>/dev/null || echo "")
  echo "[s10] 闸2：$arm 数字格 $CK_STEP 在（last -> ${rl:-无}，本档一律走数字格，坑 63）"
  for i in $(seq 1 "$REPS"); do
    suf=""; [ "$i" -gt 1 ] && suf="_rep$i"
    [ -f "$MG/runs/${arm}_rev_test_rand20_k10${suf}/eval_summary.json" ] \
      || die "闸3：K=10 参照缺产物 ${arm}_rev_test_rand20_k10${suf} ⇒ Δ 算不出来（不许拿半个参照比）"
    nref=$((nref + 1))
  done
  [ -f "$MG/runs/${arm}_fwd_test_rand20_k10/eval_summary.json" ] \
    || die "闸3：K=10 正向参照缺产物 ${arm}_fwd_test_rand20_k10"
  nref=$((nref + 1))
done
echo "[s10] 闸3：K=10 参照 $nref/$(( (REPS + 1) * 3 )) 读齐"
[ -f "$NPZ_R" ] && [ -f "$NPZ_F" ] || die "闸4：示范 npz 不在：$NPZ_R / $NPZ_F"
echo "[s10] 闸4：示范 npz 在（反向 $(basename "$NPZ_R")、正向 $(basename "$NPZ_F")）"
"$MG_PY" "$MG/code/mg_verdict_s10.py" --selftest > "$MG/logs/verdict_s10_selftest.log" 2>&1 \
  || die "闸5：mg_verdict_s10 自测不过（看 logs/verdict_s10_selftest.log）⇒ 门的实现本身不可信（预注册 §7.7）"
echo "[s10] 闸5：判定工具自测全绿 -> $(tail -1 "$MG/logs/verdict_s10_selftest.log")"
wait_gpu "$MIN_FREE_EVAL"
free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
[ "${free:-0}" -ge "$MIN_FREE_EVAL" ] || die "闸6：GPU free=${free}MiB < ${MIN_FREE_EVAL}MiB ⇒ 有别的东西在占卡；E4 是墙钟门，不并发、不抢卡"
echo "[s10] 闸 0-6 全过（K=$K、ckpt=$CK_STEP、三臂=$ARMS、GPU free=${free}MiB、DRY_RUN=$DRY_RUN）$(date '+%T')"

# ── 3. 三臂 × (4 反向 rep + 1 正向) = 15 次评测 ───────────────────────────────
for arm in $ARMS; do
  run="pi05_${DST}_${arm}"
  ck="$MG/runs/$run/checkpoints/$CK_STEP/pretrained_model"
  echo "[s10] ########## $arm · K=$K · runs/$run/checkpoints/$CK_STEP ########## $(date '+%F %T')"
  for i in $(seq 1 "$REPS"); do
    suf=""; [ "$i" -gt 1 ] && suf="_rep$i"
    one_eval reverse "s10_${arm}_rev_test_rand20_k${K}${suf}" "$REV_SEED0" "$ck" "$arm 反向 TEST rep$i"
  done
  one_eval forward "s10_${arm}_fwd_test_rand20_k${K}" "$FWD_SEED0" "$ck" "$arm 正向护栏（未见）"
done

# ── 4. 判定汇编（阈值全在 mg_verdict_s10.py / 预注册 §3 里，本链不做任何判读）──
echo "[s10] === 判定汇编 === $(date '+%F %T')"
if [ "$DRY_RUN" = "1" ]; then
  "$MG_PY" code/mg_verdict_s10.py > /tmp/s10_dryrun_verdict.md 2>&1; vrc=$?
  echo "[s10] DRY_RUN：判定写到 /tmp/s10_dryrun_verdict.md，退出码 $vrc（预期 3 = 还没有 K=50 产物 ⇒ 不采信）"
  printf '%s 档10 DRY_RUN 完成（闸全过、没跑评测、runs/ 零污染）\n' "$(date '+%F %T')" > "$MARK"
  [ -s "$MARK" ] || die "DRY_RUN 标记写空了（$MARK）"
  echo "[s10] DRY_RUN done $(date '+%F %T')"; exit 0
fi
"$MG_PY" code/mg_verdict_s10.py > "$VERD" 2>&1; vrc=$?    # 坑 80：先存 rc
tail -45 "$VERD"
[ "$vrc" = "0" ] || die "判定退出码 $vrc（2=读数不齐 ⇒ E1 UNKNOWN 不当 0 计；3=出身/对账不过 ⇒ 不采信）⇒ 不写 done 标记，看 $VERD"
e1=$(grep -m1 '^S10_E1=' "$VERD" || echo 'S10_E1=?')
e2=$(grep -m1 '^S10_E2=' "$VERD" || echo 'S10_E2=?')
e4=$(grep -m1 '^S10_E4=' "$VERD" || echo 'S10_E4=?')
# 坑 43：终态标记必须 printf 写、写完 [ -s ] 自检；date 的参数不能混进 printf 的位置参数
printf '%s 档10 K=%s 三臂 15 读完成 %s %s %s 判定=%s\n' \
       "$(date '+%F %T')" "$K" "$e1" "$e2" "$e4" "$VERD" > "$MARK"
[ -s "$MARK" ] || die "标记写空了（$MARK）⇒ 下游按 -f 判存在会误以为收工（坑 43）"
echo "[s10] done $(date '+%F %T')  标记 -> $MARK"
