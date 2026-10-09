#!/usr/bin/env bash
# RoboRSI + LIBERO-PRO 最小可跑安装（本机实测通过，2026-09-22）。
#
# 为什么不用官方的 `pip install -e ".[libero]"` 或 `scripts/reproduce_libero_pro.sh`：
#   1) RoboRSI 核心依赖里有 `lerobot[feetech,dynamixel,pi]`，它要求 torch>=2.7,<2.12，
#      会把解析器拖去下载 torch 2.11.0 的 CUDA 轮子（530 MB + 一堆 nvidia-* 依赖，
#      本机镜像只有 ~300 KB/s，等于几小时），而 LIBERO 的 configure/doctor 根本不需要 lerobot。
#   2) 本机没有 GPU 渲染栈（见 docs/infra-gpu-render.md），CUDA 版 torch 也用不上。
#   所以这里只装「CLI 导入链 + LIBERO 后端」真正需要的东西，跳过 lerobot / flexivrdk /
#   record3d / 各家 IM SDK。代价：`roborsi task`、pi0 微调那些技能不可用（本来本机也跑不了）。
#
# 用法：
#   bash scripts/install_roborsi_minimal.sh              # 全流程（约 20-40 分钟，取决于镜像速度）
#   ROOT=/data/roborsi WS=/path/in/workspace ENV_NAME=roborsi bash scripts/install_roborsi_minimal.sh
#
# 目录布局原则（实测依据见 docs/roborsi-trial-log.md 第 6 节）：
#   · 被 Python import 的东西放本地盘 $ROOT：conda 环境（65618 文件）、RoboRSI 源码、LIBERO-PRO 检出。
#     工作区所在的 /workspace/mnt/sppro 是 NFS，小文件 stat 慢 2083 倍、写慢 453 倍；
#     环境放上去光写入约 2 小时，且每条 CLI 命令都会慢一个数量级。
#   · 配置 / 产物 / 资产 / 日志放工作区 $WS。
#
# 幂等：每一步都先检查已有状态，可以重复执行续跑。
set -uo pipefail

ROOT="${ROOT:-/root/roborsi_trial}"          # 本地盘：代码树（必须本地，理由见上）
WS="${WS:-/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/roborsi_runtime}"  # 工作区：配置/资产/日志
RHOME="${WS}/home"                           # $RHOME/.roborsi 存 config.json / trace.db / evals
ENV_NAME="${ENV_NAME:-roborsi}"
PY_VER="${PY_VER:-3.12}"                      # RoboRSI requires-python >= 3.12
TORCH_WHL="${TORCH_WHL:-https://mirrors.aliyun.com/pytorch-wheels/cpu/torch-2.6.0%2Bcpu-cp312-cp312-linux_x86_64.whl}"
CONDA_ENV="/opt/conda/envs/${ENV_NAME}"
PIP="${CONDA_ENV}/bin/pip"
PY="${CONDA_ENV}/bin/python"
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
export LITELLM_LOCAL_MODEL_COST_MAP=True      # 否则每次 CLI 都会去 raw.githubusercontent.com 拉价格表，超时 3 次约 20s

echo "### [1/7] conda 环境 ${ENV_NAME} (python ${PY_VER})"
[ -x "${PY}" ] || conda create -n "${ENV_NAME}" "python=${PY_VER}" -y >/dev/null
"${PY}" -V

echo "### [2/7] RoboRSI 源码 -> ${ROOT}/RoboRSI"
mkdir -p "${ROOT}"
if [ ! -d "${ROOT}/RoboRSI" ]; then
  git clone -q --depth 1 https://github.com/nssmd/RoboRSI.git "${ROOT}/RoboRSI"
fi
( cd "${ROOT}/RoboRSI" && echo "    commit: $(git log -1 --format='%h %ad %s' --date=short)" )

echo "### [3/7] torch (CPU 轮子，约 178 MB)"
"${PY}" -c "import torch" 2>/dev/null || "${PIP}" install -q "${TORCH_WHL}"
"${PY}" -c "import torch;print('    torch', torch.__version__)"

echo "### [4/7] 安装 roborsi 本体（--no-deps，绕开 lerobot 的 torch 约束）"
( cd "${ROOT}/RoboRSI" && "${PIP}" install -q -e . --no-deps )

