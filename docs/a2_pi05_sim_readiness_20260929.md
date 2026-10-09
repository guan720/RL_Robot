# A2 → D / B2：π₀.₅ + 仿真贯通的 **P0 就绪报告**（2026-09-29）

- **作者/写入面**：智能体 **A2**（VLA 底模与仿真贯通线）。本文件只由 A2 写；产物一律落 `runs/vla/a2_*`。
- **依据**：`rl_harness_supervision/d_handoff_to_a2_20260929.md`（§0–§11，**§10/§11 为最新改判**）；
  上位方案 `RL_Harness_v4_20260924/materials/06_三轮递进调研与方案复审_20260923/01_开发技术方案.md`（只读）。
- **边界**：本轮**没有接触任何硬件**，**没有采示范数据、没有训 BC**，**没有改** `harness/`、`registry/`、`configs/`、任何 lock、
  `work/project_parameters.json`（D 单写者）、A/B/C/D 与 B2 的产物目录。原始 ckpt 目录**只读未改一字**。
- **一句话结论**：**π₀.₅ 在本机可加载、可前向、可在形态一致的仿真（gym-aloha 双臂 14 维 + 3 相机）里闭环跑完 20 局**；
  动作/时间契约的**六问已实测到"能填的都填实、不能填的标 unknown"**的程度；
  **G3 已跑完 20 局零 SFT + 20 局随机对照 + 20 局「起手位姿保持」零假设**（三批同 seed）：
  两列 success 判据在两臂上**都是 0/20（无 normalizer stats、state 通道饱和 ⇒ 判据不恒真，但 `0/20` 不构成 π₀.₅ 能力证据）**，
  而零假设对照证明 **π₀.₅ 左臂有跨 seed 一致的净接近（中位 +0.104 m，19/20 seed 为正）⇒ 不是接线死了**；
  **结论行照 D §12.11-2 写死：本次 zero-shot 不构成 π₀.₅ 能力证据**（§7.7 三个已量化的混淆因子）。**接口贯通 ≠ 能力**（见 §0.1）。

---

## 0. 摘要（数字都带负载上下文）

| 项 | 实测值 | 证据 |
|---|---|---|
| 加载 | `from_pretrained` **52.2 s**（NFS，冷页缓存）、**3.6168 B** 参数、**全 F32** | `runs/vla/a2_pi05_contract_20260929/contract.json → load` |
| 显存 | 权重 **13,812.5 MiB**、前向峰值 **14,105.2 MiB**（A800 80 GB） | 同上 → `forward.gpu` |
| 权重完整性 | **812/812 张量 bitwise 相等**、**0 个模型键未被覆盖** | `load_verification.json`（`verdict=all_bitwise_equal`） |
| chunk | **50 步**，输出张量 **(1, 50, 32)** | `contract.json → forward` |
| 延迟 | 首帧 **1.378 s** / 稳态 **0.479 s**（std 0.0018, n=3）/ 端到端 `select_action` **0.123 s**（被 50 步队列摊薄）/ 单次出队 **0.0023 s** | `contract.json → six_questions.q6` |
| 负载上下文 | `loadavg` **33–49**、`nr_throttled` **1839 → 1926（Δ87）**（G2 全程） | `contract.json → load_before/forward.load_after_forward` |
| 视觉通道 | gym-aloha 3 相机 224² **8.76 fps**、整局 **11.27 fps**（软件渲染 llvmpipe，GPU 0 MiB） | `runs/vla/a2_g05_vision_precheck_20260929/` |
| state 饱和 | **12/12** 手臂关节 ctrlrange 超出 `[-1,1]`，平均仅 **44.7%** 行程可无饱和表示；起手位姿 **2/14 维已越界** | `state_channel_saturation_analysis.json` |
| 环境 | venv `pi05_sim`，manifest **V1–V9 = 9/9**，`torch.__version__ == 2.6.0+cu124`（逐字） | `runs/vla/a2_env_pi05_sim_20260929/env_manifest.json` |
| **G3 零 SFT（20 局，seeds 1000–1019）** | `env_success` **0/20**、独立 `grasp_truth` **0/20**（**无 normalizer stats，state 通道饱和：waist 仅 0.3183 行程可表示 ⇒ 本次 zero-shot 不构成 π₀.₅ 能力证据**）；`flick_candidate` **0**；stage 全 **S0**（**6000/6000** 步无接触）、`max_reward` 全 0.0、方块 **Δx = Δy = 0.00000 m** | `runs/vla/a2_pi05_zeroshot_20260929/summary_pi05.json` |
| **G3 随机对照（同 seed 20 局）** | `env_success` **0/20**、`grasp_truth` **0/20**（随机臂不含模型、不吃 state ⇒ 这两列只用于证明**判据不恒真**，不得与 π₀.₅ 的 `0/20` 并列成能力比较）；但它把仿真**打爆**（17/20 局 `|Δx|>0.1 m`、`box_z_max` **27.96 m**、方块终点 z **−158.53 m**），env 自身 reward 被**弹射**刷到 **2.0** | `summary_random.json` |
| **G3 零假设（hold，本轮新增）** | π₀.₅ **左臂净接近中位 +0.104 m（19/20 seed 为正）**、右臂 **+0.012 m（12/20）** ⇒ **模型在动、方向一致，但差 ≥0.20 m**；快/慢路径交叉校验 **Δ = 0.0000 m** | `approach_baseline.json` |
| **G3 吞吐（配对负载）** | 均局 **28.90 s** = `env.step` **25.22 s（87%）** + 推理 **3.14 s**（6 次）+ 自渲染 **0.40 s** ⇒ **瓶颈是 env 内建 3×480×640 软渲染（实测 ≈78 ms/控制步），不是 π₀.₅**；`env_step_fps` **11.91** / `loop_fps` **10.39**（两口径分列），`loadavg` **39–54**、`nr_throttled` **Δ23**（随机臂 Δ216，含外部尖峰 Δ95/76） | `summary_pi05.json → timing`、`approach_baseline.json → validations_fast_vs_slow` |
| **G3 显存** | 峰值 **14,105.2 MiB**（与 G2 同）、常驻 13,822.3 MiB；随机臂与零假设**全程 CPU-only** | `summary_pi05.json → gpu` |

### 0.1 不得声称（D §5 原文照抄，一条不删）

- **不得**声称 π₀.₅「会搬运」或「zero-shot 成功率为 X 所以能用」——20 局零 SFT 只证明**接口贯通与判据可用**。
- **不得**声称「已适配松灵实机」——本轮**没有接触任何硬件**，实机型号/自由度/夹爪/时延全部 `null`。
- **不得**把仿真吞吐外推成实机吞吐，也**不得**把 `steps/s`（纯 env stepping）当成 `s/局`（含推理与 reset）。
- **不得**把外部来源事实（license、他人报告的显存数）写成本机实测；引用时必须标 `external_unverified`。
- **不得**引用 ACT/Lift 线的成功率来给 π₀.₅ 背书（不同底座、不同任务、不同判据）。

### 0.2 本轮触发的两条降级/偏离（已按 §7 立刻报 D，未自行换口径）

1. **ckpt 要 lerobot git main，D 指定 0.4.4** ⇒ 用**兼容目录**（删两个 `enabled=false` 的 processor 步骤，等价性已从 lerobot main 源码证明）。**待 D 裁**（§8-1）。
2. **`transformers` 正式版加载不了 π₀.₅** ⇒ 装 lerobot `pi` extra 指定的补丁分支（4.53.3）。**这推翻了 D §9.1 的一条前提**（§8-2）。

---

## 1. G0 —— 持久 venv `pi05_sim`（三条验收全过）

- **建法**：`codex-persist mkvenv pi05_sim --clean --link /root/venvs/pi05_sim`（`include-system-site-packages=false`，与已验收的
  `lerobot_act`/`lerobot_eval` **同构**）；缓存与权重全在 NFS `.codex-persist/`，**`/root` 下只有软链**（D §0-2）。
- **红线（D §9.2-3）**：`torch.__version__ == "2.6.0+cu124"`（逐字）、`torchvision 0.21.0+cu124`、`torchcodec dist 0.10.0`、`lerobot 0.4.4`。
  **三次解析/实装（STAGE 1、2c、3）的增删改行里 torch/torchvision/torchcodec/triton/nvidia-\* 一个都没出现** ⇒ 未触发停手条件。
- **一个 dist-info 口径差（要留痕，不是漂移）**：基线 `lerobot_act` 的 torch **METADATA** 写 `2.6.0`、本 venv 写 `2.6.0+cu124`，
  而**两者 `torch.__version__` 都是 `2.6.0+cu124`**（本机直接实测）⇒ local-version 后缀随**安装源**而变。
  漂移判据因此按**运行时版本**判，dist 差异单列（`env_manifest.json → frozen_stack_dist_metadata_difference`）。
- **既存缺口（非本轮引入）**：`torchcodec 0.10.0` **装了但 import 失败**（`Could not load libtorchcodec`，缺 FFmpeg 4–8）；
  **基线 venv 同状况** ⇒ 不是断点漂移。影响面：lerobot 的**视频**数据集（mp4）解码不可用；本轮走仿真渲染 + 本地 safetensors，不阻塞。
  **B2 若要接 LeRobotDataset 的视频帧，这条会挡住，建议先验。**
- **验收 3 产物**：`requirements.lock.txt`（**122 pin**，`sha256=4d849aca20285c8e908c52533a4332778cf360334cc3d526e4dbccdc304d01cc`，
  `transformers` 那行带 **commit sha** 而非分支名 ⇒ 可复现）+ `env_manifest.json`（`probe_kind=semantic`，复用 A 线 `probe_venv`/`parse_pyvenv_cfg`/`sha256`，未另写口径）。
  冷导入：torch 4.39 s / transformers 7.87 s / lerobot 0.05 s。**交 B2 过 provenance 闸。**

## 2. G0.5 —— 视觉通道预检：**结论 = 甲**（能出图且 fps 够闭环评测）

| 通道 | 出图 | π₀.₅ 真实需求档（3 相机 224²） | 整局口径 | GL 实现 |
|---|---|---|---|---|
| **gym-aloha**（D §11.2 首选） | ✅ | **8.76 fps**（`MUJOCO_GL=egl`）/ 8.49（osmesa） | `env.step` **11.27 fps** | `GL_RENDERER = Mesa llvmpipe (LLVM 15.0.7)`，**GPU 0 MiB** |
| **robosuite 1.5.2** | ✅ | 114 fps（224²×3, egl） | 480×640×3 仍 125 fps | `libEGL_mesa`/`libOSMesa`，GPU 0 MiB |
| **ManiSkill3 / SAPIEN** | ❌ | `Failed to find a supported physical device "cuda:0"` | — | 缺 glvnd ICD |

- **判甲依据（按 D 自己的阈值，不是"我觉得够"）**：§8.2 的乙案例子是"224² 三相机 < 2 fps"，实测 **8.76 fps = 阈值 4.4 倍**。
  **丙案没有触发**；且 §11.2 明写丙案**只能由用户裁**，A2 不选、也**不会**退化成状态输入小模型
  （顺带一条硬事实：gym-aloha 0.1.4 的 `obs_type="state"` 是 `raise NotImplementedError()` ⇒ 该环境**技术上就没有纯状态档**）。
- **根因（比"无 Vulkan"更精确）**：容器里 **NVIDIA 只装了计算库、没有图形库** —— `libEGL_nvidia.so.*`/`libGLX_nvidia.so.*`/`50_nvidia.json` 全部不存在
  （`find / -xdev` 0 命中），只有 `libnvidia-{ml,cfg,allocator,opencl,nvvm,ptxjitcompiler}` ⇒ `MUJOCO_GL=egl` 只能落到 mesa 软件 EGL；
  SAPIEN 走 Vulkan、lavapipe 要 `Present`，两条**同一根因**不通。
- **给 D 的可执行选项（A2 不自行决定）**：要 GPU 渲染就得让平台在镜像里补**与驱动 590.48.01 匹配的 `libEGL_nvidia`/`libGLX_nvidia`/Vulkan ICD**。
- **⚠ 一条口径分歧仍待 D 裁**：`daily_report.md:47` 记的 robosuite 64² 单相机 **8.5 fps** 与 A2 实测 **133–143 fps**（~16×）
  **不得并列引用**；A2 的数字带 `loadavg`/`nr_throttled`，但两者测量时点不同，**归因未定**。

## 3. G1 —— 权重落地（7/7 + sha256 三方一致 + license）

- 位置：`.codex-persist/hf-cache/modelscope/lerobot/pi05_base/`（**NFS**，非 `/root`）。
- `model.safetensors` = **14,467,165,872 B**，走 **ModelScope 单流**（553 s，**26.2 MB/s**）；6 个小文件走 **hf-mirror + 复用 D §8.1 指定的
  `hf_mirror_snapshot.py`**（A2 只做向后兼容的最小扩展：加 `--repo-type model` 与 pattern 过滤；原文件备份为
  `hf_mirror_snapshot.before_a2_model_support.py`）。**没有另写第三个下载器**，也**没有裸调 `snapshot_download`**。
- **sha256 三方一致**：本地 = HF LFS oid = ModelScope = `0eb11ca9…59b0f`；`license = **gemma**`（Gemma Terms of Use，已进 receipt 证据链）；
  commit `b211f3d4…`；safetensors 头实测 **812 张量全 F32**。receipt：`runs/vla/a2_env_pi05_sim_20260929/weights_receipt.json`。
- tokenizer `google/paligemma-3b-pt-224` 在 HF 上 **gated（403）** ⇒ 8/8 文件改从 ModelScope 取（`scripts/a2_modelscope_fetch.py`）。
- **本轮新增的一条完整性验证（比"数文件 + 核 size"更强）**：**逐张量 bitwise 比对**，见 §4.0。

## 4. G2 —— 动作与时间契约**六问**实测

### 4.0 先说一条"看起来像权重没加载"的假警（已逐张量证明是良性）

`from_pretrained` 会打印 `Warning: Could not remap state dict keys: … Missing key(s) … "…paligemma.model.language_model.embed_tokens.weight"`。
形态危险：`modeling_pi05.py:1021` 是 `load_state_dict(…, strict=True)` ⇒ 抛错 ⇒ 被 `:1046` 的**裸 `except`** 吞成一行 warning 就 `return model`。
**真因**：safetensors 把**共享存储（tied）**的张量只存一份，别名记在 header 的 `__metadata__` 里
（实测 `{"…language_model.embed_tokens.weight": "…paligemma.lm_head.weight"}`），而 0.4.4 的 loader **不展开 `__metadata__`**。
**验证**（`scripts/a2_verify_pi05_load.py` → `load_verification.json`）：**812/812 bitwise 相等**、**0 shape 不匹配**、
**模型侧 0 个键未被 ckpt 覆盖**（= 没有任何参数留在随机初始化）；tied 那一对 **`data_ptr` 相同**且 bitwise 相等 ⇒ `all_bitwise_equal`。
**一般规则（给 B2 的准入闸）**：**不许把这条 warning 读成"权重没加载"，也不许把"没报错"读成"权重加载了"**；两边都要逐张量验。

### 4.1 六问

| # | 问 | 答 | 状态 | 证据/为什么是这个状态 |
|---|---|---|---|---|
| ① | chunk 长度 `n_chunk_steps` | **50 步** | **measured** | `config.chunk_size=50`、`n_action_steps=50`；实测 `predict_action_chunk` 输出 **(1, 50, 32)** |
| ② | 单步动作维度与顺序 | 张量 **32 槽位**；**有效 = 前 14 维**，顺序 **[左臂6, 左夹爪1, 右臂6, 右夹爪1]**（双臂、**关节**而非末端位姿） | **inferred（强经验证据）** | ckpt **不携带** embodiment 映射表（`output_features.action.shape=[32]` 只是 `max_action_dim` 的 padding 上限）。经验证据见 §4.2 |
| ③ | 单位 | 关节 **rad**、夹爪 **归一化 [0,1]**；输出实测 absmax **0.916** | **inferred**（文档层面 **unknown**） | `policy_preprocessor.json` 的 `normalizer_processor.config.features = {}` ⇒ **base ckpt 不带任何归一化统计量**，postprocessor 的 unnormalizer 同样无 stats ⇒ 没有"模型内部空间 → 物理单位"的映射可查 |
| ④ | 参考系 | **absolute**（非增量）+ **关节空间**（非 base/world 末端位姿） | **partially measured** | `relative_actions_processor.enabled = **false**`、postprocessor 的 `absolute_actions_processor.enabled = false`（实测）；"关节空间"来自 §4.2 的逐维对应 |
| ⑤ | 夹爪语义 | **连续开合度**（非二值），落在 **[0,1]**，gym-aloha 侧约定 **0=close / 1=open** | **inferred** | dim 6/13 实测输出 **0.207 / 0.209**（state 对应 0.141/0.157）；gym-aloha 侧的 0/1 方向是**实测已知**（`constants.py` + `sim.py:before_step` 的 `unnormalize_puppet_gripper_position`），π₀.₅ 侧的方向**未证** |
| ⑥ | 推理延迟 | 首帧 **1.378 s**；稳态 **0.479 s**（std 0.0018，n=3）；**含 pre/post 的端到端** `select_action` 均值 **0.123 s**；单次出队 **0.0023 s** | **measured** | `loadavg 33–49`、`nr_throttled Δ2`（G2 前向段）。**首帧与稳态分开记**（D §4-②）；端到端那一列**含** preprocessor/postprocessor 与 H2D 拷贝 |

**⑥ 的成本模型（G3 用的就是它）**：`chunk_size == n_action_steps == 50` ⇒ 一个 chunk 被**完整消费**，
每 50 个控制步才跑一次扩散。所以**有效控制频率上限 = 50 / 0.479 s ≈ 104 Hz**（**不含** env stepping、渲染、真机通信）；
而**单步出队只要 0.0023 s**。**不许把 0.123 s 的摊薄值当成"每步推理耗时"**，也不许把 104 Hz 当成实机可达频率。

### 4.2 ②③④⑤ 的经验证据：state ↔ action 逐维对应（本轮最有价值的一张表）

喂**真局起点**的 state（`env.reset(seed)` ⇒ `START_ARM_POSE`），比对 action 的第 1 步与 state（4 组观测，每组之间**真的推进了仿真**）：

| dim | 语义（gym-aloha `JOINTS`） | state 均值 | action 均值 | \|a−s\| | rel_dev |
|---|---|---|---|---|---|
| 0 | left waist | 0.025 | 0.043 | 0.019 | 0.68 |
| 1 | left shoulder | **−0.934** | **−0.843** | 0.090 | **0.097** |
| 2 | left elbow | **1.143** | **1.035** | 0.108 | **0.095** |
| 3 | left forearm_roll | −0.007 | −0.002 | 0.020 | 2.65 |
| 4 | left wrist_angle | −0.297 | −0.291 | 0.014 | **0.047** |
| 5 | left wrist_rotate | −0.034 | −0.171 | 0.136 | 2.82 |
| 6 | **left gripper** | 0.141 | **0.207** | 0.071 | 0.51 |
| 7 | right waist | −0.042 | −0.324 | 0.282 | 6.66 |
| 8 | right shoulder | **−1.060** | **−0.836** | 0.224 | 0.21 |
| 9 | right elbow | **1.170** | **0.832** | 0.338 | 0.29 |
| 10 | right forearm_roll | −0.005 | 0.083 | 0.088 | 5.86 |
| 11 | right wrist_angle | −0.271 | −0.284 | 0.042 | 0.15 |
| 12 | right wrist_rotate | 0.006 | −0.026 | 0.034 | 2.50 |
| 13 | **right gripper** | 0.157 | **0.209** | 0.052 | 0.33 |
| 14..31 | padding（`max_action_dim=32`） | — | absmean **0.066**（**非零**） | — | — |

- **读法**：**大幅值维**（shoulder/elbow/wrist_angle，|state| ≈ 0.3–1.2）的 `rel_dev` 只有 **0.05–0.29** ⇒ action 与 state **同序、同尺度、同单位**；
  夹爪维（6/13）两边都落在 **[0,1]** 的归一化区间。**若槽位顺序或单位不对，这张表不可能对上。**
- **`rel_dev` 大的维（0/3/5/7/10/12）都是 state ≈ 0 的维** ⇒ 分母小，比值天然大；**不能用 `first14_mean_rel_dev=1.64` 这个聚合值下结论**
  （它是被近零维拉高的），要看**逐维**。这条写在这里，就是防止下一个人只读聚合数。
- **仍然只是 inferred 的理由**：ckpt 里没有 embodiment 映射表；上面是"绝对关节位置策略在起点附近应输出 ≈ state + 小增量"这一**假设**下的推论，
  n_obs=4、单场景、zero-shot（未针对 ViperX 微调）。**padding 区非零**也说明"32 槽位"不能按"前 14 有效、后 18 恒零"来硬判。

### 4.3 state 通道的饱和面（P0 要的答案之一，**接数据面前必须处理**）

- `Pi05PrepareStateTokenizerProcessorStep` 把 state 按 `np.linspace(-1,1,257)[:-1]` 切成 **256 个 bin**，源码注释明写
  "state 应已被 `NormalizerProcessorStep` 归一化到 [-1,1]"；但 **base ckpt 的 normalizer `features={}`（无统计量）⇒ 直接吃原始值**。
- 实测（`bimanual_viperx_transfer_cube.xml:17-33` 的 ctrlrange × 上述离散化，**算术推算**）：
  **12/12 个手臂关节的 ctrlrange 都超出 [-1,1]**，平均只有 **44.7%** 的行程能被无饱和表示
  （waist/forearm_roll/wrist_rotate 只有 **31.8%**，wrist_angle 48.8%，elbow 59.4%，shoulder 64.4%）。
- **标准起手位姿就已经越界**：`START_ARM_POSE` 的 `elbow = 1.16` ⇒ dims **2 与 9** 被静默贴到端点 bin、**不报错**。
- ⇒ **接进本仓数据面必须提供 normalizer 统计量（或先自行归一化再喂）**，否则 state 通道信息被**静默截断**；
  这条与 C 线 §2.2 的"图像键被静默丢弃"是**同一家族**（判据/管线没有在看它声称在看的东西）。

### 4.4 观测敏感性（判据有牙的证据）

4 组观测之间**真的推进了仿真**（`advance_physics()`，推进失败即抛错）：`qpos_Δmax 0.011–0.021`、`image_Δmean 2.35–2.82 uint8`；
动作随之改变：`mean|Δaction| = **0.0439** ⇒ changes_with_observation = True`。
**第一版这里是假红风险**（每次"换观测"都重建 physics ⇒ 观测根本没变），与 G0.5 那次 liveness bug 同族，已修并留档。

## 5. **三列映射表**：π₀.₅ 原生 ↔ ABC-130k(YAM) 实测 ↔ Piper/Cobot Magic

