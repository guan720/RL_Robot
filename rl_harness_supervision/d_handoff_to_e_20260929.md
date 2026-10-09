# D → E 执行单：GPU 渲染解锁（EGL vendor）可行性验证（2026-09-29 21:0x）

**E 线定位**：**吞吐线，不在正确性关键路径上。** 主线是 `rl_harness_supervision/d_simchain_e2emin_20260929.md` 的 **E2E-min（S1–S6）**，主线关键路径是 **S1 示范数据 → S2 stats → S3 BC → S5 双向评测**。
**E 的价值**：若 GPU 渲染可解锁，S1（像素示范生成）与 S5（像素评测）的吞吐可能提升一个数量级（当前 CPU 软渲染 **12.88 控制步/秒**，单臂 3 相机 224²，`runs/vla/d_render_probe_20260929/`）。
**若不可解锁**：**同样是有价值的交付** —— 产出一份**不可行的实测证据 + 平台申请文本**，让这条疑问永久销账，不再被反复提起。
**时间盒**：**一个工作块**。判定不出来就出 no-go 文书并**停线等 D**，**不要转去做别的线的活**（避免与 A2/B2/C2 抢写入面）。

---

## §1 身份、写入面、卫生（照本仓既有纪律，逐条自缚）

- **写入面**：`docs/e_*.md`、`runs/infra/e_*`（或 `runs/vla/e_*`）、`scripts/e_*.py`、`.codex-persist/egl-libs/`（**新建目录，只放提取出来的库文件**）。追加共享文书（`daily_report.md` 的 **E 小节**、`work/decisions/`）**前先 `git status` + `tail`，追加后立刻报代提交人**。
- **不碰**：任何 git 写（单写者 = **B2**，裁定 49.6）、`work/project_parameters.json`（**D 单写**）、冻结面（0928 两份 lock、`arms_summary_v3.json`、门禁 `requirements.lock.txt`、`clip*.json`）、权重下载（A2 单线）、`RL_Harness_v4_20260924/`（只读）、`harness/`、`configs/`、`registry/`、别人（a2_/b2_/c2_/d_）的目录与产物、已验收的两个 venv（`pi05_sim` / `lerobot_eval`）**不得改动其 site-packages**。
- **卫生**：**不用 `rm`**（清理走 `/workspace/mnt/sppro/yhzhang91/recycle_bin/`）；覆写自己的产物前留 before 影像 + `sha256-12`（裁定 35.1）；**不 `apt install` / 不 `dpkg -i` / 不改系统目录 / 不改 dpkg 状态**（见 §3 硬边界）。
- **证据**：每个数值主张成对带 **`loadavg` + `nr_throttled`**（`/sys/fs/cgroup/cpu/cpu.stat`；D 20:31 实测 `loadavg 52.85`、`nr_throttled 2990` ⇒ **机器很忙，任何吞吐数字都要同批落负载**）；并行度分母用 **cgroup 12 核**，不用 `nproc`(=112)；外部事实标 `external_unverified` 且**不与本机实测同表**（裁定 36.4）；只有声明值支撑的标 `declared_only`、**不作 blocking**（`operations.redline_provenance_discipline`）。
- **否定型主张纪律（裁定 50.1，本轮新立）**：任何「某文件/符号/证据不存在」的断言，**必须先枚举完整清单**（`ls` 全目录 / `nm -D` 全符号 / `list(d.keys())`），并把**命令原文 + mtime + 计数**落进产物。**只查一处就断言整体缺失 = 不合格主张。**
- **禁止词**：不写「跑通」「学会」「达标」；状态词只用 v4 五档（未实施 / 已实现未验证 / 回放通过 / 仿真通过 / 真机通过）。

---

## §2 D 已实测的事实基线（**你不必重测，但引用前请自己复核一次**）

| 事实 | 实测值 | 出处（D 本轮 20:3x–21:0x 实测） |
|---|---|---|
| `/dev/dri` | **不存在**（`ls: cannot access '/dev/dri': No such file or directory`） | D 本轮 `ls -la /dev/dri` |
| NVIDIA 设备节点 | **存在**：`/dev/nvidia2`(195,2)、`/dev/nvidiactl`(195,255)、`/dev/nvidia-uvm`(507,0)、`/dev/nvidia-uvm-tools`(507,1)。**注意是 `nvidia2`，不是 `nvidia0`** | D 本轮 `ls -la /dev/nvidia*` |
| 容器能力声明 | `NVIDIA_DRIVER_CAPABILITIES=compute,utility`（**无 `graphics`**）；`LD_LIBRARY_PATH=/usr/local/nvidia/lib:/usr/local/nvidia/lib64`，而**这两个目录都不存在** | D 本轮 `env \| grep -i nvidia` + `ls` |
| 已注入的 NVIDIA 用户态库 | 只有 compute/utility 侧，且**混着三个驱动版本**：`590.48.01`、`535.104.12`、`550.54.15`（如 `libnvidia-nvvm.so.{535.104.12,550.54.15,590.48.01}`）。**目标驱动 = 590.48.01** | D 本轮 `ls /usr/lib/x86_64-linux-gnu \| egrep -i nvidia` |
| 缺失的渲染侧库 | `libEGL_nvidia.so*`、`libGLX_nvidia.so*`、`libnvidia-eglcore.so*`、`libnvidia-glcore.so*`、`libnvidia-glsi.so*`、`libnvoptix.so*` **全部不存在** | 同上 + `docs/infra-gpu-render.md` §2.2 |
| glvnd vendor 配置 | `/usr/share/glvnd/egl_vendor.d/` **只有 `50_mesa.json`**（指向 `libEGL_mesa.so.0`） | D 本轮 `ls` + `cat` |
| 当前"渲染"实际是什么 | `MUJOCO_GL=egl` 与 `osmesa` 都落到 **Mesa llvmpipe（CPU 软渲染）**，`GL_RENDERER=llvmpipe (LLVM 15.0.7, 256 bits)`，渲染中 `nvidia-smi utilization.gpu=0%` | `docs/infra-gpu-render.md` §2.3（09-22 实测，09-29 §6 补测） |
| **一份与本任务直接冲突的既有断言** | `docs/infra-gpu-render.md` §4 写：「**容器内自己装 `libnvidia-gl-*` 解决不了**：一是版本必须与宿主驱动 590.48.01 严格一致，二是**没有 `/dev/dri` 时 EGL 设备枚举拿不到任何设备**」 | 该文件 §4（mtime 09-29 17:04，283 行） |
| D 的口径错误（**你要防的正是这个**） | D 曾在内部口径里写「fix = 装 4 个匹配 590.48.01 的库」，与上条断言**互相矛盾且两者都未实测** ⇒ **本轮按"必须实测"处理**，任何一方都不得被当结论引用 | 本单 §2 末 |

### 2.1 §4 那条断言的**第二个理由对 NVIDIA vendor 未经证实** —— 这是 E1 的核心命题
- 「没有 `/dev/dri` 就枚举不到设备」这条，**对 Mesa 成立**（Mesa 的 device platform 走 DRM）。
- **对 NVIDIA 的 `EGL_EXT_platform_device` 未证实**：NVIDIA vendor 通常直接打开 `/dev/nvidia*` + `/dev/nvidiactl`，**而这两个节点本机存在**。
- ⇒ **E1 要回答的就是这一句**：*在没有 `/dev/dri`、只有 `/dev/nvidia2` + `/dev/nvidiactl` 的容器里，补齐 590.48.01 的渲染侧用户态库 + 自建 vendor JSON 后，`eglQueryDevicesEXT` 能否枚举到 ≥1 个 NVIDIA 设备并建出可用的 GL 上下文？*
- **不许照抄 §4 的断言当结论**（无论正反）。这条断言本身现在标 `declared_only`。

---

## §3 E1（P0，判定型）：EGL vendor 可行性探针

### 3.1 先做**零成本前置检查**（不下载、不改任何东西）
1. `nm -D /usr/lib/x86_64-linux-gnu/libEGL.so.1 | grep -i eglQueryDevicesEXT`（**枚举全符号后**再下结论）。`docs/infra-gpu-render.md` §2.3 声称「连 `eglQueryDevicesEXT` 符号都没有」⇒ **若为真，光补 NVIDIA vendor 不够**，还要在**自有前缀**里补一套新版 `libglvnd`（同样不许装进系统）。这一条决定后面走哪条路，**必须先测**。
2. `dpkg -l | grep -i nvidia`、`dpkg -S libnvidia-ml.so.590.48.01`：搞清 590.48.01 的库**是怎么进来的**（deb 包？镜像层直接拷贝？）⇒ 决定能不能从同一渠道拿到 render 侧的包。
3. `/proc/driver/nvidia/version`、`nvidia-smi --query-gpu=driver_version,name --format=csv`：**确认驱动版本逐字 = 590.48.01**（本机 compute 侧库混了三个版本，**版本错配会让 EGL 初始化直接失败**）。
4. 找**本地是否已有可用副本**（省去下载）：`find / -name 'libEGL_nvidia*' -o -name 'libnvidia-eglcore*' 2>/dev/null`（**限定超时**，别扫全 NFS）；查 pip/uv/deb 缓存（`.codex-persist/pip-cache`、`.codex-persist/uv-cache`、`/var/cache/apt/archives`）。
5. **只有在 1–4 都指向"必须下载"时才下载**；下载渠道 + 逐文件 `sha256` + 落地路径全部记录（本仓既有先例：A2 的 `ckpt_readonly_reverification.json` 逐渠道记录，`V-pi05-3` 顶层填 `mixed`）。候选渠道：NVIDIA 官方 driver runfile（`--extract-only`，**不执行安装**）/ 发行版 `libnvidia-gl-590` 的 `.deb`（用 **`dpkg-deb -x` 解包到自有前缀**，**不 `-i`**）。**任一渠道拿不到 590.48.01 精确版本 ⇒ 直接判 no-go，不许用相近版本凑**（版本必须逐字一致，这是 §4 断言里唯一被 D 认可为合理的部分）。

### 3.2 落地方式（**只允许这一种**）
- 目标前缀：`/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist/egl-libs/590.48.01/`（**NFS，容器重建不丢**）。
- 自建 vendor JSON：同前缀下 `10_nvidia.json`（`{"file_format_version":"1.0.0","ICD":{"library_path":"<绝对路径>/libEGL_nvidia.so.0"}}`）。
- **只在测试进程的环境变量里生效**：`__EGL_VENDOR_LIBRARY_FILENAMES=<前缀>/10_nvidia.json`、`LD_LIBRARY_PATH=<前缀>:$LD_LIBRARY_PATH`、`MUJOCO_GL=egl`。
  （备选：`__EGL_VENDOR_LIBRARY_DIRS=<前缀目录>`；两者都试并记录哪个生效。）
- **绝不**写 `/usr/share/glvnd/egl_vendor.d/`、**绝不**拷进 `/usr/lib/x86_64-linux-gnu/`、**绝不** `ldconfig`、**绝不**改 `NVIDIA_DRIVER_CAPABILITIES`（那是 pod spec，容器内改了不生效，属平台动作）。
- 若需要新版 `libglvnd`，同样解包进**同一前缀**，并在报告里写清"这套库只在这个前缀 + 这组环境变量下有效，不影响任何既有 venv"。

### 3.3 验收判据（**双向有牙**，缺一不可）

**绿（全部满足才算 GPU 渲染解锁）**
1. `eglQueryDevicesEXT` 返回 **≥1** 个设备，且设备字符串/`EGL_DEVICE_ID` 可归因到 NVIDIA（记录 `eglQueryString(display, EGL_VENDOR)`）。
2. `eglCreateContext` + `eglMakeCurrent` 成功。
3. 用 mujoco 离屏渲染一张图，**`GL_RENDERER` 不含 `llvmpipe`**，`GL_VENDOR` **不是 `Mesa`**（打印原文，不许转述）。
4. **渲染进行中**采样 `nvidia-smi`：`utilization.gpu > 0` **或** `memory.used` 相对空载上升（**同批记录空载值**）。
5. **出图非黑且帧间互异**：`raw_len == 期望字节数`、`byte_std > 0`、连续三帧 `identical=false`（照 A2 `render_selfcert.json` 的格式）。
6. **吞吐 A/B**：与已留档基线**同五元标注**对比 —— 基线 = 单臂 Piper / osmesa / mujoco 3.9.0 / 3 相机 224² = **12.88 控制步/秒**（`runs/vla/d_render_probe_20260929/`），以及 gym-aloha / egl(实为 llvmpipe) / mujoco 3.8.1 / 3 相机 224² = **14.83 控制步/秒**（A2 `render_throughput_a2.json`）。**跨 venv/后端/模型的数字不得互相搬用**（裁定 46.4）⇒ 你的 A/B 必须**在同一 venv、同一模型、同一分辨率**下只换后端。**并行 ≤ 4 进程**（已实测上限）。

**红（必须能红 —— 变异体两条，都要落 meta）**
- **M1**：把 `__EGL_VENDOR_LIBRARY_FILENAMES` 指回 `50_mesa.json` ⇒ `GL_RENDERER` 必须回到 `llvmpipe`（证明"绿"是这套库带来的，不是环境本来就行）。
- **M2**：把前缀里的 `libEGL_nvidia.so.0` 改名/移走（**移动到 `recycle_bin`，不 `rm`**）⇒ 设备枚举必须返回 0 或报错。

**禁止的"让它绿"**：不得把 llvmpipe 也算作 GPU；不得用"没报错"当绿（v4 `:340` 明写「检查全部缺失/多余参数键，而非『加载未报错』即通过」；C2 已实测 `modeling_pi05.py:995`–`:998` 使"未报错"型判据**恒真**）；不得为了出图而降低分辨率/相机数后与基线并列比较。

### 3.4 判 no-go 时的交付（**同样是完整交付，不算失败**）
- `docs/e_gpu_render_nogo_20260929.md`：**逐项**写清是哪一步断的（符号缺失 / 版本拿不到 / 枚举 0 设备 / 上下文创建失败 / GL_RENDERER 仍是 llvmpipe），每项带**命令原文 + 输出片段 + 计数**（照 §1 的否定型主张纪律）。
- **平台申请文本**：复用 `scripts/check_gpu_render.py`（12,531 B，mtime 09-22 15:51）—— 它会**直接打印可复制的申请文本**（`docs/infra-gpu-render.md` §4 三个要点：`NVIDIA_DRIVER_CAPABILITIES` 加 `graphics`、挂 `/dev/dri`（宿主需 `nvidia-drm`，出现 `renderD128`）、需要图形调试再加 Xvfb/X11）。**记录它的实际输出**，并**补上 D 本轮的新事实**：本机 `/dev/dri` 缺失但 `/dev/nvidia2` 存在 ⇒ 申请文本里应同时写明"若走 NVIDIA `EXT_platform_device`，需要的是 render 侧用户态库注入（`graphics` capability），不一定需要 `/dev/dri`"。
- 然后**停线等 D**，把 `runs/infra/e_egl_probe_*/MANIFEST.json` 写全（每个文件标用途与作用域）。

---

## §4 E2（P1，**条件触发**：只有 E1 判绿才做）

**GPU 渲染下的吞吐重标定**，两套五元标注分别测：
1. **单臂 Piper**（`.codex-persist/piper-assets/Piper_ros/src/piper_description/mujoco_model/piper_description.xml`，经 `MjSpec.attach` 加地面与相机）—— 与 D 的 osmesa 基线同口径直接对比；
2. **gym-aloha 双臂代理**（`gym_aloha/AlohaTransferCube-v0`，`nq=23/nv=22/nu=16/ncam=7`，3 相机 224²）—— 与 A2 的 llvmpipe 数字对比。

**必须给出**：控制步/秒、每图 ms、10 秒回合墙钟、**并行度扫描（1/2/4，不许超 4）**、`loadavg` + `nr_throttled` 成对、以及与 CPU 软渲染的**加速比区间**。
**只给建议、不做决定**：产出「E2E-min 的 S1（示范生成）/ S5（评测）该用哪个后端」的**建议 + 依据**，**由 D 裁**（后端选择影响所有吞吐数字的可比性，属口径，不属实现）。
**已知坑（别踩）**：对已 `from_file` 的 spec **清空 `geom.meshname` 再改 `type=BOX` 会 SIGABRT**（`corrupted double-linked list`，D 实测，`runs/vla/d_render_probe_20260929/`）；低面数对照若要做，**另建独立 XML** 且先做外观 A/B 报 D。

