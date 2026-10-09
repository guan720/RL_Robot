#!/usr/bin/env bash
# 建官方 LeRobot ACT 训练环境（独立 venv，与 /root/venvs/rlrobot 完全隔离）。
#
# 为什么必须重来一遍，而不是继续修 runs/infra/lerobot_official_env：
#   1. 那个环境是 `--system-site-packages` 建的，会把 /opt/conda 的 TensorFlow + jax 拖进
#      import 链。jax 与 numpy 版本对不上（`np.dtypes.StringDType` AttributeError），
#      transformers 的惰性导入就报成 `cannot import name 'PreTrainedModel'`——看着像
#      transformers 装坏，其实是系统包污染。09-24 的 ImportError 链条根因在此。
#   2. 它复用系统 torchvision 0.19.1+cu124，不满足 lerobot 0.4.4 声明的
#      torchvision>=0.21.0,<0.26.0，属于「不被官方支持的运行时」。
#
# 本机实测的两个坑（2026-09-28）：
#   - pip 走代理下载大 wheel 只有 ~0.7 MB/s，同一条 URL 用 curl/uv 是 ~40 MB/s。
#     所以这里用 uv 装，不用 pip 装大包。
#   - pip.conf 里 `find-links = mirrors.aliyun.com/pytorch-wheels/cu124/` 会把 torch 解析成
#     `+cu124` 本地版本并从那个慢源拉；`index-url = mirrors.ustc.edu.cn` 的文件下载会 302
#     到 mirrors.tuna.tsinghua.edu.cn，对我们返回 403。uv 不读 pip.conf，显式指定 aliyun
#     PyPI 索引即可绕开两者。
#
# 用法： bash scripts/install_lerobot_act_env.sh
set -euo pipefail

VENV="${VENV:-/root/venvs/lerobot_act}"
BASE_PY="${BASE_PY:-/opt/conda/bin/python3.11}"
INDEX="${INDEX:-https://mirrors.aliyun.com/pypi/simple}"
TORCH="${TORCH:-2.6.0}"
TORCHVISION="${TORCHVISION:-0.21.0}"
LEROBOT="${LEROBOT:-0.4.4}"
# 以下两个 pin 源于 A 的提请（docs/a_handoff_to_b_anchor_shift_20260929.md §2）+ **D 裁定 34.1 第 4 条**。
# 0928 -> 0929 重建出现 3 处 lock 差异，根因是**两处未钉版本**在浮动：
#   · `imageio` 本体没钉（评测环境那条安装列表只钉了 `imageio-ffmpeg==0.6.0`）⇒ 解析器取镜像当时的最新；
#   · `uv` 那行是裸 `pip install -q --index-url "$INDEX" uv`（"[2/7] 装 uv" 那一步）⇒ 同样取当时最新可得。
#   （这里故意**不写行号**：本文件一改行号就移，D 裁定 §5 要求引用改内容锚。）
# **根因纪律：镜像内容会动 ⇒ 未钉版本 = 每次重建都漂移。** 钉住它们，下次重建才逐字节可复现
# （裁定 32.4 的溯源保护要能长期成立，前提是重建本身可复现）。
#
# 取值口径 = **「实际装成并跑通门槛验证」的那个值**（裁定 32.2「lock 是事实源、范围 pin 是意图」同型），
# **不是**回退到 0928 的值 —— 回退等于按意图改事实，而且要重装只读 venv（裁定 34.1 第 3 条已否决重装）。
#   IMAGEIO=2.38.0：A 0929 重建两份 lock 实测 `ImageIO==2.38.0`
#     （runs/infra/a_lerobot_env_rebuild_20260929/requirements.lock.txt:35 与 requirements.eval.lock.txt:38）；
#     lerobot 0.4.4 声明 imageio[ffmpeg]>=2.34.0,<3.0.0 ⇒ 2.38.0 合规；
#     B 实测 mirrors.aliyun.com/pypi/simple/imageio/ 上 2.38.0 **在**（wheel + sdist 各 1）。
#     0928 基线是 2.37.4 ⇒ 这处差异 D 已按裁定 34.1 **放行**（豁免按包按链路授：不在 48 臂链路上，
#     官方 ACT 三件套与 summarize_lerobot_act_arms.py 都不 import imageio）。
#     **裁定 37.3 的边界（引用 34.1 必须带）**：豁免只覆盖**本仓链路**（C 用每模块一个子进程回显 sys.modules
#     实测，8 个脚本 hit=[]，A 静态 grep / C 运行时 / D 复核三方一致）；**上游 lerobot.scripts.lerobot_train
#     的 import 闭包里确有 imageio（18 个子模块）⇒ 凡用上游 lerobot_train 实跑的训练/评测不在豁免内**，
#     要么另证不材料、要么重新报 D，且今后真跑须回显 imageio 生效版本。
#     详见 docs/lerobot_env_reinstall_pin_20260929.md §7.8（不写行号：本文件一改行号就移）。
#   UV=0.12.17：A 0929 重建实测 `uv==0.12.17`（同上 requirements.lock.txt:102，仅 act 侧有）；
#     B 实测 aliyun 的 uv 简单索引（316 个版本）里 **0.12.17 在、0.12.18/0.12.19/0.12.20 都不在**
#     ⇒ 钉 0928 的 0.12.19 会让下次重建**直接装不上**。这正是 A 的 0929 重建拿到 0.12.17 的原因。
#     `uv` 只是安装期工具（A 实测全仓无 `import uv`），但它**进了 lock** ⇒
#     「用什么工具装的」这个事实也属可复现性，所以照样钉，不按「工具不重要」豁免。
#     **已报 D 并结案**：0928 lock 的 `uv==0.12.19` 在当前权威 index 上不可复现，裁定 34.1 放行。
#     要装别的版本就显式 `UV=<ver>` 覆写，并自备一个可达且有该版本的 index。
IMAGEIO="${IMAGEIO:-2.38.0}"
UV="${UV:-0.12.17}"
LOCK_OUT="${LOCK_OUT:-$(cd "$(dirname "$0")/.." && pwd)/runs/infra/lerobot_act_env_20260928}"

