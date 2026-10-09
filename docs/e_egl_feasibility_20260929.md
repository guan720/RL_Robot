# E 线交付：GPU 渲染可行性判定（E1）+ 后端 A/B（E2）+ 主线口径重标定（E3）

**作者**：智能体 E（吞吐线，不在正确性关键路径上）
**执行单**：`rl_harness_supervision/d_handoff_to_e_20260929.md`（§3 E1 / §4 E2 / §8.3 E3）
**落盘时间**：2026-09-29 22:3x CST　**最后更正**：2026-09-30 00:5x CST（见 §6.0 与 §10）
**HEAD**：`c422659`（E 不提交，单写者 = B2，裁定 49.6/81.2）
**回流单**（含事故自报与需 D 裁项）：`docs/e_handoff_to_d_20260929.md`

> **⚠ 本文 22:3x 版的 §结论/§6.2/§6.3/§6.5 数字已被 E 自己作废并重测**（根因 = E 的探针污染了自己的产物，
> 见 §6.0 与 §10）。**现版数字全部来自 `summary_20260929_234814.json`（去缺陷 + 三道闸的重跑轮）**；
> 22:3x 版的字节已按裁定 35.1 留前像：`runs/infra/e_mainline_calib_20260929/before_images/docs__e_egl_feasibility_20260929.md.before`（`c3ce5cd4cfbe`）。

---

## 结论一句话

**可行，且只需 prefix-only**：把与驱动 **590.48.01 逐字同版本**的渲染侧库放进 NFS 前缀目录，只用
`LD_LIBRARY_PATH` + `__EGL_VENDOR_LIBRARY_FILENAMES` 两个环境变量注入，**不写系统目录、不 `ldconfig`、
不改 `NVIDIA_DRIVER_CAPABILITIES`、不需要 `/dev/dri`**，即可让 mujoco/dm_control 真的在 A800 上渲染。

主线口径（`gym_aloha/AlohaTransferCube-v0` 双臂 + A2 的 **29.4118 Hz** shim + 3 相机）下的**当批同机 A/B**
（**权威轮 = `summary_20260929_234814.json`**，去缺陷重跑；w=1、聚合中位数 of 2 reps）：

| 分量（口径见 §6.1） | CPU `osmesa`（llvmpipe） | GPU `egl`+NVIDIA 前缀 | 比值 | 对 34.0 ms 预算（裁定 53-2） |
|---|---|---|---|---|
| **`env_step_native`**（主线现状：`env.step()` 全路径） | **10.84 ctrl-steps/s**（92.374 ms/步） | **136.99 ctrl-steps/s**（7.300 ms/步） | **12.64×** | CPU **超预算 2.72×** → GPU **占预算 21%** |
| `env_step_plus_3cam_224`（内建 + 自采 3×224²） | 6.21（161.331 ms/步） | 78.39（12.757 ms/步） | 12.62× | 超预算 4.7× → 占预算 38% |
| `render_3cam_224`（A2 的 render-only 口径） | 14.56（68.696 ms/步） | 187.16（5.344 ms/步） | 12.85× | 超预算 2.0× → 占预算 16% |
| `render_native_3cam_480x640`（env 内建的三张 480×640） | 12.37（80.891 ms/步） | 175.58（5.696 ms/步） | 14.19× | 超预算 2.4× → 占预算 17% |
| `physics_only`（17 substeps，无渲染） | 1351.75（0.740 ms/步） | 1374.84（0.728 ms/步） | **1.02×** | 两臂都远低于预算 |

- **并行扩展（同一张卡，1→8 进程）**：GPU 臂 `env_step_native` 扩展效率 **w2 0.975 / w4 0.921 / w8 0.684**
  （聚合 **136.99 → 267.22 → 504.69 → 749.38 ctrl-steps/s**）；CPU 臂同口径掉到 **0.882 / 0.449 / 0.205**
  （聚合在 w=4 见顶 **19.46**、w=8 反降到 **17.79**）。
  ⇒ **`parallel_eval_workers_cap=4` 这条上限是 CPU 渲染口径的产物，GPU 渲染下不成立**；
  但**GPU 下 w=8 也不是"近线性"**（eff 0.684、每 worker 延迟 7.300→10.486 ms = 预算 21%→31%）
  ⇒ **w=4 是延迟甜点，w=8 只有聚合吞吐价值**（建议值见回流单 §4-2）。
- **物理不吃 GPU**：`physics_only` 两臂同为 ~1370 ctrl-steps/s（比值 1.02×）⇒ 加速全部来自渲染，
  **不得把 12.64× 说成"仿真快 12.64 倍"**。
- 负载对：本表 GPU 臂 `loadavg 39.10/39.29/38.82` → `40.22/39.53/38.92`、`nr_throttled 10227 → 10302`（8 个 GPU 批）；
  整轮（含 osmesa 臂）`nr_throttled 10227 → 12852`；逐批负载对见 §8（**机器全程很忙，单点数字不得当常数搬用**）。
- **⚠ 与 D 的裁定 84.4 存在权威值冲突**：D 定的渲染吞吐权威值仍是 **`172.32`**（出自 `summary_20260929_221443.json`），
  而该文件的 GPU 渲染族**已被 E 的 `INVALIDATED_RUNS.json` 点名作废**（虚高至 **+125.3%**）。
  **E 不单方面替换 D 的权威值**，两值并列 + 证据见 **§6.0**，需 D 裁（回流单 §4-10）。

---

## 0. 读数须知（三条口径纪律，违反就会读错这份文书）

1. **五元标注缺一不可**（裁定 46.4/53.6）。本文所有吞吐数字的完整标注 =
   `(后端 MUJOCO_GL + vendor ICD, mujoco 版本, 模型, 相机数, 分辨率)` + **控制频率** + **venv**：
   - GPU 臂：`egl` + `.codex-persist/egl-libs/590.48.01/10_nvidia.json`，mujoco **3.8.1**，
     `gym_aloha/AlohaTransferCube-v0`（`aloha_bimanual_14d`，`nq=23/nv=22/nu=16/ncam=7`，
     `nmeshface=30296`/`nmeshvert=15122`），3 相机，224²（`env_step_native` 内建的是 **480×640**），
     **29.411765 Hz**（shim `dc14466fcdcf`，`representation_version=gym_aloha_dt0.034_29.4118hz_shim_v1`），
     venv `pi05_sim`。
   - CPU 臂：**同一台机、同一批、同一 venv、同一模型、同分辨率**，只把后端换成 `osmesa`
     （后端标签**不是自证的**：每批都有 `label_integrity`，四重实证 = **批级独立子进程**取的 `GL_RENDERER` 原文 +
     每 worker 的 `/dev/nvidia*` fd + `/proc/self/maps` 里已加载的库 + **渲染双闸** `render_health_ok`，见 §6.4。
     **注意：22:3x 版这里写的是"裸 mujoco **同线程**取 `GL_RENDERER`"，那个做法本身就是要作废 221443 的原因，已删，见 §10.1**）。
2. **图像语义可跨后端比，吞吐数字不可跨后端/跨 venv/跨模型搬**。§6.5 给了同 seed 同动作序列下的
   逐相机 `mean/std` 对照：**GPU 相对 CPU 系统性略暗 −0.038%～−0.295%**（**不是 22:3x 版写的"<0.06%"，
   那一版把 osmesa 列误抄成了 GPU 值 ⇒ 差异被算成 ~0，已更正**，见 §6.5）。
   该差异比 egl 下的 LSB 级抖动（≤0.052%）大，但两者**来源不同、不可混为一谈**（§6.5 给了区分办法）。
3. **状态词只用 v4 五档**。本文里：E1/E2/E3-1 = **回放通过**（判据 + 变异体都落地在产物里）；
   E3-3/E3-4 的建议值 = **已实现未验证**（数字有了，是否作为主线口径**由 D 裁**）；
   S1/S5 后端选型 = **未实施**（E 只给建议，不改主线、不写 `work/project_parameters.json`）。

---

## 1. E1：六条绿判据（执行单 §3.3）逐条

**探针**：`scripts/e_egl_probe.py`（内含 §3.2 的**边界自缚闸** `boundary_guard`：系统目录里一旦出现
NVIDIA 渲染库或 vendor ICD 就 `exit 3` 拒跑 —— 边界靠代码，不靠自觉）。
**解释器要求**：必须用带 mujoco 的 venv（`/root/venvs/rlrobot/bin/python`）。用裸 `python3` 会让
C3/C5/C5b **假红**，本脚本已把这种情况判为 `环境无效`（exit 5）而不是 `不通过`；22:28 的两份假红产物
按原样留档并在 MANIFEST 里点名（`green_*_20260929_222803.json`、`m1_20260929_222804.json`），**勿当结论引用**。

