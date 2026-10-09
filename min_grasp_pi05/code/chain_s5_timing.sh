#!/usr/bin/env bash
# 档 5 · 实时性门（≤50 ms/step）的**隔离**读数 —— 补 chain_s5_harness.sh 判不了的那一格
#
# 为什么单开一条链：runs/S5_PREREG.md 第四节写死「实时性门**只在** timing_isolated=true 的产物上判」，
# 而主链是与档 3r seed 3000 训练**并发**跑的 ⇒ 产物一律 timing_isolated=false，
# mg_verdict_s5.py 在那一格只会打印 ⏸ 不判。并发时 GPU 争用把 ms/step 抬高
# （档 4r 的 K=10 = 41.9 ms/step 就是并发数），拿并发数判门 = 自欺欺人。
#
# 发车闸（全部看盘上产物，不看进程表 —— 房规）：
#   1) runs/s5.done         档 5 主链收工（G0b + 正式 3×20 + 判定都落盘）；
#   2) runs/s3r.done        档 3r 收工（占 GPU 10 h 的是它；坑 43 会把它写成 0 字节 ⇒ 只判 -f 不判 -s）；
#   3) runs/S5_VERDICT.md   判定已落盘（本读是给**已判定的那一臂**补测实时性，不是另开一臂）；
#   4) GPU 真的空了         nvidia-smi 的 compute 进程表为空 ∧ 显存占用 < 1500 MiB。
# 等不到就 FATAL 退出并留日志（不许静默）。
#
# ⚠️ 本读**只**用于实时性门：它的成功率只报不判、**不并入**预注册的 n=60
#   （看过 60 局的判定再往里加样本 = 事后扩样，坑 40 的纪律）。
# ⚠️ 不钉 --torch-seed：正式读数口径一致（坑 39）。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
CK="$MG/runs/pi05_mix60f120r_s2e/checkpoints/022000/pretrained_model"
OUT="$MG/runs/s5_timing_isolated_rev_test20_k10"
CONCURRENT="$MG/runs/s5_takeover_rev_test20_k10"
MD="$MG/runs/S5_TIMING.md"
MARK="$MG/runs/s5_timing.done"
NOISE='^(Warning|/root|  warnings|\[robosuite|Loading|Some robots|To setup|It is recommended)'
GATE_MS=50
die () { echo "[s5t] FATAL $*" >&2; exit 4; }

wait_file () {  # $1=路径 $2=小时上限 $3=说明
  local f="$1" h="$2" what="$3"
  for _ in $(seq 1 $((h * 60))); do
    [ -f "$f" ] && { echo "[s5t] 等到 $what：$f  $(date '+%F %T')"; return 0; }
    sleep 60
  done
  die "等 ${h} h 还没等到 $what：$f"
}

[ -d "$CK" ] || die "检查点不存在：$CK"
wait_file "$MG/runs/s5.done"  6 "档 5 主链收工"
wait_file "$MG/runs/s3r.done" 14 "档 3r 收工"
[ -s "$MG/runs/S5_VERDICT.md" ] || die "有 s5.done 却没有 S5_VERDICT.md"

apps=""; used=""
for _ in $(seq 1 90); do
  apps="$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | tr -d ' \n')"
  used="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1)"
  [ -z "$apps" ] && [ "${used:-99999}" -lt 1500 ] && break
  echo "[s5t] GPU 还没空（compute='${apps:-无}' used=${used:-?}MiB），等 60 s ..."
  sleep 60
done
[ -z "$apps" ] || die "GPU 上仍有 compute 进程：$apps ⇒ 不满足隔离条件，不测"
echo "[s5t] GPU 独占确认 used=${used}MiB  $(date '+%F %T')"

if [ -f "$OUT/eval_summary.json" ]; then
  echo "[s5t] 跳过评测（已有产物）$OUT"
else
  echo "[s5t] === 隔离实时性读数 1×20（接管打开，K=10）=== $(date '+%F %T')"
  "$MG_PY" "$MG/code/mg_eval_harness.py" --ckpt "$CK" --task-mode reverse \
      --episodes 20 --seed-mode random --seed 7000 --n-action-steps 10 \
      --out "$OUT" --isolated-timing 2>&1 | grep -vE "$NOISE" \
      | grep -E "^  ep|^\[s5\]|^严格|Error|Traceback|err\]" || true
  [ -s "$OUT/eval_summary.json" ] || die "评测没落盘（或落空）：$OUT"
