# 仿真链 E2E-min 主线重排与口径改判（2026-09-29 21:0x，D）

**性质**：本文件是**主线优先级与口径的权威文书**（裁定 50–54 的正文）。与三份执行单冲突时以本文件为准；本文件与 `RL_Harness_v4_20260924/` 原文冲突时以 v4 为准。
**作者**：D（监管/口径裁定）。**写入面**：本文件（D 单写）+ 共享文书追加。
**触发**：用户 21:0x 三条指令（见 §0）。**本轮 D 只读复核 + 文书，未跑任何 policy、未占用 GPU、未提交 git。**

---

## §0 用户指令原文与 D 的执行口径

| # | 用户指令（原文要点） | D 的执行口径 | 落点 |
|---|---|---|---|
| 1 | 「新开智能体 E，EGL 库安装验证任务交给它」 | 建 **E 线 = GPU 渲染解锁/吞吐线**，任务书已写；**定位为吞吐线，不在正确性关键路径上**，时间盒 + CPU-light | `d_handoff_to_e_20260929.md` |
| 2 | 「仅在推荐单臂仿真，且应该还没有一个完整有效结果，解除只渲单臂不是加重当前实验渲染负担嘛？」 | **成立，D 撤回该项请求**（原欠用户项②）。**单臂限制保持**，并给出机制数字（§1）。**另需澄清作用域**：π₀.₅ 底模形态本身是双臂 14 维（§2） | §1、§2 |
| 3 | 「实机硬件交互也应该在仿真跑通之后再进行，当前急于确认实机采集窗口有什么意义？」 | **成立，D 撤回该项请求**（原欠用户项③）。改为**触发式延期**：触发条件 = E2E-min S5 通过（§1.3）。成熟项目的窗口选取依据**现在不做**，触发时再做一页纸（外部事实一律标 `external_unverified`） | §1.3 |
| 4 | 「一句话，尽快把当前的仿真链 RL-VLA-harness 跑通，再考虑后续」 | 定义 **E2E-min**（对撞 v4 `01_开发技术方案.md:355`），拆成 **S1–S6**，逐段指派 owner + 有牙的出口判据；**其余一律降级或暂停**（§6） | §4–§7 |

**D 的自我批评（写进台账）**：上一轮我把 5 项"只有用户能给的输入"并列上报，其中 ②③ 两项**在主线尚未产出一个完整有效结果时就去要资源**，属于**把下游依赖当成当前阻塞**。用户两条反问都成立。已改为：**凡欠用户的请求项，必须先证明它阻塞 E2E-min 的某一段，否则不进上报清单。**

---

## §1 撤回两项请求 + 单臂限制的机制依据

### 1.1 解除单臂会加重渲染负担 —— 用户判断正确，D 用实测数字确认

| 事实 | 数值 | 出处 |
|---|---|---|
| 渲染瓶颈是**网格面数**，不是分辨率 | 单臂 Piper **183,746 faces / 91,886 verts**；224² 与 480×640 无单调差异（27 个独立子进程复现） | `runs/vla/d_render_probe_20260929/`；A2 在另一套 (venv, mujoco, 模型) 上独立复现同结论：`docs/a2_pi05_sim_readiness_20260929.md:353` |
| 并行度**已撞 CPU 配额顶** | 4 进程效率 0.98；8 进程掉到 0.54，`nr_throttled_delta` 71→407；cgroup 配额 **12 核**（`cpu.cfs_quota_us=1200000`），`nproc=112` 是宿主数不作分母 | `runs/vla/d_render_probe_20260929/parallel_cap.json`；`docs/infra-gpu-render.md` §6.3 |
| ⇒ 双臂 = 每帧几何量约 2× | 面数按臂线性叠加 ⇒ **同分辨率下每控制步渲染开销近似翻倍，吞吐近似减半**；而并行度已无余量可补 | D 推论（`kind=arithmetic_from_measured_inputs`，**非实测**；实测需双臂渲染，已被用户指令禁止 ⇒ 保持推算标注） |
| 当前机器负载 | `loadavg 52.85 / 51.97 / 51.84`、`nr_throttled 2990`、`throttled_time 6951.5 s`（20:31 实测，12 核配额） | D 本轮 `/proc/loadavg` + `/sys/fs/cgroup/cpu/cpu.stat` |

**结论**：解除单臂**只会降低**当前吞吐、且**不产生任何主线证据**（双臂装配能力已在 `runs/vla/d_render_probe_20260929/` 用 `MjSpec.attach` 证过一次，`nq=16`，标 `arms2_archived_only_per_user_directive`）。**单臂限制继续有效，D 不再请求解除。**

### 1.2 单臂限制的**作用域**必须写清（否则会误伤主线）

「只渲单臂」这条指令的**作用对象是 Piper / Cobot Magic 自有资产的渲染验证线**（D 的 `d_render_probe`，已归档）。它**不等于**"仿真代理环境也必须单臂"：

- π₀.₅ base 的形态是 **`aloha_bimanual_14d`**（14 = 2×7），权重 812 张量、3.6168 B 参数已按该形态逐位校验通过：`runs/vla/a2_pi05_contract_20260929/load_verification.json` → `compare.n_bitwise_exact=812`、`n_model_keys_not_covered_by_ckpt=0`、`verdict="all_bitwise_equal"`。
- 仿真代理 `gym_aloha/AlohaTransferCube-v0` 的模型实测 **`nq=23, nv=22, nu=16, ncam=7`**（D 本轮用 `mujoco.MjModel.from_xml_path` 直接读出，`MUJOCO_GL=disable`，未渲染）⇒ **它本身就是一个双臂场景**，不是"我们选择渲双臂"。
- ⇒ **口径裁定**：主线仿真代理**保持 gym-aloha 双臂不动**（这是底模形态的必要条件，不是渲染档位选择）；"单臂"限制**只约束 Piper 资产线**。产物一律带 `morphology` 标签，跨形态数字不得并列（裁定 36.4 / 46.4）。
- **如果用户要求"连仿真代理也换成单臂形态"**，那等于**换底模**（π₀.₅ base 是 14 维双臂；单臂要另选 6/7 维底座并重新验证加载），属**路线分叉**，需用户明确指令 ⇒ 本轮**不预裁、不自行推进**，仅登记为分叉点。

### 1.3 实机采集窗口 —— 撤回，改触发式延期

- **撤回理由**：实机交互在 v4 阶段表里是 **P4「最小实机闭环」**（`01_开发技术方案.md:349`），入口条件是 P1–P3 有可检验证据。当前 P1 连示范数据都还没有（§7 阻塞 B1）⇒ **现在确认采集窗口是提前锁定一个尚未定形的接口**，且会占用用户注意力。
- **触发条件（写死，到期自动回到上报清单）**：**E2E-min S5 通过**（= 同一冻结 checkpoint 的双向"无动作辅助"成功率有区间、失败类型可分类、评分可事后核验，v4 `:357`–`:363`）**且** S6 的一次 RL 更新已产生方向性证据（正或负都算，负则须带诊断）。
- **触发时 D 交付**：一页纸《实机窗口选取依据》，含 ① v4 `:357` 六行报表里**必须现场采到的字段**（人工控制/复位/标奖分钟、必要值守时间、有效小时、连续窗口与停止原因）；② 成熟项目的窗口口径对照（**全部标 `external_unverified`，不与本机实测同表**）；③ 需要先解决的硬件口径冲突清单（夹爪行程三值、J6 的 1.0456 rad 分歧、30/50 Hz，裁定 43）。
- **本轮不做文献检索**：用户指令是"尽快跑通仿真链"，该检索不在关键路径上。

---

## §2 频率口径改判（D 第四次同型自我纠错，必须显式记录）

**原口径（裁定 45，`work/project_parameters.json` → `timing.control_hz`）**：仿真侧控制频率 = **恰好 30.0 Hz**，实现 = 物理 `timestep=1/480` + decimation 16。

