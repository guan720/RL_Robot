#!/usr/bin/env bash
# 档 4x · K≥25 塌陷的**机理对照**（正向同任务、同 seed 窗口，唯一变量 = 模型）
#
# 预注册全文：runs/S4X_PREREG.md（**写死时间 2026-10-02 11:58，在本链发车之前**）。
# 判定规则不许在本脚本里改；本脚本只负责把 4 个读数干净地跑出来并核出身。
#
# 为什么值得花这 20 分钟 GPU：
#   档 4（正向）量到 K≤10 与 K≥25 之间一道 ~55 pp 的悬崖（80% -> 25%/30%）；
#   档 4r（反向，另一个模型）量同一条曲线，悬崖**不见了**（68.8% -> 50%/60%，Fisher 全不显著）。
#   两者差在三个变量上（任务方向 / 数据量 / 训练量），所以「反向不塌」说明不了任何事。
#   本档把任务方向、TEST seed 窗口、K、初态全部钉成一样，**只换模型**：
#     臂 A = pi05_rand60_s1/007200（60 条正向示范、7200 步）
#     臂 B = pi05_mix60f120r_s2e/022000（**同样那 60 条正向**，逐比特核过 + 120 条反向、22000 步）
#   ⇒ 回答档 4 留下的未答问题 3：「加数据/加训练量能不能把 K=50 抬起来」。
#
# 主指标不是成功率，而是 **A 类局数占比**（合爪瞬间抓空）：机理假说说的是
# 「K≥25 的塌陷主体是 A 类塌陷」，而 A 类恰好也是三臂剂量-反应里唯一显著变化的类
# （27->27->10，Fisher p=0.0024，见 runs/_diag/tax_relaxed_summary.md）。
#
# 🚫 本档**不改工作点**：K=10 仍是档 5 的设计点。挪部署点需要另立一档做非劣性检验。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
NOISE='robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation'
EP="${EP:-20}"
SEED=2000                       # 预注册：TEST seed 窗口 2000..2019
RUN_A="$MG/runs/pi05_rand60_s1";        STEP_A=7200
RUN_B="$MG/runs/pi05_mix60f120r_s2e";   STEP_B=22000
NPZ_A="$MG/data/rand60_raw.npz"          # 只用于动作分布对照，**不影响初态**
NPZ_B="$MG/data/mix60f120r_raw.npz"      # 与 NPZ_A 的正向部分逐比特相同（已核）
MARK="$MG/runs/s4x.done"
FAILED="$MG/runs/s4x.FAILED"
die () { echo "[s4x] FATAL $1" | tee -a "$FAILED"; printf '%s FATAL %s\n' "$(date +'%Y-%m-%d %H:%M:%S')" "$1" >> "$FAILED"; exit 4; }

