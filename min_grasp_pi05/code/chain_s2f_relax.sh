#!/usr/bin/env bash
# 档 2f · 放宽口径复判链（用户 2026-10-02 授权：送到目标区为首要条件，侧躺/侧挡算送到但要打标）
#
# 为什么单开一档而不是改档 2c 的判定：
#   档 2c 的严格口径数值（37/80 = 46.2%，未过 50% 门）已经落盘、已经驱动了档 2e 发车。
#   事后放宽判据 = 事后改门，属于**口径变更**，纪律是：
#     (1) 历史严格数值一律不追改，两口径**并报**；
#     (2) 放宽口径必须重新测、重新算显著性，不许沿用严格口径的 p 值；
#     (3) 专家上界也要用**同一口径**重测 —— 否则分子放宽、分母还是严格的，比值没意义。
#
# 本链的四个阶段（前一阶段不过闸，后面不跑）：
#   A 专家上界（放宽口径）+ **严格口径逐局回归**：mg_ceiling.py 把噪声流钉死成 default_rng(12345)，
#     同参数重跑 = 逐比特相同轨迹 ⇒ 严格口径必须**逐局**复现 runs/s2_ceiling_rev_test20_n05(14/20)。
#     这是「我改判据没改坏历史口径」的唯一硬证据；差一局就 FATAL 停下（坑 30：出处必须可查）。
#   B mg_eval 双口径冒烟（反向 3 局 + 正向 2 局）：只验证字段齐、不变量 relaxed ⊇ strict 成立。
#   C 档 2c 单任务 @last(007600) 反向 TEST 4×20 —— **主读数**，与严格口径同 seed 窗口 7000..7019、同 K=10。
#   D 档 2  联合   @last(014400) 反向 TEST 4×20 —— 干扰问题的对照臂（同窗口同 K）。
#   E 修 sweep 的 last 误标（坑 38）：mg_sweep_rev.sh 在 s==STEPS_TOTAL 时用 checkpoints/last，
#     而 lerobot 的 last 是**每次 save 都更新的软链**，训练还没到 22000 时它已指向 020000
#     ⇒ sweep_rev/step_22000_rev 读的是 020000 的权重（实测同一份权重两次读 6/20 与 10/20）。
#     这里等真 022000 落盘后补一格，并把误标那格改名让路（改名后 glob("step_*") 不再匹配）。
#   F 判定汇编 -> runs/S2F_RELAX_VERDICT.md
#
# ⚠️ 本链**不改**档 2e 的任何东西：档 2e 的关门读数由 chain_s2e_train.sh 自己跑，
#    它用的 mg_eval.py 已经并行输出两种口径 ⇒ 档 2e 的放宽读数是**白捡的**，不需要重跑。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
NOISE='robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation'
MARK="$MG/runs/s2f_relax.done"
FAILED="$MG/runs/s2f_relax.FAILED"
CK_C="$MG/runs/pi05_rev60_s2c/checkpoints/last/pretrained_model"      # 档2c 单任务 -> 007600
CK_J="$MG/runs/pi05_mix60f60r_s2/checkpoints/last/pretrained_model"   # 档2  联合   -> 014400
NPZ_R="$MG/data/mix60f60r_rev_raw.npz"
NPZ_F="$MG/data/mix60f60r_raw.npz"
S2E_RUN="$MG/runs/pi05_mix60f120r_s2e"
MIN_FREE_MIB="${MIN_FREE_MIB:-9000}"
EP="${EP:-20}"

die () { echo "[s2f] FATAL $1" | tee -a "$FAILED"; date +"%Y-%m-%d %H:%M:%S FATAL $1" >> "$FAILED"; exit 4; }

wait_gpu () {
  local free
  for _ in $(seq 1 120); do
    free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
    [ "${free:-0}" -ge "$MIN_FREE_MIB" ] && return 0
    echo "[s2f] 显存 free=${free}MiB < ${MIN_FREE_MIB}MiB，等 15 s ... $(date +%H:%M:%S)"; sleep 15
  done
  echo "[s2f] 等了 30 min 显存还是不够，硬着头皮跑（评测 ~12 GB，A800 80 GB）"; return 0
}

eval_rev () {  # $1=ckpt $2=eps $3=seed $4=out $5=tag
  local out="$4"
  [ -f "$MG/runs/$out/eval_summary.json" ] && { echo "[s2f] 跳过（已有产物）$out"; return 0; }
  wait_gpu
  echo "[s2f] === $5 (reverse K=10 eps=$2 seed=$3) -> runs/$out === $(date +%H:%M:%S)"
  "$MG_PY" code/mg_eval.py --ckpt "$1" --episodes "$2" --seed-mode random --seed "$3" \
      --n-action-steps 10 --task-mode reverse --demo-npz "$NPZ_R" \
      --out "$MG/runs/$out" 2>&1 | grep -vE "$NOISE" | grep -E "^  ep|成功率|放宽口径|warn|Error|Traceback"
  [ -f "$MG/runs/$out/eval_summary.json" ] || die "评测没落盘：$out"
}

