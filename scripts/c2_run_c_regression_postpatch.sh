#!/usr/bin/env bash
# C2 · 打完 T-C2-2 补丁后复核 **C 线 17 项全量回归**（裁定 49.2 要求 2：不许破坏 ACT 线基线）。
#
# 【2026-09-29 22:4x 根因修复】本驱动的上一版（sha256-12 `60aff102c836`）在 21:42:43–21:44:16
# **覆写了 `runs/infra/` 顶层 16 个 C 线产物**（裁定 68 §10.2，程序违规记一次）：它只把
# `c_env_manifest.py --check` 一处改指到 C2 目录，其余自检脚本把结果写在**自己源码里的固定路径**。
# 按纪律 `regression_driver_output_enumeration`（§10.3）：必须**枚举**、不许"挑一个最显眼的改掉"。
# ⇒ 现在全程走 `scripts/c2_driver_output_guard.py` 三段式守卫：
#     enumerate（从被调脚本源码枚举全部固定路径输出；枚举为空则拒绝开工 exit 3）
#   → snapshot（逐个留 before 影像 + sha256-12）
#   → 跑 17 项
#   → restore（新字节收进本线证据目录、before 影像写回原路径并校验 sha256-12；
#              声明过但原先不存在的新产出被搬进证据目录；**枚举漏项 ⇒ 未申报写入 ⇒ RED**）
#   守卫自检 4/4（1 基线 + 3 变异体）：`runs/infra/c2_driver_output_guard_20260929/selftest.json`。
#
# 为什么不直接跑 `scripts/c_run_all_selfchecks.sh`：
#   那个脚本把 `c_env_manifest.py --check` 的结果**写死**到
#   `runs/infra/c_env_manifest_regression.json`（现存文件 mtime 2026-09-29 17:50、1158100 B，
#   是 C 冻结期的产物）。C 线已冻结，C2 不覆盖别人的产物 ⇒ 本驱动把该项的
#   `--json-out` 指到 **C2 自己的产物目录**，其余 16 项与 C 的脚本**逐字同参**。
#
# 清单不手抄：直接从 C 的脚本里解析 `SCRIPTS=(...)` 数组，避免两份清单分叉。
#
# 退出码：0=17/17 exit=0；1=有红点；2=没有可用解释器。
set -u
cd "$(dirname "$0")/.."
export CUDA_VISIBLE_DEVICES="" MUJOCO_GL=egl OMP_NUM_THREADS=2

PY="${PY:-/root/venvs/rlrobot/bin/python}"
OUT="${OUT:-runs/vla/c2_obs_key_whitelist_20260929/c_regression_postpatch_guarded}"
# 注意：`--root` 是**子命令级**参数（共享父 parser），必须放在子命令之后
GUARD="$PY $PWD/scripts/c2_driver_output_guard.py"
mkdir -p "$OUT"
command -v "$PY" >/dev/null 2>&1 || { echo "!! 解释器不存在: $PY"; exit 2; }

echo "=== 解释器: $PY ($("$PY" -c 'import sys;print(sys.version.split()[0])')) ==="
echo "=== 输出目录: $OUT ==="
echo "=== 被复核的补丁 ==="
sha256sum harness/queue_td_learner.py harness/obs_key_coverage.py | cut -c1-12,35-

echo "=== 守卫 1/3：枚举被调脚本的全部固定路径输出（不许挑） ==="
mkdir -p "$OUT/guard"
$GUARD enumerate --root "$PWD" --run-all "$PWD/scripts/c_run_all_selfchecks.sh" \
  --extra-script c_env_manifest --out "$OUT/guard/declared.json" || { echo "!! 枚举为空/失败 ⇒ 拒绝开工"; exit 3; }
echo "=== 守卫 2/3：快照 before 影像 ==="
$GUARD snapshot --root "$PWD" --declared "$OUT/guard/declared.json" --before "$OUT/guard/before" \
  --out "$OUT/guard/snapshot.json" || { echo "!! 快照失败 ⇒ 拒绝开工"; exit 3; }

