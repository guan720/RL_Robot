#!/usr/bin/env bash
# 档 11 · 语言泛化：把**指令串**换成同义改写句，看策略学的是任务还是那两句原话
#   预注册：runs/S11_PREREG.md（2026-10-07 20:04 落盘，**早于本档任何读数**；看完数不许改门，坑 40）
#
# 唯一变量 = **指令串**（`code/mg_eval_lang.py --instruction`）。检查点/数据集/场景/seed 窗/局数/K/判据
#   与档 8 的关门读数**逐字相同**：三臂 = pi05_mix60f120r_c1_{s8c_seed2000, s8d_seed4000, s8d_seed5000}
#   的 checkpoints/022000（**数字格**，不用 last，坑 38/42/63）、K=10、每读 20 局、反向 seed 7000..7019 /
#   正向 2000..2019（与关门读数**同一批** ⇒ L2 才能配对）。原话参照**从盘上并入、不重跑**（坑 40①）。
#
# 20 读清单的唯一真源 = `$MG_PY code/mg_eval_lang.py --print-plan`（TSV）：链按它发车、判定工具按它读盘。
#   两边各写一份就一定走样（走样的形状 = 链跑 A 目录、判定读 B 目录 ⇒ 永远 UNKNOWN 却看着像「数据没出」）。
#
# ⚠️ 本档最大的静默失败 = **patch 没生效**（跑的还是原话）⇒ L1 假过、L3 假阴。所以每读完立刻要求
#   `lang_sidecar.json` 落盘，缺了就当场停（跑完 20 读才发现整档不采信，白烧 1.4 h GPU）。
# ⚠️ 排在档 10 之后、独占空卡（free ≥ 44000 MiB，坑 64）：本档没有墙钟门，但与训练抢卡会 OOM/拖慢。
#
# 房规：setsid 发车并核 SID==PID（坑 37）；标记 printf 写 + `[ -s ]` 自检（坑 43）；路径全绝对（坑 41）；
#   认产物不认进程表（坑 22(e)）；有产物就跳过 ⇒ 可断点续跑；退出码先 rc=$? 再 $(...)（坑 80）；
#   pgrep 模式用字符类防自匹配（坑 75）；不编辑在飞的 .sh（chain_s9c/s10/两个哨兵一律不碰）；
#   本链**不进**看门狗清单（坑 78）⇒ 自带终态标记 + 独立哨兵 chain_s11_sentinel.sh。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
NOISE='robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation'

PREREG="$MG/runs/S11_PREREG.md"
S8V="$MG/runs/S8_VERDICT.md"
PLAN_TSV="${PLAN_TSV:-$MG/logs/s11_plan.tsv}"
VERD="${VERD:-$MG/runs/S11_VERDICT.md}"
MARK="${MARK:-$MG/runs/s11.done}"; FAILED="${FAILED:-$MG/runs/s11.FAILED}"; SKIPPED="${SKIPPED:-$MG/runs/s11.SKIPPED}"
MIN_FREE_EVAL="${MIN_FREE_EVAL:-44000}"   # 独占空卡才许评测（bs32 训练峰值 41671，坑 64）
WAIT_H="${WAIT_H:-48}"
UP_PROC="${UP_PROC:-code/chain_s1[0]\.sh}"   # 字符类打断自匹配（坑 75）
NREADS_EXPECT="${NREADS_EXPECT:-20}"         # 6 句×3 臂 + 2 句负对照×1 臂
DRY_RUN="${DRY_RUN:-0}"                      # 1 = 只验闸 + 打印命令，不跑评测、不写 runs/
if [ -n "${UP_MARK:-}" ]; then UP_MARKS=("$UP_MARK")
else UP_MARKS=("$MG/runs/s10.done" "$MG/runs/s10.FAILED" "$MG/runs/s10.SKIPPED"); fi

die  () { echo "[s11] FATAL $*" | tee -a "$FAILED"; exit 4; }
skip () { printf '%s 档11 不发车（合法终态）原因=%s\n' "$(date '+%F %T')" "$1" > "$SKIPPED"
          [ -s "$SKIPPED" ] || echo "[s11] SKIPPED 写空了（坑 43 复发）"
          echo "[s11] SKIP：$1"; exit 0; }