echo "[s2f] === 阶段 A：专家上界（放宽口径）+ 严格口径逐局回归 === $(date +%H:%M:%S)"
CEIL="$MG/runs/s2f_ceiling_rev_test20_n05"
if [ ! -f "$CEIL/ceiling_summary.json" ]; then
  "$MG_PY" code/mg_ceiling.py --task-mode reverse --episodes 20 --seed-mode random --seed 7000 \
      --noise 0.05 --out "$CEIL" 2>&1 | grep -vE "$NOISE" | grep -E "^  ep|专家上界|放宽口径"
fi
[ -f "$CEIL/ceiling_summary.json" ] || die "专家上界没落盘"
"$MG_PY" - "$CEIL/ceiling_summary.json" "$MG/runs/s2_ceiling_rev_test20_n05/ceiling_summary.json" <<'PY' || die "严格口径回归不通过（判据被改坏，本链所有放宽读数一律不可信）"
import json, sys
new, old = (json.load(open(p)) for p in sys.argv[1:3])
print("[s2f][回归] 出处 新=%s  旧=%s" % (sys.argv[1], sys.argv[2]))
bad = 0
assert len(new["per_episode"]) == len(old["per_episode"]), "局数不同"
for a, b in zip(new["per_episode"], old["per_episode"]):
    assert a["seed"] == b["seed"], "seed 顺序不同"
    same = (a["success"] == b["success"] and a["success_step"] == b["success_step"]
            and a["steps"] == b["steps"]
            and abs(a.get("final_tilt_deg", 0) - b.get("final_tilt_deg", 0)) < 1e-6
            and abs(a["min_dist_to_target_cm"] - b["min_dist_to_target_cm"]) < 1e-6)
    if not same:
        bad += 1
        print("[s2f][回归] MISMATCH seed=%s 新=%s 旧=%s" % (a["seed"], a, b))
print("[s2f][回归] 严格口径逐局比对：20 局中 %d 局不一致" % bad)
print("[s2f][回归] 严格 %d/%d（旧 %d/%d）  放宽 %d/%d  侧躺标记 %d 局"
      % (new["n_success"], new["episodes"], old["n_success"], old["episodes"],
         new["n_success_relaxed"], new["episodes"], new["n_delivered_tipped"]))
if new["n_success"] != old["n_success"] or bad:
    sys.exit(1)
if new["n_success_relaxed"] < new["n_success"]:
    print("[s2f][回归] 违背 严格 ⊆ 放宽"); sys.exit(1)
PY
echo "[s2f] 阶段 A 通过：判据改动**没有**动到严格口径（逐局逐比特一致）$(date +%H:%M:%S)"

echo "[s2f] === 阶段 B：mg_eval 双口径冒烟 === $(date +%H:%M:%S)"
eval_rev "$CK_C" 3 7000 _smoke/s2f_smoke_rev3 "冒烟 反向 3 局"
"$MG_PY" - "$MG/runs/_smoke/s2f_smoke_rev3/eval_summary.json" <<'PY' || die "冒烟不过：mg_eval 双口径字段有问题"
import json, sys
s = json.load(open(sys.argv[1]))
need = ["pc_success", "pc_success_relaxed", "n_success", "n_success_relaxed",
        "n_delivered_tipped", "n_ever_in_target_box", "criterion"]
miss = [k for k in need if k not in s]
print("[s2f][冒烟] 出处 %s" % sys.argv[1])
print("[s2f][冒烟] 缺字段 = %s" % (miss or "无"))
print("[s2f][冒烟] 严格 %d/%d  放宽 %d/%d  侧躺标记 %d  曾进框 %d"
      % (s["n_success"], s["episodes"], s["n_success_relaxed"], s["episodes"],
         s["n_delivered_tipped"], s["n_ever_in_target_box"]))
for e in s["per_episode"]:
    assert "success_relaxed" in e and "delivered_tipped" in e and "final_tilt_deg" in e, e
    assert e["success_relaxed"] or not e["success"], "违背 严格 ⊆ 放宽：%s" % e
if miss or s["n_success_relaxed"] < s["n_success"]:
    sys.exit(1)
PY
wait_gpu
echo "[s2f] === 冒烟 正向 2 局（回归：正向判据本来就不含倾角，两口径必须相同）=== $(date +%H:%M:%S)"
if [ ! -f "$MG/runs/_smoke/s2f_smoke_fwd2/eval_summary.json" ]; then
  "$MG_PY" code/mg_eval.py --ckpt "$CK_C" --episodes 2 --seed-mode random --seed 2000 \
      --n-action-steps 10 --task-mode forward --demo-npz "$NPZ_F" \
      --out "$MG/runs/_smoke/s2f_smoke_fwd2" 2>&1 | grep -vE "$NOISE" | grep -E "^  ep|成功率|Error|Traceback"
