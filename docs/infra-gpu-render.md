# 本机渲染能力实测报告（2026-09-22）

> 复现：`python scripts/check_gpu_render.py --bench`
> **2026-09-29 补测见 §6**（ManiSkill3 state 档可用 + 容器 CPU 配额只有 12 核，两处推翻本文早先的判断）
> 结论一句话：**这台机器上 CUDA 计算完全正常，但 NVIDIA 的 GPU 渲染栈没有注入，
> 所有"渲染"实际都在 CPU 上跑（Mesa llvmpipe）。** `MUJOCO_GL=egl` 不会报错，
> 但它并不是真的在用 GPU —— 这是最容易误判的一点。

## 0.【重启 / 容器重建后，**先跑这一条命令**】（裁定 85.9-3-1，P0）

```bash
env -i /bin/bash /workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/scripts/e_coldstart_gpu_render.sh
```

- **`exit 0` ⇒ GPU 渲染可用**，可以采集标 `egl` 的数字。**`exit ≠ 0` ⇒ 一个标 `egl` 的数字都不要采**
  （因为失败可能是"静默退回 CPU 软渲染"：**92.374 ms/步（2.72× 预算）会被当成 7.300 ms/步**）。
- 失败时**看 stderr 第一行区分三种原因**（三种都不许采数，处置完全不同）：
  | stderr 关键词 | 自证件 exit | 含义 | 处置 |
  | --- | --- | --- | --- |
  | `测量无效（exit=2, invalid_measurement）` | 2 | 采样窗没覆盖渲染子进程 ⇒ L5/L5b/S2 读到的是「**没采到**」不是「测到没有」 | **把命令重跑一次**；仍为 2 才按下一种处置 |
  | `未通过（exit=1）` | 1 | 真没判成 NVIDIA GPU（库缺失 / 版本错配 / EGL 起不来 / 静默退回 CPU） | 查驱动版本与前缀（§7.2）；必要时按 §7 重装 |
  | `被边界闸拒绝（exit=3）` | 3 | 系统目录里出现了 NVIDIA 渲染库 / vendor ICD（裁定 60） | 先 `e_install_nvidia_gl_590.sh --uninstall` 回滚（**需 D 批准**） |
  > 冷启动命令**自己**只有 0 / 1 两种退出码（`e_fail` 一律 exit 1）；上表第 2 列是**它内部那份自证件**的退出码，
  > 已逐字落进产物（`selfcheck_egl_nvidia_<ts>.json` 的 `verdict` 字段：`pass` / `fail` / `invalid_measurement` / `refused`）。
  >
  > **【03:4x 更正 · E 自查出的退出码假绿】** 上一行「只有 0 / 1 两种」**已不成立**。冷启动命令自己的退出码现在是
  > **0 / 1 / 5** 三种：
  > | 命令 exit | 含义 | 可以采标 `egl` 的数字吗 |
  > | --- | --- | --- |
  > | **0** | C1–C4 全过，C4 **实测** `GL_RENDERER` 含 `NVIDIA` | **可以**（唯一一个"可用"码） |
  > | **1** | 任一环节失败（`e_fail`）；若来自 C4，stderr 会把内部自证件的 1 / 2 / 3 分开说 | **不可以** |
  > | **5** | **`E_SKIP_GPU=1`：只跑了 C1–C3，GPU 渲染根本没测** ⇒ **PARTIAL，不是通过** | **不可以** |
  > **为什么必须新增 5（而不是继续 exit 0 + 一行免责声明）**：裁定 89.5-1 之后 **`exit code` 就是权威判据**，
  > 那么"没测"就必须在**退出码这一维**上也看得见 —— 只看 `$?` 的调用方（编排器 / CI / `&&` 链）读不到散文里的免责声明。
  > **这与裁定 87.1-2 `partial_delivery_must_not_carry_a_whole_delivery_boolean` 是同一条纪律**：部分交付不得携带整体交付的布尔。
  > 5 与 `scripts/e_egl_coldstart.py` 顶层的 `PARTIAL` 档**同号同义**。**实测**：`E_SKIP_GPU=1` ⇒ `exit 5`、stdout 仍是
  > `COLDSTART_PARTIAL_OK …`、`nvidia-smi` 前后均 `0 MiB / 0 %`（未触卡）；`tooth_relink` 的断言相应从 `exit_zero` 改为
  > **`exit_partial_5`（精确等值，不是放宽）**，实测 `tooth_proven=true`
  > （证据 `runs/infra/e_egl_coldstart_20260930/COLDSTART_EVIDENCE_relinktooth_exit5.json`）。
- **成本**：墙钟 **秒级**（实测 `02:18:54` 全程 **1.33 s**）、GPU 只建一个 **64×64** 的图形上下文（`21:54` 实测峰值 **142 MiB**）、
  **可随时 kill**（前台单发、无守护、无后台残留）、**零系统写入**（前后各查一次边界闸，实测 `forbidden_paths_present=[]`）。
- **它做什么（四步，任一步失败即 exit≠0）**：`C1` 链路前提（NFS 前缀 + venv 本体 + **base 解释器**都在）→
  `C2` 重建 `/root/venvs/<name>` 符号链接（**这正是重启后必丢的那一环**）→ `C3` `eval` 激活件的 `--print`（裁定 70 的唯一合法激活方式）→
  `C4` 在**独立子进程**里实测 `GL_RENDERER` 并断言含 `NVIDIA`（裁定 82.5：绝不与被测 env 同进程）。
- **单命令、单前缀真源**：前缀只由 `E_GPU_RENDER_PREFIX` 一个变量决定（默认 `.codex-persist/egl-libs/590.48.01`），
  `C1` 检查的目录与 `C3` 激活到的目录**必然是同一个**（裁定 46.4 的根因就是两处定义漂移）。
  **无窗口 / 不想触卡时**：`E_SKIP_GPU=1 env -i … e_coldstart_gpu_render.sh` 只跑 C1–C3，
  输出会明写 **`COLDSTART_PARTIAL_OK …（未实测 GL_RENDERER，不构成裁定 85.9-3-1 的交付）`** ⇒ **它不会把"没验"伪装成"验过"**。
  **并且它 `exit 5`（不是 0）** —— 见上面那张三行表：文案诚实还不够，退出码也必须诚实。

### 0.1 **为什么必须人工跑：重启后没有任何东西会自动恢复**（④ 的实测结论，不是推测）

- `~/.codex` 的持久化靠一个 `watch` 守护进程（实测 PID 187229，`watch 120`），但它**只做单向镜像「本地 → NFS」，从不反向恢复**；
  恢复只发生在 `codex-persist bootstrap` / `auto` 里，而触发它的那个 `~/.bashrc` hook **本身就在 overlay 临时层** ⇒ 重建后 hook 也没了。
- `/root/venvs/*` 是**符号链接**，同样在 overlay 临时层 ⇒ 重建后必丢（NFS 上的 venv **本体**还在）。
- **⇒ 库本体（NFS）+ venv 本体（NFS）都在，但"把它们接起来的那几环"全在临时层。** 恢复是**机械的**，所以做成上面那一条命令；
  但**触发它必须靠人**（或靠外层编排显式调用）。D 在裁定 85.9-3-4 里的那个「若」成立。