**D 本轮实测发现它在主线环境里不可实现**：

| 实测项 | 结果 | 命令/出处 |
|---|---|---|
| gym-aloha 模型的物理步长 | **`m.opt.timestep = 0.002`**（XML 无 `<option timestep>`，走 MuJoCo 默认） | `mujoco.MjModel.from_xml_path(.../bimanual_viperx_transfer_cube.xml)`，venv `pi05_sim`，`MUJOCO_GL=disable` |
| dm_control 对非整数倍的行为 | **不是四舍五入，是 `raise ValueError`**：`compute_n_steps` 在 `abs(dt/ts - round(dt/ts)) > 1e-8` 时抛错 | `dm_control/rl/control.py:168`–`:194`（**读实现原文，非读文档**） |
| `DT=1/30=0.033333` | ratio **16.6667** ⇒ **ValueError**，直接构造失败 | 同上（D 本轮算术 + 源码判据） |
| 可行的整数倍档位 | `DT=0.034`→17 步→**29.4118 Hz**；`DT=0.032`→16 步→31.25 Hz；`DT=0.030`→15 步→33.33 Hz；`DT=0.02`→10 步→50 Hz（现状） | D 本轮枚举 |
| 团队 QC 合格区间 | **[29.0, 31.0]**（4749 帧 ÷ 159.58 s = 29.76 fps；847 条中 27 条越界） | `timing.control_hz` 原记录 |

**改判（裁定 53）**：
1. **主线仿真控制频率 = 29.4118 Hz（`DT=0.034`，17×0.002）**，落在 QC 区间内、**不改模型 XML、不动 dm_control 源码**。
2. **每控制步硬预算 = 34.0 ms**（不是 33.3 ms）。**33.3 ms/30.0 Hz 降为"名义锚"**：凡延迟判定一律用 34.0 ms，避免用名义值误红/误绿。π₀.₅ 实测 0.517 s/chunk、chunk=50 ⇒ 覆盖 50/29.4118 = **1.700 s** ⇒ **占预算 30.4%**（结论方向不变：按 chunk 执行可行、按每步推理不可行）。
3. **要精确 30.0 Hz 只有一条路**：把模型 timestep 改成 `1/480=0.0020833`（=默认值 ×1.0417）+ decim 16 ⇒ **属改第三方模型资产**，必须先做接触/稳定性 A/B 并报 D 批。**默认不走**。
4. **实现方式约束**：`DT` 是 `gym_aloha/constants.py:4` 的模块级常量、被 `env.py:134` 传给 `control.Environment(control_timestep=DT)` ⇒ **不许改 site-packages 原文件**。必须在**本仓自有 shim** 内（建议 `envs/gym_aloha_shim.py`）改口径，产物记 `representation_version` + shim 的 `sha256-12` + **实测 Hz**。
5. **同频纪律**：示范生成（S1）、BC 训练（S3）、评测（S5）、RL 采样（S6）**必须用同一个实测 Hz 值**，并写进各自 manifest；跨值不得并列。

**自我纠错定性**：裁定 45 的 `1/480 + decim 16` 是 **D 在 Piper / 原生 mujoco 口径下实测出来的**（那里 timestep 由我自己设），**被搬到了 dm_control + gym-aloha 口径**，正是裁定 46.4 禁止的"跨 venv/后端/模型搬用"。**这是同一根因（读了声明/搬了口径，没读实现）的第四次发生** ⇒ 纪律升级见 §5.3。

---

## §3 E2E-min 的定义（与 v4 原文对撞，留行号）

**v4 `RL_Harness_v4_20260924/materials/06_三轮递进调研与方案复审_20260923/01_开发技术方案.md:355` 原文**：
> 首个迭代只打通"抓空→Harness 同协议纠正→数据＋BC→一次 RL 更新→双向无动作辅助评估"。先证明数据改善 policy，再扩展复杂恢复和代码生成。

**v4 `:346`–`:353` 阶段表**（P0 接口与时间预检 / P1 共享 BC 冷启动 / P2 GPT Harness / P3 学习语义贯通 / P4 最小实机闭环 …）与 **`:357`「policy 无动作辅助能力是主结果」**。
**v4 `:5`**：允许少量 SFT，**初始成功率可以为零**；**不使用 ACT**。
**v4 `:346` P1 出口**：「基本可控行为或可靠局部纠正；**不要求预先高成功率**」。

⇒ **"跑通"的定义（D 裁定，禁用"跑通/学会/达标"这类词写进产物）**：
**S1–S6 六段各自拿到可核证据，且 S6 的"一次 RL 更新"在双向无动作辅助评估上给出方向性证据（有增益 / 无增益均算结论，无增益必须带诊断）。成功率高低不是 E2E-min 的出口条件。**

---

## §4 E2E-min 六段：owner / 入口 / 出口判据 / 产物

> 判据一律要求**双向有牙**（能被具体篡改打红 + 反向变异体不误红），格式参照 B2 的 `runs/vla/b2_env_admission_20260929/mutation_verdict.json`（37 变异 ok / 9 反向 / baseline 绿）。

### S1 · 仿真双向示范生成 —— **owner: B2**（主），A2 供契约，C2 供判据
- **为什么现在是最上游阻塞**：P1 的 BC 冷启动需要示范；v4 `:346` P1 交付物 = 「同一 θ 双目标 BC」。当前**仓内没有任何一集主线示范数据**（B2 只有形态夹具 `runs/vla/b2_bidir_demo_form_20260929/`：8 干净 + 22 负对，是**格式**不是**数据**）。
- **D 已实测的可行性事实（B2 不必重新摸索，但必须自己复核后再用）**：
  - `gym_aloha` 0.1.4 **不含任何 expert**（`grep -rn "expert" site-packages/gym_aloha --include=*.py` 命中 **0**；命令与时刻 21:0x 同批落，见 §5.3 新纪律）。
  - **但存在免写 IK 的脚本专家通道**：`gym_aloha/tasks/sim_end_effector.py:36`–`:55` 的 `BimanualViperXEndEffectorTask.before_step` 把动作写进 `physics.data.mocap_pos/mocap_quat` + `unnormalize_puppet_gripper_position` 驱动夹爪；对应资产 `assets/bimanual_viperx_end_effector_transfer_cube.xml` **含 2 处 `<equality>`**（weld，mocap→末端），而关节空间版 `bimanual_viperx_transfer_cube.xml` **含 0 处**（A2 已独立记录：`docs/a2_pi05_sim_readiness_20260929.md` §10.3）。⇒ **在 EE 空间给一条"接近→合爪→抬→搬→放"的航点序列，weld 约束负责解算，录到的 `qpos` 就是 14 维关节动作示范。**
  - **构造入口已存在但未注册**：`env.py:120`–`:124` 支持 `task="end_effector_transfer_cube"`（`gym_aloha/__init__.py` 只注册了 `AlohaInsertion-v0` / `AlohaTransferCube-v0`）⇒ 直接构造 `AlohaEnv(task="end_effector_transfer_cube")`，**不必 fork 包**。
  - **两个已知障碍（B2 必须先处理，别踩）**：① `env.py:150`–`:164` 的 `reset()` 只对 `transfer_cube` / `insertion` 播种全局 `BOX_POSE`，**其它 task 直接 `raise ValueError`** ⇒ 用 EE task 必须子类覆写 `reset()`（或旁路 `AlohaEnv`、直接用 `dm_control.rl.control.Environment`）；② `env.py:139`–`:140` `obs_type="state"` 是 `NotImplementedError` ⇒ **状态档只能用 `obs_type="pixels_agent_pos"` 的 `agent_pos`**。
  - **成功判定现状**：`env.py:174`–`:180` `terminated = is_success = (reward == 4)` ⇒ **只覆盖"右臂→左臂"这一个方向**。
