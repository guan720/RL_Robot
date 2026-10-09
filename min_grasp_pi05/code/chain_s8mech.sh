#!/usr/bin/env bash
# 档 8 · 8C 的**机理读数**（零 GPU、只用 val 窗口、**不是门**）
#   预注册出处：runs/S8_PREREG.md §9 **增补 11**（2026-10-04 17:45 落盘，早于 8C 任何读数）
#
# 为什么要有这条旁链：D1 是一个 k/80 的二值门，只说「过/不过」、不说**为什么**。而 `chain_s8c.sh` 的
# 11 格反向 val 扫描（seed 8000..8019）跑在 TEST 之前 ⇒ 用重放台把这批录像变成机理账，
# 就能在 D1 落盘前 ~1 h 拿到「纠正数据到底改了什么」的读数，且**一次策略推理都不做**（零 GPU、不抢卡）。
#
# 读数四条（口径写死，看完数不许改）：① 8C 每格的放宽成功率（直接读 eval_summary，与对照臂逐格配对）
#   ② 接管率 ③ 接管状态类构成（⚠️ 坑 74：`MOVED` 不是难度标签）④ A2（接管局放宽成功率）。
# 判读只解释、不判过不过（见增补 11）。**不改任何门**；D1/D2/D3 一律只由 code/mg_verdict_s8.py 出。
#
# 房规：setsid 发车并核 SID==PID（坑 37）；done 标记 printf 写 + `[ -s ]` 自检（坑 43）；路径全绝对（坑 41）；
#   认产物不认进程表（坑 22(e)）；不编辑运行中的 .sh（坑 22(d)）；不碰冻结文件（重放台只 import 它们）；
#   **绝不喂 TEST 窗口**（mg_s9_rescue 对 7000..7019 有硬闸，本链只喂 val 8000..8019 的语料）。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"

RUN="${RUN:-$MG/runs/pi05_mix60f120r_c1_s8c_seed2000}"          # 8C 主实验（全集 + 纠正帧）
CTL_RUN="${CTL_RUN:-$MG/runs/pi05_mix60f120r_s3r_seed2000}"     # 对照 = 档 3r 的坏 seed 臂（同步数/同 val 窗口）
OUT="${OUT:-$MG/runs/_diag/s8_mech}"                            # 产物目录（新文件夹，不与 s9_rescue 混）
BASE="${BASE:-$MG/runs/_diag/s9_rescue}"                        # 对照臂的重放台读数（已测过，直接复用）
WAIT_H="${WAIT_H:-20}"
# ── 以下 6 个只为**同一条链跑不同臂**（8D 的两个新 seed）而参数化，默认值 = 原 8C 的逐字行为：
TAG="${TAG:-8C}"                       # done 标记里的臂名
TITLE="${TITLE:-# 档 8 · 8C 的机理读数（零 GPU、val 窗口 8000..8019、**不是门**）}"
CTL_DESC="${CTL_DESC:-* 对照臂 = 档 3r 的坏 seed 2000（同 22000 步、同 val 窗口、同 K=10）；两臂**跨数据集** ⇒ normalizer 不同，}"
CTL_DESC2="${CTL_DESC2:-  下表只读**方向与机理**，干净的 1:1 归因只认 D3（\`8C-ctl\`）。**不改任何门。**}"
RULES_NOTE="${RULES_NOTE:-}"           # 追加在判读规则之后的臂特定说明（默认空）
EXTRA_MARKS="${EXTRA_MARKS:-}"         # 额外的上游终态标记（空格分隔的绝对路径），命中就安静退场
UPSTREAM_HINT="${UPSTREAM_HINT:-8C 可能没发车或半路死；看 logs/chain_s8c.log}"
STEPS="${STEPS:-22000}"; SAVE_FREQ="${SAVE_FREQ:-2000}"; NCELLS="${NCELLS:-11}"
RESCUE="${RESCUE:-1}"     # 0 = 冒烟：跳过仿真，只做汇总与对比（用盘上已有的单格 json）
FID="${FID:-1}"           # 0 = 冒烟：跳过保真格
MARK="$OUT/MECH.done"; SKIPM="$OUT/MECH.SKIPPED"; FAILM="$OUT/MECH.FAILED"
LOG="${LOG:-$MG/logs/s8_mech.log}"

