# 向平台申请：把 `NVIDIA_DRIVER_CAPABILITIES` 加上 `graphics`（**P2 文本件，非阻塞**）

> **状态**：裁定 94.7-1 的 ⑤ = **`ruled_no_local_change_platform_request_P2`**。
> **本机不改**（维持 `compute,utility`）；本文件只是**给平台的申请文本**，与 T-E-11 同批交付（D 执行单补单 §三）。
> **优先级 P2**：渲染腿**已经用自有前缀打通并实测过**，这一项只带来「零配置便利」，不是阻塞项。
> **⚠ 本文件已按裁定 77.4 删掉「挂载 `/dev/dri`」那一条**（本机实测 `drm_device_file = null` ⇒ 那一条是错的，见 §3）。
> 生成者：E（基础设施线）· 落盘 2026-09-30 12:0x · 所有读数都是 E 本机实测，`as_of` 逐条标注。

---

## 1. 一句话申请

请把本 Pod / 容器的环境变量 **`NVIDIA_DRIVER_CAPABILITIES`** 由 **`compute,utility`** 改为
**`all,compute,utility,graphics`**（**至少加 `graphics`**；若后续要跑 SAPIEN / Isaac 的 Vulkan 或窗口化渲染，
再加 `display`）。**不需要**挂载 `/dev/dri`，**不需要**改驱动版本，**不需要**给我们 root。

## 2. 现状（全部本机实测，`as_of 2026-09-30 11:58`）

| 项 | 实测值 | 取法 |
|---|---|---|
| `NVIDIA_DRIVER_CAPABILITIES` | **`compute,utility`** | `tr '\0' '\n' < /proc/1/environ \| grep NVIDIA_DRIVER_CAPABILITIES`（读的是**容器级**设置，不是某个 shell 的临时值） |
| 宿主驱动版本 | **590.48.01**（NVIDIA UNIX Open Kernel Module，Release Build，2025-12-08） | `cat /proc/driver/nvidia/version` |
| GPU | **NVIDIA A800-SXM4-80GB** | `nvidia-smi` |
| `NVIDIA_VISIBLE_DEVICES` | `GPU-dd975ddc-ec9b-af2b-81e1-54f4993b07bf` | `/proc/1/environ` |
| `NVIDIA_PRODUCT_NAME` | `CUDA` | `/proc/1/environ` |
| 注入的 `LD_LIBRARY_PATH` | `/usr/local/nvidia/lib:/usr/local/nvidia/lib64` | `/proc/1/environ` |
| **`/dev/dri`** | **不存在**（`ls: cannot access '/dev/dri': No such file or directory`） | `ls -la /dev/dri` |
| `/dev/nvidia*` | **存在**：`/dev/nvidia2`、`/dev/nvidiactl`、`/dev/nvidia-uvm`、`/dev/nvidia-uvm-tools` | `ls /dev/nvidia*` |
| 系统库目录里的 NVIDIA 渲染库 | **0 个**（`libEGL_nvidia*` / `libGLX_nvidia*` / `libnvidia-eglcore*` / `libnvidia-glcore*` 四类全缺） | `ls /usr/lib/x86_64-linux-gnu/ \| grep -cE '^libEGL_nvidia\|^libGLX_nvidia\|^libnvidia-eglcore\|^libnvidia-glcore'` ⇒ `0` |
| `ldconfig -p` 里四类 GL 库命中 | **0** | `ldconfig -p \| grep -cE '…'` ⇒ `0` |
| `/usr/share/glvnd/egl_vendor.d/` | **只有 `50_mesa.json`**（没有 `10_nvidia.json`） | `ls -la /usr/share/glvnd/egl_vendor.d/` |

**结论**：容器运行时**只按 `compute,utility` 注入了 CUDA/工具那一批库**，**渲染那一批（EGL/GLX/eglcore/glcore）根本没被挂进来**。
后果是 `MUJOCO_GL=egl` **不会报错**，但会**静默退化成 CPU 软渲染（Mesa llvmpipe）** —— 这是最容易误判的一点：
**实测 92.374 ms/步（= 34 ms 预算的 2.72×）会被当成 7.300 ms/步（= 预算的 21%）**，差 **12.6×**。

## 3. **为什么申请文本里没有「挂 `/dev/dri`」这一条**（裁定 77.4 已证伪，别再加回来）