- **出口判据（有牙）**：
  1. 正向（右→左）与反向（左→右）**各 ≥ N 集**（N 由 B2 提议、D 裁；**建议先 5 集打通格式与 QC，再扩到 50/方向**），lerobot 可消费格式，**复用 B2 已有的形态夹具口径**，不重做。
  2. **实测帧率 = 29.4118 Hz ± 0**（写死 `DT=0.034`），落在 QC 区间 [29.0,31.0]；每集带 `(DT, n_sub_steps, model timestep, shim sha256-12)`。
  3. **反向任务必须有自建判据**（env 的 `reward==4` 不覆盖），且判据要满足 v4 `:357`「评分可事后核验」⇒ 需含**几何真值**（方块在目标侧夹爪内 + 离桌面高度阈值）与**弹射/flick 检出**（沿用本仓既有纪律：`task.success_failure_unknown_rules`）。
  4. **专家自证**：脚本专家在留出 seed 上的成功率必须报告（含失败原因分类）；**低于 50% 时必须先修专家再扩量**，否则 BC 学的是噪声（阈值 `proposed`，D 裁）。
  5. **变异体**：把 `DT` 改回 0.02（50 Hz）⇒ 帧率闸必须红；把反向判据的方向写反 ⇒ 必须红；喂一段随机动作当"示范"⇒ 专家自证闸必须红。
- **产物**：`runs/vla/b2_sim_demo_bidir_20260930/`（数据集 + `demo_manifest.json` + `qc_report.json` + `mutation_verdict.json`）。

### S2 · 归一化契约与 stats —— **owner: C2**（T-C2-1，已批 P0），A2 供标注口径
- **入口**：S1 的 ≥5 集先导示范落地（**stats 必须与训练数据同源**）。
- **口径修订（裁定 52，修订 49.1 的源优先级）**：
  - **主线部署 stats = 示范数据同源（S1）**，训练与评测必须用同一份；
  - **env/ctrlrange 推导的那一版只作诊断**（用来解释 zero-shot 的状态通道饱和），**不得进主线部署包**；
  - 两版**都保留、都写进 `representation_version`（名字必须带 stats 源）**，**不许静默替换**；
  - **ABC-130k（YAM 形态）继续禁用**（裁定 43.4 / 49.1：搬 stats = 把饱和换成错配）。
- **出口判据（改判 C2 提议的 G3，见裁定 51.1）**：
  1. `stats_present=True` 且 `normalizer_processor.config.features` **非空**（清空 ⇒ 红）。
  2. **每维 scale 下限**必须存在且生效（近常量维不被放大）；阈值由 C2 给**两个候选值 + 各自在真实数据上的效果**，D 裁，**不许抄 ACT 旧阈值**。
  3. **起态覆盖闸**：A2 实测的起始位姿 `state`（`contract.json → observation.state_raw_14d`，`max|state|=1.16`、原始 2/14 维越界）经主线 stats 归一化后 **越界维数 = 0**；用 env-derived 旧 stats 或 YAM stats ⇒ **必须红**。
  4. **clip 比例上限**：一批真实轨迹帧里被 clip 到 ±1 的维比例 ≤ 阈值（`proposed`，C2 用 S1 数据提，D 裁）。
  5. **不采纳** C2 提议的「对 `ctrlrange` 的行程覆盖率 ≥ 0.95」作为**红**判据 —— 理由见裁定 51.1（示范本来就不会用满关节行程，这条会把正常数据判红 = **极性错**）；**降级为 warning 并记录实际覆盖率**。
- **产物**：`runs/vla/c2_normalizer_contract_20260929/`（照 C2 自述 §2 的四件套）。

### S3 · π₀.₅ 小规模 BC/SFT —— **owner: A2**（主），C2 供 stats，B2 供数据与闸
- **入口**：S1 数据集 + S2 主线 stats + §2 的 29.4118 Hz shim。
- **口径**：**原生头优先**（v4 `:315`「原生路线若用更少改造通过同等门槛，应优先采用」）；**同一 θ 学双目标**（v4 `:7`、`:346` P1）⇒ **不训两个方向各自的模型**，方向由语言指令区分；若出现互相干扰，先记录证据再报 D 裁是否分模型。
- **规模**：**先小规模验证"数据能改善 policy"**，不追成功率。GPU 用 1×A800（fp32 权重已占 13,812.5 MiB），**>10 分钟事前在 `daily_report.md` 申报**（预计时长/显存/可否中断）；单卡优先权 A2 > C2/E。
- **出口判据**：
  1. **同分布留出集**上动作 MSE / token 准确率相对"未微调底座"**有可测下降/上升**（带区间），且**评测帧率与训练帧率同值**。
  2. **导出/部署一致性**（v4 `:340`）：对相同观测、目标、承诺队列与随机噪声，比对**训练导出前**与**部署加载后**的规范动作与物理单位输出；**检查全部缺失/多余参数键**，不许以"加载未报错"为绿（v4 `:340` 原文要求；C2 已实测 `modeling_pi05.py:995`–`:998` 使"未报错"型判据**恒真**）。
  3. **变异体**：喂打乱时间顺序的帧 ⇒ 必须红；用 env-derived stats 训、用 demo stats 评（错配）⇒ 必须红；把 50 Hz 数据当 29.41 Hz 用 ⇒ 必须红。
- **产物**：`runs/vla/a2_pi05_bc_min_2026093*/`（checkpoint + 训练 manifest + 导出一致性报告）。

### S4 · harness ↔ VLA 运行时接线 —— **本轮新识别的无主缺口，现予指派**
- **D 实测的缺口证据（不是推测）**：
  - `harness/runtime_adapter.py`（**全文 77 行**）是 **mock 驱动 + 单 slot**：`RuntimeAdapter.__init__(policy="mock")`，`step()` 只调一次 `self.driver(request, slot[, action])` 并直接产出 `OutcomeEvent`；**没有任何 chunk 执行、没有图像、没有真实 env**。
  - `harness/env_factory.py:1`–`:45` 是 **reach/robosuite 的 monkeypatch shim**（替换 `envs.reach_env.make_reach_env`，`KNOWN=(reach, perturbed)`），**与 gym-aloha 无关**。
  - ⇒ **两者都不能承载 π₀.₅ 的"chunk=50 动作 → 29.41 Hz 逐步下发"**。C 线自己写明「任何『learner 已就绪』的说法都不成立」（`docs/ledger_data_bridge_20260928.md:212`）。
- **指派（裁定 54）**：
  - **A2 主责**：`harness/vla_runtime.py`（新文件）—— chunk 取用/逐步下发、承诺(requested)→入队(committed)→生效(activated) 三类事件对齐 v4 `:344`–`:346` 的 P0 要求、超时与取消、相机键注入（`top` / `left_wrist` / `right_wrist`）。
  - **C2 主责**：`harness/env_gym_aloha.py`（新文件，含 §2 的频率 shim）+ 成功/失败/超时/未知四类判定接 `harness/ledger.py`；**判定必须独立于 env 的 `reward==4`**（另建几何真值复核，两者不一致时**红**）。
  - **B2 主责**：这一段的所有闸（含变异体）+ 版本记录（policy version / stats version / shim version 三件套必须写进每条轨迹）。
  - **硬边界**：**不许改 `harness/contracts.py`**（冻结面）。**只允许加法式新增文件**；若确实必须改契约，**先报 D + 留 before 影像 + sha256-12**（裁定 35.1）。`harness/queue_td_learner.py` 不在冻结面（`docs/ledger_data_bridge_20260928.md:213`「随时可换」），但它是**降级线**，S4 **不复用它**，避免把 VLA 主线接到小网络 SAC 上。
