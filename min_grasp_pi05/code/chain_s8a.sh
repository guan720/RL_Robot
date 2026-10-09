#!/usr/bin/env bash
# 档 8 · 8A-0(零 GPU 探针) -> 8A(80 局产出率标定) -> 8B(采到 ≥7000 帧 + 建合并集)
#       预注册：runs/S8_PREREG.md（2026-10-04 12:25 落盘 + §9 增补，**早于本档任何读数**）
#
# 一句话：让脚本专家在**坏 seed 2000 自己访问到的失败状态**上接管，把接管片段（含双相机图）落成训练帧，
#   追加进原数据集 -> `data/mix60f120r_c1`（chain_s8c.sh 用它重训）。本链**只采集与建集，不训练**。
#
# 三条终态（都是预注册分支，看门狗认得）：
#   runs/s8a.done    = 8A 三门全过 ∧ 8B 建集对账全过 ⇒ 可以发 8C
#   runs/s8a.HELD    = 8A 的 A1/A2/A3 有一条不过（产出率/质量不够）⇒ **停下等人**，不自动降门（坑 40）
#   runs/s8a.FAILED  = 链本身出错（闸不过、工具崩、对账不符）
#
# ⚠️ 采集用 horizon=800（**只采集用**）：评测 horizon 恒 400，一个字不改（mg_env.HORIZON 是冻结口径）。
# ⚠️ 采集 seed 窗口 9000..9479 必须与所有评测/示范窗口不相交（闸 9 现算断言；泄漏会让门失效）。
# ⚠️ 纠正集的出身（策略 ckpt）一律写**数字格** 022000，不写 `last`（坑 63）。
# ⚠️ B 计划（重收 180 集）不在本链里自动跑：8A-0 探针已于 2026-10-04 12:25 判「过」
#   （runs/s8a_probe/append_probe.md），若哪天它变成不过，本链写 HELD 等人决定 —— 重收 180 集要新的
#   数据集命名与超集对账口径，那是**另一份预注册**的事，不该由链在半夜自动替你决定。
#
# 房规：setsid 发车（坑 37）；标记 printf 写 + `[ -s ]` 自检（坑 43）；路径全绝对（坑 41）；
#   完成与否一律看**磁盘产物**、不看进程表（坑 22(e)）；有产物就跳过 ⇒ 可断点续跑；
#   不编辑运行中的 .sh（坑 22(d)）；不碰冻结文件（mg_eval / mg_env* / mg_expert / mg_sweep_rev / ...）。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
NOISE='robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation|examples/s'

SRC_DS="mix60f120r"            # 原数据集（**只读**）
CORR="corr_r1"                 # 纠正集（本链产出）
DST="mix60f120r_c1"            # 合并集（8C 的训练集）
BASE_STEP=22000                # 坏 seed 的关门格（= last）
BASE_CKPT="$MG/runs/pi05_${SRC_DS}_s3r_seed2000/checkpoints/$(printf '%06d' "$BASE_STEP")/pretrained_model"
A_SEED="${A_SEED:-9000}"; A_EPS="${A_EPS:-80}"
B_SEED="${B_SEED:-9080}"; B_MAX_EPS="${B_MAX_EPS:-320}"
TARGET_FRAMES="${TARGET_FRAMES:-7000}"
HORIZON="${HORIZON:-800}"
K="${K:-10}"
MIN_FREE_EVAL="${MIN_FREE_EVAL:-9000}"
WAIT_H="${WAIT_H:-30}"          # 档 7F 最长分支 ≈12.7 h

NPZ_R="$MG/data/${SRC_DS}_rev_raw.npz"
PROBE_MD="$MG/runs/s8a_probe/append_probe.md"
PROBE_JSON="$MG/runs/s8a_probe/append_probe.json"
A_REPORT="$MG/runs/s8a_calib/collect_report"
B_REPORT="$MG/runs/s8b_collect/collect_report"
M_REPORT="$MG/runs/s8b_merge/merge_report"
MARK="$MG/runs/s8a.done"
HELD="$MG/runs/s8a.HELD"
FAILED="$MG/runs/s8a.FAILED"

die  () { echo "[s8a] FATAL $*" | tee -a "$FAILED"; exit 4; }
hold () { printf '%s 档8A 暂缓（预注册分支，不是失败）原因=%s 依据=runs/S8_PREREG.md §3「不过 ⇒ 写 runs/s8a.HELD 停下等人」\n' \
            "$(date '+%F %T')" "$1" > "$HELD"
          [ -s "$HELD" ] || echo "[s8a] HELD 写空了（坑 43 复发）"
          echo "[s8a] HELD：$1"; exit 0; }