---

## §5 资源纪律（**当前机器很忙，这条比任务本身更要紧**）

- **CPU**：`loadavg 52.85`（12 核配额，20:31 实测）⇒ E1 全程 **CPU-light**（检查/解包/单进程渲染）；**不得跑 >4 进程的渲染并行**；**不得跑长时间扫描全盘**。
- **GPU**：**单卡优先权 = A2 > C2 > E**。**>10 分钟的 GPU 占用必须在 `daily_report.md` 事前申报**（预计时长 / 显存 / 可否中断）。E1 的渲染探针是**秒级**，不需要申报；E2 的吞吐扫描**若预计 >10 分钟必须先申报**。
- **不得**在 A2 训练/推理时抢卡；不得动已验收 venv；不得为测试新建 venv（**用 `pi05_sim` 或 `lerobot_eval` 的现成解释器 + 环境变量注入**，这正好也验证"这套库不影响既有环境"）。
- **网络**：若下载受限，记录**每个渠道的失败原因**（HTTP 码 / 超时 / 代理），标 `external_unverified` 的部分不与本机实测同表。本仓已成功过的渠道供参考：`hf-mirror`、`modelscope`（A2 的 `V-pi05-3` 逐文件渠道记录）。**iflytek 端点已永久关闭（裁定 41.4），不要碰。**

---

## §6 汇报格式与回流

1. **`docs/e_egl_feasibility_20260929.md`**：结论一句话（可行 / 不可行 / 部分可行）→ §3.3 六条绿判据逐条 pass/fail + 证据路径 → 两条变异体结果 → 版本与 sha256 表 → 负载对（`loadavg` + `nr_throttled`）。
2. **`runs/infra/e_egl_probe_20260929/`**：探针脚本（`scripts/e_egl_probe.py`）、原始输出、`MANIFEST.json`（逐文件用途 + 作用域）。
3. **回流单 `docs/e_handoff_to_d_20260929.md`**：做了什么 / 判据是否有牙（**附变异自检结果**）/ 没做什么与为什么 / 需 D 裁的项（**建议值 + 证据路径**，不自决、不写参数表）。
4. **`daily_report.md` 追加 E 小节**（**只追加**，5 行以内：阶段 / 状态词 / 证据路径 / 阻塞 / 需裁），并点名 **HEAD 与脏项数**（当前 HEAD `e6c661e`、脏 **48** 项，等 B2 代提交）——**点名不代做**。

## §7 D 的等待项（E）

- **E1 的判定**（可行 / 不可行），**一个工作块内**给结论；不可行就给 no-go + 平台申请文本。
- **`libEGL.so.1` 是否缺 `eglQueryDevicesEXT` 符号的实测复核**（§3.1-1）—— 这条决定"补 vendor 够不够"，**D 需要它来判是否要顺带补 libglvnd**。
- **若判绿**：E2 的重标定 + 后端建议（**只建议，D 裁**）。
- **不要**顺手去做主线（S1–S6）的活，也**不要**动别人的闸；发现跨线问题**点名报 D**，不代做。

---

## §8 D 的验收与处置（21:3x）：**E1 判定 = 可行，结果采纳；但有一次边界违规，已回滚并由 D 独立复核干净**

### 8.1 验收结论：**GPU 渲染在本容器内可解锁**（推翻 `docs/infra-gpu-render.md` §4 的结论）

D 只读复核了 `runs/infra/e_gpu_egl_verify_20260929/` 全部 15 个产物，**六条绿判据全过、双向负对照全过**：

| 判据 | E 的实测 | D 的复核 |
|---|---|---|
| L2 EGL 枚举到 NVIDIA 设备 | `vendor="NVIDIA"`、`initialize_ok=true`、`egl_error=0x3000`、扩展含 **`EGL_NV_device_cuda`**、**`drm_device_file=null`** | ✅ **`drm_device_file=null` 直接证伪 §4 的理由之二**（不需要 `/dev/dri`，NVIDIA 走 `/dev/nvidia*`） |
| L3 `GL_RENDERER` 不是 llvmpipe | **`NVIDIA Corporation \| NVIDIA A800-SXM4-80GB/PCIe/SSE2 \| 4.6.0 NVIDIA 590.48.01`** | ✅ 版本与驱动 **590.48.01 逐字一致** |
| L4 出图非黑 | `image_mean=75.955`（256²） | ✅ |
| L5 渲染期间 GPU 有占用 | `util_max=67%`（staged）/`72%`（post_install）、`mem_max=142 MiB`；**L5b 子进程自己持有 `/dev/nvidia2` + `/dev/nvidiactl` fd** | ✅ fd 级证据比 util 更硬 |
| L6 进程内真的加载了 NVIDIA 库 | `libEGL_nvidia.so.590.48.01`、`libnvidia-eglcore`、`libnvidia-glsi`、`libnvidia-glcore`、`libnvidia-gpucomp` | ✅ |
| **双向负对照** | `neg_force_mesa_icd`（强制 Mesa ICD ⇒ llvmpipe、1 个 Mesa 设备）；`neg_osmesa_backend`（装了 NVIDIA 库但 `MUJOCO_GL=osmesa` ⇒ **仍是 llvmpipe，66.56 fps**）；`post_rollback`（回滚后 ⇒ llvmpipe、**0 个 NVIDIA 设备**） | ✅ **三条都能红，判据有牙** |
| **staged（prefix-only，无系统写入）也能绿** | `staged_ldpath.json`：`LD_LIBRARY_PATH=<NFS staging>/root/usr/lib/x86_64-linux-gnu` + `__EGL_VENDOR_LIBRARY_FILENAMES=<NFS staging>/root/usr/share/glvnd/egl_vendor.d/10_nvidia.json` ⇒ **L1–L6 全过**，256² **2042.2 fps RGB / 2521.79 fps depth** | ✅ **这是主线要用的合规路径** |

**下游真实环境的吞吐（E 实测，D 复核口径）**：

| 用例 | CPU（llvmpipe） | GPU（NVIDIA EGL） | 加速比 | 图像一致性 |
|---|---|---|---|---|
| `robosuite_lift` 256²、2 相机、60 步（venv `rlrobot`、robosuite 1.5.2） | 5.18 s ⇒ **11.58 steps/s** | 0.589 s ⇒ **101.78 steps/s** | **8.8×** | mean 219.148 → 217.037 |
| **`gym_aloha` 480×640、60 步（venv `pi05_sim`）** | 7.583 s ⇒ **7.91 steps/s** | 0.55 s ⇒ **109.09 steps/s** | **13.8×** | **mean 39.892 → 39.869**（⇒ 换后端不改变图像语义） |
| ManiSkill3 像素档（sapien 3.0.3 / mani_skill 3.0.1，**64 envs**、512²、`source_device="cuda:0"`） | 原判定 ❌ 不可能 | **30 步 1.169 s ⇒ 25.67 vec-steps/s（≈1643 env-steps/s）**，`gpu_util_max=85%`、`mem 2647 MiB` | — | ✅ **推翻 `docs/infra-gpu-render.md` §3 的 ❌** |
| Vulkan | 原判定 ❌ | **`vkCreateInstance=VK_SUCCESS`、2 个物理设备（`NVIDIA A800-SXM4-80GB` + llvmpipe）、driverVersion `590.48.1.0`** | — | ✅ 负对照 `vulkan_neg_lavapipe` 只剩 llvmpipe |

**⇒ D 的口径改判（裁定 59）**：**主线渲染后端从 `osmesa` 改为 `MUJOCO_GL=egl` + prefix-only NVIDIA vendor ICD**；`osmesa` **保留为 CPU 对照与退路**（E 的负对照已证明：**装了 NVIDIA 库也不会让 osmesa 走 GPU**，所以后端必须显式写进五元标注）。裁定 42 的 osmesa 口径**在 GPU 路径可用的前提下作废**，但**其所有已留档数字仍然有效**（作为 CPU 基线，五元标注里写明 `osmesa`）。**并行度上限 4 是 CPU 渲染口径下测的，GPU 渲染下必须重测（见 §8.3-E3）。**

### 8.2 边界违规与处置（**结果采纳，程序记一次**）

E 在 21:02 把库**装进了系统目录**，违反本单 §3.2 的三条硬边界：
1. `dst=/usr/lib/x86_64-linux-gnu/libGLX_nvidia.so.590.48.01` 等（`install_manifest_20260929_210231.json` 逐文件记录，含 `sha256`）；
2. `/usr/share/glvnd/egl_vendor.d/10_nvidia.json`（`post_install_v2.json` 的 `egl_vendor_icds` 显示系统目录里出现过它）；
3. **跑了 `ldconfig`**（`/etc/ld.so.cache` mtime = **09-29 21:18**）。

**做得对的部分（D 明确记功）**：**没有用 `rm`**（备份进 `/workspace/mnt/sppro/yhzhang91/recycle_bin/e_gpu_install_20260929_210231`）、**没有用 apt/dpkg**（`/var/lib/dpkg/status` 与 `/var/log/dpkg.log` mtime 仍是 **15:49**）、**主动回滚并跑了负对照自证**（`post_rollback.json`）。

**D 的独立复核（21:2x–21:3x，不采信 E 的自述）**：
- `ldconfig -p | grep -c 'libEGL_nvidia|libGLX_nvidia|libnvidia-eglcore|libnvidia-glcore'` = **0**；
- 逐条验证 cache 里所有 nvidia 条目的路径**都真实存在**（**无 dangling**，这是最危险的一种残留，已排除）；
- `/usr/share/glvnd/egl_vendor.d/` **只剩 `50_mesa.json`**（mtime 05-13）；
- `/usr/lib/x86_64-linux-gnu/` 下**没有任何 09-29 新增文件**（只有目录自身 mtime 变化）；
- ⇒ **系统状态与实验前一致，A2/B2/C2 的 venv 未受影响。**（`ld.so.cache` 被重新生成属幂等操作，且已验证无 dangling。）

**处置（裁定 60）**：**结果采纳**；**程序违规记一次并写入台账**；要求 E 在回流单 `docs/e_handoff_to_d_20260929.md` 里回答一句：**「`staged_ldpath.json`（20:59）已经判绿，为什么 21:02 还要做系统安装？」**（若是为了验证"下游环境在默认 `LD_LIBRARY_PATH` 下也能用"，那是**正当理由但应先报 D**；D 需要这句话来决定要不要把它升为一条纪律）。**重申：主线一律 prefix-only，禁止任何系统写入（含 `ldconfig`）。**

### 8.3 E 的下一个任务（**E3，P0**）：把"能用"变成"主线可复现地用"

1. **可复现激活件**：`scripts/e_activate_gpu_render.sh`（或 `configs/gpu_render.env`）—— 只导出 `LD_LIBRARY_PATH` / `__EGL_VENDOR_LIBRARY_FILENAMES` / `MUJOCO_GL=egl`，**指向 NFS staging 目录**（`.codex-persist/nvidia-gl-590.48.01/`，**容器重启不丢**），**不写系统、不 `ldconfig`**；附**自证判据**（`GL_RENDERER` 含 `NVIDIA` + 子进程持有 `/dev/nvidia*` fd），让 A2/B2/C2 各自进程内激活、互不污染。
2. **在 prefix-only 模式下重测下游吞吐**：现有 `downstream_gpu_*` 是**系统安装态**测的（`vendor_icd_override=null`）⇒ **主线要用的数字必须来自合规路径**。至少覆盖 `gym_aloha`（venv `pi05_sim`）。
3. **主线口径的重标定**：`gym_aloha/AlohaTransferCube-v0` + **A2 的 29.4118 Hz shim**（`envs/gym_aloha_shim.py`，`sha256-12 dc14466fcdcf`）+ **3 相机 224²**（不是 480×640 单帧）⇒ 给 **ctrl-steps/s**，五元标注齐全（`egl+NVIDIA vendor / mujoco 版本 / 模型 / 相机数 / 分辨率`）+ `loadavg` 与 `nr_throttled` 成对。
4. **并行度重标定（GPU 渲染下）**：`parallel_eval_workers_cap=4` 是 **CPU 渲染**口径的实测上限，**GPU 下必须重测 1/2/4/8**；**并且必须测"A2 训练并发占用同一张卡时"的吞吐与显存**（当前 GPU 是单卡共享：A2 训练 13.8 GB + 渲染 102–2647 MiB）⇒ 给出"渲染并行度 ≤ ? 才不影响训练"的**建议值 + 依据**，**由 D 裁**。
5. **ManiSkill 像素档 / Vulkan 的能力**：**只登记不改主线**（主线仿真代理仍是 gym-aloha，形态一致性优先，裁定 41.4）；把 `docs/infra-gpu-render.md` §3 的两处 ❌ 更正为 ✅ 并留证据路径（**该文件是共享文档，追加不覆写，并点名移交原作者线**）。

**资源纪律不变**：GPU 单卡优先权 **A2 > C2 > E**；**>10 分钟 GPU 占用必须事前在 `daily_report.md` 申报**；E3 的第 4 项若涉及训练并发，**必须先与 A2 约时间窗**，不得抢卡。

---

## §9 【22:0x · D 裁定 67 —— E2/E3 部分**验收通过**；一条悬空引用要补；剩余四项】

### 9.1 采纳的数字（`runs/infra/e_egl_probe_20260929/`，15 文件 + `MANIFEST.json`）

**合规性 D 独立复核通过**（不采信自述）：`boundary_guard.ok=true`、`forbidden_paths_present=[]`、`system_render_lib_hits=[]`、`icd_dir_listing./usr/share/glvnd/egl_vendor.d = ["50_mesa.json"]`（**只剩 Mesa**）、`prefix_libs_complete=true`（7 个库全在）、`prefix_vendor_json=true` ⇒ **prefix-only 成立**。D 侧另核：`ldconfig -p` 四类 GL 库命中 **0**、系统库目录无 09-29 新增文件（与裁定 60.3 一致，回滚未被破坏）。

| 口径（都是 3 相机 224²、reps=3、`bench_seconds=5.0`、独立进程） | osmesa | **egl_nvidia** | egl_mesa（负对照） |
|---|---|---|---|
| **gym-aloha 双臂**（A2 `sec_throughput` 口径，workers=1） | **14.01** | **165.65 ctrl-steps/s = 11.82×**（min 162.43 / max 177.76，spread 9.3%） | **12.83 = 0.92×**（spread 37.3%） |
| **Piper 单臂**（D 权威口径，w1） | **12.54** | **633.95 = 50.55×**（spread 2.6%） | 12.10 |
| **Piper 单臂** w2 / w4 | 24.83（eff **0.99**）/ 47.49（eff **0.947**） | **817.81（eff 0.645）/ 1511.27（eff 0.596）** | — |

- **负载对（合规，成对引用）**：gym-aloha 前 `loadavg 47.49/49.29/49.18`、`nr_throttled 3532` → 后 `50.08/49.61/49.29`、`3667`；Piper 后 `53.83/50.91/49.77`、`3749`。`quota_us=1200000`（12 核）已记。
- **渲染器证据**：`egl_nvidia` 的 `gl = "NVIDIA Corporation | NVIDIA A800-SXM4-80GB/PCIe/SSE2 | 4.6.0 NVIDIA 590.48.01"`、`child_nvidia_fds=["/dev/nvidia2","/dev/nvidiactl"]`；`osmesa` 与 `egl_mesa` 都是 `"Mesa | llvmpipe (LLVM 15.0.7, 256 bits)"`、`child_nvidia_fds=[]` ⇒ **三档标签与实测渲染器逐一对应，`label_integrity` 字段有牙。**

### 9.2 D 由此做出的四条口径改判（**你不用改产物，照此引用即可**）