- **出口判据**：一条**可手算的短轨迹**（v4 `:348` P3「用可手算短轨迹核对 target、mask、goal 和来源」）从 env → obs_store → ledger → 训练视图**逐字段手核通过**；并证明 obs 键白名单闸（T-C2-2）在真 π₀.₅ 形态（state + 3 图像键）下**不会静默丢图**。

### S5 · 冻结策略双向评测（无动作辅助）—— **owner: A2 跑，C2 判，B2 闸**
- **口径**：v4 `:357`–`:363` —— 关闭 Harness 临场动作生成/外部候选改写/任务内语义路线替换；保留共同的动作解码、固定调度、本地保护；**保护性终止、失败、未知全部记入试次，不静默剔除**。
- **报告三口径分开**（`evaluation.report_calibers` 已有）：policy 自主成功率（不计接管）/ 系统最终完成率（允许恢复与接管）/ 干预率。
- **出口判据**：同一 checkpoint 的**双向**成功率 + 不确定区间 + 耗时 + **失败类型分布**（识别/接近/抓取/搬运/释放）+ 扰动起态；**渲染在单臂口径不适用（§1.2：代理环境本身双臂），并行度 ≤ 4**。
- **产物**：`runs/vla/a2_pi05_eval_bidir_*/`。

### S6 · 一次 RL 更新闭环 —— **owner: A2（可行性）+ C2（语义）+ B2（闸）**
- **v4 `:355` 的完整链条**：抓空 → Harness 同协议纠正 → 数据＋BC → **一次 RL 更新** → 双向无动作辅助评估。
- **路线裁定（v4 `:315` 原生优先 + `:7`「BC＋在线 RL 将有效经验转成 policy 参数中的能力」）**：**E2E-min 用"同结构同代码、更新 π₀.₅ 部分参数（优先 action expert）"的原生路线**；**residual RL / 价值模型选候选降为备选**，只有在 S6 前置探针证明原生路线不可行（显存/梯度/稳定性）时才启用，且**必须报 D 裁**。
- **前置可行性探针（A2，先做，别直接开长训）**：① 梯度能否到达待更新参数（列出被冻结/可训练参数数与显存实测）；② 一次更新的显存峰值与耗时；③ 更新后**导出/部署一致性**（同 S3-2）；④ **对照必须是同预算的动态 Harness-DAgger/BC**，不是 RL vs 冻结 SFT（v4 `:376`，`evaluation.h1_control` 已登记）。
- **出口判据**：一次更新前后的**双向无辅助**差值 + 区间 + **预填的有意义增益门槛与允许回归**（v4 `:379`）；**辅助成功率上升而独立能力未升 ⇒ 不通过**；区间过宽 ⇒ 结论写"证据不足"，不许写"算法已被证明等效或无效"。

---

## §5 三件跨线纪律（本轮新增/升级）

### 5.1 D 自我纠错：`load_verification.json` 的证据**存在**（裁定 50.1，撤销 48.5 的驳回）
- 裁定 48.5 里 D 写「**"无随机初始化键"无任何证据**」，理由是只读到 `remap` 段的三个字段。**D 本轮亲自枚举全部顶层键后确认自己错了**：该文件顶层有 18 个键，其中 `compare` 段含 `n_compared=812`、`n_bitwise_exact=812`、`n_differ=0`、`n_shape_mismatch=0`、**`n_model_keys_not_covered_by_ckpt=0`**（note 原文：「若为空，说明权重是完整落进模型的」），`verdict="all_bitwise_equal"`。
- ⇒ **48.5 的驳回撤销**，C2 的 §1.3 主张**采纳**：该文件是"逐位相同 + 无未覆盖键"的**有效证据**。裁定 48 的**结论不变**（transformers 红线仍撤销），但**依据换成 48.1 的卫语句原文 + 本条的加载证据**，两条互不替代。
- **升为纪律（全仓）**：**任何"某证据不存在 / grep 命中 0 / 某字段没有"的否定型主张，必须先枚举完整键集或完整文件清单，并把枚举结果（命令原文 + mtime + 行数/键数）落进产物。**只读一个段就断言整体缺失 = 不合格主张。

### 5.2 C2 提议的"读侧三元组"纪律 ⇒ **采纳**（裁定 51.2）
本仓 5 条会话并发追加共享文书（C2 举的实例成立：它 19:1x grep 时 `supervisor_memo` 是 1942 行、20:14 后是 2222 行，"命中 0"与"命中 3"在不同时刻都为真）⇒ **任何 grep / 计数类主张必须同批落 `(mtime, 行数或键数, 命令原文)`**。这是既有"追加前先 `git status` + `tail`"（写侧）的读侧对偶。

### 5.3 口径搬运禁令（第四次同型事故后升级）
**任何频率/延迟/吞吐/分辨率口径，第一次被用到一个新 (venv, 后端, 模型, 环境) 组合前，必须在该组合内重测或读实现原文确认可实现性，并留下 file:line 或实测 JSON。** 本日四起：① 31.25 Hz 当契约值；② osmesa 钉死；③ `transformers>=4.57.1`；④ **`1/480+decim16` 从原生 mujoco 搬到 dm_control（§2）**。共同根因：**读了声明/搬了口径，没读实现。**

---

## §6 降级与暂停清单（本轮明确"不做什么"）

| 项 | 处置 | 理由 |
|---|---|---|
| 双臂 Piper/Cobot Magic 渲染验证 | **暂停**（能力已证一次并归档） | 用户指令 + §1.1 吞吐会降 |
| 实机 / SDK / 采集窗口 | **暂停**，触发式延期（§1.3） | v4 P4 之前无意义 |
| GPU 渲染解锁（EGL） | **交给 E 线**，时间盒、CPU-light、可判不可行即停 | 吞吐线，非正确性关键路径；若成功则 S1/S5 提速 |
| `robosuite Lift` / 小网络 SAC / `queue_td_learner` 优化 | **冻结不动**（裁定 38 / 46.6） | v4 `:5`「不使用 ACT」；C 自述 learner 不成立 |
| T-C2-6 `registry/` 多门禁并存 | **暂缓**（裁定 49.4），只留"待触发"记录 | 主线暂不需要，且会动 C 已验收的 48/48 |
| C2 的 T-C2-4 闸极性审计 | **保留 P0 但限时**：只审"当前在长的 4 把新闸 + S1–S6 新闸"，不做全仓历史普查 | 用户要求主线优先；恒真闸等于没闸（裁定 27.1） |
| 文献/前沿检索（含实机窗口口径、VLA-RL 上游实现现状） | **暂停**，触发式（§1.3 / S6 前置探针失败时） | 不在关键路径 |

---

## §7 阻塞台账（E2E-min 未销账项，21:0x）

| # | 阻塞 | 卡住哪段 | owner | 状态 |
|---|---|---|---|---|
| B1 | **仓内没有一集主线仿真示范数据**；gym-aloha 无 expert，需自建脚本专家（EE+mocap+weld 通道已由 D 实测确认存在） | S1 → S2 → S3 全链 | B2 | **未开工**（只有形态夹具） |
| B2 | **主线 stats 不存在**（`normalizer_processor.config.features={}`）⇒ 状态通道饱和（`waist` 仅 0.3183 行程可表示） | S2、S3 | C2（T-C2-1 已解锁） | 进行中（依赖 S1 先导 5 集） |
| B3 | **obs 图像键会被静默丢弃**（`harness/queue_td_learner.py:134` 的 `_obs_vector` 只挑 state 类键） | S4、S6 | C2（T-C2-2 已批） | 未开工 |
| B4 | **harness ↔ VLA 运行时接线不存在**（`runtime_adapter.py` 是 mock；`env_factory.py` 是 reach shim） | S4、S5、S6 | A2 + C2 + B2（本轮指派） | **新识别，未开工** |
| B5 | **RL 更新 π₀.₅ 的可行性未探**（梯度可达性 / 显存峰值 / 导出一致性） | S6 | A2 | 未开工（S3 之后） |
| B6 | **git 单写者代提交仍未落**（HEAD `e6c661e`，脏 **48** 项，20:31 实测） | 全线可追溯性 | B2（裁定 49.6） | **未做** |