wait_gpu () {
  local need="$1" f
  for _ in $(seq 1 240); do
    f=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
    [ "${f:-0}" -ge "$need" ] && return 0
    echo "[s11] 显存 free=${f}MiB < ${need}MiB，等 30 s ... $(date '+%T')"; sleep 30
  done
  echo "[s11] 等了 2 h 显存仍不足 ${need}MiB（不抢卡，交给下面的硬闸把关）"; return 0
}

one_read () {  # 一行 TSV：code scene arm out task_mode seed0 npz episodes k ckpt instruction
  local code="$1" scene="$2" arm="$3" out="$4" mode="$5" sd="$6" npz="$7" ne="$8" k="$9" ck="${10}" ins="${11}" rc
  local log="$MG/logs/eval_s11_${out}.log"
  if [ -f "$MG/runs/$out/eval_summary.json" ]; then echo "[s11] 跳过（已有产物）$out"; return 0; fi
  [ -f "$ck/model.safetensors" ] || die "权重不在：$ck/model.safetensors（$code/$arm）"
  [ -f "$MG/data/$npz" ] || die "示范 npz 不在：$MG/data/$npz（$code/$arm）"
  wait_gpu "$MIN_FREE_EVAL"
  echo "[s11] === $code/$scene/$arm（$mode K=$k eps=$ne seed=$sd）-> runs/$out === $(date '+%F %T')"
  echo "[s11]     instruction=$ins"                # 出处打进日志（坑 30）：指令串是本档唯一变量
  echo "[s11]     ckpt=$ck"
  echo "[s11]     全量日志 -> $log"
  if [ "$DRY_RUN" = "1" ]; then
    echo "[s11]     DRY_RUN=1 ⇒ 只打印命令不执行：$MG_PY code/mg_eval_lang.py --instruction '$ins' --ckpt $ck --episodes $ne --seed-mode random --seed $sd --n-action-steps $k --task-mode $mode --demo-npz $MG/data/$npz --out $MG/runs/$out"
    return 0
  fi
  "$MG_PY" code/mg_eval_lang.py --instruction "$ins" --ckpt "$ck" --episodes "$ne" \
      --seed-mode random --seed "$sd" --n-action-steps "$k" --task-mode "$mode" \
      --demo-npz "$MG/data/$npz" --out "$MG/runs/$out" > "$log" 2>&1
  rc=$?                                           # 坑 80：先存 rc，再做任何 $(...)
  grep -vE "$NOISE" "$log" | grep -E '^\[lang\]|^  ep|成功率|放宽口径|warn|Error|Traceback' | tail -12
  [ "$rc" = "0" ] || die "评测退出码 $rc：$out（日志 $log）"
  [ -f "$MG/runs/$out/eval_summary.json" ] || die "评测没落盘：$out（日志 $log）"
  # sidecar 是 L4 证明「patch 真生效」的唯一凭据；缺了整档不采信 ⇒ 当场停，别烧完 20 读才发现
  [ -f "$MG/runs/$out/lang_sidecar.json" ] || die "lang_sidecar.json 没落盘：$out ⇒ 无法证明指令真被换掉（L4 必挂）"
  grep -q '^\[lang\] patch ' "$log" || die "日志里没有 [lang] patch 行：$out ⇒ 外壳可能没打 patch（静默跑原话）"
}

# ── 0. 已收工/已合法跳过就别重跑（认产物 —— 坑 22(e)）────────────────────────
if [ -s "$MARK" ]; then echo "[s11] 已收工（$MARK 在）：$(head -1 "$MARK")"; exit 0; fi
if [ -s "$SKIPPED" ]; then echo "[s11] 已跳过（$SKIPPED 在）：$(head -1 "$SKIPPED")"; exit 0; fi

# ── 1. 等上游档 10 让卡（**不抢卡**；认产物 + 进程消失，坑 22(e)）──────────────
# 档 10 是 FAILED / SKIPPED 也照常跑：本档不依赖它的**结论**，只依赖它的**卡**。
echo "[s11] === 等档 10 收工并让卡（上限 ${WAIT_H} h）=== $(date '+%F %T')"
got=""
for _ in $(seq 1 $((WAIT_H * 60))); do
  for m in "${UP_MARKS[@]}"; do [ -s "$m" ] && { got="$m"; break 2; }; done
  sleep 60
done
[ -n "$got" ] || skip "等 ${WAIT_H} h 仍没等到上游终态标记 ⇒ 不抢卡、不发车"
echo "[s11] 上游终态标记：$got -> $(head -c 200 "$got")"
for _ in $(seq 1 240); do
  pgrep -f "$UP_PROC" > /dev/null 2>&1 || break
  echo "[s11] 上游链还在（收尾中），等 30 s ... $(date '+%T')"; sleep 30