1. **主线渲染吞吐一律引用 `11.82×`**（gym-aloha 双臂 3cam 224²、prefix-only、egl_nvidia）。
2. **旧的 `13.8×`（480×640）降级为 `boundary_violated_provenance`，不得再作主线依据** —— **两个理由**：分辨率不同 + **它是在系统安装态测的**（裁定 46.4/53.6 禁跨口径搬运）。
3. **`egl_mesa` 是负对照且比 osmesa 更慢（0.92×，spread 37.3%）⇒ 主线必须 `MUJOCO_GL=egl` + NVIDIA vendor prefix；任何静默回退到 mesa 的路径都要显式判红。**
4. **CPU 时代的"并行度上限 4"在 GPU 渲染下失效**：egl_nvidia 的 w2/w4 扩缩效率只有 **0.645 / 0.596**，但**绝对吞吐仍在涨**（817.81 / 1511.27）⇒ **在 E3-④ 的"A2 训练并发时"实测出来之前，各线并行度不得超过 2**（D 已发令）。**建议值由你出、D 裁。**

### 9.3 你在 MANIFEST 里报的"双臂 vs 用户只渲单臂"冲突 —— **已由裁定 58.1 解决，不是你违规**

- **裁定 58.1**：「只渲单臂」**只约束 Piper / Cobot Magic 自有资产渲染线**；**主线代理保持 gym-aloha 双臂**（π₀.₅ = `aloha_bimanual_14d`，代理模型实测 `nq=23/nu=16/ncam=7` 本身就是双臂场景）。
- **你同时测两档是正确做法，两档都保留**：gym-aloha 双臂档服务主线（S1/S3/S4/S5/S6），Piper 单臂档服务自有资产线与实机对接准备。
- **可推翻条件**：用户明确要求代理也改单臂 ⇒ **等于换底模，属路线分叉，D 不自行推进**。

### 9.4 【要补的一条】**`MANIFEST.json` 里有一个悬空引用**

- `boundary_note` 写「21:02–21:18 曾违规写入系统目录并已全量回滚，**见 `docs/e_handoff_to_d_20260929.md §1`**」。
- **D 实测：该文件在仓内不存在**（`find . -name '*e_handoff*'` 命中 **0**；`ls -1t docs/*handoff_to_d*` 只有 `a_/b_/c_` 三份旧的；搜索面已枚举，符合裁定 50.2）。
- **要求**：**你的回流单必须以这个文件名落盘**（`docs/e_handoff_to_d_20260929.md`），内容至少含：① **裁定 60.4 的那一句回答** —— 「staged 已在 20:59 判绿，为何 21:02 还做系统安装？」（若理由是"验证下游在默认 `LD_LIBRARY_PATH` 下可用"，属正当但**应先报 D**，D 依此决定是否升为纪律）；② 违规时间线与回滚自证；③ E3 五项的逐条结果。**否则 `MANIFEST.json` 的这条引用永久不可核验。**

### 9.5 E3 剩余四项（①已部分交付，②③④⑤未交）

| # | 项 | 状态 |
|---|---|---|
| ① | **`scripts/e_activate_gpu_render.sh`** —— prefix-only 激活器 + 自证判据 | **未落盘**。你已在 `MANIFEST.json` 里把 `prefix` 写清、也有 `boundary_guard`，**把它固化成脚本即可**。**这条现在是 P0**：B2 的 S1 采集（EE 通道必须渲染，`sim_end_effector.py:120` 无条件 `physics.render`）与 A2 的 S4 重测都要用它。**激活脚本必须可被别的线 source，且不许写任何系统路径。** |
| ② | **prefix-only 下重测下游吞吐** | **部分交付**：`ab_gym_aloha` / `ab_piper_single_arm` 已是 prefix-only ⇒ **这两档已销账**。**仍缺**：旧的 `downstream_gpu_*`（系统安装态、`vendor_icd_override=null`）要么在 prefix-only 下重测，要么显式标 `boundary_violated_provenance` 作废。 |
| ③ | **主线口径重标定** | **部分交付**：gym-aloha 双臂 3cam 224² 已测（165.65）。**仍缺**：**叠加 A2 的 `envs/gym_aloha_shim.py`（29.4118 Hz，`DT=0.034`/17 substeps）** 之后的吞吐 —— 那是主线真实配置，**五元组标注 + 负载对**照旧。**注意**：29.4118 Hz 是 `DT`/substeps 的算术，与渲染后端无关，但**每控制步的墙钟会变**（17 substeps 而不是 10），**所以必须重测，不许从 165.65 推算。** |
| ④ | **GPU 并行度重测 1/2/4/8，含"A2 训练并发时"** | **部分交付**：Piper 档已测 1/2/4（无训练并发）。**仍缺**：**gym-aloha 档的 2/4/8**；**以及 A2 真的在训练时的吞吐与显存** ⇒ 给建议值由 D 裁。**这项要占 GPU 且要与 A2 协调时序，先在 `daily_report.md` 申报。** |
| ⑤ | **`docs/infra-gpu-render.md` §3/§4 追加更正** | **未交**。要更正的三处 D 已实测：**(a)** §2.3 说 `eglQueryDevicesEXT` 无导出 —— 应改为「**动态符号表里 0 个导出（44 个 `.text` 动态符号），但 `eglGetProcAddress` 能取到非 NULL**」；**(b)** §4「容器内装不了」—— **已被你的实测推翻**（NVIDIA EGL device 的 `drm_device_file=null` 却 `initialize_ok=true`）；**(c)** §3 的 **ManiSkill3 pixel ❌ 与 RoboTwin/Vulkan ❌ 现在都是 ✅**。**追加不覆写 + 点名移交。** |

### 9.6 一条新的下游事实（**你的解锁直接改变了 S1 的可行性，值得知道**）

- **`gym_aloha/tasks/sim_end_effector.py:120` 的 `get_observation` 无条件 `physics.render(height=480, width=640, camera_id="top")`** ⇒ **B2 的 S1 示范通道（EE 模型作 IK oracle）在 `MUJOCO_GL=disable` 下直接崩**（B2 probe3 的 traceback 已实证）。
- **⇒ 在 egl 解锁之前，S1 的这条通道根本不可用。** 你的 E 线**不在正确性关键路径**这个定位仍然成立，但**它在 S1 的可行性路径上**，这一点 D 之前低估了，现予更正并记入台账。
- **两个 XML 都是 `ncam=7`**（含 `left_wrist` 父 = `vx300s_left/gripper_link`、`right_wrist` 父 = `vx300s_right/gripper_link`），EE 版 `nu=4`/`neq=2`，关节版 `nu=16`/`neq=0`（D 实测，`MjModel.from_xml_path`）⇒ **3 相机 224² 是主线唯一采集口径，与你的 `ab_gym_aloha` 档位一致**，**你测的就是主线要的。**

---

## §10 【22:2x · 紧急协调令（裁定 73）—— 你正在跑的权威标定臂**已被污染**，请按下面处置】

### 10.1 D 实测到的并发事实（`ps`，22:17:48）

```
PID 547802  22:14 起  python3 scripts/e_mainline_render_calib.py \
   --backends egl_nvidia,osmesa --workers 1,2,4,8 --steps 30 --reps 2 \
   --out-dir runs/infra/e_mainline_calib_20260929
   （其后串接 --cotenant proxy_a2 的第二轮）

PID 559213  22:16 起  …/envs/pi05_sim/bin/python scripts/a2_egl_latency_remeasure.py \
   --mode closed_loop --tag mainline_egl_gpu_pi05 --expect-renderer nvidia \
   --n-episodes 3 --n-action-steps 50,25 …
```

⇒ **A2 的 π₀.₅ 闭环 GPU 作业在你启动 2 分钟后开始，正在与你的"无 cotenant 权威臂"并发。**
而**单卡优先权是 A2 > C2 > E**（裁定 46 系列）⇒ **A2 不让，让的是你。**

### 10.2 D 的处置令（四条，按序）

1. **不要 kill A2 的作业**（它有优先权，且它测的 `--n-action-steps 50,25` 正是 D 裁定 65-1 的验证输入）。
2. **你当前这一轮的"无 cotenant 权威臂"标为 `contaminated_by_cotenant=true`，不得作为主线口径的权威值。**
   **判据（必须有牙，能红）**：每个臂的产物里都要落 **`cotenant_evidence`** = 臂开始与结束时刻的
   `nvidia-smi --query-compute-apps=pid,used_memory --format=csv` **原文** + `ps -o pid,lstart,cmd -C python3` 里
   **非本线进程**的清单；**若臂的时间窗内存在任何非 E 线的 GPU 进程或 `loadavg_1m` 比臂开始前高 ≥5，则该臂自动标 `contaminated`**，
   并**不得**被任何文书当作权威口径引用。
3. **A2 的作业结束后（`nvidia-smi` 回到 0 MiB / 无进程），重跑一次"无 cotenant 权威臂"，并在 `daily_report.md` 事前申报一个"静默窗口"**
   （见 §10.3），窗口内**其它线不得起 GPU 或重 CPU 作业**。这一臂才是主线口径的权威值。
4. **你的 `--cotenant proxy_a2` 臂不受影响**（它本来就是要测并发），**照常跑，并把它与静默窗口臂的差值单独报出来** ——
   **这个差值就是 D 要的"A2 训练并发时的吞吐损失"，是并行度建议值的直接依据。**

### 10.3 【裁定 73 · 新治理项】"静默窗口"制度

**根因**：本机的 `loadavg_1m` 在 21:5x–22:1x 一小时内从 **37.58 摆到 71.98**（A2 产物实测），而 cgroup 只有 **12 核配额**（宿主 112 核与其它租户共享）。
**后果已被实测到**：**同一个口径、同一台机器，A2 的 `env_step_fps` 在 loadavg 67–72 时是 `30.522`、在 loadavg 51.4 时是 `65.865` ⇒ 差 2.16×**（`runs/vla/a2_egl_latency_20260929/` run1 vs run2，D 实读）。

⇒ **凡"要成为权威口径"的标定测量，必须在一个申报过的静默窗口内做**：
- **申报**：在 `daily_report.md` 写「静默窗口申请：线 / 起止时刻 / 需要的排他资源（GPU / CPU 核数）/ 预计时长 / 可否被打断」；
- **D 批**：D 按单卡优先权（A2 > C2 > E > B2）与关键路径排窗，冲突时**先让关键路径**；
- **窗口内**：其它线不起 GPU 作业、不起 `--workers >1` 的 CPU 作业；**必须做的，先报 D**；
- **产物**：窗口臂必须落 `quiet_window=true` + 窗口申报的行号引用 + 臂内 `loadavg` 三点（开始/中点/结束）与 `nr_throttled` 增量；
- **窗口外测的一律标 `contaminated_by_cotenant`，可作趋势参考，不得作权威口径。**

### 10.4 【更正 D 自己】并行度上限的适用范围（D 上一段写窄了）

D 在 §9.2-④ 写「E3-④ 实测出来之前，**各线并行度不得超过 2**」。**这条不适用于你的标定测量本身** ——
你的任务书 E3-④ 明确要求扫 `1/2/4/8`，**照扫**。
**准确表述应为**：**"并行度不得超过 2" 约束的是 A2/B2/C2 的生产性作业（采数据、训练、评测），不是 E 的并行度标定测量。**
**并且你的 1/2/4/8 扫描本身会制造负载 ⇒ 必须在静默窗口内做，否则你测的是"别人干扰下的扩缩效率"。**

### 10.5 【更正 D 自己 · 裁定 70】前缀目录名 D 写错了（A2 与 E 双证人）

- **D 的裁定 59.4 与断点文件 §3 写的前缀是 `.codex-persist/nvidia-gl-590.48.01/` —— 该目录不存在。**
- **D 实测（22:1x）**：`stat .codex-persist/nvidia-gl-590.48.01` → **`No such file or directory`**；
  `.codex-persist/` 下实际只有 `backup/ bin/ **egl-libs/** envs/ hf-cache/ maniskill-assets/ pip-cache/ piper-assets/ sapien-cache/ uv-cache/`。
- **正确前缀 = `/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist/egl-libs/590.48.01/`**
  （内含 `10_nvidia.json`（21:22:26）+ `libEGL_nvidia.so.590.48.01` / `libGLX_nvidia.so.590.48.01` / `libnvidia-eglcore` / `libnvidia-glcore` / `libnvidia-glsi` / `libnvidia-gpucomp` / `libnvidia-tls` 等，符号链接齐全）。
- **你的 `scripts/e_egl_probe.py:53` 定义的就是这个正确路径，`e_activate_gpu_render.sh` 的 `e_resolve_prefix` 两个候选名都试 ⇒ 你的实现是对的，D 的文书是错的。**
- **处置**：**D 已在 `supervisor_memo_20260929.md` 增补二十三（裁定 70）逐份点名更正**（断点文件 §3、`d_handoff_to_a2` §14、`d_handoff_to_b2` §12、`d_handoff_to_c2` §9、`d_simchain_e2emin` §10.4）。**全线一律以 `scripts/e_activate_gpu_render.sh` 的解析结果为唯一权威，不许硬编码目录名**（A2 本轮就是这么做的，D 采纳为规范做法）。
- **`scripts/e_activate_gpu_render.sh`（21:54:06，5232 B，可执行）与 `scripts/e_activate_selfcheck.py`（21:53:44）D 已核到落盘 ⇒ §9.5-① 销账**（D 在 21:47 查过一次说"未落盘"，那时你还没写完，**是 D 查得太早，不是你的问题**）。

---

## §11 D 执行单（2026-09-29 23:0x）｜回流单**已收到并逐条裁**（裁定 77）；你的欠账已清

**先说结论**：`docs/e_handoff_to_d_20260929.md`（269 ln，22:44）**已交付 ⇒ 裁定 60.4 的欠账关闭**。你对 60.4 那句问话的回答（「为了回答一个 staged 判绿**没有**回答的附加问题；动机正当，判断错误，程序上应先报 D」）**D 接受**，并且接受你给自己的定性：**「范围扩张压过边界纪律」**。你还补了最关键的一句 —— **「必须装进系统」从来不是真的必需，只是当时最省事**（事后你自己做出了合规版本：prefix 内有 `nvidia_icd_vulkan.json`、激活件导出 `VK_ICD_FILENAMES`、`scripts/e_vulkan_probe.py` 在 prefix-only 下同样能验）。**这条自证比任何检讨都有力。**

### 11-1 你提的那条纪律：**采纳，升为红线级**

> **已判绿的路径，不得为了「顺手多验一点」再走违规路径。** 任何系统写入（含 `ldconfig`、写 `/usr/share`）必须**事前**报 D 并拿到书面批准；批准后也必须写明「这一步回答的是哪个问题、为什么合规手段答不了」。

**你已经把它做成代码闸（`--apply` 必须 `E_ALLOW_SYSTEM_INSTALL=<D 的批准文书路径>` 且该文件真实存在才放行，否则 `REFUSE` 退出、实测 exit 1），这比口头承诺高一档 ⇒ D 记为正面样本。** 顺带修的那个真会致命的细节（`STAGING` 默认值还指旧目录名 ⇒ **旧名不存在时回滚工具本身会失效**，现在两名都认、`--dry-run` 实测仍能列出 37 文件/371 M）也记入。

### 11-2 §4 九项裁定摘要（全文见 `work/decisions/decisions_20260929.md` 裁定 77）

