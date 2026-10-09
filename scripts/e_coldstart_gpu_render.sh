#!/usr/bin/env bash
# T-E-EGL-COLDSTART ①（裁定 85.9-3-1，P0）：**一条命令的冷启动自检 + 自恢复**。
#
# 为什么要有它（裁定 85.9-2）：现在所有「egl 可用」的结论都建立在**当前这个 shell 会话的环境**上。
# 重启后必然丢的三样东西，恰好是这套方案能工作的全部前提：
#   (a) `LD_LIBRARY_PATH` / `__EGL_VENDOR_LIBRARY_FILENAMES` / `MUJOCO_GL` —— **进程环境**，重启后为空；
#   (b) `/root/venvs/pi05_sim` —— **符号链接**，在 overlay 临时层，重启后消失（NFS 上的 venv 本体还在）；
#   (c) `~/.bashrc` 里的 codex-persist hook —— 也在临时层 ⇒ **重启后没有任何东西会自动恢复**（见 §4 的链路核实）。
# 而库本体（`.codex-persist/egl-libs/590.48.01/`）与 venv 本体（`.codex-persist/envs/`）**在 NFS 上，不丢**。
# ⇒ 恢复是**机械的**，本脚本把它做成一条命令，并且**恢复失败时响亮地失败**。
#
# 用法（这一行就是全部；`env -i` = 不继承任何环境，等价于重启后的新 shell）：
#   env -i /bin/bash /workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/scripts/e_coldstart_gpu_render.sh
#
# 四步，任一步失败 ⇒ **exit ≠ 0**（绝不静默退回 CPU 软渲染）：
#   C1 链路前提：NFS 上的库本体 + venv 本体 + base 解释器都在
#   C2 重建 `/root/venvs/<name>` 符号链接（缺失才建；已存在则校验指向）
#   C3 `eval "$(bash scripts/e_activate_gpu_render.sh --print)"`（裁定 70 的唯一合法激活方式）
#   C4 在**独立子进程**里实测 `GL_RENDERER` 并断言含 `NVIDIA`（裁定 82.5：绝不与被测 env 同进程）
#
# 退出码（**`exit 0` 是唯一一个可以被读作「GPU 渲染可用」的码** —— 裁定 89.5-1 之后 exit code 就是权威判据）：
#   0  = C1–C4 全过，C4 **实测** `GL_RENDERER` 含 NVIDIA ⇒ 可以采集标 `egl` 的数字
#   1  = 任一环节失败（`e_fail`）。若来自 C4，stderr 会把内部自证件的 1/2/3 三种原因分开说
#   5  = **`E_SKIP_GPU=1`：只跑了 C1–C3，GPU 渲染未被测量** ⇒ **不是通过**，一个标 `egl` 的数字都不要采。
#        与 `scripts/e_egl_coldstart.py` 顶层的 `PARTIAL` 档同号（同一种语义用同一个码）。
#        **为什么不能是 0**（本轮实测到的真缺陷）：把"没验"报成 exit 0 = 在**退出码这一维**上的假绿，
#        与裁定 87.1-2 `partial_delivery_must_not_carry_a_whole_delivery_boolean` 同型；
#        文案里的免责声明救不了只看 `$?` 的调用方（编排/CI/`&&` 链）。
# 硬边界：只读 NFS 前缀、只写 `/root/venvs/<name>` 这一个符号链接与 `--out-dir`。
#   **不写 /usr/lib、/usr/share、/etc；不 ldconfig；不 apt/dpkg；不改 NVIDIA_DRIVER_CAPABILITIES。**
set -uo pipefail

# `env -i` 下 PATH/HOME 都是空的 ⇒ 本脚本自带环境，不依赖调用者给的任何东西。
export PATH="/opt/conda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export HOME="${HOME:-/root}"
export LC_ALL=C

E_SELF="${BASH_SOURCE[0]:-$0}"
E_REPO_ROOT="$(cd "$(dirname "$E_SELF")/.." && pwd)"
E_PERSIST="${E_PERSIST:-/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist}"
E_VENV_NAME="${E_VENV_NAME:-pi05_sim}"                 # 主线解释器（gym_aloha + mujoco 3.8.1）
E_VENV_LINK="${E_VENV_LINK:-/root/venvs/$E_VENV_NAME}" # 临时层里的那一环，重启后会丢
E_VENV_BODY="$E_PERSIST/envs/$E_VENV_NAME"             # NFS 上的本体，重启后还在
E_BASE_PY="${E_BASE_PY:-/opt/conda/bin/python3.11}"    # venv 的 base 解释器（**镜像层**，不是 NFS）
E_OUT_DIR="${E_OUT_DIR:-$E_REPO_ROOT/runs/infra/e_egl_coldstart_$(date +%Y%m%d)}"
E_SKIP_GPU="${E_SKIP_GPU:-0}"                          # 1 = 只做 C1–C3（不占卡，用于无窗口时的链路自检）
# 前缀**只有一个真源**：C1 检查的目录必须与 C3 激活件解析到的目录是同一个，否则会出现
# "C1 查了 A 目录、C3 用了 B 目录"的漂移（裁定 46.4 的根因就是两处定义漂移）。
# `E_GPU_RENDER_PREFIX` 是激活件自己认的覆盖变量 ⇒ 这里显式导出，让 C1/C3 共用它。
# 变异臂（裁定 85.9-3-3 的牙）就是靠它把前缀换成**沙箱副本**而不碰真前缀。
E_PREFIX_DIR="${E_GPU_RENDER_PREFIX:-$E_PERSIST/egl-libs/590.48.01}"
export E_GPU_RENDER_PREFIX="$E_PREFIX_DIR"