早先版本的 `docs/infra-gpu-render.md` §4 写过「必须挂载 `/dev/dri`（宿主需加载 `nvidia-drm`，出现 `renderD128`）」
以及「没有 `/dev/dri` 时 EGL 设备枚举拿不到任何设备」。**这两句已被本机实测推翻**：

- NVIDIA 的 EGL device platform 用的是 **`/dev/nvidiactl` + `/dev/nvidiaN`**，**不需要 `/dev/dri`**；
- 实测 NVIDIA EGL 设备的 **`drm_device_file = null`**，而 **`initialize_ok = true`**、扩展含 **`EGL_NV_device_cuda`**；
- 渲染子进程实测**持有 `/dev/nvidia2` 与 `/dev/nvidiactl` 的 fd**（这是 GPU 归因证据链的一条腿）；
- 本机 `/dev/dri` **确实不存在**，而 GPU 渲染**已经跑通**（见 §4）⇒ 存在性证明已经足够，不需要任何推断。

⇒ 裁定 56.3 判 §4「容器内装不了」**整体作废**（其中「库版本必须与宿主驱动严格一致」这一条**仍成立**）；
裁定 77.4 明确要求**申请文本删掉 `/dev/dri` 那一条**。**本文件照办。**

## 4. 我们**已经**用什么办法把它跑通了（平台会问「那你们为什么还要申请」）

**容器内自装、prefix-only、零系统写入**：把与宿主驱动**严格同版本（590.48.01）**的渲染库放在 NFS 前缀
`/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist/egl-libs/590.48.01/`（**34 个条目 = 23 个真文件 + 11 个符号链接 / 339,337,693 B**），
再靠三个**进程级**环境变量指过去：

```bash
export LD_LIBRARY_PATH=<prefix>:$LD_LIBRARY_PATH
export __EGL_VENDOR_LIBRARY_FILENAMES=<prefix>/10_nvidia.json
export MUJOCO_GL=egl
```

**实测结果**（权威件 `runs/infra/e_egl_coldstart_20260930/COLDSTART_EVIDENCE_v3.json`，578 ln `56b81f389712`，`as_of 2026-09-30 03:02:38`）：

- `GL_RENDERER = **NVIDIA A800-SXM4-80GB/PCIe/SSE2**`、`GL_VERSION = **4.6.0 NVIDIA 590.48.01**`、`renderer_class = **nvidia_gpu**`；
- 交付判词 `delivery_status = COLDSTART_VERIFIED`、`all_teeth_proven = true`、`stages_skipped = []`、`failed_teeth = []`、**`exit 0`**；
- 反向牙 8 条判据全过，其中三条 GPU 占用旁证腿：`util_max = 76 %`、`mem_max = 142 MiB`、
  `child_nvidia_fds = ["/dev/nvidia2", "/dev/nvidiactl"]`；
- 边界干净：`boundary_clean_no_system_write = true`（**不写 `/usr/lib`、不写 `/usr/share`、不写 `/etc`、不 `ldconfig`、不 `apt/dpkg`**）；
- 吞吐权威值：**136.99 ctrl-steps/s = 7.300 ms/步 = 34 ms 预算的 21 %**（对照 osmesa 软渲染 10.84 ctrl-steps/s = 92.374 ms/步）⇒ **12.64× 加速**。

**那为什么还要申请 `graphics`？** 三点，都是运维成本、不是能力问题：

1. **零配置**：现在每个新 shell 都必须显式 `eval` 激活件（`scripts/e_activate_gpu_render.sh --print`），
   且**重启后没有任何东西会自动恢复**（`~/.bashrc` 的 hook 与 `/root/venvs/*` 的软链都在 overlay 临时层）。
   我们为此写了一条命令的冷启动自检 + 自恢复（`scripts/e_coldstart_gpu_render.sh`），但**触发它必须靠人**。
   加了 `graphics`，运行时会自动注入那批库 ⇒ 这一整层脚手架对新同事就不是必需的。
2. **少一个版本漂移面**：前缀里的库必须与宿主驱动**严格同版本**。宿主驱动一升级（例如 590.48.01 → 59x.yy.zz），
   前缀就**当场失效**，需要重新取同版本的库。由运行时注入则天然跟随宿主驱动。