- **还有一条 D 没点名的前提（E 补测出来的）**：NFS 上的 venv 只是**壳** —— `envs/pi05_sim/bin/python3.11` 是符号链接，
  指向 **`/opt/conda/bin/python3.11`**（`pyvenv.cfg` 的 `home=/opt/conda/bin`），而 `/opt/conda` 在 **overlay 的镜像只读层**。
  ⇒ **venv 能跨重建，当且仅当新镜像仍带同版本的 `python3.11`**；镜像换 python 小版本 ⇒ NFS 上的 venv 全体变悬空软链，
  激活件再对也没用。**C1 已把这条做成显式断言**（base 解释器存在 + venv 解释器真能起进程），所以这种情况会**响亮失败**而不是静默降级。
  机器可读的分层清单见 `PERSIST_MANIFEST*.json` 里每个路径的 `rebuild_class`：
  **`nfs`（15 项，`survives_container_rebuild=true`）/ `overlay_image_baked`（10 项，`conditional_same_image`）/ `overlay_runtime_upper`（4 项，`false`）**。

### 0.2 这条命令**自己也被验过有牙**（不是"写了就算"）

- **正向牙（裁定 85.9-3-3：静默回退必须响亮失败）**：在**沙箱副本**里把 `10_nvidia.json` 指向一个不存在的库（**真前缀一个字节不碰**）⇒
  实测冷启动 **exit 1**、自证件 `verdict=fail`、`render_probe.ok=false`（mujoco 在 `MUJOCO_GL=egl` 下**直接抛 `ImportError`，没有静默退回 osmesa**）、
  `child_nvidia_fds=[]`。四条腿里 **三条承重**（`selfcheck_verdict_fail` / `no_silent_fallback_to_cpu_renderer` / `coldstart_exit_nonzero`），
  第四条（`renderer_class != nvidia_gpu`）在 `gl_strings` 为空时是**平凡真** ⇒ 产物里如实标 `leg_strength=vacuous_true_when_no_gl_string`，**不冒充**。
- **反向牙（must_stay_green）**：真前缀 ⇒ 必须判成 `nvidia_gpu` 且 exit 0。**它在 `02:18:54` 咬到了 E 自己的件**：
  GPU 明明是好的（`GL_RENDERER=NVIDIA A800-SXM4-80GB/PCIe/SSE2`、400 帧渲出、`image_mean 75.73`、`libnvidia-eglcore` 确实加载），
  却报 exit 1 —— 根因是 `e_gpu_egl_verify.py` 旧采样逻辑「先 `sleep(1.0)` 再看 `proc.poll()`」，而那次子进程 `wall_s=1.001` 就退了 ⇒ **采样窗为空**，
  「没采到」被读成「没有 fd / 整机没占用」。**已根因修**（采样覆盖子进程整个生命期 + `gpu_sampling.*_measured_not_assumed` 把两种空分开 + 新增 `invalid_measurement`/exit 2 档）。
- **变异体双向证明**：`runs/infra/e_egl_coldstart_<date>/gate_mutation/GATE_MUTATION_SELFTEST_*.json`
  （M1–M5，`verdict_set_crosscheck=GREEN`、`two_sided_proof_present=true`，**全程不触卡**）。
- **完整取证件**：`runs/infra/e_egl_coldstart_<date>/COLDSTART_EVIDENCE*.json` + `PERSIST_MANIFEST*.json`
  （②③④ 三项；①就是本节这条命令）。安装/合规细节见 **§7**，能力实测见 **§6/§7**。

### 0.3 【权威状态】本节 §0 是**权威版**恢复块；checkpoint §19.0 的**临时版已被取代**（裁定 88.4-2 的第二步 · 2026-09-30 03:1x）

- **本节身份**：E（基础设施线）。裁定 88.4-2 把恢复块分成两步：**第一步** = D 已在
  `rl_harness_supervision/d_context_checkpoint_20260929_2130.md` **§19.0** 发布**临时版**（授权理由：不允许"等 E 修完"造成恢复指引缺位）；
  **第二步** = E 修完后在**本文最顶**写权威版、并**点名临时版已被取代**。⇒ **第二步现在完成，§19.0 的临时版自本行起不再是权威恢复指引。**
- **§19.0-3 那条临时判据（"以实测 `GL_RENDERER` 含 `NVIDIA` 为权威，不以 `exit code` 为权威"）**已**按其自身条款退役**：
  它写的可推翻条件是「E 修好竞态后重跑 `baseline`，**若仍 `exit != 0` ⇒ 本临时口径作废**，回到 exit code 为权威，并按真缺陷处理」。
  **实测结果走的是另一支**：采样窗竞态已**根因修**，重跑的 `baseline` 臂（真前缀）**`exit_code = 0`**、`renderer_class = nvidia_gpu`、
  **8 条判据全过、`selfcheck_criteria_failed = []`**，其中曾假红的三条占用旁证腿全部转绿：
  **L5 `util_max=76%` / `mem_max=142 MiB`**、**L5b `child_nvidia_fds=["/dev/nvidia2","/dev/nvidiactl"]`**、**S2**（D §8.3-1 指定判据）。
  ⇒ **`exit code` 恢复为权威判据**（与 D 的裁定 89.5-1 / §89.8「§19.0-3 的临时权威判据退役」一致）。
- **当前权威证据件（重启后请对照它判读，不要对照 v1/v2）**：
  `runs/infra/e_egl_coldstart_20260930/COLDSTART_EVIDENCE_v3.json`（`generated_at 2026-09-30 03:02:33`）
  + `PERSIST_MANIFEST_v3.json`。**v1（01:56）/ v2（02:18）原字节保留不动、仅作历史**：
  v1 的 `fs_of()` 未区分「镜像只读层」与「运行期可写层」；**v2 的 `baseline` 臂是假红**（竞态所致，非 GPU 不可用）。
  顶层字段：`delivery_status="COLDSTART_VERIFIED"`、`all_teeth_proven=true`、`stages_skipped=[]`、`c4_gl_renderer_measured=true`、`failed_teeth=[]`。
- **判读顺序（权威版，`exit code` 为准 + 一条防自相矛盾的硬规则）**：
  | 冷启动命令 exit | 含义 | 处置 |
  | --- | --- | --- |
  | **0** | GPU 渲染可用（C4 已实测 `GL_RENDERER` 含 `NVIDIA`） | 可以采集标 `egl` 的数字 |
  | **≠0** | 不可用 | **一个标 `egl` 的数字都不要采**；按 §0 表分 1 / 2 / 3 三种原因处置 |
  | **5** | **`E_SKIP_GPU=1` 的 PARTIAL 档：C1–C3 完好、GPU 未测量** | **不可用**（属 `≠0`）；要判"可用"就去掉 `E_SKIP_GPU` 真跑 C4 |
  | **0 但 C4 的 `gl_strings` 不含 `NVIDIA`** | **自相矛盾 = 判据失效** | **按不可用处置**（不得采集），并把该件登记为缺陷；**不许**因为 exit 0 就放行 |
  > 末行是 E 补的保守规则，理由 = 裁定 88.3-1 的红线 `absence_of_measurement_is_not_measurement_of_absence`：
  > **两个权威信号冲突时，不得挑对自己有利的那个。** `GL_RENDERER` 是 C4 在**独立子进程**里的实测（裁定 82.5），
  > 它不是 exit code 的替代品，而是 exit code 的**校验器**。
- **本节的适用边界（防滥用，与 §19.0-3 的边界同口径）**：上述判读**只针对"冷启动后 GPU 渲染是否可用"这一个问题**。
  它**不**判定任何 policy 能力（裁定 46：`capability_claim=false`）、**不**给渲染保真容差（那是裁定 83.4 的容差 + G4d 的登记带）、
  **也不**推翻红线 `render_bitwise_equality_ban_on_egl`（裁定 85.2-2：egl 上 sha/逐位相等**不能**当渲染保真闸；
  480×640 团队三槽的实测登记带见 `RENDER_DETERMINISM_TEAM480x640_EGL_REPS5_r2.json`，**仅登记、不判红**）。

### 0.4 【权威恢复块 · 2026-09-30 11:5x · T-E-9-3（裁定 92.2 的第三项欠账）】重启之后照这一节走；**机器可读版在 `RESTART_READINESS.json`**