wait_gpu () {  # $1 = 需要的 free MiB
  local need="$1" f
  for _ in $(seq 1 240); do
    f=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
    [ "${f:-0}" -ge "$need" ] && return 0
    echo "[s8a] 显存 free=${f}MiB < ${need}MiB，等 30 s ... $(date '+%T')"; sleep 30
  done
  echo "[s8a] 等了 2 h 显存仍不足 ${need}MiB（不抢卡，继续尝试）"; return 0
}

info_get () { "$MG_PY" -c "import json,sys;print(json.load(open(sys.argv[1]))[sys.argv[2]])" "$1" "$2"; }

# ── 0. 等档 7F 收工（认产物，不认进程表 —— 坑 22(e)）──────────────────────────
if [ -s "$MARK" ]; then echo "[s8a] 已收工（$MARK 在）：$(head -1 "$MARK")"; exit 0; fi
if [ -s "$HELD" ]; then echo "[s8a] 已暂缓（$HELD 在）：$(head -1 "$HELD")"; exit 0; fi
echo "[s8a] === 等档 7F 收工（上限 ${WAIT_H} h）=== $(date '+%F %T')"
got=""
for _ in $(seq 1 $((WAIT_H * 60))); do
  [ -s "$MG/runs/s7f.done" ]   && { got="done";   break; }
  [ -s "$MG/runs/s7f.FAILED" ] && { got="FAILED"; break; }
  sleep 60
done
case "$got" in
  done)   echo "[s8a] 7F 收工：$(head -1 "$MG/runs/s7f.done")" ;;
  FAILED) die "档7F 写了 runs/s7f.FAILED：$(head -1 "$MG/runs/s7f.FAILED") ⇒ 上游没干净收工，等人看" ;;
  "")     die "等 ${WAIT_H} h 仍没有 runs/s7f.done（FAILED 也没有）⇒ 7F 可能静默死亡，看 logs/ALERTS.log" ;;
esac

# ── 1. 发车闸（预注册 §7 的九条，全部看盘上产物）─────────────────────────────
echo "[s8a] === 发车闸 === $(date '+%F %T')"
[ -s "$MARK" ] && die "闸8：runs/s8a.done 已在 ⇒ 本格已收工，不重复跑"
[ -s "$HELD" ] && die "闸8：runs/s8a.HELD 已在 ⇒ 等人决定，不许自动重跑（坑 40）"
grep -q '7G_TRIGGER=' "$MG/runs/S7F_DIAG.md" 2>/dev/null \
  || die "闸1：runs/S7F_DIAG.md 里没有 7G_TRIGGER= 行（诊断没落盘）"
EP_SRC=$(info_get "$MG/data/$SRC_DS/meta/info.json" total_episodes)
FR_SRC=$(info_get "$MG/data/$SRC_DS/meta/info.json" total_frames)
[ "$EP_SRC" = "180" ] && [ "$FR_SRC" = "46426" ] \
  || die "闸2：原数据集是 $EP_SRC 集 / $FR_SRC 帧 ≠ 180 / 46426 ⇒ 分母变了（坑 33）"
[ -f "$BASE_CKPT/model.safetensors" ] || die "闸3：坏 seed 的关门权重不在：$BASE_CKPT"
rl=$(readlink "$MG/runs/pi05_${SRC_DS}_s3r_seed2000/checkpoints/last" 2>/dev/null || echo "")
[ "$rl" = "$(printf '%06d' "$BASE_STEP")" ] \
  || die "闸3：last 指向 '$rl' 而不是 $(printf '%06d' "$BASE_STEP")（坑 38：会读错权重）"
[ -f "$NPZ_R" ] || die "闸4：反向示范 npz 不在：$NPZ_R"
"$MG_PY" "$MG/code/mg_collect_corr.py"  --selftest > "$MG/logs/collect_corr_selftest.log" 2>&1 \
  || die "闸5：mg_collect_corr 自测不过（看 logs/collect_corr_selftest.log）"
"$MG_PY" "$MG/code/mg_ds_append_probe.py" --selftest > "$MG/logs/ds_append_probe_selftest.log" 2>&1 \
  || die "闸5：mg_ds_append_probe 自测不过"
"$MG_PY" "$MG/code/mg_verdict_s8.py" --selftest > "$MG/logs/verdict_s8_selftest.log" 2>&1 \
  || die "闸5：mg_verdict_s8 自测不过"