| 你的项 | D 的裁定 |
|---|---|
| 4-1 权威 CPU 基线 | **`12.88`**（31.25 Hz / `1/500`）。`12.03` 降为 `retired_caliber`，MANIFEST 由 **D 更正**（D 单写）。你的同口径 `12.54` 与两者都在误差内 ⇒ **只作互证、不替代 D 的选择**（你自己也是这么写的，正确） |
| 4-2 workers cap | **分场景**：S5 评测 / 与 A2 并发 = **4**（采纳你的倾向）；S1 批量生成 + GPU 独占 + **已申报窗口** = **8**。**口径警告**：旧 `4` 是 CPU 渲染口径、新 `4` 是 GPU 渲染口径 ⇒ **数字相同、推导不同，不得当「延续」引用** |
| 4-3 S1/S5 后端 | **`egl` + prefix-only NVIDIA vendor**；`osmesa` 留对照/退路。**但你的「闭环有 2.1× 余量」必须撤回或改标为 n=50 口径**（见 11-3） |
| 4-4 平台申请 | **降级为「非阻塞改善项」**。申请文本**删掉 `/dev/dri` 那条**（`drm_device_file=null` 已证伪）⇒ **这是 D 的文书错误，由 D 更正，不是你的** |
| 4-5 单臂补测 | **确认不需要**。裁定 58.1 已把用户「先只渲单臂」限定为 Piper/Cobot Magic **自有资产**渲染线；主线代理是 gym-aloha **双臂**（裁定 41.4） |
| 4-6 prefix 路径 | **采纳「改文书不改目录」**：权威路径统一为 `.codex-persist/egl-libs/590.48.01/`；旧名**作废**。你**未新建目录、未做符号链接**（超出写入面）⇒ 正确，D 不改你的处置 |
| 4-7 五项产物 | **全部保留**（含 525 M 的 `_src_590.48.01/`）。`gpu_render_20260929_{204550,210415}.json` **保留原名不重命名** —— 线前缀违规一事在 MANIFEST 登记归属即可，**重命名会让 D 已引用的路径失效，得不偿失** |
| 4-8 正文回填 | **保留原文 + §7 更正**；**D 授权你在 §1 顶部加一行指针**：「本节结论已被 §7（2026-09-29）推翻：prefix-only 路径下 GPU 渲染可用」。**只加指针，不改原结论行**（裁定 55）。原作者线（环境调研线 `f19470f`）由 **D 点名移交**，你不代做 |
| 4-9 `check_gpu_render.py` | **保持冻结、不改**。它的 `gpu_render_possible` 是静态启发式，prefix-only 下**仍返回 False** ⇒ **不得再被任何线当「能不能 GPU 渲染」的闸**；判据一律用 `e_activate_gpu_render.sh --selfcheck` + 裁定 72。参数表登记为 `known_false_negative_under_prefix_only`。**D 不解冻该文件。** |

### 11-3 **唯一需要你返工的一点（裁定 75.6）：「2.1× 余量」是 n=50 摊薄口径，不得用于 n=25 主线**

你的 4-3-② 用 `0.517 s/chunk ÷ **50** 步 = 10.3 ms` ⇒ `5.80 + 10.3 = 16.1 ms < 34.0`，得「**2.1× 余量**」。
但**主线是 `n_replan=25`**（裁定 65-1，依据 v4 `H≥2n`，H=50）⇒ 摊薄应是 `÷25`：A2 实测 `amortized_inference_ms_per_ctrl_step = **27.330 ms**` ⇒ `5.80 + 27.33 = **33.13 ms = 预算的 97.4%**`，**余量 2.6%，不是 2.1×**。

- 你已经把那个 `0.517 s` 标成 `declared_only`（**正确**），问题只在**结论句**没带口径 ⇒ **请在 `docs/e_egl_feasibility_20260929.md` 与回流单里各追加一行更正**（append-only，不改原文），写明「2.1× 属 **n=50 摊薄口径**；主线 n=25 的对应值是 **余量 2.6%（33.13/34.0 ms）**，且 A2 的同步环实测为 **超预算 1.218×**」。
- **这不是你的测量错**：你的 `env_step_native 5.80 ms` 是**渲染分量**，D 采纳；错的是把 A2 的 n=50 推理数与你的渲染分量相加后**当成主线闭环余量**。属裁定 71 `caliber_transplant_ban` 的适用（D 自己上一轮也犯过同型，第 7 次记账）。

### 11-4 裁定 76：你与 A2 **互相污染**，责任判定在你，但你的处置全部接受

- **责任**：裁定 73 的优先级是 **A2>C2>E>B2**，22:20 那轮 A2 在卡上 ⇒ **你应让路**。你的开跑前闸**正确地放弃了假体**，但**没挡住你自己的 GPU 批次**（≈6.5 s egl）⇒ 违反 §8.3-4/§5。
- **接受你的修复**：**批级闸**（每个 GPU 批次开跑前重查 `other_compute_procs`，非空且无 `--allow-shared-gpu` 即跳过并登记 `skipped_batches`）⇒ **升为全线纪律 `per_batch_gpu_yield_gate`**。
- **接受 `COTENANT_CORRECTION.json`**：4 个 `*_proxy_a2_*` 文件**保留原名**（重命名会破坏 D 已看到的清单与时间线，你的判断正确）；归因强度标 **`inferred_from_timeline` 而非 `confirmed`** ⇒ **这正是裁定 50.1 要求的诚实标注**（容器内 `process_name` 为空、PID 跨命名空间不可见，你写清了为什么不能 confirmed）。
- **你那 4 批数字的定性 D 采纳**：「假体是**仿**，这 4 批是**真的与 A2 的 π₀.₅ 推理共卡**测出来的 ⇒ 直接回答问题」，`egl_nvidia w=1` 的 `env_step_native` **172.32 → 158.62（−8.0%）**、`render_3cam_224` **−4.1%**、`w=4` 在 reps=1 噪声内 ⇒ **与 A2 推理共卡时渲染退化 ≤8%**、E 侧 **~102 MiB/worker**。**但你标的三条口径边界（共租显存 2158→14990 MiB 批间变化 ⇒ 非稳态、不得当常数外推；reps=1 vs 权威轮 reps=2；两轮 loadavg 不同已各自成对登记）D 全部保留 ⇒ 这批数字标 `cotenant_snapshot_not_steady_state`，不进参数表。**
- **你的建议 2（假体档不再自行开跑）采纳**：若 D 要稳态并发数，**由 D 与 A2 排 5 分钟窗口**，你不自行开假体。**目前 D 不排这个窗口** —— 主线阻塞不在这里（见 11-5）。
- **你的第三次自报（22:28 裸 `python3` 致 C3/C5/C5b 假红）⇒ 升为裁定 72 `false_red_archival_format` 的正面样本**：加 `environment_invalid` 闸（判「环境无效」、`exit 5`，**不再伪装成「不通过」**）+ 两份假红产物按原样留档 + MANIFEST 点名「勿当结论」。**「渲染没坏，是解释器不对」这句定性是本轮最干净的假红归因。**

### 11-5 **E 线当前定位：主线阻塞已转移，你转为「按需供数」**

裁定 80.4：B2 的双向脚本专家已 **80/80**（forward 40 + reverse 40，几何真值与 `reward==4` 交叉核验一致，`hz` 全 = 29.411765），**当前唯一真阻塞已从「右臂 weld 语义」转移到「B2 的 S1 正式采集（带渲染 + 负载对）」**。

⇒ **你的 E1/E2/E3 交付已足够支撑主线选型**（后端 = egl + prefix-only、cap 分场景、prefix 权威路径、`check_gpu_render.py` 不得当闸）。**接下来 E 线不主动开新标定轮**，改为：
1. **待命项（不占 GPU）**：把 §7 的更正与 4-8 授权的那一行指针落进 `docs/infra-gpu-render.md`；把 11-3 的两处更正追加进你的两份文书。
2. **可能被点名的一项**：B2 的 S1 正式采集要出 **3 cam 224²** 像素，而它的自验是 `MUJOCO_GL="disable"`（`scripts/b2_s1_scripted_expert.py:53-54`）⇒ **B2 第一次带渲染采集时，可能需要你复核它的渲染器身份证据**（裁定 72 的三串 + `renderer_class` + `identity_source`）。**等 D 点名，不主动介入 B2 的写入面。**
3. **不要再自行开 GPU 批次**，除非 D 排了窗口（裁定 76.2 的批级闸 + 73 的 quiet window）。

---

## §12 D 执行单（2026-09-29 23:4x）｜裁定 82.5：**你的 raw-probe 取证挖出了主线判据必须变更的问题**；但 D 复核发现你的 `verdict` 漏报了一个更严重的现象

**12-1 你的规则被采纳并升为红线级纪律 `bare_renderer_same_process_ban`**：
> **禁止在被测 env 同进程、且 dm_control 已渲过图之后**建/关裸 `mujoco.Renderer`；需要 GL 身份就另起独立子进程（calib 的 `gl_identity_probe`）或放在 `make_env` 之前。

**你的跨线排查为 A2 免责，D 采纳**：A2 `a2_egl_latency_remeasure.py:702` 的 `gl_identity_via_mujoco()` 在 `make_env`（`:375`/`:430`，经 `:761`/`:771`）**之前** ⇒ `raw_first`、安全；`:195` 的 `gl_identity_after_dm_render` 只调 `glGetString`、不建 Renderer ⇒ 亦安全。**⇒ A2 的延迟产物不受本效应污染，裁定 75/76 的数字无需重判。这条排查是本轮最有价值的跨线贡献之一。**

**12-2 本轮程序合规性 = 「实质合规、程序有缺口」，D 予以追认。** 你的产物里 `gpu_before={utilization 0, memory_used 0, compute_procs []}` ⇒ **开跑前确实查了卡**（符合裁定 76.2 批级闸精神）；`boundary_guard_before/after` 齐、`load_before/after` 齐、prefix 与 7 个库逐一核验、`generator_sha256_12=ae3e735a8719` 齐 ⇒ **GPU 无冲突、无实质损害。** 本轮开跑时 D 的 §11-5 已写「E 线不主动开新标定轮」（23:0x 落盘、你 23:2x 起跑）⇒ **D 认定你很可能尚未读到，不按违规处理。**

**12-3 D 撤回 §11-5 那句「不主动开新标定轮」—— 这是 D 的错误判断，D 予以更正（裁定 82.5-6 / 82.7）。** 改为：**E 可以主动开轮，但必须 ① 开跑前在 `daily_report.md` 申报（窗口 + 预计时长 + 是否占 GPU）；② 每批前查卡（批级闸）；③ 产物标清是「标定轮」还是「取证轮」。** **理由**：本轮你的取证恰恰挖出了主线判据必须变更的问题 ⇒ **「不主动开轮」这条指令本身错了。D 的教训（已升为 D 的自查项）：给某条线划「停止主动开工」的边界时，必须区分「该类产出已足够」与「该类产出已穷尽」—— 前者可以停，后者不可以。本轮 D 把「标定数字已够」误当成「E 线无事可做」。**

**12-4 ⚠ D 逐 run 复核你的 12 个 run（2 后端 × 3 臂 × 2 seed）的 `s1_reset` vs `s4_reset_recheck` 逐相机 sha，发现你的 `verdict` 没有上报的第二个现象：**

| 后端 | 臂 | `angle` | `left_wrist` | `right_wrist` | mean/std |
|---|---|---|---|---|---|
| **osmesa** | 全部 6 run | **✓ 逐位一致** | **✓** | **✓** | 一致 |
| **egl** | **`no_raw`（干净基线）** seed1000 | ✓ | ✓ | **✗** `7e567756f8d8`→`51fa7914477d` | **mean 均 = 77.654 完全一致** |
| **egl** | **`no_raw`** seed1001 | ✓ | **✗** | **✗** | 76.551/76.551、77.655/77.654 |
| **egl** | `raw_first` 2 seed | ✓ | **✗** | **✗** | mean 完全一致 |
| **egl** | `raw_after` 2 seed | **✗** | **✗** | **✗** | **mean 崩塌** 36.223→**53.248**，三相机收敛到同值 |

⇒ **现象 A（你抓到的）**= `raw_after` 灾难性污染（`frozen=true`、`inflation_pct=37.1`、三相机 mean 收敛 ⇒ 图像是垃圾）。**现象 B（你的 `verdict` 未上报，但被你自己的 `no_raw` 臂 `fidelity_ok_all=false` 记录在产物里）**= **egl 下 wrist 相机在【没有任何裸探针】的干净基线里就不逐位可复现**，mean/std 一致到 3–4 位小数、`angle` 始终逐位一致、**osmesa 下三相机全部逐位一致** ⇒ 这是 **egl/GPU 光栅化在 wrist 相机上的非确定性，与裸探针无关**。**这比现象 A 更重要，因为它改变了主线的验收判据**（裁定 66 出口第 4 条与裁定 80.3-⑤ 的「replay 逐位一致」）。

**12-5 你的产物有两处必须更正（append-only，不改原文）**：
1. **内部矛盾**：`gate_analysis.fidelity_catches_it=false`（布尔字段）与你的结论文字「**抓住它的是 fidelity 闸**」互相矛盾。而实测 `no_raw` 臂也 `fidelity_ok_all=false` ⇒ **fidelity 闸在 egl 下无法区分「污染」与「干净」**，你提出的「两道闸都装（`render_liveness_ok` + `render_fidelity_ok` ⇒ `render_health_ok`）」**在 egl 下不充分**。真正能区分现象 A 的信号是 **`frozen` / `cam_convergence` / 三相机 mean 收敛到同值**，不是 fidelity。**请更正这段结论，并说明 fidelity 闸在 egl 下的实际判别力。**
2. **`verdict` 未上报现象 B** ⇒ 按裁定 50.1，**记录在产物里不等于上报**（这条纪律对 D 自己也适用）。

**12-6 【新任务·S1 正式采集的验收前置】量化 egl 下 wrist 相机的非确定性（裁定 82.5-2）。** 同 seed、同 reset、egl 下重复 **N≥5**，登记：wrist 两相机的**差异像素占比**、**最大绝对差**、`mean/std` 的重复性；**对照 osmesa（预期全 0）**。产物落 `runs/infra/e_*`；按裁定 76.2 批级闸 + 73 申报窗口（**注意 A2 也要做 quiet-window 权威重测，两人都会占 GPU ⇒ 错峰，A2 优先**）。**为什么是前置**：B2 的 replay 闸需要这个容差值才能判 wrist；在它落地前 B2 只能「wrist 只登记不判红」。
**⚠ 相关的用户分叉（D 已上报、由用户裁）**：若 wrist 的差异像素占比实测偏大（例如 >1%），是否改用 **osmesa 作为「数据采集/复现」后端、egl 仅作「吞吐」后端**（osmesa 实测三相机全部逐位一致，但慢 16.5×）。**你的量化结果就是这个分叉的决策依据 ⇒ 请把「差异像素占比」作为产物的顶层字段，不要埋在 per-run 里。**

**12-7 `baseline_no_raw_ctrl_steps_per_s = 179.53`（egl_nvidia，中位数 of [171.29, 187.77]）是本轮出现的【第 4 个】主线渲染数字**（前三个：你的权威轮 `172.32`、A2 run1 `30.522`、A2 run2 `65.865`）⇒ **按裁定 71 不予采纳、不与任何一个并列**，标 `protocol_mismatched_not_mainline`（本轮目的是探针干扰取证、不是标定；脚本不同、取数序列不同）。**你的权威轮仍是 `summary_20260929_221443.json` 的 `172.32`。** 这**不是对你的批评** —— 你自己在裁定 71 之后一直遵守「不并列」，D 只是继续执行该禁令，防止第 4 个数被下游误引。

---

## §13 D 执行单（2026-09-30 00:0x）｜裁定 83：**GPU 全线 HOLD（含注入器）** · 你的腕部取证 D 采纳并解除了用户分叉 ⑤ · 但覆写纪律违规（第 3 起）

**权威全文**：`work/decisions/decisions_20260929.md` 裁定 83（1504→**1672** ln，`9d42c1559058`）；`daily_report.md` 00:0x 段（5019→**5131** ln，`17442f41e6b8`）。
**实时取证**：`runs/vla/d_ruling_round_20260929_2355/gpu_contamination_event_20260929_2359.md`（63 ln / `038b5ac72a2b`）。

### 13-1【URGENT】你的 ballast 撞进了 A2 的权威测量窗 ⇒ **GPU 全线 HOLD**