**关键路径**：**B1 → B2 → B3/B4（可并行）→ S3 → S5 → B5 → S6**。
**D 的判断**：当前唯一真正卡住全链的是 **B1（示范数据）**。B2/B3/B4 都可以在 S1 的先导 5 集落地后并行推进；**E 线（EGL）与 B6（git）不在关键路径上，但 B6 影响可追溯性，仍要求 B2 立即做。**

---

## §8 D 的等待项 / 需要用户的项

**等 agent（不需要用户）**
- B2：① **立即** git 代提交（B6）；② S1 的脚本专家方案 + N 集规模 + 反向判据草案（`proposed`，D 裁）；③ `V-pi05-1` 按裁定 48.4 重锚 + 3 条变异体；④ `V-pi05-3` 渠道字段填 `mixed`。
- C2：① T-C2-1 的 scale 下限**两个候选值 + 真实数据效果**；② clip 比例上限的 `proposed` 值；③ T-C2-2 的只读证伪探针；④ T-C2-4 限时审计（只审在长的闸）；⑤ 回流单 `docs/c2_handoff_to_d_20260929.md`。
- A2：① S4 的 `harness/vla_runtime.py` 接口草案（**不改 `contracts.py`**）；② 29.4118 Hz shim 的实现与实测（§2-4）；③ 裁定 44.1 最后一项（blocker→成功之间改了什么）；④ S6 前置探针计划。
- E：EGL 可行性判定（E1），**不可行就出 no-go + 平台申请文本并停线**。

**需要用户（只剩 2 项，且都是"确认/否决"级，不给新活）**
1. **§1.2 的作用域解读是否认可**：「只渲单臂」约束 **Piper 资产线**，主线仿真代理 **保持 gym-aloha 双臂**（π₀.₅ 底模是 `aloha_bimanual_14d`，这是形态必要条件）。**若你要求连仿真代理也单臂 ⇒ 等于换底模，属路线分叉，请明确说，我不会自行推进。**
2. **§2 的频率改判是否认可**：主线仿真 = **29.4118 Hz（`DT=0.034`）**，每控制步预算 **34.0 ms**；精确 30.0 Hz 需改模型 timestep（默认不走）。

---

## §9 D 自我复核与更正（2026-09-29 21:3x，用户授权"判断无误可直接确认执行"）

**复核方式**：**不重读自己的文书，全部用真跑或逐字读源码**。复核结果：**§1–§8 的裁定主体成立，但 S1 的一条关键事实是错的，另有两条 EGL 事实需要更正（对 E 有利）。**

### 9.1 【更正 · 影响 B2 的 S1】`task="end_effector_transfer_cube"` 在 gym-aloha 0.1.4 里是**死代码**，不能直接构造

D 在 §4-S1 写「`env.py:120`–`:124` 支持 `task="end_effector_transfer_cube"`（未注册但可直接构造 `AlohaEnv`）」——**这条错了**。逐字读原文（venv `pi05_sim`）：

```
120:        elif task_name == "end_effector_transfer_cube":
121:            raise NotImplementedError()          ← 就在分支第一行
122:            xml_path = ASSETS_DIR / "bimanual_viperx_end_effector_transfer_cube.xml"   ← 不可达
123:            physics = mujoco.Physics.from_xml_path(str(xml_path))                      ← 不可达
124:            task = TransferCubeEndEffectorTask()                                       ← 不可达
125:        elif task_name == "end_effector_insertion":
126:            raise NotImplementedError()
```
**D 真跑复现**：`AlohaEnv(task="end_effector_transfer_cube", obs_type="pixels_agent_pos")` ⇒ **`NotImplementedError`，抛在 `gym_aloha/env.py:121`**（`_make_env_task` 内，由 `env.py:44` 的 `__init__` 调用）。`env.py` 里 `NotImplementedError` 共 5 处（`:47`、`:121`、`:126`、`:131`、`:140`）。

**但 mocap+weld 通道本身仍然成立**（这部分 D 的核对是对的，且已逐字确认）：
- `assets/bimanual_viperx_end_effector_transfer_cube.xml:5`–`:8`：`<equality>` 内是**两条 `<weld>`** —— `body1="mocap_left" body2="vx300s_left/gripper_link"` 与 `body1="mocap_right" body2="vx300s_right/gripper_link"`（`solref="0.01 1"`、`solimp=".25 .25 0.001"`）。
- 同文件 `:15`、`:20`：`<body mocap="true" name="mocap_left" pos="0.095 0.50 0.425">` / `mocap_right pos="-0.095 0.50 0.425"`（各带 3 个可视化 site）。**关节空间版 `bimanual_viperx_transfer_cube.xml` 里 `mocap` 命中 0。**
- ⇒ **正确做法（B2 照此实施）**：**绕开 `AlohaEnv._make_env_task`，在本仓自有代码里直接构造** `control.Environment(mujoco.Physics.from_xml_path(EE_xml), TransferCubeEndEffectorTask(), time_limit=float("inf"), control_timestep=DT)` —— 这就是 `env.py:122`–`:124` + `:133`–`:135` 本来要做的事（约 5 行），另外需自行复刻 `_format_raw_obs` 与 `BOX_POSE` 播种（`env.py:150`–`:164` 的 `reset()` 对非 `{transfer_cube,insertion}` 仍会 `raise ValueError`）。**代价：比 D 原先说的"直接构造"多一层自建 env 包装，但通道物理上有效。**
- **备选（若 EE 通道实测成功率太低）**：在**关节空间**自写脚本专家（分阶段 PD 目标位姿 + `sim.py` 的夹爪归一化），**不用 mocap**。B2 自行评估后报 D。

### 9.2 【更正 · 影响 E 的任务书】`libEGL.so.1` 的 `eglQueryDevicesEXT`：**动态符号表里没有，但 `eglGetProcAddress` 能取到**

D 用三种独立方法核（裁定 50.2 要求先枚举）：`nm -D` 命中 **0**、`objdump -T` 命中 **0**（`.text` 动态符号共 **44** 个，`eglQuery*` 只有 `eglQueryAPI/eglQueryContext/eglQueryString/eglQuerySurface`）、`strings` 命中 **1**；**运行时自证**：`ctypes.CDLL('libEGL.so.1')` 的 `hasattr(lib,'eglQueryDevicesEXT')=False`，但 **`eglGetProcAddress(b'eglQueryDevicesEXT')` 返回 `0x7f0b700a4b70`（非 NULL）**，`eglGetPlatformDisplayEXT` 同样非 NULL。包版本 `libglvnd0 / libegl1 = 1.4.0-1`。

⇒ **两条更正**：
1. `docs/infra-gpu-render.md` §2.3 的「`libEGL.so.1` 里连 `eglQueryDevicesEXT` 符号都没有（没有任何 vendor 提供设备枚举）」**表述不准确**：glvnd 对 EXT 扩展**不经动态符号表导出，而是经 `eglGetProcAddress` 分发**，入口点**是存在的**。"当前枚举不到 NVIDIA 设备"的真因是**没有注册 NVIDIA vendor ICD**（`egl_vendor.d` 只有 `50_mesa.json`），不是 glvnd 缺能力。
2. **D 在 `d_handoff_to_e_20260929.md` §3.1-1 写的"若符号缺失还要在自有前缀补一套新版 libglvnd"这条分支，实测证明【不需要】**：`libglvnd 1.4.0` 足够，**只需补 NVIDIA vendor ICD + 渲染库**。