fi

GATE_MS="$GATE_MS" "$MG_PY" - "$OUT" "$CONCURRENT" "$MD" <<'PY' || die "实时性判定失败"
import json, os, sys
from datetime import datetime
out, conc, md = sys.argv[1], sys.argv[2], sys.argv[3]
gate = float(os.environ["GATE_MS"])
d = json.load(open(os.path.join(out, "eval_summary.json")))
h = d["harness"]
ms = h.get("ms_per_step") or {}
pol, exp = ms.get("policy"), ms.get("expert")
assert h.get("timing_isolated") is True, "产物 timing_isolated 不是 true ⇒ 不能判实时性门"
c_ms = None
if os.path.exists(os.path.join(conc, "eval_summary.json")):
    ch = json.load(open(os.path.join(conc, "eval_summary.json")))["harness"]
    c_ms = (ch.get("ms_per_step") or {}).get("policy")
    c_iso = ch.get("timing_isolated")
else:
    c_iso = None
ok = pol is not None and pol <= gate
L = []
L.append("# 档 5 · 实时性门（隔离读数）")
L.append("")
L.append(f"生成时间：**{datetime.now():%Y-%m-%d %H:%M:%S}**（`code/chain_s5_timing.sh`）  ")
L.append(f"产物：`{out}`（`--isolated-timing`，`timing_isolated=true`）  ")
L.append("门出处：`runs/S5_PREREG.md` 第四节 —— **≤50 ms/step（20 Hz 预算），且只在 `timing_isolated=true` 的产物上判**。")
L.append("")
L.append("| 指标 | 值 | 门 | 判定 |")
L.append("| --- | --- | --- | --- |")
L.append(f"| 策略 ms/step（隔离） | **{pol}** | ≤{gate:.0f} | {'✅ PASS' if ok else '❌ FAIL'} |")
L.append(f"| 专家 ms/step（接管段，无推理） | {exp} | — | 只报 |")
L.append(f"| 步数 策略 / 专家 | {h.get('n_steps_policy')} / {h.get('n_steps_expert')} | — | 只报 |")
L.append(f"| 主链并发读数 ms/step（`timing_isolated={c_iso}`） | {c_ms} | 不判 | 对照 |")
L.append("")
L.append(f"**判定：TIMING {'PASS' if ok else 'FAIL'}**（策略 {pol} ms/step vs 门 ≤{gate:.0f}）")
L.append("")
L.append("## 本读的成功率（**只报不判，不并入预注册的 n=60**）")
L.append("")
L.append(f"严格 {d.get('n_success')}/{d.get('episodes')} = {100*d.get('pc_success',0):.1f}%　"
         f"放宽 {d.get('n_success_relaxed')}/{d.get('episodes')} = {100*d.get('pc_success_relaxed',0):.1f}%　"
         f"侧躺 {d.get('n_delivered_tipped')}　接管 {h.get('n_takeover')}/{d.get('episodes')}")
L.append("")
L.append("理由：档 5 的 H1/H0 门在 `runs/S5_VERDICT.md` 里已经按预注册的 3×20 = 60 局判过了；"
         "看过判定再往里加第 4 读 = 事后扩样（坑 40 的纪律）。这一读的唯一用途是实时性门。")
open(md, "w", encoding="utf-8").write("\n".join(L) + "\n")
print("\n".join(L[-8:]))
PY
[ -s "$MD" ] || die "S5_TIMING.md 写空了"
printf '%s 档5 实时性隔离读数完成 out=%s gate=<=%sms/step 判定见 runs/S5_TIMING.md\n' \
  "$(date '+%F %T')" "$(basename "$OUT")" "$GATE_MS" > "$MARK"
[ -s "$MARK" ] || die "done 标记写空了（坑 43 复发）"
echo "[s5t] done $(date '+%F %T')  标记 -> $MARK  判定 -> $MD"
