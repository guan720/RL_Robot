#!/usr/bin/env bash
# 档 9B · 运输高度限位（零训练干预）—— 等 7H 让卡、不抢卡。
#
# 预注册：runs/S9_PREREG.md（2026-10-07 13:46 落盘，**早于本链任何读数**；门槛 Z0–Z6 写死在那里，
#         本链**一个字都不改门**，只负责按顺序产读数 + 出判定）。
# 房规：setsid 发车并核 SID==PID（坑 37）；标记 printf 写 + `[ -s ]` 自检（坑 43）；路径全绝对（坑 41）；
#       不编辑在飞的 .sh（坑 22(d)）⇒ **本链不进看门狗清单**（看门狗在飞、不许改），由自己的终态标记覆盖；
#       pgrep 自匹配用字符类（坑 75）。
# 口径：与关门读逐项一致 —— 反向、K=10、每读 20 局、`--demo-npz data/mix60f120r_rev_raw.npz`、img 224（默认）、
#       关门格 `checkpoints/022000/pretrained_model`；门在 **val 8000..8019**，TEST 7000.. 只作 Z5 登记。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"

MARK="$MG/runs/s9b.done"; FAILED="$MG/runs/s9b.FAILED"
LOGDIR="$MG/logs"; mkdir -p "$LOGDIR"
UP_DONE="$MG/runs/s7h.done"; UP_FAIL="$MG/runs/s7h.FAILED"; UP_SKIP="$MG/runs/s7h.SKIPPED"
WAIT_H="${WAIT_H:-14}"
MIN_FREE_EVAL="${MIN_FREE_EVAL:-9000}"          # 与 chain_s7h.sh 的 MIN_FREE_EVAL 同值（只评测）
EP=20; K=10; VAL_SEED0=8000; TEST_SEED0=7000; STEPS=22000
NPZ_R="$MG/data/mix60f120r_rev_raw.npz"        # 8C/8D 关门读用的就是这份（SRC_DS=mix60f120r）
PREREG="$MG/runs/S9_PREREG.md"
NOISE='robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation'

# 门槛常数**只从判定工具读**（单一真理源；链里另写一份 = 迟早漂移）
CAP_MAIN=$("$MG_PY" -c "import sys;sys.path.insert(0,'$MG/code');import mg_verdict_s9b as v;print(v.CAP_MAIN)")
CAP_DOSE=$("$MG_PY" -c "import sys;sys.path.insert(0,'$MG/code');import mg_verdict_s9b as v;print(v.CAP_DOSE)")
CK_SUFFIX=$("$MG_PY" -c "import sys;sys.path.insert(0,'$MG/code');import mg_verdict_s9b as v;print(v.CK_SUFFIX)")

die () { echo "[s9b] FATAL $*" | tee -a "$FAILED"
         printf '%s 档9B 失败 原因=%s\n' "$(date '+%F %T')" "$*" >> "$FAILED"
         [ -s "$FAILED" ] || echo "[s9b] FAILED 标记写空了（坑 43 复发）"; exit 4; }

wait_gpu () {
  local need="${1:-$MIN_FREE_EVAL}" f
  for _ in $(seq 1 240); do
    f=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
    [ "${f:-0}" -ge "$need" ] && return 0
    echo "[s9b] 显存 free=${f}MiB < ${need}MiB，等 30 s ... $(date '+%T')"; sleep 30
  done
  return 0
}

# arm_key -> 训练 run 名（与 mg_verdict_s9b.ARMS / ARM_TEST 逐字一致）
run_of () {
  case "$1" in
    8c_seed2000) echo "pi05_mix60f120r_c1_s8c_seed2000" ;;
    8d_seed4000) echo "pi05_mix60f120r_c1_s8d_seed4000" ;;
    8d_seed5000) echo "pi05_mix60f120r_c1_s8d_seed5000" ;;
    *) echo "" ;;
  esac
}

run_z () {   # $1=arm_key $2=cond标签 $3=cap_cm $4=seed0 $5=窗口标签(val/test) $6=rep后缀
  local armk="$1" cond="$2" cap="$3" sd="$4" win="$5" rep="$6"
  local run ck out
  run=$(run_of "$armk"); [ -n "$run" ] || die "未知臂 $armk"
  ck="$MG/runs/$run/$CK_SUFFIX"
  out="$MG/runs/s9b_${armk}_${cond}_${win}_rand${EP}_k${K}${rep}"
  if [ -s "$out/eval_summary.json" ] && [ -s "$out/zlim_sidecar.json" ]; then
    echo "[s9b] 跳过（产物已齐，断点续跑）：$(basename "$out")"; return 0; fi
  [ -d "$ck" ] || die "闸：检查点不在 $ck"
  wait_gpu "$MIN_FREE_EVAL"
  echo "[s9b] === $armk cond=$cond cap=${cap}cm ${win} seed=${sd}.. rep='${rep:-1}' -> $(basename "$out") === $(date '+%F %T')"
  "$MG_PY" code/mg_eval_zlim.py --z-cap-cm "$cap" --ckpt "$ck" --episodes "$EP" \
      --n-action-steps "$K" --seed-mode random --seed "$sd" --task-mode reverse \
      --demo-npz "$NPZ_R" --out "$out" 2>&1 | grep -vE "$NOISE" | grep -E "^  ep|\[zlim\]|成功率|err" | tail -8
  local rc=${PIPESTATUS[0]}
  [ "$rc" -eq 0 ] || die "$(basename "$out") 评测退出码 $rc"
  [ -s "$out/eval_summary.json" ] || die "$(basename "$out") 缺 eval_summary.json"
  [ -s "$out/zlim_sidecar.json" ] || die "$(basename "$out") 缺 zlim_sidecar.json（审计断链）"
}

