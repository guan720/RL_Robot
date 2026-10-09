#!/usr/bin/env bash
# C 线全量回归：所有自检 + 真实帧 smoke + 交付包校验，一次跑完。
#
# 纪律：
#   - **CPU-only**（CUDA_VISIBLE_DEVICES=""）：C 不占卡。谁在用卡以 `nvidia-smi` 实测为准，
#     脚本注释里也**不断言他线状态**（裁定 29.4 附带更正 2 的口径同样适用于注释）；
#   - 单个脚本失败不中断，最后统一汇总（一轮回归要能看到全部红点，而不是只看到第一个）；
#   - 长跑用 setsid 起后台，别用 nohup（会被回收）。
#
# 退出码：0=全绿；1=有回归红点；2=**没有可用解释器**（环境缺失，不是回归失败）。
# 三种含义必须能一眼分开 —— 0929 检修把 `/root/venvs/rlrobot` 整个清掉过，
# 那时脚本钉死的默认解释器不存在，「跑不起来」长得像「回归全红」（增补六 §0.2 第 3 条）。
#
# 用法： setsid bash scripts/c_run_all_selfchecks.sh > /tmp/c_reg.log 2>&1 < /dev/null &
#       PY=/path/to/python bash scripts/c_run_all_selfchecks.sh   # 显式指定（仍会探测并如实报告）
set -u
cd "$(dirname "$0")/.."
export CUDA_VISIBLE_DEVICES="" MUJOCO_GL=egl OMP_NUM_THREADS=2

# --- 解释器：探测优先、失败即明确报错（增补六 §0.2 第 3 条）---
# 探测集 = 本轮自检脚本**并集**里需要的第三方模块。少一个都会让某个脚本以
# ImportError 收场，而那既不是绿也不是有意义的红，所以宁可在开跑前就拦下来。
PROBE_MODULES="numpy torch pandas pyarrow robosuite gymnasium py_trees mujoco stable_baselines3"
EXPLICIT_PY="${PY:-}"
PROBE_CANDIDATES=()
[[ -n "$EXPLICIT_PY" ]] && PROBE_CANDIDATES+=("$EXPLICIT_PY")   # 显式指定排第一
PROBE_CANDIDATES+=(/root/venvs/rlrobot/bin/python python3)

probe() {  # $1=解释器；stdout 打 OK 或 MISSING:<模块(异常类型)>，全齐返回 0
  "$1" - "$PROBE_MODULES" <<'PROBEPY'
import importlib, sys
missing = []
for name in sys.argv[1].split():
    try:
        importlib.import_module(name)
    except BaseException as exc:                              # noqa: BLE001
        missing.append("%s(%s)" % (name, type(exc).__name__))
print("MISSING:" + ",".join(missing) if missing else "OK")
sys.exit(1 if missing else 0)
PROBEPY
}

echo "=== 解释器探测（需要: $PROBE_MODULES）==="
PY=""
for cand in "${PROBE_CANDIDATES[@]}"; do
  if ! command -v "$cand" >/dev/null 2>&1; then
    echo "  跳过 $cand（不存在或不可执行）"
    continue
  fi
  out="$(probe "$cand" 2>&1)"; rc=$?
  echo "  探测 $cand -> ${out##*$'\n'}"
  if [[ $rc -eq 0 ]]; then PY="$cand"; break; fi
done

PARTIAL_ENV=0
if [[ -z "$PY" ]]; then
  if [[ -n "$EXPLICIT_PY" ]]; then
    # 显式覆盖仍然放行（增补六 §0.2 第 3 条给过的临时做法），但绝不静默：
    # 缺什么已经打印在上面，并在汇总里再声明一次「红点可能是环境缺失」。
    PY="$EXPLICIT_PY"
    PARTIAL_ENV=1
    echo "!! 显式指定的 PY=$PY 未通过依赖探测，仍按指定执行；"
    echo "!! 由此产生的红点**可能是环境缺失**而不是回归失败（SKIP≠PASS，见汇总声明）。"
  else
    echo "!! 没有可用解释器：候选 [${PROBE_CANDIDATES[*]}] 全部未通过探测。"
    echo "!! 这是环境问题，不是回归红点（exit=2）。处置："
    echo "!!   1) 按 requirements.lock.txt 重建 venv（本轮重建脚本/日志见 runs/infra/c_env_rebuild_20260929/）；"
    echo "!!   2) 或显式覆盖：PY=/path/to/python bash scripts/c_run_all_selfchecks.sh"
    exit 2
  fi
fi
echo "=== 使用解释器: $PY ($("$PY" -c 'import sys;print(sys.version.split()[0])' 2>/dev/null || echo '?')) ==="

SCRIPTS=(
  selfcheck_ledger_views
  selfcheck_obs_store
  selfcheck_release_bundle
  selfcheck_harness_contracts
  selfcheck_runtime_adapter
  selfcheck_stage3
  c_selfcheck_golden_conformance
  c_selfcheck_verdict_identity
  c_selfcheck_verdict_wiring
  c_run_manifest
  c_selfcheck_goal_conditioning_t17
  c_selfcheck_decisions_registry
  c_contract_lift_smoke
  c_contract_lift_takeover_smoke
  c_learner_shard_smoke
)

# 有的脚本**默认动作是产出真产物**而不是自检 ⇒ 在回归里必须显式要自检模式。
# 否则一次回归跑会顺手覆写权威产物，把「测试」和「发布」混成一件事
# （与 §8.4 里 `c_env_manifest --check` 写独立产物是同一条纪律）。
declare -A SCRIPT_ARGS=(
  [c_run_manifest]="--selftest"
)

declare -a RESULTS=()
for s in "${SCRIPTS[@]}"; do
  echo "=== $s ==="
  timeout 2400 "$PY" "scripts/$s.py" ${SCRIPT_ARGS[$s]:-}
  rc=$?
  RESULTS+=("$s exit=$rc")
  echo "exit=$rc"
done

echo "=== c_env_manifest --check（lock 一致性闸）==="
# 写**独立**产物，不覆写默认那份 `runs/infra/c_env_manifest_20260929.json`：
# 后者是 A 线 `a_env_readiness_gate.py` E6 五个 term 的取值来源（裁定 37.2 据它解封 A 线），
# 让一次回归跑就地换掉跨线消费的权威快照，是把「测试」和「发布」混成一件事。
# 要刷新权威快照请单独跑 `c_env_manifest.py`（它会自动归档上一版并带 previous_manifest/changed_fields，
# 裁定 37.4 第 2 条）。
timeout 900 "$PY" scripts/c_env_manifest.py --check \
  --json-out runs/infra/c_env_manifest_regression.json
rc=$?
RESULTS+=("c_env_manifest_check exit=$rc")
echo "exit=$rc"

echo "=== verify_package ==="
timeout 600 "$PY" RL_Harness_v4_20260924/tools/verify_package.py 2>&1 | grep -E '"ok"|"errors"'
RESULTS+=("verify_package exit=$?")

echo "=== 汇总 ==="
echo "  解释器: $PY"
fail=0
for r in "${RESULTS[@]}"; do
  echo "  $r"
  [[ "$r" == *"exit=0" ]] || fail=1
done
if [[ $PARTIAL_ENV -eq 1 ]]; then
  echo "环境不全（显式 PY 未通过依赖探测）：以上 exit!=0 的项**未被区分**是回归失败还是缺依赖，"
  echo "本次不构成一次可信的全量回归；补全环境后须重跑。"
fi
[[ $fail -eq 0 ]] && echo "全绿" || echo "有红点（见上）"
exit $fail
