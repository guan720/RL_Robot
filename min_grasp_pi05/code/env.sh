# 最小抓取链路 · 环境激活（source 本文件，或用 `bash -c 'source code/env.sh && python ...'`）
# 设计约束：只用本目录 + 只读的公共基础设施（NFS 上的 EGL 驱动库、已校验的 π₀.₅ 权重硬链接）。
# 不 source 仓内其它线的脚本，不 export 它们的变量。

export MG_ROOT="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
export MG_PY="/root/mg_venvs/min_grasp/bin/python"

# ---- GPU 离屏渲染（robosuite 相机观测必须；库文件来自 NFS 只读前缀）----
EGL_PREFIX="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist/egl-libs/590.48.01"
export LD_LIBRARY_PATH="${EGL_PREFIX}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export __EGL_VENDOR_LIBRARY_FILENAMES="${EGL_PREFIX}/10_nvidia.json"
unset __EGL_VENDOR_LIBRARY_DIRS
export MUJOCO_GL=egl
export PYOPENGL_PLATFORM=egl

# ---- 模型权重全部走本地（离线），杜绝训练中途联网卡死 ----
export HF_HOME="${MG_ROOT}/weights/hf-cache"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export HF_ENDPOINT=https://hf-mirror.com

# ---- 线程数：单卡单进程，避免 OMP 抢核拖慢仿真 ----
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export TOKENIZERS_PARALLELISM=false

# ---- PATH：本 venv 优先（lerobot-train / pip 都用它，绝不落到共享 venv）----
export PATH="/root/mg_venvs/min_grasp/bin:$PATH"