### 9.3 【已被 E 实测推翻的一条既有断言】"没有 `/dev/dri` 就枚举不到设备"—— **对 NVIDIA 不成立**

E 的 `runs/infra/e_gpu_egl_verify_20260929/staged_ldpath.json` 实测：枚举到的 NVIDIA EGL 设备 **`drm_device_file: null`**、`vendor: "NVIDIA"`、`initialize_ok: true`、设备扩展含 **`EGL_NV_device_cuda`**；`GL_RENDERER = "NVIDIA Corporation | NVIDIA A800-SXM4-80GB/PCIe/SSE2 | 4.6.0 NVIDIA 590.48.01"`。
⇒ **`docs/infra-gpu-render.md` §4 的理由之二被证伪**（NVIDIA 的 `EGL_EXT_platform_device` 走 `/dev/nvidia*`，本机有 `/dev/nvidia2` + `/dev/nvidiactl`）。**该文件 §4 的结论"容器内装不了"整体作废**，其"版本必须与宿主驱动严格一致"这一半仍成立（E 用的正是 **590.48.01**）。

### 9.4 【D 自己踩的同一个坑，A2 抓到了 —— 升为纪律】monkeypatch 必须核对目标模块的 import 形式

D 的 §2-4 只说"`DT` 是 `gym_aloha/constants.py:4` 的模块级常量，用自有 shim 改"。**A2 实施时发现不够**：`gym_aloha/env.py:7`–`:12` 是 **`from gym_aloha.constants import (…, DT, …)`** ⇒ `DT` 在 `env.py` 里是**已复制的模块级绑定**，**只改 `gym_aloha.constants.DT` 对已 import 的 `env.py` 无效，会静默保持 50 Hz**（`envs/gym_aloha_shim.py` 的 docstring 已写明，并把"只改 constants 不够"做成了可复现变异实验）。
⇒ **纪律（裁定 57.4）**：**任何 monkeypatch 必须先读目标模块的 import 语句形式**：`import m` + `m.X` 用法 ⇒ 改 `m.X` 有效；**`from m import X` ⇒ 必须同时改使用方模块里的同名绑定**；并**必须配一条"只改一半 ⇒ 静默错值"的变异体**。D 的 §2-4 表述不完整，以 A2 的实现为准。

### 9.5 用户委托 D 自行确认的两项（裁定 58，**现已确认生效**）

用户 21:2x 明示「你这边自己再核对一遍，无问题可直接确认……后续你判断无误可直接确认执行」。D 复核后**确认**以下两项，并写死**可推翻条件**：
- **① 单臂限制的作用域（裁定 55.4）⇒ 确认**：「只渲单臂」只约束 **Piper / Cobot Magic 自有资产渲染线**；**主线仿真代理保持 gym-aloha 双臂**（π₀.₅ base = `aloha_bimanual_14d`，代理模型 `nq=23/nu=16/ncam=7` 本身即双臂场景）。**推翻条件**：用户明确要求代理也单臂（⇒ 换底模，属路线分叉，需重开选型）。
- **② 频率口径 29.4118 Hz / 34.0 ms（裁定 53）⇒ 确认**，且**已由 A2 独立真跑复现**：`runs/vla/a2_hz_shim_29p4118_20260929/hz_shim_verification.json` —— `DT=0.034` → `n_sub_steps=17` → `control_hz=29.411765`、`in_qc_band_29_31=true`、`per_step_budget_ms=34.0`；`DT=1/30` 一条被标为「名义 30.0 Hz（裁定 45 原口径）」且 `compute_n_steps_error` 非空。**D 与 A2 在两套独立脚本上得到同一结果**（D：`dm_control.rl.control.compute_n_steps` 直调，实测报 `ValueError: Control timestep (0.0333…) must be an integer multiple of physics timestep (0.002)`）。**推翻条件**：团队流水线的 QC 区间 [29.0,31.0] 被上游修订，或用户要求精确 30.0 Hz（⇒ 需改模型 timestep 到 1/480 + 接触稳定性 A/B）。
- **③ 附带确认（裁定 58.3）**：`max_episode_steps=300` 在 29.4118 Hz 下 = **10.2 s 仿真时长**（原 50 Hz 下为 6.0 s）。**D 裁：保持 300 步不缩放**，但**必须把 `episode_horizon_s=10.2` 写进每份 manifest，超时/失败一律按秒登记，跨频率对比不得按步数并列**；若需与 50 Hz 生态数字对比，必须显式换算并标注。

---

## §10 【2026-09-29 22:0x · D 的第七轮复核与全局口径改判（裁定 64–69）】

> **本节是"追加式更正"，不修改 §1–§9 的任何一行。** §4-S4 的 `:143` 与 `d_handoff_to_a2_20260929.md:502` 里的 v4 行号引用**以 §10.1 为准**，原行保留作痕迹。

### 10.1 【裁定 64 · D 第五次同型自我纠错】v4 引用的**文件身份**必须与行号一起给

**触发**：A2 在 `docs/a2_s4_vla_runtime_interface_20260929.md` §0-5 报"D 把 requested→committed→activated 的出处写错了"。**D 在核实前差点直接接受**，核了才发现**双方读的不是同一个文件**。

| 文件 | 行数 | `sha256-12` | 谁引的 |
|---|---|---|---|
| `RL_Harness_v4_20260924/materials/06_三轮递进调研与方案复审_20260923/01_开发技术方案.md` | **418** | **`0a9a2092e18a`** | **D**（§4-S4 `:143`：`:344`–`:346`「P0 要求」） |
| `RL_Harness_v4_20260924/materials/06_三轮递进调研与方案复审_20260923/appendices/01_接口契约与开发验收.md` | **433** | **`aae20ffe604f`** | **A2**（`:344`–`:346` = T24/T25/T26；`:375`） |

**D 逐字复核结果（两个文件都读了原文）**：
- **A2 的三条断言在附录一里全部成立**：`:344` T24 ✓、`:345` T25「仅开启训练并发或仅开启执行并发 ⇒ 前者不被称作已实现异步动作调度」✓、`:346` T26 ✓、`:375`「真实决策请求、提交的动作结果与机械激活相互关联但分别记录，是异步 BC＋RL 接口成立的关键」✓、`:103`「动作长度 `H≥2n`」✓、`:105`–`:107` C/E/D 三槽 ✓、`:111`「错过 deadline 不把晚到结果塞进过期索引。Runtime 按冻结的迟到规则继续已有合法动作、保持或结束尝试，并记录实际选择」✓。
- **但 D 引的是 `01_开发技术方案.md`，那里 `:344` 是空行、`:345`–`:346` 是表头与分隔行，P0 那一行在 `:347`**（「请求／入队／执行可区分，**能选择 n**」）⇒ **D 偏了 1–3 行，A2 的"陷阱表"读法不构成对 D 原引用的否证（不同文件）。**
- **A2 自身也有一处内部不一致**：其 §2.4 写「v4 `:346`（T25）」，而 T25 在 **`:345`**（其 §0-5 写的 `:345` 是对的）。
- **D 另两处引用同样偏行，一并更正**：`:340`「发布检查」→ 正文在 **`:341`**；`:357`–`:363`「policy 无动作辅助能力是主结果」→ 该句在 **`:361`**。`:355`（首个迭代只打通"抓空→…→双向无动作辅助评估"）与 `:376`（RL 的对照必须是同预算的动态 Harness-DAgger/BC）**D 复核为逐字准确，不改**。

**裁定 64**：
1. **requested→committed→activated 的权威出处 = 双文件双引用**：**`appendices/01_接口契约与开发验收.md:375`（契约陈述）** + **`01_开发技术方案.md:347`（P0 晋级依据）**。
2. **升级为纪律 `citation_file_identity_discipline`**：**任何 v4 行号引用必须带文件身份三元组 `(相对路径, sha256-12, 行号)`**；**只有行号的引用一律视为不可核验，不得进入裁定依据。**
3. **这是 D 第五次同型事故**（前四次：31.25 Hz 当契约值 / 渲染后端钉死 osmesa / `transformers>=4.57.1` / `1-480+decim16` 跨环境搬运）。**共同根因第六次重复：读了声明，没读实现／没核身份。**