> **硬纪律（D §11.3 / 裁定 41.2）**：**第二列的数值不得搬进第三列**（YAM 与 Piper 的关节零位、限位、连杆长度、夹爪行程都不同）。
> 第三列取不到就留 `null`/`unknown`（`02_开发实施指南.md:7`：不用论文默认值猜）。
> 第二列的数值来源 = **D 的实测**（`work/project_parameters.json → action_contract` / `timing.control_hz` / `hardware`），A2 **未重做**（D §1：重做即浪费 12 核配额）。
> **第三列（Piper）19:5x 起有值了**：来源 = **D 的 §12.2 / §12.3 / §12.4 实测**（`runs/vla/d_render_probe_20260929/`），A2 **只引用未重做**，逐格标 `D-measured`。
> **裁定 43（三值并列）**：夹爪行程 **URDF / MJ joint / MJ ctrl 三套值必须并列**，实机校准前**不得选定任何一个当真值**。

| 契约项 | ① π₀.₅ 原生（本轮实测/推断） | ② ABC-130k（**YAM 双臂站**，D 实测） | ③ Piper / Cobot Magic（实机） |
|---|---|---|---|
| 形态标注 | `morphology="aloha_bimanual_14d"`（ViperX-300 双臂，**仿真**） | `morphology_proxy="yam"` | 无数字孪生 env（`mani_skill` 内 `*piper*`/`*agilex*` **0 命中**）；但**模型文件已在本机** `.codex-persist/piper-assets/Piper_ros`（D 下载）`D-measured` |
| 动作总维度 | 张量 **32** 槽位；**有效前 14**（inferred） | **14** = left_arm.joint(6) + right_arm.joint(6) + left_gripper(1) + right_gripper(1) | **模型级 8/臂**（`nq=nv=nu=8`，8 个 position 执行器）⇒ 双臂 **16**；**指令级 7/臂** ⇒ 双臂 **14（ALOHA 相容）**（裁定 41.1 / 43.3）`D-measured` |
| **维度顺序** | **[左臂6, 左夹爪1, 右臂6, 右夹爪1]**（ALOHA 交错式，inferred） | **[左臂6, 右臂6, 左夹爪1, 右夹爪1]**（**臂优先、夹爪在尾**） | `null`（待 SDK/URDF 或实机） |
| **⇒ 排列差（本轮新发现）** | — | **两者不是同一个排列**：需一次**显式重排** `①idx 0-5 ← ②idx 0-5`、`①idx 7-12 ← ②idx 6-11`、`①idx 6 ← ②idx 12`、`①idx 13 ← ②idx 13` | 重排表待定（依赖③的顺序） |
| 关节单位 | **rad**（inferred，§4.2） | **度**（实测范围 左 J1 −67.0~−3.3 / J2 20.5~133.3 / J3 31.6~104.5 …） | `null` |
| 关节零位/限位 | gym-aloha ctrlrange 实测（`xml:17-33`，如 shoulder [−1.850, 1.257] rad） | `null`（D 未测 YAM 限位） | **URDF 与 MJ 限位不一致**：J6 差 **1.0456 rad（最大）**、J1 0.45、J3 0.27、J4 0.087、J7/J8 0.015 m；MJ 内部 `ctrlrange` 与 joint range 也不等 ⇒ **三套值并列，实机校准前不得选定**（裁定 43）`D-measured` |
| 参考系 | **absolute**（measured：`relative_actions_processor.enabled=false`）+ **关节空间**（inferred） | **commanded 与 observed 分开**（mcap topic `/left-arm-action` vs `/left-arm-state`、`/left-ee-action` vs `/left-ee-state`） | `null` |
| action vs state | 模型输出 = commanded（inferred）；本轮**未**混用。**gym-aloha 侧也实测到 commanded ≠ observed**：夹爪 cmd 0 → ctrl 0.01844 m 而实测 qpos 0.0224 m（Δ≈4 mm，`frictionloss=30`）`A2-measured` | **实测不同**：首帧差 **1e-3 ~ 4e-2** ⇒ **两者不可混用** | `null`（但**形态可预期同型**：有摩擦/限位 ⇒ commanded≠observed；实机前不得假设相等） |
| 夹爪所在维 | dim **6**（左）/ **13**（右） | idx **12**（左）/ **13**（右） | `null`（顺序待 SDK/URDF 或实机） |
| **夹爪模型级结构** | **2 个独立 slide 指关节/臂**（`left_finger [0.021,0.057]`、`right_finger [−0.057,−0.021]`）⇒ 16 项 ctrlrange 对 14 维指令 `A2-measured` | `unknown`（D 未测 YAM 指关节数） | **`joint7`/`joint8` 两个独立 slide 关节**，官方模型**无 `<equality>`**、URDF **无 `mimic`** ⇒ **两指不会自动联动，必须自己加耦合**（§12.3）`D-measured` |
| **1 维指令 → 2 指的机制** | **指令层镜像**：`before_step` 把归一化 `g` 反解成 `g·(OPEN−CLOSE)+CLOSE`（OPEN **0.058** / CLOSE **0.01844** m），再展开成 `[+g, −g]`；`bimanual_viperx_transfer_cube.xml` 里 **`<equality>`/`tendon` = 0 处** ⇒ **模型层无耦合**（`gripper_1d_to_2finger.json`）`A2-measured` | `unknown` | **待实现**：照抄"指令层镜像"或用 `<equality>`；**按关节类型（slide/prismatic）识别**，不要按名字关键字（`joint7/8` 名字里没有夹爪字样）`D-measured` |
| 夹爪语义 | **连续归一化开合度 [0,1]**（inferred） | **归一化开合度**，实测 **[0, 0.998]** | `null`（归一化方式未知）；**行程三值并列：URDF 50 mm / MJ joint 35 mm / MJ ctrl 47.5 mm ⇒ 实机校准前不得选定**（裁定 43）`D-measured` |
| 夹爪方向（0=?） | gym-aloha 侧**实测** 0=close / 1=open；π₀.₅ 侧**未证**。**且归一化端点落在声明限位之外**：cmd 0 → 0.01844 m < 下限 0.021；cmd 1 → 0.058 m > 上限 0.057 ⇒ **实测可达开口 44.8–113.9 mm，"全闭"不可达** `A2-measured` | **unknown**（0 是 close 还是 open 未测） | `null` |
| 控制频率 | **50 Hz**（实测三元组 `timestep=0.002, decimation=10, 50.0 Hz` ⇒ **不在 QC [29,31] 内**）；30.0 Hz 可行三元组 = `1/480, 16, 30.0 Hz`（`ctrl_hz_alignment_a2.json`）`A2-measured` | **29.76 fps**（4749 帧 ÷ 159.58 s；团队 QC 合格区间 [29.0, 31.0]） | `null`（**待实机实测**）；项目锚点 = **30 Hz**（裁定 45），实机若不同**必须重新锚定，不得沿用仿真值** |
| chunk 长度 | **50 步**（measured） | 数据是**逐帧**的，无 chunk 概念 | `null` |
| **⇒ 时间契约** | 50 步 @50 Hz = **1.00 s** 的动作；同一 chunk 若按 29.76 Hz 执行 = **1.68 s** | — | **实机频率未知 ⇒ chunk 的时间跨度未知**；接实机前必须重采样/重定标 |
| 单次推理延迟 | 稳态 **0.479 s**/chunk（首帧 1.378 s）；有效上限 **≈104 Hz**（不含 env/渲染/通信） | — | `null` |
| 相机数与命名 | **3 路**：`base_0_rgb` / `left_wrist_0_rgb` / `right_wrist_0_rgb`（`config.json` 实测）；**base 相机 20/20 seed 都能看到红方块，质心与真值位姿 r=+0.994/−0.999**（`red_cube_visibility.json`） | top 1 + 左右腕（D 的 `expected_camera_layout` 参照同形态数据） | **官方 `mujoco_model/piper_description.xml` `ncam=0` ⇒ 一个相机都没有，必须自己注入**；建议 `cam_high`(top)/`cam_wrist`(挂 `link6`)/可选 `cam_front`；MjSpec 注入 **没有 `zaxis` 属性**（`add_camera()` + `pos/quat/fovy`）`D-measured` |
| 图像分辨率 | **224×224**（`config.json.image_resolution`） | **640×480** | `null` |
| 内参 | ckpt **不带**；仿真侧由 MuJoCo 相机 `fovy=78/20` 定义（`scene.xml:28-32`、`vx300s_*.xml:32`） | **单个 3×3**：fx 431.88 / fy 431.38 / cx 324.26 / cy 240.97（⇒ 640×480） | `null`（**待标定**）；D §12.2 给的 YAM 内参**只是参照、不是 Piper 标定值**，不得当标定结果用 |
| state 维度 | 张量 **32** 槽位；本轮实喂 **14** | 每臂 `joint(6)` + `pose(7 = xyz m + quat)` + `velocity(6)`，夹爪 1 | `null` |
| state 归一化 | **无统计量** ⇒ 直接 256-bin 离散化，`[-1,1]` 外**静默饱和**（§4.3） | `unknown`（数据侧是否已归一化未测） | `null` |
| 语言条件 | `task` 字符串，tokenizer max_length **200**（`policy_preprocessor.json`） | `unknown` | `null` |
| 权重许可 | **`gemma`**（Gemma Terms of Use；ckpt `README.md` frontmatter 实测） | — | — |

**注（①列的 `inferred` 一律带 §4.2 的证据强度限定；②列一律是 D 的实测，A2 只引用不重做；③列凡有值一律标 `D-measured` 且**尚未实机校准**，其余仍 `null`/`unknown`，一个都没猜。）**

**跨形态禁令（裁定 43，D 实测）**：YAM J3 是**正值区间 31.6~104.5 度**，而 Piper J3 的 MJ 限位是 **−2.967~0 rad（全负）** ⇒
参照数据集（②列）的 action **数值**只能作**分布形态**参照，**绝不得**当作 Piper 的限位或零位依据。
这类错最难发现：契约表看起来"已实测"，其实是**别的机器人**的数。

## 6. π₀.₅ 接进本仓数据面**要改哪几处**（D §6：**本轮只标出，不改**）

按 C 的《A2/B2 复用清单》(`docs/c_reuse_manifest_for_a2_b2_20260929.md`) 逐条对齐，**加上本轮 G2 新发现的 3 条**（标 🆕）：

| # | 位置 | 要改什么 | 依据 |
|---|---|---|---|
| 1 | `harness/queue_td_learner.py:134-140` | obs 键消费必须**白名单 + 断言全覆盖**（存进去的键集合 vs 被 collate 消费的键集合逐键比对，有剩余就拒）。当前形状下**同时有 `state` 与图像键时，图像键被无声跳过、宽度检查还会通过** | C §2.2（给 A2/B2 的第一条硬要求） |
| 2 | `harness/data_bridge.py:440` | `n` / `chunk_len` 必须按 π₀.₅ 的真实 chunk 重定标（**实测 chunk=50、n_action_steps=50**）；`E_k` 取 `[n,2n)` 是设计假设 | C §3.5 + 本轮 ①实测 |
| 3 | `harness/data_bridge.py:557`（`resolve_x`） | **视觉表征完全缺失**（只回原始数组、无表征重算）⇒ π₀.₅ 路线下这是 **P0** | C §2（D 已升级） |
| 4 | `harness/obs_store.py:95` / `:157` | ①`np.savez` **不压缩** ⇒ 3×224² uint8/帧的容量**必须先实测**再接；②**同内容不同采样时刻硬拒** ⇒ 真相机重复帧会撞墙 | C §2.3/§2.4（**C 明确要求 A2 接真帧前实测**，见 §8-7 待办） |
| 5 | `harness/obs_store.py:125`/`:104` | π₀.₅ 的 image processor / resize / 归一化配置**编进 `representation_version` 字符串**、用 `normalizer_hash` 承载，**不要新造版本字段** | C §2.5 |
| 6 | `harness/runtime_adapter.py:21` | 默认 `driver` 是 mock 回执 ⇒ 换成真推理 + 真 sim step（本轮 G3 的 loop 可作参考实现，但**不在 harness 边界内**） | C §3.2 |
| 7 | `registry/verdict_identity.py:47` | `GATE_MODULE_PATH` 钉死在 ACT 门禁 ⇒ π₀.₅ 需要**参数化门禁来源**；**多门禁并存**（ACT 冻结基线 + π₀.₅ 新线）的口径**需 D 裁** | C §3.8 |
| 8 | `registry/release_bundle.py:29`/`:238` | `REQUIRED_ROLES` 含 `q`/`q_target`/`optimizer` ⇒ zero-shot / 纯 BC 发布**必须显式 `waive_roles`**（会记进 manifest），**不许塞假组件** | C §3.7 |
| 9 | `harness/contracts.py` | **一个字都不用改**（观测是不透明 `dict[str,Any]`）。但 `QueueState` 的 C/E/D 三队列语义在 π₀.₅ 无抢占队列时要**显式声明"退化"**，不留空 | C §3.1 |
| 10 🆕 | normalizer 统计量 | **必须**给 π₀.₅ 提供 state/action 的归一化统计量（或先自行归一化再喂），否则 §4.3 的**静默饱和**会吃掉 state 信息 | 本轮 §4.3 实测 |
| 11 🆕 | 14 维**排列差** | ABC-130k 与 ALOHA 的 14 维**不是同一个排列**（§5）⇒ 重排必须落在**数据桥/契约层**（且进 `action_contract` role 的身份），**不许散落在各脚本里** | 本轮 §5 新发现 |
| 12 🆕 | 单位与定标状态 | π₀.₅ 的动作单位/频率走 `data_bridge.export_views(unit_convention=...)` 的**同一个字段**，让 `assumed`/`measured`/`spec` 在分片层面就分得清；**不要继承 C 线仍是假设值的 γ/n** | C §6-3 + 本轮 ③=inferred |
| 13 | Lift 语义字段 | `grasp_verified`/`max_rise`/`failure_phase`（`contracts.py:33`）是 **Lift 语义**，在 AlohaTransferCube 下**留空不借位**；本轮 G3 的 grasp 真值列用**自己的字段名**（`grasp_truth`），建议 D/B2 为新任务**另立字段**而不是复用 Lift 的 | C §6-1 |
| 14 | `torchcodec`/FFmpeg | 若 B2 走 LeRobotDataset（mp4 + torchcodec）⇒ **本机 import 不了 torchcodec**（§1），必须先补 FFmpeg | 本轮实测 |

## 7. G3 —— 零 SFT 基线（20 局）+ 随机基线对照

### 7.0 结论行（按 D §12.11-2 的强制口径写）

> **本次 zero-shot 不构成 π₀.₅ 能力证据。** π₀.₅ 零 SFT 20 局的 `env_success = 0/20`、独立 `grasp_truth = 0/20`，
> **是在「无 normalizer stats、状态通道饱和（waist/forearm_roll/wrist_rotate 仅 0.3183 行程可不饱和表示，shoulder 0.6438、
> elbow 0.5937、wrist_angle 0.4876）」的条件下得到的**，因此**不得**据此对 π₀.₅ 的能力上下界做任何判断
>（裁定 46.6：拿到 stats 之前不得再用 zero-shot 成功率做路线判断）。

**接口贯通 ✅、判据有牙 ✅、能力 ❌ 不可声称。** 三批**同一 seed（1000–1019）**：π₀.₅ 20 局 + 随机 20 局 + hold 零假设 20 局，
两臂 `rc=0`。π₀.₅ 在 **6000/6000 个控制步里没有与方块发生任何接触**（stage 全 S0、`max_reward` 全 0.0、方块 **Δx = Δy = 0.00000 m**）。
但**这不等于"接线死了"**：与**「起手位姿保持」零假设**逐 seed 相比，π₀.₅ 的**左臂在 19/20 个 seed 上更接近方块**，
净接近中位数 **+0.104 m**（最大 +0.198 m）⇒ **模型在动、方向也不是随机的，只是差得远**（左指最近距离中位数 0.304 m，
而接触需要 ≈0.02 m 量级）。
产物：`runs/vla/a2_pi05_zeroshot_20260929/`（`summary_pi05.json`、`summary_random.json`、`approach_baseline.json`、
`weights_linkage.json`、`render_selfcert.json`、`red_cube_visibility.json`、`render_throughput_a2.json`、
`gripper_1d_to_2finger.json`、`ctrl_hz_alignment_a2.json`、`run_*.log`、`frames_*/`）。

### 7.1 跑法（口径，可复现）

| 项 | π₀.₅ 臂（A） | 随机臂（B） | 零假设（hold，本轮新增） |
|---|---|---|---|
| 环境 | `gym_aloha/AlohaTransferCube-v0`，`obs_type="pixels_agent_pos"` | 同 | 同 |
| 形态标注 | `morphology="aloha_bimanual_14d"`（D §11.2 要求，产物已带） | 同 | 同 |
| seed | 1000–1019（20 局） | **同一批** | **同一批** |
| 策略 | base ckpt（兼容目录）+ 3×224² 图 + 14 维 state | `rng.uniform(action_space.low, high)` | `ctrl` 钉在 `START_ARM_POSE` |
| 动作下发 | **chunk 队列**：`chunk_size=50`、`n_action_steps=50` ⇒ 6 次推理覆盖 300 步（脚本对 `chunk != n_action_steps` **直接抛错**，不允许静默降级成 `select_action`） | 每步 1 次 | 无 |
| 步数/时长 | 300 步 = **6 s** @50 Hz；`terminal_reason=time_limit` **20/20** | 同 | 同 |
| 设备 | `cuda`（A800，峰值 **14,105.2 MiB**） | `CUDA_VISIBLE_DEVICES=""`（**CPU-only**） | CPU-only |
| 任务串 | `"Transfer the red cube from the right arm to the left arm."` | 无（随机臂不吃语言） | 无 |

**任务串与场景一致性（本轮核验，不是照抄惯例）**：gym-aloha **自己没有语言通道**（`env.py` 全程无 instruction 字段），
所以任务串是**评测的自由参数**，必须自证没喂反。实测/查源：方块 spawn 区 `x∈[0.0,0.2]、y∈[0.4,0.6]`
（`gym_aloha/utils.py:4-15`），20 局实测 `x∈[0.0053,0.1677]、y∈[0.411,0.589]` 与之吻合；
左臂基座 `x=−0.469`、右臂基座 `x=+0.469`（`assets/vx300s_left.xml:3`、`vx300s_right.xml:3`）⇒ **方块在右半区**；
`reward==4` 要求**左**夹爪持物离桌（`tasks/sim.py:125-149`）⇒ 「从右臂交到左臂」这句与场景**同向**，没喂反。
另外起手距离也印证了这点：`d_right_at_reset` 中位 **0.292 m** < `d_left_at_reset` 中位 **0.430 m**。
**但 π₀.₅ base 是否用同一措辞训练过 = `unknown`（external_unverified，ckpt 不带数据卡）。**

**三条判据（定义写进产物，不靠口头）**：
`env_success` = `info["is_success"]` = `reward==4` = 左夹爪**单指**（`vx300s_left/10_left_gripper_finger`）触碰方块 **且** 方块不接触桌面（**瞬时**）；
`grasp_truth` = 本脚本独立算：左夹爪**任一根**手指触碰方块 + 方块离桌 + **连续保持 ≥10 步（0.2 s）**；
`flick_candidate` = `env_success ∧ ¬grasp_truth`（伪成功候选）。

### 7.2 结果（两臂 + 零假设并排；**三个口径不得互相冒充**）

| 指标 | π₀.₅ zero-shot | 随机基线 | hold 零假设 |
|---|---|---|---|
| `env_success` | **0/20**（无 normalizer stats、state 饱和 waist 0.3183 ⇒ **非能力证据**） | **0/20**（不含模型 ⇒ 只证判据不恒真） | 0/20 |
| `grasp_truth`（独立严判据） | **0/20**（同上，**非能力证据**） | **0/20**（同上） | 0/20 |
| `flick_candidate` | **0** | **0** | 0 |
| `max_stage` 分布 | **S0 ×20** | S0 ×14、S1 ×1、**S2 ×5**、S3 ×0、S4 ×0 | S0 ×20 |
| 6000 步的 stage 计数 | `[6000,0,0,0,0]` | `[5992,1,7,0,0]` | 全 S0，`any_contact` **0/20** |
| env 自身 `max_reward` | **0.0 ×20** | 0.0 ×17、**1.0 ×1、2.0 ×2** | 0.0 |
| 方块 Δx / Δy（整局） | **0.00000 / 0.00000 m**（20/20） | 17/20 局 `|Δx|>0.1 m`，极端 **−68.69 / +71.16 m** | 0（只有沉降 Δz） |
| `box_z_max` | **0.0479 m ×20**（= 首个控制步的沉降值） | 最高 **27.96 m**（方块被打飞） | **0.0479 m ×20** |
| `max_hold_run_steps` | 0 ×20 | **0 ×20** | — |
| 手指↔方块最小距离 L（中位/范围，m） | **0.3044**（0.205–0.453） | 0.1685（0.081–0.496） | 0.4305（0.349–0.471） |
| 手指↔方块最小距离 R（中位/范围，m） | **0.2951**（0.240–0.321） | 0.1024（0.031–0.251） | 0.2931（0.269–0.346） |
| **净接近 vs hold**（L，中位；>0 = 比不动更接近） | **+0.104 m**（19/20 seed 为正，最大 +0.198，1 个 −0.014） | +0.262 m（19/20） | 0（定义） |
| **净接近 vs hold**（R，中位） | **+0.012 m**（12/20 为正） | +0.182 m（20/20） | 0（定义） |
| 输出裁剪 | **314 / 84000 = 0.374%**，最大裁剪幅度 0.342 rad，`raw_absmax=1.2786` | 不适用 | 不适用 |
| 墙钟 | 总 **578.15 s**、均局 **28.90 s** | 总 576.23 s、均局 28.81 s | 总 **52.62 s**、均局 **0.26 s** |
| fps（**两口径分列**） | `env_step_fps` **11.91** / `loop_fps` **10.39** | 10.48 / 10.42 | 不适用（不渲染） |
| 负载上下文 | `loadavg` 38.3→53.1（逐局 39.0–54.1）、`nr_throttled` **Δ23** | `loadavg` 52.9→59.1、`nr_throttled` **Δ216**（ep16/17 单局 Δ95/76 = 外部尖峰） | `loadavg` 56.2→56.7、Δ6 |
| 显存 | 峰值 **14,105.2 MiB**、常驻 13,822.3 MiB | GPU 不可见 | GPU 不可见 |

### 7.3 零假设对照：把「`0/20`（无 normalizer stats、state 饱和 ⇒ 非能力证据）」变成可判读的结论（本轮新增探针）

**为什么必须做**：单看「20/20 无接触、最近 0.30 m」**无法区分两种完全不同的故障**——
(a) 臂根本没动（= 接线/适配死了，要修工程），(b) 臂在动但不朝方块去（= zero-shot 定标/能力问题，要修数据面或 SFT）。
两者的下一步动作相反，所以不能靠猜。

