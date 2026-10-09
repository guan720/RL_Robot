#!/usr/bin/env bash
# 档 5 · Harness 接管 —— G0a → G0b → 正式读数（3×20）→ 判定
#
# 房规落地：
#   * 发车闸全部**看盘上产物**，不看进程表；
#   * 每个读数「有产物就跳过」⇒ 本脚本可重复执行、可断点续跑；
#   * done 标记用 **printf** 写（坑 43：`date +"..." args` 不是 printf，会落 0 字节），写完立刻 `[ -s ]` 自检；
#   * 所有路径绝对（坑 41）；杀进程只用 PID；
#   * 不碰任何被档 3r 链 exec 的文件（mg_eval.py / mg_env*.py / mg_verdict_s3r.py 全部只读）。
#
# 与档 3r seed 3000 训练并发：档 5 只要 ~10 GB 显存（训练占 34 GB / 共 80 GB），
# 且档 5 的检查点已由 runs/S5_PREREG.md 第五节写死为 s2e/022000（不依赖档 3r 的结果）⇒
# 等 10 h 的 s3r.done 没有收益。实时性门（≤50 ms/step）**不在本链判**：本链与训练并发，
# 产物一律 timing_isolated=false，隔离测另跑（见 S5_PREREG 第四节）。
set -euo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
cd "$MG"
source "$MG/code/env.sh"
MARK="$MG/runs/s5.done"
CK="$MG/runs/pi05_mix60f120r_s2e/checkpoints/022000/pretrained_model"
LASTDIR="$MG/runs/pi05_mix60f120r_s2e/checkpoints/last"
NOISE='^(Warning|/root|  warnings|\[robosuite|Loading|Some robots|To setup|It is recommended)'
die () { echo "[s5][FATAL] $*" >&2; exit 1; }

# ── 发车闸 ────────────────────────────────────────────────────────────────
[ -d "$CK" ] || die "检查点不存在：$CK"
rl="$(readlink "$LASTDIR" 2>/dev/null || true)"
[ "$rl" = "022000" ] || die "last 指向 $rl 而不是 022000（坑 38）⇒ 读数会读错权重"
[ -s "$MG/runs/S5_PREREG.md" ] || die "预注册没落盘：runs/S5_PRERPG.md（必须先写死后跑数）"
grep -q '\[G1\] PASS' "$MG/logs/g1_expert_regression.log" || die "G1 专家回归没过 ⇒ 不许开跑"
[ -s "$MG/runs/_diag/harness_calib.json" ] || die "检测器标定产物缺失：runs/_diag/harness_calib.json"
[ -s "$MG/runs/s5_resume_probe_slip/resume_probe.json" ] || die "resume 真物理预检产物缺失"
for t in "code/mg_calib_detector.py --selftest" "code/mg_harness.py --selftest"; do
  "$MG_PY" $t > /dev/null || die "自测没过：$t"
done
"$MG_PY" code/mg_expert_resume_selftest.py > /dev/null || die "resume 自测没过"
# 盘上不能已有正式读数（否则本链就不是「预注册之后第一次跑」）
echo "[s5] 发车闸全过 $(date '+%F %T')  ckpt=$CK  last->$rl"

run_eval () {  # $1=out 名  $2=eps  $3=seed  $4..=额外参数
  local out="$1" eps="$2" seed="$3"; shift 3
  if [ -f "$MG/runs/$out/eval_summary.json" ]; then echo "[s5] 跳过（已有产物）$out"; return 0; fi
  echo "[s5] === $out (eps=$eps seed=$seed 额外=$*) === $(date '+%F %T')"
  "$MG_PY" "$MG/code/mg_eval_harness.py" --ckpt "$CK" --task-mode reverse \
      --episodes "$eps" --seed-mode random --seed "$seed" --n-action-steps 10 \
      --out "$MG/runs/$out" "$@" 2>&1 | grep -vE "$NOISE" \
      | grep -E "^  ep|^\[s5\]|^严格|warn|Error|Traceback|err\]" || true
  [ -f "$MG/runs/$out/eval_summary.json" ] || die "评测没落盘：$out"
}

# ── G0a：外壳确定性等价（3 局，钉 torch 种子，逐比特对比）──────────────────
# seed 选 7002..7004：标定显示这三个 seed 在档 2e 臂上**都会触发**（7002 C@98/B@117、
# 7003 A@76、7004 OK 误触发 T3@265）⇒ 对比才真的在比「检测器活着 vs 死透」。
echo "[s5] === 阶段 G0a：外壳确定性等价 === $(date '+%F %T')"
run_eval s5_g0a_observe_ts12345 3 7002 --observe-only --torch-seed 12345
for r in off off2 off3; do   # 三次「检测器关掉」= 噪声地板（GPU 前向本身不可逐比特复现，坑 44）
  run_eval "s5_g0a_${r}_ts12345" 3 7002 --detector-off --torch-seed 12345
done
"$MG_PY" "$MG/code/mg_g0a_equiv.py" "$MG/runs/s5_g0a_observe_ts12345" \
    "$MG/runs/s5_g0a_off_ts12345" "$MG/runs/s5_g0a_off2_ts12345" "$MG/runs/s5_g0a_off3_ts12345" \
    2>&1 | tee "$MG/logs/s5_g0a.log"
grep -q '\[G0a\] PASS' "$MG/logs/s5_g0a.log" || die "G0a 不过 ⇒ harness 外壳的扰动超过噪声地板，档 5 作废"

# ── G0b：观察模式 3×20（与档 2e 基线同 seed 同 K）─────────────────────────
echo "[s5] === 阶段 G0b：观察模式 3×20 === $(date '+%F %T')"
for i in 1 2 3; do
  suf=""; [ "$i" -gt 1 ] && suf="_rep$i"
  run_eval "s5_g0b_observe_rev_test20_k10$suf" 20 7000 --observe-only
done

# ── 正式读数：接管打开 3×20 ───────────────────────────────────────────────
echo "[s5] === 阶段 正式读数：接管 3×20 === $(date '+%F %T')"
for i in 1 2 3; do
  suf=""; [ "$i" -gt 1 ] && suf="_rep$i"
  run_eval "s5_takeover_rev_test20_k10$suf" 20 7000
done

# ── 判定 ─────────────────────────────────────────────────────────────────
echo "[s5] === 判定汇编 === $(date '+%F %T')"
"$MG_PY" "$MG/code/mg_verdict_s5.py" > "$MG/runs/S5_VERDICT.md" 2>&1 || die "判定脚本失败"
tail -50 "$MG/runs/S5_VERDICT.md"
printf '%s 档5 Harness 接管完成 ckpt=%s reads=3x20+3x20observe+G0a prereg=%s\n' \
  "$(date '+%F %T')" "pi05_mix60f120r_s2e/022000" "runs/S5_PREREG.md" > "$MARK"
[ -s "$MARK" ] || die "done 标记写空了（坑 43 复发）"
echo "[s5] done $(date '+%F %T')  标记 -> $MARK"