done
pgrep -f "$UP_PROC" > /dev/null 2>&1 \
  && echo "[s11] ⚠️ 等了 2 h 上游链仍在 ⇒ 靠显存硬闸把关，不硬抢"

# ── 2. 发车闸（预注册 §7；全部只读盘上产物）──────────────────────────────────
echo "[s11] === 发车闸 === $(date '+%F %T')"
[ -f "$PREREG" ] || die "闸0：预注册不在（$PREREG）⇒ 没有事前判据，不许跑（坑 40）"
# 闸0b：任何 s11_* 产物都**必须晚于**预注册（否则就是「看完数才写门」或来路不明的产物）
early=$(find "$MG/runs" -maxdepth 1 -name 's11_*' ! -newer "$PREREG" 2>/dev/null | head -5)
[ -z "$early" ] || die "闸0b：有 s11_* 产物早于预注册落盘时间 ⇒ 时序不对（坑 40）：$early"
echo "[s11] 闸0：预注册在（$(date -r "$PREREG" '+%F %T') 落盘），且没有早于它的 s11_* 产物"
grep -q '^S8_D4=PASS' "$S8V" \
  || die "闸1：$S8V 里没有 S8_D4=PASS ⇒ 原话参照（65/65/64、正向 16/12/16）的出处不成立，Δ 就没有分母"
echo "[s11] 闸1：S8_D4=PASS 在（原话参照的出处成立）"
"$MG_PY" code/mg_eval_lang.py --print-plan > "$PLAN_TSV" 2>"$MG/logs/eval_s11_plan.log" \
  || die "闸2：--print-plan 跑不出来（看 logs/eval_s11_plan.log）⇒ 没有唯一真源清单，不许发车"
nplan=$(tail -n +2 "$PLAN_TSV" | grep -c . || true)
ncol=$(head -1 "$PLAN_TSV" | awk -F'\t' '{print NF}')
[ "$nplan" = "$NREADS_EXPECT" ] || die "闸2：清单 $nplan 读 ≠ 预期 $NREADS_EXPECT 读（$PLAN_TSV）"
[ "$ncol" = "11" ] || die "闸2：清单表头 $ncol 列 ≠ 11 列 ⇒ TSV 形状变了，read 会错位（错位的形状 = 拿 A 的指令跑 B 的臂）"
echo "[s11] 闸2：清单 $nplan 读 / $ncol 列 -> $PLAN_TSV（链按它发车、判定按它读盘）"
for arm in s8c_seed2000 s8d_seed4000 s8d_seed5000; do
  run="pi05_mix60f120r_c1_${arm}"
  ck="$MG/runs/$run/checkpoints/022000/pretrained_model"
  [ -f "$ck/model.safetensors" ] || die "闸3：权重不在 $ck/model.safetensors（$arm）"
  rl=$(readlink "$MG/runs/$run/checkpoints/last" 2>/dev/null || echo "")
  echo "[s11] 闸3：$arm 数字格 022000 在（last -> ${rl:-无}，本档一律走数字格，坑 63）"
  for i in 1 2 3 4; do
    suf=""; [ "$i" -gt 1 ] && suf="_rep$i"
    [ -f "$MG/runs/${arm}_rev_test_rand20_k10${suf}/eval_summary.json" ] \
      || die "闸4：K=10 反向参照缺产物 ${arm}_rev_test_rand20_k10${suf} ⇒ 对账与配对都做不了"
  done
  [ -f "$MG/runs/${arm}_fwd_test_rand20_k10/eval_summary.json" ] \
    || die "闸4：K=10 正向参照缺产物 ${arm}_fwd_test_rand20_k10"
done
echo "[s11] 闸4：原话参照 15 读齐（反向 4 rep × 3 臂 + 正向 1 × 3 臂；**不重跑**，坑 40①）"
[ -f "$MG/data/mix60f120r_rev_raw.npz" ] && [ -f "$MG/data/mix60f120r_raw.npz" ] \
  || die "闸5：示范 npz 不在（mix60f120r_rev_raw.npz / mix60f120r_raw.npz）"