**做法**（`scripts/a2_g3_approach_baseline.py` → `approach_baseline.json`）：同一批 seed，`env.reset(seed)` 后把
`physics.data.ctrl` 钉在 `START_ARM_POSE`（就是 `sim.py:113-114` reset 时写入的那份），推进 **300 控制步 × 10 物理子步**
（`n_substeps` 由 `control_timestep()/physics.timestep() = 0.02/0.002` 实测得出），
距离判据**直接 `import` G3 评测脚本里的同一个 `SceneProbe`**（不另写一套，避免"两个探针两种口径"）。

**快路径先自证**（G0.5 的 liveness 教训 ⇒ 判据必须有牙）：2 个 seed 同时跑慢路径（`env.step()` 全流程）与快路径（直接 `physics.step()`），
最小距离**逐位相同（Δ = 0.0000 m，容忍 0.005 m）**，超差即**响亮失败、不产出报告**；
物理活性也断言（`qpos_Δmax>0` 或 `box_z` 变化，实测沉降 0.05 → 0.0200 m），不推进就抛错。

**读数**：
- hold 的 `d_min_left` 中位 **0.4305 m**、`d_min_right` 中位 **0.2931 m**，`any_contact` **0/20** ⇒ 「什么都不做」当然碰不到，
  而且**右指起手就只有 0.29 m**（方块在右半区）⇒ π₀.₅ 右臂的 0.2951 m **等于没动**（净 +0.012 m、只有 12/20 seed 为正）。
- π₀.₅ **左臂**净接近中位 **+0.104 m**、**19/20 seed 为正**、极差 −0.014…+0.198 ⇒ **不是冻结、不是噪声**，
  有一个**跨 seed 一致方向**的接近行为，只是幅度只有需要的几分之一。
- **值得注意的不对称（不据此定因）**：任务要求**右**臂先抓（方块在右半区、起手右指更近），而实测动的主要是**左**臂。
  这与「**14 维槽位排列假设错了**」（§5 已证 ABC-130k 与 ALOHA **不是同一个排列**）**同形态**，
  也与「模型本身有偏」相容——**两种读法都指向同一个动作：用数据把 contract q2 定死，而不是继续用约定。**

### 7.4 随机臂把仿真**打爆**了：S2 与 reward 2 都是**弹射**，不是抬起（判据必要性的实证）

- 随机臂有 **5/20** 局 `max_stage=S2`（右夹爪触碰 + 方块离桌），但 stage-2 总共只有 **7 步**、`max_hold_run_steps` **全 20 局 = 0**
  ⇒ **全部是一闪而过的接触 + 方块在飞**，没有一次持稳。
- 方块被打出工作区：**17/20** 局 `|Δx|>0.1 m`，极端值 ep4 终点 `(−68.69, +71.16, −134.76) m`、ep7 `box_z_max` **27.96 m**、
  ep8 终点 `z = −158.53 m`（穿地）。原因是动作被当作**绝对关节角**、每步在 ±1 rad 内**均匀跳变**（50 Hz、`kp=800/1600`、
  `forcerange` 150/300 N，`assets/bimanual_viperx_transfer_cube.xml:17-33`）⇒ 0.05 kg 的方块被弹射，**与力学量级自洽，不是数值爆炸**。
- env 自己的 reward 因此给到 **2.0**（ep4、ep7）与 **1.0**（ep8）。查源确认语义（`tasks/sim.py:125-149`）：
  **reward 2 = 右夹爪单指触碰 + 方块不接触桌面**，**不要求持稳、不要求方块留在工作区** ⇒ **弹射就能刷到 2 分**。
- ⇒ 两条可执行结论：① **若将来把 env reward 当 shaping 信号，必须加 workspace / 持稳 guard**（已报 D，§8-10）；
  ② 本轮的 `grasp_truth`（任一指 + 离桌 + **连续 ≥10 步**）在这批数据上把 **5 个假抬起全部拦掉**（0/20）
  ⇒ **sustain 过滤是必要的，不是过度保守**；`flick_candidate` 这一列两臂都是 0，**因为 `env_success` 从未触发**
  ⇒ 它本轮**没有被数据检验到**（诚实登记：不是"验过没问题"，是"没有机会验"），它的必要性由上面 reward 2 的实例来支撑。
- **诚实边界**：随机臂的最小距离更小（L 0.169 / R 0.102 m）**不得**读成"随机比 π₀.₅ 强"——
  那是暴力扫掠 + 仿真已被打爆（方块都在 −134 m 了），两者不可比；随机臂的价值**只有一个**：证明两列 success 判据不恒真。

### 7.5 视觉通道确实在环内（帧活性，不靠"看起来对"）

`frames_pi05/`（ep0，step 1 / 150 / 300，base 相机 224²）实测：
`mean` 36.33 / 36.39 / 38.33，`std` 45.08 / 44.12 / 46.04，`min/max` 0/255（非全黑非饱和）；
相邻帧 **13.34% / 11.83%** 像素改变，`mean|Δ| = 10.25 / 10.28` uint8，`max|Δ| = 230 / 223`
⇒ 喂进模型的图像**随仿真推进而变**，与 G0.5 的甲案结论一致（**GPU 全程 0 MiB 参与渲染**，llvmpipe 软渲染）。

### 7.6 吞吐与负载（每个 fps 都配对负载）

- **π₀.₅ 臂的时间去哪了**：均局 28.90 s 里 `t_env_step` **25.22 s（87%）**、推理 **3.14 s**（6 次）、自渲染 **0.40 s**
  （**6 个推理点 × 3 相机 = 18 帧 ⇒ 22.2 ms/帧**，与下面的独立微基准 22.4 ms/帧一致）
  ⇒ **瓶颈是 gym-aloha `env.step()` 内建的 3×480×640 软件渲染，不是 π₀.₅**。
- **A2 自己的渲染微基准**（`render_throughput_a2.json`，五元标注 = `egl` / mujoco **3.8.1** / viperx **双臂** / 相机数 / 分辨率；
  同进程 3 重复，`loadavg 53.5–54.8`、`nr_throttled Δ0`）：3 相机 **224² = 14.83 控制步/秒**（67 ms/步，极差 1.55%）、
  3 相机 **480×640 = 14.91 控制步/秒**（极差 5.63%）、单相机 224² = **34.58 帧/秒**（29 ms/帧）。
  ⇒ **分辨率不是杠杆**（224² 与 480×640 无单调差异），**独立复现了 D §12.6-2 在另一套 (venv, mujoco, 模型) 上的同一结论**；
  两套数字**不互相搬用**（口径各自标注）。
- **实测的吞吐杠杆（64×，仅限"固定 ctrl"路径）**：同一 seed、同样 300 控制步，
  走 `env.step()` = **23.80 / 23.92 s**，走直接 `physics.step()`（10 子步/控制步、不渲染）= **0.37 / 0.24 s**，
  且两条路径的最小距离**逐位相同** ⇒ 渲染 ≈ **78 ms/控制步**（`loadavg 56`）。
  **要把它用到策略评测上，必须自己复刻 `before_step` 的 14→16 维动作映射（`sim.py:38-55`，约 10 行）**——
  **本轮未做、未测**，只登记为机会，**不主张收益数字**（不得写成"策略评测可以快 64 倍"）。
- 负载：π₀.₅ 臂 `nr_throttled` Δ23、`loadavg` 39–54；随机臂 Δ216（ep16/17 单局 Δ95/76，**外部负载尖峰**）⇒ 两臂墙钟几乎相同（578 vs 576 s）
  也正说明**都是 env-bound**，随机臂并没有因为"不算模型"而更快。

### 7.7 为什么 **`0/20` 不能**读成 π₀.₅ 的能力（三个已量化的混淆因子；**结论行见 §7.0**）

1. **槽位映射是假设**（`contract.json` q2 = `unknown`）：`model_out[0:14] → action[0:14]` 标 `assumed_from_convention`；
   §7.3 的左右不对称正是"排列错了会产生的形态"。
2. **没有归一化统计量**（q3 = `unknown`，ckpt 的 normalizer `features={}`）：
   - **state 侧**：12/12 手臂关节 `ctrlrange` 超出 `[-1,1]`、起手位姿 **2/14 维已越界**（§4.3）⇒ 静默贴端点 bin；
   - **action 侧**：实测 `raw_absmax = 1.2786`，当作绝对关节角后**平均只覆盖各关节行程的 57%**
     （waist / forearm_roll / wrist_rotate 仅 **40.7%**，shoulder 81.6%，elbow 75.9%，wrist_angle 62.4%；
     逐关节算术见 `approach_baseline.json → reachable_envelope[summary_pi05]`）；裁剪率 **0.374%**。
   - ⇒ 在这个配置下「**够不到方块**」是**可预期的结果**，不是"模型坏了"，也不能反推能力。
3. **任务串是自由参数**（env 无语言通道）：本轮已核验与场景同向（§7.1），但**π₀.₅ base 训练时的措辞 = `unknown`**。

### 7.8 本节专属的"不得声称"

- **不得**把 `0/20`（无 normalizer stats、state 通道饱和：waist 仅 0.3183 可表示）写成「π₀.₅ zero-shot 能力 = 0」——§7.7 三个混淆因子一个都没消。
- **不得**把随机臂更小的 `d_min` 写成「随机比 π₀.₅ 好」，也**不得**把它的 S2 / reward 2 写成「抬起了方块」（弹射，`max_hold_run=0`）。
- **不得**把 64× 写成「策略评测可以快 64 倍」（那是固定 ctrl 的零假设路径，未复刻 `before_step`）。
- **不得**把 `env_step_fps` 与 `loop_fps` 混用，也**不得**把本环境成功率/时延外推到 Piper / Cobot Magic
  （产物已带 `morphology="aloha_bimanual_14d"`；D §11.2）。
- **不得**写「示范数据不可得」——本阶段的示范来源见 **B2 §10**（D §11.4）。

### 7.9 G3 产物补强（应 D §12.11-3 / -4 / -9，**全部 CPU-only、未跑任何 policy**）

| 产物 | 回答 D 的哪一条 | 关键内容 |
|---|---|---|
| `weights_linkage.json` | §12.11-3（两份产物之间没有链接，D 差点把 `0/20` 误判成"权重没加载"） | 把 G2 的逐张量校验**摘要 + sha256 指纹**放进 G3 目录：`verdict=all_bitwise_equal`、**812/812 bitwise**、**0 个模型键未被 ckpt 覆盖**、tied 对 `same_storage_data_ptr=true`、告警原文与"为什么良性"、被链接文件的 `sha256=18d9149a…`；**并写死规则**：不许把 warning 读成"没加载"，也不许把"没报错"读成"加载了" |
| `render_selfcert.json` | §12.11-4（后端由使用方在自己 venv 内自证）+ §12.11-9（亮度/直方图） | 五元标注 `(egl, mujoco 3.8.1, viperx 双臂, 3 相机, 224²)`；PNG 几何与 `raw_len=150752 = 224×224×3 + 224 行 filter 字节`（**精确相等**）；三帧互异（`changed_pixel_frac` 13.36% / 11.83%，`identical=false`）；**逐相机**亮度 + 16-bin 直方图（base mean 36.33 / p50 **0** / std 45.08；left_wrist 76.70；right_wrist 77.69） |
| `red_cube_visibility.json` | §12.11-9 的**替代判据**（同视角参照数据集本机没有） | base 相机 **20/20 seed 可见红方块**，像素质心与**真值 box 位姿**的相关性 **r_x=+0.9938、r_y=−0.9991** ⇒ 相机朝向/光照**不是**信息缺失的原因。**判据 pass，但按 D 明令：不断言"图像正常"，也不断言"图像有问题"** |
| `render_throughput_a2.json` | §12.1（必须给出 A2 自己的数字） | 3 相机 224² **14.83 控制步/秒**、3 相机 480×640 **14.91**、单相机 224² **34.58 帧/秒**（同进程 3 重复，`loadavg 53.5–54.8`、`nr_throttled Δ0`）⇒ **分辨率不是杠杆**，独立复现 D §12.6-2 |
| `gripper_1d_to_2finger.json` | §12.11-8（1 维夹爪指令怎么变成两个指关节） | **指令层镜像 `[+g,−g]`**，模型层 **0 处 `<equality>`/`tendon`**；`OPEN=0.058`/`CLOSE=0.01844` m；`frictionloss=30` ⇒ **commanded≠observed**；归一化端点**落在声明限位之外** ⇒ 可达开口 **44.8–113.9 mm**，"全闭"不可达 |
| `ctrl_hz_alignment_a2.json` | §12.10 / §12.11-6（频率锚定 30 Hz） | A2 环境实测三元组 **(0.002, 10, 50.0 Hz) ⇒ 不在 QC [29,31]**；30.0 Hz 的整数解 = **(1/480, 16, 30.0 Hz)**；**只改 DT 不改 timestep ⇒ 只能得 29.41 或 31.25 Hz**；hold 零假设动力学 A/B（同 6 s 仿真）差 ≤2.5 mm；三案对 chunk 时间尺度的影响 + A2 推荐 **丙**（**D 裁**） |
| `ckpt_readonly_reverification.json` | §12.8 第 1 项（要"原始 ckpt 只读未改"的 sha256 对照） | 20:18:01 重算 **7/7 文件 sha256 与尺寸逐项等于** G1 的 17:50:53 receipt（`model.safetensors = 0eb11ca9…59b0f`，14,467,165,872 B），safetensors header 与 commit sha 也相同 ⇒ `PASS`、`failures=[]` |

---

## 8. 偏离、待裁与待办

| # | 事项 | A2 的做法 | 归谁 |
|---|---|---|---|
| 1 | **ckpt 要 lerobot git main，D 指定 0.4.4** | 兼容目录 `pi05_base_compat_lerobot044/`（大文件软链回原 ckpt，只删两个 **`enabled=false`** 的 processor 步骤）。等价性证据：lerobot main `src/lerobot/processor/relative_action_processor.py`（blob sha `3405402904cf15ca18227b3a3fe006d7936f9d53`）`:154` 与 `:213` 均为 `if not self.enabled: return transition` ⇒ **恒等映射**；diff 见 `compat_dir_diffs.patch`（**只有**被删的两块）。shim **自带牙**：只允许删「registry 缺失 **且** `enabled` 明确 false」的步骤，其它一律**非零退出、不产出目录** | **D 裁**：甲=保留 0.4.4+兼容目录 / 乙=升级 lerobot（**断点变更**，需登记 + 重过 B2 闸 + 重核 torch 红线，且 G2/G3 要重跑） |
| 2 | **`transformers` 正式版加载不了 π₀.₅** | 装 lerobot `pi` extra（`pyproject.toml:138`）指定的 `fix/lerobot_openpi` 分支，commit `dcddb970…`、版本 **4.53.3**、`siglip/check.py` 存在（173 B）。副作用只有 `tokenizers 0.22.2 → 0.21.4` | **D 需更正 §9.1**：「extras 里没有 `pi`」**不成立**——`pi` 在**源码 pyproject** 里有，只是**已发布 wheel 的 METADATA 剥掉了它**（git 直连 URL）。D 用 `importlib.metadata.requires()` 读 METADATA，**读法没错、结论要改** |
| 3 | `pi` extra 还要 `scipy<1.15`，本机 **1.17.1** | **不降**（最小变更）；实测加载/前向/评测路径未触发任何 scipy 问题 | D 追认 |
| 4 | lerobot **带依赖**安装（§9.2-1 写 `--no-deps`） | 带依赖 + torch 钉在同一次解析（`--no-deps` 会漏掉 lerobot 自己的核心依赖 ⇒ `import lerobot.policies.pi05` 直接 ImportError，正是 §9.2-4 警告的形态） | D 追认（18:0x 段已报） |
| 5 | `tokenizers 0.22.2 → 0.21.4` | 跟随补丁分支 | D 备案 |
| 6 | `torchcodec` 装了但 import 不了（缺 FFmpeg） | 记为**既存缺口**、不修（基线 venv 同状况） | D / B2（接视频帧则必修） |
| 7 | C §2.4 要求「A2 接真帧前实测重复帧触发面」 | **本轮未做**（G3 用的是仿真帧，未接真相机/真数据集帧）⇒ 明确**不主张一定发生**，登记为**待办**，接 ABC-130k 真帧前必须实测 | A2（下一轮）/ B2 |
| 8 | robosuite fps 口径分歧（8.5 vs 133–143 fps，~16×） | 两个数字**未并列引用** | **D 裁** |
| 9 | ABC-130k 是否由 Piper 采集（§10.1 的 `pending_user`） | 裁定 41.3 已确证 **ABC-130k = YAM，不是 Piper** ⇒ 该列按 ③ 处理，**第二列数值不搬进第三列** | 已由 D 裁定 |
| 10 🆕 | **gym-aloha 的 dense reward 可被"弹射"刷分**：`reward 2` = 右夹爪**单指**触碰 + 方块不接触桌面，**不要求持稳、不要求方块留在工作区**（`tasks/sim.py:125-149`）。随机臂实测拿到 **2.0**，而该局方块终点在 `(−68.69, +71.16, −134.76) m`、另一局 `box_z_max = 27.96 m`（§7.4） | 本轮**不把 env reward 当 shaping**：成功只认 `reward==4`/`is_success`，另加自建的**持续 ≥10 步** `grasp_truth`（它把这 5 个假抬起**全部拦掉**，`max_hold_run=0`） | **D / B2**（若将来要用 env reward 做奖励整形，**必须先加 workspace + 持稳 guard**） |
| 11 🆕 | **吞吐瓶颈不在模型**：G3 均局 28.90 s 里 **87% 是 `env.step()` 内建的 3×480×640 软渲染**（实测 ≈78 ms/控制步）；本轮实测**固定 ctrl 路径**可绕过（快/慢路径最小距离 Δ=**0.0000 m**，64× 更快） | **本轮不改评测脚本**（绕过渲染需自己复刻 `before_step` 的 14→16 维映射，未做未测 ⇒ **不主张收益数字**） | **D**（要不要在下一轮把它做成正式加速项）/ B2（批量评测时需要） |
| 12 🆕 | **红线「transformers `>=4.57.1`」与「π₀.₅ 可加载」互斥**：`modeling_pi05.py:576-584` 的闸是 `siglip.check.check_whether_transformers_replace_is_installed_correctly()`，而该函数全文是 **`__version__ == "4.53.2" or == "4.53.3"`** 的硬白名单 ⇒ 4.57.6 实测 `ValueError`（§10.8）。**连带影响**：B2 的 `TRANSFORMERS_FLOOR = 4.57.1` 与 M3/M4 两颗牙会把 `pi05_sim` 判 **RED** ⇒ π₀.₅ 线永远过不了闸 | A2 选 **(甲)**：4.53.3 可用，**申请红线改判成语义判据**（①`siglip.check` 可导入 ②函数返回 True ③版本 ∈{4.53.2,4.53.3} ④**钉 commit `dcddb970…`**）；**A2 不改 B2 的文件，只报** | **D 裁**（红线改判）+ **B2**（闸的下界与 M3/M4 同步改） |
| 13 🆕 | **用户「先只渲染单臂」与 D §11.2「gym-aloha 双臂是形态一致首选」相撞**：`AlohaTransferCube-v0` 本质双臂（14 维 = 2×(6+1)、任务就是两臂交接），**无法只渲染单臂而保持形态一致**（§10.1）。G3 在 §12 到达前已跑完（19:24–19:45 vs §12 的 19:5x） | A2 按 §11.2 继续用 gym-aloha 双臂，并把冲突**显式登记**、**不自决**；若停用令也覆盖 gym-aloha，A2 立即停并改走 state 档/单臂任务（**会牺牲形态一致性**，且丙案仍不自选） | **D 裁**（必要时回报用户） |
| 14 🆕 | **gym-aloha 的 dense reward 与"全闭"都不可照搬**：夹爪归一化端点（0.01844 / 0.058 m）**落在声明限位（0.021 / 0.057）之外** ⇒ **全闭不可达**、可达开口 **44.8–113.9 mm**；`frictionloss=30` ⇒ **commanded ≠ observed**（Δ≈4 mm）（§10.3） | 已写进契约表①列（标 `A2-measured`）；**Piper 侧数值一律不搬**（行程三值并列，裁定 43） | **D 备案** / B2（做准入闸时按 commanded/observed 分列断言） |

## 9. 产物索引与复现

```
runs/vla/a2_env_pi05_sim_20260929/     G0：resolve_dryrun.txt（三次解析）、stage2c_install.log、stage3_install.log、
                                        requirements.lock.txt（122 pin）、env_manifest.json（9/9）、weights_receipt.json、
                                        manifest_run1_probe_false_red/、manifest_run2_dist_drift_false_red/（两版留档，不改写）
runs/vla/a2_g05_vision_precheck_20260929/  G0.5：三通道 × 分辨率/相机数网格 + samples/ + round1_liveness_probe_bug/（留档）
runs/vla/a2_pi05_contract_20260929/    G2：contract.json、load_verification.json、compat_dir_report.json、compat_dir_diffs.patch、
                                        state_channel_saturation_analysis.json、pi05_base_compat_lerobot044/、
                                        probe_run1_transformers_blocker.log、probe_run2_processor_registry_blocker.log、
                                        run3_xml_default_pose_defect/（三版留档，不改写）
runs/vla/a2_pi05_zeroshot_20260929/    G3：summary_pi05.json、summary_random.json、run_pi05.log、run_random.log、
                                        approach_baseline.json（hold 零假设 + 净接近 + 可达包络算术）、
                                        approach_baseline_run1_pi05_only_missing_throttle_delta.json（第一版留档：
                                          只缺 nr_throttled 计数（cgroup v1 路径没兜住），hold 数字与终版**逐位相同**，不改写）、
                                        approach_baseline_run2.log、frames_pi05/、frames_random/（随机臂不存图，空目录）
              （§12 后补的六份，全部 CPU-only、`policy_executed=false`）
                                        weights_linkage.json（§12.11-3）、render_selfcert.json（§12.11-4/-9）、
                                        red_cube_visibility.json（§12.11-9 替代判据，verdict=pass）、
                                        render_throughput_a2.json（§12.1）、gripper_1d_to_2finger.json（§12.11-8）、
                                        ctrl_hz_alignment_a2.json（§12.5/§12.10，含 latency_budget_claim）、
                                        selfcert_*.png（逐相机自证图）、post_g3_diagnostics.log
runs/vla/a2_pi05_contract_20260929/ckpt_readonly_reverification.json
                                       §12.8 第 1 项要的「原始 ckpt 只读未改」sha256 对照（7/7 逐项等于 G1 receipt）
scripts/a2_*.py                        探针与工具（全部带 a2_ 前缀）；G3 相关三支：
                                        a2_pi05_zeroshot_eval.py（两臂评测，chunk≠n_action_steps 即抛错）、
                                        a2_g3_approach_baseline.py（hold 零假设，快/慢路径超差即**响亮失败、不产出报告**）、
                                        a2_post_g3_diagnostics.py（§12 的六份证据，分 section 可单跑）
```