3. **Vulkan / display 类栈**：`graphics` 只解决 EGL/GL；若将来要跑 SAPIEN、Isaac Sim 或任何需要 Vulkan/窗口的仿真，
   还需要 `display`（以及对应的 ICD 注入）。**本次申请不要求这一项**，只是提前说明。

## 5. **为什么我们不自己把 `NVIDIA_DRIVER_CAPABILITIES` 改掉**（边界，写清楚免得平台误会）

- 它是**容器创建时**由运行时读取的变量 ⇒ 在容器内 `export` **无效**，必须**改 Pod 规格并重启容器**才生效。
- 而「改一个已经**实测可用**的态、换成一个**未测**的态，还要付一次重启代价」与用户的「速度优先」相反
  ⇒ 裁定 94.7-1 判 **本机不改**，只留这份申请文本。
- E 线的硬边界（裁定 55.1 / 60）：**不写系统目录、不 `ldconfig`、不 `apt/dpkg`、不改 `NVIDIA_DRIVER_CAPABILITIES`**。
  2026-09-29 21:02 曾违规 `--apply` 装进系统目录，21:18 已全量回滚（37 个文件移入 `recycle_bin`，**未用 `rm`**），
  处置 = 裁定 60「**结果采纳、程序违规记一次**」。⇒ 现在安装模式已被**代码闸**挡死
  （`scripts/e_install_nvidia_gl_590.sh` 必须 `E_ALLOW_SYSTEM_INSTALL=<D 的批准文书路径>` 且该文件真实存在才会执行）。

## 6. 平台改完之后，我们怎么验收（**给平台的验收命令，可直接复制**）

```bash
# 1) 变量真的生效了吗（读容器级，不读某个 shell）
tr '\0' '\n' < /proc/1/environ | grep NVIDIA_DRIVER_CAPABILITIES
#    期望：NVIDIA_DRIVER_CAPABILITIES=all,compute,utility,graphics

# 2) 渲染库被运行时注入了吗
ls -l /usr/lib/x86_64-linux-gnu/libEGL_nvidia.so.0 \
      /usr/lib/x86_64-linux-gnu/libGLX_nvidia.so.0 \
      /usr/lib/x86_64-linux-gnu/libnvidia-eglcore.so.* \
      /usr/lib/x86_64-linux-gnu/libnvidia-glcore.so.*
ldconfig -p | grep -E 'libEGL_nvidia|libGLX_nvidia|libnvidia-eglcore|libnvidia-glcore'
ls /usr/share/glvnd/egl_vendor.d/          # 期望：出现 10_nvidia.json（原来只有 50_mesa.json）

# 3) 版本必须与宿主驱动严格一致
cat /proc/driver/nvidia/version | head -1  # 期望：590.48.01（若宿主驱动升级，这里会变）

# 4) 真渲染一次并看 GPU 归因（**不要**只看 GL_RENDERER 字符串）
nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv   # 渲染期间 utilization 应 > 0
```

**注意（这一条是我们踩出来的，请平台一起看）**：加了 `graphics` 之后，我们的 **prefix-only 前缀会与运行时注入的系统库并存**。
届时**系统目录里出现 NVIDIA 渲染库**会触发我们自己的**边界闸**（`e_activate_selfcheck.py` 判 `refused`、冷启动 `exit 3`）——
那是裁定 60 为防止「悄悄写系统」装的牙，**不是故障**。所以请平台改完之后**通知我们一声**，
我们会在同一轮里把边界闸的判据从「系统目录必须干净」调整为「系统库由**运行时注入**、不是我们写的」，
并**先申报再改**（`daily_report.md`），不静默改判据。

## 7. 本文件**不**主张什么

- **不**主张任何 policy 能力（裁定 46 的禁令不变：BC 出结果之前，任何「能搬运 / 学会了」的表述都无效）。
- **不**主张 `/dev/dri` 相关任何事情（§3 已证伪）。
- **不**主张「加了 `graphics` 会更快」：渲染吞吐由 GPU 与 mujoco 决定，**注入方式不改变帧率**；
  申请理由是**运维成本与版本漂移面**，不是性能。
- 本文的所有读数都只在**本机、本容器、驱动 590.48.01、A800-SXM4-80GB** 上成立，**不外推**到其他机型。
