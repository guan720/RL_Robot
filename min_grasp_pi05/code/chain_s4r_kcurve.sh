#!/usr/bin/env bash
# 档 4r · 反向任务的 chunk 执行扫描（用户阶梯第 4 步在反向侧的补做）
#
# 正向档 4 已经量过：K=1 85% ≈ K=10 80% ≫ K=25 25% ≈ K=50 30%，结论是「K=10 是唯一
# 又准又实时的点」（K=1 超实时预算 6.5 倍，不可部署）。反向到现在只在 K=10 上读过数
# （档 2e 严格 52.5% / 放宽 68.8%），**不知道反向是不是同一条 K 曲线**。
# 这一档就补 K ∈ {1, 25, 50}，检查点、数据集、TEST seed 窗口、局数全部沿用档 2e。
#
# 检查点 = 档 2e 的 `last`（022000），即当前反向最强的那一个。不重训、不换数据 ⇒ 唯一变量是 K。
#
# 预注册判读（跑前写死）：
#   * K=10 是**工作点**（已有 4×20 = 80 局，不重跑）；本档只回答「离开 K=10 会怎样」。
#   * 若 K=25/50 相对 K=10 掉 ≥20 pp ⇒ 与正向同一条曲线，开环 chunk 执行不行，档 5 Harness
#     必须按 K=10 的实时预算设计（50 ms/step，见坑 36：K<10 不是实时的，别想用调 K 修 A 类）。
#   * 若 K=1 明显高于 K=10 ⇒ 反向也吃「纠偏密度」，但 K=1 不可部署（正向实测超预算 6.5 倍），
#     只能记为「能力上限参考」，不改工作点。
#   * 两口径都报：主口径 = 放宽 R，严格并列。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
NOISE='robosuite|Remapped|WARNING:root|^The PI05|^This implementation|^Original implementation'
RUN="${RUN:-$MG/runs/pi05_mix60f120r_s2e}"
CK="$RUN/checkpoints/last/pretrained_model"
WANT="${WANT:-022000}"
NPZ_R="$MG/data/mix60f120r_rev_raw.npz"
EP="${EP:-20}"
KS="${KS:-1 25 50}"
MARK="$MG/runs/s4r.done"
FAILED="$MG/runs/s4r.FAILED"
die () { echo "[s4r] FATAL $1" | tee -a "$FAILED"; exit 4; }

# 坑 38：`last` 是每次 save 都重指的软链，用之前必须核对它指向终点格
rl=$(readlink "$RUN/checkpoints/last" 2>/dev/null || echo "")
echo "[s4r] 检查点 $CK（last -> ${rl:-无}，期望 $WANT）"
[ "$rl" = "$WANT" ] || die "last 指向 ${rl:-无} 而不是 $WANT ⇒ 会读错权重（坑 38）"
[ -f "$CK/model.safetensors" ] || die "没有权重文件：$CK"

for K in $KS; do
  out="s4r_rev_test_rand20_k${K}"
  if [ -f "$MG/runs/$out/eval_summary.json" ]; then echo "[s4r] 跳过（已有产物）$out"; continue; fi
  for _ in $(seq 1 120); do
    free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
    [ "${free:-0}" -ge 9000 ] && break
    echo "[s4r] 显存 free=${free}MiB，等 15 s ... $(date +%H:%M:%S)"; sleep 15
  done
  echo "[s4r] === 反向 TEST K=$K eps=$EP seed 7000.. -> runs/$out === $(date +%H:%M:%S)"
  "$MG_PY" code/mg_eval.py --ckpt "$CK" --episodes "$EP" --seed-mode random --seed 7000 \
      --n-action-steps "$K" --task-mode reverse --demo-npz "$NPZ_R" \
      --out "$MG/runs/$out" 2>&1 | grep -vE "$NOISE" | grep -E "^  ep|成功率|放宽口径|Error|Traceback"
  [ -f "$MG/runs/$out/eval_summary.json" ] || die "评测没落盘：$out"
done

echo "[s4r] === 判定汇编 === $(date +%H:%M:%S)"
"$MG_PY" code/mg_verdict_s4r.py > "$MG/runs/S4R_VERDICT.md" 2>&1
tail -30 "$MG/runs/S4R_VERDICT.md"
# 坑 43：`date +"…%s…" 参数` **不是 printf**，多余参数会让 date 报 extra operand 并写出**空标记**
printf '%s 档4r 反向 K 曲线完成 K=%s ckpt=%s\n' \
       "$(date +'%Y-%m-%d %H:%M:%S')" "$(echo "$KS" | tr ' ' ',')" "$WANT" > "$MARK"
[ -s "$MARK" ] || die "标记写空了（$MARK）⇒ 下游按 -f 判存在会误以为收工"
echo "[s4r] done $(date +%H:%M:%S)  标记 -> $MARK"