echo "[1/7] 建干净 venv（不带 --system-site-packages）: $VENV"
[[ -d "$VENV" ]] && { echo "  已存在，跳过创建（要重建请先把它 mv 到回收站，本项目禁止 rm）"; } \
  || "$BASE_PY" -m venv "$VENV"

echo "[2/7] 装 uv（小包，走 pip 也很快）"
"$VENV/bin/pip" install -q --index-url "$INDEX" "uv==$UV"
"$VENV/bin/uv" --version | sed 's/^/  uv 实装：/'

echo "[3/7] 用 uv 装 torch/torchvision + lerobot 全套依赖"
export UV_HTTP_TIMEOUT=180
export UV_CONCURRENT_DOWNLOADS=8
"$VENV/bin/uv" pip install --python "$VENV/bin/python" --index-url "$INDEX" \
  "torch==$TORCH" "torchvision==$TORCHVISION"
"$VENV/bin/uv" pip install --python "$VENV/bin/python" --index-url "$INDEX" \
  "lerobot==$LEROBOT" "imageio==$IMAGEIO"

echo "[4/7] 门槛验证（两条命令都必须过）"
"$VENV/bin/python" -c "from lerobot.policies.act.configuration_act import ACTConfig; from lerobot.policies.act.modeling_act import ACTPolicy; print('  GATE act-import: OK')"
"$VENV/bin/python" -m lerobot.scripts.lerobot_train --help > /dev/null && echo "  GATE lerobot_train --help: OK"
"$VENV/bin/python" - <<'PY'
import torch, torchvision, lerobot, numpy
print(f"  lerobot={lerobot.__version__} torch={torch.__version__} torchvision={torchvision.__version__} numpy={numpy.__version__}")
print(f"  cuda_available={torch.cuda.is_available()} device={torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu'}")
assert torch.cuda.is_available(), "GPU 不可用，先查驱动 / CUDA_VISIBLE_DEVICES"
PY

echo "[5/7] 写版本锁: $LOCK_OUT/requirements.lock.txt"
mkdir -p "$LOCK_OUT"
"$VENV/bin/pip" freeze > "$LOCK_OUT/requirements.lock.txt"

# ---------------------------------------------------------------------------
# 评测环境：官方 ACT 推理 + robosuite 真值评测必须在同一个解释器里，否则
# checkpoint 要跨环境搬。它和训练环境分开建，避免污染上面已验证过的那一套。
#
# 这里有一个真实的依赖冲突：robosuite 1.5.2 -> mink 0.0.5 -> numpy<2.0.0，
# 而本项目继承的口径是 numpy 2.4.6（mink 的 pin 是陈旧的，实测能跑）。
# uv/pip 的正常解析会直接判 unsatisfiable，所以用 --override 强制 numpy。
# 只有评测环境需要这么做；训练环境不装 robosuite，保持干净。
# ---------------------------------------------------------------------------
EVAL_VENV="${EVAL_VENV:-/root/venvs/lerobot_eval}"
if [[ "${BUILD_EVAL_ENV:-1}" == "1" ]]; then
  echo "[6/7] 建评测环境（lerobot + robosuite 同解释器）: $EVAL_VENV"
  [[ -d "$EVAL_VENV" ]] || "$BASE_PY" -m venv "$EVAL_VENV"
  printf 'numpy==2.4.6\n' > /tmp/uv_overrides_lerobot_eval.txt
  "$VENV/bin/uv" pip install --python "$EVAL_VENV/bin/python" --index-url "$INDEX" \
    --override /tmp/uv_overrides_lerobot_eval.txt \
    "torch==$TORCH" "torchvision==$TORCHVISION" "lerobot==$LEROBOT" \
    "numpy==2.4.6" "gymnasium==1.2.3" "mujoco==3.9.0" "robosuite==1.5.2" "numba==0.67.0" \
    "opencv-python==4.10.0.84" "py_trees==2.6.0" "imageio-ffmpeg==0.6.0" \
    "imageio==$IMAGEIO"
  "$EVAL_VENV/bin/python" - <<'PY'
import numpy, torch, lerobot, gymnasium, mujoco, robosuite
from lerobot.policies.act.modeling_act import ACTPolicy
print(f"  EVAL_ENV numpy={numpy.__version__} torch={torch.__version__} lerobot={lerobot.__version__} "
      f"gymnasium={gymnasium.__version__} mujoco={mujoco.__version__} robosuite={robosuite.__version__} "
      f"cuda={torch.cuda.is_available()}")
PY
  "$EVAL_VENV/bin/pip" freeze > "$LOCK_OUT/requirements.eval.lock.txt"
  echo "  评测环境版本锁: $LOCK_OUT/requirements.eval.lock.txt"
else
  echo "[6/7] 跳过评测环境（BUILD_EVAL_ENV=0）"
fi

echo "[7/7] 完成。训练/评测入口示例见 docs/lerobot_act_env_setup_20260928.md"
