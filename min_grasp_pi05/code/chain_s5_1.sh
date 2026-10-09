#!/usr/bin/env bash
# 档 5.1 · descend 停滞阶梯 + 认输交还（hand-back）—— 正式读数 4×20 → 判定
#
# 预注册：runs/S5_1_PREREG.md（写盘 2026-10-02 23:23:32，早于任何档 5.1 读数）。
# 本链**只**做预注册第三节写死的那 4 个读数 + 判定，不新增臂、不扩样（坑 40）。
#
# 房规落地：
#   * 发车闸全部**看盘上产物**，不看进程表；每个读数「有产物就跳过」⇒ 可重复执行、可断点续跑；
#   * G1 闸门除了看日志里的 PASS，还核 `runs/s5_1_g1_ceiling_rev_test20_n05` 里记的
#     mg_expert.py sha16 == 当前文件 sha16（坑 49 候选：改完专家没换 G1_NEW ⇒ PASS 是旧的、假的）；
#   * G2 闸门直接读 stall_calib.json 的 grid（T=0.1 mm ∧ W=25 那一格），不读人写的 md；
#   * 检测器锚不可覆盖：harness_calib.json 与 recheck_postguard.json 去掉 generated 后必须逐键相同；
#   * done 标记用 **printf** 写（坑 43），写完立刻 `[ -s ]` 自检；路径全绝对（坑 41）；杀进程只用 PID；
#   * ⚠️ **必须用 `setsid` 发车**（坑 37）：`nohup … &` 挂在交互 shell 的进程组里，PTY 一回收整条链被 SIGKILL
#     （2026-10-02 23:39 实测：链与评测进程一起消失、raw log 0 字节、没有任何 FATAL 行）。
#     正确发法：`setsid nohup bash <绝对路径>/code/chain_s5_1.sh > <绝对路径>/logs/chain_s5_1.log 2>&1 < /dev/null &`
#     发完核两件事：`pgrep -af 'chain_s5_1\.sh'` 只有 **1** 条；该 PID 的 `SID == PID`（STAT 带 s）。
#
# 与档 3r seed 3000 训练并发：档 5.1 只要 ~10 GB 显存（训练占 ~35 GB / 共 80 GB），
# 检查点是 s2e/022000（预注册写死，不依赖训练结果）⇒ 等 s3r.done 没有收益。
# ⚠️ 并发 ⇒ 产物一律 timing_isolated=false：实时性门（≤50 ms/step）**不在本链判**，
#    隔离测由 chain_s5_timing.sh 另跑。本链的主判据是**配对净收益**，与 ms/step 无关。
set -euo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
cd "$MG"
source "$MG/code/env.sh"
MARK="$MG/runs/s5_1.done"
CK="$MG/runs/pi05_mix60f120r_s2e/checkpoints/022000/pretrained_model"
LASTDIR="$MG/runs/pi05_mix60f120r_s2e/checkpoints/last"
PREREG="$MG/runs/S5_1_PREREG.md"
G1LOG="$MG/logs/s5_1_g1_expert_regression.log"
G1DIR="$MG/runs/s5_1_g1_ceiling_rev_test20_n05"
NOISE='^(Warning|/root|  warnings|\[robosuite|Loading|Some robots|To setup|It is recommended)'
REPS=("" "_rep2" "_rep3" "_rep4")
die () { echo "[s5.1][FATAL] $*" >&2; exit 1; }

# ── 发车闸 1：权重与出身 ──────────────────────────────────────────────────
[ -d "$CK" ] || die "检查点不存在：$CK"
rl="$(readlink "$LASTDIR" 2>/dev/null || true)"
[ "$rl" = "022000" ] || die "last 指向 $rl 而不是 022000（坑 38）⇒ 读数会读错权重"
[ -s "$PREREG" ] || die "预注册没落盘：runs/S5_1_PREREG.md（必须先写死后跑数）"
grep -q '配对净收益' "$PREREG" || die "预注册里没有主判据「配对净收益」⇒ 口径可疑，不开跑"
grep -q -- '--hand-back' "$PREREG" || die "预注册里没写 --hand-back ⇒ 与本链要跑的臂不符"
for r in "${REPS[@]}"; do
  [ -s "$MG/runs/s2e_rev_test_rand20_k10$r/eval_summary.json" ] \
    || die "配对基线缺 rep：runs/s2e_rev_test_rand20_k10$r（没基线就没法算净收益）"