# 从 C 的脚本解析清单（不手抄）
mapfile -t SCRIPTS < <(sed -n '/^SCRIPTS=(/,/^)/p' scripts/c_run_all_selfchecks.sh \
  | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' | grep -E '^[A-Za-z0-9_]+$')
echo "=== 解析到 ${#SCRIPTS[@]} 个自检脚本: ${SCRIPTS[*]} ==="

declare -A RESULTS=()
fail=0
for s in "${SCRIPTS[@]}"; do
  args=""
  [[ "$s" == "c_run_manifest" ]] && args="--selftest"     # 与 C 的 SCRIPT_ARGS 一致
  echo "=== $s $args ==="
  timeout 2400 "$PY" "scripts/$s.py" $args > "$OUT/$s.log" 2>&1
  rc=$?
  RESULTS["$s"]=$rc
  echo "  exit=$rc (log: $OUT/$s.log)"
  [[ $rc -eq 0 ]] || fail=1
done

echo "=== c_env_manifest --check（输出改指 C2 目录，不覆盖 C 的冻结产物）==="
timeout 900 "$PY" scripts/c_env_manifest.py --check \
  --json-out "$OUT/c_env_manifest_regression.json" > "$OUT/c_env_manifest_check.log" 2>&1
rc=$?; RESULTS["c_env_manifest_check"]=$rc; echo "  exit=$rc"
[[ $rc -eq 0 ]] || fail=1

echo "=== verify_package ==="
timeout 600 "$PY" RL_Harness_v4_20260924/tools/verify_package.py > "$OUT/verify_package.log" 2>&1
rc=$?; RESULTS["verify_package"]=$rc
grep -E '"ok"|"errors"' "$OUT/verify_package.log" | head -3
echo "  exit=$rc"
[[ $rc -eq 0 ]] || fail=1

echo "=== 守卫 3/3：复原别人的产物 + 未申报写入检测 ==="
$GUARD restore --root "$PWD" --snapshot "$OUT/guard/snapshot.json" --evidence "$OUT/guard/new_bytes" \
  --out "$OUT/guard/restore.json" --scan-root runs/infra --maxdepth 2
guard_rc=$?
echo "  guard exit=$guard_rc"

echo "=== 汇总（共 ${#RESULTS[@]} 项）==="
n_ok=0
for k in "${!RESULTS[@]}"; do
  echo "  $k exit=${RESULTS[$k]}"
  [[ "${RESULTS[$k]}" == "0" ]] && n_ok=$((n_ok+1))
done
echo "  => $n_ok/${#RESULTS[@]} exit=0"
{
  echo "generated_at=$(date -Iseconds)"
  echo "interpreter=$PY"
  echo "n_items=${#RESULTS[@]}"
  echo "n_exit0=$n_ok"
  echo "guard_exit=$guard_rc"
  echo "guard_verdict=$(python3 -c "import json;print(json.load(open('$OUT/guard/restore.json'))['verdict'])" 2>/dev/null)"
  echo "guard_n_restored=$(python3 -c "import json;print(json.load(open('$OUT/guard/restore.json'))['n_restored'])" 2>/dev/null)"
  echo "guard_n_undeclared=$(python3 -c "import json;print(len(json.load(open('$OUT/guard/restore.json'))['undeclared_writes']))" 2>/dev/null)"
  for k in "${!RESULTS[@]}"; do echo "item=$k exit=${RESULTS[$k]}"; done
} > "$OUT/summary.txt"
if [[ $fail -eq 0 && $guard_rc -eq 0 ]]; then echo "全绿（回归 + 守卫）"; exit 0; fi
echo "有红点：回归 fail=$fail 守卫 guard_rc=$guard_rc（见上）"
[[ $fail -ne 0 ]] && exit $fail
exit $guard_rc
