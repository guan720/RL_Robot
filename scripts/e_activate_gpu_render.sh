#!/usr/bin/env bash
# E 线 E3-1：GPU 渲染的**可复现激活件**（prefix-only，裁定 59 / 60）。
#
# 用法（三选一）：
#   source scripts/e_activate_gpu_render.sh              # 在当前 shell 里激活 GPU 渲染后端
#   source scripts/e_activate_gpu_render.sh --mode cpu   # 对照臂：osmesa（CPU 软渲染，不注入 NVIDIA ICD）
#   bash   scripts/e_activate_gpu_render.sh --print      # 只打印 export 行，不改当前 shell（给子进程用）
#   bash   scripts/e_activate_gpu_render.sh --selfcheck  # 自证：GL_RENDERER 含 NVIDIA + 子进程持有 /dev/nvidia* fd
#
# 硬边界（D 执行单 §3.2 / §8.2，裁定 60）：本脚本**只导出环境变量**。
#   不写 /usr/lib、/usr/share、/etc；不 ldconfig；不 apt/dpkg；不改 NVIDIA_DRIVER_CAPABILITIES。
#   库文件只从 NFS 前缀目录读取（容器重启不丢，系统临时层的改动不会存活）。
#   `--selfcheck` 会**先核系统目录是否干净**，脏则拒跑（exit 3），边界靠代码不靠自觉。
set -uo pipefail

E_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
E_PERSIST="${E_PERSIST:-/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist}"
E_MODE="egl_nvidia"
E_SELFCHECK_PY="${E_SELFCHECK_PY:-/root/venvs/rlrobot/bin/python}"
E_OUT_DIR="${E_OUT_DIR:-$E_REPO_ROOT/runs/infra/e_activate_selfcheck_20260929}"

while [ $# -gt 0 ]; do
  case "$1" in
    --mode)      E_MODE="${2:-}"; shift 2 ;;
    --python)    E_SELFCHECK_PY="${2:-}"; shift 2 ;;
    --out-dir)   E_OUT_DIR="${2:-}"; shift 2 ;;
    --print)     E_MODE_PRINT=1; shift ;;
    --selfcheck) E_MODE_SELFCHECK=1; shift ;;
    -h|--help)   sed -n '2,20p' "${BASH_SOURCE[0]:-$0}"; return 0 2>/dev/null || exit 0 ;;
    *) echo "[e_activate] 未知参数: $1" >&2; return 2 2>/dev/null || exit 2 ;;
  esac
done

# ── 前缀目录解析（按优先级；两个候选名都支持，因为 D §8.3-1 与 E §1 写入面用了不同目录名）──
e_resolve_prefix() {
  local c
  for c in \
      "${E_GPU_RENDER_PREFIX:-}" \
      "$E_PERSIST/egl-libs/590.48.01" \
      "$E_PERSIST/nvidia-gl-590.48.01" \
      "$E_PERSIST/nvidia-gl-590.48.01/root/usr/lib/x86_64-linux-gnu" ; do
    [ -z "$c" ] && continue
    if [ -f "$c/libEGL_nvidia.so.0" ]; then echo "$c"; return 0; fi
  done
  return 1
}

E_PREFIX="$(e_resolve_prefix)" || {
  echo "[e_activate] 找不到含 libEGL_nvidia.so.0 的前缀目录（试过 E_GPU_RENDER_PREFIX / $E_PERSIST/egl-libs/590.48.01 / $E_PERSIST/nvidia-gl-590.48.01）" >&2
  return 4 2>/dev/null || exit 4
}

# vendor ICD：前缀自带的 10_nvidia.json（绝对路径指向前缀），没有就退到 _src 解包里的相对路径版
E_VENDOR_ICD="$E_PREFIX/10_nvidia.json"
[ -f "$E_VENDOR_ICD" ] || E_VENDOR_ICD="$E_PERSIST/egl-libs/_src_590.48.01/root/usr/share/glvnd/egl_vendor.d/10_nvidia.json"
E_VULKAN_ICD="$E_PREFIX/nvidia_icd_vulkan.json"

e_emit_exports() {
  case "$E_MODE" in
    egl_nvidia)
      echo "export LD_LIBRARY_PATH=\"$E_PREFIX\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}\""
      echo "export __EGL_VENDOR_LIBRARY_FILENAMES=\"$E_VENDOR_ICD\""
      echo "unset __EGL_VENDOR_LIBRARY_DIRS"
      echo "export MUJOCO_GL=egl"
      echo "export PYOPENGL_PLATFORM=egl"
      [ -f "$E_VULKAN_ICD" ] && echo "export VK_ICD_FILENAMES=\"$E_VULKAN_ICD\""
      ;;
    mesa_egl)   # 变异臂：库在 LD_LIBRARY_PATH 上，但 ICD 指回 Mesa ⇒ 必须回到 llvmpipe
      echo "export LD_LIBRARY_PATH=\"$E_PREFIX\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}\""
      echo "export __EGL_VENDOR_LIBRARY_FILENAMES=\"/usr/share/glvnd/egl_vendor.d/50_mesa.json\""
      echo "unset __EGL_VENDOR_LIBRARY_DIRS"
      echo "export MUJOCO_GL=egl"
      echo "export PYOPENGL_PLATFORM=egl"
      ;;
    cpu|osmesa) # 对照臂：不注入任何 NVIDIA 库，走 CPU 软渲染（裁定 59：osmesa 装了库也永远走 CPU）
      echo "export MUJOCO_GL=osmesa"
      echo "export PYOPENGL_PLATFORM=osmesa"
      echo "unset __EGL_VENDOR_LIBRARY_FILENAMES"
      echo "unset __EGL_VENDOR_LIBRARY_DIRS"
      ;;
    *) echo "[e_activate] --mode 只支持 egl_nvidia|mesa_egl|cpu（收到 '$E_MODE'）" >&2; return 2 ;;
  esac
}

if [ "${E_MODE_PRINT:-0}" = "1" ]; then
  e_emit_exports
  return 0 2>/dev/null || exit 0
fi

if [ "${E_MODE_SELFCHECK:-0}" = "1" ]; then
  mkdir -p "$E_OUT_DIR"
  eval "$(e_emit_exports)"          # 只作用于本 bash 进程，不写任何系统路径
  E_PREFIX="$E_PREFIX" E_VENDOR_ICD="$E_VENDOR_ICD" E_MODE="$E_MODE" \
  E_OUT_DIR="$E_OUT_DIR" E_REPO_ROOT="$E_REPO_ROOT" \
  "$E_SELFCHECK_PY" "$E_REPO_ROOT/scripts/e_activate_selfcheck.py"
  exit $?
fi

if [ -n "${BASH_SOURCE[0]:-}" ] && [ "${BASH_SOURCE[0]}" != "$0" ]; then
  eval "$(e_emit_exports)"
  echo "[e_activate] mode=$E_MODE prefix=$E_PREFIX"
  echo "[e_activate] MUJOCO_GL=$MUJOCO_GL __EGL_VENDOR_LIBRARY_FILENAMES=${__EGL_VENDOR_LIBRARY_FILENAMES:-<unset>}"
  echo "[e_activate] 自证：bash scripts/e_activate_gpu_render.sh --selfcheck"
else
  # 直接执行（非 source）：给出可 eval 的文本，避免"看起来生效其实没有"
  echo "[e_activate] 本脚本需 source 才会改当前 shell；直接执行只输出 export 文本：" >&2
  e_emit_exports
fi
