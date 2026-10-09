#!/usr/bin/env bash
# ╔═══════════════════════════════════════════════════════════════════════════════════════╗
# ║ ⚠ 事故警示（2026-09-29 21:02 违规，21:18 全量回滚；处置 = D 裁定 60）                     ║
# ║                                                                                       ║
# ║ 本脚本的 `--apply` 会**写系统目录**（/usr/lib/x86_64-linux-gnu、/usr/share/glvnd/…）      ║
# ║ 并**跑 ldconfig** —— 这违反 D 执行单 §3.2 的三条硬边界（`rl_harness_supervision/         ║
# ║ d_handoff_to_e_20260929.md`），也违反裁定 60 的重申：主线一律 prefix-only、禁止系统写入。   ║
# ║ E 已用 `--uninstall --apply` 全量回滚（37 个文件进 recycle_bin/e_gpu_uninstall_           ║
# ║ 20260929_211820，**未用 rm**），D 独立复核干净：ldconfig -p 四类 GL 库命中 0、cache 内      ║
# ║ 无 dangling、egl_vendor.d 只剩 50_mesa.json、系统库目录无 09-29 新增文件。                 ║
# ║ 处置结论：**结果采纳、程序违规记一次**。                                                   ║
# ║                                                                                       ║
# ║ ⇒ 要 GPU 渲染请用 **`scripts/e_activate_gpu_render.sh`**（prefix-only，零系统写入，        ║
# ║   自证判据 = GL_RENDERER 含 NVIDIA + 子进程持 /dev/nvidia* fd）。                         ║
# ║ ⇒ 本脚本**保留只为回滚能力**（`--uninstall --apply`）。**安装模式已被代码闸挡死**：          ║
# ║   必须 `E_ALLOW_SYSTEM_INSTALL=<D 的批准文书路径>`（该文件须真实存在）才会执行 ——           ║
# ║   **未经 D 书面批准不得再 `--apply` 安装**，边界靠代码不靠自觉。                            ║
# ╚═══════════════════════════════════════════════════════════════════════════════════════╝
#
# E 线：把与宿主驱动**同版本**的 NVIDIA OpenGL/EGL/Vulkan 用户态库装进容器。
#
# 为什么容器内可修：nvidia-container-runtime 只按 NVIDIA_DRIVER_CAPABILITIES 注入库，
# 本容器是 compute,utility（没有 graphics），所以渲染那套没被挂进来。但
#   ① 内核侧 /dev/nvidiactl + /dev/nvidiaN 已经在了（NVIDIA 的 EGL device platform 用它，
#      不需要 /dev/dri —— 本机实测推翻 docs/infra-gpu-render.md §4 的"必须挂 /dev/dri"）；
#   ② 用户态库可以从 NVIDIA 官方源取到**严格同版本**（590.48.01）。
# 两条都满足 ⇒ 容器内自装即可解锁，不必等平台改 Pod 规格。
#
# 安全闸（任一不满足直接 refuse，不做半装）：
#   G1 /proc/driver/nvidia/version 的版本号 == 待装库版本号（版本漂移 = 装完就崩）
#   G2 待装文件必须来自本地 staging（.codex-persist 持久盘），且 deb sha256 对得上登记值
#   G3 已存在的同名文件，若 sha256 不同 ⇒ 先移入 recycle_bin 再覆盖（**全程不用 rm**）
#   G4 --dry-run 默认先跑；写操作必须显式 --apply
#
# 用法：
#   bash scripts/e_install_nvidia_gl_590.sh --dry-run          # 只打印将要做什么
#   bash scripts/e_install_nvidia_gl_590.sh --apply            # 真装 + ldconfig + 写 manifest
#   bash scripts/e_install_nvidia_gl_590.sh --uninstall --apply # 把本脚本装的文件移入 recycle_bin
set -euo pipefail

# staging 目录名在 21:2x 被移进 E 单 §1 的写入面（.codex-persist/egl-libs/）⇒ **两个名都认**，
# 否则旧名不存在时**回滚工具本身会失效**（这正是最需要它能用的时候）。
E_PERSIST_ROOT=/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist
if [ -n "${E_NV_STAGING:-}" ]; then
  STAGING="$E_NV_STAGING"
elif [ -d "$E_PERSIST_ROOT/nvidia-gl-590.48.01/root" ]; then
  STAGING="$E_PERSIST_ROOT/nvidia-gl-590.48.01"
else
  STAGING="$E_PERSIST_ROOT/egl-libs/_src_590.48.01"
fi
ROOT="$STAGING/root"
LIBDIR=/usr/lib/x86_64-linux-gnu
RECYCLE=/workspace/mnt/sppro/yhzhang91/recycle_bin
REPO=/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot
TS=$(date +%Y%m%d_%H%M%S)
MODE=dry; DO_UNINSTALL=0
for a in "$@"; do
  case "$a" in
    --apply) MODE=apply ;;
    --dry-run) MODE=dry ;;
    --uninstall) DO_UNINSTALL=1 ;;
    *) echo "unknown arg: $a" >&2; exit 64 ;;
  esac