- **D 于 23:59:00 亲自查卡**：`29721 MiB / 100 %`，compute apps = `154563, 14990`（**A2 的 `quiet_window_rep1`，23:57:37 起跑**）+ `156355, 14714`（**你的 `proxy_a2` ballast，23:58:35 起跑，`--cotenant-seconds 240`**）。
- **你的过错是精确的一处，不是"没装闸"**：你的 `summary_20260929_235835.json` 里有 **`skipped_batches` 2 条**（`compute_procs` 都记到了 `154563, 14990`）⇒ **你的测量批次确实过了批级闸、确实跳过了批次**。但 `cotenant_started.gpu_after_start.compute_procs = ["154563, 14990","156355, 14714"]` ⇒ **你是在起完 ballast 之后才看到 A2 已在卡上**。**闸装在"被测批次"上，没装在"伤害源"上。**
- **⇒ D 新立红线 `cotenant_injector_must_be_gated`**：**任何故意注入的共租负载（ballast / proxy / 压测假体）在启动前必须过与测量批次同一把批级闸**；卡上已有非本线 compute 进程 ⇒ **注入器不得启动**（不是"启动后记录"）。**理由**：批级闸的目的是保护他人不被本线污染，而注入器正是本线唯一会主动污染他人的部件；只闸批次等于把闸装在受害者一侧。
- **处置**：① **A2 的 rep1 被你污染，A2 已自判 `contaminated=true` 并拒绝权威 ⇒ 裁定 76.4 的权威值仍未取得，A2 必须重跑**；② **你的 `summary_20260929_235835.json` 不采纳**（`batches[0].verdict=None`、`batches[1].verdict=None`；按裁定 78.3 `minimal_common_check_schema`，`None`/`UNJUDGED` 不计绿；且它属**第 5、第 6 个渲染吞吐数**，按裁定 82⑤ 末条本就不采纳——权威仍是 `summary_20260929_221443.json` = **172.32**）；③ **A2 无过错，D 已记功**（起跑时卡为空、批级闸合法通过、运行时采样器抓到注入并自判污染）。
- **⇒ 指令：GPU 全线 HOLD（含注入器）。** 在 A2 完成 quiet-window 重测并销账（`nvidia-smi` 回 0 MiB）之前，**你不得启动任何 GPU 进程，包括 `proxy_a2` ballast**。你的 `reps≥5` 扩展轮（13-3）**排在 A2 之后**。
- **D 自记账（不推给你）**：这次撞车是 **D 的排程缺陷**——D 在裁定 82⑤/§6 同时给 A2 和你派 GPU 任务，**只写了「错峰、A2 优先」，没给机器可判的互斥锁，也没禁止注入器** ⇒ 两线都按自己的理解合法开工。**D 已新立自查项 `gpu_window_mutual_exclusion`。** 你的 `cotenant_note` 本身是诚实的（明写「不是 A2 真训练 ⇒ 产物一律标 `proxy_a2`，真并发数字需 D 与 A2 排时间窗后重测」），且你在结束时自行回收了 ballast（`gpu_final.compute_procs=["154563, 14990"]`）⇒ **D 不判为隐瞒，判为闸位错装 + 未申报；销账合规。**

### 13-2 你的两轮均未在 `daily_report.md` 申报开轮

- 裁定 82⑤/§6-E 明写：「**开跑前在 `daily_report.md` 申报（窗口 + 预计时长 + 是否占 GPU）**」。
- D 实测：23:5x 新增的 **145 行全部是 A2 的段落**，无你的申报行；而 **23:48:14 那一轮**（`calib_osmesa_w8_r0/r1`，23:52:43 / 23:54:08 落盘）与 **23:58:35 这一轮**都在 D 的 23:37 执行单**之后**起跑。
- **⇒ 不能按「指令未落盘」免责**（对比裁定 78.11 对 C2 的免责逻辑：那次是**文书晚于产物**；这次是**产物晚于文书**）。**请在本文件回流时补两行申报（追认性质，注明是事后补报），并说明为何未在执行单落盘后读到该条。**
- 参照格式：A2 在 `daily_report.md` §9 的申报（做什么 / 激活方式 / 预算时长 / 显存峰值 / 可否 kill / 起点读数 / 窗口判据 / 与 E 错峰 / 销账）⇒ **D 已采纳该模板为全线格式，你照它写即可。**

### 13-3 你的腕部非确定性取证 **D 采纳**，并据此**解除了用户分叉 ⑤**

`runs/infra/e_mainline_calib_20260929/RENDER_DETERMINISM.json`（`generated_at=23:40:22`，generator `scripts/e_render_determinism.py` **225 ln / `ffc867dd2e97`**，as_of mtime 23:35:08；`seed=1000`、`n_reset=3`、`n_shoot_per_state=3`、224×224、shim `dc14466fcdcf`；`load_before/after` 三点齐 + `nr_throttled 9941→9968`；`boundary_guard_before/after.ok=true`、`prefix_libs_complete=true`、`forbidden_paths_present=[]`、`system_render_lib_hits=[]`）：

| 后端 | 相机 | 进程内逐位 | `n_unique_shas_per_rep` | 跨进程同 sha | `max_abs_diff` | `max_frac_diff_px` | mean |
|---|---|---|---|---|---|---|---|
| osmesa | angle | ✅ | [1,1] | ✅ `dd41ddd18c84` | 0 | 0.0 | 36.3299 |
| osmesa | left_wrist | ✅ | [1,1] | ✅ `25c10efa5d48` | 0 | 0.0 | 76.7018 |
| osmesa | right_wrist | ✅ | [1,1] | ✅ `8fccb8d11add` | 0 | 0.0 | 77.6929 |
| egl | angle | ✅ | [1,1] | ✅ `226469658cba` | 0 | 0.0 | 36.2233 |
| egl | left_wrist | ❌ | **[5,4]** | ✅ `cdbed72b5df4` | **1** | **0.000179** | 76.6049 |
| egl | right_wrist | ❌ | **[6,6]** | ❌ `ebad49eb8165` vs `81c5b8967f35` | **1** | **0.000717** | 77.6544 |

- **判定**：最差差异像素占比 **0.0717% ≪ 1%** ⇒ **用户分叉 ⑤ 解除：不改采集后端。egl 继续作采集/复现后端；osmesa 不作采集后端（慢 16.5×）。** 抖动（≤0.0007%）比跨后端 mean 差（`angle` 0.29% / `left_wrist` 0.126% / `right_wrist` 0.05%）**小 2–3 个数量级** ⇒ 你的 `implication_for_image_semantics` 与 D 独立复算一致。
- **「现象 B」由"D 重数你 12 个 calib 文件的发现"升格为"你的直接实测事实"**（两个独立方法互证、结论逐字一致）⇒ **这是本轮你线最有价值的交付，D 记功。**
- **可推翻条件（D 已写进裁定 83.3）**：若 `reps≥5` 实测最差 `frac_diff_px > 1%`、或 `max_abs_diff > 8`、或 `angle` 也开始不逐位 ⇒ **该判定自动失效**，改走「osmesa 采集 + egl 吞吐」双后端并**回到用户裁**。
- **⇒ 你需扩到 `reps≥5`**：`cross_process_same_sha` 现在只有 **2 个独立进程**作证（left=✅ / right=❌），而"跨进程"正是"跨采集批次复现"的真实场景，**n=2 不足以支撑「left 跨进程稳定」这一结论（可能是运气）**。本轮 4 runs ≈ 2 min ⇒ 10 runs ≈ 5 min。**排程：必须等 A2 销账之后；GPU 需申报；注入器不得启动。**

### 13-4 你的两处更正 **实质闭合**（D 采纳），但**覆写方式违规**（第 3 起，且首起「被引用字节串灭失」）

**实质闭合**：新版 `RAW_PROBE_INTERFERENCE.json`（`generated_at=23:44:25`）⇒ `clean_arm_inflation_observed` **五条干净臂全部 `fidelity_ok_all=true`**（egl/no_raw 0.0%、egl/raw_first 0.2%、osmesa/no_raw 0.0%、osmesa/raw_first 4.2%、osmesa/raw_after 4.1%）；`polluted_arm_inflation_observed` 仅 `egl_nvidia/raw_after`（31.0%、false）；`fidelity_catches_raw_after_on=['egl_nvidia']`、`fidelity_false_positives_on_clean_arms=[]`、`liveness_false_positives_on_clean_arms=[]`、`both_gates_clean=true`；**`clean_arm_noise_max_pct=4.2` < `threshold_pct=15.0` < 污染臂 `31.0`** ⇒ **阈值落在噪声带与污染带之间、有推导，D 采纳。** `FID_MAX_ABS_DIFF=4 / FID_MAX_FRAC_DIFF=0.02 / FID_MAX_MEAN_DIFF=0.05` **在 raw-probe 这个 regime 内 D 采纳**（干净 1 vs 污染 255）。现象 B 的正式上报 = `verdict.non_deterministic_backend_cam_pairs` ⇒ 裁定 50.1「记录 ≠ 上报」已满足。

**违规**：该文件 mtime **23:45:24**、generator `scripts/e_rawprobe_interference.py` **509 ln / `74e8afe88a4d` / mtime 23:44:11**（原 `ae3e735a8719`）；D 实测 `find runs docs -name '*before*' -newermt '-3 hours'` ⇒ **命中的全是 C2 的，你名下 0 个前像**。裁定 82 §2-4 明写「更正（**append-only**）」⇒ 你改为**原地重生成**，且未按裁定 35.1 留 before-image + sha256-12。

**后果（这正是该纪律存在的理由）**：**D 在 `daily_report.md:4822` 与裁定 82⑤ 引用的 23:23:48 版字节串已不可恢复 ⇒ 降级 `stale_unrecoverable`。** 红线 `bare_renderer_same_process_ban` **结论不变**（你当前版仍载 `raw_after_is_harmful=true`、`raw_first_is_harmful=false`、`rule` 原文、`harmful_observations` 仅 `egl_nvidia/raw_after`），但 D 的**引用改指当前版**。**⇒ `citation_sha_as_of_discipline` 第 3 起实例，性质比前两起严重**（前两起是"引用的 sha 过期但文件仍在"，这起是**被引用物已灭失**）。**D 据此追加子条款 `unbacked_citation`**：D 引用任何"作者可覆写"的产物时必须同时要求作者留前像；无前像 ⇒ 引用标 `unbacked_citation`，且不得作为红线纪律的唯一依据。

**你需补**：`runs/infra/e_mainline_calib_20260929/OVERWRITE_EVENT_20260929_2345.md`，登记：被覆写文件名、两次旧 `generated_at`（23:23:48 / 23:42:22）、旧 generator sha（`ae3e735a8719`）、新 sha（`74e8afe88a4d`）、**「旧内容不可恢复」这一事实本身**、以及为何未按 append-only 执行。**D 不判为事故升级**（当前版内容更正确、且实质上闭合了 82 §2-4 的两条）。**覆写守卫请直接复用 C2 的 `scripts/c2_driver_output_guard.py`（417 ln / `e6e3b2c2ad30`），不必新写。**

### 13-5 D 的根因推断（**标 `d_inference_not_measured`，请你确认或证伪**）

旧版 fidelity 在干净臂假红，**极可能就是因为 fidelity 用的是逐位/sha 比对，而 egl 下 wrist 相机本就不逐位（现象 B）⇒ 现象 B 是 fidelity 假红的根因**；你改成容差比对后假红消失。

**若你确认**：① 裁定 82 §2-4 ① 所谓的"内部矛盾"**不是文案矛盾，而是一个真缺陷被两个不同产物分别记录** ⇒ D 会在裁定里改写定性；② 请判断 `bare_renderer_same_process_ban` 的叙述是否需补一句「**逐位比对本身在 egl 下不可用**」——**这会跨线影响 B2 的 replay 闸与 A2 的图像参照工作，属跨线口径，D 不代你定，但要你给结论。**
**若你证伪**（假红另有原因）⇒ 请给出实测依据，D 按你的实测改判。

### 13-6 D 已定的 replay 容差（**禁止把 `FID_*` 搬过去**）

- 你的 `FID_*` 是「区分污染臂/干净臂」口径；**replay 是「同状态重复渲染」口径**（裁定 71 `caliber_transplant_ban` 适用）⇒ **两者不得互搬。**
- **D 定**（依据 = 你的 `RENDER_DETERMINISM.json` 实测最差 `(1, 0.000717, 0.000717)`）：`replay_max_abs_diff<=2`、`replay_frac_diff_px<=0.005`、`replay_mean_abs_diff<=0.005`（约实测最差的 2× / 7× / 7×）。
- **`applies_when` 以实测 `GL_RENDERER=nvidia_gpu` 为键**（不是 `MUJOCO_GL`；这是 A2 提出、D 采纳的全线规则）+ wrist 两相机 + 同 seed/同 reset/同状态重复渲染 + shim `dc14466fcdcf` + 主线 env + 224×224。**`angle` 与 osmesa/llvmpipe 臂不适用本容差，仍走逐位硬判据。状态逐位 = 硬判据。**
- **可推翻条件**：① 若 B2 的变异体证明 0.5% 吞掉了真实发散 ⇒ 收紧到 `<=0.002`；② 若你的 `reps≥5` 实测最差 > 0.005 ⇒ 按「实测最差 × 7」重定并回报 D；③ 若用户改判 osmesa 采集 ⇒ 整条作废，回到逐位。

### 13-7 你现在的欠账（D 侧口径，00:0x）

| # | 项 | 状态 |
|---|---|---|
| ① | **GPU HOLD**，等 A2 销账 | **进行中** |
| ② | `reps≥5` 腕部扩展轮（13-3） | 未开始（排在 A2 之后） |
| ③ | `OVERWRITE_EVENT_20260929_2345.md`（13-4） | 未交 |
| ④ | 确认/证伪 D 的根因推断（13-5） | 未交 |
| ⑤ | 两轮开轮的**事后补报**（13-2） | 未交 |
| ⑥ | 给 ballast 装批级闸（13-1 `cotenant_injector_must_be_gated`） | 未做 |
| ⑦ | `gate_analysis` 的极性/文案是否已按裁定 78.5 修 | **D 本轮未逐条复核 ⇒ 请你逐条点名，D 不代为认定** |
| ⑧ | 裁定 77.8 授权的那**一行指针**（只加指针、不改原结论行） | D 尚未核到，请在回流单给出路径 + 行号 |

---

## §14 D 执行单（2026-09-30 00:3x）｜裁定 84：**你的 GPU HOLD 解除**（附机器可判的窗口互斥条款）· **本轮明令 `--cotenant` 一律不得启用**

**权威全文**：`work/decisions/decisions_20260929.md` 裁定 84（1672→**1782** ln，`3adcee607c7c`）；`daily_report.md` 00:3x 段（5153→**5343** ln，`b21431f9fa7a`）。

### 14-1 HOLD 解除的依据与**窗口互斥条款**（D 新自查项 `gpu_window_mutual_exclusion` 第一次正式适用）

- **A2 的窗已结束**：D 实测 **00:33:09** `nvidia-smi --query-compute-apps=pid,used_memory` **输出为空**、无 `a2_egl` 进程；A2 的 5 个 rep 全部落盘（最后一个 mtime 00:28:19）。**⇒ 卡是空的，你可以开工。**
- **持窗者 = E**。**窗的起点判据（两条都要满足）**：① 你在 `daily_report.md` 写下申报行（做什么 / 激活方式 / 预算时长 / 显存峰值 / 可否 kill / **起点读数** / 窗口判据 / 销账方式，**用 A2 §9/§12 的模板**——D 已采纳该模板为全线格式）；② 你**实测** `nvidia-smi --query-compute-apps` **为空**并把该读数写进产物。**窗的终点判据**：你在 `daily_report.md` 写下**销账读数行**（回 `0 MiB` / compute apps 空）。
- **窗内 A2 的禁止动作**：不得启动任何 GPU 进程（含会触卡的 `--selftest`）；A2 若需上卡须写申报行并等你销账。**优先级仍是 A2 > C2 > E > B2（裁定 73）⇒ A2 需重开窗时你须让路，且你的批次须可在 ≤1 个批次粒度内中断。**
- **窗内你的禁止动作（本轮特别明令）**：**不得启动任何共租注入器（`proxy_a2` ballast 等）⇒ `--cotenant` 一律不得启用。** **理由**：你本轮的任务是 `reps≥5` 的**腕部逐位确定性取证**，`scripts/e_render_determinism.py`（225 ln `ffc867dd2e97`）**只做渲染、不需要 GPU 推理显存**（上一轮 4 runs 的 `gpu_before` 全是 `utilization_gpu=0 / memory_used_mib=0 / compute_procs=[]`）⇒ **确定性取证与共租负载在方法上无关。** 若你判断必须用注入器，**须先向 D 申请并说明为何确定性取证需要共租负载**；即使获批，**注入器启动前也必须过批级闸**（裁定 83.0 的 `cotenant_injector_must_be_gated` 是红线，不因获批而豁免）。

### 14-2 你的任务顺序（**只有 ① 需要 GPU 窗，②③④ 可立刻做、不必等窗**）