> **同源互引、不写两份口径**（D 执行单 §二-3 的明确要求）：本节的**机器可读权威版**是
> `runs/infra/e_restart_readiness_20260930/RESTART_READINESS.json` 的 **item 3「一条命令恢复路径 + 恢复后的验证点」**
> （1757 ln `4587672f186f`）。本节是它的**人读摘要**；两者冲突时**以 JSON 为准**（它是工具在落笔时刻生成的，
> 身份串人不碰 —— 裁定 92.3(i)）。§0.3 的**退出码判读表仍然是权威**，本节不复制它。

**一条命令（与 §0 逐字相同，不另立）**

```bash
env -i /bin/bash /workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/scripts/e_coldstart_gpu_render.sh
```

**恢复后的四个验证点**（逐条都在 `RESTART_READINESS.json` item 3 里有**实测字段**，这里只给判读口径）

| # | 验证点 | 怎么判 | 本轮 E 实测到什么程度 |
|---|---|---|---|
| V1 | **退出码语义** | `0` = 可用（唯一）；`1` = 不可用（stderr 分 1/2/3）；`5` = PARTIAL（**没测 GPU**）⇒ 见 §0.3 的表 | **实测**：`env -i` + `E_SKIP_GPU=1` 的沙箱臂 exit **5**、C1/C2「**已重建**」/C3/「跳过 C4」四个旗标全真 |
| V2 | `renderer_class = nvidia_gpu` | C4 在**独立子进程**里实测 `GL_RENDERER` 含 `NVIDIA`（裁定 82.5） | **本轮 `not_measured`**（禁上卡）。历史实测 = v3 的 03:02:38（`NVIDIA A800-SXM4-80GB/PCIe/SSE2`），且被测对象自那次以来**逐位未变** |
| V3 | **C4 本身通过** | 同 V2；`exit 0` 但 `gl_strings` 不含 `NVIDIA` ⇒ **自相矛盾 = 判据失效**，按不可用处置（§0.3 末行） | 同 V2；**搭 A2 的 S4b 便车复验**（T-E-10，`verification_kind="third_party_piggyback"`，不单开窗口） |
| V4 | **不许写系统**（含 `ldconfig`） | `egl_vendor.d` 只有 `50_mesa.json`；`ldconfig -p` 四类 GL 库命中 **0**；`/usr/lib/x86_64-linux-gnu` 里四类渲染库 **0** 个 | **实测**（本轮当场扫）：三项全 0/只有 mesa ⇒ `boundary_clean_no_system_write = true` |

**自 §0.3 以来变了两件事（都要知道，否则会读到对不上的身份串）**

1. **持久化清单换权威件了**：`PERSIST_MANIFEST_v3.json`（771 ln `877546896375`）→ **`PERSIST_MANIFEST_v4.json`（1150 ln `4011ae621f61`）**。
   改的是裁定 92.2 批的三项 CPU 修：① 前缀里唯一那条悬空绝对链接已相对化（`libnvidia-vksc-core.so.1`）；
   ② `install_one()` 加了绝对链接相对化（`scripts/e_install_nvidia_gl_590.sh:121`）；③ 清单 schema 加了
   **`link_target_exists` / `dangling` 两个实测字段**（判据是 `Path.exists()` 的真实 stat，**不是**字符串形状）。
   **v3 原字节保留、未覆写**；v4 里带 `supersedes` / `superseded_by=null` / `coldstart_evidence_authority_still`。
   **前缀内容一个字节没变**：23 个真文件的 sha256 与字节数逐条一致、`total_bytes` 仍是 **339,337,693 B**
   （对账件 `runs/infra/e_restart_readiness_20260930/V3_TO_V4_DELTA.json`，66 ln `c8e2b1cc0878`，`verdict=PASS`）。
   ⇒ **v3 的 34 条 sha 记录没有一条过期。**
2. **冷启动权威件没换，但多了两个机器可读标注**：`COLDSTART_EVIDENCE_v3.json`（578 ln `56b81f389712`）**仍是唯一权威**
   （裁定 92.1：不需要 v4；用户已按 D 推荐追认，见 §94.7-1 的 ⑧）。旁边新增**旁证件**
   `COLDSTART_EVIDENCE_v3.ANNOTATIONS.json`（447 ln `9a48b11db93e`），落裁定 92.1(a)(b)：
   - **(a)** v3 里的 `tooth_relink.exit_code = 0` 是**修法前的历史值**，**当前期望值是 `5`**
     （`scripts/e_coldstart_gpu_render.sh:106`）。⇒ **将来谁"复现 v3"都会得到 5，那不是复现失败。**
   - **(b)** `reproduction_caliber_gap` 按**三个 scope 分开**登记，不选一个也不平均：
     **A** = v3 的 `tooth_relink.exit_code` 这一维不可由当前脚本逐位复现（其余各维不受影响，逐臂已核）；
     **B** = 480×640 团队三槽 `{top,left_wrist,right_wrist}` 全不逐位，`max_abs_diff=1`、`frac_diff_px` 最差 **0.000225（0.0225%）**；
     **C** = 224² 采集臂 `{angle,left_wrist,right_wrist}`，`frac_diff_px` 最差 **0.000518（0.052%）**。
     ⚠ **B 与 C 是两轮不同口径**（分辨率与相机集都不同），**`0.052%` 属于 C、不属于 B**；
     把 C 的值安到 B 的相机名上 = 裁定 71 `caliber_transplant_ban`。对照后端 osmesa 三相机**全逐位**（`max_abs_diff=0`）。

**本节不做什么**：不判 policy 能力（裁定 46 禁令不变）· 不给渲染保真容差（那是裁定 83.4 + G4d 的登记带，倍数由 D 定）·
不推翻红线 `render_bitwise_equality_ban_on_egl`（裁定 85.2-2）· 不改 `NVIDIA_DRIVER_CAPABILITIES`（裁定 94.7-1 的 ⑤：**本机维持 `compute,utility`**，
向平台申请加 `graphics` 已降为 P2 文本件 = `docs/e_platform_request_graphics_capability.md`，**其中已按裁定 77.4 删掉 `/dev/dri` 那一条**）。

## 1. 结论速览

> **本节结论已被 §7（2026-09-29）推翻：prefix-only 路径下 GPU 渲染可用。**（裁定 77.8 授权的指针行；
> 下表原始结论行按裁定 55 **一字未改**，更正与证据见 §7）

| 项目 | 实测结果 |
| --- | --- |
| 系统 | Ubuntu 22.04.4 容器 / 宿主内核 4.19.90 BCLinux / 112 core / ~2 TB RAM |
| **CPU 配额** | **cgroup 只有 12 核**（`cpu.cfs_quota_us=1200000` / `period=100000`，已实测被限流 `nr_throttled=746`）；`nproc`=112 是宿主可见数，**不是能用的量** ⇒ 并行度分母按 12 算，见 §6.3 |
| GPU | NVIDIA A800-SXM4-80GB，驱动 590.48.01，`torch.cuda.is_available()=True` |
| CUDA 计算 | ✅ 正常（训练、推理都没问题） |
| NVIDIA GPU 渲染（EGL/GLX/Vulkan/OptiX） | ❌ 不可用，容器内无法自行修复 |
| CPU 软渲染（llvmpipe） | ✅ 可用，256×256 RGB 约 55–70 fps |
| `MUJOCO_GL=egl` | ⚠️ 能跑，但底层是 Mesa llvmpipe（软件），**不是 GPU** |
| `MUJOCO_GL=osmesa` | ✅ 能跑，同样 llvmpipe，性能与 egl 相同 |
| `MUJOCO_GL=glfw` | ❌ 失败（无 X / 无 DISPLAY） |