复现（G2）：
```bash
P=/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist
MUJOCO_GL=egl HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /root/venvs/pi05_sim/bin/python -u \
  scripts/a2_pi05_contract_probe.py \
  --weights-dir runs/vla/a2_pi05_contract_20260929/pi05_base_compat_lerobot044 \
  --tokenizer-dir $P/hf-cache/modelscope/google/paligemma-3b-pt-224 \
  --out runs/vla/a2_pi05_contract_20260929/contract.json
```

复现（G3，两臂 + 零假设；**零假设与随机臂全程 CPU-only，不占卡**）：
```bash
P=/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist
OUT=runs/vla/a2_pi05_zeroshot_20260929
# 臂 A：π₀.₅ zero-shot（GPU，峰值 14.1 GB；实测总墙钟 578 s）
MUJOCO_GL=egl HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=4 \
  /root/venvs/pi05_sim/bin/python -u scripts/a2_pi05_zeroshot_eval.py \
  --policy pi05 --n-episodes 20 --seed0 1000 --save-frames-episodes 0 \
  --weights-dir runs/vla/a2_pi05_contract_20260929/pi05_base_compat_lerobot044 \
  --tokenizer-dir $P/hf-cache/modelscope/google/paligemma-3b-pt-224 --out-dir $OUT
# 臂 B：随机基线（同 seed，CPU-only；实测总墙钟 576 s）
CUDA_VISIBLE_DEVICES="" MUJOCO_GL=egl OMP_NUM_THREADS=4 \
  /root/venvs/pi05_sim/bin/python -u scripts/a2_pi05_zeroshot_eval.py \
  --policy random --n-episodes 20 --seed0 1000 --out-dir $OUT
# 零假设：起手位姿保持（CPU-only，实测 52.6 s；含快/慢路径等价校验）
CUDA_VISIBLE_DEVICES="" MUJOCO_GL=egl OMP_NUM_THREADS=2 \
  /root/venvs/pi05_sim/bin/python -u scripts/a2_g3_approach_baseline.py \
  --n 20 --seed0 1000 --validate-n 2 --summary $OUT/summary_pi05.json \
  --summary $OUT/summary_random.json --out $OUT/approach_baseline.json
```

---

## 10. 对 D §12（12.1–12.11，19:5x 下达）的**逐条回答**

### 10.0 时序声明（避免"没看到指令"的误会）

- **§12 到达 = 19:5x**；G3 两臂 **19:24:40 起跑、19:45:21 结束**（`a2_pi05_zeroshot_full.log` 首末行有 UTC 时间戳）
  ⇒ **G3 是在 §12 之前就已启动并跑完的**，不是无视 §12.7 的"先只渲染单臂"。
- **§12 之后做的一切**（§7.3 零假设、§7.9 六份产物、§10.9 的红线取证、§10.10 的频率分析）
  **全程 CPU-only（`CUDA_VISIBLE_DEVICES=""`）、未跑任何 policy** ⇒ 遵守裁定 46.6（拿到 stats 前不再做能力评测）。
- **GPU**：占用窗口 **19:24–19:35**（仅臂 A），峰值 **14,105.2 MiB**；19:35 起 `nvidia-smi` **0 MiB / 0% / 无 compute app**，
  **已在 `daily_report.md` 销账**。

### 10.1 §12.1 渲染口径 —— A2 自己的数字已给（未重测后端选型）

- **五元标注**：`(MUJOCO_GL=egl, mujoco 3.8.1, viperx300s 双臂, 相机数, 分辨率)`，venv `pi05_sim`。
- **数字**（`render_throughput_a2.json`，同进程 3 重复，`loadavg 53.5–54.8`、`nr_throttled Δ0`）：
  3 相机 **224² = 14.83 控制步/秒**（67 ms/步，极差 1.55%）、3 相机 **480×640 = 14.91**（极差 5.63%）、
  单相机 224² = **34.58 帧/秒**（29 ms/帧）。
- **协议差异自陈**：A2 是**同进程 3 重复**，D 的基准是**独立进程 3 重复** ⇒ 两套数字**不互相搬用**（D §12.11-4 的边界保留，A2 照办）。
- **一处独立复现**：224² 与 480×640 的 ms/图**无单调关系** ⇒ 在**另一套 (venv, mujoco 版本, 模型)** 上复现了 D §12.6-2 的"分辨率不是杠杆"。
- **⚠️ 一条冲突，请 D 裁（A2 不自决）**：用户指令「**先只渲染单臂**」与 D §11.2「**gym-aloha 双臂 14 维是形态一致首选**」在 A2 这条线上直接相撞——
  `AlohaTransferCube-v0` **本质是双臂**（14 维 = 2×(6+1)、任务就是两臂交接），**无法"只渲染单臂"而保持形态一致**。
  A2 的理解是：§12.7 的停用令针对**D 自己用 MjSpec 拼的 Piper 双臂**（`arms=2` 的 5 份 JSON），
  而 §11.2 的 gym-aloha 双臂仍是首选 ⇒ 所以 G3 与本轮探针都用了 gym-aloha 双臂。
  **若 D 认为停用令也覆盖 gym-aloha，请明示**：A2 会立即停，并改走 (a) state 档或 (b) 单臂任务，
  但两者都**牺牲形态一致性**（§11.2 选 gym-aloha 的唯一理由），且**丙案（换节点/后置形态验证）A2 仍不自选**。

### 10.2 §12.2 相机注入（Piper `ncam=0`）—— **本轮未做**，方案与前置条件如下

- **状态**：**未实施**（Piper 模型侧是下一个工作包；本轮时间用在 §12.9/§12.10/§12.11 三条 P0 上）。
- **方案（照 D 的已验证路径）**：`mujoco.MjSpec.from_file(piper_description.xml)` → `body.add_camera()` →
  设 `cam.pos / cam.quat / cam.fovy`（**不用 `zaxis`，MjSpec 没有这个属性**）；命名 **`cam_high`**（top）、**`cam_wrist`**（挂 `link6`），
  需要三相机再加 `cam_front`；产物里写清命名 + 内外参来源，YAM 内参（fx 431.88 / fy 431.38 / cx 324.26 / cy 240.97 ⇒ 640×480）
  **标 `reference_not_calibration`**，不得写成 Piper 标定值。
- **前置**：① 单臂（用户指令）；② 后端由 A2 在目标 venv 内**自证并记录**（§12.11-4 修订后不再由 D 钉死）；
  ③ 注入后必须附**出图非黑证据**（尺寸 / `raw_len` vs `expected_len` / byte_std / 帧互异），照 `render_selfcert.json` 的格式。
- **不做**：不对已 `from_file` 的 spec 清空 `geom.meshname` 再改 `type=BOX`（§12.6-1，SIGABRT）；低面数对照若要做，**另建独立 XML** 且先做外观 A/B 报 D。

### 10.3 §12.3 夹爪两指耦合 —— **参照实现已查清**（本轮实测交付；Piper 侧实施待做）

- **gym-aloha 的答案：指令层镜像（command-layer mirror），不是等式约束、不是 tendon、不是 URDF mimic。**
  `tasks/sim.py:38-55`：`unnormalize_puppet_gripper_position(g) = g·(OPEN−CLOSE)+CLOSE`（**OPEN=0.058 / CLOSE=0.01844 m**），
  然后 `env_action = [left_arm(6), +g, −g, right_arm(6), +g, −g]` ⇒ **两指同号幅度、反号方向**。
  `bimanual_viperx_transfer_cube.xml` 里 **`<equality>`/`tendon` = 0 处**（只有 `end_effector_*` 变体各有 2 处）⇒ **模型层确实没有耦合**。
- **数值验证**（`gripper_1d_to_2finger.json`，每个归一化值 step 50 次让执行器收敛）：
  | 归一化指令 | 反解 ctrl (m) | 实测指 qpos (m) | 开口 (mm) | 镜像成立 |
  |---|---|---|---|---|
  | 0.00 | 0.01844 | 0.022405 | 44.80 | ✓ |
  | 0.25 | 0.02833 | 0.028329 | 56.65 | ✓ |
  | 0.50 | 0.03822 | 0.038209 | 76.41 | ✓ |
  | 1.00 | 0.05800 | 0.056970 | 113.93 | ✓ |
- **两条要写进 Piper 侧设计的硬事实**：
  1. **归一化端点落在声明限位之外**：cmd 0 → 0.01844 m **< ctrlrange/joint 下限 0.021**；cmd 1 → 0.058 m **> 上限 0.057**
     ⇒ 实测可达开口 **44.8–113.9 mm**，**"全闭"不可达**。指关节 `frictionloss=30`（`damping=0`）是主因之一。
  2. **commanded ≠ observed**（cmd 0：0.01844 vs 0.0224 m，Δ≈4 mm）⇒ 与 D 在 ABC-130k(YAM) 上实测的
     `/left-arm-action` vs `/left-arm-state` **同一形态**。契约表里夹爪一栏**必须写明是 commanded 还是 observed**，两边不得互相当对方用。
- **Piper 侧建议（未实施）**：照抄"指令层镜像"最省事（不改模型、与 14 维指令契约天然对齐），
  代价是**忘记镜像就会静默错**（§12.3 说的硬缺口）；若要在模型层耦合则用 `<equality>`（joint 约束）。
  **无论选哪种都要写进产物**（§12.3 要求）。识别夹爪**按关节类型 `slide`/`prismatic`**，不要按名字关键字（`joint7`/`joint8` 名字里没有夹爪字样）。

### 10.4 §12.4 契约第三列三值并列 —— **已写进 §5**（9 处标 `D-measured`，含跨形态禁令）

- 夹爪行程 **URDF 50 mm / MJ joint 35 mm / MJ ctrl 47.5 mm 三值并列**，实机校准前**不选定**；
- 关节限位 **URDF vs MJ 不一致**（J6 差 **1.0456 rad** 最大，J1 0.45、J3 0.27、J4 0.087、J7/J8 0.015 m）⇒ 并列记录；
- DOF 口径 **模型级 8/臂（双臂 16）/ 指令级 7/臂（双臂 14，ALOHA 相容）**；
- **跨形态禁令**：YAM J3 = 正值区间 31.6~104.5 度，Piper J3 的 MJ 限位 = −2.967~0 rad（全负）⇒ ②列数值**只作分布形态参照**。

### 10.5 §12.5 推理延迟 —— **口径认领**（`ctrl_hz_alignment_a2.json → latency_budget_claim`）

| 项 | 值 | 口径 |
|---|---|---|
| 每 chunk 墙钟（G3 日志） | **0.523 s**（= 3.14 s ÷ 6 次/局） | **含** preprocess（3 路图像张量化 + state tokenizer）、`predict_action_chunk`（10 步去噪）、postprocess、前后各一次 `torch.cuda.synchronize()` |
| 首次预热 | **0.583 s**（ep00：3.5 s ÷ 6） | **不含**在上面那个 0.523 里（0.523 是 ep01–19 的均值口径） |
| G2 裸前向 | 稳态 **0.479 s** / 首帧 **1.378 s** | 不含 pre/post，`contract.json → six_questions.q6` |
| dtype | **fp32**（`param_dtypes=["torch.float32"]`） | **改 bf16 会单独报，不与本表混列** |
| 50 Hz 预算 | chunk 覆盖 **1.0 s**，推理占 **52%** | 每步硬预算 20 ms |
| **30 Hz 预算** | chunk 覆盖 **1.667 s**，推理占 **31%** | 每步硬预算 **33.3 ms** |
| **折算闭环控制步/秒** | **10.39**（`loop_fps`，含推理 + env 渲染；`loadavg 39–54`、`nr_throttled Δ23`） | **低于 30 Hz 也低于 50 Hz ⇒ 当前不是实时闭环**，是离线评测节奏；瓶颈是 env 内建 3×480×640 软渲染（≈78 ms/控制步），**不是推理** |

**认领结论**：D 的判定"**按 chunk 执行时实时闭环可行、按每步推理不可行**"，A2 **认可**；
但要补一句边界：**推理项只占 31%（30 Hz）不等于闭环就能到 30 Hz**——实测闭环 10.39 步/秒是被**渲染**卡住的，
所以要真做 30 Hz 实时闭环，**必须同时解决渲染成本**（§7.6 的杠杆：减相机数 / 降面数，后者需先做外观 A/B 报 D）。

### 10.6 §12.6 三个"不要做" —— 逐条确认

1. **mesh ablation**：A2 本轮**未做任何 mesh 改写**（未清空 `meshname`、未改 `type=BOX`）。
2. **降分辨率当提速**：**不采用**；A2 在自己的环境独立复现了"无单调关系"（224² 67 ms/步 vs 480×640 67 ms/步）。
3. **官方 `piper_mujoco_pid.py`**：**未使用**（依赖已弃用的 `mujoco_py`+`glfw`）；`piper_sdk`（CAN）**未装未测**，A2 **不假设可用**。

### 10.7 §12.8 我 6 项待裁的处置 —— 回应

- **第 1 项（兼容目录）⇒ 自证已补齐**：
  - **代码级恒等证据**：lerobot main `src/lerobot/processor/relative_action_processor.py`（blob sha `3405402904cf15ca18227b3a3fe006d7936f9d53`）
    `:154` 与 `:213` 均为 `if not self.enabled: return transition` ⇒ **`enabled=false` 时该步骤是恒等映射**（不是"读 config 就下结论"）；
  - **diff 范围**：`compat_dir_diffs.patch` **只含被删的两块**；造目录的脚本 `scripts/a2_make_pi05_compat_dir.py` **自带牙**
    （只允许删「registry 缺失 **且** `enabled` 明确 false」的步骤，其它一律非零退出、不产出目录）；
  - **原始 ckpt 只读未改的 sha256 对照（本轮新做）**：`ckpt_readonly_reverification.json`（**20:18:01**）与 G1 `weights_receipt.json`（**17:50:53**）
    **7/7 文件的 sha256 与尺寸逐项相同**，`model.safetensors = 0eb11ca9587678c1d2ef8cf32807c29f8ce53a2bfdfc1aa4a4c96f16fca59b0f`
    （14,467,165,872 B），safetensors header（812 张量、`__metadata__` 别名、dtype 直方图）与 HF commit sha `b211f3d4…` 也相同 ⇒ `PASS`、`failures=[]`。
- **第 6 项（robosuite fps 分歧）⇒ A2 侧口径完整给出**：
  - A2 的 **133–143 fps**：venv **`rlrobot`**、robosuite **1.5.2**、mujoco **3.9.0**、`MUJOCO_GL=egl`、任务 **`PickCube-v1`**、
    **64²×1 相机**、`steady_fps = 40 帧稳态 ÷ steady_s`（warmup 2）、**每控制步含 10 个物理子步**、
    **不含策略推理、不含视频写盘、不是整回合折算**；`loadavg 52.19`、整轮探针 `nr_throttled Δ5`；
    同轮 480×640×3 相机 = **117.1 fps**（robosuite 一次 step 渲染全部 camera_names ⇒ fps 已含 3 路成本）。
  - 旧数 **8.5 fps**（`daily_report.md:47`）：任务 **`PickPlaceCan`**、单相机 64²，**口径未记录**
    （是否含策略前向/反向、是否含回放缓冲与视频写盘、子步数、是否整回合折算 ⇒ **全部未知**）。
  - ⇒ 两者**环境不同、日期不同、口径一边缺失** ⇒ 按 D 的处置，**任一数字都不得单独引用**；A2 已把自己这侧口径写进产物，
    **请 D 让旧数的产出方补口径**（A2 不改他人产物）。
- **第 2/3/4/5 项**：追认收到；**torch 红线未动**（本轮 `torch.__version__ == 2.6.0+cu124` 逐字未变，未做任何解析/安装动作）。

### 10.8 §12.9 **必须先答** ⇒ 答案 **(甲)**：4.53.3 下 π₀.₅ 确实可用，**申请红线改判（由 D 裁）**

**判据不是版本号，是 lerobot 自己的 4 行代码。** `lerobot/policies/pi05/modeling_pi05.py:576-584`：

```python
msg = """An incorrect transformer version is used, please create an issue on https://github.com/huggingface/lerobot/issues"""
try:
    from transformers.models.siglip import check
    if not check.check_whether_transformers_replace_is_installed_correctly():
        raise ValueError(msg)
except ImportError:
    raise ValueError(msg) from None
```

而补丁分支里 `transformers/models/siglip/check.py` 的**全文**（173 B，本机实读）：

```python
import transformers

def check_whether_transformers_replace_is_installed_correctly():
    return transformers.__version__ == "4.53.2" or transformers.__version__ == "4.53.3"
```

⇒ **π₀.₅ 的构造器要求 `transformers.__version__ ∈ {4.53.2, 4.53.3}` 的硬白名单**，
而红线要求 **`>=4.57.1`** ⇒ **两者互斥**（不是"可能冲突"，是 4 行代码证明的互斥）。
实测两侧都验过：
- **4.57.6（PyPI 正式版，`transformers-dep` extra 解析结果）⇒ 加载失败**：`probe_run1_transformers_blocker.log` 末尾
  `modeling_pi05.py:584 → ValueError: An incorrect transformer version is used`；且 4.57.6 的 `models/siglip/` 里**没有 `check.py`**（目录清单已核，`resolve_dryrun.txt:387`）。
- **4.53.3（lerobot `pi` extra 指定的 `fix/lerobot_openpi` 分支）⇒ 可用**，且**活体探针当场为真**：
  `transformers.__version__ = 4.53.3`、`siglip.check` 可导入、`check_whether_transformers_replace_is_installed_correctly() == True`；
  `direct_url.json` = `{"url": "https://github.com/huggingface/transformers.git", "vcs_info": {"commit_id": "dcddb970176382c0fcf4521b0c0e6fc15894dfe0", "requested_revision": "fix/lerobot_openpi"}}`；
  在这个版本上完成了 **812/812 bitwise 加载校验 + G2 前向 + G3 40 局评测**。

**A2 申请的红线改判文本（D 裁，A2 不改）**：把「transformers 走 extra `transformers-dep` 且 `>=4.57.1`」换成**语义判据**——
① `from transformers.models.siglip import check` 可导入；② `check.check_whether_transformers_replace_is_installed_correctly() is True`；
③ `transformers.__version__ ∈ {4.53.2, 4.53.3}`；④ **`direct_url.json.vcs_info.commit_id == dcddb970…`（必须钉 commit）**。
**为什么④不可省**：白名单只看版本号字符串，**任何自称 4.53.3 的构建都能过** ⇒ 只钉版本等于没钉。

**对 B2 闸的直接影响（A2 只报不改）**：`scripts/b2_env_admission_pi05.py:185 TRANSFORMERS_FLOOR = "4.57.1"`、
`:2675 tf_lock = tf_live = "4.57.1"`，以及 M3（`4.30.0 < 4.57.1` 必须红）、M4（"已装 4.57.1 但产物没写"必须红）三颗牙
都以 **4.57.1** 为基准 ⇒ **按现行闸，A2 的 `pi05_sim` 会被 V-pi05-1 判 RED，π₀.₅ 线永远过不了闸**。
红线改判后，**下界与这三颗牙要同步改**（改法建议：把牙从"版本下界"换成上面①–④的语义判据，
并把 M3 的期望值改成"装了 4.57.x ⇒ 必须红，因为 π₀.₅ 构造器会 ValueError"）。

**版本口径没有分叉（D 点名的第二问）**：
| 环境 | lerobot 实装 | transformers 实装 | 来源 |
|---|---|---|---|
| `pi05_sim`（A2 本轮） | **0.4.4** | **4.53.3** @ `dcddb970` | `importlib.metadata` 当场实测 |
| `lerobot_act`（已验收基线） | **0.4.4** | **未安装**（`PackageNotFoundError`） | 同上 |
| `lerobot_eval`（已验收基线） | **0.4.4** | **未安装**（`PackageNotFoundError`） | 同上 |
| B2 脚本里出现的 `0.4.5` | — | — | **只在 `M1_lerobot_drift` 变异分支**（`b2_env_admission_pi05.py:2682`）⇒ 是**注入用的假漂移**，不是任何环境的实装值 |

⇒ **三方一致，无分叉**；`LEROBOT_ANCHOR = "0.4.4"` 与 A2 实装相同。
**顺带一条与红线直接相关的事实**：两套已验收 venv **根本没有 transformers** ⇒ 「`>=4.57.1`」这条红线
**在任何已验收环境里都从未被满足过**；它是从 lerobot 0.4.4 wheel METADATA 的
`Requires-Dist: transformers<5.0.0,>=4.57.1; extra == "transformers-dep"`（本机实读 METADATA:52）读来的**计划书值**，
而 π₀.₅ 真正的要求在 **`pi` extra**（源码 `pyproject.toml:138`，**wheel METADATA 里被剥掉了**，因为是 git 直连 URL）。

**（丙）不需要**：两份产物来自**同一个环境**，环境指纹见 §1（`env_manifest.json` V1–V9 = 9/9、
`requirements.lock.txt` 122 pin、`sha256=4d849aca20285c8e908c52533a4332778cf360334cc3d526e4dbccdc304d01cc`）。

### 10.9 §12.10 / §12.11-6 频率对齐 —— **三案已分析，A2 推荐丙，请 D 裁（不静默选）**

- **A2 环境实测三元组**：`(timestep=0.002, decimation=10, 50.0 Hz)` ⇒ **不在 QC [29.0, 31.0] 内**（`ctrl_hz_alignment_a2.json → as_is`）。
- **30.0 Hz 的整数解**：`(timestep=1/480=0.0020833, decimation=16, 30.0 Hz)`，`integer_decimation=true`。
- **陷阱（必须先说）**：**只改 `DT` 不改物理 timestep ⇒ decimation 只能取整**：
  取 17 ⇒ **29.41 Hz**；取 16 ⇒ **31.25 Hz**，而 31.25 Hz 正是裁定 45 明令**不得当契约值**的那个数
  ⇒ **30.0 Hz 必须同时改物理 timestep**（`naive_pitfall` 已写进产物）。
- **动力学 A/B（hold 零假设，同为 6 s 仿真时长）**：`box_z_end` **完全相同**（0.0200 m）、
  `min_dist` 差 **1.6 / 2.5 mm**、`qpos` 偏差差 **5e-6 rad** ⇒ 改 timestep **不会把场景搞崩**。
  **边界**：这只是 hold 零假设的沉降/保持 A/B，**不是策略行为的 A/B**（本轮不跑 policy，裁定 46.6）。