die () { printf '%s [mech] FATAL %s\n' "$(date '+%F %T')" "$*" | tee -a "$FAILM"; exit 4; }
cells_ready () {  # $1=run 目录；回显齐了几格
  local n=0 s
  for s in $(seq "$SAVE_FREQ" "$SAVE_FREQ" "$STEPS"); do
    [ -f "$1/sweep_rev/step_${s}_rev/eval_summary.json" ] && n=$((n + 1))
  done
  echo "$n"
}

mkdir -p "$OUT/rescue" "$OUT/fid"
if [ -s "$MARK" ]; then echo "[mech] 已收工（$MARK 在）：$(head -1 "$MARK")"; exit 0; fi

# ── 0. 等 8C 的 11 格 val 扫描齐（认产物；上游若终止就安静退场）──────────────────
echo "[mech] === 等 8C 的 ${NCELLS} 格 val 扫描（上限 ${WAIT_H} h）=== $(date '+%F %T')"
for _ in $(seq 1 $((WAIT_H * 60))); do
  for m in "$MG/runs/s8a.HELD" "$MG/runs/s8a.FAILED" "$MG/runs/s8c.SKIPPED" "$MG/runs/s8c.FAILED" $EXTRA_MARKS; do
    if [ -s "$m" ]; then
      printf '%s 8C 机理读数不发车（上游终态 %s：%s）\n' "$(date '+%F %T')" "$(basename "$m")" "$(head -1 "$m")" > "$SKIPM"
      [ -s "$SKIPM" ] || echo "[mech] SKIPPED 写空了（坑 43 复发）"
      echo "[mech] SKIP：上游写了 $m"; exit 0
    fi
  done
  n=$(cells_ready "$RUN")
  [ "$n" -ge "$NCELLS" ] && break
  sleep 60
done
n=$(cells_ready "$RUN")
[ "$n" -ge "$NCELLS" ] || die "等 ${WAIT_H} h 只齐了 $n/$NCELLS 格（${UPSTREAM_HINT}）"
[ -d "$BASE" ] || die "对照臂的重放台读数不在：$BASE（先跑 code/mg_s9_rescue.py，见 FINDINGS §十）"
echo "[mech] 8C 的 val 扫描齐了（$n/$NCELLS 格）⇒ 开始机理读数 $(date '+%F %T')"

# ── 1. 重放台：11 格 rescue（零 GPU）────────────────────────────────────────
if [ "$RESCUE" = "1" ]; then
  for s in $(seq "$SAVE_FREQ" "$SAVE_FREQ" "$STEPS"); do
    d="$RUN/sweep_rev/step_${s}_rev"
    echo "[mech] === rescue step_${s} === $(date '+%T')"
    "$MG_PY" "$MG/code/mg_s9_rescue.py" --mode rescue --runs "$d" --out "$OUT/rescue" >> "$LOG" 2>&1 \
      || die "重放台在 $d 上非 0 退出（看 $LOG）"
  done
fi
"$MG_PY" "$MG/code/mg_s9_rescue.py" --mode report --indir "$OUT/rescue" --out-md "$OUT/rescue/REPORT.md" >> "$LOG" 2>&1 \
  || die "report 模式非 0 退出（看 $LOG）"

# ── 2. 保真格（末格）：重放台的**自检**——纯重放的放宽成功率必须与该格 eval_summary 逐字相同 ──
if [ "$FID" = "1" ]; then
  "$MG_PY" "$MG/code/mg_s9_rescue.py" --mode fidelity --runs "$RUN/sweep_rev/step_${STEPS}_rev" \
      --out "$OUT/fid" >> "$LOG" 2>&1 || die "fidelity 模式非 0 退出（看 $LOG）"
fi

# ── 3. 逐格对比（8C vs 对照臂）+ 保真自检 ⇒ COMPARE.md ────────────────────────
RUN="$RUN" CTL_RUN="$CTL_RUN" OUT="$OUT" BASE="$BASE" STEPS="$STEPS" SAVE_FREQ="$SAVE_FREQ" \
  TITLE="$TITLE" CTL_DESC="$CTL_DESC" CTL_DESC2="$CTL_DESC2" RULES_NOTE="$RULES_NOTE" TAGCOL="$TAG" \
  "$MG_PY" - >> "$LOG" 2>&1 <<'PY' || die "对比脚本非 0 退出（看 $LOG）"