### 10.2 【裁定 66】S1 路线定稿 —— **EE 模型只作 IK oracle，示范必须在关节模型里采**

**D 的第六次同型自我纠错**：§4-S1（`:100`）写「EE 空间给航点、**weld 解算**、录 `qpos` 即 14 维关节示范」—— **这是从资产声明（XML 里有 `<weld>`）推出的行为断言，D 没实测。B2 的 probe2 实测推翻它**：`mocap_right` 阶跃 `[0,-0.05,+0.05]` 后 `vx300s_right/gripper_link` 残差 **step1 0.0872 m → step50 0.1359 m，不收敛反而变大**。

**D 实测补充的硬事实**（`MjModel.from_xml_path` 直读，21:5x）：

| | 关节版 `bimanual_viperx_transfer_cube.xml` | EE 版 `bimanual_viperx_end_effector_transfer_cube.xml` |
|---|---|---|
| `ncam` / 相机名 | **7** | **7**（名字与父体**完全相同**） |
| 腕部相机 | `left_wrist` 父 = `vx300s_left/gripper_link`；`right_wrist` 父 = `vx300s_right/gripper_link` | **同上，也有** |
| `nu` / `neq` | **16 / 0** | **4 / 2**（4 个 actuator 名**全为空串** ⇒ 臂关节无 actuator） |
| `nq` / `nv` | 23 / 22 | 23 / 22 |
| XML 元素 | 0 `<equality>` / 0 `<weld>` | **1 个 `<equality>` 含 2 个 `<weld>`**（A2/B2 对 D "2 处 `<equality>`" 的更正**成立**） |

- **⇒ A2 §2.3 的结论要精确化**：不是"模型没有腕部相机"，而是 **"`AlohaEnv` 的 observation 只把 `top` 交给 agent"**；**三相机可以直接从 physics 渲出，两个模型都能。**
- **⇒ B2 的 H2（无臂 actuator，整条臂只靠 soft weld 吊着）在结构上成立**（B2 实测 `solref=[0.01,1]`、`solimp=[0.25,0.25,0.001,0.5,2]`）。
- **⇒ 一条跨线硬事实**：`gym_aloha/tasks/sim_end_effector.py:120` 的 `get_observation` **无条件 `physics.render(480×640, camera_id="top")`**（B2 probe3 的 traceback 实证）⇒ **EE 通道在 `MUJOCO_GL=disable` 下不可用**。**在 E 线解锁 egl 之前，S1 的这条通道根本不可行 —— D 之前把 E 线定位为"不在正确性关键路径"，就 S1 的可行性而言低估了，现予更正。**

**S1 路线裁定**：**EE 模型只作 IK oracle → 录 `qpos` → 在关节模型（`AlohaTransferCube-v0`，`nu=16`）里用它自己的 actuator 重放，并在关节模型里采 3 相机图像与 14 维动作。** **不允许在 EE 模型内直接采示范** —— 因为 EE 的重力下垂 + soft-weld 滞后与关节模型的 actuator 动力学**不是同一套动力学**，而 **S5 评测必然在关节模型里跑** ⇒ 那会引入**训练/评测动力学错配**（正是附录一 `:346` T26 与 D 的口径搬运禁令所禁）。

**右臂发散的当前状态（B2 probe4，21:52）**：**左臂残差收敛到 `0.0013 m`（<3 mm 判据绿）；右臂发散到 `0.2469 m`、姿态残差 `2.376 rad`。** D 的假设（标 `d_inference_not_measured`）：两侧 weld **不是同构镜像** —— 左 `relpose_quat_wxyz_raw=[1,0,0,0]`（单位）、右 `=[-3.67e-06,0,0,0.99875]`（**绕 z 轴 180°**），且 `anchor2` 的 x 分量左右反号（`-0.134706` / `+0.134706`）⇒ **解析反解可能对右臂沿用了左臂的单位 `qrel`，未逐侧复合**。**判据：逐侧复合 `qrel` 后右臂残差应 <3 mm；若仍 >3 mm ⇒ 假设被否，转 H2/H3。**

**S1 出口判据（任务级，不是残差级）**：见 `d_handoff_to_b2_20260929.md` §13.8（五条：几何真值搬运成功且独立于 `reward==4`／3 相机 224² + 14 维动作／`episode_horizon_s` + 三件套版本／重放可复现／反向同理且判据自建）。

### 10.3 【裁定 65】S4 的四条口径 —— **S4 不等 S1，立即开工**

| # | 事项 | 裁定 | 依据（带文件身份） |
|---|---|---|---|
| 1 | **`n_replan`** | **25**（`H=50`，取 `H≥2n` 等号）；进 `representation_version`，S1/S3/S4/S5/S6 同值 | 附录一（`aae20ffe604f`）`:103` `H≥2n`、`:105`–`:107` C/E/D、`:101`「首版可采用异步执行、分批训练」、`:345` T25。**n=50 会让 E=`[50,100)`、D=`[50,50)` 双空 ⇒ 三槽退化成同步整块执行 ⇒ 验的不是 v4 定义的异步调度，S6 的 TD 时序前提也对不上** |
| 2 | **`max_episode_steps`** | **维持 300（驳回 A2 的 176）**；`episode_horizon_s=10.2` 进 manifest；跨口径并列一律标 `not_comparable_horizon` | ① 176 想保的"与已发表 300 步/6 s 可比"**在采纳 29.4118 Hz 那一刻就已失去**（发表口径 `DT=0.02`/50 Hz，动作保持时长差 1.7×）；② v4 要求的对照是**同预算动态 Harness-DAgger/BC**（`01_开发技术方案.md:376` 逐字核过），**不是**已发表数字；③ E2E-min 出口判据不是成功率（`:5`、`:348` P1「不要求预先高成功率」）；④ 176 是新派生口径且偏离注册资产配置（`gym_aloha/__init__.py:16`）。**可推翻条件：S5 失败归因显示 timeout 占主导 ⇒ D 必须开 176 敏感性臂** |
| 3 | **`late_policy`** | **`hold`**；必须记录"实际选择"三态 + `expired` 事件；值进 `representation_version`；**迟到帧不得被重标为 `activated`** | 附录一 `:111` 逐字：「错过 deadline 不把晚到结果塞进过期索引。Runtime 按冻结的迟到规则**继续已有合法动作**、保持或结束尝试，并**记录实际选择**…异常事实保留，**不重标成"准时"**」 |
| 4 | **`lease_generation` / `epoch`** | **`lease_generation` = 控制代际 = chunk 代际；`epoch` 保持 `ledger.py` 既有语义不动**（A2 实测 `epoch` 在 `ledger.py` 命中 18 处） | A2 自行作废其"重定义 `epoch`"的初稿，D 采纳并记功 |

**S4 排期裁定（驳回 A2 的"等 S1 有第一批示范再落地"）**：
- **S4 的证据是结构性的**（chunk 代际推进、C/E/D 三槽、七类事件、`ledger.frame_fact` 逐字段、deadline 与迟到计数），**不需要示范数据**；
- **A2 手上有真实 env + 真实 3 相机渲染路径**（`scripts/a2_pi05_zeroshot_eval.py:190`、`:249`–`:250`，已跑 20 局）**⇒ 不是 mock env，"第二个假组件"的风险不成立**；
- **用 zero-shot π₀.₅ 作真实 obs 载体是允许的，但裁定 46.6 继续有效：不得用 zero-shot 成功率做任何路线/能力判断**，S4 的成功率一栏写 `not_an_exit_criterion`；
- **若 S4 等 S1，而 S1 正卡在右臂 weld ⇒ 全链停摆。S1 只阻塞 S3/S5，不阻塞 S4。**
- **拆两段**：**S4a（立刻做）** = `harness/vla_runtime.py` + chunk 循环 + 三槽 + 事件 + 版本三件套，对真实 env 跑一条**可手算短轨迹**逐字段手核（对撞 `01_开发技术方案.md:350` P3）；**S4b（等 C2 的 `harness/env_gym_aloha.py`）** = 四类判定接 `ledger`，**独立于 `reward==4`，不一致即红**。
- **硬边界重申**：**`harness/contracts.py` 一个字节不动**（七个 `EVENT_KINDS` 够用，不新增 kind）；只允许加法式新增文件。