| 案 | 做法 | chunk（50 步）覆盖时长 | 对时间尺度的影响 | 代价/风险 | A2 看法 |
|---|---|---|---|---|---|
| **甲** | 示范 30 → 50 Hz 重采样，仿真保持 50 Hz | **1.000 s** | 模型在 50 Hz 语义下微调 ⇒ 与仿真一致 | 50/29.76 = **1.68 非整数比** ⇒ 必须插值，**造出数据里不存在的帧与动作**；且把部署频率推到 50 Hz，而**实机能否吃 50 Hz 指令 = `null`** | **不推荐** |
| **乙** | 示范保持 30 Hz，chunk 时长按 30/50 缩放 | **1.667 s** | 相邻动作间隔变成 1/30 s ⇒ **同样的动作增量意味着 0.6× 速度** | 不重新微调就会整体变慢/变糊（正是 D §12.10 说的"能接近但抓不准"）；重采样口径要写进 `representation_version` | **次选**（仅在 30 Hz 仿真改不动时用，且必须配合微调） |
| **丙** | 仿真改 30.0 Hz（`timestep=1/480` + decim 16），示范保持 30 Hz | **1.667 s** | 仿真 / 示范 / 契约**三者同频** ⇒ 时间尺度自洽 | D 已实测吞吐代价 **+0.5%**（Piper 模型，osmesa）；本环境需改 XML timestep（本节已做 hold A/B）；与 ALOHA 生态的 50 Hz 口径**不再同频** ⇒ 跨论文数字不可并列 | **推荐** |

- **推荐丙的理由**：与**裁定 45 的 30 Hz 锚点**、**ABC-130k 实测 29.76 Hz**、**团队 QC [29,31]** 全部一致；
  甲要**造数据**并把契约押在**实机未知的 50 Hz** 上；乙若不重新微调会引入 0.6× 的速度偏差。
- **接线本轮未实施**（等裁定，避免白改一遍）：需要 ① 覆写 `gym_aloha.env.DT = 1/30`（`env.py:134` 用 `control_timestep=DT`），
  ② 让 XML 带 `<option timestep="1/480"/>` —— **不改 site-packages**：把 assets 复制到 A2 产物目录后改副本，或重建 dm_control `Environment`。
- **不得沿用**：第三列（Piper/Cobot Magic）的**实际控制频率仍是 `null`** ⇒ 无论选哪案，**实机对接时必须用实机数据重新锚定**。

### 10.10 §12.11 逐条

| # | D 的要求 | A2 的落实 |
|---|---|---|
| (1) | `0/20` 推进度低于随机基线，**必须先归因** | 已归因四处：§7.3（hold 零假设 ⇒ **不是接线死了**：左臂 19/20 seed 净接近中位 +0.104 m）、§7.4（随机臂的 S2 与 reward 2 是**弹射**，`max_hold_run=0`，方块飞到 −134.76 m ⇒ 那不是任务推进）、§7.7（三个已量化混淆因子）、`red_cube_visibility.json`（**相机朝向/光照不是信息缺失的原因**：20/20 可见、r=+0.994/−0.999）。**正确读法**：两臂都远不足以完成任务，但"随机更靠前"是**暴力扫掠 + 仿真被打爆**的产物，**不可比** |
| (2) | 结论行必须写"不构成能力证据"，`0/20` 同句带 normalizer/饱和 | **已写死在 §7.0 的引用块**（结论行），并在 §0 摘要表、§7.2 表格单元、§7.8"不得声称"里**逐处同句**带上「无 normalizer stats，state 通道饱和：waist 仅 0.3183 可表示」 |
| (3) | tied 检查写进 zero-shot 产物 | `weights_linkage.json`（§7.9 第一行）：含 `load_verification.json` 的 **sha256 指纹**、812/812 bitwise、0 未覆盖键、tied 对 `same_storage_data_ptr=true`、告警原文与良性理由、以及"两边都不许反推"的规则 |
| (4) | 渲染后端自证并记录 | `render_selfcert.json`：五元标注 + PNG 几何 + `raw_len=150752` 与 `expected_len` **精确相等** + byte_std + 三帧互异（**与 D 独立解析的结论一致**） |
| (5) | 认领延迟口径 | §10.5（含/不含逐项写明；**认可** D 的"按 chunk 可行、按每步不可行"，并补了"渲染才是闭环瓶颈"这条边界） |
| (6) | 频率重采样方案报 D 裁 | §10.9（三案 + chunk 时长 + A2 推荐丙 + 未实施接线） |
| (7) | 拿到 stats 前不得用 zero-shot 成功率做路线判断 | **收到并执行**：本轮 §12 之后的所有探针**未跑任何 policy**（产物里 `policy_executed=false`）；A2 的有效工作已按 D 的清单交付（契约三列 §5、延迟口径 §10.5、渲染自证、频率对齐提案）；**接口适配**待 §12.2/§12.3 的 Piper 侧实施 |
| (8) | `env_action_space` 声明/语义不一致进契约表第一列；查清 1 维夹爪 → 2 指 | 已在 §5（①列 + `A2-measured` 标注）与 `summary_*.json → env_action_space`；夹爪机制见 §10.3（**指令层镜像**，附数值验证表） |
| (9) | 附同视角亮度/直方图对比；**给出对比前不许断言图像正常或有问题** | 逐相机亮度 + 16-bin 直方图已附（`render_selfcert.json`）。**同视角参照数据集本机没有**：ABC-130k(YAM) 帧未下载（且机型/视角不同），D 的 Piper 渲染是**另一模型另一套相机** ⇒ 并列会踩"跨口径不得并列"（裁定 31.3/33.4/36.4）。改用**无需参照**的判据（红方块可见性 + 质心随真值位姿 r=0.994/−0.999，20/20 seed，`verdict=pass`）。**A2 不断言图像正常、也不断言图像有问题**。**若 D 仍要同视角亮度对照，需授权下载 ABC-130k 抽样帧**（新下载，A2 单线执行） |

**关于 D 的 `mean≈9.3/255`、非零字节 7%（A2 复现不出，请 D 指认）**：
A2 落盘的 **28 份 PNG** 在**六种读法**下都得不到 9.3——
像素均值（gym-aloha base **36.33–50.77**、robosuite **212.6–219.5**）、灰度 `L` 均值（36.31–39.75）、
逐通道均值（R 36.66 / G 36.17 / B 36.17）、像素非零占比（**0.415–1.000**）、
**PNG 文件字节**非零占比（**0.9961**）、以及帧间差分（`mean|Δ| = 10.25 / 10.28`）。
**唯一落在 9.3 附近的量是"帧间平均绝对差 10.25"** ⇒ **一个假设（不是结论）**：若 D 测的是**差分图**，
"偏暗"就会是**把运动量读成亮度**。请 D 指认所测**文件与相机**，A2 会按同一口径复算；
在指认前，A2 只报**自己的实测表**，不对 D 的数字下任何判断。
**另附一条与"偏暗"相关的实测事实（不带评价）**：base（`angle`）相机的 **p50 = 0**、非零像素占比 **0.465**
⇒ 画面约 **53.5% 是纯黑背景**（场景本身暗、桌面外无背景几何）；两个腕部相机 **mean 76.7 / 77.7、p50 = 61**，明显更亮。

### 10.11 本轮**未做**的事（明确登记，不含糊）

1. **§12.2 Piper 相机注入**、**§12.3 Piper 侧两指耦合实施** —— 未做（方案与前置条件已给，等 D 排期；两者建议同一个工作包一起做）。
2. **30 Hz 接线** —— 未做（等 §10.9 的裁定）。
3. **同视角亮度对照** —— 未做（本机无参照数据；需 D 授权下载）。
4. **C §2.4 的"重复帧触发面"实测** —— 仍未做（接 ABC-130k 真帧前必须做；**A2 不主张它一定发生**）。
5. **`torchcodec`/FFmpeg** —— 未修（既存缺口，基线 venv 同状况；B2 若走 mp4 数据集则必修）。

---

## 11. 本轮增补（**21:0x**）：裁定 48.6 / 49.5 / 48.5 三条闭合 + 裁定 46 **第 5 项完成** + **A2 三处自纠**

> **本节与 §1–§10 的关系**：§1–§10 **原文不动**（house rule：已落盘产物不重写）。
> 本节里凡与 §10.11 冲突的，**以本节为准并显式点名作废**（见 §11.7）。
> 本轮**全程 CPU-only**：未占 GPU、未渲染新帧、未跑任何 policy（裁定 46.6）。

### 11.0 一句话

裁定 48.6 只剩的那一条**已闭合并做成机器承载**（`env_manifest.json` 重出，**10/10 全绿**，含裁定 48 的新红线 V10 + **6/6 变异自检**）；
裁定 46 的第 5 项（同视角亮度对比）**已完成**，且**顺带否证了「观测近乎全黑」这个假说的测量基础**（D 引的 `9.3/7%` 是 **PNG 滤波残差域**，不是像素域）；
裁定 49.5 的 `mixed` 顶层**已按 sidecar 闭合**（receipt **未重写**，sha256 前后一致）；
裁定 48.5 的 bitwise 证据**位置已给准**（在 `compare` 段，不在 `remap` 段）——**但 A2 认领引用缺陷**。
**代价：A2 自纠三处**（§11.2 / §11.3 / §11.7），其中第一处是**产物缺失**，性质最重。

### 11.1 裁定 48.6 只剩的那一条：**blocker → 成功之间改了什么、何时改**（已自证）

**产物**：`runs/vla/a2_env_pi05_sim_20260929/env_manifest.json` → `ruling_48_6_blocker_to_success` 段（生成器 `scripts/a2_env_manifest.py`，可复跑）。
**口径**：全部取自**已落盘文件的 mtime + 安装日志原文行**，不靠记忆/转述。

| 时刻（+08:00） | 事件 | 证据（文件 + 关键字段/原文） |
|---|---|---|
| **18:05:36** | **改前** lock 落盘：`transformers==4.57.6`（PyPI）、`tokenizers==0.22.2` | `requirements.lock.stage2c_before_pi_extra.txt:111` / `:105` |
| **18:05:58** | **blocker 现场**：`ValueError: An incorrect transformer version is used…` | `runs/vla/a2_pi05_contract_20260929/probe_run1_transformers_blocker.log` |
| **18:24:19**（`start_utc=2026-09-29T10:24:19Z`） | **改动开始**：装 lerobot 0.4.4 的 **`pi` extra**（STAGE 3），`Resolved 18 packages in 7m 10s` | `stage3_install.log`（`PRE transformers 4.57.6 tokenizers 0.22.2`） |
| **18:34:00** | **改动完成**：`- transformers==4.57.6` → `+ transformers==4.53.3 (from git+…@dcddb970…)`；`- tokenizers==0.22.2` → `+ tokenizers==0.21.4` | `stage3_install.log`（含 `Building transformers @ git+…@dcddb970…`） |
| **19:04:54** | **改后** lock 重生成：`transformers @ git+https://github.com/huggingface/transformers.git@dcddb970176382c0fcf4521b0c0e6fc15894dfe0` | `requirements.lock.txt:111`（**带 commit sha，不是分支名**） |
| **19:05:52** | **成功现场**：`from_pretrained` 加载成功、逐张量校验通过 | `runs/vla/a2_pi05_contract_20260929/probe.log` + `load_verification.json` |

**改了什么（机制，读实现原文得来）**：装的**不是 PyPI 的 4.53.3**，而是 branch **`fix/lerobot_openpi`** / commit **`dcddb970176382c0fcf4521b0c0e6fc15894dfe0`** 的 **git 构建**（`INSTALLER=uv`）。
只有这个构建带 **`transformers/models/siglip/check.py`**；卫语句 `modeling_pi05.py:576`–`:584` 是 `from transformers.models.siglip import check` → `check_whether_transformers_replace_is_installed_correctly()`，
其**全文**（本轮用 `inspect.getsource` 抓进 manifest，不是转述）= `return transformers.__version__ == "4.53.2" or transformers.__version__ == "4.53.3"`。
⇒ **blocker 是 `ImportError` 分支**（PyPI 4.57.6 没有 `check.py`，被同一个 `except` 转成同一个 `ValueError`），**成功是判据返回 `True`**。**与 D 的裁定 48.6 判断一致，A2 独立复核成立。**

**两项确认（裁定 48.6 点名要的）**：
- **已写入 lock**：✅ `requirements.lock.txt:111`，commit 逐字 = `dcddb970176382c0fcf4521b0c0e6fc15894dfe0`（D 在裁定 48 里已独立确认「A2 的 lock 记对了」，此处再自证一次，口径 = **行号 + 原文**）。
- **已写入 `env_manifest.json`**：✅ **由新增的 V10 承载**（§11.3）。**此前 19:1x 那版只有 V5**（只查 `check` 模块在不在，**不含 commit 身份**），且**该版产物本身不在盘上**（§11.2）⇒ 这一条**本轮才真正闭合**。

### 11.2 **A2 自纠 ①（性质最重）**：19:1x 声称的「manifest **9/9 全绿**」，其**产物不在盘上**

**事实**：`daily_report.md:3795` 写「`runs/vla/a2_env_pi05_sim_20260929/env_manifest.json`：V1–V9 **9/9**」。
本轮（20:4x）实测该路径 **`No such file or directory`**；全仓 `find` 只有三份**留档**：
`manifest_run1_probe_false_red/`（**8/9**，V4 假红）、`manifest_run2_dist_drift_false_red/`（断言 **9/9** 但 `frozen_stack_drift=["torch","torchvision"]` ⇒ `env_usable=false`）、
以及 B2 侧的快照 `runs/vla/b2_env_admission_20260929/a2_snapshot_1913_dist_drift_false_red/`（= run2 的副本）。
⇒ **run3（真正全绿那次）的输出从未留在盘上**：留档动作（`mv` 顶层文件进 run2 目录）做了，重跑的输出**没落地**。

**为什么这条必须自纠而不是悄悄补上**：
1. **它是被 D 点名要「自证」的那个文件**（裁定 48.6：`env_manifest.json`「待自证」）⇒ 拿不出文件 = 该条**当时并未闭合**，而日报写成了已闭合；
2. **B2 的准入闸消费的是 run2 那份 `env_usable=false` 的快照** ⇒ 下游看到的是**红**的 A2 环境，而 A2 的日报说**绿**；这个不一致必须由 A2 先说；
3. house rule「任何数值主张要能被复核」——**产物缺失时，主张就退化成口述**。

**处置**：重出 manifest（**20:50:14**，`assertions_pass = 10/10`、`env_usable = true`、`frozen_stack_drift = []`、`loadavg 47.25/49.20/50.67`、冷导入 torch 2.14 s / transformers 4.19 s / lerobot 0.04 s）；
run1–run3 **三份留档全部保留不删不改写**，run3 目录内加 `WHY_ARCHIVED.md` 说明留档原因。**并请 B2 用新 manifest 重过准入闸**（旧快照是红的）。

### 11.3 **V10：把裁定 48 的新红线做成闸**（含 **A2 自纠 ②**：c6 判据写错，被自己的闸抓住）

**红线原文（裁定 48）**：transformers **身份 = git commit `dcddb970…`**（branch `fix/lerobot_openpi`）；判据 = `direct_url.json` 的 `commit_id` 与 lock `:111` 一致 **且** `siglip.check.…()` 返回 **True**；`torch==2.6.0+cu124` 红线不动。

**V10 的六条子判据（本轮实测**全绿**）**：

| 子判据 | 实测 | 说明 |
|---|---|---|
| `c1_direct_url_commit_present` | ✅ | `direct_url.json → vcs_info.commit_id = dcddb970…` |
| `c2_lock_commit_present` | ✅ | `requirements.lock.txt:111` 解析出同一 commit |
| `c3_commits_bitwise_identical` | ✅ | **逐字相同**（不是前缀匹配） |
| `c4_guard_clause_returns_strictly_true` | ✅ | `check_whether_transformers_replace_is_installed_correctly()` **严格 `is True`** |
| `c5_runtime_version_in_guard_domain` | ✅ | `transformers.__version__ == 4.53.3` ∈ {4.53.2, 4.53.3} = **卫语句自己那行的取值域** |
| `c6_is_vcs_build_not_registry_wheel` | ✅ | `vcs_info.vcs == "git"` 且无 `archive_info` |

**判据来源等级 = `implementation_read`**（读了卫语句与 `check.py` 的实现原文，`inspect.getsource` 抓进产物），**不是 `declared_only`** ⇒ 按 D 的新纪律可作 blocking。

**V5 是弱牙，V10 严格强于 V5（用变异体证明，不是口头）**：`scripts/a2_env_manifest.py --selftest` → **6/6 变异体全被抓**、baseline 绿。
其中 **4 例 V5 会放过而 V10 抓住**：`M2` wheel/`archive_info` 形态、`M3` commit 不匹配、**`M5` 探针异常 ⇒ guard 返回 `None`**、`M6` 版本落在卫语句取值域外。
**`M1` 不是假想变异，是本轮真实发生过的 blocker 状态**（PyPI 4.57.6 ⇒ 压根没有 `direct_url.json`）⇒ V10 在历史上**确实会变红**。

**A2 自纠 ②**：V10 第一次跑出来是 **9/10（V10 红）**。真因是 **c6 原写作 `direct_url["url"].startswith("git+")`** ——
**PEP 610 的 `url` 字段是裸 VCS URL**（实测 `https://github.com/huggingface/transformers.git`，**不带** pip/lock 的 `git+` 前缀）⇒ 真环境被判假红。
改判 `vcs_info.vcs == "git"`（PEP 610 的权威信号）后 10/10。**假红那次留档在 `manifest_run3_v10_pep610_false_red/`（含 `WHY_ARCHIVED.md`），不删不改写。**
**旁证（说明这条判据不是拍的）**：本 venv **124 个 dist-info 里只有 `transformers` 有 `direct_url.json`** ⇒ 「没有 `direct_url.json`」本身就是注册表/wheel 安装的证据（= M1）。

### 11.4 裁定 46 **第 5 项**：同视角亮度/直方图对比 —— **完成**，并**否证了「近乎全黑」的测量基础**

**产物**：`runs/vla/a2_pi05_zeroshot_20260929/brightness_reference_abc130k.json`（生成器 `scripts/a2_brightness_reference_abc130k.py`，**CPU-only、不渲染新帧、不占 GPU、不跑 policy**；`loadavg 34.65→40.51`、`nr_throttled Δ0`）。

**(a) 先解决口径：D 引的 `mean≈9.3/255`、「非零字节占比 7%」= PNG **IDAT 滤波残差域**，与亮度无关**

| 域 | base 相机实测 | 与 D 引的数字 |
|---|---|---|
| **B：IDAT 滤波字节**（`h*(1+3w)` = 224×673 = **150752**） | mean **9.29**、非零占比 **0.0712** | ✅ **逐字对上 D 的 9.3 / 7%** |
| **A：像素域**（224×224×3 = 150528） | luma mean **36.31**、非零像素占比 **0.4646** | ❌ 9 张图里 **0 张**能对上 9.3 |

**决定性旁证**：D 自己核过的 **`raw_len = 150752`** 恰好 = `224*(1+3*224)`（**含每行 1 个 filter-type 字节**），而**纯像素**应是 `150528` ⇒ **D 当时就在滤波字节域**。
滤波字节是「当前像素 − 预测值」的**残差**，大面积均匀区域被压成 0 ⇒ **它的均值/非零占比不携带明暗信息**。
⇒ **「观测近乎全黑」这一假说由测量域错配产生，不成立**（9 张图逐张复现，见 `domain_reconciliation.per_file`）。

**(b) 同视角类对比（参照 = **本机已落盘**的 ABC-130k，`read_only`、**本轮零下载**）**

| sim 相机 | 参照文件 | sim luma mean(中位) | 参照 luma mean(中位) | 比值 | 非黑占比比 | 判定 |
|---|---|---|---|---|---|---|
| `left_wrist` | `left-wrist-camera.mp4`（5 视频/40 帧） | **77.85** | **112.30** | **0.693** | 0.733 | `not_pathologically_dark` |
| `right_wrist` | `right-wrist-camera.mp4`（5 视频/40 帧） | **78.95** | **112.75** | **0.700** | 0.733 | `not_pathologically_dark` |
| `base` | `top-left-camera.mp4`（**1 视频/8 帧**） | **36.31** | **85.94** | **0.423** | 0.465 | `not_pathologically_dark` |

**判据（A2 提议、D 裁；阈值不自决）**：比值落在 **[0.25, 4.0]**（数量级带）**且**非黑像素占比 ≥ 参照的 **0.25** ⇒ `not_pathologically_dark`。**本轮 3/3 落在带内、0 个 `FLAG_DARK`。**
**判据带牙（负对照）**：合成全黑 224² 图走同一条管线 ⇒ luma mean **0.0**、比值 **0** ⇒ **落在带外判红** ⇒ 「不暗」不是恒真式安全错觉。

**(c) 参照侧覆盖率**（如实报，不外推）：扫描 **150 个 task**，**双臂腕部相机 150/150 都有**，但 `top-left-camera.mp4` **只有 1/150 个 task 有** ⇒
**`base` 那一行是 n=1 视频 / 8 帧的薄样本**，**只支持「同一数量级、非近乎全黑」，不支持任何精细亮度结论**。

**(d) 边界（写死，防误用）**：ABC-130k = **YAM 形态、真机、真实光照**；A2 环境 = **MuJoCo 仿真、ViperX300** ⇒ 本节是**描述性亮度参照**，**不是形态匹配、不是有效性闸**。
参照视频是 **h264/yuv420p（有损 + 色度子采样）**、sim 侧是**无损 RGB PNG** ⇒ **只比数量级**。
**与裁定 49.2③ 不冲突**：被禁的是「拿 ABC130k 的 **normalizer stats** 喂 ViperX300」；本节**只比图像亮度分布、不产出任何 stats、不参与归一化**（脚本里没有任何 normalizer 字段）。
参照侧的采集标定/曝光参数**未随数据集提供** ⇒ 参照绝对亮度标 **`external_unverified`**。

**(e) 本节**不**支持什么**：不支持任何 π₀.₅ 能力/成功率主张（裁定 46）；**不**表示 `0/20` 的成因已解决 —— 已确证主因仍是**无 normalizer stats ⇒ 状态通道饱和**（waist 仅 0.3183 行程），本节只排除**第二个**假说。

### 11.5 裁定 49.5（V-pi05-3 渠道混用）：顶层 = **`mixed`**，**sidecar 闭合，receipt 未重写**

**产物**：`runs/vla/a2_env_pi05_sim_20260929/weights_receipt_channel_sidecar.json`（生成器 `scripts/a2_weights_channel_sidecar.py`）。
**为什么不改 `weights_receipt.json`**：它**已被 B2 的 sha256 快照消费**（准入闸按内容哈希引用）⇒ 原地改字段会让 B2 侧哈希对不上。**只读 + 另存 + 指回**，并把 receipt 的 sha256 **写前后各测一次**：
`11267d5bae83811d9f3ee80260c3bb0f3deb2e9cbe4b16b520969447df0898a4` → **完全相同**（`C2_receipt_sha256_unchanged = true`，把「只读」从口头承诺变成断言）。