fi
"$MG_PY" - "$MG/runs/_smoke/s2f_smoke_fwd2/eval_summary.json" <<'PY' || die "正向回归不过"
import json, sys
s = json.load(open(sys.argv[1]))
print("[s2f][正向] 出处 %s  task_mode=%s env=%s" % (sys.argv[1], s["task_mode"], s["env_class"]))
print("[s2f][正向] 严格 %d/%d  放宽 %d/%d（正向无倾角项 ⇒ 必须相等）"
      % (s["n_success"], s["episodes"], s["n_success_relaxed"], s["episodes"]))
sys.exit(0 if s["n_success_relaxed"] == s["n_success"] else 1)
PY

echo "[s2f] === 阶段 C：档 2c 单任务 @last 反向 TEST 4×$EP（放宽口径主读数）=== $(date +%H:%M:%S)"
for i in "" _rep2 _rep3 _rep4; do
  eval_rev "$CK_C" "$EP" 7000 "s2f_relax_s2c_rev_test_rand20_k10$i" "档2c 单任务 @last$i"
done
echo "[s2f] === 阶段 D：档 2 联合 @last 反向 TEST 4×$EP（对照臂）=== $(date +%H:%M:%S)"
for i in "" _rep2 _rep3 _rep4; do
  eval_rev "$CK_J" "$EP" 7000 "s2f_relax_s2joint_rev_test_rand20_k10$i" "档2 联合 @last$i"
done

echo "[s2f] === 阶段 E：补 s2e 真 step22000 val 点（修坑 38）=== $(date +%H:%M:%S)"
STEPS_TOTAL="${STEPS_TOTAL:-22000}"
TRUE_DIR=$(printf "%s/checkpoints/%06d" "$S2E_RUN" "$STEPS_TOTAL")
for _ in $(seq 1 240); do
  [ "$(readlink "$S2E_RUN/checkpoints/last" 2>/dev/null)" = "$(basename "$TRUE_DIR")" ] \
    && [ -f "$TRUE_DIR/pretrained_model/model.safetensors" ] && break
  echo "[s2f] 等真 last -> $(basename "$TRUE_DIR")（当前 $(readlink "$S2E_RUN/checkpoints/last" 2>/dev/null)）... $(date +%H:%M:%S)"
  sleep 60
done
[ -f "$TRUE_DIR/pretrained_model/model.safetensors" ] || { echo "[s2f] 真 022000 一直没落盘，跳过阶段 E"; }
if [ -f "$TRUE_DIR/pretrained_model/model.safetensors" ]; then
  # 等 chain_s2e_train.sh 把 val 选点消费完（它会读 sweep_rev，包含那格误标），再动目录
  for _ in $(seq 1 120); do [ -f "$S2E_RUN/ckpt_selection.json" ] && break; sleep 60; done
  BOGUS="$S2E_RUN/sweep_rev/step_${STEPS_TOTAL}_rev"
  if [ -d "$BOGUS" ] && [ ! -f "$BOGUS/.mislabel_moved" ]; then
    trash="$S2E_RUN/sweep_rev/_trash_step_${STEPS_TOTAL}_rev_MISLABEL_020000weights_$(date +%Y%m%d_%H%M%S)"
    echo "[s2f] 误标格 $BOGUS（读的是 020000 权重）-> 改名让路：$(basename "$trash")"
    mv "$BOGUS" "$trash" && touch "$trash/.mislabel_moved"
  fi
  if [ ! -f "$BOGUS/eval_summary.json" ]; then
    wait_gpu
    echo "[s2f] 补测真 step $STEPS_TOTAL 的反向 val（20 局）=== $(date +%H:%M:%S)"
    "$MG_PY" code/mg_eval.py --ckpt "$TRUE_DIR/pretrained_model" --episodes 20 --seed-mode random \
        --seed 8000 --n-action-steps 10 --task-mode reverse --demo-npz "$MG/data/mix60f120r_rev_raw.npz" \
        --out "$BOGUS" 2>&1 | grep -vE "$NOISE" | grep -E "^  ep|成功率|放宽口径"
  fi
fi

echo "[s2f] === 阶段 F：判定汇编 === $(date +%H:%M:%S)"
"$MG_PY" code/mg_verdict_s2f.py > "$MG/runs/S2F_RELAX_VERDICT.md" 2>&1
tail -40 "$MG/runs/S2F_RELAX_VERDICT.md"
# 坑 43：`date +"…%s…" 参数` **不是 printf**，多余参数会让 date 报 extra operand 并写出**空标记**
printf '%s 档2f 放宽口径复判完成 ceiling=%s s2c=4x%d s2joint=4x%d\n' \
       "$(date +'%Y-%m-%d %H:%M:%S')" "$CEIL" "$EP" "$EP" > "$MARK"
[ -s "$MARK" ] || die "标记写空了（$MARK）⇒ 下游按 -f 判存在会误以为收工"
echo "[s2f] done $(date +%H:%M:%S)  标记 -> $MARK"