done

# ── 发车闸 2：预注册必须早于任何已存在的档 5.1 读数（坑 40 的时序纪律）───────
"$MG_PY" - "$PREREG" "$MG/runs" <<'PY' || die "预注册晚于已有读数 ⇒ 事后补注册，本链不开跑"
import sys, json
from pathlib import Path
prereg, runs = Path(sys.argv[1]), Path(sys.argv[2])
pt = prereg.stat().st_mtime
late = []
for d in sorted(runs.glob("s5_1_handback_rev_test20_k10*")):
    f = d / "eval_summary.json"
    if f.exists() and f.stat().st_mtime < pt:
        late.append(str(f))
if late:
    print("[s5.1][FATAL] 这些读数比预注册还早：", ", ".join(late), file=sys.stderr)
    raise SystemExit(1)
print(f"[s5.1] 闸2 预注册时序 OK（prereg mtime={pt:.0f}，没有更早的 s5_1_handback 读数）")
PY

# ── 发车闸 3：G1 专家逐比特回归（且必须是**当前** mg_expert.py 跑出来的）──────
grep -q '\[G1\] PASS' "$G1LOG" || die "G1 专家回归没过（logs/s5_1_g1_expert_regression.log）⇒ 不许开跑"
[ -s "$G1DIR/ceiling_summary.json" ] || die "G1 产物缺失：$G1DIR/ceiling_summary.json"
# 说明：G1 锚（mg_ceiling.py）只跑纯专家、不经 harness ⇒ 产物里记的是 env/expert 四个文件的 sha；
#       mg_harness.py 的 hand_back 改动由它自己的 --selftest（261 项）钉，不在 G1 的射程里。
"$MG_PY" - "$G1DIR/ceiling_summary.json" "$MG/code" <<'PY' \
  || die "G1 产物不是当前专家跑出来的（改完专家必须换 G1_NEW 重跑，坑 49 候选）"
import hashlib, json, sys
from pathlib import Path
summ = json.load(open(sys.argv[1])); code = Path(sys.argv[2])
have = summ.get("code_sha256_16", {})
assert "mg_expert.py" in have, "G1 产物没记 mg_expert.py 的 sha ⇒ 锚不可用"
for name, got in sorted(have.items()):
    f = code / name
    if not f.exists():
        print(f"[s5.1][FATAL] G1 产物记的 {name} 现在不存在了", file=sys.stderr); raise SystemExit(1)
    cur = hashlib.sha256(f.read_bytes()).hexdigest()[:16]
    if got != cur:
        print(f"[s5.1][FATAL] {name} 当前 sha16={cur} 但 G1 产物记的是 {got}", file=sys.stderr)
        raise SystemExit(1)
    print(f"[s5.1] 闸3 {name} sha16={cur} 与 G1 产物一致")
assert (summ["n_success"], summ["n_success_relaxed"]) == (14, 20), "G1 产物聚合口径不是 严格14/20 放宽20/20"
print("[s5.1] 闸3 G1 = 严格 14/20 ∧ 放宽 20/20 ∧ env/expert sha 全对齐 ⇒ 停滞阶梯是纯增量")
PY

# ── 发车闸 4：G2 停滞窗长标定（直接读 grid，不读人写的 md）──────────────────
"$MG_PY" - "$MG/runs" <<'PY' || die "G2 标定产物不满足预注册第二节（T=0.1mm ∧ W=25）"
import json, sys
from pathlib import Path
runs = Path(sys.argv[1])
def cell(tag):
    d = json.load(open(runs / f"s5_1_stall_calib_{tag}" / "stall_calib.json"))
    hits = [e for e in d["grid"] if abs(e["T_mm"] - 0.1) < 1e-9 and e["W"] == 25]
    assert len(hits) == 1, f"{tag}: T=0.1/W=25 那一格找到 {len(hits)} 个"
    return d, hits[0]