e_fail() { echo "[coldstart] FAIL: $*" >&2; exit 1; }
e_note() { echo "[coldstart] $*" >&2; }

mkdir -p "$E_OUT_DIR" 2>/dev/null || true

# ── C1 链路前提（纯 CPU，不占卡）────────────────────────────────────────────
e_note "C1 链路前提检查"
[ -d "$E_PERSIST" ]                       || e_fail "持久盘不存在: $E_PERSIST（NFS 未挂载？这一步不成立后面全不成立）"
[ -d "$E_PREFIX_DIR" ]                    || e_fail "EGL 前缀目录不存在: $E_PREFIX_DIR"
[ -f "$E_PREFIX_DIR/libEGL_nvidia.so.0" ] || e_fail "EGL 库本体缺失: $E_PREFIX_DIR/libEGL_nvidia.so.0"
[ -f "$E_PREFIX_DIR/10_nvidia.json" ]     || e_fail "vendor ICD 缺失: $E_PREFIX_DIR/10_nvidia.json"
[ -d "$E_VENV_BODY" ]                     || e_fail "venv 本体缺失（NFS）: $E_VENV_BODY"
[ -x "$E_VENV_BODY/bin/python" ]          || e_fail "venv 本体不可执行: $E_VENV_BODY/bin/python"
# 这一环 D 没点名，但它是真的会断：NFS 上的 venv 只是个壳，它的 bin/python3.11 是**指向镜像层**的符号链接。
# 镜像换了（python 版本变）⇒ venv 本体在 NFS 上也照样是死的。所以必须实测 base 解释器能跑。
[ -e "$E_BASE_PY" ]                       || e_fail "base 解释器缺失（镜像层，非 NFS）: $E_BASE_PY"
"$E_VENV_BODY/bin/python" -c 'import sys; sys.exit(0)' 2>/dev/null \
  || e_fail "venv 解释器跑不起来（base 解释器 ABI 变了？）: $E_VENV_BODY/bin/python"
e_note "C1 ok: 前缀（$E_PREFIX_DIR）+ venv 本体 + base 解释器（$E_BASE_PY）都在"

# ── C2 重建符号链接（幂等；只碰 /root/venvs 下这一个链接）───────────────────
e_note "C2 venv 符号链接: $E_VENV_LINK"
if [ -L "$E_VENV_LINK" ]; then
  got="$(readlink "$E_VENV_LINK")"
  [ "$got" = "$E_VENV_BODY" ] || e_fail "符号链接指向不对: $E_VENV_LINK -> $got（期望 $E_VENV_BODY）"
  e_note "C2 ok: 已存在且指向正确（未改动）"
elif [ -e "$E_VENV_LINK" ]; then
  # 是真实目录而不是软链 ⇒ 本脚本不删任何东西（纪律：不 rm）
  e_fail "$E_VENV_LINK 是**真实目录**不是软链；本脚本不删它。请人工 mv 到 /workspace/mnt/sppro/yhzhang91/recycle_bin/ 后重跑"
else
  mkdir -p "$(dirname "$E_VENV_LINK")" || e_fail "无法创建 $(dirname "$E_VENV_LINK")"
  ln -s "$E_VENV_BODY" "$E_VENV_LINK"  || e_fail "无法创建符号链接 $E_VENV_LINK -> $E_VENV_BODY"
  [ -x "$E_VENV_LINK/bin/python" ]     || e_fail "符号链接建好了但解释器不可用: $E_VENV_LINK/bin/python"
  e_note "C2 ok: **已重建** $E_VENV_LINK -> $E_VENV_BODY（这正是重启后会丢的那一环）"
fi
E_PY="$E_VENV_LINK/bin/python"