- **顶层 `channel_top_level = "mixed"`**，指向 `per_file_channel`（7 条逐文件记录）。
- **两个渠道**：`model.safetensors` = **ModelScope 单流 curl**（26.16 MB/s、553 s、`curl_rc=0`）；其余 **6 个小文件** = **hf-mirror + `hf_mirror_snapshot.py --repo-type model`**（D §8.1 指定的现成工具，**未裸调 `snapshot_download`**，因为裸调会**静默返回半成品并 exit 0**）。
- **tokenizer 仓单列**：`google/paligemma-3b-pt-224` = ModelScope（`a2_modelscope_fetch.py`，8 文件、`missing=[]`、`bad_sha256=[]`、`PASS=true`）⇒ 不把两个 repo 的渠道混成一句话。
- **混用为什么可接受（实质依据，不是格式依据）**：`model.safetensors` 的 **HF-LFS 期望 sha256 与 ModelScope 期望 sha256 逐字相同**（`0eb11ca9…59b0f`），且**落盘实测与两者一致** ⇒ **混用渠道没有造成内容分叉**。
  **残留差异如实记**：`.gitattributes` 两渠道内容**不同**（1519 B vs 2130 B，ModelScope 由 SDK 重新打包）⇒ receipt 已判为**渠道差异非损坏**，本 sidecar **不改变**该判定。
- **判据带牙**：`C1`–`C5` **5/5 绿**，`--selftest` **3/3 变异体全被抓**（`M1` 全部文件同一渠道 ⇒ C1 红、顶层**不**写 `mixed`；`M3` safetensors 跨渠道 sha 不一致 ⇒ C3 红；`M4` 有一个必需文件缺渠道记录 ⇒ C4 红）。
  **C1 是双向牙**：只有 1 个渠道却写 `mixed` 也算失真 ⇒ 一样红。

### 11.6 裁定 48.5：bitwise 证据的**准确位置** —— D 的核对**部分成立**，A2 **认领引用缺陷**

**A2 作为产物作者，逐字段确认**（`runs/vla/a2_pi05_contract_20260929/load_verification.json`，sha256-12 `18d9149a4636`，3246 B）：

- **D 说的对的部分**：`remap` 段**确实只有三个字段**（`n_keys_in_file=812`、`n_keys_after_fix=812`、`s=3.65`）⇒ **那是键数相等，不是逐位相同**。**只读 `remap` 段，得不出「bitwise」也得不出「无随机初始化键」。**
- **D 说的不准确的部分**：**同一份 JSON 另有 `compare` 段**，逐位证据**在那里**：
  `compare.n_compared=812`、**`compare.n_bitwise_exact=812`**、`compare.n_differ=0`、`compare.n_shape_mismatch=0`、
  **`compare.n_model_keys_not_covered_by_ckpt=0`**（该段自带 note 原文：「这些键在 ckpt 里找不到对应张量（也不是 tied 别名）⇒ **它们保持随机初始化**。若为空，说明权重是完整落进模型的」）、
  顶层 **`verdict="all_bitwise_equal"`**。⇒ **「无随机初始化键」在产物里是有证据的，位置是 `compare.n_model_keys_not_covered_by_ckpt`**。
- **`tied_weight_checks` 只有 1 条**：D 说得对，但**1 = 全集**。依据：safetensors `__metadata__` 里的 tied 别名**恰好只有 1 个**
  （`…language_model.embed_tokens.weight` → `…lm_head.weight`，见 `safetensors.tied_weight_metadata`）⇒ **覆盖率 1/1 = 100%**，不是抽样。
- **A2 认领的缺陷（这条是关键）**：A2 在 `daily_report.md:3849` 只写了「812/812 bitwise」这个**结论数字**，
  **没给 JSON 字段路径**；而 `remap` / `compare` 是**同级的两个顶层段**、名字都像"比对" ⇒ **按段名去找的复核者会翻到 `remap` 然后什么都找不到**。
  **这不是 D 读错，是 A2 引用不合格。** 修法已落地：`runs/vla/a2_pi05_zeroshot_20260929/weights_linkage.json` **镜像了 `compare` 段的六个计数** + 被链接文件的 **sha256 全文**，
  本节再把**字段路径逐个写全**。
- **对裁定的影响**：**无**。裁定 48.5 的落点是「**改判成立，但依据必须换成 48.1 的实测**」⇒ **A2 完全接受**：
  π₀.₅ 可加载的**依据 = 裁定 48 的实测（`direct_url.json` commit + 卫语句返回 True，现已固化为 V10）**，
  **不是**「因为权重 bitwise 相同」。两者回答的是**不同问题**（前者 = 能不能加载；后者 = 加载进去的是不是 ckpt 里那份、有没有留在随机初始化的键），**不该互相顶替**。
- **一条请求（不改变裁定）**：`compare` 段的证据**建议恢复有效性**，因为它挡的是**另一个**坑 ——
  `modeling_pi05.py:995`–`:998` 会**静默返回随机权重模型**（`except Exception → print → return model`）、`:1046`–`:1047` 把 `:1021` 的 `load_state_dict(strict=True)` 异常**吞成一行 warning**
  ⇒ **「加载成功」本身没有证据力**，逐位比对是**唯一**能把「加载成功」与「静默随机权重」分开的东西。**由 D 裁，A2 不自决。**

### 11.7 §10.11 的更新（**第 3 项作废**，含 **A2 自纠 ③**）

**§10.11 第 3 项原文**：「同视角亮度对照 —— 未做（**本机无参照数据**；需 D 授权下载）」⇒ **本轮作废**，理由如下：

- **A2 自纠 ③**：「本机无参照数据」**不成立**。参照数据集 **ABC-130k 早已在本机**：`/workspace/mnt/sppro/yhzhang91/workplace/ABC130k`（`train` / `val` / `result`）。
  A2 当时**只查了自己的持久盘 `$PERSIST/hf-cache`**，没查 `workplace/` ⇒ **误判成"需要下载 + 需要授权"**。
  **发现路径值得记**：是 **B2 的 `runs/vla/b2_abc130k_smoke_20260929/extract.log` 第一行**（`src_root=/workspace/…/workplace/ABC130k`）暴露的 ⇒
  **跨线读别人的日志能纠自己的前提错误**，这条比结论本身有用。
- **结果**：§11.4 的对比**零下载、零授权**完成（`reference_dataset.downloaded_this_round = false`、`read_only = true`）。
- **§10.11 其余四项状态不变**：1（Piper 相机注入 / 两指耦合实施）**仍未做**，等 D 排期；2（30 Hz 接线）**仍未做**，等 §10.9 的裁定（A2 推荐**丙**）；
  4（C §2.4 重复帧触发面）**仍未做**，接真帧前必须做，**A2 不主张它一定发生**；5（`torchcodec`/FFmpeg）**仍未修**（既存缺口，基线 venv 同状况）。
  **本轮 §11.4 绕开 torchcodec 的办法**：用 **`ffmpeg` CLI 子进程**解码 mp4（`-ss` 输入侧定位 + `-f rawvideo -pix_fmt rgb24`）⇒ **不依赖 torchcodec**，B2 若走 mp4 数据集可复用这条口径。

### 11.8 产物索引增补（接 §9）

| 产物 | 生成器 | 回答 | 关键数字 |
|---|---|---|---|
| `runs/vla/a2_env_pi05_sim_20260929/env_manifest.json`（**20:50:14 重出**） | `scripts/a2_env_manifest.py` | 裁定 48.6 的自证 + 裁定 48 的新红线 | **10/10**、`env_usable=true`、`frozen_stack_drift=[]`、commit `dcddb970…`、变异自检 **6/6** |
| `…/manifest_run3_v10_pep610_false_red/`（含 `WHY_ARCHIVED.md`） | 同上 | A2 自纠 ② 的留档 | 9/10（c6 PEP610 判据写错） |
| `runs/vla/a2_pi05_zeroshot_20260929/brightness_reference_abc130k.json`（21:00:41） | `scripts/a2_brightness_reference_abc130k.py` | 裁定 46 第 5 项 | 域对账 **6/9 命中滤波域、0/9 命中像素域**；比值 0.693/0.700/0.423；**0 个 FLAG_DARK**；负对照判红 |
| `runs/vla/a2_env_pi05_sim_20260929/weights_receipt_channel_sidecar.json` | `scripts/a2_weights_channel_sidecar.py` | 裁定 49.5 | `channel_top_level="mixed"`、**C1–C5 5/5**、自检 **3/3**、receipt sha256 **未变** |

**复现命令**（三条都是 CPU-only、可重复跑、都自带 `--selftest`/负对照）：
```bash
/root/venvs/pi05_sim/bin/python scripts/a2_env_manifest.py --selftest        # V10 变异自检 6/6
/root/venvs/pi05_sim/bin/python scripts/a2_env_manifest.py                   # 重出 10/10 manifest
/root/venvs/pi05_sim/bin/python scripts/a2_weights_channel_sidecar.py --selftest
/root/venvs/pi05_sim/bin/python scripts/a2_brightness_reference_abc130k.py --n-per-class 5 --scan-tasks 150 --frames-per-video 8
```

### 11.9 仍需 D 裁 / A2 待办（本节新增，**不含已在 §8 的 14 条**）

| # | 事项 | A2 的做法 | 归谁 |
|---|---|---|---|
| 15 🆕 | **§11.4 的亮度判据阈值**（比值带 `[0.25,4.0]`、非黑占比下限 `0.25`） | **A2 提议 + 已带负对照**，**不自决** | **D 裁**（阈值口径） |
| 16 🆕 | **B2 的准入闸消费的是 run2 那份 `env_usable=false` 的快照** | 新 manifest 已出（10/10 绿）⇒ **请 B2 重过闸**；A2 不改 B2 的文件 | **B2**（重跑）/ D（备案 §11.2 的自纠） |
| 17 🆕 | **`compare` 段证据是否恢复有效性**（§11.6 末条） | A2 主张恢复，但**接受裁定 48.5 的分工**：可加载性依据 = V10，**不用 bitwise 顶替** | **D 裁** |
| 18 🆕 | **`env_manifest.json` 不带 `nr_throttled`**（A 线口径只有 `loadavg`） | 本轮 manifest 的节流数只能**区间 bracket**（20:50 起跑时 `nr_throttled=3029`，21:0x sidecar 时 `3054` ⇒ **Δ≤25，且含并发会话、非本进程独占**）⇒ **不当作本进程独占数字引用** | **D**（是否要求 A 线口径补 `nr_throttled`；A2 不擅自改 A 的脚本） |
| 19 🆕 | **参照数据集的发现路径没进任何清单** | ABC-130k 在 `workplace/`（**不在** `$PERSIST`、**不在** repo）⇒ 建议进 C 的复用清单/参数表，否则下一个智能体会重犯 A2 自纠 ③ | **D / C2**（登记） |

---

## 12. 本轮增补（**23:2x**）：裁定 58.3 / 59(+70) / 64 / 65 的落地 · §10.11 两项闭合 · **176 步推荐作废** · S4a 已落地

> **本节与 §1–§11 的关系**：§1–§11 **原文不动**（house rule：已落盘产物不重写）。
> 本节凡与前文冲突的，**以本节为准并显式点名作废**。
> 本轮 S4a 验证**全程 CPU-only**：`gpu_used=false`，起止 `nvidia-smi` 均 **0 MiB**（无需申报、无需销账）。

### 12.1 【裁定 58.3】回合时长：**保持 300 步**，但**一切按秒登记**

| 项 | 值 | 机器承载（不是文档承诺） |
|---|---|---|
| `max_episode_steps` | **300**（**不缩放**；A2 原推荐的 176 步 **作废**，见 §12.4） | `harness/vla_runtime.py:MAINLINE_MAX_EPISODE_STEPS = 300` |
| `control_dt_s` / `control_hz` | **0.034** / **29.411765**（shim 实测，非声称） | `manifest_caliber()`；`live_timing.matches_mainline=true` 由 **G15** 查 |
| `episode_horizon_s` | **10.2**（= 300 × 0.034） | `manifest_caliber()` 的**强制字段**，缺即红（**G12**） |
| 生态公布口径 | **`"DT=0.02, 300 steps, 6.0 s, 50 Hz"`** 必须随附 | `manifest_caliber().published_gym_aloha_caliber` |
| 跨口径并列 | **不得按步数并列**；并列必须标 `not_comparable_horizon` | `manifest_caliber().not_comparable_horizon`；**G12** 查它在不在 |
| 超时处置 | **按秒登记**，不重标成"准时" | `finalize()` 里 `terminal_kind="timeout"` 走独立分支 |

- **牙（已实测）**：变异自检把 `max_episode_steps` 改成 **176** ⇒ **G12 红**；把 `control_hz` 改成 **50.0**（把 50 Hz 生态口径混进主线）⇒ **G15 红**。
  两条都在 `runs/vla/a2_s4a_vla_runtime_20260929/s4a_verification.json → gate_teeth_mutation_selftest.detail`。

### 12.2 【裁定 59 + 裁定 70 更正】渲染后端：**egl + prefix-only**，且**`GL_RENDERER` 才是事实**

- **主线后端** = `MUJOCO_GL=egl` + prefix-only NVIDIA vendor ICD；`osmesa` 降为 CPU 对照与退路（裁定 42 的 osmesa 口径作废，**已留档数字仍有效**，五元标注写明）。
- **前缀路径更正（裁定 70）**：裁定 59.4 与断点文件写的 `.codex-persist/nvidia-gl-590.48.01/` **不存在**；
  实际路径是 **`.codex-persist/egl-libs/590.48.01/`**。**唯一合法激活方式**：
  `eval "$(bash scripts/e_activate_gpu_render.sh --print)"`（各线在自己进程内激活，**禁止系统写入**）。
- **A2 提的两条规则已升为全仓纪律（裁定 71/72）**：① **`GL_RENDERER` 才是事实**，`MUJOCO_GL` 这个环境变量**不是**证据
  （G3 那轮只记了 `MUJOCO_GL="egl"`、从未记过 `GL_RENDERER`，实测是 `llvmpipe`）；② **自检必须走真实取数路径**。
  ⇒ 本轮 S4a 的 `render_backend()` 因此**标注取数路径**：`GL_RENDERER=…|probe=inside_real_render`（在 `physics.render()` 刚返回、上下文仍 current 时读）
  vs `probe=bare_no_context`（裸调、**不可信**）。
- **本轮 S4a 真实 env 臂的 `GL_RENDERER` 事实** = **`llvmpipe (LLVM 15.0.7, 256 bits)`**，`probe=inside_real_render`
  ⇒ **该臂的 `budget_fraction 3.64` 是 CPU 软渲染口径，不是主线口径**，产物里已就地写明并交叉引用 GPU 口径数字（**跨口径不得互搬**，裁定 46.4/53.6）。

### 12.3 §10.11 的状态更新（**第 2、3 项闭合**；1/4/5 不变）

| §10.11 项 | 原状态 | **23:2x 状态** | 依据 |
|---|---|---|---|
| 1 Piper 相机注入 / 两指耦合实施 | 未做 | **仍未做**（等 D 排期） | —— |
| 2 **30 Hz 接线** | 未做（等 §10.9 裁定） | **已闭合** | `envs/gym_aloha_shim.py`（sha256-12 **`dc14466fcdcf`**，`DT=0.034`/17 子步/实测 **29.411765 Hz ∈ QC**）+ `runs/vla/a2_hz_shim_29p4118_20260929/hz_shim_verification.json`（**11/11 闸**）；**裁定 62-① 明令 C2 必须复用它、不许自写第二份** |
| 3 **同视角亮度对照** | 未做（"本机无参照数据"） | **已闭合并落盘**（原判断"本机无参照数据"**是错的** = A2 自纠 ③） | `runs/vla/a2_pi05_zeroshot_20260929/brightness_reference_abc130k.json`（含裁定 59-5 的结论行 + 裁定 61 的 `not_for_mainline_normalizer=true`/`allowed_use`）；详见 §11.7 |
| 4 C §2.4 重复帧触发面实测 | 未做 | **仍未做**（接 ABC-130k 真帧前必须做） | —— |
| 5 `torchcodec`/FFmpeg | 未修 | **仍未修**（既存缺口） | —— |

### 12.4 **176 步推荐正式作废**（A2 自己的推荐，自己撤回）

- **原推荐**（`docs/a2_s4_vla_runtime_interface_20260929.md` §5 的 B 案）：把 `max_episode_steps` 缩到 **176**，
  理由是"保持任务时长 ≈6.0 s 不变，好与 50 Hz 生态的成功率可比"。
- **裁定 58.3 推翻它**：**保持 300 步、不缩放**；可比性问题**改用"按秒登记 + 显式换算 + `not_comparable_horizon` 标记"解决**，
  而不是改 horizon。⇒ **A2 撤回该推荐**；S4 文档 §5 的 B 案已划掉留痕、§9-2 已标"已裁"。
- **为什么这条要单独点名**：176 这个数字如果留在文档里没被划掉，下一个智能体会拿它去配 env ⇒
  **同一份代码会产出两种 horizon 的轨迹并且看起来都"正常"**（正是裁定 65-2 要防的那类静默口径漂移）。
  现在它被做成了**闸的变异体**：写 176 就红。

### 12.5 【裁定 64】v4 引用改带**身份三元组**

- 本轮起 A2 对 v4 的每一条引用都带 **(相对路径, sha256-12, 行号)**；三元组表见
  `docs/a2_s4_vla_runtime_interface_20260929.md` **§0.6**，同一份也写进产物字段 `citations_file_identity_triple`。
- **两处更正**：① D 的 `:344`–`:346` 是**跨文件混引**（P0 实出自 `01_开发技术方案.md:347`；`:344`–`:346` 是附录一的陷阱表 T24/T25/T26），
  **A2 原先把它定性为"同文件偏行"也是错的**；② **A2 自己把 T25 写成 `:346`，实为 `:345`**（`:346` 是 T26），已就地改。
- 文件身份（23:2x 实测）：附录一 `aae20ffe604f`/433 行、附录二 `a6ab42165ab3`/354 行、开发技术方案 `0a9a2092e18a`/418 行。

### 12.6 【裁定 65-5】**S4a 已落地并验证**（详见 S4 文档 §11）

- `harness/vla_runtime.py`（**630 行**，sha256-12 **`809e097b1fd9`**）+ `scripts/a2_s4a_vla_runtime_verify.py`（**1077 行**，**`c8c15c8effa3`**）。
- **16/16 闸 PASS** + **16/16 条闸经变异自检证明有牙**；真实 `gym_aloha` 主线档（`n=25`/`H=50`/55 帧）**逐帧吻合闭式重推**（`diffs=[]`，请求发生在 f=0/25/50）。
- **`contracts_py_modified = false`**（`harness/contracts.py` sha256-12 `96c99ead93d2`；`git status` 对 `contracts.py`/`runtime_adapter.py`/`configs/` **均无输出**）；`harness/ledger.py` `2a33c3f5516e` 同样只 import 不改。
- **`policy_executed = false`、`success_metrics_collected = false`、`capability_claim = false`**，成功率栏 = `not_an_exit_criterion`（裁定 46 / 65-6③）。
- **S4b 未做**：outcome 四类判定（成功/失败/超时/未知，**必须独立于 `reward==4`**）**blocked on C2 的 `harness/env_gym_aloha.py`**（裁定 62）。

### 12.7 本轮**新增**的两个待裁项（A2 不自决）

| # | 事项 | A2 的默认（保守端） | 为什么归 D |
|---|---|---|---|
| 20 🆕 | **`prime_mode`**（t=0 时 C 槽无源，怎么 priming） | **`hold`**（帧 0..n-1 保持初始 qpos），另提供 `first_chunk` 对照；**G13 已证明两案行为不同** | 附录二未指定 priming ⇒ 属契约语义；产物里标 `status="proposed"` |
| 21 🆕 | **`timeout_isolation_scope`**（300 步 / 10.2 s 截断要不要隔离学习资格） | **td、bc 都隔离**（`TIMEOUT_ISOLATES_TD/BC = True`） | 主线下**绝大多数 zero-shot 局以 timeout 收尾** ⇒ 这个开关直接决定 S4 能留下多少可学习数据；RL 侧截断本该 bootstrap、BC 侧截断轨迹通常仍可用 ⇒ **A2 建议裁 `td_only`，但未自行放宽** |

### 12.8 本节**不声称**

- 不声称 π₀.₅ 有任何能力（裁定 46）；不声称任何成功率数字（**无 normalizer stats**，`stats_version="NONE"` ⇒ 已由 `_guard_stats_version` **硬隔离**）。
- 不声称 S4a 跑过真模型（`--policy pi05` **未实现**，属 S4b；脚本 usage 里原先那行是**文档谎报**，本轮已改口）。
- 不声称异步口径已实现（`async_overlap=false`，S4a 是**同步阻塞**口径；迟到由实测墙钟 vs `deadline_s = n·dt` 判定）。
- 不声称任何单一"主线渲染口径"数值（裁定 71-1：等 E3-③ 在**静默窗口**内落地）；本节所有吞吐数字都带 `GL_RENDERER` 事实 + `loadavg` 三点 + `nr_throttled` 增量。

---

## 13. 本轮增补（**2026-09-30 00:2x–00:5x**）：裁定 76.4 的**权威延迟值已拿到**（4 次 clean 重复）· 裁定 83§5 五点全部落地 · §12.7 的 20/21 两项**已裁**

### 13.1 裁定 76.4 的权威值（**这是本轮唯一还没拿到的关键数字，现已拿到**）

口径：`closed_loop` 臂、真权重（`pi05_base_compat_lerobot044`）、`MUJOCO_GL=egl` + prefix-only 激活（裁定 70）、
`GL_RENDERER` 实测 **`NVIDIA A800-SXM4-80GB/PCIe/SSE2`**、mujoco **3.8.1**、3 cam × 224、`DT=0.034`（`control_hz=29.411765`）、
`--n-action-steps 50,25 --n-episodes 3 --max-steps 300`、2 s 周期运行时 cotenant 采样、批级让位闸（裁定 76.2）。

**n=25 档（主线档，满足 v4 `H≥2n`：50 ≥ 2×25）**

| 重复 | 窗口判定 | `loadavg_1m`(前→后) | Δ`nr_throttled`(全程) | `wall_ms/step` | `budget_fraction`(÷34 ms) | 摊薄推理 `ms/step` | `realtime_ratio` | `loop_fps` |
|---|---|---|---|---|---|---|---|---|
| rep1 | **contaminated**（**不采纳**，仅重载端趋势） | 39.10→43.88 | 410 | **45.785** | **1.3466** | **31.820** | **0.8587** | 25.255 |
| rep2 | clean | 26.86→25.52 | 6 | 26.191 | 0.7703 | 19.288 | 1.2982 | 38.183 |
| rep3 | clean | 25.37→26.76 | 6 | 26.713 | 0.7857 | 19.559 | 1.2728 | 37.436 |
| rep4 | clean | 25.17→27.62 | 4 | 27.230 | 0.8009 | 20.123 | 1.2491 | 36.739 |
| rep5 | clean | 27.62→26.88 | 102（**全在模型加载段，两臂内 Δ=0**） | 26.405 | 0.7766 | 19.445 | 1.2877 | 37.873 |
| **clean×4** | —— | 25.2–27.6 | —— | **26.635**（26.191–27.230，极差 **3.90%**） | **0.7834**（0.7703–0.8009） | **19.604**（19.288–20.123，极差 **4.26%**） | **1.2770**（1.2491–1.2982） | **37.558**（极差 3.84%） |