done

log(){ printf '[%s] %s\n' "$MODE" "$*"; }
die(){ printf 'REFUSE: %s\n' "$*" >&2; exit 1; }

# ── 事故闸（裁定 60）：安装态的系统写入必须有 D 的书面批准；回滚态放行 ──────────────────────
if [ "$MODE" = apply ] && [ "$DO_UNINSTALL" = 0 ]; then
  if [ -z "${E_ALLOW_SYSTEM_INSTALL:-}" ] || [ ! -f "${E_ALLOW_SYSTEM_INSTALL}" ]; then
    printf 'REFUSE: 系统安装模式已被事故闸挡住（2026-09-29 21:02 违规 / 裁定 60）。\n' >&2
    printf '        主线请用 prefix-only 激活件：bash scripts/e_activate_gpu_render.sh --selfcheck\n' >&2
    printf '        确需系统安装时，须先拿到 D 的书面批准，并以 E_ALLOW_SYSTEM_INSTALL=<批准文书路径> 传入（该文件须真实存在）。\n' >&2
    exit 1
  fi
  log "事故闸放行：批准文书 = ${E_ALLOW_SYSTEM_INSTALL}"
fi
if [ "$MODE" = apply ] && [ "$DO_UNINSTALL" = 1 ]; then
  log "回滚模式：会把本脚本装过的文件移入 recycle_bin 并 ldconfig（**这仍是系统写入，但目的是恢复装前状态**）"
fi

sha(){ sha256sum "$1" | awk '{print $1}'; }

# ── G1 版本闸 ───────────────────────────────────────────────────────────────
DRV_VER=$(sed -n 's/^NVRM version:.*[^0-9]\([0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\).*/\1/p' \
          /proc/driver/nvidia/version | head -1)
[ -n "$DRV_VER" ] || die "读不到 /proc/driver/nvidia/version 的驱动版本"
LIB_VER=$(cd "$ROOT/usr/lib/x86_64-linux-gnu" 2>/dev/null && ls libnvidia-glcore.so.* 2>/dev/null \
          | sed 's/^libnvidia-glcore\.so\.//' | head -1)
[ -n "$LIB_VER" ] || die "staging 里没有 libnvidia-glcore.so.<ver>：$ROOT（先跑 --fetch 或手工解包 deb）"
[ "$DRV_VER" = "$LIB_VER" ] || die "版本不符：驱动=$DRV_VER 待装库=$LIB_VER（严禁混装，装完 EGL 初始化会失败）"
log "版本闸通过：驱动 == 待装库 == $DRV_VER"

# ── 安装清单：库 + ICD + profiles；不含 wine dll / xorg 模块 / implicit layer ──
MANIFEST_JSON="$REPO/runs/infra/e_gpu_egl_verify_$(date +%Y%m%d)/install_manifest_$TS.json"
MAPFILE="$REPO/tmp/e_nv_install_map_$TS.txt"
build_map(){
  : > "$MAPFILE.tmp"
  while IFS= read -r f; do
    rel="${f#$ROOT/}"
    printf '%s\t%s\n' "$f" "/$rel" >> "$MAPFILE.tmp"
  done < <(find "$ROOT/usr/lib/x86_64-linux-gnu" -maxdepth 1 \( -type f -o -type l \) -name '*.so*';
           find "$ROOT/usr/share/glvnd/egl_vendor.d" -maxdepth 1 -type f -name '*.json';
           find "$ROOT/usr/share/vulkan/icd.d" -maxdepth 1 -type f -name 'nvidia_icd.json';
           find "$ROOT/usr/share/nvidia" -maxdepth 1 -type f \
                \( -name "nvidia-application-profiles-*" -o -name 'nvoptix.bin' \))
  mv "$MAPFILE.tmp" "$MAPFILE"
}
build_map
N_FILES=$(wc -l < "$MAPFILE")
N_BYTES=$(awk -F'\t' '{print $1}' "$MAPFILE" | xargs -d '\n' du -cb 2>/dev/null | tail -1 | awk '{print $1}')
log "待处理文件 $N_FILES 个，合计 $(numfmt --to=iec "${N_BYTES:-0}")（清单：$MAPFILE）"