import glob, json, os
RUN, CTL, OUT, BASE = os.environ["RUN"], os.environ["CTL_RUN"], os.environ["OUT"], os.environ["BASE"]
TITLE, CTL_DESC = os.environ["TITLE"], os.environ["CTL_DESC"]
CTL_DESC2, RULES_NOTE = os.environ["CTL_DESC2"], os.environ["RULES_NOTE"]
STEPS, SF = int(os.environ["STEPS"]), int(os.environ["SAVE_FREQ"])

def summ(run, s):
    p = f"{run}/sweep_rev/step_{s}_rev/eval_summary.json"
    if not os.path.isfile(p):
        return None
    j = json.load(open(p))
    return j

def bench(indir, s):
    hit = glob.glob(os.path.join(indir, f"*step_{s}_rev.json"))
    return json.load(open(hit[0])) if hit else None

L = []
A = L.append
BAD = {}
A(TITLE)
A("")
A("* 预注册出处：`runs/S8_PREREG.md` §9 **增补 11**（8D 的机理旁读沿用同一份口径，见 **增补 12**）；"
  "工具：`code/mg_s9_rescue.py`（重放台，不做一次策略推理）。")
A(CTL_DESC)
A(CTL_DESC2)
A("")
A(f"| step | 放宽成功率 {os.environ.get('TAGCOL', '8C')} | 对照臂 | Δ(pp) | 接管率 {os.environ.get('TAGCOL', '8C')} "
  f"| 对照臂 | TILT 占接管 {os.environ.get('TAGCOL', '8C')} | 对照臂 | A2 {os.environ.get('TAGCOL', '8C')} | 对照臂 |")
A("|--:|:--|:--|--:|:--|:--|:--|:--|:--|:--|")
tot = {"c": [0, 0], "b": [0, 0], "tkc": [0, 0], "tkb": [0, 0], "tiltc": 0, "tiltb": 0, "a2c": [0, 0], "a2b": [0, 0]}
pc = lambda k, n: "—" if not n else f"{100.0 * k / n:.1f}%"
for s in range(SF, STEPS + 1, SF):
    sc, sb = summ(RUN, s), summ(CTL, s)
    bc, bb = bench(f"{OUT}/rescue", s), bench(BASE, s)
    if not (sc and bc):
        A(f"| {s} | （缺产物） | | | | | | | | |")
        continue
    kc = sc.get("n_success_relaxed", -1); nc = sc.get("episodes", 0)
    kb = (sb or {}).get("n_success_relaxed", -1); nb = (sb or {}).get("episodes", 0)
    tkc, tkb = bc["takeover"], (bb or {"takeover": {"k": 0, "n": 0}})["takeover"]
    cc, cb = bc["state_class_counts"], (bb or {}).get("state_class_counts", {})
    a2c, a2b = bc["A2_relaxed_success_of_takeover"], (bb or {"A2_relaxed_success_of_takeover": {"k": 0, "n": 0}})["A2_relaxed_success_of_takeover"]
    d = f"{100.0 * (kc - kb) / max(1, nc):+.1f}" if (kc >= 0 and kb >= 0 and nc) else "—"
    A(f"| {s} | {kc}/{nc} = {pc(kc, nc)} | {kb}/{nb} = {pc(kb, nb)} | {d} | {tkc['k']}/{tkc['n']} = {pc(tkc['k'], tkc['n'])} "
      f"| {tkb['k']}/{tkb['n']} = {pc(tkb['k'], tkb['n'])} | {cc.get('TILT', 0)}/{tkc['k']} | {cb.get('TILT', 0)}/{tkb['k']} "
      f"| {a2c['k']}/{a2c['n']} = {pc(a2c['k'], a2c['n'])} | {a2b['k']}/{a2b['n']} = {pc(a2b['k'], a2b['n'])} |")
    tot["c"][0] += max(0, kc); tot["c"][1] += nc
    tot["b"][0] += max(0, kb); tot["b"][1] += nb
    tot["tkc"][0] += tkc["k"]; tot["tkc"][1] += tkc["n"]
    tot["tkb"][0] += tkb["k"]; tot["tkb"][1] += tkb["n"]
    tot["tiltc"] += cc.get("TILT", 0); tot["tiltb"] += cb.get("TILT", 0)
    tot["a2c"][0] += a2c["k"]; tot["a2c"][1] += a2c["n"]
    tot["a2b"][0] += a2b["k"]; tot["a2b"][1] += a2b["n"]