echo "### [5/7] LIBERO extra + CLI 导入链依赖"
"${PIP}" install -q \
  "bddl==1.0.1" "cloudpickle>=2.1,<4.0" "easydict>=1.9,<2.0" "future>=0.18.2" \
  "gym==0.25.2" "h5py>=3.8,<4.0" "imageio>=2.36,<3.0" "imageio-ffmpeg>=0.5,<1.0" \
  "matplotlib>=3.5,<4.0" "msgpack-numpy>=0.4.8,<1.0" "mujoco==3.3.0" "numpy>=1.26,<2.3" \
  "opencv-python>=4.10,<5.0" "pillow>=10,<13" "pyzmq>=26,<28" "pyyaml>=6.0,<7.0" \
  "robosuite==1.4.0" "scikit-learn>=1.5,<2.0" "scipy>=1.11,<2.0" "termcolor>=2.4,<4.0" \
  "transformers>=4.57,<6.0" \
  "typer>=0.20" "rich>=14" "pydantic>=2.12,<3" "pydantic-settings>=2.12,<3" \
  "loguru>=0.7.3" "httpx>=0.28" "openai>=2.8" "litellm>=1.82.1,<2" "mcp>=1.26,<2" \
  websockets websocket-client ddgs oauth-cli-kit croniter prompt-toolkit json-repair chardet \
  tiktoken msgpack socksio python-socketio readability-lxml 2>&1 | tail -3

echo "### [6/7] LIBERO-PRO 代码（本地盘） + LIBERO-Pro 资产（工作区）"
[ -d "${ROOT}/LIBERO-PRO" ] || git clone -q --depth 1 https://github.com/Zxy-MLlab/LIBERO-PRO.git "${ROOT}/LIBERO-PRO"
DEST="${WS}/LIBERO-PRO-assets"
mkdir -p "${DEST}" "${WS}/logs" "${RHOME}"
# 注意：hf-mirror 会 429 限流，而 `hf download` 被限流时**仍然返回 0** 并打印
# "Returning existing local_dir ... cannot be accessed"。所以只能按"文件是否下全"判断，不能看退出码。
for attempt in $(seq 1 15); do
  "${CONDA_ENV}/bin/hf" download zhouxueyang/LIBERO-Pro --repo-type dataset \
      --local-dir "${DEST}" --max-workers 1 > "/tmp/hf_dl_${attempt}.log" 2>&1 || true
  limited=$(grep -c 'cannot be accessed' "/tmp/hf_dl_${attempt}.log" || true)
  ninit=$(find "${DEST}/init_files" -type f 2>/dev/null | wc -l)
  echo "    attempt=${attempt} rate_limited=${limited} init_files=${ninit} total=$(find "${DEST}" -type f | wc -l)"
  [ "${limited}" = "0" ] && [ "${ninit}" -gt 200 ] && break
  sleep $((30 + attempt * 15))
done

echo "### [7/7] configure + doctor（HOME 指向工作区，配置与产物都落 WS）"
# 用 env 前缀覆盖 HOME，只在单条命令作用域内生效。不要把 export HOME 写进当前 shell，
# 否则 pip / conda / hf 的缓存会被写到 NFS 上，既慢又占配额。
ROB() {
  HOME="${RHOME}" ROBORSI_HOME="${RHOME}/.roborsi" ROBORSI_EVALS_ROOT="${RHOME}/.roborsi/evals" \
  LITELLM_LOCAL_MODEL_COST_MAP=True MUJOCO_GL="${MUJOCO_GL:-osmesa}" \
  "${CONDA_ENV}/bin/roborsi" "$@"
}
ROB onboard < /dev/null > /dev/null 2>&1 || true
ROB libero configure \
  --root "${ROOT}/LIBERO-PRO" \
  --bddldir "${DEST}/bddl_files" \
  --initdir "${DEST}/init_files" --json
echo "    --- doctor（osmesa，约 2-3 分钟）---"
ROB libero doctor --backend libero --task libero_object/0 --reset --json 2>/dev/null \
  | "${PY}" -c "import sys,json;s=sys.stdin.read();d=json.loads(s[s.find('{'):]);print('   importable=%s backend=%s tasks=%s reset=%s'%(d['importable'],d['backend']['available'],d['task_count'],d.get('reset',{}).get('ok')))"
echo "### INSTALL_DONE"
echo "    本地盘（代码 + 环境）: ${CONDA_ENV} , ${ROOT}"
echo "    工作区（配置 + 资产）: ${WS}"
echo "    日常入口: source ${WS}/env.sh"