# ── 0. 两个检查点都走**编号格**，并交叉核对 last 的指向（坑 38/42）──────────────
for pair in "A:$RUN_A:$STEP_A" "B:$RUN_B:$STEP_B"; do
  tag=${pair%%:*}; rest=${pair#*:}; run=${rest%%:*}; step=${rest#*:}
  want=$(printf "%06d" "$step")
  ck="$run/checkpoints/$want/pretrained_model"
  [ -f "$ck/model.safetensors" ] || die "臂 $tag 没有权重：$ck"
  rl=$(readlink "$run/checkpoints/last" 2>/dev/null || echo "")
  echo "[s4x] 臂 $tag 检查点 = $ck（交叉核对：last -> ${rl:-无}，期望 $want）"
  [ "$rl" = "$want" ] || die "臂 $tag 的 last 指向 ${rl:-无} 而不是 $want ⇒ 出身可疑（坑 38）"
done
[ -f "$NPZ_A" ] && [ -f "$NPZ_B" ] || die "缺正向示范 npz"
echo "[s4x] 两臂正向示范逐比特核对："
"$MG_PY" - "$NPZ_A" "$NPZ_B" <<'PY' || die "两臂的正向示范不是逐比特相同 ⇒ 对照不干净"
import hashlib, sys
import numpy as np
a, b = np.load(sys.argv[1]), np.load(sys.argv[2])
for k in ("action", "state", "episode_lengths", "seeds"):
    ha = hashlib.md5(np.ascontiguousarray(a[k]).tobytes()).hexdigest()
    hb = hashlib.md5(np.ascontiguousarray(b[k][:len(a[k])]).tobytes()).hexdigest()
    print("  [s4x]   %-16s rand60=%s  mix60f120r(前%d行)=%s  %s"
          % (k, ha[:12], len(a[k]), hb[:12], "逐比特相同" if ha == hb else "不同"))
    assert ha == hb, k
print("  [s4x]   ⇒ 臂 B 见到的正向示范与臂 A **完全相同**，唯一差别是 +120 条反向与 3× 训练量")
PY

wait_gpu () {
  local free
  for _ in $(seq 1 120); do
    free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
    [ "${free:-0}" -ge 9000 ] && return 0
    echo "[s4x] 显存 free=${free}MiB，等 15 s ... $(date +%H:%M:%S)"; sleep 15
  done
  echo "[s4x] 等了 30 min 显存还不够，硬上"; return 0
}

# $1=run $2=step $3=K $4=out $5=npz
run_eval () {
  local ck="$1/checkpoints/$(printf '%06d' "$2")/pretrained_model" out="$4"
  if [ -f "$MG/runs/$out/eval_summary.json" ]; then echo "[s4x] 跳过（已有产物）$out"; return 0; fi
  wait_gpu
  echo "[s4x] === 正向 K=$3 eps=$EP seed $SEED.. ckpt=$(basename "$(dirname "$(dirname "$ck")")") -> runs/$out === $(date +%H:%M:%S)"
  "$MG_PY" code/mg_eval.py --ckpt "$ck" --episodes "$EP" --seed-mode random --seed "$SEED" \
      --n-action-steps "$3" --task-mode forward --demo-npz "$5" \
      --out "$MG/runs/$out" 2>&1 | grep -vE "$NOISE" | grep -E "^  ep|成功率|放宽口径|Error|Traceback"
  [ -f "$MG/runs/$out/eval_summary.json" ] || die "评测没落盘：$out"
}

# ── 1. 四个新读数（历史读数不重跑，由判定脚本核出身后并入）───────────────────
run_eval "$RUN_A" "$STEP_A" 50 "s4x_fwdA007200_k50_rep2" "$NPZ_A"
run_eval "$RUN_B" "$STEP_B" 50 "s4x_fwdB022000_k50"      "$NPZ_B"
run_eval "$RUN_B" "$STEP_B" 50 "s4x_fwdB022000_k50_rep2" "$NPZ_B"
run_eval "$RUN_B" "$STEP_B" 25 "s4x_fwdB022000_k25"      "$NPZ_B"

# ── 2. 判定汇编 ─────────────────────────────────────────────────────────────
echo "[s4x] === 判定汇编 === $(date +%H:%M:%S)"
"$MG_PY" code/mg_verdict_s4x.py > "$MG/runs/S4X_VERDICT.md" 2>&1 || die "判定脚本非 0 退出"
tail -40 "$MG/runs/S4X_VERDICT.md"
# 坑 43：`date +"…%s…" 参数` 不是 printf，会写出**空标记**
printf '%s 档4x K>=25 机理对照完成 ep=%d seed=%d..%d arms=A007200,B022000 reads=4\n' \
       "$(date +'%Y-%m-%d %H:%M:%S')" "$EP" "$SEED" "$((SEED + EP - 1))" > "$MARK"
[ -s "$MARK" ] || die "标记写空了（$MARK）"
echo "[s4x] done $(date +%H:%M:%S)  标记 -> $MARK"