free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
[ "${free:-0}" -ge "$MIN_FREE_EVAL" ] || die "闸7：GPU free=${free}MiB < ${MIN_FREE_EVAL}MiB（别的实验在跑，不抢卡）"
# 闸 9：采集窗口与所有评测/示范窗口不相交（现算，不靠肉眼）
"$MG_PY" - "$A_SEED" "$A_EPS" "$B_SEED" "$B_MAX_EPS" <<'PY' || die "闸9：采集 seed 窗口与评测/示范窗口相交"
import sys
sys.path.insert(0, "/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05/code")
from mg_collect_corr import EVAL_WINDOWS, windows_disjoint
a0, an, b0, bn = (int(x) for x in sys.argv[1:5])
ca = windows_disjoint((a0, a0 + an - 1), EVAL_WINDOWS)
cb = windows_disjoint((b0, b0 + bn - 1), EVAL_WINDOWS)
print(f"[s8a] 闸9 窗口 8A={a0}..{a0+an-1} 冲突={ca} / 8B={b0}..{b0+bn-1} 冲突={cb}")
sys.exit(0 if not (ca or cb) else 1)
PY
echo "[s8a] 闸 1-9 全过（GPU free=${free}MiB；三个自测见 logs/*_selftest.log）$(date '+%T')"

# ── 2. 格 8A-0：数据集「复制 + 追加」探针（零 GPU，5 s；已有产物就只核对判定）──
if [ -f "$PROBE_JSON" ]; then
  echo "[s8a] 8A-0 探针产物已在：$(grep -m1 '判定' "$PROBE_MD" || true)"
else
  echo "[s8a] === 格 8A-0 · 追加探针（零 GPU）=== $(date '+%F %T')"
  "$MG_PY" "$MG/code/mg_ds_append_probe.py" > "$MG/logs/s8a0_probe.log" 2>&1
  rc=$?; echo "[s8a] 8A-0 rc=$rc -> ${PROBE_MD#$MG/}"
  [ "$rc" -eq 0 ] || hold "格 8A-0 探针不过（rc=$rc）⇒ 建集要走 B 计划（重收 180 集），那是另一份预注册的事"
fi
"$MG_PY" -c "import json,sys;sys.exit(0 if json.load(open(sys.argv[1]))['pass'] else 1)" "$PROBE_JSON" \
  || hold "格 8A-0 探针判定为「不过」⇒ 复制+追加路线不成立，等走 B 计划"

# ── 3. 格 8A：产出率标定（80 局，GPU ~35 min）────────────────────────────────
if [ -f "$A_REPORT.json" ]; then
  echo "[s8a] 跳过 8A（已有产物）：${A_REPORT#$MG/}.md"
  A_RC=0
  grep -q '"all_pass": true' "$A_REPORT.json" || A_RC=5
else
  echo "[s8a] === 格 8A · 产出率标定（$A_EPS 局 / seed $A_SEED.. / horizon=$HORIZON / K=$K）=== $(date '+%F %T')"
  wait_gpu "$MIN_FREE_EVAL"
  "$MG_PY" "$MG/code/mg_collect_corr.py" --mode collect \
      --ckpt "$BASE_CKPT" --episodes "$A_EPS" --seed "$A_SEED" --horizon "$HORIZON" \
      --n-action-steps "$K" --out "$CORR" --gate-a --report "$A_REPORT" \
      > "$MG/logs/s8a_collect.log" 2>&1
  A_RC=$?
  echo "[s8a] 8A rc=$A_RC $(date '+%F %T') 日志 -> logs/s8a_collect.log 报告 -> ${A_REPORT#$MG/}.md"
  grep -E '^\[gate|^  ep' "$MG/logs/s8a_collect.log" | tail -12
fi
case "$A_RC" in
  0) echo "[s8a] 8A 三门全过 ⇒ 进 8B" ;;
  5) hold "格 8A 的 A1/A2/A3 有一条不过（读数见 ${A_REPORT#$MG/}.md）⇒ 不许当场改门（坑 40）" ;;
  *) die "格 8A 非 0/5 退出（rc=$A_RC）⇒ 采集器崩了，看 logs/s8a_collect.log" ;;
esac

# ── 4. 格 8B：续采到目标帧数（GPU 1.5~2.5 h）─────────────────────────────────
HAVE=$(info_get "$MG/data/$CORR/meta/info.json" total_frames 2>/dev/null || echo 0)
NEED=$((TARGET_FRAMES - HAVE))
echo "[s8a] 8B：已有 $HAVE 可用帧 / 目标 $TARGET_FRAMES ⇒ 还需 $NEED"
if [ "$NEED" -le 0 ]; then
  echo "[s8a] 跳过 8B 采集（已达目标帧数）"