## 2. 证据

### 2.1 驱动只注入了 compute/utility

```
NVIDIA_DRIVER_CAPABILITIES=compute,utility      # 缺 graphics
NVIDIA_VISIBLE_DEVICES=GPU-c2039775-...
LD_LIBRARY_PATH=/usr/local/nvidia/lib:/usr/local/nvidia/lib64   # 这两个目录是空的
```

nvidia-container-runtime 只会按 `NVIDIA_DRIVER_CAPABILITIES` 注入对应用户态库。
没有 `graphics`，OpenGL/EGL/Vulkan 那一套就不会被挂进容器。

### 2.2 缺失的库与设备节点

`/usr/lib/x86_64-linux-gnu/` 里只有计算相关的 NVIDIA 库
（`libnvidia-ml`、`libnvidia-allocator`、`libnvidia-cfg`、`libnvidia-nvvm`、
`libnvidia-opencl`、`libnvidia-ptxjitcompiler`），渲染相关的全部缺失：

```
✗ libEGL_nvidia.so.0     ✗ libGLX_nvidia.so.0     ✗ libnvidia-glcore.so
✗ libnvidia-eglcore.so   ✗ libnvidia-glsi.so      ✗ libnvoptix.so
✗ /dev/dri               （没有 renderD128 / card0）
✗ /usr/share/vulkan/icd.d/*.json                  ✗ Xvfb / Xorg
```

EGL vendor ICD 只有 Mesa 一个：`/usr/share/glvnd/egl_vendor.d/50_mesa.json` → `libEGL_mesa.so.0`。
另外 `libEGL.so.1` 里连 `eglQueryDevicesEXT` 符号都没有（没有任何 vendor 提供设备枚举）。

### 2.3 关键反直觉点：`MUJOCO_GL=egl` 静默退化成 CPU 渲染

直接问 GL 上下文"你是谁"，两种后端答案完全一样：

```
MUJOCO_GL=egl     → GL_VENDOR=Mesa  GL_RENDERER=llvmpipe (LLVM 15.0.7, 256 bits)  GL 4.5 Mesa 23.2.1
MUJOCO_GL=osmesa  → GL_VENDOR=Mesa  GL_RENDERER=llvmpipe (LLVM 15.0.7, 256 bits)  GL 4.5 Mesa 23.2.1
```

渲染进行中采样 GPU：`nvidia-smi` → `utilization.gpu = 0 %`，`memory.used = 0 MiB`，无图形进程。

原因是 mujoco 的 EGL 后端通过 glvnd 找 vendor，本机只有 Mesa ICD，
Mesa 的 `EGL_MESA_platform_surfaceless` 不需要 `/dev/dri` 就能建上下文，
于是走 llvmpipe 软渲染 —— **能出图，但 GPU 全程没参与，而且不会给你任何警告**。

所以：`README.md` 里"默认 `MUJOCO_GL=egl`（GPU）"这句在本节点不成立，
egl 和 osmesa 在这里是同一件事，选哪个只影响报错方式，不影响性能。

### 2.4 帧率基准（RGB 离屏渲染，llvmpipe）

测量时 `load average ≈ 441`（机器被别人的任务占满），所以这是**保守下界**；
空载时会更快。数字有 ±20% 抖动属正常。

| 分辨率 | RGB fps | 深度 fps |
| --- | --- | --- |
| 64×64 | ~65 | ~1250 |
| 256×256 | **55–70** | ~300–550 |
| 512×512 | ~70–90 | ~240–340 |

注意两点：
- 分辨率从 64 降到 256 帧率几乎没变 → **每帧固定开销（约 15 ms）占主导**，
  想靠"把图缩小"来提速基本无效，得靠减少渲染次数或并行多进程。
- 深度渲染比 RGB 便宜一个数量级（RGB 要算阴影/反射/多重采样）。

**由此得出的可行边界：**
- ✅ 录 mp4、离线可视化、随机策略冒烟：完全够用（一段 200 帧视频几秒渲染完）。
- ✅ 状态观测（关节角/位姿）的 RL：**根本不需要渲染**，物理本身是 CPU 的，A800 只跑策略网络。
- ⚠️ 像素观测的 RL：单进程约 60 fps，SAC 要 10⁵–10⁶ 帧就很痛；只能靠多进程并行压时间（**并行度上限 12 路，不是 16–32**：容器 cgroup 配额 12 核，实测 8 路内近线性、12 路撞顶、16 路效率掉到 70%，见 §6.3）。
- ❌ Isaac Sim / SAPIEN 那种"GPU 上并行几千个环境 + GPU 渲染"的吞吐：本机不可能达到。

## 3. 对下游框架的可行性判定

| 框架 / 后端 | 渲染需求 | 本机能否跑 | 说明 |
| --- | --- | --- | --- |
| 手写 Reach（`envs/reach_env.py`） | 无 | ✅ | 纯 numpy，与渲染无关 |
| MuJoCo + robosuite / LIBERO | MuJoCo 离屏 GL | ✅（CPU 软渲染） | `MUJOCO_GL=osmesa` 或 `egl` 等价，慢但能跑 |
| RoboRSI（LIBERO 后端） | MuJoCo EGL，默认 256px + depth | ⚠️ 能跑但慢 | 见 `docs/roborsi-callchain.md`；官方脚本要求"NVIDIA/CUDA stack for the LIBERO renderer" |
| RoboRSI（RoboTwin 后端） | SAPIEN + Vulkan + cuRobo | ❌ | 需要 `libvulkan1`、`mesa-vulkan-drivers`、`libnvidia-gl-<ver>` |
| ManiSkill3（**state 档**） | SAPIEN 渲染设备（可占位） + PhysX GPU(CUDA) | ✅ **有条件** | `render_mode="state"` + `render_backend="cpu"` + lavapipe + Xvfb，**实测 1024 envs 并行 21k steps/s**，见 §6.1 |
| ManiSkill3（**像素档**） | SAPIEN + NVIDIA Vulkan | ❌ | 需要 §4 的平台改造；ROADMAP 里"并行采样优先 ManiSkill3"只在 state 档成立 |
| Genie Sim / Isaac Sim 5.1 | RTX + OptiX + Vulkan + docker | ❌ | 本机还没有 docker / nvidia-container-toolkit |
| PyTorch3D / gsplat 等纯 CUDA 渲染 | CUDA | ✅ | 不依赖 GL |
| nvdiffrast（GL 后端） | EGL + NVIDIA GL | ❌ | CUDA 后端部分算子可用，光栅化不行 |

## 4. 要开 GPU 渲染，需要平台改容器配置

`python scripts/check_gpu_render.py` 会直接打印可复制的申请文本，要点：

1. Pod/容器环境变量 `NVIDIA_DRIVER_CAPABILITIES` 改为 `all,compute,utility,graphics`（至少加 `graphics`；跑 SAPIEN/Isaac 还要 `display`/vulkan）。
2. 挂载 `/dev/dri`（宿主需加载 `nvidia-drm`，出现 `renderD128`）。
3. 需要图形界面调试再加 Xvfb / X11 转发。

**容器内自己装 `libnvidia-gl-*` 解决不了**：一是版本必须与宿主驱动 590.48.01 严格一致，
二是没有 `/dev/dri` 时 EGL 设备枚举拿不到任何设备。

重启后的验收命令：

```bash
ls /usr/lib/x86_64-linux-gnu/libEGL_nvidia.so.0 && ls /dev/dri
python scripts/check_gpu_render.py --bench      # GL_RENDERER 应变成 NVIDIA，且 egl 帧率远高于 osmesa
nvidia-smi                                       # 渲染时 utilization.gpu 应该 > 0
```