for tag in ("clean_rev", "clean_fwd"):
    d, e = cell(tag)
    assert e["n_runs"] == 20 and e["n_fired"] == 0, f"{tag}: n_runs={e['n_runs']} n_fired={e['n_fired']}（要 20/0）"
    print(f"[s5.1] 闸4 {tag}: 20 局干净专家跑 T=0.1mm/W=25 触发 0/20，最长停滞游程 {e['max_longest']} 步")
d, e = cell("trace")
tags = {f["tag"] for f in e["fired"]}
assert e["n_fired"] >= 2 and any("7014" in t for t in tags) and any("7015" in t for t in tags), \
    f"trace: 卡死局没被阶梯抓到 fired={sorted(tags)}"
print(f"[s5.1] 闸4 trace: 档5 接管 trace 上触发 {e['n_fired']}/{e['n_runs']}（含 7014/7015 死循环）⇒ 该抓的抓得到")
PY

# ── 发车闸 5：检测器锚未被覆盖 + 守卫已否决留档 ─────────────────────────────
[ -s "$MG/runs/_diag/harness_calib.json" ] || die "检测器标定锚缺失：runs/_diag/harness_calib.json"
[ -s "$MG/runs/_diag/harness_calib_recheck_postguard.json" ] || die "加 guard_w 后的对账产物缺失"
"$MG_PY" - "$MG/runs/_diag/harness_calib.json" "$MG/runs/_diag/harness_calib_recheck_postguard.json" <<'PY' \
  || die "检测器锚被改动了（档 5/5.1 的判定引用的就是这份，不可覆盖）"
import json, sys
a, b = (json.load(open(p)) for p in sys.argv[1:3])
a.pop("generated", None); b.pop("generated", None)
assert a == b, "harness_calib.json 与 recheck_postguard.json 除 generated 外不一致 ⇒ 检测器口径漂了"
print("[s5.1] 闸5 检测器锚逐键一致（guard_w 默认关，行为未变）")
PY
[ -s "$MG/runs/_diag/guard_calib.md" ] || die "守卫否决的标定记录缺失：runs/_diag/guard_calib.md"

# ── 发车闸 6：阶梯常数与预注册逐字对齐 ──────────────────────────────────────
grep -q '^DESCEND_STALL_DZ = 0.0001' "$MG/code/mg_expert.py"    || die "DESCEND_STALL_DZ 不是 0.1 mm"
grep -q '^DESCEND_STALL_MAX = 25'    "$MG/code/mg_expert.py"    || die "DESCEND_STALL_MAX 不是 25 步"
grep -q '^DESCEND_MAX_RESTAGES = 2'  "$MG/code/mg_expert.py"    || die "DESCEND_MAX_RESTAGES 不是 2"
grep -q '^GIVE_UP_PHASE = "give_up"' "$MG/code/mg_expert.py"    || die "GIVE_UP_PHASE 不是 give_up"

# ── 发车闸 7：自测全绿 ─────────────────────────────────────────────────────
for t in "code/mg_calib_detector.py --selftest" "code/mg_harness.py --selftest" \
         "code/mg_expert_resume_selftest.py" "code/mg_calib_guard.py --selftest" \
         "code/mg_verdict_s5_1.py --selftest"; do
  "$MG_PY" $t > /dev/null || die "自测没过：$t"
  echo "[s5.1] 闸7 自测绿：$t"
done
echo "[s5.1] 发车闸全过 $(date '+%F %T')  ckpt=$CK  last->$rl  专家sha16=$(sha256sum "$MG/code/mg_expert.py" | cut -c1-16)"

# 只验闸不开跑（S51_GATES_ONLY=1）：用于发车前自检闸门本身有没有写错
if [ "${S51_GATES_ONLY:-0}" = "1" ]; then echo "[s5.1] S51_GATES_ONLY=1 ⇒ 只验闸，不开跑"; exit 0; fi

# ── GPU 余量（与训练并发；不够就等，不硬挤）────────────────────────────────
wait_gpu_room () {
  local need="${1:-14000}" free
  for _ in $(seq 1 90); do
    free="$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits 2>/dev/null | head -1)"
    [ "${free:-0}" -ge "$need" ] && { echo "[s5.1] GPU 余量 ${free} MiB ≥ ${need} MiB，开跑"; return 0; }
    echo "[s5.1] GPU 余量只有 ${free:-?} MiB（< ${need}），等 60 s ..."
    sleep 60
  done
  die "等 90 min 仍拿不到 ${need} MiB 显存"
}