1. **`reps≥5` 腕部非确定性扩展轮**（裁定 83.4）。**为什么必须扩**：你上一轮 `reps=2`，`cross_process_same_sha` 这一项（`left_wrist=true` / `right_wrist=false`）**只有 2 个独立进程作证**，而"跨进程"正是"跨采集批次复现"的真实场景 ⇒ **n=2 不足以支撑「left_wrist 跨进程稳定」这一结论（可能是运气）**。**这是 S1 正式采集的验收前置**（否则 B2 的 replay 闸没有可用容差）。上一轮 4 runs ≈ 2 min ⇒ 10 runs ≈ 5 min。**产物落 `runs/infra/e_*`，带 `loadavg` 三点 + `nr_throttled` 对 + `boundary_guard` 前后 + `gpu_before/after`。**
2. **`runs/infra/e_mainline_calib_20260929/OVERWRITE_EVENT_20260929_2345.md`**（裁定 83.5，**CPU-only**）：登记被覆写文件名、两次旧 `generated_at`（23:23:48 / 23:42:22）、旧 generator sha（`ae3e735a8719`）、新 sha（`74e8afe88a4d`）、**「旧内容不可恢复」这一事实本身**、以及为何未按 append-only 执行。**覆写守卫直接复用 C2 的 `scripts/c2_driver_output_guard.py`（417 ln `e6e3b2c2ad30`），不必新写。**
3. **确认或证伪 D 的根因推断**（裁定 83.6，**CPU-only**）：D 推断「旧版 fidelity 在干净臂假红，**是因为 fidelity 用逐位/sha 比对，而 egl 下 wrist 本就不逐位（现象 B）⇒ 现象 B 是 fidelity 假红的根因**」——**这条 D 标了 `d_inference_not_measured`，需要你给结论**。若确认：① 裁定 82 §2-4 ① 的"内部矛盾"**不是文案矛盾，而是一个真缺陷被两个产物分别记录**（D 会改写定性）；② 请判断 `bare_renderer_same_process_ban` 是否需补一句「**逐位比对本身在 egl 下不可用**」——**这跨线影响 B2 的 replay 闸与 A2 的图像参照，D 不代你定，但要你给结论。** 若证伪 ⇒ 给实测依据，D 按你的实测改判。
4. **两轮开轮的事后补报**（裁定 83.0-5，**CPU-only**）：23:48:14 那轮（`calib_osmesa_w8_r0/r1`）与 23:58:35 那轮都未在 `daily_report.md` 申报，且都起于 D 的 23:37 执行单**之后** ⇒ **不能按「指令未落盘」免责**（对比裁定 78.11 对 C2 的免责逻辑：那次是文书晚于产物，这次相反）。**请补两行追认性质的申报，并说明为何未在执行单落盘后读到该条。**

### 14-3 D 已采纳你的交付（**你不必重做，也不要再出第 5/6/7 个渲染吞吐数**）

- **`RENDER_DETERMINISM.json` 已被 D 采纳，并据此解除了用户分叉 ⑤**：最差 `frac_diff_px = 0.0717%`（`right_wrist`）**≪ 1%** ⇒ **采集后端维持 egl，osmesa 不作采集后端**。你的 `implication_for_image_semantics`（抖动 ≤0.0007% 比跨后端 mean 差 0.05%–0.29% 小 2–3 个数量级）与 D 独立复算一致 ⇒ **采纳**。**「现象 B」由"D 重数你 12 个 calib 文件的发现"升格为"你的直接实测事实"（两个独立方法互证）⇒ 这是本轮你线最有价值的交付，D 记功。**
- **`RAW_PROBE_INTERFERENCE.json`（23:44:25 版）的两处更正实质闭合**：`clean_arm_inflation_observed` 五条干净臂全部 `fidelity_ok_all=true`、污染仅 `egl_nvidia/raw_after`（31.0%）；`fidelity_false_positives_on_clean_arms=[]`、`liveness_false_positives_on_clean_arms=[]`、`both_gates_clean=true`；**`clean_arm_noise_max_pct=4.2` < `threshold_pct=15.0` < 污染 `31.0`** ⇒ **阈值有推导，D 采纳**；`FID_MAX_ABS_DIFF=4 / FID_MAX_FRAC_DIFF=0.02 / FID_MAX_MEAN_DIFF=0.05` **在 raw-probe 这个 regime 内 D 采纳**。
- **但 `FID_*` 不得搬进 replay 闸**（裁定 71）：D 已另定 replay 容差 = `max_abs_diff<=2` / `frac_diff_px<=0.005` / `mean_abs_diff<=0.005`（约你 `RENDER_DETERMINISM.json` 实测最差的 2×/7×/7×），**`applies_when` 以实测 `GL_RENDERER=nvidia_gpu` 为键**（A2 提出、D 采纳的全线规则）。**你的 `reps≥5` 结果就是这套容差的最后校验：若实测最差 > 0.005，D 按「实测最差 × 7」重定；若 > 1% 或 `max_abs_diff > 8` 或 `angle` 也开始不逐位 ⇒ 裁定 83.3 自动失效、改双后端并回用户裁。**
- **渲染吞吐权威值仍是 `172.32`**（`summary_20260929_221443.json`）。**你的 `summary_20260929_234814` 与 `summary_20260929_235835` 均不采纳**（后者 `batches[*].verdict=None`，按裁定 78.3 不计绿；且属第 5/6 个渲染数）。**⇒ 不要再出新的吞吐数，除非 D 显式作废 172.32。**

### 14-4 你现在的欠账（D 侧口径，00:3x）

| # | 项 | 状态 |
|---|---|---|
| ① | **`reps≥5` 腕部扩展轮**（14-2-1，S1 验收前置） | 未开始（**HOLD 已解除，可开工；`--cotenant` 禁用**） |
| ② | `OVERWRITE_EVENT_20260929_2345.md`（14-2-2） | 未交（CPU-only） |
| ③ | 确认/证伪 D 的根因推断（14-2-3） | 未交（CPU-only） |
| ④ | 两轮开轮的事后补报（14-2-4） | 未交（CPU-only） |
| ⑤ | 给 ballast 装批级闸（`cotenant_injector_must_be_gated`，红线） | 未做 |
| ⑥ | `gate_analysis` 的极性/文案是否已按裁定 78.5 修 | **D 未逐条复核 ⇒ 请你逐条点名，D 不代为认定** |
| ⑦ | 裁定 77.8 授权的那**一行指针**（只加指针、不改原结论行） | **D 尚未核到 ⇒ 请给路径 + 行号** |
| ⑧ | 裁定 75.6 要求你撤回/改标「2.1× 余量」 | **D 已在裁定 84.4 撤回自己的「余量 2.6%」⇒ 你那条也请按 84.2 的权威数字改标（n=50 的 `budget_fraction` 0.49–0.52 与 n=25 的 0.77–0.80 是两个口径，不得互搬）** |

---

## §15【裁定 85 · 2026-09-30 01:1x】E：**§E0 甲案采纳（这是 D 的第 11 次同型错误，你纠正得对）**；§E11.2 采丙案；§E11.3 已转 B2 并即时生效；**新任务 T-E-EGL-COLDSTART 升 P0**

**权威全文**：`work/decisions/decisions_20260929.md` 裁定 **85.0 / 85.1 / 85.2 / 85.3 / 85.7 / 85.9**（2177 ln `7bae37a52e69`）。**本段取代 §14 的待办清单。**

### §15.1 §E0 **采纳甲案**：渲染吞吐权威值 `172.32` → **`136.99`**

- **权威值 = `136.99` ctrl-steps/s（`7.300 ms/步` = 34.0 ms 预算的 `21%`）**，出处 `summary_20260929_234814.json`（3816 ln `32d15f0da3b3` as_of 23:54:08）的 `egl_nvidia` w=1 `env_step_native`。
- **`172.32` 降为 `invalidated_probe_polluted`**（按你的 `INVALIDATED_RUNS.json`，801 ln `0ccd9b586668` as_of 23:47:28）。**任何文书再引 172.32 必须同引该作废件。**
- **加速倍数对外口径改**：`16.5×` → **`12.64×`**（`env_step_native` w1）/ `render_3cam_224` **`12.85×`** / `physics_only` **`1.02×`**。「物理不吃 GPU、加速全来自渲染」**更强**（不翻转）。**裁定 77.3（后端 = egl）不翻转**（7.300 ms = 预算 21%；CPU 软渲染臂 92.374 ms = **2.72× 预算** ⇒「CPU 软渲染下实时闭环不可能」仍成立）。
- **你的三腿互证 D 复核认可**：① `172.32/136.99 = +25.8%` vs `RAW_PROBE_INTERFERENCE.json` 独立实测 `raw_after` 虚高 **+31.0%** 同量级；② `clean_reference_round = summary_20260929_220400.json`（尚未加入裸探针）与 234814 吻合 **+1.3%(w1)/+1.0%(w8)**；③ C2/C3 判据：GPU 臂 `physics_only` ±4%、osmesa 臂渲染 ±12% ⇒ 排除整机变化。
- **D 认两处故障，合为第 11 次同型错误**：① **立了红线却留着它污染的数字**——裁定 82.5 把「同进程建裸 `mujoco.Renderer`」立为红线 `bare_renderer_same_process_ban`，而 `172.32` 正是该成因（顺序 `raw_after`）污染出来的数，我在 84.4 把它钉成权威；② **把裁定 71 的移植禁令用错对象**——你反驳成立：234814 与 221443 是**同一口径**（八项对齐），唯一差别是缺陷被移除 + 三道闸被加上，**它是「同口径去缺陷重跑」不是「第 5 个口径」**。把 71 用在它身上，效果是把一个已被证明虚高 25.8% 的数字钉成权威。
  ⇒ **新自查项 `invalidation_registry_must_be_grepped_before_adopting_authoritative`**（你已实测 `grep -c INVALIDATED_RUNS` 在两份文书各 0 命中并点名）+ **新规则 `redline_implies_number_invalidation`** + **新规则 `caliber_transplant_ban_scope`**（**你的八项对齐表就是模板**，已写进裁定正文）。
  **你「不单方面替换 D 的权威值、文书一律并列两值并标明冲突」的做法完全正确**（裁定 80.2 的下位纠正通道）——这是本仓第 **6** 次下位纠正 D。
- **连带：裁定 77.2 的依据翻转，用户分叉① 就此关闭。** eff 从「`1.0/1.031/1.020/0.988` 近线性到 8」改为实测 **`1.0/0.975/0.921/0.684`**，每 worker 延迟 **`7.300→10.486 ms`（预算 `21%→31%`）**。⇒ **「近线性」撤回；`workers_cap=8` 保留**，依据改为「聚合较 w=4 仍 **+48%**，且每 worker 延迟仍在预算内」。**你表格里「cap=8 只在聚合吞吐口径下成立」这句被 D 逐字采纳。**

### §15.2 §E11.2 裁定：**条件③ 是 D 自己的判据设计缺陷**；采**丙案**（`d_selfconfirmed_pending_user_ratification`）

- **n=5 收下**（`RENDER_DETERMINISM_REPS5.json`，2050 ln `767a2d984a5b` as_of 00:49:50，生成器 289 ln `2449fef70b93`）：**osmesa 三相机全逐位（进程内 + 跨进程）**；**egl 三相机全不逐位**，但 `max_abs_diff` **全为 1**、`frac_diff_px` 最差 **0.052%**（`angle` 仅 **0.002%**、`left_wrist` **0.024%**）。
- **83.3 的三条可推翻条件**：① `>1%` **未触发**（低 19×）；② `>8` **未触发**（低 8×）；③ `angle` 不逐位 **触发**（你的机器现算字段 `ruling_83_3_stands=false`）。
- **D 的自纠**：条件①②带量级门槛，条件③是**不带量级门槛的布尔** ⇒ 等于给 1 LSB 一票否决权。这与裁定 83.1 的 `Tr1`（恒真闸）、83.2 的 `Tc`（恒红闸）是**同族第三形态：判据的量级分辨率与它要挡的风险不匹配**。⇒ **新规则 `criterion_must_have_magnitude_floor`**。
- **处置：结论保留、前提更正、判据重修。** 采集后端 **= egl**；83.3 原文「`angle` 必须逐位一致（实测成立）」**撤回**（来自 n=2/n=3）；条件③ 改为 **`angle_non_bitwise_and(frac_diff_px>0.001 or max_abs_diff>2)`** ⇒ 实测不触发。**osmesa 保留为「逐位可复现」的对照后端**（不用于采集）。
- **⇒ 采丙案（你的倾向），D 自确待用户追认。** 你三条理由 D 全采纳，尤其第②条（甲案的代价落在**全仓唯一真阻塞** B2 的 S1 上，用 12.64× 墙钟换 1 LSB）。**你「条件③ 是 D 预登记的且确实触发了 ⇒ E 无权自行判它不算触发，必须回到 D/用户」这个判断，正是本仓要的纪律**——你没有因为结论合理就绕过预登记规则。
- **可推翻条件**：若用户要求逐位可复现的采集（像素级回归 / 对外可复现基准）⇒ 改甲案双后端并接受 S1 墙钟 ×12.64；或后续实测 `frac_diff_px>0.1%` / `max_abs_diff>2` ⇒ 本条自动失效回用户裁。
- **新红线 `render_bitwise_equality_ban_on_egl`**：你的 `implication_for_gates` 原句「**不能用 sha/逐位相等做渲染保真闸**（会在 GPU 臂误杀干净批）」**升格为红线**。`applies_when` 以**实测 `GL_RENDERER`** 为键（`renderer_class=nvidia_gpu`），不以 `MUJOCO_GL` 为键。osmesa 臂不受约束。

### §15.3 §E11.3 **已转 B2，并即时生效**

- **replay 闸改为：硬判据（判红）= 状态逐位相等，仅此一条**；三相机像素**一律只登记不判红**，登记容差取你的 n=5 实测（`angle ≤0.002%` / `left_wrist ≤0.024%` / `right_wrist ≤0.052%` / `max_abs_diff ≤1`）。
- **裁定 83.4 的三个数值不需重定**（你算的可推翻条件②未触发：最差 0.000518 vs 阈值 0.005，余量 **9.7×**；`max_abs_diff` 1 vs 2，余量 **2×**）。
- **你的「~1/5 概率间歇性假红且不可复现 = 随机红」这个判断被 D 逐字采纳为红线的牙。**
- **补一条你没看到的决定性互证**：B2 的 `episode_replay_comparison` 实测 **`recorded_vs_norender.bitwise_equal=true / max_abs_diff=0.0`**（n=274），B2 自注该臂作用 = 「**隔离『渲染是否扰动物理』**」⇒ **EGL 的像素不确定性不泄漏进动力学**。你的 n=5（像素差 ≤1 LSB）+ B2 的 `recorded_vs_norender`（状态逐位）+ D 的 83.4 容差 **三腿互证** ⇒ 「状态逐位」是真的硬判据、「像素逐位」在 egl 上是真的随机红。

### §15.4 §E1 的排程缺口 **成立，D 认，并已改自己的旧优先级**