| 判据 | 实测（22:30 复跑，与 21:31/21:34 两批一致） | 结论 | 证据路径 |
|---|---|---|---|
| **C1** `eglQueryDevicesEXT` ≥1 设备且可归因 NVIDIA | `num_devices=1`（注入 NVIDIA ICD 后 Mesa 设备被顶掉）、`vendor="NVIDIA"`、`egl_version=1.5`、`initialize_ok=true`、`egl_error=0x3000`、设备扩展含 **`EGL_NV_device_cuda`**、**`drm_device_file=null`** | **PASS** | `runs/infra/e_egl_probe_20260929/green_filenames_20260929_223047.json` → `criteria.evidence.egl_displays` |
| **C2** `eglCreateContext` + `eglMakeCurrent` 成功（纯 ctypes 走完整链，不借 mujoco） | 全链 ok；**NVIDIA 对 pbuffer surface 返 `EGL_BAD_PARAMETER(0x300c)`** ⇒ 走 mujoco 同款 **surfaceless** 路径才通 | **PASS** | 同上 → `C2_egl_context_chain.steps` |
| **C3** `GL_RENDERER` 不是 llvmpipe | `NVIDIA Corporation \| NVIDIA A800-SXM4-80GB/PCIe/SSE2 \| 4.6.0 NVIDIA 590.48.01`（EGL 上下文直取与 mujoco 内取**两处一致**） | **PASS** | 同上 → `criteria.evidence.gl_strings_via_egl_context` / `gl_strings_via_mujoco` |
| **C4** 渲染期间 GPU 有占用 | `util_max=1%`（filenames）/`3%`（dirs）、`mem_max=96 MiB`；**空载基线同批采**（`util 0%`、`mem 0 MiB`，5 次采样） | **PASS**（util 低是因为 32² 小图 + 采样间隔 0.2 s；**归因不靠它**，靠 C5b） | 同上 → `gpu_util_max_during_render` / `gpu_idle_baseline` |
| **C5** 出图非黑且帧间互异 | `raw_len == h*w*3`、`byte_std > 0`、连续三帧 `identical_to_prev=false` | **PASS** | 同上 → `criteria.evidence.frames` |
| **C5b** 子进程自己持有 `/dev/nvidia*` fd | **`/dev/nvidia2`、`/dev/nvidiactl`**（进程级归因，**无法被并发进程伪造**；注意本机是 `nvidia2` 不是 `nvidia0`） | **PASS** | 同上 → `child_nvidia_fds` |
| **C6** 吞吐 A/B | 见 §5（E2）与 §6（E3，主线口径） | **PASS** | `ab_piper_single_arm_20260929_214137.json`、`runs/infra/e_mainline_calib_20260929/` |

**两种 vendor 注入方式都生效**（D §3.1 要求两种都试）：
`__EGL_VENDOR_LIBRARY_FILENAMES=<前缀>/10_nvidia.json`（前缀自带、内含**绝对路径**）与
`__EGL_VENDOR_LIBRARY_DIRS=<前缀>`（用系统 `10_nvidia.json` 的**相对** `library_path`，靠 `LD_LIBRARY_PATH` 解析）
⇒ 六条判据都过。**建议主线用 `FILENAMES`**：它把"用哪个 ICD"钉死在文件路径上，不依赖目录扫描顺序。

**负载对**：`loadavg 37.27/38.35/41.48`，`nr_throttled 9486 → 9491`（22:30 复跑）；
21:31–21:34 那批为 `loadavg 51.02/50.79/49.44`，`nr_throttled 3422 → 3428`。

---

## 2. 变异体 M1/M2：判据**有牙**（不是恒真闸）

| 变异体 | 做法 | 必须发生 | 实测 | 结论 |
|---|---|---|---|---|
| **M1** | 库不变，只把 `__EGL_VENDOR_LIBRARY_FILENAMES` 指回系统 `/usr/share/glvnd/egl_vendor.d/50_mesa.json` | `GL_RENDERER` 退回 llvmpipe、GPU 全程 0 占用 | `Mesa \| llvmpipe (LLVM 15.0.7, 256 bits) \| 4.5 (Compatibility Profile) Mesa 23.2.1`、`util_max=0%`、`mem=0 MiB`、**子进程 `/dev/nvidia*` fd 为空** | **通过** ⇒ "绿"是**这套 vendor ICD**带来的，不是"设了 `MUJOCO_GL=egl`"带来的 |
| **M2** | 把前缀里的 `libEGL_nvidia.so.0`（+ 真身）**移进 `recycle_bin`**（不 `rm`） | 设备枚举必须归零或报错 | `num_devices=0`、`egl_error=0x3000`、`GL_RENDERER=(空)`；跑完**自动移回**并按 **sha256 逐字复核一致**（`prefix_restored=true`） | **通过** ⇒ C1 不是"总能枚举到设备"的恒真判据 |

M2 的证据：`runs/infra/e_egl_probe_20260929/m2_20260929_213429.json`（负载对 `loadavg 51.02/50.79/49.44`、
`nr_throttled 3426 → 3428`）。**本轮（22:3x）未重跑 M2**：前缀目录现在被 A2 共用
（`runs/vla/a2_egl_latency_20260929/` 的 `activation_env.prefix_paths_verified` 显示 A2 直接依赖它），
临时移走 `libEGL_nvidia.so.0` 会打断别的线 ⇒ **M2 已变成"需要约窗口/加锁"的操作**，这条报 D（回流单 §4-6）。

**一处键名歧义自报**：`criteria.checks` 里的键名（如 `C3_gl_renderer_not_llvmpipe`）语义是
**「是否符合本臂预期」**，不是字面断言 —— M1 里它 = `true` 的意思是"确实是 llvmpipe = 符合变异臂预期"。
逻辑本身按 `expect_nvidia` 分支取值（**不是恒真**），但键名会误导读者 ⇒ 已在产物里补
`check_expectations` + `semantics_note` 两个字段逐条写明预期；**改键名会动 D 已复核过的产物 schema，本轮不改**，是否改名由 D 裁。

---

## 3. 版本与 sha256（可复现的来源链）

| 项 | 值 |
|---|---|
| 宿主驱动 | **590.48.01**（`/proc/driver/nvidia/version`，Open Kernel Module） |
| 前缀目录名 | `egl-libs/590.48.01` ⇒ `version_exact_match=true`（**逐字一致**，不是"兼容版本"） |
| 来源 `.deb`（`dpkg-deb -x` 解包，**不是 `dpkg -i`**，dpkg 状态未变） | `libnvidia-gl_590.48.01-0ubuntu1_amd64.deb` 106,981,350 B `sha256 b6a34197683057711be7a7ab3918e727819a2f905c60a55920ebb08e0aebd9d5`；`libnvidia-gpucomp_590.48.01-0ubuntu1_amd64.deb` 23,332,564 B `sha256 219fce60c8647de485869bba1d5fb8c1be0634d766f65f842f170e715832e774` |
| 渠道 | `developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/`（301 → `.cn`，经公司代理，实测 41 MB/s）；runfile 通道 `download.nvidia.com/XFree86/Linux-x86_64/590.48.01/` 亦可达（未使用）；`us.download.nvidia.com/tesla/590.48.01/` **超时**（25 s，0 字节） |
| 关键库 sha256（前缀内） | `libEGL_nvidia.so.590.48.01` 1,288,448 B `9f4ceddcc377…`；`libGLX_nvidia.so.590.48.01` 1,211,968 B `b1747499d597…`；`libnvidia-glcore.so.590.48.01` 36,118,984 B `56f9a3b4b9bb…`（全表见 `precheck_20260929_213429.json` → `prefix_lib_sha256`） |
| 前缀体积 | 324 MB（`.codex-persist/egl-libs/590.48.01/`）；解包源 `_src_590.48.01/` 525 MB（含两个 `.deb` 原件） |

---

## 4. D 的等待项：`libEGL.so.1` 是否缺 `eglQueryDevicesEXT` 符号（§3.1-1）

按裁定 50.1 的否定型主张纪律，**先枚举完整清单**再下结论：
`nm -D /usr/lib/x86_64-linux-gnu/libEGL.so.1 | wc -l` = **108** 个动态符号（命令原文与输出都在产物里），其中