# ── C3 激活（裁定 70：唯一合法方式 = eval 激活件的 --print，不硬编码目录名）──
e_note "C3 激活 GPU 渲染后端"
E_EXPORTS="$(bash "$E_REPO_ROOT/scripts/e_activate_gpu_render.sh" --print)" \
  || e_fail "激活件 --print 失败（前缀解析不到？见 C1）"
[ -n "$E_EXPORTS" ] || e_fail "激活件 --print 输出为空"
eval "$E_EXPORTS"
e_note "C3 ok: MUJOCO_GL=${MUJOCO_GL:-<unset>} ICD=${__EGL_VENDOR_LIBRARY_FILENAMES:-<unset>}"
e_note "C3     LD_LIBRARY_PATH=${LD_LIBRARY_PATH:-<unset>}"

if [ "$E_SKIP_GPU" = "1" ]; then
  e_note "E_SKIP_GPU=1 ⇒ 跳过 C4（不占卡）。**注意：这不是冷启动验证通过**，只证明 C1–C3 链路完好。"
  echo "COLDSTART_PARTIAL_OK c1_c2_c3（未实测 GL_RENDERER，不构成裁定 85.9-3-1 的交付）"
  # **exit 5，不是 0**：exit code 现在是权威判据（裁定 89.5-1），"没测"必须在一个只读 `$?` 的
  # 调用方眼里也是"没测"。0 会被 `&&` 链、编排器与 CI 当成"可用"⇒ 退出码层面的假绿。
  e_note "exit 5 = PARTIAL（C1–C3 完好、GPU 未测量）。**不要**在此状态下采集任何标 egl 的数字。"
  exit 5
fi

# ── C4 实测断言（秒级 GPU 探针；判据复用激活件自证件，不另写一套 = 裁定 46.4）─
e_note "C4 实测 GL_RENDERER（独立子进程，$E_PY）"
E_MODE="${E_MODE:-egl_nvidia}" E_OUT_DIR="$E_OUT_DIR" E_REPO_ROOT="$E_REPO_ROOT" \
  bash "$E_REPO_ROOT/scripts/e_activate_gpu_render.sh" --selfcheck --python "$E_PY" --out-dir "$E_OUT_DIR" \
  > "$E_OUT_DIR/coldstart_selfcheck_stdout.json" 2> "$E_OUT_DIR/coldstart_selfcheck_stderr.txt"
rc=$?
e_note "C4 自证件 exit=$rc（stdout 落在 $E_OUT_DIR/coldstart_selfcheck_stdout.json）"
# 三种响亮失败**分开说**（三种都不许采数，但处置完全不同）。不分开的后果是实测到的：
# 02:18:54 那一轮 GPU 明明是好的（GL_RENDERER=NVIDIA A800、400 帧渲出、image_mean 75.73），
# 却因为采样窗为空而报 exit=1 ⇒ 运维会拿着一个假红去查一块好卡，而本脚本自己的文案是
# 「不要采集任何标 egl 的数字」⇒ 整条主线被一个测量缺陷卡死。
#   rc=2 invalid_measurement：采样窗没覆盖渲染子进程 ⇒ L5/L5b/S2 读到的是「没采到」不是「测到没有」⇒ **重跑一次即可**
#   rc=1 fail：真没判成 NVIDIA GPU（库缺失 / 版本错配 / EGL 起不来 / 静默退回 CPU 软渲染）⇒ **查驱动与前缀**
#   rc=3 refused：边界闸拒跑（系统目录里出现 NVIDIA 渲染库 / vendor ICD，裁定 60）⇒ **先回滚**
if [ "$rc" -eq 2 ]; then
  e_fail "冷启动自检**测量无效**（exit=2, invalid_measurement）：本轮没采到渲染子进程的 GPU 归因证据（fd / 整机占用）。GPU **既没被证明坏、也没被证明好** ⇒ 请**把本命令重跑一次**；若仍为 2，再按 exit=1 处置。在此之前**不要**采集任何标 egl 的数字。"
elif [ "$rc" -eq 3 ]; then
  e_fail "冷启动自检**被边界闸拒绝**（exit=3）：系统目录里出现了 NVIDIA 渲染库 / vendor ICD（裁定 60 / D 执行单 §3.2）。先用 scripts/e_install_nvidia_gl_590.sh --uninstall 回滚（**需 D 批准**）再重跑。**不要**采集任何标 egl 的数字。"
elif [ "$rc" -ne 0 ]; then
  e_fail "冷启动自检**未通过**（exit=$rc）。**不要**在此状态下采集任何标 egl 的数字 —— 它可能已经静默退回 CPU 软渲染（92.374 ms/步 会被当成 7.300 ms/步）。详见 stderr 与产物。"
fi

echo "COLDSTART_OK venv=$E_PY MUJOCO_GL=${MUJOCO_GL:-} prefix_icd=${__EGL_VENDOR_LIBRARY_FILENAMES:-}"
exit 0