## 5. 三个已经踩过的坑（省得再踩）

1. **MuJoCo 默认离屏 framebuffer 只有 480×480**。直接 `Renderer(model, 512, 512)` 会报
   `ValueError: Image height 512 > framebuffer height 480`。自己写 XML 时必须加
   `<visual><global offwidth="1024" offheight="1024"/></visual>`；robosuite/LIBERO 会自己设，
   但裸用 mujoco 时容易忘。
2. **`enable_depth_rendering()` 之后 `render()` 返回的是深度图**。做基准计时时必须
   "先测 RGB、再开深度测深度"，顺序反了会得到差一个数量级的假数字（本脚本第一版就错了，
   256px 一度被测成 282 fps，实际约 60 fps）。
3. **`MUJOCO_EGL_DEVICE_ID=0` 在本机不会报错**（mujoco 3.13 的 egl 后端不做 EGL 设备枚举，
   直接走 Mesa surfaceless），所以不必担心这个变量导致启动失败；但退出时可能看到
   `EGLError` 的 GC 噪声，调 `renderer.close()` 就没有了。

## 6. 2026-09-29 补测：ManiSkill3 state 档 + CPU 配额（两处推翻本文早先判断）

> 复现：`runs/infra/maniskill_state_probe_20260929/`（README + `setup_maniskill_state_env.sh` + `run_all.sh`）、
> `runs/infra/robosuite_throughput_probe_20260929/`。所有数字都是当批实测，原始 JSON 与日志在同目录。

### 6.1 §3 里 ManiSkill3 的 ❌ 是"结论歪打正着、理由是错的"

原判定说 ManiSkill3 需要 SAPIEN + Vulkan 所以跑不了。实测三条路径：

| 组合 | 结果 |
| --- | --- |
| `render_mode="state"` + `render_backend="gpu"`（默认） | ❌ `vk::createInstanceUnique: ErrorIncompatibleDriver`（SAPIEN `_vulkan_tricks.py:78` 自动塞自带 `nvidia_icd.json`，指向不存在的 `libGLX_nvidia.so.0`） |
| `render_mode="state"` + `render_backend="none"` | ❌ `RuntimeError: failed to find a rendering device` |
| `render_mode="state"` + `render_backend="cpu"` + lavapipe + Xvfb | ✅ **跑通** |

关键机制：`mani_skill/render/utils.py::can_render()` 的实现只有 `return device is not None`
（注释自己承认 sapien 的探测不准），而任务侧建 actor 时**无条件**要渲染材质
（`utils/building/actors/common.py:87` 的 `sapien.render.RenderMaterial(...)`）。
⇒ **ManiSkill 官方文档"state-based simulation does not require any additional dependencies"这句话在它自己的实现上不成立**，
不是本机特殊。`render_backend="none"` 这个看起来是官方出口的参数也堵死在这一步。

能跑通的组合需要三件容器层的东西（缺一即失败，失败原文见上表）：

```bash
apt-get install -y --no-install-recommends libvulkan1 mesa-vulkan-drivers xvfb
export VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.x86_64.json   # 否则被 SAPIEN 覆写成 nvidia_icd.json
xvfb-run -a python ...                                                 # 否则 lavapipe Present:0，SAPIEN 拒收该设备
# gym.make(..., render_mode="state", render_backend="cpu")
```

物理走 **PhysX GPU（CUDA）**，与 Vulkan 无关；那个 CPU 渲染设备只是**从不真正出图的占位**。
⇒ **像素档仍然 ❌**，§4 的平台申请照旧成立、优先级不变。
另外 PhysX GPU 库 226 MB 首次会从 GitHub 下到 `/root/.sapien/`（临时层），已镜像到
`.codex-persist/sapien-cache/`，`setup_maniskill_state_env.sh` 会回链。

### 6.2 实测吞吐：GPU 并行 state 采样比多进程 robosuite 高一个数量级

PickCube-v1，`render_mode="state"`，`render_backend="cpu"`（`num_envs=1` 时 ManiSkill 默认 `physx_cpu`，`>1` 才是 `physx_cuda`；
且 **GPU PhysX 一个进程只能启用一次**，每档必须独立进程）：

| num_envs | 建环境 | ms/step | 总吞吐 steps/s | CUDA 显存 |
| --- | --- | --- | --- | --- |
| 1（physx_cpu） | 0.32 s | 2.20 | 454 | 0.0 MiB |
| 16 | 1.02 s | 22.14 | 723 | 8.2 MiB |
| 64 | 1.15 s | 27.94 | 2,291 | 8.3 MiB |
| 256 | 1.55 s | 33.62 | 7,616 | 8.5 MiB |
| **1024** | 3.12 s | 48.14 | **21,270** | 9.6 MiB |

对照：**robosuite 1.5.2 Lift state-only 多进程最好 1,156 steps/s**（16 进程，见 §6.3）。
⇒ **18.4×**（@1024 envs）/ **6.6×**（@256 envs）。

**⚠️ 上表的 21,270 不是常数**：同配置（PickCube-v1, num_envs=1024）第二批实测 **41,322 steps/s**，
**差 1.94 倍**，唯一可见差别是宿主 `loadavg` 36 → 16.7。
⇒ 与 `docs/notes_stage3.md:1206` 第 25 条（同一任务 25.5 s/局 vs 2.4 s/局）是**同一个坑**：
**本节点任何吞吐/成本数字都必须同时记 `loadavg` 与 `cpu.stat` 的 `nr_throttled`，单点数字不得当常数引用。**

三条可直接用的读数：
1. `ms/step` 从 22→48 ms 只涨 2.2 倍而 env 数涨 256 倍 ⇒ **固定开销主导，总吞吐近线性**，还没到拐点。
2. **显存 ≤10 MiB**，A800 80GB 完全不是约束；瓶颈在别处（见 §6.3 的 CPU 配额）。
3. **GPU 并行采样基本不吃 CPU 配额**，所以它绕开的正是 §6.3 那个硬约束——这才是它值得接的理由，
   不只是"快 18 倍"。

判据侧附带一个高价值发现：`info` 直接吐 `is_grasped / is_obj_placed / is_robot_static / success`
（全是 GPU 上的批量 bool），且 `is_grasped` 是**真接触判据**（`agents/robots/panda/panda.py:237`：
双指 pairwise 接触力各 ≥0.5 N 且力方向与张开方向夹角 ≤85°），不是 attach 魔法。
但 `pick_cube.py:155` 的 `"success": is_obj_placed & is_robot_static` **不含 `is_grasped`**
⇒ 与 `docs/notes_stage3.md` 第 24 条在 robosuite Lift 上抓到的 `success_flick` **同一类缺陷**；
差别是这里 `success & is_grasped` 一行就能得到 `grasp_verified`，不必事后审计重建。
"成功判据是任务设计的一部分，不是环境的既成事实"这条结论**不变**。

确定性：同 seed 两次 30 步（num_envs=64），obs 的 sha256 **逐字节相同**。
（只覆盖同进程内同 seed 重跑；跨断点复现仍按 A 线 env manifest + 断点登记口径，本探针不声称。）

### 6.3 容器 CPU 配额是 **12 核**，`nproc`=112 是假的可用量

```
/sys/fs/cgroup/cpu/cpu.cfs_quota_us  = 1200000
/sys/fs/cgroup/cpu/cpu.cfs_period_us =  100000        ⇒ 12.0 核
/sys/fs/cgroup/cpuset/cpuset.cpus    = 0-111          （不绑核，但配额卡死）
/sys/fs/cgroup/memory/memory.limit_in_bytes = 241591910400  ⇒ 225 GiB
nproc / os.cpu_count() / sched_getaffinity = 112      （宿主可见数）
cpu.stat: nr_throttled=746, throttled_time≈2950 s     （已经被限流过了）
```