| 符号 | 是否导出 |
|---|---|
| `eglQueryDevicesEXT` | **0（未导出）** |
| `eglQueryDeviceStringEXT` | **0（未导出）** |
| `eglGetPlatformDisplayEXT` | **0（未导出）** |
| `eglGetProcAddress` | **1（导出）** |
| `eglGetPlatformDisplay`（core 1.5 版） | **1（导出）** |

**⇒ 结论：只补 vendor 就够了，不需要顺带补 libglvnd。** 三个 `*EXT` 入口点虽然不在动态符号表里，
但**经 `eglGetProcAddress` 都能取到可用地址**（本探针的 C1/C2 就是这么走通全链的：
`eglGetProcAddress("eglQueryDevicesEXT")` → 枚举到 NVIDIA 设备 → `eglGetPlatformDisplayEXT` → `eglCreateContext`
→ `eglMakeCurrent(surfaceless)` 全 ok）。这与 D 的裁定 56 一致，E 侧给出**符号级**的独立复核。
证据：`runs/infra/e_egl_probe_20260929/precheck_20260929_213429.json` → `commands` / `libegl_exported`
（系统 glvnd 版本 = **1.4.0**，`libEGL.so.1.1.0`）。

---

## 5. E2：后端 A/B（同 venv / 同模型 / 同分辨率，**只换后端**）

三臂定义（每臂都用 `GL_RENDERER` 原文实证，`label_integrity.ok=true`、`mismatches=[]`）：
`osmesa` = CPU 软渲染；`egl_nvidia` = `egl` + 前缀 NVIDIA ICD；**`egl_mesa` = 变异臂**
（前缀在 `LD_LIBRARY_PATH` 上，但 ICD 指回 `50_mesa.json` ⇒ 证明"快"来自 ICD 选中 NVIDIA，不是来自"设了 egl"）。

### 5.1 单臂 Piper（3 相机 224²，decim=16，ctrl 31.25 Hz，独立进程 3 重复）

复用 D 的 worker `runs/vla/d_render_probe_20260929/piper_single_arm_sweep.py one "3,224,224,rep"`（**只读，未改 D 的脚本**）。

| 后端 | w=1 | w=2 | w=4 | 相对 osmesa w=1 |
|---|---|---|---|---|
| `osmesa` | 12.54 | 24.83（eff 0.99） | 47.49（eff 0.947） | 1.0× / 1.98× / 3.79× |
| **`egl_nvidia`** | **633.95** | **817.81**（eff 0.64） | **1511.27**（eff 0.596） | **50.55× / 65.2× / 120.5×** |
| `egl_mesa`（变异臂） | 12.10 | 24.53 | 48.01 | 0.96× / 1.96× / 3.83× ⇒ **回到 CPU 水平** |

单位 = ctrl-steps/s（聚合）。负载对：`loadavg 49.72/49.55` → `53.83/50.91`，`nr_throttled 3667 → 3749`。
证据：`runs/infra/e_egl_probe_20260929/ab_piper_single_arm_20260929_214137.json`。
**注意**：Piper 单臂的 GPU 并行扩展是**次线性**（eff 0.60）—— 它的瓶颈是**网格面数**
（183,746 faces / 91,886 verts，D 与 A2 都已实测），单帧就要 ~1.6 ms GPU，8 万面的模型把单卡吃满得快；
gym-aloha 的 30,296 faces 轻得多 ⇒ **扩展效率不能跨模型搬用**（见 §6.3 的 0.94–1.03）。

### 5.2 gym-aloha 双臂（3 相机 224²，render-only 口径 = A2 `sec_throughput`，独立进程 3 重复）

| 后端 | ctrl-steps/s | 相对 osmesa |
|---|---|---|
| `osmesa` | 14.01（spread 1.1%） | 1.0× |
| **`egl_nvidia`** | **165.65**（spread 9.3%） | **11.82×** |
| `egl_mesa`（变异臂） | 12.83（spread 37.3%） | 0.92× |

负载对：`loadavg 47.49/49.29` → `50.08/49.61`，`nr_throttled 3532 → 3667`。
证据：`ab_gym_aloha_20260929_214002.json`。**这一档是双臂**（用户「先只渲单臂」指令的作用域按裁定 58.1
只约束 Piper 自有资产线；且 D §4-2 自己要求测 gym-aloha），冲突已报 D（回流单 §4-5）。

### 5.3 与留档基线的互证（**同口径才并列，口径差写清**）