run_eval () {  # $1=rep 后缀（""/_rep2/...）
  local rep="$1" out="s5_1_handback_rev_test20_k10${rep}" raw="$MG/logs/s5_1_eval${rep:-_rep1}.raw.log"
  if [ -f "$MG/runs/$out/eval_summary.json" ]; then echo "[s5.1] 跳过（已有产物）$out"; return 0; fi
  wait_gpu_room 14000
  echo "[s5.1] === $out（eps=20 seed=7000 random reverse K=10 --hand-back）=== $(date '+%F %T')"
  "$MG_PY" "$MG/code/mg_eval_harness.py" --ckpt "$CK" --task-mode reverse \
      --episodes 20 --seed-mode random --seed 7000 --n-action-steps 10 --hand-back \
      --out "$MG/runs/$out" > "$raw" 2>&1 || { tail -30 "$raw" >&2; die "评测进程失败：$out（原始日志 $raw）"; }
  grep -vE "$NOISE" "$raw" | grep -E "^  ep|^\[s5\]|^严格|^放宽|warn|Error|Traceback|err\]" || true
  [ -f "$MG/runs/$out/eval_summary.json" ] || die "评测没落盘：$out"
  "$MG_PY" - "$MG/runs/$out/eval_summary.json" "$out" <<'PY' || die "产物出身不符（坑 41/42）：$out"
import json, sys
d = json.load(open(sys.argv[1])); h = d.get("harness", {})
assert h.get("hand_back") is True, f"{sys.argv[2]}: harness.hand_back != true ⇒ 不是档 5.1 的臂"
assert d.get("task_mode") == "reverse" and int(d.get("episodes", 0)) == 20, f"{sys.argv[2]}: 口径不符"
assert h.get("min_remain") == 0 and int(d.get("n_action_steps", -1)) == 10, f"{sys.argv[2]}: K/min_remain 不符"
seeds = [e["seed"] for e in d["per_episode"]]
assert seeds == list(range(7000, 7020)), f"{sys.argv[2]}: seed 窗口不是 7000..7019"
assert h.get("timing_isolated") is False, f"{sys.argv[2]}: 与训练并发却标了 isolated ⇒ 口径脏"
print(f"[s5.1] 出身核对 OK：hand_back=True K=10 seeds=7000..7019 timing_isolated=False "
      f"接管={h.get('n_takeover')} 认输={h.get('n_unrecoverable')} 交还={h.get('n_handback')} "
      f"restage合计={h.get('restages_total')} 死循环≥100步={h.get('n_deadloop_ge100')}")
PY
}

for rep in "${REPS[@]}"; do run_eval "$rep"; done

# ── 判定（脚本自己写 runs/S5_1_VERDICT.md；stdout 只 tee 到日志，不重定向到同一个文件）──
echo "[s5.1] === 判定汇编 === $(date '+%F %T')"
rc=0
"$MG_PY" "$MG/code/mg_verdict_s5_1.py" 2>&1 | tee "$MG/logs/s5_1_verdict.log" | tail -60 || rc=$?
[ -s "$MG/runs/S5_1_VERDICT.md" ] || die "判定没落盘：runs/S5_1_VERDICT.md"
if [ "$rc" -ne 0 ]; then
  echo "[s5.1][FATAL] 判定脚本退出码 $rc（6 = 机理门未过 ⇒ 成功率不采信）。产物与判定已落盘，不写 done 标记。" >&2
  exit "$rc"
fi
printf '%s 档5.1 hand-back 完成 ckpt=%s reads=4x20(--hand-back,K=10,seed7000,reverse) prereg=%s verdict=%s\n' \
  "$(date '+%F %T')" "pi05_mix60f120r_s2e/022000" "runs/S5_1_PREREG.md" "runs/S5_1_VERDICT.md" > "$MARK"
[ -s "$MARK" ] || die "done 标记写空了（坑 43 复发）"
echo "[s5.1] done $(date '+%F %T')  标记 -> $MARK"