robosuite Lift state-only 实测扩展曲线（`has_offscreen_renderer=False`，完全不碰 GL；1500 步/worker，OMP=1）：

| nproc | 聚合 steps/s | 效率 | 100k 步 |
| --- | --- | --- | --- |
| 1 | 103.7 | 100% | 964 s |
| 4 | 441.1 | 106% | 227 s |
| 8 | 843.3 | 102% | 119 s |
| **12** | **1,093.7** | **88%** ← 拐点=配额 | 91 s |
| 16 | 1,155.7 | 70% | 87 s |

⇒ §2.4 那句"112 core 可以开 16–32 路"**不成立**（已就地改正），实测 **12 路即到顶，性价比拐点在 8–12 路**。
这与 `docs/notes_stage3.md:1207` 的"`os.getloadavg()` 读到的是宿主机口径"是**同一类错误**：
容器里看得见的资源数字（`loadavg`、`nproc`）都不等于自己能拿到的量。
**规则：任何并行度/成本估算，分母用 cgroup 配额（读 `cpu.cfs_quota_us / cfs_period_us`），不用 `nproc`。**

### 6.5 任务矩阵与资产下载（2026-09-29 续测）

- **零资产任务共 70 个**（`DATA_GROUPS` 为空即可跑），实测 **11/12 通过**，256 envs 下 **6.2k–13.6k steps/s**、
  1024 envs 下 **23k–43k steps/s**，显存 ≤13 MiB。唯一失败是本探针不支持多机器人的 Dict `action_space`，不是环境问题。
- 判据是**分解式**的（GPU 上的批量 bool），例如 `SO100GraspCube-v1` 直接吐
  `reached_object / is_grasped / cube_lifted / touching_table / distance_to_rest_qpos / success`，
  且其 `success = cube_lifted & is_grasped & reached_rest_qpos`
  （`mani_skill/envs/tasks/digital_twins/so100_arm/grasp_cube.py:414`）——
  **对照** `PickCube-v1` 的 `success = is_obj_placed & is_robot_static` **不含 `is_grasped`**，仍可被 flick 拿到。
  ⇒ **选任务时必须逐个核 `evaluate()`，不能假定 `success` 含抓取真值。**
- **资产下载是本机接 ManiSkill 生态的真瓶颈**（三条实测坑，细节与工具见
  `runs/infra/maniskill_state_probe_20260929/README.md` §12）：
  1. `url=` 型数据源用 `urllib` 拉**硬编码的 `huggingface.co`**、**不看 `HF_ENDPOINT`** ⇒ 代理 503；
     只有 `hf_repo_id=` 型走 `snapshot_download` 才用镜像。**`docs/ROADMAP.md:131` 那条"HF 资源走 hf-mirror"要补此限定。**
  2. `snapshot_download` 被 **429** 时会打印 `Returning existing local_dir ...` 然后**正常返回、exit 0**
     ⇒ 实测把 **719/895 文件、569 MB/1.67 GB** 的半成品当成了下载完成（`scenes/`、`stage_*`、`object_urdf/` 整个缺失）。
     **规则：资产下载完必须自己数文件对远端清单，不能信返回码。**
  3. 并发度是夹逼：8 worker ⇒ **429**；单流 curl 只有 **~28 KB/s**（同域名 range 请求同一时刻却有 2.5 MB/s
     ⇒ 是**单连接被限速**）；实操用 **2–3 worker + 重试**。
- `MS_ASSET_DIR` 默认 `~/.maniskill`（**临时层，重建即丢**）⇒ 必须指到 NFS（本轮用 `.codex-persist/maniskill-assets`）。
- **坑 4（本轮新踩）**：下载器**不能并发跑两个实例**——`curl -C -` 会对同一文件重复追加，
  实测把 3 个 `.glb` 撑大（`got>want`），只有按 size 校验才看得见。`hf_mirror_fetch.py` 已加 `flock` 单实例锁。
- 现状：`ReplicaCAD` 已 **872/872 完整**（0 缺失、0 尺寸不符）；`ycb` 与 `ReplicaCADRearrange` **未下**。

### 6.4 边界（不得外推的部分）

- 只测了 **PickCube-v1**（纯 primitive，无外部资产）。带 YCB/URDF 资产的任务要走下载，
  `HF_ENDPOINT=https://hf-mirror.com` 是否够用**未测**；更重的接触任务吞吐**未测**，21k steps/s 是轻任务上界。
- 测的是 **steps/s（纯 env stepping、随机动作）**，不是 `notes_stage3.md:2263` 那张成本表的 **s/局**
  （含策略推理与 reset）。⇒ **不得**拿 21k 直接代进 F1~F4 重算成本；那张表的最终结论
  （F2 = 6 臂 2.9 h，买得起）本探针**既不推翻也不需要推翻**，它改变的是同样预算下**买得起的局数/分辨率**。
- **§6.2 的 21k–43k steps/s 只适用于轻桌面任务**。整套公寓场景（`ReplicaCAD_SceneManipulation-v1`）
  实测 **697 steps/s @64 envs**、`ms/step` 随 num_envs 上涨（59.6@16 → 91.8@64，**次线性**），
  比 `SO100GraspCube-v1` 低 1–2 个数量级 ⇒ **不得把轻任务吞吐外推到家居/重排场景**。
- **HAB 这条线只复用到一半**：`ReplicaCAD_SceneManipulation-v1` 的 `info` **只有 `elapsed_steps`，没有任何成功判据**
  （它是 `mani_skill/envs/scenes/base_env.py:19` 的通用 `SceneManipulationEnv` = 可交互场景，不是任务）。
  HAB 的任务层（子任务序列 / realistic grasping / 失败模式）在 **MS-HAB** 里，不在 mani_skill 3.0.1 里。
- **ManiSkill-HAB**（ICLR 2025, arXiv:2412.13211）**未安装未测**：`haosulab|mani-skill/ManiSkill-HAB` 全 **404**，
  公开只有匿名投稿镜像 `anonsubmit0/maniskill-hab`，装法是 **py3.9 + ManiSkill fork + `git lfs` + `coacd` +
  `fast_kinematics==0.1.11`**（本机 `nvcc 12.4` 在、`git-lfs` 不在）⇒ 与 §6.1 已验通的栈**不是同一套**，
  三个前置条件要在 fork 上重验。还差 `ReplicaCADRearrange` 1.49 GB（`url=` 型 + 单流 ~27 KB/s ⇒ **~15 h**）。
  **⇒ 已由 `rl_harness_supervision/d_freeze_abc_20260929.md` 裁定 38.6 终结：不开 MS-HAB 线、
  `ReplicaCADRearrange` 下载停（实际从未落盘）、`ReplicaCAD_SceneManipulation-v1` 不再作为候选任务。**
  替代口径：`SO100GraspCube-v1` 已用**零资产 + 43k steps/s**给到"真实接触失败结构 + grasp 真值判据"。
- 接线是**新增适配层**的活：ManiSkill 是 gym 向量化语义（一个 env 内含 num_envs 个子场景，
  obs 是 `tensor(n,42)@cuda:0`、action `Box(-1,1,(n,8))`），与本仓 `harness/env_factory.py` 现在的
  单环境口径不同，不是改配置能接上的。

## 7. 2026-09-29 22:0x E 线补测：**GPU 渲染已在本容器内解锁**（本文 §1/§3/§4/§5-3 四处结论被实测推翻）