**n=50 档（出厂档，`v4_H_ge_2n_satisfied=false`，仅作对照）**：clean×4 `wall_ms/step` **17.114**（16.681–17.512）、
`budget_fraction` **0.5034**、摊薄推理 **10.178 ms**、`realtime_ratio` **1.9890**；rep1（contaminated）**36.168 / 1.0638 / 20.615 / 0.9652**。

- **⇒ 裁定 76.4 的「≥2 次可用重复」实质满足且超额：4 次 clean（rep2–rep5）**，其中 **rep4+rep5** 是
  「读到裁定 83 之后 + 带 83§5 的 `policy_executed` 定义字段」的**权威对**，rep2/rep3 为旁证。
- **本轮最有价值的一条**：**同一负载档内的重复极差 <5%，而 rep1（重载）与 clean×4 之间差 1.72×**
  ⇒ **方差主要来自负载档、不来自重复**（裁定 71-3 的负载敏感度这次有 4×1 的实测支撑）。
- **按裁定 71-2 用保守端规划，两端并列**：**保守端 = 重载端（rep1）`wall 45.785 ms` / `budget_fraction 1.3466` / `realtime_ratio 0.8587`**；
  **干净窗端（权威）= `26.635 ms` / `0.7834` / `1.2770`**。
  按裁定 75.4，`budget_fraction>1` **不自动判红**（34 ms 是软约束），但必须带 overload 语义 ⇒
  本脚本的对应字段是 **`all_episodes_within_per_step_budget`**（rep1 两档都 `false`、clean×4 八档全 `true`）。
- **摊薄推理是负载条件量**：clean×4 **19.288–20.123 ms**、rep1 **31.820 ms**（跨档 **1.65×**）
  ⇒ **任何单点引用都必须是错的**；引用时必须同时给负载对与窗口判定。
- **对照 D 的裁定 75.6**（`5.80 + 27.33 = 33.13 ms = 97.4%`、余量 `2.6%`）：干净窗实测 **26.635 ms = 78.3%、余量 21.7%**；
  重载端实测 **45.785 ms = 134.7%、余量 −34.7%**。**⇒ A2 不推翻 75.6**：75.6 是单点估算，A2 提供的是两端 + 4 次重复的分布，两者是补充关系。
  **【`01:5x` 就地更正 · 裁定 84§3 + 85.1】**：上面这句「A2 不推翻 75.6」**已被 D 自己超越**——D 在裁定 84§3
  **撤回**了 75.6 的「余量 2.6%」与「97.4%」（理由：`5.80` 与 `27.33` 来自**不同 run、不同口径**，分量之和
  `33.13 ms` **大于**同 run 实测总量 `26.28 ms`，违反 D 自立的 `caliber_transplant_ban`；并新立自查项
  `component_sum_must_not_exceed_measured_total`）。**权威余量 = 19.91%–22.97%**（裁定 84.2/84.8）。
  另 `5.80 ms` 那个渲染分量的出处口径也已在裁定 85.1 改判：**渲染权威值 `172.32` → `136.99` ctrl-steps/s
  = `7.300 ms/步`**（`172.32` 降为 `invalidated_probe_polluted`）。⇒ **本行保留作历史留痕，读者请以本更正为准**；
  A2 的延迟推导**从未使用** `172.32` / `5.80` / `16.5×`（自查见 §14.8）。
- **裁定 75 的可推翻条件核查**：条件 = 「摊薄推理 ≥ 34 ms」。**干净窗 19.604 ms < 34；重载端 31.820 ms 亦 < 34 ⇒ 两端都不触发 ⇒ 75.2/75.3 维持。**
  **注意区分**：触发不了"摊薄推理 ≥34 ms"≠"wall 不超 34 ms"——重载端 wall 45.785 ms 确实超了，**超的是总墙钟、不是推理单项**。
- **分解自洽（同步串行 ⇒ 应可加）**：`env_step_ms + 摊薄推理_ms` vs `wall_ms` 的残差 —— **clean×4 = +1.19%~+2.22%**，
  **rep1 = +6.65%~+7.15%** ⇒ 干净窗下"env + 推理 ≈ wall"成立（残差 ~1%，即零重叠，与 `async_overlap=false` 一致）；
  **重载端残差放大到 ~7%，这条残差本身可以当污染的第二判据**。
- **裁定 82.5 的 caveat 照带**：`mean_loop_fps` / `env_step_fps` / `t_render_s` **受影响**（egl/GPU 下 wrist 相机不逐位可复现、`raw_first` 臂渲染速率被抬高 `8.3%`）；
  **`t_infer_s` 与摊薄推理不受影响（推理不经 GL）** ⇒ 本节作为主判据的 `wall_ms/step`、摊薄推理、`budget_fraction` **不带 82.5 的 caveat**。
  适用性**按实测 `GL_RENDERER` 判、不按 `MUJOCO_GL` 判**（裁定 71，83§5 已升为跨线规则）。

### 13.2 裁定 83§5 的 A2 澄清项：`policy_executed` 的**定义**（已写进产物，裁定 50.1）

- **D 指出的不一致成立，A2 认**：`latency_quiet_window_rep1.json` 顶层 `policy_executed=false`，而 `closed_loop.policy_executed=true`、
  同产物 GPU 实测 `14,990 MiB`、`closed_loop.arms.*.t_infer_s` 在册 ⇒ 自相矛盾；而 A2 在申报里写的是 `true` ⇒ **申报值与产物字段不一致**。
- **真因不是取值错，是缺一步重算**：顶层字段在 build 期写死 `False`，臂跑完后**从未被重算**。
- **A2 采读法 A**：`policy_executed` = 「**由策略权重驱动的前向推理，且其输出被用于 `env.step()`**」；
  **读法 B**「以产出任务结果为目的执行策略」**归 `capability_claim` / `success_metrics_collected`**（恒 `false`，裁定 46）。
  **为什么不合并**：若定义成读法 B，则 `closed_loop` 臂写 `true` 就等于同时声称"在做任务、有结果"⇒ **放大**能力主张的误读面。
- **落地**（`scripts/a2_egl_latency_remeasure.py` **1071→1171 ln**、`ded5ffa39660`→**`7e53558498ab`**）：
  `POLICY_EXECUTED_DEFINITION` 逐字进每份产物（`--selftest` 产物也带）、顶层值臂后按 **OR** 重算、
  新牙 `gates.policy_executed_consistency`（**缺模式级证据时不许静默判绿**）；
  **自检 9/9 → 13/13**（新增 **M4a** 喂入 rep1 同型缺陷 ⇒ 红、**M4b/M4c** 绿见证（裁定 83.2）、**M4d** 无证据 ⇒ 红）。
  旧自检产物**改名留档不覆写**：`selftest.json`(9/9、`388d78c05182`) → `selftest_20260929_2350_pre83s5.json`。
- **S4a 侧的取值不同、不得互搬**：S4a 验证产物 **`policy_executed=false`**（stub 策略 + 真实 env 的**接线验证**，没跑过真模型）。

### 13.3 §12.7 的待裁项 **20 / 21 已被裁定 83§5 裁完**

| # | 事项 | 裁定 | 落地 |
|---|---|---|---|
| 20 | `prime_mode` | **83§5① = `hold`**，进 `representation_version` | 产物 `status` 由 `proposed` → **`ruled_83_5_1`**；G13 证明两案行为不同 |
| 21 | `timeout_isolation_scope` | **83§5② = `td_only`**（**D 改 A2 的保守默认**），标 `d_selfconfirmed_pending_user_ratification` | `TIMEOUT_ISOLATES_BC` **True→False**；`representation_version` 含 **`timeout_bc=kept_flagged`**（token 由常量派生）；BC 记录带 **`truncated_by_timelimit=true`**；**新闸 G18**（10 项 checks + 7 条红牙 + 绿见证）+ 4 个产物级变异体 G18a–d；**验证 17/17→18/18、变异体 19/19→23/23、`exit 0`** |

- **A2 已按 D 给的可推翻条件逐条查过 v4 原文：未找到明文禁止**，反找到 **8 处正面支撑**
  （附录一 `aae20ffe604f`/433 ln 的 `:241`「非终局超时不冒充 `done=1`」+ `:332`(T12)「原始帧保留」+ `:388`(T35)「**BC质量与TD资格分开**」；
  开发技术方案 `0a9a2092e18a`/418 ln 的 `:239`/`:241`「**BC 可信标签 mask、实际执行 mask、TD 资格是三种不同条件**」；
  异步附录 `a6ab42165ab3`/354 ln 的 `:215`/`:228`「超时属中断／删失，**不因此把后续价值设为零**」/`:235`）⇒ **A2 按裁定执行，不请求回退**。
- **一条如实登记的口径差**：v4 这些句子里的「超时」多指**槽级**（推理超时／deadline miss／失联／接管），
  而本开关管**回合级** gym TimeLimit（300 步 / 10.2 s）⇒ 属**原则迁移**，A2 **不把它放大成「v4 逐字允许」**。
  回退成本 = 翻 `TIMEOUT_ISOLATES_BC=True` 一行，版本串 token 自动变 `isolated`。
- **给 B2/C2 的点名（不代做）**：`harness/data_bridge.py` 的 `SAMPLE_COLUMNS`（`:657`–`:663`）**没有**
  `truncated_by_timelimit` / `bc_kept_flagged` / `timeout_isolation_scope` 三列。**那不是 A2 的文件、A2 不动它**；
  但 `td_only` 生效后 BC 侧开始收 timeout 局 ⇒ 这三列必须在数据桥侧补上，否则硬约束① 在跨文件处断链。
  详见 `docs/a2_s4_vla_runtime_interface_20260929.md` **§12.4**（含 `TrainingView.isolation_reasons` 是**并集**的读法陷阱）。

### 13.4 本轮 A2 的文件面（供 B2 代提交；`runs/` 被 `.gitignore:12` 排除 ⇒ 证据只在 NFS）

| 文件 | 变化 | sha256-12（**A2 自行重算**，裁定 83§7） |
|---|---|---|
| `harness/vla_runtime.py` | 772 → **932 ln** | `a42a3dd17c47` → **`1a75f6181a36`** |
| `scripts/a2_s4a_vla_runtime_verify.py` | 1282 → **1394 ln** | `6f4ed1228a4c` → **`a1959aaf97a4`** |
| `scripts/a2_egl_latency_remeasure.py` | 1071 → **1171 ln** | `ded5ffa39660` → **`7e53558498ab`** |
| `docs/a2_s4_vla_runtime_interface_20260929.md` | 573 → **692 ln**（+§12） | `216ea6e20218` → **`54a39a13cd68`** |
| `docs/a2_pi05_sim_readiness_20260929.md` | 982 → **1089 ln**（+§13） | 改前 **`5da5abddef95`**；**改后本文件不自引 sha**（自引会自我失效：写下 sha 的那次编辑本身就改变了 sha）⇒ **以 `daily_report.md` §14 的文件面表为权威** |

- **新增/改名留档产物**：`latency_quiet_window_rep{3,4,5}.json`、`selftest.json`(13/13)、
  `s4a_verification.json`（00:48:59、18/18 + 23/23）；改名留档 `selftest_20260929_2350_pre83s5.json`、
  `s4a_verification_20260929_2351_pre83s5.json`（`45a1850fdde8`）。
- **冻结面**：`harness/contracts.py`(`96c99ead93d2`)、`harness/runtime_adapter.py`、`configs/` **未触碰**
  （`git status --porcelain` 对三者**空输出**，00:49 复核）；`harness/ledger.py`(`2a33c3f5516e`) 只 import。
- **GPU 销账**：`2026-09-30 00:28:21` 实测 `0 MiB / 0 %`、compute apps **空** ⇒ **E 的 GPU HOLD 已可解除**（见 `daily_report.md` §13.0）。

### 13.5 本节**不声称**

- **不声称「异步实时闭环」**：`async_overlap=false`（裁定 83§5④）⇒ `realtime_ratio 1.2770` 只是**同步串行环**的 `control_timestep ÷ wall`；
  `timing_report().realtime_closed_loop_claim` 仍**恒 `false`**，G17a 的牙保留。
  **裁定 84§6 已解除裁定 75 对「实时闭环」措辞的禁令，但严格限定范围** ⇒ **现在可以写**「主线 `n_replan=25` 的**同步闭环在预算内**」
  （须带完整口径 + `loadavg` 三点 + `nr_throttled` 对；A2 采用的那一句见 §13.6 与 `docs/a2_s4_vla_runtime_interface_20260929.md` §12.7）；
  **仍然禁止写**任何「异步重叠 / 线程并发 / async 实时闭环」的声明。见 §13.6。
- **不声称任何成功率 / 能力**（裁定 46）：本轮全部产物 `success_metrics_collected=false`、`capability_claim=false`。
  延迟臂的 `policy_executed=true` 的正当理由 = **推理延迟本身是被测对象**（裁定 59-②）。
- **不声称 rep1 可作权威**：它被 A2 自己的运行时采样判成 `contaminated=true`（裁定 73），**只作重载端趋势参考**；
  归因强度只写 **`inferred_from_pid_and_timeline`**，不写 `confirmed`（裁定 76.1）。
- **不声称 `td_only` 已被用户追认**（`d_selfconfirmed_pending_user_ratification`）。
- **不声称 S4b 可做**：blocked on C2 的 `harness/env_gym_aloha.py`（裁定 62），且裁定 83§5⑤ 已把前置**正式挂到 C2 线**、排在 T-C2-1 主线 stats 之后。

---

## 13.6 裁定 84（00:3x）的 A2 侧回流：**76.4 已闭合** · 「同步闭环在预算内」解禁 · 84§4 两条新规则 A2 已自合规

### 13.6.1 D 的判定（A2 逐条对账，**无异议**）

| 裁定 84 | D 的判定 | A2 的对账 |
|---|---|---|
| §0 | **rep4/rep5 = 权威**、rep2/rep3 = **旁证**、rep1 = **不采纳**；采纳 A2 自己的权威指定与两条理由；**「A2 本可主张 4 个 rep 都权威，这是高诚信行为」** | 与 A2 §13.1 的自判**逐字一致** |
| §1 | `n_replan=25` **STANDS**，依据由「v4 合规（唯一）」升级为「**v4 合规 + 实测可行（双重）**」；余量权威值 **19.91%–22.97%**；`n=50` 仍驳回，且**驳回理由是「结构」不是「延迟」**（`H≥2n`，E 段 `[50,100)`、D 段 `[50,50)` 双空） | 一致。**A2 补一条**：`gates.v4_H_ge_2n` 已是机器闸（实测 `n=50 satisfied=false` / `n=25 true`）⇒ 这条结构判据**不再依赖人工引用 v4 行号** |
| §2 | **污染幅度首次被量化**：rep1 相对干净窗 `loop_fps` 压低 31.2%–52.7%、`budget_fraction` 抬高 68.3%–116.8%、**`all_episodes_within_per_step_budget` 极性反转** ⇒ 若采纳污染数会得出「必须降 n」的**相反结论** | 一致。**A2 补一条同型证据**：分解残差（`env + 摊薄推理 − wall`）在干净窗 **+1.19%~+2.22%**、在 rep1 **+6.65%~+7.15%** ⇒ **这条残差本身可以当污染的第二判据**（独立于 cotenant 采样） |
| §3 | **D 撤回自己裁定 75.6 的「余量 2.6% / 97.4%」**（第 10 次同型错误：跨 run/跨线分量相加，且分量之和 33.13 ms > 同口径实测总量 26.28 ms）；新立自查项 `component_sum_must_not_exceed_measured_total`；并**取消「轻载/重载并列报」的额外测量成本**（实测 `budget_fraction` 在 `loadavg_1m` 25.17–72 全区间几乎不变） | A2 **不据此删负载对**：`loadavg` 三点 + `nr_throttled` 对**照带**（D 自己也写了"纪律不变"）。**A2 的 §13.3 两端并列表保留**，但**改标性质**：它不再是"必须补的测量"，而是**已完成的负载敏感度证据**（且 rep1 是 `contaminated`、只作趋势） |
| §4 | A2 的 `policy_executed` 澄清项**闭合、D 销账**；字段拆法**升为两条全线规则** `boolean_field_reading_must_be_declared` + `top_level_aggregate_must_declare_semantics`；**A2 自发实现 83.2 的 `green_witness_required`，D 记功** | **A2 已按两条新规则让自己的产物先合规**（见 §13.6.3） |
| §5 | **E 的 GPU HOLD 解除**；持窗者 = E；**窗内 A2 禁止启动任何 GPU 进程**（含会触卡的 `--selftest`）；A2 若需上卡须写申报行并等 E 销账 | A2 **遵守**：E 已于 **00:50:48** 销账（`daily_report.md` §E11.0）；A2 在 00:50:48 之后的全部验证都是 **CPU 臂**（`gpu_used=false`、`GL_RENDERER=llvmpipe`），**未触卡**（01:0x 复测 `nvidia-smi` = `0 MiB` / compute apps 空） |
| §6 | **解除**裁定 75 对「实时闭环」措辞的禁令，**严格限定**：可写「同步闭环在预算内」（带完整口径），**仍禁**「异步重叠/线程并发/async 实时闭环」 | **A2 照办，且只照办被解除的那一半**：`realtime_closed_loop_claim` **仍恒 `false`**（它承载异步语义）、G17a 的牙保留 |
| §7 | A2 待办：① 补 §13（销账读数行 + 定义澄清回流段）；② 两份 `WHY_ARCHIVED.md` 的**绝对路径**；③ **76.4 已闭合、不必再跑 quiet-window**；④ S4b 等 C2；⑤ 上卡须申报 | **① 已完成但 D 未见到**（D 的 before 影像停在 **5153 ln / `85f396771aa6`**，A2 的 §13 落在 **5155–5257**）⇒ 见 §13.6.2；**② 见 §13.6.2**；③④⑤ **遵守** |

### 13.6.2 D §7-① / §7-② 的直接回答（**都是"已交付、请核路径"**，不是"待做"）

- **①「补 §13：rep4/rep5 的销账读数行 + 定义澄清回流段」⇒ 已在盘上，D 的 before 影像没覆盖到**：
  - **销账读数行** = `daily_report.md` **`:5157`–`:5159`**（§13.0 标题行 + 读数行）：
    **「`2026-09-30 00:28:21` 实测：`nvidia-smi` = `0 MiB / 0 %`、`--query-compute-apps` = 空；`loadavg = 26.88 / 25.89 / 28.17`；`nr_throttled = 13,562`（`nr_periods 506,603`）」**
    ⇒ **A2 自己的销账读数，不是 D 00:33:09 的代测**（裁定 50.1「记录 ≠ 上报」A2 认，故本行是 A2 实测的）。
  - **定义澄清回流段** = `daily_report.md` **§13.6**（**标题行 `:5227`**、正文首条 `:5229`；A2 于 `01:1x` 用 `grep -n "^### §13\.6"` 复核过，原稿写的 `:5229` 是正文首条而非段首 ⇒ 按裁定 64「只有行号的引用不可核验」就地改正）+ 本文 §13.2 + `docs/a2_s4_vla_runtime_interface_20260929.md` **§12.5**。
- **② 两份 `WHY_ARCHIVED.md` 的绝对路径**（裁定 78.6；**A2 于 01:0x 实测 `ls -la` + `sha256sum`**）：
  | # | 绝对路径 | 字节 | mtime | sha256-12 |
  |---|---|---|---|---|
  | 1 | `/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/runs/vla/a2_env_pi05_sim_20260929/manifest_run1_probe_false_red/WHY_ARCHIVED.md` | 2388 | `2026-09-29 23:32` | **`0027df8bab78`** |
  | 2 | `/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/runs/vla/a2_env_pi05_sim_20260929/manifest_run2_dist_drift_false_red/WHY_ARCHIVED.md` | 2980 | `2026-09-29 23:32` | **`dff71fd7f31e`** |
  | 3（附带） | `/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/runs/vla/a2_env_pi05_sim_20260929/manifest_run3_v10_pep610_false_red/WHY_ARCHIVED.md` | —— | —— | **`a4086f3885f2`** |
  **⇒ 裁定 72 的 `false_red_archival_format` 唯一模板实例现有 3 份**（run1/run2/run3 各一），第 3 份是模板本身。

### 13.6.3 裁定 84§4 的两条新全线规则：**A2 自己的产物先合规**（不是只写在文书里）

| 规则 | 承载物 | 落地 | 验证（**都跑过、都 `exit 0`**） |
|---|---|---|---|
| ① `boolean_field_reading_must_be_declared` | `POLICY_EXECUTED_DEFINITION` | 逐字进**每份**延迟族产物（含 `--selftest`） | `gates.policy_executed_consistency` + 自检 **M4a–M4d** ⇒ `selftest.json` **13/13** |
| ② `top_level_aggregate_must_declare_semantics` | `AGGREGATE_FIELD_SEMANTICS`（**两个脚本各一份**） | 逐字进产物顶层：延迟族 **13** 键、S4a 验证 **10** 键 | **S4a：18/18 闸 + 23/23 变异体有牙、`exit 0`、`generated_at=01:05:17`**；**延迟族：CPU `env_only` 代码路径核查 `exit 0`、7/7 闸绿**（`latency_code_path_check_aggsem_cpu_llvmpipe.json`） |

- **②的验证为什么用 CPU 臂**：裁定 84§5 明令「**窗内 A2 不得启动任何 GPU 进程（含会触卡的 `--selftest`）**」，
  且裁定 84§7-③ 明令「**76.4 已闭合、不必再跑 quiet-window**」⇒ **A2 不开 GPU 窗**。
  该核查臂**不带 prefix** ⇒ 实测 `renderer_class=mesa_cpu_software`、`GL_RENDERER=llvmpipe (LLVM 15.0.7, 256 bits)`、
  `gpu_used=false`、`env_step_fps=10.091`。**这是代码路径核查，不是延迟测量**；它的 `env_step_fps` 属 **CPU 软渲染口径**，
  **不得与 §13.1 的 GPU 干净窗数字互搬**（裁定 46.4/53.6/71）——产物内已带 `cross_transport_ban` 与 `retro_label`。
- **`as_of 01:0x` 的文件面（**§13.4 那张表已过期，原文不删**）**：
  | 文件 | 行数 | sha256-12 |
  |---|---|---|
  | `harness/vla_runtime.py` | **932** | **`1a75f6181a36`**（§13.4 之后**未再改**） |
  | `scripts/a2_s4a_vla_runtime_verify.py` | **1443** | **`d708cbc6773f`**（§13.4 的 `1394 / a1959aaf97a4` 已过期） |
  | `scripts/a2_egl_latency_remeasure.py` | **1223** | **`b26f3df785f6`**（§13.4 的 `1171 / 7e53558498ab` 已过期） |
  | `docs/a2_s4_vla_runtime_interface_20260929.md` | **748** | **`490411105046`**（+§12.7、三处 `as_of`） |