block4 () {  # $1=arm_key $2=cond $3=cap $4=seed0 $5=窗口
  local armk="$1" cond="$2" cap="$3" sd="$4" win="$5" rep
  for rep in "" "_rep2" "_rep3" "_rep4"; do run_z "$armk" "$cond" "$cap" "$sd" "$win" "$rep"; done
}

verdict () {
  "$MG_PY" code/mg_verdict_s9b.py > "$MG/runs/S9B_VERDICT.md" 2>&1
  local rc=$?
  echo "[s9b] 判定 -> runs/S9B_VERDICT.md（退出码 $rc）$(date '+%T')"
  return $rc
}
mline () { awk -v k="S9B_$1=" 'index($0,k)==1{sub(k,"");split($0,a," ");print a[1];exit}' "$MG/runs/S9B_VERDICT.md"; }

# ───────────────────────── 闸 1–7（全过才发车）─────────────────────────
echo "[s9b] === 闸 1–7 === $(date '+%F %T')"
[ -s "$PREREG" ] || die "闸1：预注册不在 $PREREG（坑 40：先落盘再产数）"
"$MG_PY" code/mg_eval_zlim.py --selftest > "$LOGDIR/s9b_zlim_selftest.log" 2>&1 \
  || die "闸2：限位外壳自测不绿（$(tail -3 "$LOGDIR/s9b_zlim_selftest.log" | head -1)）"
"$MG_PY" code/mg_verdict_s9b.py --selftest > "$LOGDIR/s9b_verdict_selftest.log" 2>&1 \
  || die "闸3：判定工具自测不绿（$(tail -3 "$LOGDIR/s9b_verdict_selftest.log" | head -1)）"
[ -f "$NPZ_R" ] || die "闸4：示范 npz 不在 $NPZ_R"
for armk in 8c_seed2000 8d_seed4000 8d_seed5000; do
  run=$(run_of "$armk"); ck="$MG/runs/$run/$CK_SUFFIX"
  [ -f "$ck/model.safetensors" ] || die "闸5：$armk 的关门格不在 $ck"
  rl=$(readlink "$MG/runs/$run/checkpoints/last" 2>/dev/null || echo "")
  [ "$rl" = "$(printf '%06d' "$STEPS")" ] || die "闸5b：$armk 的 last -> ${rl:-无}（坑 38 守卫：必须指向 $(printf '%06d' "$STEPS")）"
done
echo "[s9b] 闸 1-5 过（预注册在、两把自测绿、npz 在、三臂关门格与 last 软链核对过；cap 主值=$CAP_MAIN 副值=$CAP_DOSE）"

# 闸6：不抢卡 —— 等 7H 终态 + 进程消失
if [ -s "$MARK" ]; then echo "[s9b] 已收工：$(head -1 "$MARK")"; exit 0; fi
got=""
for _ in $(seq 1 $((WAIT_H * 120))); do
  [ -s "$UP_DONE" ] && { got="DONE"; break; }
  [ -s "$UP_FAIL" ] && { got="FAILED"; break; }
  [ -s "$UP_SKIP" ] && { got="SKIPPED"; break; }
  sleep 30
done
[ -n "$got" ] || die "闸6：等 7H 终态超过 ${WAIT_H} h（三个标记都不在）⇒ 停下等人"
echo "[s9b] 闸6：上游 7H = $got（$(head -c 160 "$UP_DONE" "$UP_FAIL" "$UP_SKIP" 2>/dev/null | head -2)）"
for _ in $(seq 1 60); do
  pgrep -f 'chain_s7h[.]sh' > /dev/null || break
  echo "[s9b] chain_s7h.sh 还在飞，等 30 s ... $(date '+%T')"; sleep 30
done
pgrep -f 'chain_s7h[.]sh' > /dev/null && die "闸6b：chain_s7h.sh 30 min 后仍在飞 ⇒ 不抢卡，停下等人"
pgrep -f 'lerobot-train' > /dev/null && die "闸6c：还有 lerobot-train 在飞 ⇒ 不抢卡，停下等人"
wait_gpu "$MIN_FREE_EVAL"
free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
[ "${free:-0}" -ge "$MIN_FREE_EVAL" ] || die "闸7：GPU free=${free}MiB < ${MIN_FREE_EVAL}MiB"
echo "[s9b] 闸 1-7 全过（GPU free=${free}MiB）$(date '+%F %T')"