> **本节只追加、不覆写原文**：原文作者 = 环境调研线（`git log --follow docs/infra-gpu-render.md` → `f19470f`，
> 提交信息「环境调研线快照（无智能体前缀）」），§6 是 D/C 线的 09-29 补测。**上文表格里的 ❌ 与「容器内无法自行修复」
> 一律原样保留**，读者以本节为准；**是否回填正文由 D 裁定并点名移交原作者线**（E 不动别人的结论行，裁定 55 上报纪律）。
>
> **复现（三条命令，全部 prefix-only、零系统写入）**：
> ```bash
> bash scripts/e_activate_gpu_render.sh --selfcheck          # 三臂自证：GPU 臂 + 两个变异臂
> python scripts/e_egl_probe.py --stage all                   # 六条绿判据 + M1/M2 变异体 + 边界闸
> python scripts/e_mainline_render_calib.py --backends egl_nvidia,osmesa --workers 1,2,4,8 --steps 30 --reps 2
> ```
> **原始产物**：`runs/infra/e_egl_probe_20260929/`（E1+E2，15 文件 + `MANIFEST.json`）、
> `runs/infra/e_gpu_egl_verify_20260929/`（15 文件，含 `post_rollback.json`）、
> `runs/infra/e_activate_selfcheck_20260929/`、`runs/infra/e_mainline_calib_20260929/`。

### 7.1 四处被推翻的结论（逐条：原断言 → 实测 → 证据路径）

| # | 原位置与原断言 | 09-29 22:0x 实测 | 证据路径 |
|---|---|---|---|
| ① | §1「NVIDIA GPU 渲染（EGL/GLX/Vulkan/OptiX）**❌ 不可用，容器内无法自行修复**」 | **可解锁，且不需要平台改容器**：把与驱动 **590.48.01 逐字同版本**的渲染侧库放进 NFS 前缀目录，只用 `LD_LIBRARY_PATH` + `__EGL_VENDOR_LIBRARY_FILENAMES` 两个环境变量注入 ⇒ `GL_RENDERER = "NVIDIA Corporation \| NVIDIA A800-SXM4-80GB/PCIe/SSE2 \| 4.6.0 NVIDIA 590.48.01"`，64² 裸渲染 **2258 fps**（同机 llvmpipe **79–104 fps**） | `runs/infra/e_activate_selfcheck_20260929/selfcheck_egl_nvidia_20260929_215406.json`；`runs/infra/e_egl_probe_20260929/green_dirs_20260929_213429.json` |
| ② | §4「**没有 `/dev/dri` 时 EGL 设备枚举拿不到任何设备**」（以及 §4 的验收命令把 `ls /dev/dri` 当验收项） | **证伪**：NVIDIA 走 `EGL_EXT_platform_device`，枚举到 **2 个设备**（index 0 = `vendor="NVIDIA"`、`initialize_ok=true`、`egl_error=0x3000`、扩展含 **`EGL_NV_device_cuda`**），且 **`drm_device_file=null`** —— 它压根不需要 `/dev/dri`，靠 `/dev/nvidia2`+`/dev/nvidiactl`（渲染子进程自己持有这两个 fd）。本机**永远不会有** `/dev/dri`（宿主未加载 `nvidia-drm`）⇒ **该验收项对本机恒红，不能用它判"渲染不可用"** | `runs/infra/e_gpu_egl_verify_20260929/post_install_devid0.json` → `egl_device_probe.devices`；`runs/infra/e_activate_selfcheck_20260929/selfcheck_egl_nvidia_20260929_215406.json` → `child_nvidia_fds` |
| ③ | §3 表格「**ManiSkill3（像素档）❌**」「RoboRSI/RoboTwin（SAPIEN + Vulkan）❌」 | **像素档 ✅**：sapien 3.0.3 / mani_skill 3.0.1，`PickCube-v1` **64 envs、512²、`source_device="cuda:0"`** ⇒ **25.67 vec-steps/s（≈1643 env-steps/s）**，`gpu_util_max=85%`、显存 **2647 MiB**（`num_envs=4/16` 分别 ≈179/593 env-steps/s）。**Vulkan ✅**：`vkCreateInstance=VK_SUCCESS`、枚举到 **2 个物理设备**（`NVIDIA A800-SXM4-80GB` + llvmpipe）、`driverVersion 590.48.1.0`；负对照（不给 ICD）只剩 llvmpipe。**RoboTwin/cuRobo 整栈仍未装未测**（本条只覆盖 SAPIEN+Vulkan 这一层能力） | `runs/infra/e_gpu_egl_verify_20260929/downstream_gpu_maniskill_ne64.json`、`.../vulkan_post_install.json`、`.../vulkan_neg_lavapipe.json` |
| ④ | §5-3「`MUJOCO_EGL_DEVICE_ID=0` 在本机不会报错（**mujoco 的 egl 后端不做 EGL 设备枚举，直接走 Mesa surfaceless**）」 | **不准确**：mujoco 的 egl 后端**确实做设备枚举**，`MUJOCO_EGL_DEVICE_ID=0` 在注入 NVIDIA vendor 后**选中的就是 index 0 = NVIDIA**（实测 256² **2002.85 fps**、512² **1363.21 fps**，六条判据全过）。原文那句的观察是在**只有 Mesa 一个 vendor** 的旧状态下得到的 —— 那时"枚举不到 NVIDIA"是真的，但原因是**没东西可枚举**，不是"不做枚举"。另一个细节：NVIDIA 对 pbuffer surface 返 **`EGL_BAD_PARAMETER(0x300c)`**，mujoco 走的 **surfaceless** 路径才通 ⇒ surfaceless 与 NVIDIA 兼容，原文的"直接走 Mesa surfaceless"混淆了这两件事。**版本指称无法在本机复核**：原文写「mujoco 3.13」，本机三个 venv 实测为 `rlrobot 3.9.0` / `pi05_sim 3.8.1` / `lerobot_eval 3.9.0`，无 3.13（标 `declared_only`，不作 blocking） | `runs/infra/e_gpu_egl_verify_20260929/post_install_devid0.json`；`runs/infra/e_egl_probe_20260929/precheck_20260929_213429.json` |

### 7.2 合规用法（**prefix-only**，裁定 59.4 / 60）与一条必须知道的红线

```bash
source scripts/e_activate_gpu_render.sh              # MUJOCO_GL=egl + 前缀 LD_LIBRARY_PATH + 前缀 10_nvidia.json
source scripts/e_activate_gpu_render.sh --mode cpu   # 对照/退路臂：osmesa（CPU 软渲染）
bash   scripts/e_activate_gpu_render.sh --selfcheck  # 自证：GL_RENDERER 含 NVIDIA + 子进程持 /dev/nvidia* fd
```

- 库前缀（NFS，**容器重启不丢**）：`.codex-persist/egl-libs/590.48.01/`（324 MB，含 `10_nvidia.json`、`nvidia_icd_vulkan.json`）；
  来源 `.deb` 与 sha256 见 `docs/e_egl_feasibility_20260929.md`。**红线：不写系统目录、不 `ldconfig`、不 apt/dpkg**
  （E 曾在 21:02 违规系统安装，21:18 全量回滚，D 独立复核干净 ⇒ 裁定 60）。
- **`MUJOCO_GL=osmesa` 装了库也永远走 CPU**（负对照实测 66.56 fps、llvmpipe）⇒ **后端必须显式写进五元标注**，
  不能靠"装了库"推断。
- **`scripts/check_gpu_render.py` 的 `gpu_render_possible` 是静态启发式**（要求 `/dev/dri` + `graphics` capability），
  prefix-only 解锁后它**仍返回 False** ⇒ **不要再拿它当"能不能 GPU 渲染"的闸**；该脚本属冻结面，E 未改动，
  是否修订**由 D 裁**（建议：保留它作为"平台侧是否注入 graphics 能力"的探针，另立 prefix 路径的判据 = `--selfcheck`）。