- **⇒ 一个必须处理的后果（A2 主动做了，不等 D 提醒）**：裁定 84§0 引用了 **`7e53558498ab`** 作为 rep4/rep5 的 `generator_sha256_12`，
  而 A2 现在改了这个生成器 ⇒ **磁盘上不再有那个字节串**，正是裁定 83.5 点名的首起「**被引用字节串灭失**」同型风险。
  **处置**：改之前把被引用的三份生成器**逐字节留档**到
  `runs/vla/a2_egl_latency_20260929/generator_archive/{a2_egl_latency_remeasure.7e53558498ab.py, vla_runtime.1a75f6181a36.py, a2_s4a_vla_runtime_verify.a1959aaf97a4.py}`
  （**留档后 `sha256sum` 复核 = `7e53558498ab` / `1a75f6181a36` / `a1959aaf97a4`，与文件名逐字对应**），
  附 `WHY_ARCHIVED.md`（`8c6585b5a512`，40 ln，写明**这不是作废档**：三份副本没有一份是错的，只是不再是当前版）。
- **改名留档（不覆写）清单**：`selftest.json`（13/13、`35c968718fce`）→ `selftest_20260930_0023_13of13_pre_aggsem.json`；
  `s4a_verification.json`（00:48:59、18/18、`73c25b3eec0f`）→ `s4a_verification_20260930_0048_18of18_pre_aggsem.json`；
  更早的 `s4a_verification.json`（23:51:03、17/17、`45a1850fdde8`）→ `s4a_verification_20260929_2351_pre83s5.json`。

### 13.6.4 A2 现在**没有**在等的东西 / 仍然 blocked 的东西

- **不等 GPU**：76.4 已闭合（裁定 84§7-③），A2 **不再申请 quiet-window**；后续如需上卡（S4b 真模型臂）会按 84§5 写申报行并等当时持窗者销账。
- **仍 blocked**：**S4b**（outcome 四类判定 + 真模型臂）—— 裁定 83§5⑤ 已把前置**正式挂到 C2 线**、排在 T-C2-1 主线 stats 之后。
  **A2 观察到的进展（如实报，不替 C2 定性）**：`harness/env_gym_aloha.py` **已在盘上**（01:0x 实测 **579 ln / `6c4d71eb732e` / mtime `2026-09-29 22:09`**），
  且 C2 在 `runs/vla/c2_norm_contract_20260929/gate/run_20260930_003414/`、`run_20260930_004116/` 有带变异体的闸运行
  ⇒ **裁定 62 的那把锁正在被 C2 打开，但 A2 不据此自行开跑 S4b**（顺序归 D，且裁定 84§7-④ 明写「S4b 等 C2」）。
- **仍待用户事后追认**：`timeout_isolation_scope = td_only`（`d_selfconfirmed_pending_user_ratification`）。
  **A2 已把 D 给的可推翻条件查完并给出结论：未触发**（v4 无明文禁止、反有 8 处支撑；但**槽级 vs 回合级的口径差如实登记**，见 §13.3）。

---

## 14. 本轮增补（**2026-09-30 01:2x–01:5x**）：裁定 85.0 的**三网红线**已落地 —— 占卡探测器从「一网半」升级为「三网」，**复用 E 的 `card_busy()`、不重造**

**as_of**：`2026-09-30 01:5x`。本节全部为 **CPU 臂**验证（`gpu_used=false`、`GL_RENDERER=llvmpipe`），**未触卡、未占窗**。

### 14.1 为什么必须改（A2 认这个缺陷，且它是 A2 自己的）

- **根因**：`nvidia-smi --query-compute-apps` **只列已分配显存的 compute 进程**。对 ①**EGL 图形上下文**、②**已起跑但尚未分配显存**的进程（π₀.₅ 的 `from_pretrained` 要 60–185 s 才真正分配），它返回**空**。
- **A2 侧的后果**：`scripts/a2_egl_latency_remeasure.py` 的占卡判据是 `--query-compute-apps` + `ps`（旧 `:135`）⇒ **rep4/rep5 把 B2 的 EGL 图形负载判成了「卡空」**。E 于 `00:42:53` 独立实测该负载：持 `/dev/nvidia2`+`/dev/nvidiactl`、util/mem = **11% / 102 MiB**，而 compute-apps = **空**。
- **D 的处置（裁定 85.0-2-②）**：rep4/rep5 的 `contaminated=false` **重判为** `contaminated=undetermined_detector_blind_to_egl`（rep5 另加 `unexplained_start_mem_102MiB`）。**数值带不变（`0.7703–0.8009`）、只有标签变**（§20.2 给了三条理由，A2 复核认）。
- **A2 对自己那句"记功"的限定**：D 记功的那句「闸以 compute apps 为键、不以显存余量为键」出自 A2 §13.1，**它当时是一句自我辩护**（解释 A2 为何不因显存未回收而拒绝起跑），A2 写它时**没有意识到它会暴露探测器盲区** ⇒ 它是「如实登记」的附带产物帮了 D，**不是 A2 主动做的盲区分析**。A2 不把这条记功说成自己有预见性。

### 14.2 落地了什么（`scripts/a2_egl_latency_remeasure.py` **1223→1820 ln**、`b26f3df785f6`→**`7ead22591a63`**）

| # | 改动 | 位置 | 说明 |
|---|---|---|---|
| 1 | **复用 E 的探测器**：`_load_e_calib_module()` | **`:136`** | `importlib` 载入 `scripts/e_mainline_render_calib.py`，**不复制 E 的代码**（裁定 85.0-2-① 明写「复用 E 的实现口径，不重造」；抄一份 = 两处定义漂移，裁定 46.4 的根因）。三网的口径常量 `THREE_NET_RULING` 在 **`:174`** |
| 2 | **被复用件的身份钉进产物**：`module_identity()` | **`:153`** | 落 `path / sha256_12 / n_lines_wc_l / bytes / loaded_from / reuse_not_reimplemented`。**行数口径 = `wc -l`**（数换行符）——A2 原先写的 `count("\n")+1` 对以换行结尾的文件**多算 1 行**（E 的件实测 `wc -l`=1162 而旧公式给 1163），已就地改正并把口径写进字段名 `n_lines_wc_l` |
| 3 | **三网读数归一**：`three_net_snapshot()` | **`:218`** | 一次拿齐裁定 85.7-2-① 要求的**三项读数**：`n_compute_apps` / `n_foreign_fd_holders`（+ PID 列表）/ `memory_used_mib`，另加窄档 `n_other_line_gpu_intent` 与宽档 `n_other_line_script_wide` |
| 4 | **自致假阳防护**：`drop_own_descendants()` | **`:198`**（`_ppid_of()` 在 `:190`） | `nvidia-smi` 自己会短暂持 `/dev/nvidiactl` ⇒ 不剔会让 fd 网把**采样器自己的子进程**当"别人"，闸恒忙、永远拒绝开跑（与 RR-B2-18「恒真 ⇒ 狼来了」同族，裁定 85.6-2）。E 的 `_own_tree()` 只覆盖**自身+祖先**、**不覆盖子进程** ⇒ 这一段是 A2 侧必须补的；**覆盖深度如实登记 = 1 代**（`nvidia-smi` 不派生孙进程） |
| 5 | **yield 闸三网化**：`three_net_yield_gate()` | **`:256`** | 8 个 check（三网各自零命中 + `memory.used==0` + 三项声明齐全）。**缺证据不许判绿**：`snap is None` ⇒ `ok=False, refuse=True`（与 `classify_cotenant` 同一条纪律）。`main()` 在**起跑前**调它（`:1500`），`refuse` ⇒ 打印三网读数 + `exit 4`，**臂不起跑、不产生任何延迟数字** |
| 6 | **运行时采样器三网化** | class **`:366`**、`__init__` **`:389`**、`_one_sample` **`:405`**、`evidence` **`:492`** | `RuntimeCotenantSampler` 新增 `calib=` / `three_net_strict=`；**每个样本**额外落一次三网读数 + `memory.used`。**开销不预先声称百分比**：旧 docstring 那句「开销 <5%」是**一网时代**的估算、三网后已不成立 ⇒ 改为实测登记（`scan_overhead_s_max/_mean`；本次实测 **max 0.0738 s / mean 0.0675 s**，间隔 1.0 s） |
| 7 | **污染判据并列两条 + OR 汇总** | **`:1702`–`:1723`** | 不改 `classify_cotenant`（它在**被复用的既有件** `scripts/a2_artifact_amendments_20260929.py` 里，改它会连带改动它已写进历史产物的判据语义，裁定 72）⇒ **并列**：`classification`（一网）+ `classification_three_net`（三网）+ `contaminated_final`（**OR、就地重算、不留初值**，裁定 84§4）。**单调性：只会更严、不会更松**（任一 True ⇒ True；无 True 但有 unknown ⇒ unknown；**永不由 unknown 降为 False**） |
| 8 | **新闸** `gates.three_net_detector_85_0` | 函数 **`:818`**、挂进 `extra_gates` 在 **`:1748`** | **9 个 check**。它守的**不是**"卡上有没有人"，而是"**用来判断卡上有没有人的那个探测器是不是三网**"——即 rep4/rep5 被降级的那个根因 |
| 9 | `AGGREGATE_FIELD_SEMANTICS` **+5 键**（13→18） | **`:790`–`:815`** | 按裁定 84§4 给每个新汇总字段声明聚合语义（`AND` / `OR（严格化）` / `count（逐网分别计数、不合并）` / `max` / `mean+max`） |

**行号口径**：上表行号 = A2 于 `01:5x` 对 **1820 ln / `7ead22591a63`** 那版用 `grep -n "^def …"` 实测；改文件后须重测（裁定 64：只有行号的引用不可核验 ⇒ 每行都配了函数名/字段名作二次锚点）。

### 14.3 牙：**M5 族 14 个变异体**（自检 **13/13 → 27/27**，`exit 0`，`gpu_used=false`）

- **红见证 11 条**：**M5a**（**fd-_only** 命中：compute-apps=0 + fd 网=1 + `102 MiB` ⇒ 拒绝，**这就是 rep4/rep5 的盲区本体**）、**M5b**（cmdline 窄档命中 ⇒ 拒绝）、**M5d**（`snap=None` 缺证据 ⇒ 拒绝，不许判绿）、**M5e**（**探测器退化成一网 ⇒ 即使读数全空也判红**：红的是探测器、不是探测结果，这条正是新红线本身的牙）、**M5f**（未记录被复用件身份 ⇒ 红）、**M5g**（`memory.used=102≠0` 且未解释 ⇒ 拒绝，裁定 85.11 `unexplained_nonzero_reading_must_block_clean_claim`）、**M5h**（污染判据：fd-_only**必须**翻成 `contaminated_three_net=True`，而一网视角会说 `False`）、**M5i**（无样本 ⇒ `unknown_not_collected`，**不许** false）、**M5k**（**产物级**：把一份 rep4/rep5 同型的旧产物喂给 `three_net_detector_gate` ⇒ **9 个 check 全红**）、**M5m**（`contaminated_final` 留初值 `None` ⇒ 红）、**M5n**（`contaminated_final` 与两条子判据的 OR 不符 ⇒ 红）。
- **绿见证 3 条**（裁定 83.2 `green_witness_required`）：**M5c**（三网全空 + `memory.used=0` ⇒ 判绿；**否则闸恒忙 = 狼来了**）、**M5j**（宽档命中 ⇒ yield 闸拒绝**但**污染判据**不**自动翻转，证明"宽/窄档切分"确实如声明实现）、**M5l**（三网齐全的新产物形状 ⇒ 判绿，证明 M5k 的红不是恒真）。
- **`unidirectional_by_design=false`** 已在闸里显式声明。

### 14.4 一条**口径切分**，A2 显式登记、D 可推翻

- **宽档（任何他线脚本 `scripts/{a,a2,b,b2,c,c2,d}_*`）只喂 yield 闸（`strict=True` ⇒ 拒绝开跑），不喂事后污染定性。**
- **理由**：一条**纯 CPU** 的他线脚本不是 GPU 共租者。把宽档当污染判据 ⇒ 本机基线 load 就有 18–27、四线并行是常态，**每一批都会被标污染**，标记失去信息量（这正是 D 在裁定 85.6-2 里认定的 RR-B2-18「恒真 ⇒ 狼来了」缺陷）。
- **计入污染的**：compute-apps 命中 ∪ **fd 网**外来持有者 ∪ cmdline **窄档** GPU 意图。**fd 网这一项就是 rep4/rep5 缺的那一项。**
- **A2 不自决**：这条切分写进产物字段（`three_net.wide_net_hits_do_not_auto_contaminate=true` + `wide_net_split_rationale`）与闸 check（`wide_narrow_split_declared`），**D 若要改成"宽档也算污染"，翻一个常量即可，A2 不预先写那个分支**。

### 14.5 CPU 臂验证产物（**不是延迟测量，不得与 §13.1 的干净窗互搬**）

- `runs/vla/a2_egl_latency_20260929/selftest.json`：**27/27**、`all_ok=true`、`18,208 B`、sha256-12 **`23b3515d3793`**、`generated_at=2026-09-30T01:47:xx`、`gpu_used=false`、`policy_executed=false`、`capability_claim=false`、`success_metrics_collected=false`；内含 `three_net_detector.detector_module`（**真实**身份：`scripts/e_mainline_render_calib.py` / **`2d1320672224`** / `n_lines_wc_l=1162` / `73,807 B` / `has_card_busy=true`）。
- `runs/vla/a2_egl_latency_20260929/latency_three_net_code_path_check_cpu_llvmpipe.json`：**42,258 B**、sha256-12 **`6cd88a079a76`**、`generated_at=2026-09-30T01:48:31+08:00`、`gates_all_ok=true`（**8/8 闸绿**，含新闸 `three_net_detector_85_0`）。
  - **口径（必须随数字走）**：`renderer_class=mesa_cpu_software`、`GL_RENDERER=llvmpipe (LLVM 15.0.7, 256 bits)`、`MUJOCO_GL=egl` **无 prefix** ⇒ **这是 CPU 软渲染的代码路径核查，不是延迟测量**；其中 `env_step_fps=9.177` 与 §13.1 的 GPU 干净窗（`n=25` `wall 26.635 ms`）**不得互搬**（裁定 46.4 / 53.6 / 71）。
  - **三网实测读数（起跑前，`strict=True`）**：`n_compute_apps=0` / `n_foreign_fd_holders=0` / `memory_used_mib=0`；4 个周期样本**全部**带三网读数（`n_samples_missing_three_net_reading=0`、`three_net_errors=[]`）；`contaminated_final=false`（一网 false OR 三网 false）。
  - **负载对**：`loadavg 18.82 / 19.66 / 22.32`（前）→ `18.82 / 19.66 / 22.32`（后）、`Δnr_throttled = 0`；`scan_overhead_s`（起跑前那一次三网扫描）= **0.0914 s**。
  - **窗口纪律**：本臂**未触卡**（`gpu_used=false`、`memory.used=0`），起跑时 B2 的 §B2-9 短窗申报在册但其作业当时不在卡上 ⇒ **A2 未行使 85.7-2 的优先级、未与 B2 抢卡**。
- **一次失败尝试也如实登记**：A2 于 `01:48:04` 先用 `MUJOCO_GL=disable` 起跑（**A2 自己选错了环境变量**，抄了 B2 导出器的口径）⇒ `dm_control` 抛 `RuntimeError: No OpenGL rendering backend is available.`、`exit 1`、**未产生任何产物**（臂在 `env.reset()` 就断了）。日志 `tmp/a2/yield_gate_live_refusal.log`。⇒ 随后改用 `MUJOCO_GL=egl`（无 prefix ⇒ llvmpipe）重跑，才是上面那份产物。**这一次失败没有污染任何数字，也没有留下半成品产物。**

### 14.6 本轮文件面（增量，供 B2 代提交；`runs/` 被 `.gitignore:12` 排除）

| 文件 | 行数 | sha256-12 | 变化 |
|---|---|---|---|
| `scripts/a2_egl_latency_remeasure.py` | **1820** | **`7ead22591a63`** | 1223→1820 ln（三网红线）；before 影像 `/tmp/a2_latency_before_threenet.py`（**`b26f3df785f6`**） |
| `docs/a2_pi05_sim_readiness_20260929.md` | **本文末** | 见 §14.7 | +§14（本节） |

- **改名留档（不覆写）**：`selftest.json`（13/13、`fdb6ba4a3e4c`）→ `selftest_20260930_0103_13of13_pre_threenet.json`；（27/27 中间态、`pre_detid`）→ `selftest_20260930_0131_27of27_pre_detid.json`；（27/27、`pre_wclfix`）→ `selftest_20260930_0133_27of27_pre_wclfix.json`。**⇒ 当前 `selftest.json` = 27/27 / `23b3515d3793`。**
- **冻结面**：`harness/contracts.py`（`96c99ead93d2`）、`harness/runtime_adapter.py`、`configs/` **未触碰**；`harness/ledger.py`（`2a33c3f5516e`）、`harness/data_bridge.py` 只 import。`git status --porcelain` 对五者**空输出**（`01:5x` 复核）。
- **跨线依赖如实登记**：本脚本现在 **import E 的 `scripts/e_mainline_render_calib.py`**。这是**裁定 85.0-2-① 明令要求的复用**，它推翻了本文 §「硬约束」里 A2 早先那条「不 import E 的文件，避免跨线耦合」的自律（那条自律**只对 `boundary_guard` 一项仍然有效**）。**后果如实说**：E 若改动 `card_busy()` / `OTHER_LINE_SCRIPT_RE` / `GPU_INTENT_PATTERNS`，A2 的闸口径会跟着变 ⇒ **A2 用 `module_identity()` 把被复用件的 sha256-12 钉进每份产物**，使"复用的是哪一版"永远可核、漂移可被发现。**请 E 改动该文件时知会 A2（不阻塞 E，只是让 A2 能重跑自检）。**

### 14.7 本节**不声称**

- **不声称** rep4/rep5 的清洁认证已恢复：它们的标签仍是 `undetermined_detector_blind_to_egl`，**解除条件是 §20.3-② 的「三网清洁证书 rep」**，而那个 rep **需要上卡**（P2，排 B2 formal 间隙）⇒ **本节没有解除它**。
- **不声称**任何延迟/吞吐数字：本节唯一的 `env_step_fps=9.177` 是 **CPU/llvmpipe** 口径的代码路径核查产物。
- **不声称**三网探测器在**真卡负载**下已被 A2 亲验：M5 族喂的是**合成读数**（`gpu_used=false`），活见证只到「起跑前三网读数全零 + 4 个样本齐全」这一层。**E 已验过真卡上的牙**（`GPU_YIELD_INCIDENT_2358.json` 的 `fix_applied.verification`：M2 双向 + fd 网 + cmdline 网 + 纯 `sleep` 无误报 + 扫描开销 0.08 s），A2 复用其口径但**不把 E 的验证说成 A2 的验证**。
- **不采成功率**（裁定 46）；**不声称异步实时闭环**（`async_overlap=false`、`realtime_closed_loop_claim` 恒 false）。

### 14.8 裁定 85 §20.4「引用限制」的 A2 侧自查（**逐条核过，不是口头遵守**）

| §20.4 的要求 | A2 的自查动作（`01:5x` 实测 `grep -rn`） | 结论 |
|---|---|---|
| **① `all_episodes_within_per_step_budget=true` 与 84.7 的措辞，在拿到三网清洁证书前必须随附 §20.1 的 caveat；84.7 降为 `provisional_pending_three_net_certificate`** | 本文 §13.1 / §13.6.1 与 `daily_report.md` §13.2 / §14.7 是那些数字的落点 ⇒ A2 已在 `daily_report.md` **§14.11 更正 2** 里把 caveat **逐字补齐**（含 B2 窗口重叠时刻、`102 MiB` 签名匹配、`inferred_strong_signature_match`），并把 84.7 标为 `provisional_pending_three_net_certificate`（**不撤回**：可推翻条件「任一清洁窗 `budget_fraction>1`」未触发，4 窗最大 = 0.8009） | **已照办**（caveat 与数字同处一文，不再分离） |
| **② 若在任何延迟推导里用过 `172.32` 或 `5.80 ms`，更正为 `7.300 ms`** | `grep -rn "172\.32\|5\.80\|16\.5×\|136\.99\|7\.300\|env_step_native\|render_3cam_224"` 打在 **A2 的四件**（本文、`docs/a2_s4_vla_runtime_interface_20260929.md`、`scripts/a2_egl_latency_remeasure.py`、`harness/vla_runtime.py`）上：**`172.32` / `16.5×` / `136.99` / `7.300` / `env_step_native` / `render_3cam_224` = 0 命中**；`5.80` **仅 1 处**（本文 §13.4 那行，且是**引用 D 的 75.6 公式作对照**、不是 A2 自己的推导输入） | **A2 的延迟推导从未建立在 E 的渲染吞吐数上** ⇒ 无需更正数值；那 1 处已就地加更正框（见 §13.4）。**A2 的 `env_step` 分量一直是自己实测的**（`closed_loop.arms.*.t_env_step_s` / `env_only.env_step_fps`），不是从 E 搬的 |
| **③ 延迟/实时性主张必须用 w=1 的 `7.300 ms`，不得拿聚合数除 worker 数冒充单 worker 延迟** | A2 侧**不开多进程渲染**（裁定 59-③，`no_multiprocess_rendering=true` 写在每份产物里），也**从不引用 w=2/4/8 的聚合数** ⇒ 该禁令对 A2 无适用面 | **不适用但已遵守**；A2 的 `realtime_ratio` 一律是**单进程同步串行**口径（`caliber=synchronous_blocking_serial`、`async_overlap=false`） |
| **④ 裁定 77.2 的 `workers_cap=8` 保留但依据改了（eff 实测 `1.0/0.975/0.921/0.684`，不是"近线性到 8"）** | A2 不持有 `workers_cap`（它是 B2/C2 的采集与训练并发口径）；A2 侧唯一相关的是**不开多进程渲染** ⇒ 不受影响 | **登记知悉，无 A2 侧动作** |

- **A2 顺带自查了 D 在裁定 85.11 新立的两条规则**：
  - `prose_caveat_adjacent_to_machine_field_is_part_of_the_field`：**A2 认这条正是冲着自己那段散文来的**（§13.1 那句「闸以 compute apps 为键、不以显存余量为键」是散文，而 `mem=102 MiB` 是机器字段，D 在 84.1 只引了字段没引散文）。⇒ A2 的对策已落地：把那句散文限定**升格为机器字段**——现在每份产物都有 `per_batch_gpu_yield_gate.detector_nets`（三网清单）+ `three_readings_required_by_85_7_2`（三项读数）+ `gate.checks.memory_used_mib_is_zero`，**读者不再需要读散文才能知道判据是什么**。
  - `unexplained_nonzero_reading_must_block_clean_claim`：已做成**牙**（自检 **M5g**：`memory.used=102≠0` 且未解释 ⇒ 拒绝开跑），并在 `three_net_yield_gate.checks` 里占一个独立 check。
