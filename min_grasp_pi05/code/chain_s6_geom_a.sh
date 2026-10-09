#!/usr/bin/env bash
# 档 6 · 格 6A：A 类失败（can 从没离地）的几何定位 —— **离线**，零 GPU 训练占用
#
# 预注册：runs/S6_GEOM_PREREG.md（2026-10-03 12:07 先落盘，坑 40）
# 回答的唯一问题：A 类是「合爪那一刻横向偏差超过物理指隙」还是「臂根本没走到 can 附近」？
#   两者处方相反：前者 = 数据侧修法（收紧专家 XY_TOL → 重采示范 → 重训 ~10 h）；
#                 后者 = 收紧专家判据无用（示范本来就对准了），瓶颈在接近段/视觉。
#
# 工具复用 code/mg_diag_miss.py（不新写口径：口径一变结论就变，该工具头注释原话）。
# ⚠️ 必须给 --demo-npz（反向示范）：不给的话工具会退回正向硬编码 GRASP_Z_DEMO=0.880，
#    它自己会打警告说「反向 H2 判定不可信」（code/mg_diag_miss.py:159-163）。
#
# 发车闸（看盘上产物）：三个 seed 各 4 rep 的 rollout npz + eval_summary 都在；反向示范 npz 在。
# 房规：setsid 发车（坑 37）；done 标记 printf 写 + `[ -s ]` 自检（坑 43）；路径全绝对（坑 41）。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"
DEMO="$MG/data/mix60f120r_rev_raw.npz"
MARK="$MG/runs/s6_geom_a.done"
die () { echo "[s6a] FATAL $*" >&2; exit 4; }

[ -f "$DEMO" ] || die "反向示范 npz 不在：$DEMO"
declare -A REPS=(
  [1000]="s2e_rev_test_rand20_k10 s2e_rev_test_rand20_k10_rep2 s2e_rev_test_rand20_k10_rep3 s2e_rev_test_rand20_k10_rep4"
  [2000]="s3r_seed2000_rev_test_rand20_k10 s3r_seed2000_rev_test_rand20_k10_rep2 s3r_seed2000_rev_test_rand20_k10_rep3 s3r_seed2000_rev_test_rand20_k10_rep4"
  [3000]="s3r_seed3000_rev_test_rand20_k10 s3r_seed3000_rev_test_rand20_k10_rep2 s3r_seed3000_rev_test_rand20_k10_rep3 s3r_seed3000_rev_test_rand20_k10_rep4"
)
for s in 1000 2000 3000; do
  for d in ${REPS[$s]}; do
    [ -f "$MG/runs/$d/eval_summary.json" ] || die "缺 $d/eval_summary.json"
    [ -f "$MG/runs/$d/rollout_actions.npz" ] || die "缺 $d/rollout_actions.npz（6A 全靠它，没 state 就没几何）"
  done
done
echo "[s6a] 发车闸全过 $(date '+%F %T')"

for s in 1000 2000 3000; do
  out="$MG/runs/_diag/miss_s3r_seed${s}_rev.json"
  log="$MG/logs/s6_geom_a_seed${s}.log"
  args=""
  for d in ${REPS[$s]}; do args="$args $MG/runs/$d"; done
  echo "[s6a] === seed$s 几何定位（4 rep × 20 = 80 局）=== $(date '+%F %T')"
  # shellcheck disable=SC2086
  "$MG_PY" "$MG/code/mg_diag_miss.py" $args --demo-npz "$DEMO" --out "$out" > "$log" 2>&1
  rc=$?
  echo "[s6a] seed$s rc=$rc  $(date '+%F %T')  日志 -> $log"
  [ "$rc" -eq 0 ] || die "mg_diag_miss.py 退出码 $rc（seed$s，看 $log）"
  [ -s "$out" ] || die "6A 产物写空了：$out"
done

printf '%s 档6 格6A 完成 tool=mg_diag_miss.py 产物=runs/_diag/miss_s3r_seed{1000,2000,3000}_rev.json 预注册=runs/S6_GEOM_PREREG.md 判据=不改门只定机理归属\n' \
  "$(date '+%F %T')" > "$MARK"
[ -s "$MARK" ] || die "done 标记写空了（坑 43 复发）"
echo "[s6a] done $(date '+%F %T')  标记 -> $MARK"