### 10.4 【裁定 67】渲染口径改判（E 线 E2 验收）

**主线渲染后端 = `MUJOCO_GL=egl` + prefix-only NVIDIA vendor**（`LD_LIBRARY_PATH` + `__EGL_VENDOR_LIBRARY_FILENAMES` → `/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist/egl-libs/590.48.01`）；**osmesa / egl_mesa 都是 CPU，只作对照与回退**；**禁止任何系统写入（含 `ldconfig`）**。

| 口径（3cam 224²、reps=3、独立进程、prefix-only） | osmesa | **egl_nvidia** | egl_mesa |
|---|---|---|---|
| **gym-aloha 双臂**（主线） | 14.01 | **165.65 ctrl-steps/s = `11.82×`** | 12.83（**0.92×，比 osmesa 更慢**） |
| **Piper 单臂**（自有资产线）w1 | 12.54 | **633.95 = `50.55×`** | 12.10 |
| Piper 单臂 w2 / w4 | 24.83（eff 0.99）/ 47.49（eff 0.947） | 817.81（eff **0.645**）/ 1511.27（eff **0.596**） | — |

- **旧 `13.8×`（480×640）降级为 `boundary_violated_provenance`**（分辨率不同 + 系统安装态），**不得再作主线依据**；A2 的 `loop_fps≈10.5`/`0.21× 实时` 与 `97.66 ms/控制步` 同为 osmesa 口径 ⇒ **作废，在 egl 下重测**。
- **`165.65 ÷ 29.4118 Hz = 5.63× 实时（仅渲染）` ⇒ 闭环是否实时现在取决于 π₀.₅ 的推理墙钟，不再取决于渲染**；A2 §2.4 的预算算术分母被换掉，**n=25 的占比必须重算**。
- **并行度**：CPU 时代的"上限 4"在 GPU 渲染下失效；**在 E3-④（含 A2 训练并发）实测出来之前，各线并行度不得超过 2**；建议值由 E 出、D 裁。
- **S1 的采集成本因此变化**：300 步/集 在 egl_nvidia 下 **≈1.81 s/集**（osmesa **≈21.4 s/集**）⇒ **20 集 ≈ 36 s（原 7.1 min）**。**B2 从此受 GPU 申报纪律约束**（单卡优先权 A2 > C2 > E > B2）。

### 10.5 【裁定 68】C2 的 T-C2-2 补丁**验收通过** + 一次覆写违规

- **采纳**：`harness/queue_td_learner.py` **+17/−1** 纯加法、默认 `obs_key_contract=None ⇒ derive_contract()`；闸 **14 检查 0 红**；**4 个变异体 `missed_red=[]`/`false_red=[]`（双向有牙）**；G1 实测 `vec_sha12=4fd32aacc677` 与打补丁前逐字节相同（**ACT 线基线未破**）；G3 实测点名三路图像键后 `refused`；**`harness/contracts.py` 一个字节未动**；**C 线 17 项全量回归 `n_exit0=17/17`**。
- **违规（记一次）**：其回归驱动只改指了 `c_env_manifest.py --check` 一处，**其余自检脚本写 `runs/infra/` 顶层固定路径** ⇒ **21:42:43–21:44:16 覆写了 16 个 C 线产物、无 before 影像，且 `runs/` 被 `.gitignore:12` 排除 ⇒ 无 git 恢复路径**。**D 已逐条复核被其它线文书引用的数字在新字节里全部保留**（`c_learner_shard_smoke.json`：`n_checks=46`、`pass=true`、`substantive_gap`、`takeover 28/28`、`clean/terminal 0/0` 且 `ratio=None`、`lift-state-proprio50+obj10-v1`、`n=4/γ=0.99/H=8`）⇒ **不构成实质证据损失，但原始 C 运行字节的 mtime 溯源已断，永久登记。**
- **升级为纪律 `regression_driver_output_enumeration`**：**跨线回归驱动开工前必须从被调脚本源码里枚举其全部固定路径输出，逐个改指本线目录或逐个留 before 影像；不许"挑一个最显眼的改掉"**（D 实测：17 个自检脚本里 14 个写固定路径）。

### 10.6 【裁定 69】阻塞台账更新（**B6 已销账**）

| 段 | owner | 21:0x 状态 | **22:0x 状态** |
|---|---|---|---|
| **S1** 仿真双向示范 | B2 | **唯一真阻塞**，且 D 给的通道是错的 | **仍是唯一真阻塞**；D 的错误通道已作废（§10.2），路线定稿为 EE-oracle→关节重放；**左臂已收敛 1.3 mm，右臂按 D-H1 判定后即可动**；**渲染阻塞已由 E 线解除** |
| **S2** 归一化契约与 stats | C2 | 待 D 裁数据源 | **数据源与口径已裁**（= B2 的 S1 示范；QUANTILES + 逐维 scale 下限 + 近常量维显式标记；IDENTITY 作对照分支，两案并列）；**时刻 = B2 先导 5 集落地即算** |
| **S3** π₀.₅ 小规模 BC | A2 | 等 S1 | 等 S1（不变） |
| **S4** harness↔VLA 接线 | A2+C2+B2 | 新识别的无主缺口 | **已指派并解锁**：A2 立即做 S4a（不等 S1）；C2 的 obs 键覆盖闸**已落地验收**；B2 的 `GATE_MODULE_PATH` 改查表已裁 |
| **S5** 冻结双向评测 | A2/C2/B2 | 等 S3 | 等 S3（不变）；**渲染口径已改判，评测吞吐按 `11.82×` 估** |
| **S6** 一次 RL 更新 | A2+C2+B2 | 探针计划未交 | **A2 的 P1–P5 探针计划已采纳**（P5 `stats_version` 前后必须相同且 `!= "NONE"` 升为必备闸）；**新增前置：A2 与 C2 都必须先读 `appendices/02_异步动作时间轴与学习目标.md`**（附录一 `:109` 指过去，TD 样本时序前提以它为准） |
| **B6** git 代提交 | B2 | **HEAD 仍 `e6c661e`，脏 55+** | **已销账：HEAD = `c422659`**（21:2x）；**21:2x 后又脏 23 项 ⇒ 本轮结束后再代提交一次** |

### 10.7 本轮 D 落盘的文书（全部 NFS，追加式，before 影像在 `runs/vla/d_ruling_round_20260929_2200/`）

| 文件 | 行数变化 | before `sha256-12` |
|---|---|---|
| `rl_harness_supervision/d_handoff_to_b2_20260929.md` | 397 → **497** | `4b1c898fe6ba` |
| `rl_harness_supervision/d_handoff_to_a2_20260929.md` | 530 → **623** | `dc97a7dbc792` |
| `rl_harness_supervision/d_handoff_to_c2_20260929.md` | 265 → **339** | `b25d78540198` |
| `rl_harness_supervision/d_handoff_to_e_20260929.md` | 173 → **225** | `9f4e3dc55481` |
| `rl_harness_supervision/d_simchain_e2emin_20260929.md`（本节） | 270 → **本节** | `8ebf8d8308d1` |