A(f"| **池化** | **{tot['c'][0]}/{tot['c'][1]} = {pc(*tot['c'])}** | **{tot['b'][0]}/{tot['b'][1]} = {pc(*tot['b'])}** "
  f"| {100.0 * tot['c'][0] / max(1, tot['c'][1]) - 100.0 * tot['b'][0] / max(1, tot['b'][1]):+.1f} "
  f"| {tot['tkc'][0]}/{tot['tkc'][1]} = {pc(*tot['tkc'])} | {tot['tkb'][0]}/{tot['tkb'][1]} = {pc(*tot['tkb'])} "
  f"| {tot['tiltc']}/{tot['tkc'][0]} | {tot['tiltb']}/{tot['tkb'][0]} "
  f"| {tot['a2c'][0]}/{tot['a2c'][1]} = {pc(*tot['a2c'])} | {tot['a2b'][0]}/{tot['a2b'][1]} = {pc(*tot['a2b'])} |")
A("")
# 保真自检：纯重放（检测器关掉）的放宽成功率必须与该格 eval_summary 逐字相同
fp = glob.glob(os.path.join(OUT, "fid", f"*step_{STEPS}_rev.json"))
if fp:
    fj = json.load(open(fp[0]))
    ss = summ(RUN, STEPS) or {}
    recs = [r for r in fj["per_episode"] if r["fid_ok"]]
    k_pr, n_pr = sum(1 for r in recs if r["success_relaxed"]), len(recs)
    k_es, n_es = ss.get("n_success_relaxed"), ss.get("episodes")
    same = (k_pr == k_es and n_pr == n_es)
    A("## 保真自检（末格 `step_%d`）%s" % (STEPS, "✅" if same else "🚨 **不过**"))
    A("")
    A(f"* 重放保真 `max|Δ|` = **{fj['fidelity']['max_over_all']:.3e}**（容差 {fj['fidelity']['tol']}）、"
      f"剔出 **{fj['fidelity']['n_bad']}/{fj['n_episodes']}** 局")
    A(f"* 纯重放（检测器关掉）的放宽成功 = **{k_pr}/{n_pr}**；同一格 `eval_summary.json` = "
      f"**{k_es}/{n_es}**（`pc_success_relaxed={ss.get('pc_success_relaxed')}`）⇒ {'逐字相同' if same else '🚨 **不同**'}")
    A("* ⚠️ 不同 ⇒ 语料/口径错了，**本文件全部读数作废**（重放台的三条外部对账见 `runs/_diag/s9_rescue/FINDINGS.md` §一）。")
    if not same:
        BAD["fid"] = f"保真自检不过：纯重放 {k_pr}/{n_pr} vs eval_summary {k_es}/{n_es}"
else:
    A("## 保真自检：未跑（`FID=0`）⇒ 本文件的读数**没有自检背书**，只当草稿看。")
    BAD["fid"] = "FID=0：没跑保真自检（冒烟口径）"
A("")
A("## 判读规则（增补 11 写死，**只解释、不判过不过**）")
A("")
A("* D1 ✅ ∧ 接管率↓ / TILT 占比↓ ⇒ 与 H8 的机理一致（纠正数据补上了「别把 can 弄乱」那一步）。")
A("* D1 ✅ ∧ 接管率与构成没变 ⇒ 抬升更可能来自「救球能力」⇒ 判定里标「机理未证」。")
A("* D1 ❌ ∧ TILT 占比没降 ⇒ **覆盖偏差**是第一个解释（增补 10 §2）；处方另立预注册。")
A("* D1 ❌ ∧ val 放宽成功率整体没动 ⇒ 是**剂量**不够（7000 帧 / 15% 占比），与教材内容无关。")
if RULES_NOTE:
    A("")
    A(RULES_NOTE)
A("")
open(os.path.join(OUT, "COMPARE.md"), "w").write("\n".join(L) + "\n")
print("[mech] 写出 %s（%d 行）" % (os.path.join(OUT, "COMPARE.md"), len(L)))
if BAD:
    print("[mech] 🚨 自检/口径问题：" + "；".join(BAD.values()))
    raise SystemExit(3)
PY

printf '%s %s 机理读数跑完（%d 格；对照臂=%s；产物=%s/COMPARE.md + rescue/REPORT.md；零 GPU、不是门）\n' \
  "$(date '+%F %T')" "$TAG" "$NCELLS" "$(basename "$CTL_RUN")" "$OUT" > "$MARK"
[ -s "$MARK" ] || die "done 标记写空了（坑 43 复发）"
echo "[mech] 收工 $(date '+%F %T')  标记 -> $MARK"