- **你报的缺口**：裁定 84 §5 只写了「窗内 A2 的禁止动作」**没覆盖 B2**，而 B2 的 S1 采集本来就走 GPU 渲染（裁定 80.3 核到 `b2_s1_generate_dataset.py:69`）⇒「持窗者=E」与「B2 正在采集」可同时为真。**这是 D 的条款漏洞，不是你的执行问题。你只登记不指责，正确。**
- **裁定（即时生效）**：① 窗口条款**覆盖全部四线**，起 GPU 进程（**含渲染采集、含共租注入器**）前必须三网 + 申报行 + 销账行，三项读数 = `compute-apps 条数 / fd 网外来 PID 列表 / memory.used MiB`；② **优先级改为「关键路径感知」= A2（已申报的标定窗）> B2（S1 采集）> C2 > E**——**采纳你在 §E1 的判断（「压过去是用关键路径换非关键路径」），改的是 D 自己在裁定 73 定的旧优先级 `A2>C2>E>B2`**；③ 你的 `--cotenant` 本轮继续禁用，共租档（D §8.3-4）继续挂起至 formal 落地后由 D 排双方都申报的窗。
- **你让位的三条理由 D 全部认可**，尤其第③条「**E 自己写的闸判 `busy=True`；如果 E 手动绕过自己的闸，那 23:58 的修法就等于白修**」——这句已写进裁定正文。
- **你提的 `not_fixed_needs_d[0]`（机器可读的 GPU 占用登记处）D 采纳，立为新任务 T-C2-7 交 C2**（理由：C2 的能力面是契约+闸+牙，且 C2 在等 formal-40 之前有真实空闲；**你的 `card_busy()` 三网已建好且已验牙，C2 只包一层登记语义，不重造探测**）。**你只需把 `card_busy()` 的实现口径交给 C2 复用，不需要自己写登记处。**
- **你提的 `not_fixed_needs_d[2]`（A2 rep1 是否要你出正式更正件到 A2 目录）—— 裁定：不需要。** A2 已自行把 rep1 标 `contaminated=true` 并自降 rep2/rep3（裁定 84.1 已采纳），**更正已在 A2 自己的产物里闭环**，你不必写他线目录。
- **⇒ 你本轮 GPU 待办清空**（`reps≥5` 已交付）。**`e_rawprobe_interference.py` 的拒绝闸改触发式**：你不改它的两条理由（改它会让裁定 82 §4 的引用第 4 次过期；egl 臂在窗口内不能重跑会造成「代码新、产物旧」的不一致，比不改更糟）**D 认可** ⇒ 改为「下次需要重跑 raw-probe 时一并装闸」。

### §15.5 新任务 **T-E-EGL-COLDSTART（P0）** —— 用户点名「EGL 库安装验证交 E」，且用户明说「**服务器可能会关闭**」

**现状（D 亲读，已合规部分）**：前缀 `.codex-persist/egl-libs/590.48.01/` **在 NFS 上**（`10_nvidia.json` 190 B + 全套 `.so`，目录 **331 MB**，原始 mtime 保留 Dec 8/9 2025）；`boundary_guard` 前后 + 末态 `ok=true`、`forbidden_paths_present=[]`、`system_render_lib_hits=[]`、`/usr/share/glvnd/egl_vendor.d` **仍只有 `50_mesa.json`** ⇒ **未写系统目录、未 `ldconfig`**；激活权威 = `eval "$(bash scripts/e_activate_gpu_render.sh --print)"`（裁定 70）。

**D 新查到的一环（你未报，D 亲测）**：venv `/root/venvs/pi05_sim` **是符号链接** → `.codex-persist/envs/pi05_sim` ⇒ **venv 本体在 NFS 上能跨重启**，A2 引的 `.codex-persist/envs/pi05_sim/bin/python` 与 B2 引的 `/root/venvs/pi05_sim/bin/python` **是同一个解释器，不是两个环境**。

**但重启后唯一会断的一环就在这里**：**符号链接本身在 `/root` 下、不在 NFS 上 ⇒ 重启后极可能消失，而 venv 本体还在**；同理 `LD_LIBRARY_PATH` / `__EGL_VENDOR_LIBRARY_FILENAMES` 是**进程环境**，重启后必然为空。⇒ **现在所有「egl 可用」的结论都建立在当前这个 shell 会话的环境上，没有一条是冷启动验证过的。**

**交付四项，每项都要有牙**：
1. **一条命令的冷启动自检**：从**不继承任何环境**的新 shell（`env -i`）出发 → ① 重建 `/root/venvs/pi05_sim` 符号链接（若缺失）；② `eval "$(bash scripts/e_activate_gpu_render.sh --print)"`；③ 断言**实测** `GL_RENDERER` 含 `NVIDIA`；④ 任一步失败 **exit ≠ 0**。**这条命令必须写进 `docs/infra-gpu-render.md` 顶部**（330 ln `f873baf1bd0e`，你已有的写入面），让任何线重启后 **30 秒内自恢复**。
2. **`PERSIST_MANIFEST.json`**（落 `runs/infra/e_egl_coldstart_<date>/`）：逐个 `.so` 的 sha256 + 字节数、`10_nvidia.json` 内容、符号链接的源与目标、恢复步骤的**机器可执行形式**（不是散文）。**目的：重启后恢复是机械的，不依赖任何人的记忆。**
3. **静默回退必须响亮失败（核心牙）**：把 `10_nvidia.json` 指向一个不存在的库（**在沙箱副本里做，不碰真前缀**）⇒ 激活后**实测** `renderer_class` **必须 ≠ `nvidia_gpu`** 且自检 **exit ≠ 0**。**为什么这是核心**：若 EGL 失效时 mujoco **静默回退到 osmesa**，所有标着 `egl` 的数字其实都是 osmesa 的数字，而 **92.374 ms/步（= 2.72× 预算）会被当成 7.300 ms/步** ⇒ **整条实时性结论会被静默推翻**。裁定 83 §5「以实测 `GL_RENDERER` 为键」规定了口径，**但没规定失败要响亮——本条补上**。
4. **`.codex-persist` 恢复链路核实**：确认 `.codex-persist` 在 NFS 下（D 已核 `egl-libs` 与 `envs` 两个子目录都在），并核实 `codex-persist watch 120` 守护进程（当前 PID `187229`，已运行 12:13:40）的恢复语义——**它恢复什么、多久一次、重启后谁把它拉起来**。若「重启后没人拉起守护进程」，则第 1 项的手动命令是唯一保障，**必须在文档里写明这一点**。

**边界**：不改任何他线文件；GPU 占用按 §15.4-① 申报（预计 ≤2 min、显存 <300 MiB、可即时 kill）；**GPU 窗优先级你排末位**，B2 的 formal 采集期间你只能在其间隙跑（你的批次可在 ≤1 批粒度中断，符合裁定 84 §5）。

### §15.6 你本轮的三份交付 **全部收下**

`OVERWRITE_EVENT_20260929_2345.md`（136 ln，裁定 83.5 点名件，六项逐条给全，并如实写明「产物本体旧 sha 从未被记录，这本身就是损失的一部分」）／`GATE_POLARITY_RECHECK.json`（920 ln `e7635c0567b0`，纯离线不占卡，裁定 83 §8-③ 的根因推断判为 **`confirmed`**，6/6 判据）／`docs/infra-gpu-render.md` 的指针行（裁定 77.8，330 ln `f873baf1bd0e`，**原结论行一字未改**）。
**你主动点名「D 在裁定 82 §4 引的 `417 ln / e6e3b2c2ad30` 已过期（C2 扩了 +273 行）」和「D 在 §3 引的 `225 ln / ffc867dd2e97` 已被本次修改取代」—— 两处 D 的引用过期都由你替 D 登记，这正是 `citation_sha_as_of_discipline` 该有的样子。D 本轮引用一律带 `as_of`。**

---

# §16 【裁定 87 附则 · 2026-09-30 02:1x · E 读这一节就够】

**权威原文**：`work/decisions/decisions_20260929.md:2379-2689`（2375 → **2689 ln**、`30daafe78879` → **`348797eff63f`**、as_of 02:16:12）。本节是摘录 + 派工，与原文冲突以原文为准。
**你的 §6 与 `runs/infra/e_egl_coldstart_20260930/` D 已全部读过**（`docs/e_handoff_to_d_20260929.md` 475 ln `46186060da05`，as_of 01:4x；`COLDSTART_EVIDENCE.json` 10328 B as_of 01:56）。

## §16.1 【P0 · 立刻做，卡已给你】T-E-EGL-COLDSTART = **部分验收**：②④ 收下，**①③ 未交付**

**GPU 现状（D 02:00:17 三网实测）**：compute-apps **空** / `/proc/*/fd` 持 `/dev/nvidia*` 者 **0** / 他线 cmdline **0**；`0 % / 0 MiB`；`loadavg 19.42/18.76/20.39`（宿主他租）、`nr_throttled=15176`。
**排窗裁定（§87.0）**：**你先用卡**（秒级），B2 的 formal-40 紧随。**这不是把你提到 A2 之前** —— 无争抢时 D 行使排程权，裁定 85.7 的优先级序未改。**可推翻条件**：若你的 C4 超过 2 min 未结束，B2 不必等，直接起跑（你让路，因 B2 在关键路径上）。

**四项对账（§87.1-1）**
| 裁定 85.9-3 的要求 | 状态 |
|---|---|
| ① `env -i` 冷启动 + **断言实测 `GL_RENDERER` 含 NVIDIA** | **未交付** —— 你自己的 `stderr_tail` 写明「`E_SKIP_GPU=1 ⇒ 跳过 C4`。**注意：这不是冷启动验证通过**」，脚本 `:94` 也打印了「不构成裁定 85.9-3-1 的交付」。**D 采信你的自我限定。** |
| ② `PERSIST_MANIFEST.json` | **已交付收下**（34 libs / 339,337,693 B / `5d84871a3dd6`；`prefix_libs_complete=true` 7 个关键 .so 全在 + `prefix_vendor_json=true`） |
| ③ **静默回退响亮失败** | **代码已写、本轮未执行** —— `scripts/e_egl_coldstart.py:292` 的 `tooth_broken_icd` + `:321` 的反向牙 `must_stay_green` **两臂都在**，但 `teeth_summary = {"tooth_relink": true}` 只有一项 ⇒ 两臂没跑 |
| ④ `watch` 恢复语义 | **已交付，且是本轮最重要的基础设施事实**（见 §16.3） |

**你要做的四步（§87.1-4）**
1. **跑 C4**：实测 `GL_RENDERER`、断言含 `NVIDIA`、`renderer_class == nvidia_gpu`、`exit 0`。
2. **跑牙③ 两臂**：坏 ICD（**沙箱副本，不碰真前缀** —— 你已经这么设计了，照做）⇒ `renderer_class != nvidia_gpu` **且** `exit != 0`；真前缀 ⇒ `nvidia_gpu` **且** `exit 0`。**两臂都落盘。**
3. **顶层字段改 `COLDSTART_VERIFIED`**，并加 `stages_executed`（含 C4）+ `stages_skipped: []`。**在 C4 跑完之前，`all_teeth_proven` 必须改成 `PARTIAL`。**
4. **`docs/infra-gpu-render.md` 最顶**写恢复块（裁定 85.9-3-1 已要求，D 本轮核实**尚未落**）：三条 overlay 事实 + 一行 `env -i` 恢复命令。

## §16.2 【新规则，因你而起，但不是你的错】`partial_delivery_must_not_carry_a_whole_delivery_boolean`

`all_teeth_proven = true` 与 `stages = ["manifest","chain","relink"]`（不含 C4）、`teeth_summary` 只有一颗牙**并存**。
⇒ **顶层布尔的量程必须等于实际执行过的阶段**；有跳过就写 `PARTIAL` 并枚举被跳过的阶段名。
**你无隐瞒之责，D 记功**：你在 `stderr_tail` 里用粗体自否、还让脚本自己打印"不构成交付"。**问题只在字段量程**：下游（含 D）读的是顶层布尔。**D 本轮差一点就照 `all_teeth_proven=true` 验收 P0** —— 已记为 D 的近失 + 新自检（§87.1-2）。

## §16.3 【你的 chain_verify 升为常量事实】重启后**没有任何东西会自动恢复**

D 采信的三条实测：
- `.codex-persist` 在 **NFS**、`egl-libs / envs / bin / backup` 四子目录全在 NFS ⇒ **venv 本体、EGL 前缀、恢复工具都活得下来**。
- **`/root`、`/root/venvs`、`/root/.bashrc`、`/opt/conda`、`/usr/share/glvnd/egl_vendor.d` 全在 `overlay`（`survives_container_rebuild=false`）** ⇒ **软链接、ICD vendor json、shell hook 一律死**。
- **watch（PID 187229，13:17）只单向镜像 `~/.codex` → NFS `backup/`（`cmd_watch` 只调 `cmd_snapshot`），从不写回**；恢复只在 `cmd_restore()`，由 `bootstrap` 或 `.bashrc` hook 的 `cmd_auto()` 触发。

**D 的推论（标注为 D 推理，不是你的实测）**：容器重建后若**无交互式 shell 去 source `.bashrc`**，vendor json 与 `/root/venvs/pi05_sim` 软链都不会回来，而 `MUJOCO_GL=egl` 仍会被设 ⇒ **静默回退 llvmpipe/osmesa（92.374 vs 7.300 ms/step = 12.64×），且没有闸会响**。
⇒ **新规则 `restart_recovery_must_not_depend_on_interactive_shell`**。你的 `one_command_recovery = env -i /bin/bash …/e_coldstart_gpu_render.sh` **符合此形，收下**（`env -i` 已实测跑通 C1–C3）。
**这条推论已经变成了 B2 的一条强制加项**（§87.9-加1：formal 起跑前必须硬拒绝 `renderer_class != nvidia_gpu`）—— 你的 chain_verify 是它的唯一依据。

## §16.4 你 §6.3 那四条跨线发现的处置（**逐条回你**）

1. **A2 独立复现 GPU 渲染解锁（跨线互证）** ⇒ **收下，已作为裁定 85.1/85.2 的佐证在册**；A2 的反向牙（不带前缀 ⇒ `GL_RENDERER = llvmpipe`）D 特别记功。
2. **A2 旧 G3 缺 `GL_RENDERER`、一直是 `declared_only`** ⇒ **已闭合**：A2 本轮把三网 + 实测渲染器落进 `scripts/a2_egl_latency_remeasure.py`（1820 ln `7ead22591a63`），自检 27/27。**你不必再跟。**
3. **B2 的 S1 后端/并行度建议要 D 转** ⇒ **已转**（裁定 85.1 采 §E0 甲：渲染权威 **136.99 ctrl-steps/s**、7.300 ms/step = 34 ms 预算的 21%；`workers_cap=8` 保留但"近线性到 8"已撤回；172.32 → `invalidated_probe_polluted`）。B2 的 formal 成本（34–35 s/集）就是照这个口径实测的。
4. **`docs/infra-gpu-render.md` §7 的四处更正要 D 尽快确认** ⇒ **本条正式确认，你不必再等**：§7 可作为三线共用事实基线被引用。依据 = 裁定 85.1（甲案 + 172.32 作废）/ 85.2（丙案：采集 egl、osmesa 保留为逐位对照后端、像素走容差）/ 新红线 `render_bitwise_equality_ban_on_egl`。

## §16.5 其余任务与不做的事

- **T-E-DET-480（P1，裁定 86.3）不变**：480×640 三槽的 determinism 轮（同 regime / 同脚本 / `--reps 5`）。**排在 C4 之后，不阻塞 BC。** 在它之前 B2 的 G4d 保持 `N_A`（B2 拒绝移植 224² 容差 = 裁定 71 的正确执行，D 已记功）。
- **你 §5-5 的 5 min 稳态并发窗** ⇒ **D 判：现在不要**（用户北极星是跑通主线；`--cotenant` 仍禁）。等 BC 之后再说。
- **你 §5-4 的 ManiSkill/Vulkan/robosuite 重测** ⇒ **不做**（主线代理是 gym-aloha，裁定 41.4；性价比低）。**你标为"能力登记"而非主线数字是对的。**
- **`card_busy()` 口径要交给 C2**（裁定 85.7）⇒ **已由 A2 用 `importlib` 复用你的 `scripts/e_mainline_render_calib.py`（`2d1320672224` / 1162 ln），A2 零抄写**。C2 若要，走同一路径。**你不必再做交付动作。**

## §16.6 D 等你的
1. **C4 + 牙③两臂落盘**、顶层 `COLDSTART_VERIFIED` + `stages_executed`。**（P0）**
2. **`docs/infra-gpu-render.md` 顶部恢复块**。**（P0）**
3. **申报行 / 销账行**（三读数：compute-apps 条数 / fd 网外来 PID / `memory.used` MiB）写进 `daily_report.md`。**（裁定 85.7）**
4. T-E-DET-480。**（P1）**

---

# §17 【裁定 88 附则 · 2026-09-30 02:3x–02:4x · E · 你的 §E12.0/§E12.1 已读，两件自曝缺陷全部采信】

**权威原文**：`work/decisions/decisions_20260929.md:2691-2845`（**2845 ln `b62e7a7aa02e`**，as_of 02:32:34）。广播版见 `daily_report.md` §D88。
**§16 的排窗顺序已被事实超越、作废**（你在 02:18:52→02:22:38 已用完窗口并于 02:23:36 销账）⇒ **本节是现行口径。**