- **根治仍建议平台侧做**：把 `NVIDIA_DRIVER_CAPABILITIES` 加 `graphics`（让容器运行时自己注入这四个库），
  这样各线不必依赖前缀环境变量；**但 prefix-only 已足够主线使用**，平台改造不再是阻塞项。

## 8. 2026-09-30 12:4x【裁定 96.1-③】占卡判定 `card_busy()` 的**网③口径已收紧**：裸关键字 ⇒ 真实执行形态 ∧ 关键字 ∧ 非闲置

> 本节是 `runs/infra/e_card_busy_fix_20260930/CARD_BUSY_FIX_VERDICT.json`（1752 ln `c7457467514f`）的**人读摘要**；
> 冲突时以那份 JSON 为准（它由 `scripts/e_card_busy_probe.py`（870 ln `c828725ad2e0`）在落笔时刻生成，身份串人不碰，裁定 92.3(i)）。
> 被改的那一件 = `scripts/e_mainline_render_calib.py`：1279 ln `fd582e261e87` → **1419 ln `cce2d743ae77`**。

### 8.1 为什么要改（F 实测两起，不是推断）

`card_busy()` 的网③（cmdline 网）两档都在做**字面量匹配**，于是「只在文本里提到 GPU 关键字」的纯 CPU 进程
会被判成占卡。F 的只读探针实测（`runs/vla/f_oversight_20260930/probe_card_busy_20260930_115613.json`）：
宽档命中 PID **214244** = `/bin/bash -c … python3 - <<'PY' … pathlib.Path("scripts/a2_s4b_outcome_ledger_verify.py")`
—— 那是在**改文件**。后果具体：A2 按裁定 94.9-1② 要在**起跑那一刻**实测三网 ⇒ 窗口被判 `contaminated`
（D 明示不认该窗口的数字）或被起跑前拒绝逻辑挡下（`exit 3`）⇒ **白跑一轮上卡**，而裁定 95.2 的六步序列
第 1–3 步全部要上卡。与 B2 自报的 **RR-B2-18** 同族同因（那条归 B2 同批修）。**这是 Ⅰ 类**（它保护的是
延迟/吞吐数字的可靠性）⇒ 裁定 95.1 的冻结令不挡它（95.1-5 已认定过渡协议属 Ⅰ 类而保留）。

### 8.2 新口径（机器可读版在 `card_busy()["cmdline_net_caliber"]`）

| 档 | 旧 | 新（裁定 96.1-③） |
|---|---|---|
| 窄档 `gpu_intent` | cmdline 里出现 11 个关键字之一即计入 | **真实执行形态 ∧ 关键字 ∧ 非闲置** |
| 宽档 `other_line_script` | cmdline 里出现 `scripts/{a,a2,b,b2,c,c2,d}_` 即计入 | 同一个执行形态 / 非闲置门槛（「宽档同理」） |
| 网①`compute-apps` / 网②`/dev/nvidia*` fd | 实测占用 | **一字未改**（ast 逐对象机器比对 **7/7**：`gpu_snapshot`, `other_compute_procs`, `nvidia_fd_holders`, `_cmdline`, `_own_tree`, `GPU_INTENT_PATTERNS`, `OTHER_LINE_SCRIPT_RE`） |

- **真实执行形态** = `EXEC_FORM_RE`（逐字复用 F 的 `scripts/f_probe_card_busy.py`，207 ln `0c0034426d31`；「读别人的工具、写自己的文件」）
  ∨ argv0 本身是 GPU 启动器（`torchrun`/`accelerate`/`deepspeed`/`lerobot-train`）∨ `python -m` 分布式启动器。
- **非闲置** = 累计 `utime+stime` > 1 tick（= 0.01 s @ `SC_CLK_TCK`=100）∨ 状态不属 `S/T/Z`。
  **定标是实测的**：真跑诱饵 26 tick vs 闲置载体 0 tick（裕度 26.0×）；
  取不到 `/proc/<pid>/stat` ⇒ **不**判闲置（宁可过判不可漏判；`D` 态同理不排除 —— 那正是「已起跑、尚未分配显存」的盲区）。
- **不再计入 busy 的仍原样登记**在 `cmdline_hits_text_mention_only`（消费方可审计「为什么这一刻没判忙」）。
- **接口未破**：`card_busy(exclude_pids=None, strict=False)` 的签名与 8 个旧键全在，只**新增** 2 键
  （`cmdline_hits_text_mention_only` / `cmdline_net_caliber`）⇒ A2 的 `a2_egl_latency_remeasure.py`（按路径 import 本模块）
  与 `e_selfcheck_gate_mutation.py`（monkeypatch 它）都不需要改。

### 8.3 证据（六腿 + 两向对照探针，裁定 93.8 / 缺陷类 ⑲）

- **重放腿 R**：12/12 —— 喂的是**真实记录过的 argv**（F 实测的 3 条 + 23:58 抢卡事故的假体形态 + A2 延迟臂 + 裸 `torchrun` + 冷启动入口）。
- **活体腿 L / 差分腿 D**：4/4，两向都在（正腿 True、负腿 True）。
  **差分腿的形**：文本提及腿必须「**旧版判忙 ∧ 新版不判忙**」，真跑腿必须「旧版判忙 ∧ 新版判忙」⇒ 断言不是恒真（把修法退回去这套探针会红）。
- 另有**闲置定标腿**、**接口未破腿**、**现场读数腿**（56 个可见进程、11 条内部自洽判据全过）。
- **对照探针**：注入坏形态 = `grep -rn a2_egl_latency_remeasure --mode closed_loop quiet…` ⇒ `detected=True`、`both_directions=True`。
- **GPU 边界（本节自己也要守）**：全程纯 CPU、不需窗口；诱饵不导入 torch/mujoco/OpenGL、不开 `/dev/nvidia*`
  （由 `decoy_self_report_L1.json` 自证）；探针起止两次**只读** `nvidia-smi`：util **0→0**、
  mem **0→0 MiB**、`compute_procs` **[]**（网① `measurement_status=measured`，
  即「`compute_procs=[]` 是测到的空，不是没测」）；`nr_throttled` 增量 **0**、`loadavg` ['2.69', '4.46', '6.25'] → ['2.77', '4.32', '6.14']。
- **判词**：`PASS`（exit 0）。

### 8.4 四条残留风险（都带消费方与到期时刻，裁定 94.9-5 / 缺陷类 ⑳）——详见 verdict 件的 `residual_risk_register`

1. **RR1 词表会过期（需 D 点头才动）**：窄档词表是手工维护的；六步序列会引入新入口（如 `a2_s3_bc_overfit*`），
   若它不含现有 11 个关键字、又还没加载 CUDA 库，则**预分配显存之前**那段（`from_pretrained` 实测 60–185 s）网③会漏判。
   消费方 = A2 起跑时的 `GPU_WINDOW.json` + E 一行补词表；到期 = 六步第 1 步第一次上卡。**E 不自决扩范围**（裁定 96.1-③「不扩范围」）。
2. **RR2 `bash -c` 里的纯文本会被过判**（安全侧：宁可让路）；消费方 = F 的每轮只读探针（已能分开这两类）。
3. **RR3 闲置排除的裕度**（阈值 1 tick，实测真跑 26 tick）；消费方 = 本探针 L1 + A2 起跑时复测。
4. **RR4 B2 的同口径副本会漂移**（`scripts/b2_s1_generate_dataset.py` 的 `card_busy_three_net`）；消费方 = B2（RR-B2-18 同批修）+ D 里程碑审查。
   **若 A2 的起跑前拒绝逻辑走的是 B2 的副本，则本次修法对 A2 还不生效** ⇒ 这条是 8.3 那套证据的**作用域边界**，不是可省略的脚注。