| 留档数字 | 出处与口径 | E 本轮同口径实测 | 差 |
|---|---|---|---|
| **14.83** ctrl-steps/s | A2 `runs/vla/a2_pi05_zeroshot_20260929/render_throughput_a2.json`：`egl`(实为 llvmpipe)/mujoco 3.8.1/gym-aloha 双臂/3cam 224²/**同进程** 3 重复/`bench_seconds=5`/`loadavg 53.5` | E3 权威轮 `osmesa` w=1 `render_3cam_224` = **13.81**（独立进程、30 步、`loadavg 39.4`） | **−6.9%** |
| **12.88** ctrl-steps/s | D `runs/vla/d_render_probe_20260929/single_arm_controlled.json`：osmesa/3.9.0/单臂 Piper STL/3cam 224²/decim16/31.25 Hz/独立进程 3 重复/`loadavg 35.86` | E2 `osmesa` w=1 = **12.54** | **−2.6%** |
| **12.03** ctrl-steps/s | D `ctrl_hz_alignment.json` → summary.B：同上但 `timestep=1/480`、ctrl **30.0 Hz**、`loadavg 61.89` | 未复测（E 未改 timestep，那是第三方资产） | — |

⇒ **三处都在 ±7% 内互证**，说明 E 的测量没有系统性偏移。**12.88 vs 12.03 谁是权威基线仍需 D 二选一**
（口径差 = ctrl_hz + timestep + 机器负载；回流单 §4-1）。

---

## 6. E3-2/E3-3：主线口径重标定（**prefix-only 合规路径**，权威轮）

**为什么必须重测**：D §8.3-2 指出既有 `runs/infra/e_gpu_egl_verify_20260929/downstream_gpu_*.json` 是
**系统安装态**（违规窗口内）测的 ⇒ 主线要用的数字必须来自合规路径。本节全部数字来自
**只导出环境变量**的 prefix-only 路径，且每批前后各核一次 `boundary_guard`（末态 `ok=true`）。

**权威轮（E 侧）**：`runs/infra/e_mainline_calib_20260929/summary_20260929_234814.json`
（16 批 = 2 后端 × 4 并行度 × 2 重复；每批 30 控制步 × 5 个分量；GPU 批次**全部独占卡**，
`other_compute_procs=[]`；`label_integrity.ok=true` 全批；**16/16 批 `render_health_all_ok=true`**；
`_excluded_batches=null`；`boundary_guard_final.ok=true`）。

**22:3x 版指的 `summary_20260929_221443.json` 已被 E 自己作废**（见 §6.0 与 §10.1）。
首轮 `summary_20260929_220400.json` 因后端标签缺"批级独立子进程 `GL_RENDERER`"实证，**仅留档不作权威**；
但它的**数字**是干净的（该轮尚未加入裸探针），被 `INVALIDATED_RUNS.json` 用作 `clean_reference_round` 交叉验证。

### 6.0 ⚠ 权威值冲突：**必须与 §结论一起读**（E 不单方面替换 D 的裁定）

| 口径 | 数值（`egl_nvidia` w=1 `env_step_native`） | 出处 | 状态 |
|---|---|---|---|
| **D 的裁定 84.4 权威值** | **172.32 ctrl-steps/s（5.80 ms/步）** | `summary_20260929_221443.json` | **该文件的 GPU 渲染族已被 E 点名作废** |
| **E 的去缺陷重跑值** | **136.99 ctrl-steps/s（7.300 ms/步）** | `summary_20260929_234814.json` | 16/16 批全闸通过、`_excluded_batches=null` |
| 比值 | **172.32 / 136.99 = +25.8%** | — | 与独立实测的 `raw_after` 虚高 **+31.0%** 同量级 |

- **作废依据**（`runs/infra/e_mainline_calib_20260929/INVALIDATED_RUNS.json`，三判据全中）：
  **C1** GPU 臂渲染类分量显著虚高（`max_gpu_render_inflation_pct=125.3`）；
  **C2** 同两轮 GPU 臂 `physics_only` **不变**（±4%）⇒ 排除"整机变快"；
  **C3** 同两轮 **osmesa 臂渲染不变**（±12%）⇒ 污染是 GPU 臂特有。
  根因 = 221443 那轮的 `e_mainline_render_calib.py` 在**被测 env 同进程**里建过一次裸 `mujoco.Renderer`
  （顺序 `raw_after`），该动作已被 D 采纳为红线 **`bare_renderer_same_process_ban`**（裁定 82.5）。
- **第三腿交叉验证**：`clean_reference_round` = `summary_20260929_220400.json`（**尚未加入**裸探针的那轮）
  与 234814 吻合 **+1.3%（w1）/ +1.0%（w8）** ⇒ 136.99 不是"变慢了"，是 221443 曾经"虚高了"。
- **⇒ D 裁 84.4 时这份作废件不在 D 的视野里**（`grep -c INVALIDATED_RUNS work/decisions/decisions_20260929.md daily_report.md`
  在 00:4x 实测 = **两份文书各 0 命中**）。E 已于 `daily_report.md` §E0 上报，走裁定 80.2 的下位纠正通道，
  **请 D 在「甲：权威改为 136.99」与「乙：维持 172.32 但加标 `known_inflated_upper_bound_do_not_plan_on`」之间裁**。
- **在 D 裁之前，本文所有表格用 234814 的数字，并在每处标"与裁定 84.4 冲突，见 §6.0"**；
  **E 不改 D 的文书、不改 `work/project_parameters.json`。**

> **【03:2x 结案行 · 冲突已由 D 裁定，本节不再悬空】** D 在**裁定 85.1-1 采纳甲案**：
> **权威值 = `136.99` ctrl-steps/s（`7.300 ms/步` = 34.0 ms 预算的 `21%`）**，出处 `summary_20260929_234814.json`；
> **`172.32` 降为 `invalidated_probe_polluted`**（任何文书再引它必须同引 `INVALIDATED_RUNS.json`）。
> 连带改判（**裁定 85.1-3**，**用户分叉① 就此关闭**）：聚合吞吐 w=1/2/4/8 = **`136.99 / 267.22 / 504.69 / 749.38`**、
> 并行效率 = **`1.0 / 0.975 / 0.921 / 0.684`**（**「近线性到 8」的理由撤回**；`workers_cap=8` 保留但依据改为
> 「较 w=4 仍 +48% 且每 worker 延迟 `10.486 ms` = 预算 `31%`」）、加速倍数对外口径 **`16.5×` → `12.64×`**（`env_step_native` w1）。
> **后端选择由丙案定**（裁定 85.2）：**egl 继续作采集/复现后端**、**osmesa 保留为逐位对照后端**（慢 16.5×），
> 并立红线 **`render_bitwise_equality_ban_on_egl`**（egl 上 sha/逐位相等**不能**当渲染保真闸；像素走**裁定 83.4 的容差**，硬判据只剩状态逐位）。
> **裁定 77.3（S1/S5 后端 = egl）不翻转**：`7.300 ms` = 预算 21%，而 CPU 软渲染 `92.374 ms` = **2.72× 预算** ⇒「CPU 软渲染下实时闭环不可能」仍成立。
> **另**：D 在**裁定 85.1-2** 把这起冲突记为**它自己的第 11 次同型错误**，并立了两条新规则
> （`invalidation_registry_must_be_grepped_before_adopting_authoritative` / `redline_implies_number_invalidation`）
> 与一条范围澄清（`caliber_transplant_ban_scope`：**裁定 71 只挡跨口径并列，不挡同口径去缺陷重跑取代旧值**；
> E 本轮的**八项对齐表**被 D 采为「判同口径」的模板）。
> **⇒ 本节上表第 3 行的「请 D 裁」已履行完毕；本文其余各处的「与裁定 84.4 冲突，见 §6.0」标注自此可读作「已按裁定 85.1 改判」。**
> **E 仍不改 D 的文书、不改 `work/project_parameters.json`**（参数表 rev16 由 D 落）。

### 6.1 五个可归因分量（不是只报一个"快了多少"）

`env.step()` 里的 **3 次 480×640 渲染是 `gym_aloha/tasks/sim.py:92-94` 硬编码的**（`top`/`angle`/`front_close`），
改它要动 site-packages（禁止）⇒ 把成本拆开测，D 才能按主线的真实用法取数：

| 分量 | 含义 | 主线对应 |
|---|---|---|
| `physics_only` | 每控制步 17 次 `physics.step()`，不渲染 | 物理成本下限 |
| `render_3cam_224` | 每控制步 3 次 `physics.render(224²)`，相机 `angle`/`left_wrist`/`right_wrist`（**与 A2 同一组**） | π₀.₅ 的像素输入口径 |
| `render_native_3cam_480x640` | 每控制步 3 次 480×640（`top`/`angle`/`front_close`） | env 内建渲染的**单独成本** |
| **`env_step_native`** | 完整 `env.step(action)`（= 内建 3×480×640 渲染 + 17 substeps） | **主线现状**（S1/S5 直接用 gym-aloha 就是这个） |
| `env_step_plus_3cam_224` | `env.step()` + 额外 3 次 224² | 若主线要自采 224² 像素喂 π₀.₅ |

动作序列：`np.random.default_rng(seed).uniform(-1,1,(30,14))`，**两臂逐字相同**；每分量前各 3 步预热。

### 6.2 主表（聚合 ctrl-steps/s，中位数 of 2 reps；括号 = 每控制步 ms）

| 后端 | workers | `physics_only` | `render_3cam_224` | `render_native_480x640` | **`env_step_native`** | `env_step_plus_3cam_224` |
|---|---|---|---|---|---|---|
| `egl_nvidia` | 1 | 1374.84 (0.728) | 187.16 (5.344) | 175.58 (5.696) | **136.99 (7.300)** | 78.39 (12.757) |
| `egl_nvidia` | 2 | 2729.64 (0.732) | 344.61 (5.804) | 319.02 (6.269) | **267.22 (7.492)** | 150.32 (13.318) |
| `egl_nvidia` | 4 | 5508.45 (0.725) | 665.91 (6.050) | 624.99 (6.266) | **504.69 (7.934)** | 292.24 (13.680) |
| `egl_nvidia` | 8 | 10878.78 (0.732) | 945.62 (8.514) | 820.65 (9.814) | **749.38 (10.486)** | 420.84 (18.989) |
| `osmesa` | 1 | 1351.75 (0.740) | 14.56 (68.696) | 12.37 (80.891) | **10.84 (92.374)** | 6.21 (161.331) |
| `osmesa` | 2 | 2653.87 (0.754) | 23.36 (85.709) | 22.02 (90.846) | **19.12 (105.000)** | 11.59 (172.980) |
| `osmesa` | 4 | 2977.82 (1.536) | 21.77 (185.689) | 16.09 (252.476) | **19.46 (205.394)** | 12.12 (330.741) |
| `osmesa` | 8 | 4564.51 (3.111) | 22.37 (359.041) | 16.71 (478.646) | **17.79 (448.147)** | 10.50 (767.515) |

**34.0 ms 预算判定（裁定 53-2）**：GPU 臂**五个分量 × 四个并行度全部在预算内**（最坏 **18.989 ms = 56% 预算**，
出现在 w=8 的 `env_step_plus_3cam_224`；主线现状口径 `env_step_native` 最坏 **10.486 ms = 31% 预算**）；
CPU 臂**除 `physics_only` 外全部超预算**（w=1 已 **92.374 ms = 2.72×**，w=8 恶化到 **448.147 ms = 13.2×**）。
⇒ **"29.4118 Hz 实时闭环"在 CPU 软渲染下不可能，在 GPU 渲染下主线口径有 1.6–4.7× 余量**（这是 E 给 D 的核心结论之一）。
**注**：22:3x 版写的"最坏 10.10 ms = 30% 预算 / 3–6× 余量"来自被作废的 221443，**现值更保守**（余量变小，但结论方向不变）。

**osmesa 臂的跨轮摆动必须一并读**：`osmesa` 的 `physics_only` 在 w=4/w=8 出现 **spread 87.88% / 17.24%**
（`INVALIDATED_RUNS.json` 的 C5 附带观察：跨轮摆动 ±41%）⇒ **CPU 臂在共租机上是噪声主导**，
它的 w≥4 数字**只能读趋势、不能读单点**（GPU 臂同批 spread 全 ≤5.25%）。

### 6.3 并行扩展效率（相对同后端 w=1 的聚合吞吐）

| 后端 | w=2 | w=4 | w=8 | 读法 |
|---|---|---|---|---|
| `egl_nvidia` `env_step_native` | 0.975 | **0.921** | **0.684** | **w≤4 近线性、w=8 明显次线性**；渲染虽卸载到 GPU，但 w=8 时 CPU 侧（物理 + Python + 12 核配额）成为瓶颈 |
| `egl_nvidia` `render_3cam_224` | 0.921 | 0.889 | **0.632** | 同上，且更早开始掉（纯渲染路径对 GPU 上下文切换更敏感） |
| `egl_nvidia` `render_native_480x640` | 0.908 | 0.890 | **0.584** | 同上 |
| `egl_nvidia` `env_step_plus_3cam_224` | 0.959 | 0.932 | 0.671 | 同上 |
| `egl_nvidia` `physics_only` | 0.993 | **1.002** | 0.989 | 纯 CPU 但**几乎完美扩展到 8**（12 核配额还没吃满）⇒ **w=8 的掉速全部来自渲染侧，不是物理侧** |
| `osmesa` `env_step_native` | 0.882 | 0.449 | **0.205** | **CPU 软渲染在 w≥4 崩溃**（渲染线程抢 12 核配额，`nr_throttled` 单批涨 300–800） |
| `osmesa` `render_3cam_224` | 0.802 | 0.374 | **0.192** | 同上 |

⇒ **`parallel_eval_workers_cap=4` 是 CPU 渲染口径的上限，GPU 渲染下 8 仍在扩展（聚合 +48% over w=4），
但扩展效率只有 0.684，不是 22:3x 版写的 0.988「近线性到 8」**（那个数出自被作废的 221443）。
**每 worker 延迟 w1→w8 = 7.300 → 10.486 ms（预算 21% → 31%）**，仍在预算内但余量收窄。
**每 worker 显存 ~102 MiB、w=8 实测 815 MiB / util 99%**（`nvidia-smi` 整机口径，本轮 GPU 批全部独占卡）。
⇒ **w=4 是延迟甜点，w=8 只有聚合吞吐价值**；上限该定几**由 D 裁**（回流单 §4-2 给建议值 + 依据，
并已点名裁定 77.2 的"近线性"依据在干净数据下不成立）。

### 6.4 后端标签完整性（**标签不许自证**）

每批记 `label_integrity`，判据 = **四条实证**同时成立（22:3x 版是三条，第 ① 条的做法已被推翻，见下）：
① **批级独立子进程**探针 `gl_identity_probe()` 取到的 `GL_RENDERER` 原文
   （GPU 臂含 `NVIDIA` 且不含 `llvmpipe`；CPU 臂反之）——**绝不与被测 env 同进程**；
② **每个 worker** 的 `/proc/self/fd` 里的 `/dev/nvidia*`（GPU 臂必须有，CPU 臂必须为空；本轮 GPU 臂 1/2/4/8 个 fd 全中）；
③ `/proc/self/maps` 里已加载的库（GPU 臂有 `libEGL_nvidia/libnvidia-eglcore/libnvidia-glcore`；CPU 臂有 `libOSMesa.so.8.0.0`）；
④ **渲染双闸** `render_health_ok` = `render_liveness`（渲→走物理→再渲，sha **必变**）
   ∧ `render_fidelity`（回到同 seed reset 态重拍，差必须在 LSB 级容差内）。
**16/16 批 `ok=true`、`mismatches=[]`、`gl_identity_probe_ok=true`、`render_health_all_ok=true`。**
`build_sweep` 的入场条件 = `all_ok ∧ render_health_all_ok ∧ label_integrity_ok`，**不满足的批进 `_excluded_batches`，
不静默丢弃**（本轮 `_excluded_batches=null`，即 16/16 全入场）。

> **① 的做法为什么被换掉（这是本文最重要的一处更正）**：22:3x 版写的是"裸 mujoco **同线程**渲染后取 `GL_RENDERER`"。
> 那个做法**本身就是污染源的成因**：在被测 env 同进程、且 dm_control 已渲过图之后建/关裸 `mujoco.Renderer`
> （顺序 `raw_after`）会破坏共享的 `EGLDisplay`，使 GPU 臂后续所有 `physics.render` 退化
> ⇒ **渲染吞吐虚高 +27%～+95%**（`RAW_PROBE_INTERFERENCE.json` 实测 egl 臂 **+31.0%**）。
> 这就是 §6.0 里 221443 被作废的根因，也是 D 立红线 **`bare_renderer_same_process_ban`**（裁定 82.5）的依据。
> **修法** = GL 身份改由**独立子进程**取（`gl_identity_probe()`），被测 env 进程里**一个裸 Renderer 都不建**
> （产物里 `RAW_XML` / `gl_strings_raw_mujoco` 字段已清零）。

> **一个必须记下的读法坑（仍然有效）**：`glGetString` 在 **CPU 臂的主线程里返回三个 `None`** —— 因为 dm_control 把渲染
> 放在**独立渲染线程**里 make current（`dm_control/_render/executor/render_executor.py`），OSMesa 上下文
> 不在主线程；EGL 臂却能取到。⇒ **不能拿主线程 `glGetString` 当 CPU 臂的后端证据**（会误判成"标签拿不到"）。
> 22:3x 版为此改用"裸 mujoco 同线程渲染"，**代价是污染**；现版改用**独立子进程**，两臂都取得到且不碰被测 env。
> 这与 A2 shim 里 `_deref` 的教训同族（裁定 53.3：连**读法**都不能跨 venv/跨包装层搬）。同一族的第二个坑：
> `physics.model` 在本 venv 是 **dm_control 的包装类**，`mujoco.mj_id2name(model, …)` 直接 `TypeError`
> ⇒ 相机名要用 `model.camera(i).name`。
> **第三个坑（本轮新增，跨线影响最大）**：**egl 下图像不是逐位确定的**，任何 sha/逐位比对在 GPU 臂都会**间歇性假红**
> ⇒ 详见 §6.6 与 `RENDER_DETERMINISM_REPS5.json`。

### 6.5 图像语义跨后端一致性（同 seed=1000、同 reset、同动作序列）——**22:3x 版此处有错，已更正**

**22:3x 版的错误**：那张表把 **`osmesa` 列抄成了 GPU 值**（两列几乎逐字相同、差写成 0 / <1e-4），
于是得出"换后端图像完全一致"的结论。**真实情况是 GPU 相对 CPU 系统性略暗**：

| 相机 | `osmesa` mean/std | `egl_nvidia` mean/std | **GPU 相对 CPU** |
|---|---|---|---|
| `angle` 224² | **36.3300** / 45.0775 | 36.2230 / 44.9601 | **−0.2945%** |
| `left_wrist` 224² | **76.7020** / 57.1019 | 76.6050 / 57.0416 | **−0.1265%** |
| `right_wrist` 224² | **77.6930** / 57.8581 | 77.6540 / 57.8302 | **−0.0502%** |
| `top` 480×640 | **39.8720** / 50.7539 | 39.8500 / 50.7198 | **−0.0552%** |
| `angle` 480×640 | **33.6030** / 46.9168 | 33.5190 / 46.8419 | **−0.2500%** |
| `front_close` 480×640 | **23.9130** / 38.5610 | 23.9040 / 38.5381 | **−0.0376%** |

- **差值区间 = −0.0376% ～ −0.2945%，且六相机全部为负** ⇒ 这是**系统性偏移**（GPU 光栅化/色彩路径与 llvmpipe 不同），
  **不是随机噪声**（随机的话不会六项同号）。
- **⇒ 结论要改口径**：不是"换后端图像逐字一致"，而是"**换后端不改变图像语义，但有 ≤0.3% 的系统性亮度偏移**"。
  这个量级**远小于**任何会影响策略行为的尺度，但**任何拿"跨后端 mean 完全相等"当判据的闸都会误判**。
  与 D 已验收的 480×640 单帧结论 `39.892 → 39.869`（−0.058%）**同向同量级** ⇒ 两处互证。
- **两个差异来源必须分开，不可混为一谈**（这是本轮最容易读错的一点）：
  ① **跨后端系统偏移 = 0.038%–0.295%**（本节，GPU vs CPU）；
  ② **同后端 LSB 抖动 ≤ 0.052%**（§6.6，egl 下同状态重复渲染）。
  ①**有方向、可复现**；②**无方向、不可逐位复现**。二者量级接近但**性质完全不同**。
- **吞吐数字仍不得跨后端搬用**（裁定 46.4/53.6）。证据：`summary_20260929_234814.json` →
  `batches[*].images_at_reset_w0`（本节六行全部由该文件现算，未手抄）。

### 6.6【本轮新增】egl 下渲染**不是逐位确定的**（跨线影响最大的一条，S1 验收前置）

**产物**：`RENDER_DETERMINISM.json`（n=2）→ **`RENDER_DETERMINISM_REPS5.json`（n=5，2050 ln / `767a2d984a5b`）**；
生成器 `scripts/e_render_determinism.py`（**289 ln / `2449fef70b93`**）。同 seed=1000、同 reset、同状态重复渲染，
**5 个独立进程**（= "跨采集批次复现"的真实场景）。

| 后端 | 相机 | 进程内逐位（5 rep） | **跨进程同 sha** | 最坏 `max_abs_diff` | 最坏 `frac_diff_px` |
|---|---|---|---|---|---|
| `egl_nvidia` | `angle` | **4/5 det、1/5 NONDET** | **❌** | 1 | **0.0020%** |
| `egl_nvidia` | `left_wrist` | 0/5 det（`n_unique_shas` 4–5） | **❌**（n=2 时曾是 ✅ ⇒ **那是运气**） | 1 | 0.0239% |
| `egl_nvidia` | `right_wrist` | 0/5 det（`n_unique_shas` 恒 6） | **❌**（5 个进程 5 个不同 sha） | 1 | **0.0518%** |
| `osmesa` | 三相机全部 | **5/5 全 det** | **✅ ×3** | **0** | **0.0** |

- **⇒ egl 下没有任何一个相机在"跨进程"意义上逐位可复现**；**osmesa 下三相机在 5 个独立进程里全部逐位一致**。
- **判据后果（三条，都是硬的）**：
  ① **不能用 sha/逐位相等做 egl 下的渲染保真闸** —— 会**间歇性假红**，而且**假红不可复现**（重跑一次大概率又绿）
     ⇒ 这是最坏的一种闸：**随机红**。E 自己的旧 fidelity 闸就因此在干净臂 4/4 假红
     （根因已由 `GATE_POLARITY_RECHECK.json` 反事实重算**确认为 `confirmed`**，6/6 判据）。
  ② **`angle` 逐位不能再当硬判据**：裁定 82⑤/83.4 写的"`angle` 必须逐位一致（实测成立）"来自 n=2/n=3；
     **n=5 实测 4/5** ⇒ 若继续当硬判据，预期 **~1/5 概率的间歇性假红**（已报 D，请转 B2）。
  ③ **状态量逐位仍是硬判据**（不受本条影响）：本条只关于**像素**。
- **量级判定（给 D/用户的比例尺）**：最坏 **0.0518% 像素差、1 LSB**，比 fork ⑤ 当初设的 **1% 门槛低 19×**，
  比跨后端系统偏移（§6.5，0.038%–0.295%）**小 2–6×** ⇒ **不构成"图像语义变了"**。
- **裁定 83.3 的可推翻条件③ 已被触发**（`angle` 也开始不逐位）⇒ 产物里机器现算字段
  `falsification_conditions_ruling_83_3 = {any_condition_met: true, ruling_83_3_stands: false}`。
  **E 不自决**，三条路（甲＝改走 osmesa 采集 / 乙＝`angle` 降为容差判据 / 丙＝乙 + 保留 osmesa 作对照，**E 倾向丙**）
  与代价已写在 `daily_report.md` §E11.2，**回到用户裁**。
- **D 定的 replay 容差在 n=5 下仍够用**（其可推翻条件②未触发）：`replay_max_abs_diff<=2`（实测最差 **1**）、
  `replay_frac_diff_px<=0.005`（实测最差 **0.000518**，余量 **9.7×**）⇒ **裁定 83.4 的三个数值不需重定**。

---

## 7. E3-4：与 A2 共卡时的吞吐与显存 —— **状态词改为「未交付」**（22:3x 版的结论已作废）

> **⚠ 本节 22:3x 版给出的"共卡退化 ≤8%、w=4 在噪声内 ⇒ 渲染并行度 4 与 A2 推理共卡是安全的"这一结论，
> E 现在撤回，状态词改为「未交付」。** 三条理由：
> ① 下表"独占卡（权威轮）"那一列取自 **221443**，而 221443 的 GPU 渲染族**已被作废**（§6.0）⇒
>    **比值的分母是脏的**，−8.0% / +0.6% 这些差值不成立；
> ② 共卡轮 **222019** 自己的 GPU 渲染族**同样被作废**（`INVALIDATED_RUNS.json` 的 `invalidated[1]`，
>    `max_gpu_render_inflation_pct=56.0`，另附 `proxy_a2` **误标**）⇒ **分子也是脏的**；
> ③ **假体模式现已被禁止**：裁定 83.0 立红线 `cotenant_injector_must_be_gated`，裁定 84 §5 对本轮明令
>    「`--cotenant` 一律不得启用」⇒ **要拿到干净的共卡数字，必须由 D 排一个真窗口**（E 不再自行起假体）。
> **⇒ 共卡吞吐/显存 = 未交付；23:58 那次尝试是事故（§10.3），其产物 `summary_20260929_235835.json` 留档禁用。**
> **仍然有效的部分**：显存量级（**~102 MiB/worker**，w=8 实测 **815 MiB / util 99%**，独占卡、234814 轮）
> 与"A2 的 π₀.₅ 占 ~15 GB ⇒ 80 GB 卡上两者相加 <20%"这个**容量**判断（容量是加法，不受吞吐污染影响）。

D §8.3-4 要求测"A2 训练并发占用同一张卡时"的吞吐与显存。本轮实际情况（**已落更正件**
`runs/infra/e_mainline_calib_20260929/COTENANT_CORRECTION.json`）：

- E 准备的**占位假体**（torch 13.8 GB 球重 + 4096² fp16 matmul，仿 A2 训练占用）**从未启动** ——
  开跑前闸检测到卡上已有别人的 compute 进程（`existing_compute_procs = ["559213, 1758"]`）⇒ 按"不得抢卡"放弃。
- 因此 `summary_20260929_222019.json` 那 4 批是在**一个真实共租进程**下测的：**PID 559213**，
  显存轨迹 **2158 → 14990 MiB**、`util` 冲到 **100%**。归因 = **A2 的 π₀.₅ 闭环延迟重测**
  （`scripts/a2_egl_latency_remeasure.py` mtime 22:15:53；其产物 `latency_mainline_egl_gpu_pi05.json`
  `generated_at=22:17:00`、文件 mtime **22:21:26**，完整覆盖 E 的 22:20:19–22:21:30 批次；显存量级与 π₀.₅ fp32 一致）。
  **归因强度 = `inferred_from_timeline`**（容器内 `nvidia-smi` 的 `process_name` 为空、该 PID 在 E 的命名空间不可见），
  **不是 `confirmed`**；且那是**推理**不是**训练**，共租方正在**加载/爬显存**（非稳态）。
- **E 真正占卡 ≈6.5 s**（两个 `egl_nvidia` 批各 ~3 s；两个 `osmesa` 批纯 CPU 不占卡）。
  **程序问题自报**：开跑前闸只挡了假体、**没挡 E 自己的 GPU 批次** ⇒ 已修为**批级闸**
  （每个 GPU 批开跑前重查 `other_compute_procs`，非空且未显式给 `--allow-shared-gpu` 就跳过并登记 `skipped_batches`）。

| 分量 | 独占卡（**221443，已作废**） | 与 A2 π₀.₅ 推理共卡（**222019，GPU 渲染族已作废**） | 变化（**不成立**） |
|---|---|---|---|
| `egl_nvidia` w=1 `env_step_native` | ~~172.32~~ | ~~158.62~~ | ~~-8.0%~~ |
| `egl_nvidia` w=1 `render_3cam_224` | ~~242.06~~ | ~~232.17~~ | ~~-4.1%~~ |
| `egl_nvidia` w=1 `physics_only` | 1375.97 | 1325.04 | −3.7%（**`physics_only` 未受污染，此行仍有效**） |
| `egl_nvidia` w=4 `env_step_native` | ~~702.98~~ | ~~706.86~~ | ~~+0.6%~~ |
| `egl_nvidia` w=4 `render_3cam_224` | ~~909.17~~ | ~~917.77~~ | ~~+0.9%~~ |
| `osmesa` w=1 / w=4 `env_step_native` | 10.45 / 19.68 | 10.75 / 17.94 | +2.9% / −8.8%（**osmesa 臂未受污染，此行仍有效**） |

**干净的独占卡对照值（234814，供将来重测共卡时当分母）**：`egl_nvidia` w=1 `env_step_native` = **136.99**、
`render_3cam_224` = **187.16**、`physics_only` = **1374.84**；w=4 依次 **504.69 / 665.91 / 5508.45**。

**显存**：E 的渲染 worker **~102 MiB/个**（w=1 → 92–102 MiB；w=4 → 408–522 MiB；w=8 → 769–1034 MiB，
`nvidia-smi` **整机**口径，含共租方）；A2 那轮 π₀.₅ 占 **~15 GB** ⇒ **80 GB 卡上两者相加 <20%**。
负载对：`loadavg 37.35/45.58` → `36.46/43.94`，`nr_throttled 9072 → 9477`。

⇒ **撤回的结论**：~~与 A2 推理共卡时渲染吞吐退化 ≤8%（w=1）、w=4 在噪声内 ⇒ 渲染并行度 4 与 A2 推理共卡是安全的~~。
**现在的状态词 = 未交付**：推理共卡与训练态共卡**都需要 D 排窗口后重测**（用 234814 当独占卡分母）。
**E 不再自行起假体**（裁定 83.0 红线 + 裁定 84 §5 明令）。

---

## 8. 负载对总表（**每个数字都要能追回它当时的机器状态**）

| 批次 | 时间 | `loadavg`（1 分/5 分） | `nr_throttled` | GPU |
|---|---|---|---|---|
| E1 precheck + green×2 + M1 + M2 | 21:31–21:34 | 51.02 / 50.79 | 3422 → 3428 | 独占 |
| E2 gym-aloha A/B（3 臂 ×3 重复） | 21:38–21:40 | 47.49 / 49.29 → 50.08 / 49.61 | 3532 → 3667 | 独占 |
| E2 单臂 Piper A/B（3 臂 ×3 并行度 ×3 重复） | 21:41–21:47 | 49.72 / 49.55 → 53.83 / 50.91 | 3667 → 3749 | 独占 |
| E3-1 激活件三臂自证 | 21:54 | 35.20 / 37.57 | 3771 → 3772 | 独占 |
| 首轮扫描（仅留档） | 22:04–22:13 | 38.9 → **81.71 / 57.90** | 3754 → 6494 | 独占 |
| ~~E3 权威轮~~ → **已作废轮**（16 批，GPU 渲染族） | 22:14–22:19 | 39.41 / 45.12 → 51.66 / 49.13 | **6529 → 9072** | 8 个 GPU 批全部独占 |
| E3-4 共卡轮（4 批，GPU 渲染族**已作废**） | 22:20–22:21 | 37.35 / 45.58 → 36.46 / 43.94 | 9072 → 9477 | **与 A2 π₀.₅ 共卡** |
| E1 复跑（green×2 + M1） | 22:30 | 37.27 / 38.35 | 9486 → 9491 | 独占 |
| **冒烟 `e_mainline_calib_smoke_v4`**（两臂） | 23:09 | 见产物 | 见产物 | 独占（GPU 臂 `NVIDIA A800/590.48.01` + `/dev/nvidia2`；osmesa 臂 llvmpipe + 无 fd） |
| **取证轮**：raw-probe 干扰（12 run）+ 渲染确定性（n=2） | 23:2x–23:45 / 23:30–23:40 | 38.62 / 39.44 → 42.74 / 40.07；45.76 / 40.22 → 45.38 / 40.24 | **10045 → 10104**；**9941 → 9968** | 是（egl 臂）；开跑前 `gpu_before={util 0, mem 0, procs []}` |
| **E3 权威轮（去缺陷重跑，16 批）** | **23:48:14–23:54:08** | **39.10 / 39.29 → 33.88 / 39.50** | **10227 → 12852** | **8 个 GPU 批全部独占**，w=8 实测 **util 99% / 815 MiB** |
| ~~23:58 共卡尝试~~ = **抢卡事故轮**（留档禁用） | 23:58:35–23:59:55 | 见 `GPU_YIELD_INCIDENT_2358.json` | 见该件 | **压进 A2 的 `quiet_window_rep1`**（§10.3） |
| **离线复判**（`GATE_POLARITY_RECHECK.json`） | 00:34 | 25.69 / 24.55 / 28.82 | 已记 | **否**（`gpu_used=false`、不渲染、不起子进程） |
| **`reps=5` 确定性扩展轮**（10 run） | **00:48:59–00:49:50（≈51 s）** | **29.44 / 32.05 / 29.62 → 28.18 / 31.64 / 29.52** | **14672 → 14705（Δ33）** | 是；**10/10 run 全跑、0 跳过**；00:50:48 销账 `0 MiB / apps 空` |

分母口径：**cgroup 12 核**（`cpu.cfs_quota_us=1200000`/`period=100000`），**不是** `nproc`=112。
`nr_throttled` 全程在涨（**3422 → 14705**）⇒ **机器一直很忙，任何单点吞吐数字都不应当常数搬用**。
**未申报开轮的两轮（23:2x 取证轮、23:48:14 标定轮）已在 `daily_report.md` §E6 事后补报**（裁定 83.0-5），
E 认账：违反裁定 82⑤ 附加条件，且**不能按"指令未落盘"免责**。

---

## 9. 边界与不做的外推

- **本节所有 GPU 数字都来自 prefix-only**；系统目录**当前干净**（`boundary_guard` 每批前后 + 末态都核过：
  `/usr/share/glvnd/egl_vendor.d/` 只有 `50_mesa.json`；`/usr/lib/x86_64-linux-gnu/` 无 NVIDIA 渲染库；
  `ldconfig -p` 四类库命中 0）。21:02–21:18 的违规安装已全量回滚，D 独立复核干净（裁定 60）。
- **容器重启后**：前缀在 NFS ⇒ **库不丢**；但环境变量**不会自动生效**，各线必须自己
  `source scripts/e_activate_gpu_render.sh`（或在自己的进程里注入同样三个变量）。
  **根治仍建议平台侧把 `NVIDIA_DRIVER_CAPABILITIES` 加 `graphics`**（让运行时自己注入），但那**不再是阻塞项**。
- **未测/不外推**：ManiSkill 像素档在 prefix-only 下的吞吐（E1 那批是系统安装态测的，**未重测**）；
  Vulkan 在 prefix-only 下的 ICD 枚举（同上）；robosuite/LIBERO 在 prefix-only 下的吞吐（同上）；
  **S1/S5 的后端选型未实施**（E 只给建议）；训练态共卡（需 D 排窗）。
- **`scripts/check_gpu_render.py` 的 `gpu_render_possible` 仍是 `False`**：它是**静态启发式**
  （要求 `/dev/dri` + `graphics` capability），prefix-only 解锁后也不会变绿 ⇒ **不能再当"能不能 GPU 渲染"的闸**。
  该脚本属冻结面，E 未改动；已在 `docs/infra-gpu-render.md` §7.2 写明，是否修订由 D 裁。
- **`docs/infra-gpu-render.md` 已追加 §7**（四处被推翻的结论逐条 + 证据路径，**追加不覆写**，
  并点名移交原作者线 = 环境调研线 `f19470f`）。

---

## 10. 程序问题自报（**四次，全部已修或已报 D 排期**；按裁定 60 主动登记，不等被查）

> 本节是 22:3x 版没有的。E 的立场：**测量事故比测量结果更重要**，因为这四次里有两次
> 直接改变了主线判据（§10.1 作废了权威值、§10.4 触发了裁定 83.3 的可推翻条件）。

### 10.1【第一次·最严重】**E 的探针污染了 E 自己的两轮产物** ⇒ 权威值 `172.32` 作废

- **事实**：`e_mainline_render_calib.py` 早期版本为了取后端身份，在**被测 env 同进程**、
  且 dm_control **已渲过图之后**建/关了一次裸 `mujoco.Renderer`（顺序 = `raw_after`）。
- **代价（实测，不是推断）**：GPU 臂后续所有 `physics.render` 退化 ⇒ **渲染吞吐虚高**
  （`RAW_PROBE_INTERFERENCE.json`：egl 臂 **+31.0%**、`fidelity_ok_all=false`；`INVALIDATED_RUNS.json`：
  两轮最大虚高 **+125.3% / +56.0%**）。**osmesa 臂不受影响**（+4.1%，在噪声带内）⇒ 污染是 GPU 臂特有。
- **作废范围**：`summary_20260929_221443.json` 与 `summary_20260929_222019.json` 的
  **仅 GPU 臂渲染类四个分量**（`render_3cam_224` / `render_native_3cam_480x640` / `env_step_native` / `env_step_plus_3cam_224`）。
  **仍有效**：两轮的 `physics_only`、整个 osmesa 臂、`images_at_reset_w0`（探针在其之后才跑）。
- **修法（已生效）**：① 删掉同进程裸探针，GL 身份改由**独立子进程** `gl_identity_probe()` 取
  （产物里 `RAW_XML` / `gl_strings_raw_mujoco` 已清零）；② 加**渲染双闸** `render_health_ok`
  = `render_liveness`（渲→走物理→再渲，sha **必变**）∧ `render_fidelity`（回同 seed reset 态重拍，差在 LSB 级容差内）；
  ③ `build_sweep` 入场条件 = `all_ok ∧ render_health_all_ok ∧ label_integrity_ok`，被排除批进 `_excluded_batches`（**不静默丢弃**）。
- **纪律提案（D 已采纳为红线 `bare_renderer_same_process_ban`，裁定 82.5）**：
  > **禁止在被测 env 同进程、且 dm_control 已渲过图之后建/关裸 `mujoco.Renderer`**；
  > 需要 GL 身份就另起独立子进程，或放在 `make_env` 之前。
- **跨线排查（A2 已免责，D 采纳）**：A2 `scripts/a2_egl_latency_remeasure.py:702` 的 `gl_identity_via_mujoco()`
  在 `make_env`（`:761`/`:771`）**之前** ⇒ 属 `raw_first`，**安全**；A2 的 `gl_identity_after_dm_render`（`:195`）
  只调 `glGetString`、**不建** Renderer ⇒ **亦安全**。⇒ **A2 的延迟产物不受本效应污染。**
- **遗留欠账（报 D 排期）**：`scripts/e_rawprobe_interference.py` 的 docstring 仍写"`sha12` 必须逐字相同"（旧语义），
  与实现的容差判据**自相矛盾** ⇒ 判定 `stale_docstring`（裁定 78.5 同族）。**E 未改**，因为它的 sha `74e8afe88a4d`
  已被裁定 82 §4 引用、且 egl 臂不能随时重跑（改了会造成"代码新、产物旧"）。

### 10.2【第二次】**抢卡闸只挡了一半**（22:20）⇒ 已修为批级闸

开跑前闸检测到卡上有别人的 compute 进程 ⇒ **正确放弃了假体**，但**没同时挡住 E 自己的 GPU 批次**，
结果在 A2 上卡期间跑了 **≈6.5 s** 的 `egl_nvidia` 批。**修法** = 批级闸（每个 GPU 批开跑前重查）。
副作用（好的那面）：那 4 批成了真实 A2 并发数据，但文件名 `proxy_a2` 是**误标** ⇒ 已落 `COTENANT_CORRECTION.json` 更正（**不重命名文件**）。

### 10.3【第三次·E 全责】**23:58 抢卡事故**：E 的假体压进了 A2 的权威窗口

- **事实**：E 的 `proxy_a2` ballast（**PID 156355、14714 MiB、100% util**）在 **23:58:39–23:59:55（76 s）**
  压进了 A2 裁定 76.4 的 `quiet_window_rep1`，占该申报窗口的 **50.4%**。
- **A2 无过错**：A2 起跑时卡为空、批级闸合法通过；**A2 自己的运行时采样器抓到了**（76 样中 20 次记到 PID 156355）
  并**自判 `contaminated=true`、拒绝权威**（证据 `runs/vla/a2_egl_latency_20260929/latency_quiet_window_rep1.json`）。
  ⇒ **裁定 76.3 的机制在真实事故里第一次被验证有效**（D 已给 A2 记功）。A2 已于 00:02 跑完 rep2。
- **根因（D 的定性，E 认）**：**闸装在受害者一侧，没装在伤害源上** —— E 的**测量批次**过了闸
  （`summary_20260929_235835.json` 有 `skipped_batches` 2 条），但 **E 的注入器本身没过闸**
  （`cotenant_started.gpu_after_start.compute_procs=["154563, 14990","156355, 14714"]` 证明 E 是**起完 ballast 之后**才看到 A2）。
- **修法（已生效，三网并查 `card_busy()`）**：① `nvidia-smi --query-compute-apps`；
  ② **扫 `/proc/*/fd` 找持有 `/dev/nvidia*` 的进程**（能看见"已起跑但尚未分配显存"的进程 —— **这正是 23:58 的盲区**）；
  ③ cmdline 网分两档（窄档 `GPU_INTENT_PATTERNS` 用于批级闸；宽档 `OTHER_LINE_SCRIPT_RE=(?<!\w)scripts/(a2?|b2?|c2?|d)_` 仅用于起假体）。
  **起假体须显式 `--i-have-declared-gpu-window`**，缺旗标 ⇒ `refused_no_declared_window`（不起假体、不跑 GPU 批）；
  **假体起后 20 s 复查**，命中他线即撤（`withdrawn_other_line_appeared`）。
- **⇒ 第一次生产验证（00:42:53，E 自己被别人拦住）**：`compute-apps` 报**空**，但 fd 网抓到
  **PID 235015 持有 `/dev/nvidia2`+`/dev/nvidiactl`**、cmdline = `b2_s1_generate_dataset.py --stage pilot`
  ⇒ `card_busy(strict=True)=True` ⇒ **E 没开窗、让位 B2**（`daily_report.md` §E1）。
  **如果 E 还按 23:58 之前的写法只看 `compute-apps`，此刻已经压进 B2 的 S1 pilot 了。**
- **D 已立红线 `cotenant_injector_must_be_gated`**（裁定 83.0）；产物 `GPU_YIELD_INCIDENT_2358.json` 留档，
  该轮 `summary_20260929_235835.json` **留档禁用**（`batches[*].verdict=None`，按裁定 78.3 不计绿）。

### 10.4【第四次·最新】**`reps=5` 扩展轮触发了裁定 83.3 的可推翻条件③**（`angle` 也开始不逐位）

- **事实**：n=2/n=3 时 `angle` 相机在 egl 下**看起来**逐位确定（裁定 82⑤ 因此把"`angle` 逐位"钉成**硬判据**）；
  **n=5 实测 4/5 逐位、1/5 不逐位**，且**跨进程 sha 不一致**（`3b7b688775e6` vs `226469658cba`×4）。
  `left_wrist` 的"跨进程稳定"同样被推翻（n=2 记 ✅，n=5 是 3/5 同、2/5 异 ⇒ **那是运气**）。
- **⇒ 裁定 83.3 预登记的可推翻条件③ 触发**，产物机器现算字段
  `falsification_conditions_ruling_83_3 = {any_condition_met: true, ruling_83_3_stands: false}`。
  另两条（`frac_diff_px>1%`、`max_abs_diff>8`）**未触发**（实测最差 **0.0518% / 1 LSB**，低 19× / 8×）。
- **即时跨线影响（已报 D，请转 B2）**：若 B2 的 replay 闸继续拿 `angle` 逐位当硬判据，
  **预期 ~1/5 概率的间歇性假红，且假红不可复现**（重跑大概率又绿）⇒ 最坏的一种闸：**随机红**。
  建议 D 裁之前 B2 把 `angle` 也按"只登记不判红"处理，**只保留"状态逐位"为硬判据**。
- **E 不自决**：甲（改走 osmesa 采集，代价 = S1 墙钟放大 **12.64×**）／乙（`angle` 降为容差判据）／
  **丙（E 倾向：乙 + 保留 osmesa 作逐位对照后端）**，三条路与代价见 `daily_report.md` §E11.2 ⇒ **回到用户裁**。
- **方法学自证**：这一条是**D 要求扩到 N≥5 才暴露出来的**（裁定 83.4 明写"n=2 不足以支撑 left 跨进程稳定，可能是运气"）
  ⇒ **D 的怀疑成立，E 的 n=2 结论确实不够**。这也是 E 把可推翻条件从散文改成**机器现算字段**的理由：
  散文写的规则不会被自动检查，字段会。

### 10.5 四次的共同根因（E 的自查，不是辩解）

| # | 事故 | 表层原因 | **共同根因** |
|---|---|---|---|
| 1 | 探针污染自己的产物 | 想"顺手"多取一个后端证据 | **副作用没被量化就当免费** |
| 2 | 抢卡闸只挡一半 | 闸写在"开跑前"，没写在"每批前" | **闸装在错误的位置** |
| 3 | 23:58 压进 A2 窗口 | 闸装在受害者侧，没装在伤害源侧 | **闸装在错误的位置**（同 2） |
| 4 | n=2 就当"`angle` 逐位成立" | 样本量不足以支撑"全称"断言 | **用 n=2 证明"永远"** |

⇒ **E 的两条自我约束（已落成代码，不靠自觉）**：
① **任何"顺手的探针"都必须先量代价**（本轮的 `RAW_PROBE_INTERFERENCE.json` 就是为此而生）；
② **任何全称断言（"逐位确定"/"总是"/"从不"）都必须带样本量，且 n 要写进产物字段**
   （`reps` 现在是 `RENDER_DETERMINISM*.json` 的顶层字段，22:3x 版**缺这个字段**，D 只能从 run 数反推）。