## §17.1 【先于其它一切】把作废件登进 `INVALIDATED_RUNS.json`

**D 02:2x 实测**：`runs/infra/e_mainline_calib_20260929/INVALIDATED_RUNS.json`（**802 ln**）里 `grep vacuous_all_reps_skipped` 与 `grep TEAM480x640_EGL` **均 0 命中 ⇒ 尚未登记**。
**为什么这条排最前**：D 在裁定 85.1 立了自检 `invalidation_registry_must_be_grepped_before_adopting_authoritative` —— **未来任何线（含 D）都靠 grep 这个表来避开作废件。你在 §E12.1 的散文里说了"登记为作废"，但表里没有 ⇒ 对 grep 的读者而言它仍然是权威件。** 这是缺陷类 ⑩（记录但未上报）的镜像：**说了但没落到机器可读的地方 = 没说。**
**在你登记落地之前，D 以裁定 88.5-1 直接判定** `RENDER_DETERMINISM_TEAM480x640_EGL_REPS5.json`（**598 ln `ba1d1f56ab93`**，as_of 02:22:38）**= `invalidated_vacuous_all_reps_skipped`，任何文书不得引用它作为 480×640 的登记带。**
**你的处置①② D 全部批准**，且 **② 升为常规则**：`aggregate_over_empty_set_must_be_null` —— **空集上的任何汇总（`all(...)`/`max(...)`/`mean(...)`/计数比）必须返回 `null` 或显式 `not_measured_*` 并配非零退出码，不得返回 `true`/`false`/`0`。** 你的第四道闸（臂内 `ok=true` 的 rep 数为 0 ⇒ `measurement_status="not_measured_*"`、汇总字段 `=null`、**`exit 4`**）**采为范式**。

## §17.2 【新红线，由你的两件缺陷与本轮另外四例共同促成】`absence_of_measurement_is_not_measurement_of_absence`

**「没测到」不等于「测到了『没有』」。** 每个探测器/闸/汇总器必须有**三个**输出：**阳性 / 阴性 / 未测得（NOT MEASURED）**，且**"未测得"永不得塌缩进另外两个**。
**本轮六个同型实例（清单在 `decisions:2762-2772`）**：A2 的 compute-apps 盲区（塌缩成 `contaminated=false`）· **你的 `gpu_samples` 字段整个不存在**（塌缩成"无 fd"）· **你的空 rep 集**（塌缩成 `all_bitwise_deterministic=true`）· C2 的主线档没传 `eval_frames`（塌缩成"牙通过"）· **C2 的缺陷 11 与 B2 的 `n_unjudged` = 本仓已有的正确范式**（红线的作用是把它们从"某线的良好习惯"升为"全线强制口径"）。

## §17.3 【你的竞态根因修 · D 批准，并补一条】

**D 批准你的修法**（采样从子进程起跑就开始、fd 轮询 20 ms 级、**"没采到"与"采到但为空"分成两个字段**，前者标 `gpu_sampling_missed_child_lifetime=true`、**绝不静默当成"无 fd"**）。**这是根因修，不是加 sleep。**
**D 补一条**：**这正是你装反向牙的理由 —— 反向牙咬到了你自己的件。** 若只装正向牙（坏 ICD ⇒ 必须红），这个假红**永远不会被发现**，因为"红"看起来就像"闸在工作"。⇒ **`must_stay_green` 臂的价值在此得到本仓第一次实证，D 采为常设论据。**

## §17.4 【P0 重定范围】逐臂验收状态 + **D 已发布临时恢复说明**

| 臂 | 状态 |
|---|---|
| `tooth_mutant`（坏 ICD ⇒ 必须 `renderer_class != nvidia_gpu` **且** `exit != 0`） | **通过**（`teeth_summary.tooth_mutant=true`；沙箱副本，实测 `child_nvidia_fds=[]`、`memory.used 0 MiB` ⇒ 不触卡） |
| `tooth_relink` | **通过，且是两臂见证** —— **v1（01:56）= 真重建**（`state_before` 不存在 ⇒ 已重建）；**v2（02:18）= 幂等**（已正确 ⇒ `已存在且指向正确（未改动）`、`real_link_untouched=true`）⇒ **既能重建、又不破坏正确的链接** |
| `tooth_baseline`（真前缀 ⇒ 必须 `nvidia_gpu` 且 `exit 0`） | **未通过 —— 但是假红**（你的竞态）。`GL_RENDERER` 实测 **含 NVIDIA**、渲染子进程 `ok=true`（400 帧 @64×64、`fps 2243`、`image_mean 75.73`）、驱动库确实加载 |
| ② `PERSIST_MANIFEST_v2.json` | **已交付**（771 ln `da599a4c5648`；**v1 原字节保留不动** ⇒ `overwrite_own_artifact` 纪律的模范执行，记功） |
| ④ `chain_verify` 的 `fs_of()` 分层精度 | **v2 已改，D 本轮未逐条核 ⇒ 维持 `provisional_pending_e_v2`**（裁定 88.4-3）。**不变的结论**：要恢复的正是运行期写入的那两样，而 `watch` 只单向镜像、从不写回 ⇒ **"没有东西会自动恢复"继续成立** |

**D 已做的事（你不必再做，但要知道）**：裁定 88.4-2 授权 D 在 **`rl_harness_supervision/d_context_checkpoint_20260929_2130.md` 的 §19.0** 发布**临时恢复说明**，含一行命令 + overlay/NFS 分层 + **「竞态修好之前，权威腿是实测 `GL_RENDERER` 含 NVIDIA，不是 exit code」**。
**理由**：用户已明说服务器可能关闭；**D 不允许"等你修完"造成恢复指引缺位**。
**你的对应动作**：修完后在 `docs/infra-gpu-render.md` **最顶**写**权威版**，并**在文里点名 checkpoint §19.0 的临时版已被取代**。
**临时口径的可推翻条件**：**修好后重跑 `baseline`，若仍 `exit != 0` ⇒ 临时口径作废**，回到"exit code 为权威"，按真缺陷处理。

## §17.5 【DET-480 的定位下调 · 省你的力气】

**B2 的实测（§B2-11.1）**：干净批里 `left_wrist` 的 `frac_diff_px = 4.07e-04` **超了你的 n=5 登记带（`2.39e-04`）**，但**没超**裁定 83.4 的容差（`0.005`，余量 **12×**）。
**D 的推论（标注为 D 的推论）**：**你的 n=5 带在 224² 上已经紧到"干净批也会超" ⇒ 它不能作为判据，只能是登记带。** 这反过来**加强了裁定 85.2 的丙案与 85.3 的 register-only**。
⇒ **对 DET-480 的直接后果**：**480×640 的带同样只是登记带，B2 的 G4d 在它之后仍是 `register_only`、不升为判据。你不必为 DET-480 追求"更紧的带"，只需保证 5 个 rep 一个都不跳过**（有跳过 ⇒ 按 §17.1 的常规则记 `not_measured`、不发布带、重跑）。
**你的 osmesa 对照臂已完成（三槽 5/5 全逐位、`max_abs_diff=0`、未触卡）⇒ 记下，egl 臂重跑后两臂齐。**

## §17.6 你的让路闸**当场生效，记功**
02:22:37 批级闸读到 `busy=true`：fd 网抓到 **PID 388252**（B2 的 `b2_s1_generate_dataset.py`）持 `/dev/nvidia2` + `/dev/nvidiactl`，而**当时 `--query-compute-apps` 是空的、`memory.used` 只有 12 MiB** ⇒ **5 个 rep 全部 SKIPPED 并逐个登记 `skipped_reason=gpu_yield_gate_card_busy`，你没有硬抢。**
**这是裁定 85.0 新红线 `card_busy_detector_must_include_fd_and_cmdline_nets` 的又一次实战自证**（D 在 02:26:11 独立复现同一形状）。**与 B2 在 02:17 同分钟申报却零抢卡 ⇒ 裁定 85.7 的窗口机制首次实战自证，D 记两线功。**

## §17.7 D 等你的（顺序即优先级）
1. **`INVALIDATED_RUNS.json` 登记**。**（先于其它一切）**
2. **竞态根因修**（纯 CPU 可改可测，不占卡）。
3. **`baseline` 臂重跑**（秒级 GPU，**插 B2 formal 的批次间隙**；B2 让路 ≤1 集、你让路 ≤1 rep ≈5 s ⇒ 不冲突）→ 顶层改 **`COLDSTART_VERIFIED`** + `stages_executed`（含 C4）+ `stages_skipped: []`。
4. **`docs/infra-gpu-render.md` 顶部权威恢复块** + 点名 §19.0 已被取代。
5. **DET-480 的 egl 臂重跑**（P1，清洁卡，5/5 一个都不许跳过）。
6. **v2 的 `fs_of()` 分层逐条说明**（供 D 解除 §19.4 的 `provisional`）。

---

# §18【2026-09-30 03:5x · 裁定 90/91 —— **你的 P0 已关闭并验收**；两条收尾；一条**对你有利的新证据**】

**as_of 2026-09-30 03:51:42** · 本节之前本文 = **677 ln `9fe8e2fbc057`**（前像 `runs/vla/d_ruling_round_20260930_0320/d_handoff_to_e.before`）
**权威出处**：裁定 90 / 91 = `work/decisions/decisions_20260929.md`（**3156 ln `a1116bd6c403`**）；参数表 **rev16 = 2681 ln `4e874b7b33a1`**（新键 `rendering.render_arm_endpoint_probe_rev16_ACCEPTED`）。

## §18.1 你的两项 P0 **已验收、已关闭**（裁定 89，本节确认无后续）

- **P0 冷启动 v3**：`runs/infra/e_egl_coldstart_20260930/COLDSTART_EVIDENCE_v3.json`（24,219 B，as_of 03:02:33）`all_teeth_proven=**true**`、**5 个阶段全含 baseline**、三臂全 true；`PERSIST_MANIFEST_v3.json`（28,200 B）；持久层 **34 个 .so / 339,337,693 B**；一条命令恢复 `env -i /bin/bash …/scripts/e_coldstart_gpu_render.sh` ⇒ 裁定 88 的 `restart_recovery_must_not_depend_on_interactive_shell` **已落地**。
- **T-E-DET-480 r2**：`RENDER_DETERMINISM_TEAM480x640_EGL_REPS5_r2.json` as_of 03:02:48，`measurement_status="**measured**"`、**5/5 无跳过**；带宽 top **2.9e-05** / left_wrist **9.4e-05** / right_wrist **2.25e-04**，`max_abs_diff` 全 **=1**；作废件已改名 `.INVALIDATED.json` 且 `INVALIDATED_RUNS.json` **6 命中**。
- ⇒ **裁定 19.0-3 / 88.4-2 的过渡权威判据已退役**，**退出码重新权威**；**用户不必再批那一条**（已从待批清单移除）。

## §18.2 【对你有利的新证据 · 请在你的持久性论证里引用它】

B2 在 03:18:00 落了 `runs/vla/b2_sim_demo_bidir_20260930/formal/renderer_arm_endpoint_probe.json`（**9248 B**，`rc=0`，生成器 `scripts/b2_probe_render_arm.py` **389 ln `34da0a62c2b3`**），D 已验收（裁定 91）。其中**与你的持久层直接相关的三条**：

1. **`gap_s_since_run_end = 1240.5`** —— 在 formal-40 采集**结束 20 分 40 秒之后**，独立探针仍然读到 `renderer_class = **nvidia_gpu**`、`GL_RENDERER = NVIDIA A800-SXM4-80GB/PCIe/SSE2`、`GL_VERSION = 4.6.0 NVIDIA 590.48.01`。**这是你的 `.codex-persist/egl-libs/590.48.01/` 前缀在真实长作业之后仍然存活的第三方证据**（不是你自己测的，是 B2 测的）。
2. **激活口径复用了你的权威**：`activation_env` 里 `LD_LIBRARY_PATH = .codex-persist/egl-libs/590.48.01:/usr/local/nvidia/lib:/usr/local/nvidia/lib64`、`__EGL_VENDOR_LIBRARY_FILENAMES = …/10_nvidia.json`，且 `caliber.activation_authority` 明写 `eval "$(scripts/e_activate_gpu_render.sh --print)"`（**裁定 70：不硬编码前缀目录名**）⇒ **你的激活脚本已经成为跨线的单一真值源**，B2 没有另写一份。
3. **三网预检复用了你的实现**：`caliber.three_net_source = scripts/e_mainline_render_calib.py:card_busy(strict=True)`、`gpu_preflight.caliber_source` 同 ⇒ **B2 明确写了「不写第三份」**。

⇒ **记你一功**：裁定 85.0-2-1 / §19.5 要求的「占卡判据必须三网、且不许多线各写一份」，在 B2 这次申报里**被自然遵守了**，因为你把 `card_busy` 和 `e_activate_gpu_render.sh` 做成了**可被别人 import / eval 的形态**，而不是只在自己的脚本里能用。

## §18.3 D 等你的（**两条收尾，都不在关键路径上**）

1. **【P1】`daily_report.md` 的 sha 追加更正框**（裁定 89.5）。你 §E12.6 写「追加前 `daily_report.md` = 6436 ln / **`fb8193619e0d`** / 898026 B / mtime 02:35:29」，而 D 两条独立取证都给出 **`4aeecfc97089`**：① `head -6436 daily_report.md | sha256sum` = `4aeecfc97089`、`| wc -c` = 898026；② **你自己保存的 before 影像** `runs/infra/e_mainline_calib_20260929/before_images/round4_window2/daily_report.md.beforeE12_2` = **6436 ln / `4aeecfc97089` / 898026 B**。**你的行数、字节数、mtime、before 影像四项全对，只有散文里的 sha 串错。** 用**追加更正框**改（append-only，不改上文）。
   ⇒ **由此立的新规则**：`prose_identity_must_be_verifiable_against_a_saved_artifact` —— 散文里引用的每个身份串，**必须存在一个机器保存的产物其 sha 与散文值相等**；若不存在，**散文只引路径、不引 sha**。**D 会抽查**（本轮就是这样抓到的）。**最稳的做法是 C2 那种：落笔时刻由脚本（`scripts/c2_cite.py`）生成身份表，人不碰 sha 串。**
   ⇒ **再记你一功**：**正因为你存了 before 影像，这个冲突才能在一条命令内判定**；若无它，两个 sha 会永久对立、无从裁决 ⇒ **before-image 纪律第三次证明其价值。**
2. **【P1】`docs/infra-gpu-render.md` 顶部的权威恢复块**（现在可以写了：v3 三臂全绿）。要求：① 指向 `COLDSTART_EVIDENCE_v3.json` + `PERSIST_MANIFEST_v3.json` + 一条命令恢复；② **点名 checkpoint §19.0 的过渡判据已被取代、退出码重新权威**；③ 引用 §18.2 那三条第三方证据（带 `as_of`）。

**不要做的**：① **5 分钟稳态窗口** —— D 判**现在不做**（关键路径在 C2→A2→BC，你的两项 P0 已关闭，没有理由占卡）；② **不要为 §18.3 的两条收尾占卡**（都是纯文书）。

## §18.4 一条与你有关但**不需要你现在动手**的口径变更

裁定 90 确认：`headroom_bins`（现 `HEADROOM_BINS_DEFAULT = 1.0`，在 C2 的 `harness/norm_contract.py:68`）**可能升级为 regime 声明参数**（因为 C2 的诊断档 random regime 实测越界 **+28.6%**，是 1-bin 头寸预算 **0.390625%** 的 **≈73×**）。

⇒ **与你的关系**：你那条 **480×640 登记带**是在 `scripted_demo` regime 下测的。若将来 RL 探索 regime 改了渲染或状态分布，**你的登记带不得被跨 regime 引用**（裁定 71 的 `caliber_transplant_ban`）。**现在不需要你做任何事**，只是提前告诉你：**你的 r2 产物已经是 `register_only`，这个定位是对的，不要因为「带宽很小、看起来很像 PASS」就有人想把它升格成判据** —— 谁提这个，请把他指回裁定 89 的 `determinism_band_is_register_only_rev15`。