elif [ -f "$B_REPORT.json" ]; then
  echo "[s8a] 跳过 8B 采集（已有产物）：${B_REPORT#$MG/}.md"
else
  echo "[s8a] === 格 8B · 续采（seed $B_SEED.. / 上限 $B_MAX_EPS 局 / 目标 +$NEED 帧）=== $(date '+%F %T')"
  wait_gpu "$MIN_FREE_EVAL"
  "$MG_PY" "$MG/code/mg_collect_corr.py" --mode collect --append \
      --ckpt "$BASE_CKPT" --episodes "$B_MAX_EPS" --seed "$B_SEED" --horizon "$HORIZON" \
      --n-action-steps "$K" --out "$CORR" --target-frames "$NEED" --report "$B_REPORT" \
      > "$MG/logs/s8b_collect.log" 2>&1
  rc=$?; echo "[s8a] 8B 采集 rc=$rc $(date '+%F %T') 日志 -> logs/s8b_collect.log"
  [ "$rc" -eq 0 ] || die "格 8B 采集非 0 退出（rc=$rc）"
  grep -E '^\[corr\] [0-9]+ 局' "$MG/logs/s8b_collect.log" | tail -3
fi
HAVE=$(info_get "$MG/data/$CORR/meta/info.json" total_frames)
EPC=$(info_get "$MG/data/$CORR/meta/info.json" total_episodes)
echo "[s8a] 纠正集 $CORR：$EPC 集 / $HAVE 帧（目标 $TARGET_FRAMES；不足则按实际走并在判定里写明）"

# ── 5. 格 8B 建集：cp -a 原数据集 -> 追加纠正 episode -> B1/B2/B3 对账 ────────
EP_DST=$(info_get "$MG/data/$DST/meta/info.json" total_episodes 2>/dev/null || echo 0)
if [ "$EP_DST" -gt 180 ]; then
  echo "[s8a] 跳过合并（$DST 已是 $EP_DST 集 > 180 ⇒ 合并已做过，不重复追加）"
else
  if [ -d "$MG/data/$DST" ]; then
    die "$MG/data/$DST 存在但还是 $EP_DST 集 ⇒ 上次合并中断在半路，人工看 ${M_REPORT#$MG/}.md 后决定（不自动覆盖）"
  fi
  echo "[s8a] === 格 8B 建集 · cp -a data/$SRC_DS -> data/$DST（4.8 GB，~2 min）=== $(date '+%F %T')"
  cp -a "$MG/data/$SRC_DS" "$MG/data/$DST" || die "cp -a 失败（磁盘？权限？）"
  [ -f "$MG/data/$DST/meta/info.json" ] || die "拷贝完却没有 meta/info.json"
  echo "[s8a] === 追加纠正 episode + B1/B2/B3 对账（零 GPU）=== $(date '+%F %T')"
  "$MG_PY" "$MG/code/mg_collect_corr.py" --mode merge \
      --out "$CORR" --dst "$DST" --target-frames "$TARGET_FRAMES" --report "$M_REPORT" \
      > "$MG/logs/s8b_merge.log" 2>&1
  rc=$?; echo "[s8a] 合并 rc=$rc $(date '+%F %T') 报告 -> ${M_REPORT#$MG/}.md"
  grep -E '^\[gate|逐比特' "$MG/logs/s8b_merge.log" | tail -8
  [ "$rc" -eq 0 ] || die "格 8B 对账不过（rc=$rc）⇒ 合并集不可用，**不许**进 8C，看 ${M_REPORT#$MG/}.md"
fi
FR_DST=$(info_get "$MG/data/$DST/meta/info.json" total_frames)
EP_DST=$(info_get "$MG/data/$DST/meta/info.json" total_episodes)
[ "$EP_DST" -gt 180 ] || die "合并集还是 $EP_DST 集 ⇒ 追加没生效"
[ -f "$MG/data/$DST/MG_DATASET_CARD.json" ] || die "合并集没有数据卡片（出身不可查）"

printf '%s 档8A/8B 完成 探针=过 8A=%s局(三门全过) 纠正集=data/%s(%s集/%s帧) 合并集=data/%s(%s集/%s帧) 目标帧=%s 采集horizon=%s(评测恒400) 报告=runs/s8a_calib,runs/s8b_collect,runs/s8b_merge\n' \
  "$(date '+%F %T')" "$A_EPS" "$CORR" "$EPC" "$HAVE" "$DST" "$EP_DST" "$FR_DST" "$TARGET_FRAMES" "$HORIZON" > "$MARK"
[ -s "$MARK" ] || die "done 标记写空了（坑 43 复发）"
echo "[s8a] 收工 $(date '+%F %T')  标记 -> $MARK"