# ───────────────────────── Z0 保真读（cap=off，1×20）─────────────────────────
echo "[s9b] === Z0 保真读（cap=off，必须证明外壳从未改动任何一维动作）=== $(date '+%F %T')"
if [ -s "$MG/runs/s9b_z0_fidelity/eval_summary.json" ] && [ -s "$MG/runs/s9b_z0_fidelity/zlim_sidecar.json" ]; then
  echo "[s9b] 跳过（已齐）：s9b_z0_fidelity"
else
  ck="$MG/runs/$(run_of 8d_seed4000)/$CK_SUFFIX"
  wait_gpu "$MIN_FREE_EVAL"
  "$MG_PY" code/mg_eval_zlim.py --z-cap-cm 0 --ckpt "$ck" --episodes "$EP" --n-action-steps "$K" \
      --seed-mode random --seed "$VAL_SEED0" --task-mode reverse --demo-npz "$NPZ_R" \
      --out "$MG/runs/s9b_z0_fidelity" 2>&1 | grep -vE "$NOISE" | grep -E "^  ep|\[zlim\]|成功率|err" | tail -6
  rc=${PIPESTATUS[0]}; [ "$rc" -eq 0 ] || die "Z0 保真读退出码 $rc"
fi
"$MG_PY" - "$MG/runs/s9b_z0_fidelity/zlim_sidecar.json" <<'PY' || die "Z0 保真门不过 ⇒ 按预注册 §3.4 全部作废、停下等人"
import json,sys
s=json.load(open(sys.argv[1]))
assert float(s.get("cap_cm",-1))==0.0, f"cap_cm={s.get('cap_cm')} != 0"
assert int(s.get("n_clamped_total",-1))==0, f"n_clamped_total={s.get('n_clamped_total')} != 0"
assert float(s.get("max_abs_dz_delta",-1))==0.0, f"max|Δdz|={s.get('max_abs_dz_delta')} != 0.0"
assert int(s.get("n_ep",-1))==20, f"n_ep={s.get('n_ep')} != 20"
print(f"[s9b] Z0 ✅ 保真：cap=off、n_clamped=0、max|Δdz|=0.0、n_ep={s['n_ep']}、steps={s['n_steps_total']}")
PY

# ───────────────────────── Z1–Z4 主段（val，2 臂 × {off, cap} × 4×20）─────────────────────────
echo "[s9b] === 主段（val ${VAL_SEED0}..）=== $(date '+%F %T')"
for armk in 8c_seed2000 8d_seed4000; do
  block4 "$armk" "off"     0          "$VAL_SEED0" val
  block4 "$armk" "cap1287" "$CAP_MAIN" "$VAL_SEED0" val
done
# Z6 剂量副读（不是门）
block4 8d_seed4000 "cap1177" "$CAP_DOSE" "$VAL_SEED0" val

verdict; VRC=$?
Z0=$(mline Z0); Z1=$(mline Z1); Z2=$(mline Z2); Z3=$(mline Z3); Z4=$(mline Z4); TRUST=$(mline TRUST)
echo "[s9b] 主段判定：Z0=$Z0 Z1=$Z1 Z2=$Z2 Z3=$Z3 Z4=$Z4 TRUST=$TRUST（判定退出码 $VRC）"
[ "$Z0" = "PASS" ] || die "Z0=$Z0 ⇒ 外壳不干净，全部 9B 读数作废（预注册 §3.4）"

# ───────────────────────── Z5 TEST 登记（仅当三门全过）─────────────────────────
Z5RAN="NO"
if [ "$Z1" = "PASS" ] && [ "$Z2" = "PASS" ] && [ "$Z3" = "PASS" ] && [ "$TRUST" = "YES" ]; then
  echo "[s9b] === Z5 TEST 部署数字登记（3 臂 × cap=${CAP_MAIN}cm × 4×20；**不是门**）=== $(date '+%F %T')"
  for armk in 8c_seed2000 8d_seed4000 8d_seed5000; do
    block4 "$armk" "cap1287" "$CAP_MAIN" "$TEST_SEED0" test
  done
  verdict || true
  Z5RAN="YES"
else
  echo "[s9b] Z1/Z2/Z3 未全过（Z1=$Z1 Z2=$Z2 Z3=$Z3 TRUST=$TRUST）⇒ 按预注册 §3.4 **不烧卡**跑 Z5"
fi

RES=$(mline DECISION)
printf '%s 档9B 完成 干预=运输高度限位(cap=%scm/专家p75,只夹dz>0) 窗口=val8000(门)+TEST7000(Z5登记=%s) Z0=%s Z1=%s Z2=%s Z3=%s Z4=%s TRUST=%s 判定=runs/S9B_VERDICT.md 结论=%s\n' \
  "$(date '+%F %T')" "$CAP_MAIN" "$Z5RAN" "$Z0" "$Z1" "$Z2" "$Z3" "$Z4" "$TRUST" "$RES" > "$MARK"
[ -s "$MARK" ] || die "done 标记写空了（坑 43 复发）"
echo "[s9b] 收工 $(date '+%F %T')  标记 -> $MARK"