echo "[s11] 闸5：示范 npz 在（反向 + 正向）"
"$MG_PY" "$MG/code/mg_eval_lang.py" --selftest > "$MG/logs/eval_lang_selftest.log" 2>&1 \
  || die "闸6：mg_eval_lang 自测不过（看 logs/eval_lang_selftest.log）⇒ patch 机制本身不可信"
echo "[s11] 闸6：语言外壳自测全绿 -> $(tail -1 "$MG/logs/eval_lang_selftest.log")"
"$MG_PY" "$MG/code/mg_verdict_s11.py" --selftest > "$MG/logs/verdict_s11_selftest.log" 2>&1 \
  || die "闸7：mg_verdict_s11 自测不过（看 logs/verdict_s11_selftest.log）⇒ 门的实现本身不可信"
echo "[s11] 闸7：判定工具自测全绿 -> $(tail -1 "$MG/logs/verdict_s11_selftest.log")"
wait_gpu "$MIN_FREE_EVAL"
free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
[ "${free:-0}" -ge "$MIN_FREE_EVAL" ] || die "闸8：GPU free=${free}MiB < ${MIN_FREE_EVAL}MiB ⇒ 有别的东西在占卡；不并发、不抢卡"
echo "[s11] 闸 0-8 全过（20 读、K=10、ckpt=022000、GPU free=${free}MiB、DRY_RUN=$DRY_RUN）$(date '+%T')"

# ── 3. 20 读评测（进程替换 ⇒ 循环在当前 shell 里，die 才真的能停链；管道会开子壳吞掉退出）──
while IFS=$'\t' read -r code scene arm out task_mode seed0 npz episodes k ckpt instruction; do
  [ -n "${code:-}" ] || continue
  one_read "$code" "$scene" "$arm" "$out" "$task_mode" "$seed0" "$npz" "$episodes" "$k" "$ckpt" "$instruction"
done < <(tail -n +2 "$PLAN_TSV")

# ── 4. 判定汇编（阈值全在 mg_verdict_s11.py / 预注册 §3 里，本链不做任何判读）──
echo "[s11] === 判定汇编 === $(date '+%F %T')"
if [ "$DRY_RUN" = "1" ]; then
  "$MG_PY" code/mg_verdict_s11.py > /tmp/s11_dryrun_verdict.md 2>&1; vrc=$?
  echo "[s11] DRY_RUN：判定写到 /tmp/s11_dryrun_verdict.md，退出码 $vrc（预期 3 = 还没有 s11 产物 ⇒ 不采信）"
  printf '%s 档11 DRY_RUN 完成（闸全过、没跑评测、runs/ 零污染）\n' "$(date '+%F %T')" > "$MARK"
  [ -s "$MARK" ] || die "DRY_RUN 标记写空了（$MARK）"
  echo "[s11] DRY_RUN done $(date '+%F %T')"; exit 0
fi
ngot=$(find "$MG/runs" -maxdepth 2 -name eval_summary.json -path '*/s11_*' 2>/dev/null | wc -l)
[ "$ngot" = "$NREADS_EXPECT" ] || die "只落盘 $ngot/$NREADS_EXPECT 读 ⇒ 判定必然 UNKNOWN（缺读不当 0 计，坑 40③）；看 logs/eval_s11_*.log"
"$MG_PY" code/mg_verdict_s11.py > "$VERD" 2>&1; vrc=$?    # 坑 80：先存 rc
tail -45 "$VERD"
[ "$vrc" = "0" ] || die "判定退出码 $vrc（2=读数不齐 ⇒ L1 UNKNOWN 不当 0 计；3=出身/对账不过 ⇒ 不采信）⇒ 不写 done 标记，看 $VERD"
l1=$(grep -m1 '^S11_L1=' "$VERD" || echo 'S11_L1=?')
l1b=$(grep -m1 '^S11_L1B=' "$VERD" || echo 'S11_L1B=?')
l3=$(grep -m1 '^S11_L3=' "$VERD" || echo 'S11_L3=?')
# 坑 43：终态标记必须 printf 写、写完 [ -s ] 自检；date 的参数不能混进 printf 的位置参数
printf '%s 档11 语言泛化 %s 读完成 %s %s %s 判定=%s\n' \
       "$(date '+%F %T')" "$ngot" "$l1" "$l1b" "$l3" "$VERD" > "$MARK"
[ -s "$MARK" ] || die "标记写空了（$MARK）⇒ 下游按 -f 判存在会误以为收工（坑 43）"
echo "[s11] done $(date '+%F %T')  标记 -> $MARK"