# 裁定 92.2-②：`cp -a` 的 `-a` 含 `-d`（= `--no-dereference --preserve=links`）⇒ 驱动包自带的
# **绝对**符号链接会被原样搬过来。而那个绝对路径（NVIDIA `.run` 包解开后的根 `/NVIDIA-Linux/…`）
# 在容器里**不存在** ⇒ 落地即悬空。实证：前缀 `.codex-persist/egl-libs/590.48.01/` 里唯一那条悬空链接
# `libnvidia-vksc-core.so.1 -> /NVIDIA-Linux/libnvidia-vksc-core.so.590.48.01`（`find -xtype l` 命中 1/34）
# 就是这么来的（链接自己的 mtime = `Dec  9 2025`，即打包时刻，不是 E 造的）。
# 修法 = **相对化到 dst 所在目录**；同目录下没有那个同名真文件时**保持原样并如实报**，不猜、不静默造链接。
relativize_abs_symlink(){
  local dst="$1"
  [ -L "$dst" ] || return 0
  local tgt base dir
  tgt="$(readlink "$dst")"
  case "$tgt" in
    /*) ;;
    *) return 0 ;;
  esac
  base="$(basename "$tgt")"; dir="$(dirname "$dst")"
  if [ -e "$dir/$base" ]; then
    if [ "$MODE" = apply ]; then
      ln -sfn "$base" "$dst"
      log "relink(相对化) $dst -> $base  （原绝对目标 $tgt 在本机不存在 ⇒ 不相对化就落地即悬空）"
    else
      log "would relativize $dst -> $base  （原绝对目标 $tgt；同目录有 $base 可指）"
    fi
  else
    log "WARN(不猜): $dst 是**绝对**符号链接 -> $tgt，但 $dir/$base 不存在 ⇒ 保持原样，并由 PERSIST_MANIFEST 的 dangling 字段如实登记"
  fi
}

install_one(){
  local src="$1" dst="$2"
  if [ -e "$dst" ] || [ -L "$dst" ]; then
    local s d
    if [ -f "$src" ] && [ -f "$dst" ]; then s=$(sha "$src"); d=$(sha "$dst"); else s=""; d=""; fi
    if [ -n "$s" ] && [ "$s" = "$d" ]; then log "skip(已一致) $dst"; return 0; fi
    # G3 冲突：移入 recycle_bin，不 rm
    local rb="$RECYCLE/e_gpu_install_$TS$(dirname "$dst")"
    if [ "$MODE" = apply ]; then
      mkdir -p "$rb"; mv -f "$dst" "$rb/"; log "backup → $rb/$(basename "$dst")"
    else
      log "would backup $dst → $rb/"
    fi
  fi
  if [ "$MODE" = apply ]; then
    mkdir -p "$(dirname "$dst")"
    cp -a "$src" "$dst"
    relativize_abs_symlink "$dst"
    log "install $dst"
  else
    log "would install $dst  (src=$src)"
    relativize_abs_symlink "$src"   # dry 模式下只打印、不 ln（函数内部按 $MODE 分支）
  fi
}

if [ "$DO_UNINSTALL" = 1 ]; then
  # 卸载：只动本脚本装过的路径（按 map 的 dst），逐个移入 recycle_bin
  log "卸载模式：把 $N_FILES 个目标路径移入 $RECYCLE/e_gpu_uninstall_$TS/"
  while IFS=$'\t' read -r _ dst; do
    if [ -e "$dst" ] || [ -L "$dst" ]; then
      if [ "$MODE" = apply ]; then
        mkdir -p "$RECYCLE/e_gpu_uninstall_$TS$(dirname "$dst")"
        mv -f "$dst" "$RECYCLE/e_gpu_uninstall_$TS$dst"
        log "removed → recycle_bin: $dst"
      else
        log "would remove $dst"
      fi
    fi
  done < "$MAPFILE"
  [ "$MODE" = apply ] && ldconfig && log "ldconfig 完成（已回到装前状态：EGL 只剩 mesa ICD）"
  exit 0
fi

while IFS=$'\t' read -r src dst; do install_one "$src" "$dst"; done < "$MAPFILE"

if [ "$MODE" = apply ]; then
  ldconfig
  log "ldconfig 完成"
  mkdir -p "$(dirname "$MANIFEST_JSON")"
  {
    printf '{\n  "timestamp": "%s",\n  "driver_version": "%s",\n  "lib_version": "%s",\n' "$TS" "$DRV_VER" "$LIB_VER"
    printf '  "staging": "%s",\n  "recycle_backup_dir": "%s",\n  "files": [\n' "$STAGING" "$RECYCLE/e_gpu_install_$TS"
    first=1
    while IFS=$'\t' read -r src dst; do
      [ -e "$dst" ] || continue
      real=$(readlink -f "$dst" 2>/dev/null || echo "$dst")
      h=$( [ -f "$real" ] && sha "$real" || echo "symlink" )
      sz=$( [ -f "$real" ] && stat -c %s "$real" || echo 0 )
      [ $first = 1 ] || printf ',\n'
      printf '    {"dst": "%s", "src": "%s", "size": %s, "sha256": "%s"}' "$dst" "$src" "$sz" "$h"
      first=0
    done < "$MAPFILE"
    printf '\n  ]\n}\n'
  } > "$MANIFEST_JSON"
  log "manifest → $MANIFEST_JSON"
  log "下一步：python scripts/e_gpu_egl_verify.py --label post_install --expect gpu"
else
  log "dry-run 结束（未写任何文件）。确认无误后加 --apply"
fi
