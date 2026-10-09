# D 线上下文断点（2026-09-29 21:3x）——**服务器可能关闭，本文件是重启后恢复监管的唯一入口**

**用途**：D（监管/口径裁定）会话若被销毁或节点重启，**新会话只读本文件即可接续**。本文件**只登记状态与指针，不替代正文**；每条都给了正文路径。
**写入者**：D 单写。**读取者**：D 的新会话；A2/B2/C2/E 可读不可写。
**自检**：本文件末尾 §12 有 D 全部文书的 `sha256-12`；重启后第一件事是核对这些哈希（防止文件被截断/丢失）。

---

## §1 身份与协作机制

- **仓库**：`/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot`（**NFS，节点重启不丢**）。
- **我是 D = 监管 / 口径裁定**。**不写实现代码、不提交 git、不覆写别人的产物**；共享文书**只追加**。
- **协作全靠文件**：`rl_harness_supervision/`（D 的执行单与备忘）、`work/decisions/`（决定登记）、`daily_report.md`（各线追加自己的小节）、`work/project_parameters.json`（**D 单写**的参数/口径表）、`runs/vla/{a2,b2,c2,d}_*` 与 `runs/infra/{c2,e}_*`（各线产物，**目录名必须带线前缀**）。
- **单写者席位**：`work/project_parameters.json` = **D**；**git = B2**（裁定 49.6；D/A2/C2/E 均不提交）；`work/decisions/registry/` = **B2**（C 移交，裁定 47.2）。
- **活线**：**A2**（π₀.₅ 底模与仿真贯通）、**B2**（数据与判据/git）、**C2**（契约/normalizer/obs/闸审计）、**E**（GPU 渲染解锁 = 吞吐线）。**A/B/C 已冻结**（收尾产物是冻结面，接着用不重做；`rl_harness_supervision/d_freeze_abc_20260929.md`）。

## §2 项目目标与基线（**不要再次偏离**）

- **目标**：实机自动搬运（A 区 → B 区，正反双向），路线 = **预训练 VLA + 本机少量示范 SFT/BC + 在线 RL + Harness 纠正与监督**。
- **设计基线 = `RL_Harness_v4_20260924/`（只读）**，关键行号：`:5`（允许少量 SFT、**初始成功率可为零**、**不使用 ACT**）、`:7`（同一目标条件模型学正反两任务；BC＋在线 RL 转成 policy 参数中的能力）、`:315`（**原生路线若用更少改造通过同等门槛应优先采用**）、`:340`（发布检查：**不许以"加载未报错"即通过**）、`:346`–`:353`（P0–P6 阶段表）、**`:355`（首个迭代只打通"抓空→Harness 同协议纠正→数据＋BC→一次 RL 更新→双向无动作辅助评估"）**、`:357`–`:363`（**policy 无动作辅助能力是主结果**）、`:376`（**RL 的对照必须是同预算的动态 Harness-DAgger/BC**）。
- **历史偏差（已纠）**：09-24 起曾把「官方 LeRobot ACT on robosuite Lift」当主线，并用一条**自设晋级门**把 VLA 挡在外面；09-29 16:5x 作废该门、主线纠回 v4（裁定 38），ACT/Lift 线冻结为**辅助实验/环境与方法学基线**，**不进 v4 主线能力结论**。
- **纪律（由该偏差升级而来）**：**任何"前置条件/晋级门"第一次被引用前，必须与 v4 原文对撞并留下行号**；自设门被反复引用会获得既成地位。

## §3 平台与硬件事实（全部本机实测）

| 项 | 值 | 备注 |
|---|---|---|
| 实机平台 | **松灵 Cobot Magic**（分体式 ALOHA 具身遥操，多臂） | **被控臂 = Piper**；实机交互**已触发式延期**（裁定 55.5） |
| 主线仿真代理 | **`gym_aloha/AlohaTransferCube-v0`**（ViperX300 双臂） | 形态 **`aloha_bimanual_14d`**；模型实测 **`nq=23, nv=22, nu=16, ncam=7`**、`m.opt.timestep=0.002`；`max_episode_steps=300` |
| 底模 | **`lerobot/pi05_base`（π₀.₅）**，**3.6168 B 参数 / 812 张量 / fp32 / 13,812.5 MiB** | 加载验证 **`verdict="all_bitwise_equal"`**、`n_model_keys_not_covered_by_ckpt=0`；权重目录**只读**；tokenizer = `google/paligemma-3b-pt-224` |
| ABC-130k | **YAM 形态**（不是 Piper），本地 `workplace/ABC130k`（train 180 任务 / val 163）+ `yfw_input/0730/XDOF_ABC-130k` | **只作形态/格式参照与 QC 指标**；**其 stats 禁用于主线 normalizer**（裁定 43.4/52/61）；源目录**一律只读** |
| GPU | **1× A800-SXM4-80GB**，驱动 **590.48.01**，`/dev/nvidia2`（不是 nvidia0）+ `/dev/nvidiactl` + `/dev/nvidia-uvm` | **单卡共享，优先权 A2 > C2 > E**；**>10 分钟占用必须在 `daily_report.md` 事前申报** |
| CPU | **cgroup 配额 12 核**（`cpu.cfs_quota_us=1200000`）；**`nproc=112` 是宿主数，不作分母** | 每个吞吐数字必须**成对带 `loadavg` + `nr_throttled`**（`/sys/fs/cgroup/cpu/cpu.stat`）；21:2x 实测 `loadavg≈51`、`nr_throttled≈3270`（机器很忙） |
| **GPU 渲染** | **已解锁（E 线 21:0x 实测）**：`GL_RENDERER = NVIDIA Corporation \| NVIDIA A800-SXM4-80GB/PCIe/SSE2 \| 4.6.0 NVIDIA 590.48.01` | **合规用法 = prefix-only**：`LD_LIBRARY_PATH` + `__EGL_VENDOR_LIBRARY_FILENAMES` 指向 **`.codex-persist/nvidia-gl-590.48.01/`**（NFS，重启不丢）+ **`MUJOCO_GL=egl`**；**禁止系统写入、禁止 `ldconfig`**；**`osmesa` 装了库也永远走 CPU**（负对照实测） |
| 渲染/吞吐关键数字 | `gym_aloha` 480×640：**7.91 → 109.09 steps/s（13.8×）**，图像 `mean 39.892 → 39.869`（语义不变）；`robosuite_lift` 256²：**11.58 → 101.78（8.8×）**；mujoco 裸渲染 256²：**2042 fps RGB / 2522 fps depth**（vs llvmpipe 63–80 fps）；**ManiSkill3 像素档（64 envs, 512², `cuda:0`）与 Vulkan 均 ✅**（原判定 ❌，已推翻） | CPU 基线（**仍有效，五元标注 `osmesa`**）：单臂 Piper 3 相机 224² = **12.88 ctrl-steps/s**、并行上限 **4**（8 进程效率 0.54）；**瓶颈 = 网格面数**（单臂 Piper **183,746 faces / 91,886 verts**），分辨率无单调效应（27 进程复现，A2 独立复现） |
| 控制频率 | **主线 = 29.4118 Hz（`DT=0.034` = 17×0.002）**，落在团队 QC 区间 **[29.0, 31.0]**；**每控制步硬预算 34.0 ms**（33.3 ms/30.0 Hz 降为名义锚） | **精确 30.0 Hz 不可实现**：`dm_control/rl/control.py:168`–`:194` 对非整数倍 **`raise ValueError`**（`DT=1/30` 实测报错）。shim = `envs/gym_aloha_shim.py`（`sha256-12 dc14466fcdcf`，`site_packages_modified=false`） |
| π₀.₅ 推理 | **0.517 s/chunk**（chunk=50、`num_inference_steps=10`、A800、fp32）⇒ 29.4118 Hz 下覆盖 **1.700 s** ⇒ **占预算 30.4%** | 旧闭环数字（`loop_fps≈10.5`、`0.21× 实时`）是 **CPU 渲染口径**，GPU 下**需重测**，瓶颈会移到推理 |

## §4 E2E-min（主线，正文 `rl_harness_supervision/d_simchain_e2emin_20260929.md`，270 行）

**"跑通"的定义（裁定 54.1）**：**S1–S6 各自有可核证据 + S6 的一次 RL 更新在双向无动作辅助评估上给出方向性证据（无增益也算结论、须带诊断）；成功率高低不是出口条件**（v4 `:5`/`:346`）。**产物里禁用「跑通/学会/达标」，只用 v4 五档状态词**（未实施 / 已实现未验证 / 回放通过 / 仿真通过 / 真机通过）。

| 段 | owner | 状态（21:3x） | 出口判据要点 |
|---|---|---|---|
| **S1 仿真双向示范** | **B2** 主 + A2 供契约 + C2 供判据 | **未开工 = 全仓唯一真正卡链的阻塞** | 正/反各 ≥N 集（N 待 B2 提案，D 建议先 5 集再扩 50/方向）；29.4118 Hz；专家自证成功率（`proposed` <50% 先修专家）；反向必须自建判据（`env.py:174`–`:180` 的 `reward==4` **只覆盖右→左**）+ 几何真值 + flick 检出；3 条变异体 |
| **S2 normalizer 契约与 stats** | **C2**（T-C2-1，P0） | 进行中（依赖 S1 先导 5 集） | **主线 stats = 与示范同源**（裁定 52）；env 推导版**只作诊断**；四条真牙（`features` 非空 / 每维 scale 下限 / **起态覆盖闸**：`max|state|=1.16`、原始 2/14 维越界 → 归一化后越界维数=0 / clip 比例上限）；**「对 ctrlrange 覆盖率 ≥0.95」已驳回为红判据（极性错）** |
| **S3 π₀.₅ 小规模 BC/SFT** | **A2** 主 | 未开工 | 同一 θ 学双目标（**不训两个模型**）；原生头优先（v4 `:315`）；留出集可测改善 + **导出/部署一致性**（v4 `:340`）；3 条变异体 |
| **S4 harness↔VLA 接线** | **A2**（`harness/vla_runtime.py`）+ **C2**（`harness/env_gym_aloha.py` + 四类判定接 ledger）+ **B2**（闸与三版本记录） | **本轮新识别的无主缺口，已指派** | 缺口证据：`harness/runtime_adapter.py` **全文 77 行 = mock + 单 slot**；`harness/env_factory.py:1`–`:45` = reach/robosuite monkeypatch shim ⇒ **都不能承载 chunk=50 → 29.41 Hz 下发**。**不许改 `harness/contracts.py`（冻结面）**，只允许加法式新增；`queue_td_learner.py` 属降级线不复用；出口 = 一条**可手算短轨迹**逐字段手核（v4 `:348`）+ obs 键白名单闸不静默丢图 |
| **S5 冻结策略双向评测** | A2 跑 + C2 判 + B2 闸 | 未开工 | v4 `:357`–`:363`：关闭 Harness 动作辅助；三口径分开（policy 自主成功率 / 系统完成率 / 干预率）；失败类型分布；并行度待 GPU 口径重测 |
| **S6 一次 RL 更新闭环** | A2（可行性）+ C2（语义）+ B2（闸） | 未开工 | v4 `:355` 全链条；**原生路线优先**（更新 π₀.₅ 部分参数，优先 action expert），residual/价值选候选为备选；**对照 = 同预算动态 Harness-DAgger/BC**（v4 `:376`）；先做梯度可达性/显存峰值/导出一致性探针 |

**关键路径**：**B1 示范 → B2 stats → B3/B4（可并行）→ S3 → S5 → B5 RL 可行性 → S6**。
**降级/暂停**：双臂渲染、实机与采集窗口、Lift/小网络 SAC/`queue_td_learner`、T-C2-6（`registry/` 多门禁）、文献检索；C2 的 T-C2-4 保留 P0 但**限时**（只审"在长的闸 + S1–S6 新闸"）。

## §5 阻塞台账（21:3x）

| # | 阻塞 | owner | 状态 |
|---|---|---|---|
| B1 | 仓内**无一集主线仿真示范**；gym-aloha **无 expert**，且 **EE/mocap 通道在 `env.py:121` 是死代码**（需绕开 `AlohaEnv._make_env_task` 自行构造 `control.Environment`，见 §9.1 更正） | B2 | 未开工 |
| B2 | 主线 stats 不存在（`normalizer_processor.config.features={}` ⇒ 状态通道饱和，`waist` 仅 0.3183 行程可表示） | C2 | 进行中 |
| B3 | obs 图像键会被静默丢弃（`harness/queue_td_learner.py:134` 的 `_obs_vector` 只挑 state 类键） | C2 | **探针已交付**（`runs/vla/c2_obs_key_whitelist_20260929/probe_20260929/`，含双向变异 + `selftest.json`），**补丁待做** |
| B4 | harness↔VLA 运行时接线不存在 | A2 + C2 + B2 | 已指派，未开工 |
| B5 | RL 更新 π₀.₅ 的可行性未探（梯度/显存/导出一致性） | A2 | 未开工（S3 之后） |
| B6 | **git 代提交仍未落**：HEAD **`e6c661e`**，脏 **55 项**（21:2x） | B2（裁定 49.6） | **未做（最高优先的旧账）** |
| B7 | **GPU 渲染的下游吞吐只在"系统安装态"测过**，主线要用的数字必须来自**合规的 prefix-only 路径** | E（E3-2） | 未做 |

## §6 各线状态与欠账（21:3x）

- **A2**：频率 shim **已交付并验收通过**（`envs/gym_aloha_shim.py` + `runs/vla/a2_hz_shim_29p4118_20260929/hz_shim_verification.json`），**且纠正了 D 一处**（`from … import DT` 的绑定问题 → 裁定 57.4 纪律）。**欠**：`harness/vla_runtime.py` 接口草案、GPU 下重测闭环延迟、亮度对比的**结论行**（`brightness_reference_abc130k.json` 已到，参照集是 YAM ⇒ 标 `morphology_proxy=yam`，不得当 Piper 标定值）、裁定 44.1 最后一项（blocker→成功之间改了什么）、tied 检查抄进 zeroshot 产物、S6 前置探针计划。
- **B2**：**欠**：git 代提交（B6）、S1 脚本专家方案 + **N 集数提案** + 反向判据草案 + 专家成功率阈值、`V-pi05-1` 按裁定 48.4 重锚（锚 git commit `dcddb970176382c0fcf4521b0c0e6fc15894dfe0` + `siglip.check` 返回 True）+ 3 条变异体、`V-pi05-3` 顶层渠道填 `mixed`、频率闸 required 值改 **29.4118 Hz**、**ABC-130k 产物加 `not_for_mainline_normalizer=true`**（裁定 61）。已交付：准入闸自检（37 变异 ok / 9 反向 / baseline 绿）、qc_calib、`b2_abc130k_pairs_20260929/`（`morphology_proxy="yam"`、源只读、license 标 `external_unverified` ⇒ 这三条做得对）。
- **C2**：已交付准入自述 `docs/c2_task_selfintake_20260929.md`（179→ 现 26,375 B）与 **T-C2-2 的只读探针**（含双向牙）。**欠**：T-C2-2 补丁、T-C2-1 的 **scale 下限两个候选值 + 真实数据效果**、clip 比例上限 `proposed`、`harness/env_gym_aloha.py`（三条硬约束见其执行单 §9-2）、T-C2-4 限时审计（新增"monkeypatch 只改一半"审点）、T-C2-3（**容量测算要分 CPU/GPU 两档**）、T-C2-5、**回流单 `docs/c2_handoff_to_d_20260929.md`（尚未落盘）**。
- **E**：**E1 判定 = 可行，结果采纳**（六条绿判据 + 三条负对照全过，D 独立复核）。**有一次边界违规**（21:02 装进 `/usr/lib/x86_64-linux-gnu/`、写 `/usr/share/glvnd/egl_vendor.d/10_nvidia.json`、跑 `ldconfig`）；**做得对的部分**：没用 `rm`（备份进 `recycle_bin/e_gpu_install_20260929_210231`）、没用 apt/dpkg（`/var/lib/dpkg/status` mtime 仍 15:49）、主动回滚 + 负对照自证。**D 独立复核回滚干净**：`ldconfig -p` 里 GL 库命中 0、cache 内所有 nvidia 路径真实存在（**无 dangling**）、`egl_vendor.d` 只剩 `50_mesa.json`、系统库目录无 09-29 新增文件。**处置（裁定 60）**：结果采纳、程序违规记一次、要求 E 在回流单回答"staged 已判绿为何还做系统安装"。**欠（E3，P0）**：① `scripts/e_activate_gpu_render.sh`（prefix-only 激活 + 自证判据）；② **prefix-only 下重测下游吞吐**；③ 主线口径重标定（gym-aloha + A2 的 29.4118 Hz shim + 3 相机 224²，五元标注 + 负载对）；④ **GPU 渲染下并行度重标定 1/2/4/8，且必须测"A2 训练并发时"的吞吐与显存**，给建议值由 D 裁；⑤ 把 `docs/infra-gpu-render.md` §3 的两处 ❌ 更正为 ✅（**追加不覆写**，点名移交原作者线）。
- **A/B/C（冻结）**：产物是冻结面，接着用不重做。C 的既成资产：登记簿 **79 entries**（red=0 warn=0）、自检 **68/68**、`physical_fact` 接线 **48/48**、逐臂 manifest **246 臂**、全量回归 **17/17 exit=0**。

## §7 裁定索引（38–62，正文都在 `rl_harness_supervision/supervisor_memo_20260929.md`）

| 裁定 | 一句话 | 正文 |
|---|---|---|
| 38 | 主线纠回 v4（作废自设晋级门），ACT/Lift 线冻结为辅助实验 | 增补十七 |
| 40/41 | 实机 = 松灵 Piper → 改判 Cobot Magic 双臂 ALOHA；**iflytek 端点永久关闭**；仿真代理选 gym-aloha | 增补十八 |
| 42 | 渲染口径（单臂 + osmesa；像素档判定可行，不退 state 档、不换节点） | 增补十九 §72 |
| 43 | Piper 契约"三值并列"（夹爪行程 URDF 50mm / MJ joint 35mm / MJ ctrl 47.5mm；J6 差 1.0456 rad；模型级 8 DOF/臂 vs 指令级 7）；夹爪耦合归 A2；**按关节 TYPE 检测，不按关键词** | §73 |
| 44 | A2 三处绕障的处置 | §74 |
| 45 | 控制频率锚定 30.0 Hz（**已被裁定 53 改判为 29.4118 Hz**）；31.25 Hz 作废为契约值 | §76 |
| 46 | **zero-shot `0/20` 不是能力结论**（机制 = 无 stats 导致状态通道饱和）；撤销"后端统一钉死 osmesa"；跨口径数字不得互搬 | §77 |
| 47 | C2 建线边界与准入；C 留的两项（写入边界追认 / 待办 6 不批） | §78 |
| 48 | **撤销 `transformers >= 4.57.1` 红线**（真卫语句是 `siglip.check`，只认 4.53.2/4.53.3 的 **git 构建 commit `dcddb970…`**；装 >=4.57.1 会让 π₀.₅ 加载失败）；`torch==2.6.0+cu124` 不动 | §79 |
| 49 | C2 六条任务处置（1/2/3/4/5 批，6 暂缓）；**git 单写者 = B2** | §79 |
| **50** | **D 自我纠错**：撤销 48.5 的错误驳回（`load_verification.json` 有 18 个顶层键，`compare.n_bitwise_exact=812`、`n_model_keys_not_covered_by_ckpt=0`、`verdict=all_bitwise_equal`）；**立"否定型主张必须先枚举"纪律**；采纳 C2 的 grep/计数三元组纪律 | 增补二十 |
| **51** | C2 五项需裁项逐条裁（**驳回 ctrlrange 覆盖率 ≥0.95 作红判据 = 极性错**；video-backed obs 只报不改） | 增补二十 |
| **52** | **stats 源改判**：主线 = 与示范同源；env 推导版降为诊断；ABC-130k(YAM) 继续禁用 | 增补二十 |
| **53** | **频率第四次改判 = 29.4118 Hz / 34.0 ms**（`dm_control` 对非整数倍 `raise ValueError`）；**口径搬运禁令** | 增补二十 + `d_simchain_e2emin_20260929.md` §2 |
| **54** | **E2E-min 六段重排**；S1/S4 两处无主缺口指派 | 同上 §3–§4 |
| **55** | **E 线建立**；**撤回两项欠用户的请求**（解除单臂 / 实机窗口）；**「只渲单臂」作用域 = 只约束 Piper 资产线**；上报纪律 | 同上 §0–§1 + `d_handoff_to_e_20260929.md` |
| **56** | D 自我复核：**EE task 是死代码（更正 S1）**；EGL 入口点经 `eglGetProcAddress` 可取（更正 E 任务书 §3.1-1）；`drm_device_file=null` 证伪 `/dev/dri` 断言 | `d_simchain_e2emin_20260929.md` §9.1–§9.3 |
| **57** | A2 的 shim 验收通过；**monkeypatch 必须核对使用方 import 形式**（`from m import X` 要同时改绑定 + 配"只改一半"变异体） | 同上 §9.4 + `d_handoff_to_a2_20260929.md` §14 |
| **58** | **用户委托 D 自行确认的两项已确认生效**（单臂作用域 / 29.4118 Hz），各带**可推翻条件**；`episode_horizon_s=10.2`（300 步不缩放，超时按秒登记） | 同上 §9.5 |
| **59** | **渲染后端改判 = `MUJOCO_GL=egl` + prefix-only NVIDIA vendor**；osmesa 降为 CPU 对照/退路；并行上限 4 需重测 | `d_handoff_to_e_20260929.md` §8.1 |
| **60** | **E 的边界违规处置**：结果采纳、程序记一次、回滚经 D 独立复核干净；主线一律 prefix-only | 同上 §8.2 |
| **61** | **ABC-130k 产物必须加 `not_for_mainline_normalizer=true` + `allowed_use`** | `d_handoff_to_b2_20260929.md` §12-4 |
| **62** | C2 的 `env_gym_aloha.py` 三条硬约束（复用 A2 shim / monkeypatch 变异牙 / 回合时长按秒） | `d_handoff_to_c2_20260929.md` §9-2 |

## §8 全仓硬约束（**违反即事故**）

1. **永不用 `rm`** ⇒ 清理走 `/workspace/mnt/sppro/yhzhang91/recycle_bin/`。
2. **永不碰** `/workspace/mnt/sppro/yhzhang91/datasets`；**`RL_Harness_v4_20260924/` 只读**；**原始权重目录只读**（`.codex-persist/hf-cache/modelscope/lerobot/pi05_base`）。
3. **不做任何系统级写入**：不 `apt install` / 不 `dpkg -i` / 不写 `/usr/lib`、`/usr/share`、`/etc` / 不 `ldconfig` / 不改 `NVIDIA_DRIVER_CAPABILITIES`（E 已违规一次，见裁定 60）。**GPU 渲染只用 prefix-only 激活。**
4. **不改别人的 venv 与 site-packages**（`pi05_sim`、`lerobot_eval`、`lerobot_act`、`rlrobot`、`maniskill_probe` 均已验收）；改口径走**本仓自有 shim**。
5. **冻结面不动**：0928 两份 lock、`arms_summary_v3.json`、门禁 `requirements.lock.txt`、`clip*.json`、`harness/contracts.py`、`harness/runtime_adapter.py`、`configs/`。
6. **run 目录必须带线前缀**：`runs/vla/{a2,b2,c2,d}_*`、`runs/infra/{c2,e}_*`；脚本 `scripts/{a2,b2,c2,e}_*.py`。
7. **每个数值主张成对带 `loadavg` + `nr_throttled`**；并行度分母用 **12 核**；**跨 venv/后端/模型/环境的数字不得互搬**（裁定 46.4/53.6）；外部事实标 **`external_unverified`** 且不与本机实测同表；只有声明值支撑的标 **`declared_only`** 且**不得 blocking**。
8. **闸必须双向有牙**（能被具体篡改打红 + 反向变异不误红）；**恒真的闸等于没有闸**（裁定 27.1）；参照 B2 `mutation_verdict.json` 格式。
9. **覆写自己的产物前留 before 影像 + `sha256-12`**（裁定 35.1）；共享文书**只追加**，追加前 `git status` + `tail`，追加后报代提交人。
10. **版本声称必须比到 local tag / commit / dist-info 指纹**（`torch 2.6.0` vs `2.6.0+cu124` 是不同产物；`transformers 4.53.3` PyPI 版 vs git 构建 `dcddb970…` 是不同产物）。
11. **禁用词**：不写「跑通」「学会」「达标」；只用 v4 五档状态词。
12. **D 不提交 git、不写实现代码、不自选退路**（分叉交用户；用户 21:2x 已授权"判断无误可直接确认执行"⇒ 技术性口径 D 可自决并写死可推翻条件）。

## §9 D 的三条自我纠错纪律（**本日四次同型事故，务必继续执行**）

1. **`redline_provenance_discipline`**：任何版本/阈值/下界红线，**首次入文书前必须读卫语句或判据的实现原文并留 `file:line`**；只有声明值支撑的标 `declared_only` 且不得 blocking。
2. **`absence_claim_discipline`**：任何否定型主张（"证据不存在/命中 0/某字段没有"）**必须先枚举完整键集或清单**，并落命令原文 + mtime + 计数。
3. **`caliber_transplant_ban`**：任何频率/延迟/吞吐/分辨率口径，**首次用于新 (venv,后端,模型,环境) 组合前必须在该组合内重测或读实现原文确认可实现性**。
   **四起同型**：31.25 Hz 当契约值 / 渲染后端钉死 osmesa / `transformers>=4.57.1` / `1/480+decim16` 从原生 mujoco 搬到 dm_control。**共同根因：读了声明、搬了口径，没读实现。**
4. **`user_ask_admission_rule`**：欠用户的请求项，**必须先证明它阻塞 E2E-min 的某一段**，否则不进上报清单。

## §10 需要用户的项（**当前无阻塞项**）

用户 21:2x 明示「后续你判断无误可直接确认执行」⇒ 原两项（单臂作用域 / 29.4118 Hz）**已由 D 确认生效（裁定 58）**，各带可推翻条件。
**仍属用户保留、但已触发式延期、不阻塞主线**：① 是否解除"只渲单臂"（D 已撤回请求，**默认不解除**）；② 实机采集窗口与人力（触发 = S5 通过 + S6 有方向性证据）；③ Piper SDK / 实机标定接触（用于收敛夹爪三值与 J6 的 1.0456 rad）；④ **若要求仿真代理也改单臂形态 ⇒ 等于换底模，属路线分叉，必须用户明确指令，D 不自行推进**；⑤ C2/E 的工时预算。

## §11 重启后 D 的接续步骤（照顺序跑）

```bash
cd /workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot
date "+%F %T"; cat /proc/loadavg; grep -E 'nr_throttled|throttled_time' /sys/fs/cgroup/cpu/cpu.stat
git log --oneline -1; git status --porcelain | wc -l          # HEAD 应仍是 e6c661e，除非 B2 已代提交
tail -60 daily_report.md                                       # 看各线最新小节
ls -1t runs/vla/ runs/infra/ | head -30                        # 看新产物（按线前缀）
ls -1t docs/ | head -15                                        # 看新文书（含各线回流单 *_handoff_to_d_*）
sha256sum rl_harness_supervision/d_*.md work/project_parameters.json | cut -c1-12,65-   # 与本文件 §12 对账
python3 -c "import json;d=json.load(open('work/project_parameters.json'));print('rev',d['revision_history'][-1]['rev'],'measurements',len(d['measurements_and_decisions']))"
```
**然后按优先级处理**：① 各线回流单（`docs/{a2,b2,c2,e}_handoff_to_d_*.md`）→ 逐条裁；② B6 git 代提交是否落地；③ B1 示范数据是否开工（**这是全链唯一真阻塞**）；④ 新产物是否有"恒真闸/跨口径搬用/否定型主张未枚举"三类问题；⑤ 追加 `daily_report.md` 的 D 小节 + 更新本断点文件（**每次重大裁定后都要更新 §4–§7 与 §12**）。

## §12 D 文书完整性清单（`sha256-12`，21:3x）

| 文件 | 行数 | sha256-12 |
|---|---|---|
| `rl_harness_supervision/d_simchain_e2emin_20260929.md` | 270 | `8ebf8d8308d1` |
| `rl_harness_supervision/d_handoff_to_e_20260929.md` | 173 | `9f4e3dc55481` |
| `rl_harness_supervision/d_handoff_to_a2_20260929.md` | 530 | `dc97a7dbc792` |
| `rl_harness_supervision/d_handoff_to_b2_20260929.md` | 397 | `4b1c898fe6ba` |
| `rl_harness_supervision/d_handoff_to_c2_20260929.md` | 265 | `b25d78540198` |
| `rl_harness_supervision/supervisor_memo_20260929.md` | 2268 → 见增补二十一后更新 | `535b740c0ff8`（增补二十后） |
| `work/decisions/decisions_20260929.md` | 1182 → 见 DR-D52 后更新 | `22f9d91d6c2f`（DR-D51 后） |
| `work/project_parameters.json` | rev9（63 条）→ rev10 待落 | `d8d23be3e722`（rev9） |
| `daily_report.md` | 4234 → 追加中 | `3c460935db6e`（21:0x 节后） |
| **before 影像（都在 `runs/vla/d_render_probe_20260929/`）** | — | `project_parameters.rev8.json` = `32475cf20dc5`；另有 memo/decisions/daily_report 的 before 影像 |

> **注**：本文件自身写入后哈希会变；**§12 里 memo/decisions/params/daily_report 四项在增补二十一与 rev10 落地后需回填一次**（D 在本轮末尾更新）。

---

# §13 【2026-09-29 22:3x 更新 —— **本节取代 §4–§7 与 §12；重启后先读本节，再按需回查上文**】

**本节写入前 before 影像** = `runs/vla/d_ruling_round_20260929_2200/rl_harness_supervision_d_context_checkpoint_20260929_2130.md`（160 行，`sha256-12 3ccacb42d138`）。**本节为追加，未修改 §1–§12 任何一行。**

## 13.1 【更正 §3 的一处事实错误 · 裁定 70】渲染前缀目录名

- **§3 表格里"合规用法 = prefix-only：… 指向 `.codex-persist/nvidia-gl-590.48.01/`"是错的 —— 该目录不存在**（D 实测 `stat` → `No such file or directory`；A2 与 E 双证人）。
- **正确前缀 = `/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist/egl-libs/590.48.01/`**（含 `10_nvidia.json` + `libEGL_nvidia`/`libGLX_nvidia`/`libnvidia-eglcore`/`libnvidia-glcore`/`libnvidia-glsi`/`libnvidia-gpucomp`/`libnvidia-tls` 等，符号链接齐全）。
- **规范做法（不许硬编码目录名）**：`eval "$(bash scripts/e_activate_gpu_render.sh --print)"`（脚本 21:54:06 / 5232 B / 可执行；`e_resolve_prefix` 两个候选名都试）。**产物必须落 `activation_env` + `prefix_paths_verified` 三条布尔。**
- **§3 其余各项 D 已复核无误**（实机平台 = 松灵 Cobot Magic、被控臂 = Piper；主线代理 = `gym_aloha/AlohaTransferCube-v0`；底模 = `lerobot/pi05_base` 3.6168 B/812 张量/fp32/13,812.5 MiB、`all_bitwise_equal`；ABC-130k = YAM 形态、stats 主线禁用；GPU = 1× A800 `/dev/nvidia2` 驱动 590.48.01；CPU = cgroup 12 核、`nproc=112` 不作分母）。
- **§3 需补一行（D 实测，`MjModel.from_xml_path`，21:5x）**：**两个 gym-aloha XML 都 `ncam=7`、相机名与父体完全相同**（含 `left_wrist` 父=`vx300s_left/gripper_link`、`right_wrist` 父=`vx300s_right/gripper_link`）；**EE 版 `nu=4`（actuator 名全为空串）/`neq=2`（1 个 `<equality>` 含 2 个 `<weld>`），关节版 `nu=16`/`neq=0`，两者 `nq=23`/`nv=22` 相同**。⇒ **三相机可直接从 physics 渲出（两个模型都能）；"`AlohaEnv` 只交 `top`"是 observation 面的限制，不是模型面的限制。**

## 13.2 本轮裁定清单（64–74，全文见 `supervisor_memo_20260929.md` 增补二十二/二十三；登记见 `work/decisions/decisions_20260929.md` DR-D56–DR-D60）

| 裁定 | 一句话 |
|---|---|
| **64** | **v4 引用必须带文件身份三元组 `(相对路径, sha256-12, 行号)`**；只有行号的引用不可核验、不得进裁定依据。**权威出处改双引用：附录一（`aae20ffe604f`）`:375` + 主方案（`0a9a2092e18a`）`:347`。D 第五次同型 = 未核文件身份就准备接受 A2 的"更正"。** |
| **65** | **A2 的 S4 六条裁完**：`n_replan=25`／**`max_episode_steps` 维持 300、驳回 176**／`late_policy=hold`／`lease_generation`=chunk 代际而 `epoch` 不动／行号见 64／**S4 不等 S1、立即开工（拆 S4a 立刻 + S4b 等 C2 的 env）** |
| **66** | **S1 路线定稿：EE 模型只作 IK oracle → 录 `qpos` → 在关节模型里重放并采集；不允许在 EE 模型内直接采示范**（训练/评测动力学错配）。**D 的"weld 会解算"推断被 B2 probe2 实测证伪 ⇒ 第六次同型。** 右臂给出 D-H1 假设 + 能红判据；probe4 四条实测原语（方块沉降 12 步／夹爪 cmd→spread 表／存 14 维不存 16 维／指尖偏置）；出口判据五条（任务级） |
| **67** | **E 的 E2 验收通过**（prefix-only 合规自证 + D 独立复核）；主线后端 = `MUJOCO_GL=egl` + prefix-only；`egl_mesa` 比 osmesa 更慢（0.92×）⇒ 静默回退 mesa 必须判红。**但 `11.82×` 后被裁定 71 降级。** |
| **68** | **C2 的 T-C2-2 补丁验收通过**（+17/−1 纯加法、`contracts.py` 未动、14 检查 0 红、4 变异极性全对、C 线 17/17 回归）；**同时记一次未申报的覆写违规：其回归驱动只改指 1 处输出，而 17 个自检脚本里 14 个写固定路径 ⇒ 覆写 16 个 C 线产物、无 before 影像、`runs/` 被 gitignore 故无恢复路径**。**损害可恢复（被引用数字全部保留），但原始字节 mtime 溯源已断、永久登记。** |
| **69** | **C2 六条自提任务全部裁定**（T-C2-1 P0 批 + **stats 源 = B2 的 S1 示范** + `norm_map` 两案并列；T-C2-3/4/5 P1 批；T-C2-6 由 B2 改 `GATE_MODULE_PATH` 为按 `gate_id` 查表）；**`transformers` 那条闸改判**（required = 实测版本 + commit `dcddb970…` + `all_bitwise_equal`；声明下界 `>=4.57.1` 标 `declared_only` 不得 blocking）；**`V-pi05-3` 填 `mixed`（已由 A2 的 sidecar 闭合）** |
| **70** | **前缀目录名更正**（见 §13.1）；**E3-① 销账**（激活脚本 + 自检已落盘；D 21:47 说"未落盘"是查得太早） |
| **71** | **三个自称同口径的主线渲染数字互相冲突**（E `165.65` / A2 run1 `30.522` / A2 run2 `65.865`）⇒ **E3-③ 落地前不得声明任何单一主线渲染口径值**；`11.82×` 与 `5.63× 实时` 降级 `protocol_mismatched_not_mainline`；**规划用保守端 `30.522`（20 集 ≈3.3 min）**；**`caliber_transplant_ban` 机械化 = 逐维列出原/目标组合并比对。D 第七次同型 = 在自己写下禁令的同一轮里违反它。** |
| **72** | **A2 提的两条规则升为全仓纪律**：`renderer_identity_evidence_discipline`（**`MUJOCO_GL` 表达意图、`GL_RENDERER` 才表达事实**）+ `selftest_must_execute_acquisition_path`（**自检至少要有一案真的调用被测的取数函数**）；**新增 `self_artifact_reuse_discipline`**（复用自己早先的读法/键名/路径必须重读原文留 `file:line`+`mtime`）+ **`gate_applicability_declaration`**（每道闸声明 `applies_when`，不适用输出 `n_a` 而非 `ok=false`；聚合器必须能区分）+ **`false_red_archival_format`**（A2 run1 的归档格式 = 本仓最好的一次，B2/C2 照抄） |
| **73** | **静默窗口制度**：凡"要成为权威口径"的标定测量必须在申报过的窗口内做；**每臂落 `cotenant_evidence`，窗内存在非本线 GPU 进程或 `loadavg_1m` 高出 ≥5 ⇒ 自动标 `contaminated`**；**首次触发 = E 的权威臂（22:14）被 A2 的 GPU 作业（22:16）污染 ⇒ 优先权在 A2，E 让并重跑**；**更正 D 自己：并行度上限 2 只约束 A2/B2/C2 的生产性作业，不约束 E 的标定扫描**；**A2 的 22:0x GPU 申报格式采纳为全仓模板** |
| **74** | **`n=25` 由实测支撑**：`n=50` `mean_loop_fps=59.176`（占预算 49.7%，**但违反 `H≥2n` 不能用**）；**`n=25` `38.055`（26.28 ms/步、657 ms/chunk、占 `850 ms` 的 77.3%、余量 22.7%）**。**A2 外推的 61.6%/38.5% 乐观了 15.7 个百分点，A2 自己标了 `proposed_from_g3_measurement` 救了它。裁定 65-1 维持不变（依据是 v4 合规、不是延迟）。** |

## 13.3 D 本日同型事故台账（**七起，共同根因始终是"读声明不读实现"**）

| # | 事故 | 升级成的纪律 |
|---|---|---|
| 1–4 | 31.25 Hz 当契约值 / 渲染后端钉死 osmesa / `transformers>=4.57.1` / `1-480+decim16` 跨环境搬运 | `redline_provenance_discipline`、`caliber_transplant_ban` |
| **5** | 未核文件身份就准备接受 A2 的"行号更正" | **`citation_file_identity_discipline`** |
| **6** | 从 XML 里有 `<weld>` 推断"weld 会解算"，被 B2 probe2 实测证伪 | **"能解算/能收敛"类主张必须实测或读求解器原文；只凭资产声明标 `declared_only`、不得作路线依据** |
| **7** | 用 E 的 `165.65`（stock DT + 5 s 窗口 + loadavg 47–50）算主线 S1 成本，违反自己同轮写下的禁令 | **`caliber_transplant_ban` 机械化：逐维列出原/目标组合并比对** |
| **附** | 前缀目录名不存在（引用自己先前的结论而没重读） | **`self_artifact_reuse_discipline`**（A2 的 `tied_weight` 键名是同一起的第二例） |

**D 的自评（重启后的新会话请照此继续）**：**光有禁令不够，禁令需要机械化检查点**（裁定 64 的三元组格式、71.5 的逐维比对、73 的 `cotenant_evidence` 判据、72 的 `applies_when`/`n_a` 都是把纪律变成**可失败的形式**）。**并且本轮 D 的错误有两次是被下属抓到的（A2 抓前缀路径与行号、B2 的 probe2 证伪 weld 推断）⇒ "下属可以纠正 D"这条通道有效，必须继续保护它：任何线报上来的对 D 的更正，D 必须先核实（含文件身份）再裁，既不能不加核就接受，也不能因为是自己写的就驳回。**

## 13.4 各线状态与 D 的等待项（**取代 §4–§7 的对应部分**）

- **A2（活线，22:16 起有 GPU 作业 PID 559213，持有当前单卡优先权）**：已交 `docs/a2_s4_vla_runtime_interface_20260929.md`（394 行，本轮质量最高的交付）+ `runs/vla/a2_egl_latency_20260929/`（run1 已归档为 `gpu_run1_two_a2_defects/` 并附 `WHY_ARCHIVED.md`；run2 `latency_mainline_egl_gpu.json` 22:16:55 `gates_all_ok=True`、5 道闸全绿；`latency_retro_label_no_prefix.json` `retro_label.valid=true`）+ `env_manifest.json` 10/10 `env_usable=true` + `weights_receipt_channel_sidecar.json`（`channel_top_level="mixed"`）。**D 等待**：① **S4a 开工（第一优先）**；② **run2 的 `closed_loop` 臂（`--n-action-steps 50,25`）落地并报 D**（裁定 65-1 的证据升级项；两个负载端并列，不许只报好看的）；③ 读 `appendices/02_异步动作时间轴与学习目标.md`；④ 裁定 44.1 最后一项。**已销账**：亮度结论行、egl 下重测、S6 探针计划 P1–P5、`V-pi05-3` sidecar、`env_manifest`。
- **B2（活线，git 单写者 + `registry/` 单写者）**：已交 `scripts/b2_s1_probe_ee_channel.py`/`probe2_mapping_and_replay.py`/`probe3_weld_semantics.py` + `runs/vla/b2_sim_demo_bidir_20260930/probe/{probe,probe2,probe3,probe4}.json`（probe3 崩在渲染上、如实留 `error`；probe4 把 weld 标定推进到左臂 1.3 mm 收敛、右臂 0.2469 m 发散 + 夹爪 cmd→spread 表 + 方块沉降 12 步 + 指尖偏置）。**B6 已销账（HEAD `c422659`）**。**D 等待**：① **S1 开工（全链唯一真阻塞）**，按 `d_handoff_to_b2_20260929.md` §13.5–§13.8；② N 集数提案 + 反向判据草案 + 专家成功率阈值（一次报齐）；③ ABC-130k 产物加禁用标记（裁定 61）；④ `V-pi05-1` 重锚（**必须用 A2 的新 manifest 重过闸**）；⑤ 频率闸 required 改 `29.4118 Hz`；⑥ `GATE_MODULE_PATH` 改按 `gate_id` 查表 + 3 变异体；⑦ 闸要能判"`late_policy=hold` 下迟到帧被重标为 `activated`"红；⑧ 闸聚合器要能区分 `ok=false` 与 `n_a`；⑨ **本轮结束后 git 再代提交一次**（注明 `runs/` 被 `.gitignore:12` 排除）。**已撤下**：`V-pi05-3`（A2 的 sidecar 已闭合）。
- **C2（活线）**：已交 `harness/queue_td_learner.py` +17/−1 + `harness/obs_key_coverage.py`（183 行）+ `scripts/c2_gate_obs_key_coverage.py`（468 行）+ `scripts/c2_run_c_regression_postpatch.sh` + `scripts/c2_probe_obs_key_drop.py` + `runs/vla/c2_obs_key_whitelist_20260929/`（`gate_20260929`/`probe_20260929`/`probe_20260929_postfix`/`c_regression_postpatch` + 三个 `WHY_ARCHIVED.md` 归档）。**T-C2-2 已验收**。**D 等待**：① **回流单 `docs/c2_handoff_to_d_20260929.md`（从 15:26 就位至今唯一未交的必交文书）**，含 T-C2-2 逐条判据表 + **`overwritten_c_artifacts` 登记（16 个文件的新溯源起点）** + T-C2-1 两案并列 + T-C2-4 审计（**现在 6 起**，新增 `applies_when`/`acquisition_path_untested`/聚合器 `n_a` 三个审点）；② `harness/env_gym_aloha.py`（裁定 62 三条硬约束 + 四类判定独立于 `reward==4`）；③ T-C2-1 的 scale 下限两候选 + clip 上限 `proposed`；④ T-C2-3 分 CPU/GPU 两档（**GPU 档用 `30.522`/`65.865` 两档，不要用 `11.82×`**）；⑤ 读附录二；⑥ T-C2-5 加一列 `overwritten_by_c2_regression`。
- **E（活线，22:14 起有 CPU/GPU 标定作业 PID 547802）**：已交 `scripts/e_activate_gpu_render.sh`（21:54:06）+ `e_activate_selfcheck.py` + `e_egl_probe.py`（22:10:24 改）+ `e_backend_ab.py` + **`e_mainline_render_calib.py`（22:14:15，正在跑）** + `runs/infra/e_gpu_egl_verify_20260929/`（15 JSON）+ `runs/infra/e_egl_probe_20260929/`（15 文件 + MANIFEST）。**E3-① 已销账**。**D 等待**：① **静默窗口申请 + 权威臂重跑**（裁定 73；当前这轮已被 A2 污染）；② `cotenant_evidence` 判据落进每个臂；③ **回流单必须以 `docs/e_handoff_to_d_20260929.md` 落盘**（`MANIFEST.json` 现在引用了一个**不存在**的文件 = 悬空引用；内容含**裁定 60.4 那一句回答**："staged 已在 20:59 判绿，为何 21:02 还做系统安装？"）；④ E3-②（旧 `downstream_gpu_*` 重测或标 `boundary_violated_provenance` 作废）/③（主线口径 = shim `DT=0.034` + 3cam 224² + egl，**必须在静默窗口内，且不许从 `165.65` 推算**）/④（并行度建议值含 cotenant 差值）/⑤（`docs/infra-gpu-render.md` §3/§4 追加更正三处）。
- **需用户**：**当前无阻塞项**。**保留但延期**：① 解除"只渲单臂"（默认不解除，作用域见裁定 58.1）；② 实机采集窗口（触发 = S5 通过 + S6 有方向性证据）；③ Piper SDK / 实机标定接触；④ **代理是否也改单臂（= 换底模，路线分叉，必须用户明确指令）**；⑤ C2/E 工时预算。

## 13.5 E2E-min 关键路径（22:3x）

**S1 示范（B2）→ S2 stats（C2）→ S3 BC（A2）→ S4 harness↔VLA 接线（A2+C2+B2，**S4a 已解锁不等 S1**）→ S5 冻结双向评测 → S6 一次 RL 更新。**
- **"跑通"= 每段有可核证据 + S6 给方向性证据（无增益也算，须带诊断）；成功率不是出口判据**（`01_开发技术方案.md:5`、`:348`）。
- **S1 仍是全链唯一真阻塞**（S3/S5 等它）；**S4a 与 S2 的生成器/闸可以并行推进**。
- **S1 的两个已解除的障碍**：① D 给的错误通道已作废、路线定稿（EE-oracle→关节重放）；② **渲染阻塞已由 E 线解除**（EE 通道**必须**渲染：`gym_aloha/tasks/sim_end_effector.py:120` 无条件 `physics.render`）。**S1 剩下的唯一技术障碍 = 右臂 weld 发散（按 D-H1 判定）。**

## 13.6 【取代 §12】D 文书完整性清单（`sha256-12`，22:3x）

| 文件 | 行数 | `sha256-12` | before（22:00 影像，在 `runs/vla/d_ruling_round_20260929_2200/`） |
|---|---|---|---|
| `rl_harness_supervision/d_context_checkpoint_20260929_2130.md`（**本文件；重启恢复入口**） | 160 → **本节** | `3ccacb42d138`（追加前） | 同左 |
| `rl_harness_supervision/d_simchain_e2emin_20260929.md` | 270 → **380** | **`87de84c1bd16`** | `8ebf8d8308d1` |
| `rl_harness_supervision/d_handoff_to_a2_20260929.md` | 530 → **706** | **`79e77c79d8df`** | `dc97a7dbc792` |
| `rl_harness_supervision/d_handoff_to_b2_20260929.md` | 397 → **542** | **`3ce03952be48`** | `4b1c898fe6ba` |
| `rl_harness_supervision/d_handoff_to_c2_20260929.md` | 265 → **380** | **`a8e9b4680b16`** | `b25d78540198` |
| `rl_harness_supervision/d_handoff_to_e_20260929.md` | 173 → **288** | **`312bea7807f5`** | `9f4e3dc55481` |
| `rl_harness_supervision/supervisor_memo_20260929.md` | 2310 → **2431** | **`d77ceb206b05`** | `e3d6804ffc17` |
| `work/decisions/decisions_20260929.md` | 1215 → **1266** | **`75b3a1106812`** | `9f6bae476e39` |
| `daily_report.md` | 4488 → **4578** | **`860d718d6da2`** | `0f35c4158a5b`（22:00 影像，含 21:3x 的 D 段与 A2 的 22:0x 段） |
| `work/project_parameters.json` | **rev10，76 条** | **`3b9626569685`** | `d8d23be3e722`（rev9，63 条） |
| `rl_harness_supervision/d_freeze_abc_20260929.md` | 未改 | `0304adb1bdb4` | — |

**v4 只读基线的文件身份（裁定 64 要求，重启后引用 v4 必须带这三元组）**：
- `RL_Harness_v4_20260924/materials/06_三轮递进调研与方案复审_20260923/01_开发技术方案.md` = **418 行，`0a9a2092e18a`**（`:5` 允许少量 SFT/初始成功率可为零/不使用 ACT；`:7` 同一目标条件模型学正反两任务；`:315` 原生路线优先；**`:341`** 发布检查；**`:347`** P0「请求／入队／执行可区分，能选择 n」；`:348` P1「不要求预先高成功率」；`:350` P3 可手算短轨迹；`:351` P4 最小实机闭环；**`:355`** 首个迭代只打通"抓空→纠正→数据＋BC→一次 RL 更新→双向无动作辅助评估"；**`:361`** policy 无动作辅助能力是主结果；**`:376`** RL 的对照必须是同预算的动态 Harness-DAgger/BC）
- `RL_Harness_v4_20260924/materials/06_三轮递进调研与方案复审_20260923/appendices/01_接口契约与开发验收.md` = **433 行，`aae20ffe604f`**（`:101` 首版可异步执行+分批训练；**`:103`** `H≥2n`；**`:105`–`:107`** C/E/D 三槽；`:109` 指向附录二；**`:111`** 冻结的迟到规则；`:344`–`:346` T24/T25/T26；**`:375`** requested/committed/activated 分别记录）
- `RL_Harness_v4_20260924/materials/06_三轮递进调研与方案复审_20260923/appendices/02_异步动作时间轴与学习目标.md` = **存在（D 已核实）；S6 的 TD 样本时序前提以它为准；A2 与 C2 都必须先读（裁定 69.2）**

## 13.7 重启后 D 的接续步骤（**取代 §11**）

```bash
cd /workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot
date "+%F %T"; cat /proc/loadavg; grep -E 'nr_throttled|throttled_time' /sys/fs/cgroup/cpu/cpu.stat
git log --oneline -1; git status --porcelain | wc -l      # HEAD 应是 c422659 或 B2 之后的新提交
sha256sum rl_harness_supervision/d_*.md work/project_parameters.json daily_report.md work/decisions/decisions_20260929.md | cut -c1-12,65-   # 与本文件 §13.6 对账
tail -80 daily_report.md                                   # 各线最新小节（注意有没有新的静默窗口申请）
ps aux | grep -E 'a2_|b2_|c2_|e_' | grep -v grep           # 有没有活作业；GPU 优先权 A2 > C2 > E > B2
nvidia-smi --query-compute-apps=pid,used_memory --format=csv   # GPU 是否已销账（应为 0 MiB / 无进程）
find . -path ./.git -prune -o -type f -newermt '-90 minutes' -print | grep -v __pycache__ | head -60   # 新产物
ls -1t docs/ | head -15                                     # 新文书（含各线回流单 *_handoff_to_d_*）
python3 -c "import json;d=json.load(open('work/project_parameters.json'));print('rev',d['revision_history'][-1]['rev'],'measurements',len(d['measurements_and_decisions']))"   # 应为 rev 10 / 76
```
**然后按优先级**：① **各线回流单**（`docs/{a2,b2,c2,e}_handoff_to_d_*.md` —— **C2 与 E 的仍欠，E 的那份还是 `MANIFEST.json` 的悬空引用目标**）；② **静默窗口申请的批/驳**（裁定 73）；③ **S1 是否开工 + 右臂 D-H1 的判定结果**（全链唯一真阻塞）；④ **A2 的 run2 `closed_loop` 臂（`n=50,25`）结果**（裁定 74 的证据升级）；⑤ **E3-③ 的静默窗口重测结果**（裁定 71 的对账仪器，落地后才能声明主线渲染口径值）；⑥ 新产物是否有"恒真闸/跨口径搬用/否定型主张未枚举/闸缺 `applies_when`/自检未执行取数路径"五类问题；⑦ 追加 `daily_report.md` 的 D 小节 + 更新本断点文件（**每次重大裁定后都要更新 §13.2/§13.4/§13.6**）。

---

# §14 【2026-09-29 23:0x 更新 —— **本节取代 §13.2/§13.4/§13.5/§13.6/§13.7；重启后先读本节**】

**本节写于裁定 75–81 落盘之后。** §13.1（prefix 路径更正）、§13.3（D 的七起同型事故台账）、§13.6 里的 v4 只读基线文件身份三元组 **仍然有效**，不必重读上文即可续跑。

## 14.1 本轮做了什么（一句话版）

D 完成一次**全量自核 + 裁定 75–81**：把 A2 的「n=25 超预算」认定为**同步环口径**（不是异步不可行）从而**保住 `n_replan=25`**；认定 A2 run2 与 E 的共卡批次**互相污染**、两者均降为非权威；**逐条裁完 E 回流单的 9 项**（E 欠账已清）；**接受 C2 的 T-C2-4 极性与变异审计**（其自审发现的「假绿」是本轮全仓最有价值的一条）；**接受 C2 的第二次未申报覆写（event2）登记**并判定其守卫整改**已闭合**；**逐行复核 B2 的双向脚本专家 80/80**，据此**证实 D-H1** 并**更正 D 自己的裁定 66**（EE oracle 步骤作废）；**命令 B2 先代提交 git**（脏项已 39）。本轮新立/升格纪律 **7 条**（5 红线 + 1 一般 + 1 升格）+ 2 条判据设计规则。

## 14.2 【最重要】当前链路状态：**唯一真阻塞已转移**

| 阶段 | 状态（v4 五状态词） | 证据 |
|---|---|---|
| π₀.₅ base 加载 / 接口贯通 | **仿真通过**（不含能力主张） | `a2_pi05_zeroshot_20260929/summary_pi05.json`（zero-shot **0/20**，已按裁定 44.1/46 **同句标注**「无 normalizer stats ⇒ 不构成能力结论」；随机基线同为 0/20 但 `max_stage_hist` 有 `right_lift:5` ⇒ **判据非恒真成立**）；`weights_linkage.json`；run2 `tied_weight=tie_ok` |
| GPU 渲染解锁 | **仿真通过** | E：`egl_nvidia w=1 env_step_native = 172.32 ctrl-steps/s`（5.80 ms/步 = 预算 17%）vs `osmesa 10.45`（95.73 ms = **超预算 2.8×**）⇒ **16.5×**；权威轮 `summary_20260929_221443.json` |
| env 判定层 | **仿真通过**（D 亲自复跑） | C2 `harness/env_gym_aloha.py`（579 ln, `6c4d71eb732e`, `c2-env-gym-aloha-v1`）+ 闸 `c9100b3811cd`；**D 22:52:32 复跑 offline = PASS/`n_checks=15`/`red=[]`**；online 13 条 `n_red=0`；**E11 实测 monkeypatch 只改一半 ⇒ `measured_hz=50.0` 且模块拒绝构造** |
| **S1 双向示范** | **自验通过、正式采集未实施** ← **当前唯一真阻塞** | B2 `expert_selfverify_40x2.json`（22:23:02）：forward 40 + reverse 40 = **80/80 success**，`env_reward4` 80/80、`on_goal_side_diag` 80/80、`hz` 全 = 29.411765、`n_plan_nonconverged=0`、`timeouts` 全空。**但那是 `--selftest` 且 `MUJOCO_GL="disable"`（无渲染）⇒ 不是正式采集** |
| normalizer stats（T-C2-1） | **未实施**（数据源已定 = B2 的 S1 正式示范） | 裁定 69；`abc130k_stats_forbidden=true` |
| S4a 运行时骨架 | **未实施**（A2 可立即开工，CPU-only） | 裁定 65-6（S4 不等 S1，拆 S4a/S4b） |
| S4b / S5 / S6 | **未实施** | —— |

**⇒ 链路顺序（裁定 80.4/80.5）**：**B2 补 5 项缺口 → pilot 5 + formal 20/方向** ⇒ **C2 的 T-C2-1 stats** ⇒ **A2 的 S4b 接真帧**。**A2 的 S4a 骨架与 C2 的 T-C2-1 生成器/闸可并行先做（都不依赖 B2 数据、都 CPU-only）。**

## 14.3 B2 正式采集前必须补的 5 项（裁定 80.3，**重启后第一件事就是核这 5 项**）

1. **渲染 + 渲染器身份**：自验是 `MUJOCO_GL="disable"`（`scripts/b2_s1_scripted_expert.py:53-54`）⇒ 80/80 无像素。正式采集要出 **3cam 224²**，须落裁定 72 的三串 GL + `renderer_class` + `identity_source`，且**自检必须真的调用采集函数**；后端 `egl` + prefix-only；激活一律 `eval "$(bash scripts/e_activate_gpu_render.sh --print)"`，**不得硬编码 prefix**。⚠ **不得再用 `scripts/check_gpu_render.py` 当闸**（裁定 77.9：`known_false_negative_under_prefix_only`）。
2. **负载对缺失**：产物有 `wall_s`（0.288 s/局）但**无 `loadavg`(3点)+`nr_throttled`** ⇒ 任何产能/排期数字在补齐前一律 **`declared_only`**、**不得进参数表、不得用于排期**。
3. **五元组 + 版本三元组 + `as_of` 脚本 sha**（B2 脚本 30 分钟内从 1127 ln/`25ffe837896a` 变成 1162 ln/`952437930706` ⇒ sha 不稳，必须带 `as_of`，裁定 78.11）。**建议直接复用 C2 的 env 判定层，不要自造**（否则与 J1–J15 分叉）。
4. **规模 = pilot 5 + formal 20（每方向）**；**80/80 是自验规模，不得替代 formal 20**。
5. **replay 逐位可复现**（同 seed 重跑）。

## 14.4 裁定 75–81 一句话索引（全文在 `work/decisions/decisions_20260929.md`，1419 ln，`5ab60141fa06`）

- **75** A2 的 `n=25 超预算（1.218×）` = **同步串行环口径**（D 独立核算：`t_infer+t_render+t_env+t_other` 严格相加 = `episode_wall_s` ⇒ 零重叠；n=25 每局 12 次推理 ×0.7204 s = 8.645 = `t_infer_s`）。v4 `:103` 的 `H≥2n` 本是**异步**条件 ⇒ **`n_replan=25` 维持**（依据 = v4 合规，非延迟）；异步下摊薄推理 27.330 ms < 34.0 ⇒ **占比 80.4%、裕量 19.6%**。预算改为**软约束 + `overload_flag`**（**P4 真机不适用**）；**异步实测前禁止写「实时闭环」**（最小证据 = `queue_drain_events` + 两个 ms 分列 + 负载对 + 运行时 cotenant 采样）；**E 的「2.1× 余量」属 n=50 摊薄、不得搬到 n=25（真实余量 2.6%）**；`num_inference_steps`/bf16 = P4 前置且 bf16 须另开 `representation_version`；**n=17 不推荐**。
- **76** A2 run2 与 E 的 4 个 `proxy_a2` 批次 **互相污染**（E 的假体从未启动，实际与 A2 的 π₀.₅ PID 559213 共卡 ≈6.5 s；A2 的窗 22:16–22:21 被 E 的 PID 547802 污染）⇒ **两者均不得作权威**。**A2 权威端 = run1（38.055/59.176）；E 权威轮 = `summary_20260929_221443.json`**；首轮 `220400` 仅留档。**责任在 E**（优先级 A2>C2>E>B2 应让路），E 已改**批级闸** ⇒ 新红线纪律 **`per_batch_gpu_yield_gate`**；A2 的 `collected_at_run_time=false`（22:38 事后重建）⇒ 新红线纪律 **`cotenant_evidence_must_be_runtime`**；**强制一次 quiet-window 权威重测**（n=25/n=50 各 ≥2 次重复 + 负载对 + 运行时采样）。E 的第三次自报（裸 `python3` 致假红）⇒ 加 `environment_invalid` 闸（`exit 5`，不伪装成「不通过」）= **`false_red_archival_format` 的第二正面样本**。
- **77** E 回流单 9 项逐条裁（**E 欠账已清**）：4-1 CPU 权威基线 **12.88**（`12.03` → `retired_caliber`，MANIFEST 由 D 更正）；4-2 `parallel_eval_workers_cap` **分场景 4（S5/共卡）与 8（S1 独占+已申报）**，**口径警告：数字相同、推导不同，不得当「延续」**；4-3 后端 **egl + prefix-only**（但 2.1× 撤回、规划口径标 `derived_not_measured` ⇒ **主线规划一律用 A2 的 38.055**）；4-4 平台申请**降级为非阻塞改善项** + 删 `/dev/dri`（**D 的文书错误**）；4-5 **确认不需补单臂 GPU 数字**；4-6 **改文书不改目录**，prefix 统一 **`.codex-persist/egl-libs/590.48.01/`**；4-7 **五项产物全留**（`gpu_render_20260929_*` 保留原名不重命名）；4-8 保留原文 + §7 更正，**授权 E 在 §1 顶部加一行指针**（不改原结论行）；4-9 **`check_gpu_render.py` 保持冻结不改**。E 提的纪律「**已判绿的路径，不得为了『顺手多验一点』再走违规路径**」+ 系统写入须事前书面批准 ⇒ **升红线级**，且 E 已做成代码闸（`--apply` 须 `E_ALLOW_SYSTEM_INSTALL=<批准文书路径>` 且文件真实存在，否则 `REFUSE`/exit 1）。
- **78** C2 的 T-C2-4 审计**接受**。**C2-4 = 本轮全仓最有价值的发现**：变异体构造器复用旧 `harness` 副本 ⇒ 子进程 import 到**未变异旧副本** ⇒ **假绿（牙不咬）**；C2 的定性「**假红会被人发现，假绿不会**」D 完全采纳 ⇒ 新红线纪律 **`mutant_construction_isolation`**。三条上报裁完：**最小公共 check schema `id/ok/status/required/observed/red_when`** + 顶层 `ok` 唯一失败判据 + **`UNJUDGED` 计入非绿** + 顶层四元组（78.2）；委托闸补 **45 条 `id`** + 去 `"  G2_..."` 的**两个前导空格**（78.3）；**`delegated_g1_g5_freeze` 降级为「清单核对」**（25 条从未非绿且无变异体）、`delegated_v0_v9` 标 `teeth_delegated_to_upstream`（78.4）。**F3 WARN 极性错 ⇒ B2 必修**；**F5 ⇒ A2 补两份 `WHY_ARCHIVED.md`**（run3 = 唯一模板实例）。**F7 三处实现层恒真/吞异常 ⇒ 判据设计约束**（`normalize_processor.py:305-307` 静默 IDENTITY ⇒ T-C2-1 必须显式断言 `stats_present=true`；`:362-377` `denom` 只防 0 无下限 ⇒ 必须实现每维 scale floor + 近常量维标记；`modeling_pi05.py:995-998`+`:1046-1047` 缺键静默返回随机权重 ⇒ **S3 出口第 2 条必须显式查缺失/多余键**）。**D1 ⇒ C2 的独立读码证实裁定 69**：真卫语句是 `modeling_pi05.py:576-584` 的 siglip `check_whether_transformers_replace_is_installed_correctly()`、A2 的 4.53.3 是 git 构建（commit `dcddb970…`、branch `fix/lerobot_openpi`）其 `check.py` 只接受 4.53.2/4.53.3 ⇒ **装 `>=4.57.1` 会让 π₀.₅ 直接加载失败**；B2 不得再以声明下界判红。**D3 ⇒ 147 KB（PNG 压缩推算）与 1765.19/2701.04 KB（`np.savez` 未压缩实测）分开登记、不换算**。**78.11 文件身份时序问题**：审计 `:253` 引 `387f78e2c49f` 而当前是 `6c4d71eb732e`（mtime 22:09:11 > 审计 22:07:14）⇒ **证据有效、引用过期** ⇒ C2 补勘误行 + 新红线纪律 **`citation_sha_as_of_discipline`**。
- **79** C2 的 **event2（第二次未申报覆写，22:33:45–22:35:36，16 文件）** 接受登记 ⇒ **裁定 68 要求的账本已交付、C2 欠账清一项**。根因 = 写 `WHY_BEFORE_IMAGE.md` 用了**未加引号 heredoc `<<EOF`**，正文反引号被 bash 当命令替换 ⇒ **意外把驱动本体跑了一遍（PID 593988）** ⇒ 新红线纪律 **`heredoc_quoting_discipline`**（**这不是排版问题，是任意代码执行**；实际后果 = 在监管者不知情下重跑 16 个自检脚本；新增文书生成脚本必须自带「正文含反引号 ⇒ 不得执行任何命令」自检）。**整改判定闭合**：驱动现为守卫版 `3ba62c9567e9`（enumerate→snapshot→restore，枚举为空即 exit 3 拒绝开工），守卫 `c2_driver_output_guard.py` `e6e3b2c2ad30` **自检 4/4**（含 `M1_enumerate_only_first`）；**D 22:45:24 实时核验：C2 正在重跑（PID 10421），`runs/infra/c_*` mtime 刷新但字节数与 event2 表逐一一致 ⇒ 守卫生效、无第三次事件**。`regression_driver_output_enumeration` **升格红线级** + 补「守卫必须自检且自检必须含『只枚举一部分 ⇒ 必须红』的变异体」。**C2 仍欠 `docs/c2_handoff_to_d_20260929.md` ⇒ 现为四条线里唯一欠交者。**
- **80** B2 双向专家 **80/80**（**D 逐行复核 80 行、不采信 `summary`**）。**① D-H1 = 证实**：`assets/vx300s_right.xml:3` 的 `euler="0 0 3.1416"` ⇒ 右臂基座绕 z 装反 180°、weld `eq_data[6:10]` 左右约定不统一；`eq_data[3:6]` 的 `anchor2=±0.134706 m` 镜像 + 上游 `initialize_robots` 把 mocap 设成等于复位后 `gripper_link` 位姿 ⇒ **复位瞬间即违反 0.1347 m** ⇒ 第一步臂被猛拉 13.5 cm（≈4 m/s）；反解一致 mocap 后左臂残差 ≤1.3 mm、右臂 0.247 m / 2.376 rad。**② B2 的路线优于裁定 66 ⇒ D 更正自己的原判、裁定 66 的「EE oracle」步骤作废**（B2 完全不用 EE 模型/weld，在**部署 env 自己的 `MjData`** 上用**雅可比阻尼最小二乘 IK 做 plan-then-replay**，更好地满足裁定 66 的意图且少一层机器；其余各条继续有效）。**③ 新纪律 `actuator_dynamics_before_control_law`**（B2 第一版每步闭环 IK 失败：position actuator kp 800/1600 的滞后吃掉 `q+dq`；改 plan-then-replay 后滞后只影响跟踪误差不影响路径长度）。**④ 这是自验不是正式采集**（5 项缺口见 14.3）。**⑤ 唯一真阻塞已转移**（见 14.2）。
- **81** **命令 B2 在开始 S1 pilot 之前先代提交 git**（裁定 49.6：单写者 = B2，**D 从不提交**）。HEAD 仍 `c422659`，**脏项 ~23 → 39**（D 22:44 实测）。提交信息须点名裁定 75–81。⚠ **`runs/` 被 `.gitignore:12` 排除 ⇒ 全部实测证据只在 NFS、不在 git；服务器重启后 NFS 是唯一证据载体 ⇒ NFS 路径不得改动。**

## 14.5 本轮新立/升格的纪律（**7 条，重启后必须继续执行**）

| 纪律 | 级别 | 一句话 |
|---|---|---|
| `heredoc_quoting_discipline` | **红线（新失败模式）** | 写含反引号/`$( )`/`$VAR` 的正文时 heredoc **必须** `<<'EOF'`；未加引号 = **把文档当脚本执行** |
| `per_batch_gpu_yield_gate` | 红线 | **每个** GPU 批次开跑前重查 `--query-compute-apps`；不许只在任务级查一次 |
| `cotenant_evidence_must_be_runtime` | 红线 | `collected_at_run_time` 必须为 `true`；不得事后从别人文书重建 |
| `mutant_construction_isolation` | 红线 | 变异体在独立目录构造 + 构造器自证「被 import 的就是变异副本」（读活对象） |
| `citation_sha_as_of_discipline` | 红线 | 引用**自己写入面内、仍在编辑**的文件时 sha 必须**落笔时刻重读** + 带 `as_of` mtime |
| `regression_driver_output_enumeration` | **升格红线** | 枚举全部固定路径输出；**守卫必须自检且含「只枚举一部分 ⇒ 必须红」变异体** |
| `actuator_dynamics_before_control_law` | 一般 | 设计控制器前先读执行器增益与滞后；不得假设「下发即到达」 |

**另采纳 2 条判据设计规则**：`minimal_common_check_schema`（78.2）、`always_true_gate_downgrade_rule`（78.4）。**指定 `false_red_archival_format` 的唯一模板实例 = A2 的 `manifest_run3_v10_pep610_false_red/WHY_ARCHIVED.md`**；第二正面样本 = E 的 `environment_invalid` 闸。

## 14.6 【取代 §13.6】D 文书完整性清单（`sha256-12`，23:0x）

| 文件 | 行数 | `sha256-12` |
|---|---|---|
| `rl_harness_supervision/d_context_checkpoint_20260929_2130.md`（**重启入口，本文件**） | **373** | `69aa5d5e5570`（**含 §14**；本次自引用行更新后会再变，以 `sha256sum` 实测为准） |
| `work/decisions/decisions_20260929.md` | **1419** | `5ab60141fa06` |
| `daily_report.md` | **4787** | `a39b4a658354` |
| `work/project_parameters.json` | **1147**（rev11、**86** 条测量） | `68cb84295f1d` |
| `rl_harness_supervision/d_handoff_to_a2_20260929.md` | **748**（+§17） | `f06841e440a5` |
| `rl_harness_supervision/d_handoff_to_b2_20260929.md` | **600**（+§15） | `4110234659c0` |
| `rl_harness_supervision/d_handoff_to_c2_20260929.md` | **463**（+§12） | `79d5c692312c` |
| `rl_harness_supervision/d_handoff_to_e_20260929.md` | **340**（+§11） | `9686078e10ce` |
| `rl_harness_supervision/supervisor_memo_20260929.md` | **2431**（增补二十三；**本轮增补二十四尚未写入 ⇒ 重启后第一件事补它，或直接以本 §14 为准**） | `d77ceb206b05` |
| `rl_harness_supervision/d_simchain_e2emin_20260929.md` | 380 | `87de84c1bd16` |
| 本轮 before 影像（9 份） | —— | `runs/vla/d_ruling_round_20260929_2255/*.before` |

**被引用的关键下游产物身份（重启后核对用）**：
- `harness/env_gym_aloha.py` = 579 ln / **`6c4d71eb732e`** / mtime 22:09:11（**C2 审计里写的 `387f78e2c49f` 已过期**）
- `scripts/c2_gate_env_gym_aloha.py` = 549 ln / `c9100b3811cd`
- `scripts/c2_run_c_regression_postpatch.sh` = 107 ln / **`3ba62c9567e9`（守卫版）**；旧的未守卫版是 `60aff102c836`
- `scripts/c2_driver_output_guard.py` = 417 ln / `e6e3b2c2ad30`
- `scripts/b2_s1_scripted_expert.py` = **不稳定**（22:2x 1127 ln/`25ffe837896a` → 22:53:16 1162 ln/`952437930706`）⇒ 引用必带 `as_of`
- `scripts/a2_egl_latency_remeasure.py` = `b544f3741665`；`scripts/e_mainline_render_calib.py` = `72a3f98e0c8f`；`envs/gym_aloha_shim.py` = `dc14466fcdcf`
- `docs/c2_gate_polarity_audit_20260929.md` = 260 ln（22:07:14）；`docs/e_handoff_to_d_20260929.md` = 269 ln（22:44）；`docs/e_egl_feasibility_20260929.md` = 338 ln（22:39:35）；`docs/infra-gpu-render.md` = 327 ln（22:06）；`docs/a2_s4_vla_runtime_interface_20260929.md` = 451 ln（22:26）
- **`docs/c2_handoff_to_d_20260929.md` = 仍缺（C2 是唯一欠交者）**

## 14.7 【取代 §13.7】重启后 D 的接续步骤

```bash
cd /workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot
date "+%F %T"; cat /proc/loadavg; grep -E 'nr_throttled|throttled_time' /sys/fs/cgroup/cpu/cpu.stat 2>/dev/null || grep -E 'nr_throttled' /sys/fs/cgroup/cpu.stat
git log --oneline -1; git status --porcelain | wc -l     # HEAD 应为 c422659 或 B2 依裁定 81.2 的新提交；脏项 23:0x 时为 39
sha256sum work/decisions/decisions_20260929.md daily_report.md work/project_parameters.json rl_harness_supervision/d_handoff_to_{a2,b2,c2,e}_20260929.md | cut -c1-12,65-   # 与 §14.6 对账
python3 -c "import json;d=json.load(open('work/project_parameters.json'));print('rev',d['revision_history'][-1]['rev'],'meas',len(d['measurements_and_decisions']))"   # 应为 rev 11 / 86
nvidia-smi --query-gpu=memory.used --format=csv; nvidia-smi --query-compute-apps=pid,used_memory --format=csv   # 23:0x 时为 0 MiB / 无进程
ps -eo pid,etime,args | grep -E 'a2_|b2_|c2_|e_|c_selfcheck' | grep -v grep     # 有无活作业；GPU 优先权 A2 > C2 > E > B2
tail -120 daily_report.md                                 # D 段在 4671–4787 行；看各线有没有新追加
ls -1t docs/*handoff_to_d* ; ls -1t docs/c2_* | head -5    # C2 的回流单到了没有（唯一欠交项）
find . -path ./.git -prune -o -path ./RL_Harness_v4_20260924 -prune -o -type f -newermt '-90 minutes' -print 2>/dev/null | grep -v __pycache__ | head -60
```

**然后按优先级（重启后照此顺序）**：
1. **B2 是否已代提交 git**（裁定 81.2）。若未提交且脏项 >39 ⇒ 催。
2. **B2 的 S1 正式采集**：核 14.3 的 **5 项缺口**是否补齐（尤其 ① 渲染器身份 与 ② 负载对）。这是**全链唯一真阻塞**。
3. **C2 的回流单** `docs/c2_handoff_to_d_20260929.md`（唯一欠交）+ **审计勘误行**（裁定 78.11）。
4. **A2 的 quiet-window 权威重测**（裁定 76.4）：必须 `collected_at_run_time=true`；**以及 S4a 骨架**（含 75.5 的异步最小证据字段 + 75.4 的 `overload_flag`）。
5. **A2 的两份 `WHY_ARCHIVED.md`**（裁定 78.6）+ **E 的两处「2.1× 余量」更正**（裁定 75.6）+ **E 的 §1 一行指针**（裁定 77.8 已授权）。
6. **B2 的 5 件闸务**（裁定 78.3/78.4/78.5/78.8 + 78.2 的四元组）：`V-pi05-1` 改判清 RED、委托闸补 `id` 去前导空格、`G2` WARN 极性、`delegated_g1_g5_freeze` 二选一、最小公共 schema。
7. **静默窗口申请的批/驳**（裁定 73 + 76.2 的批级闸）。
8. **新产物五类通病巡检**：恒真闸 / 跨口径搬用 / 否定型主张未枚举 / 闸缺 `applies_when` / 自检未执行取数路径。**本轮新增两类**：**假绿（变异体没咬）**、**引用 sha 已过期**。
9. **治理**：追加 `daily_report.md` 的 D 小节 + **更新本断点文件（每次重大裁定后都要更新 §14.2/§14.4/§14.6）** + 若写了新裁定则同步 `supervisor_memo`（**注意：本轮的增补二十四尚未写入 memo，裁定全文已在 `decisions_20260929.md` 与本 §14 ⇒ 重启后可以直接以这两处为准，不必补 memo，除非要继续编号**）。

## 14.8 需要用户裁的分叉（**D 不自决，已按「建议值 + 可推翻条件」暂行**）

1. **`parallel_eval_workers_cap` 若工程上必须是单一常数**：取 4 还是 8？（D 已按场景分开定：S5/共卡 = 4，S1 独占+已申报 = 8。**若必须单值 ⇒ 需用户裁。可推翻条件：若 S1 与 S5 实际上永远不同时跑，则单值 8 更优；若经常与 A2 推理并发，则单值 4 更安全。**）
2. **是否向平台申请 `NVIDIA_DRIVER_CAPABILITIES` 加 `graphics`**：D 已降级为**非阻塞改善项**（prefix-only 已足够主线），但**申请动作本身要用户点头**。**可推翻条件：若后续新增线（如 ManiSkill 像素档 / Vulkan / robosuite）需要在不 source 激活件的情况下直接 GPU 渲染，则申请变为必要。**
3. **bf16 是否投入测试**：改数值口径 ⇒ **影响所有已留档数字的可比性**（必须另开 `representation_version`、不得与 fp32 同表）。**可推翻条件：若 P4 真机实测延迟达标，则 bf16 不必投入；若 n=25 异步版在真机上裕量 <20%，则必须投入。**
4. **E 的稳态并发数字是否要**：E 建议「若 D 要稳态训练并发数，请 D 与 A2 排一个 5 分钟窗口」。**D 目前不排** —— 主线阻塞不在这里（在 B2 的 S1 正式采集）。**可推翻条件：若 S6 的在线 RL 真的要与训练并发跑评测，则这个窗口变为必要。**

## 14.9 用户偏好（不变，重启后照旧）

中文；证据优先、带 `file:line` 与**文件身份三元组 `(path, sha256-12, line)`**（裁定 64）**+ 本轮新增的 `as_of` mtime**（裁定 78.11）；**分叉留给用户裁**，D 自确技术口径时**必须写可推翻条件**；共享文书 **append-only**；每轮更新以「D 等各线什么 + 需用户什么」收尾；**D 的自我更正必须显式写出并升为常设规则**（本轮：更正裁定 66 的 EE oracle 步骤、更正 `/dev/dri`、固化 prefix 路径）；**任何 D 自创的闸在没有与 v4 原文对撞前不得获得事实上的地位**；**服务器可能关闭 ⇒ 每次重大裁定后更新本断点文件**；**保护「下位可以纠正 D」的通道**（本轮实例：**B2 的路线优于裁定 66 ⇒ D 更正自己的原判**；**C2 的 D1 读码证实并补强了裁定 69**；**E 的 4-6 指出 D 的文书路径错误 ⇒ D 改文书不改目录**；接受前一律先独立复核含文件身份，不因是 D 自己写的就驳回）。

---

# §15 【2026-09-29 23:4x 更新 —— **本节取代 §14.2/§14.3/§14.6/§14.7；重启后先读本节，再回查 §14 与 §13.1/§13.3**】

**本节写于裁定 82 落盘之后。** §14 的全部内容仍有效，本节只更新「链路状态、待办、文书哈希、重启步骤」四项。

## 15.1 裁定 82 一句话（全文 `work/decisions/decisions_20260929.md`，1419→**1504** ln，sha256-12 `303250dff9d2`）

**触发**：23:2x 巡检发现四线同时落新产物（C2 的 T-C2-1、B2 的 S1 正式采集器 2333 ln、E 的 `RAW_PROBE_INTERFERENCE.json`、A2 的 S4 文书更新）。**本轮以「防止关键路径返工」为最高优先。**

- **82.1 C2 的 T-C2-1 交付认定**（本仓「闸有牙」的最佳实例之一）：`harness/norm_contract.py`（437 ln, `df215ddee8b5`）+ `scripts/c2_build_norm_stats.py`（397 ln）+ `matrix.json` + `mainline_status.json` + 12 个 stats 分支。**裁定 69 合规满分**（两案并行、`coef_status="proposed_pending_s1"` 不冒充已定）；**`mainline_status.json` 的 `refused_to_substitute=["env_derived_diagnostic","yam_abc130k"]` 是最重要证据** ⇒ C2 明确拒绝用替代数据顶替主线 stats（**D 曾怀疑违反 `abc130k_stats_forbidden`，核对后怀疑不成立，已诚实记录**）；**`verdict="RED"` + `must_red_branches_all_red=true` 是【正确】结果**（诊断分支必须红），三条红理由实质性：起态越界维 `[8,9]`（原始 `[2,9]`、`max|state|=1.16`）、**最差维 `clip_ratio=0.526667`**、非法 bin 维 `[7,8,9,10]` ⇒ **这是裁定 44.1「无 stats ⇒ 状态通道饱和」的量化版，也解释了 A2 的 zero-shot 为何 0/20**；`eval_frames_are_held_out=true`（600 build/600 eval）；`load_pair` 齐。**C2 对起态来源的口径边界论证 D 采纳**（起态位姿是几何量、不随控制频率变化 ⇒ 不构成裁定 71 的跨口径移植；但必须带注记引用）。
- **82.2【关键路径·已紧急下达 B2】C2 的 `interface_ask_to_b2` 被采纳为 S1→T-C2-1 的【绑定契约】**：先导 5 集落地时同时导出 `states_14d.npz`（`frames=[N,14] float64` 按集拼接、`start_poses=[E,14]`、`physical_range=[14]`，**臂关节读 `jnt_range`、夹爪维=1.0**）+ `manifest.json`（五元 + `control_hz=29.4118` + `episode_horizon_s=10.2`）；C2 的生成器 `--s1-frames` 直接吃、不需改代码。**D 实测 `grep -n "states_14d\|np.savez" scripts/b2_s1_generate_dataset.py` ⇒ 0 命中（脚本 sha `b7e93e65d5f5`、2333 ln、mtime 23:29:14）⇒ B2 当前不导出它。** **若 B2 先跑完正式采集再补 ⇒ 关键路径一次完整返工**（T-C2-1 的 stats 是 A2 的 S4b 前置）。C2 的对等义务：拿到 npz 后不得改口径重算；不符则报 D、不自行修补 B2 产物。
- **82.3 B2 的「一处偏离裁定 66 字面路线」= 裁定 80.2 已批准；B2 的声明程序是标准形态。** `scripts/b2_s1_generate_dataset.py:33-41` 明写「**EE 模型一个字节都不加载**…**这是对裁定 66 字面路线的一处偏离，理由与实测证据在 `demo_manifest.json → route_compliance` 里逐条留痕，并报 D**」⇒ **「下位纠正 D」通道的标准形态**（自行声明偏离 + 留痕 + 报 D，而不是静默改路线）。B2 新提供的第三处硬伤（`sim_end_effector.py:120` 无条件渲染 ⇒ `MUJOCO_GL=disable` 下 EE 不可用）D 采纳。**裁定 66 §13.7 采集四条 B2 全部实现**，其中 **`box_settle_steps=12` 且沉降 12 步不进数据集**（否则前 12 帧教「方块凭空下落」）⇒ **比裁定 66 原文更严，D 特别肯定**；夹爪标定表（开 `cmd=1.0`/spread `0.08412`、闭 `0.0`/`0.01833`、阈值 `≈0.45`/spread `0.04`=方块宽）全进 manifest；**存 14 维不存 16 维 `qpos`** 且把 `tasks/sim.py:47-48` 的 `(+v,−v)` 展开**写死进 `representation_version`（`grip14_to_qpos_pair=+v,-v`）**；指尖偏置用实测 `[0.0935,0.0,0.0021]`（probe4 E1）。**12 道闸全三值 + `red_when` + 变异牙；3 变异体**（`dt-back-to-50hz`/`reverse-judge-flipped`/`random-actions`）。**B2 已自行闭合裁定 80.3 的 ①②③**（`:69` 走激活件且注明裁定 70；`:211` `loadavg3()`；`:303` 注明裁定 72-1 + `:305-330` 完整身份探针）⇒ **判为「已在实现中闭合，待产物落地后由 D 复核」**；`verify_lerobot`（`:879-924`）读回自己写的数据集逐字段核 = 裁定 72 `selftest_must_execute_acquisition_path` 的形态，`:924` 把「lerobot 自己算的 min/max/mean/std」口径归属写清、不与 C2 的 stats 混淆 ⇒ 正确。
- **82.4 图像存储 甲/乙/丙 ⇒ 裁【甲】（PNG 内嵌 parquet）；【丙】明确禁止。** 甲的理由：无损（不引入压缩伪影混淆 stats 与 SFT）+ `fps` 字段诚实（29.4118 Hz 非整数，裁定 53）+ 时间戳精确（S6 的 TD 时序前提）+ 不碰第三方运行时。**丙禁止**：monkeypatch lerobot 编码器 = 改第三方运行时，与裁定 78.7、57.4 及 **B2 自己 `:62` 的硬边界「只读 lerobot site-packages、一个字节都不改」直接冲突**；将来若确需，必须 D 解冻 + 配齐 57.4 全部牙 + 另开 `representation_version`。**乙**（若为 mp4 + 取整 fps）**驳回** = 口径谎言；**若 B2 的乙案不是这个形态，B2 补原文 D 再裁**。**体积口径按裁定 78.9 分开登记**：甲属 **PNG 压缩**族（与 C 线 `147 KB/帧` 同族），**与 C2 的 `np.savez` 未压缩 `1765.19/2701.04 KB/帧` 不同族** ⇒ B2 必须实测登记真实 KB/帧与总字节，**不得引用上述任何数字代替**。根因：lerobot 0.4.4 的视频路径把 fps 直接喂 PyAV（`datasets/video_utils.py:460`）。
- **82.5【主线判据变更】E 的 `RAW_PROBE_INTERFERENCE.json`（23:23:48，generator `scripts/e_rawprobe_interference.py` sha `ae3e735a8719`）**：
  - **规则采纳并升红线纪律 `bare_renderer_same_process_ban`**：**禁止在被测 env 同进程、且 dm_control 已渲过图之后**建/关裸 `mujoco.Renderer`；需要 GL 身份就另起独立子进程或放在 `make_env` 之前。
  - **A2 免责（E 的跨线排查，D 采纳）**：A2 `a2_egl_latency_remeasure.py:702` 的 `gl_identity_via_mujoco()` 在 `make_env`（`:375`/`:430`，经 `:761`/`:771`）**之前** ⇒ `raw_first`、安全；`:195` 的 `gl_identity_after_dm_render` 只调 `glGetString`、不建 Renderer ⇒ 亦安全。**⇒ A2 的延迟产物不受污染，裁定 75/76 的数字无需重判。**
  - **⚠ D 逐 run 复核 12 个 run（2 后端 × 3 臂 × 2 seed）发现 E 的 `verdict` 未上报的现象 B**：**egl 下 wrist 相机在【没有任何裸探针的干净基线 `no_raw`】里就不逐位可复现** —— seed1000 右腕 `7e567756f8d8`→`51fa7914477d`、seed1001 双腕都变，而 **mean/std 一致到 3–4 位小数**；`angle`（基座相机）**始终逐位一致**；**osmesa 下三相机全部逐位一致（6/6 run）**。⇒ 这是 **egl/GPU 光栅化在 wrist 相机上的非确定性，与裸探针无关**。**现象 A（E 抓到的）**= `raw_after` 灾难性污染（`frozen=true`、`inflation_pct=37.1`、三相机 mean 崩塌并收敛到同值 53.248/53.252/53.248）。**现象 B 比 A 更重要，因为它改变了主线验收判据。**
  - **裁定：`replay 可复现` 判据重定范围**（影响裁定 66 出口第 4 条与裁定 80.3-⑤）：**① 状态量（`qpos`/`states`/动作序列）必须逐位一致 = 硬判据**（**B2 的 `cmp_states`/`norender_vs_expert`/`recorded_vs_norender`/`verdicts_all_equal`（`:629-640`）已经就是这个形态 ⇒ D 采纳并钉为强制项**）；**② 像素逐位一致【不得】作为 egl 下的验收判据**（实测不成立，当判据会造成永久假红）；**③ 像素改为**：`angle` **必须逐位一致**（实测成立）+ 两个 wrist 的 `mean/std` 在**登记容差**内、且**差异像素占比与最大绝对差被实测登记**（不是「必须为 0」）。
  - **指派 E 量化现象 B（S1 正式采集的验收前置）**：同 seed、同 reset、egl 下重复 **N≥5**，登记 wrist 的**差异像素占比**、**最大绝对差**、`mean/std` 重复性；**对照 osmesa（预期全 0）**；产物落 `runs/infra/e_*`；按裁定 76.2 批级闸 + 73 申报（**与 A2 的 quiet-window 重测错峰，A2 优先**）。**「差异像素占比」必须是产物顶层字段**（它是用户分叉 ⑤ 的决策依据）。**在它落地前，B2 的 replay 闸按「状态逐位 + `angle` 逐位 + wrist 只登记不判红」运行**，并把 wrist 差异像素占比如实登记进 `demo_manifest.json`（不得省略、不得写成 0）。
  - **E 的产物两处必须更正（append-only）**：① **内部矛盾** —— `gate_analysis.fidelity_catches_it=false`（布尔字段）与结论文字「**抓住它的是 fidelity 闸**」互相矛盾；实测 `no_raw` 臂也 `fidelity_ok_all=false` ⇒ **fidelity 闸在 egl 下无法区分「污染」与「干净」**，E 提的「liveness + fidelity 两道闸 ⇒ `render_health_ok`」**在 egl 下不充分**；真正能区分现象 A 的信号是 **`frozen` / `cam_convergence` / 三相机 mean 收敛到同值**。② **`verdict` 未上报现象 B** ⇒ 按裁定 50.1，**记录在产物里不等于上报**。
  - **`baseline_no_raw_ctrl_steps_per_s = 179.53`（egl_nvidia，中位数 of [171.29, 187.77]）= 本轮出现的【第 4 个】主线渲染数字**（前三个：E 权威轮 `172.32`、A2 run1 `30.522`、A2 run2 `65.865`）⇒ **按裁定 71 不予采纳、不并列**，标 `protocol_mismatched_not_mainline`。**E 的权威轮仍是 `summary_20260929_221443.json` 的 `172.32`。**
  - **E 本轮程序合规性 = 「实质合规、程序有缺口」，D 予以追认**：`gpu_before={utilization 0, memory_used 0, compute_procs []}` ⇒ **开跑前确实查了卡**（符合裁定 76.2 精神）；`boundary_guard_before/after` 齐、`load_before/after` 齐、prefix 与 7 个库逐一核验、`generator_sha256_12` 齐 ⇒ **GPU 无冲突、无实质损害**。开跑时 D 的 §11-5「E 线不主动开新标定轮」已落盘（23:0x）而 E 23:2x 起跑 ⇒ **D 认定 E 很可能尚未读到，不按违规处理**。
  - **D 撤回 §11-5 那句「不主动开新标定轮」（这是 D 的错误判断）**，改为：**E 可以主动开轮，但必须 ① 开跑前在 `daily_report.md` 申报（窗口 + 预计时长 + 是否占 GPU）；② 每批前查卡（批级闸）；③ 产物标清是「标定轮」还是「取证轮」。**
- **82.6 C2 的 `matrix.json` generator sha 已过期 = `citation_sha_as_of_discipline` 的【第二起实例】**（裁定 78.11 落盘后 20 分钟内）：`matrix.json`（23:25:00）记 `generator.sha256_12="99159100eb59"`，而 D 实测 `scripts/c2_build_norm_stats.py` = **397 ln / `faf7cfc6ccd4` / mtime 23:25:16** ⇒ **脚本在 matrix 写完后 16 秒被改**。（同文件 `contract_module.sha256_12="df215ddee8b5"` **与 D 实测一致** ⇒ **只有 generator 一处过期**。）C2 须追加勘误（另落 `erratum.json` 或在回流单点名，**不改原 JSON 本体**）。**D 不判为违规事故**（纪律 23:0x 落盘、产物 23:25:00 落盘，且损害为零），**但两起同型都在 C2 线上 ⇒ D 已要求 C2 把「落笔时刻重读 sha」做成文书生成脚本里的一个函数，不要靠自觉。**
- **82.7 本轮 D 的自我更正（第 3 处）**：**D 撤回「E 线不主动开新标定轮」。** 理由：D 当时依据「主线阻塞已转移到 B2、E 的交付已足够支撑选型」，这在**标定**层面成立，但 **D 没考虑到 E 还能在「取证」层面挖出改变主线判据的问题（现象 B）**。**教训（升为 D 的自查项）：给某条线划「停止主动开工」的边界时，必须区分「该类产出已足够」与「该类产出已穷尽」—— 前者可以停，后者不可以。本轮 D 把「标定数字已够」误当成「E 线无事可做」。**

## 15.2 【取代 §14.2】当前链路状态（23:4x）

| 阶段 | 状态 | 证据 / 阻塞 |
|---|---|---|
| π₀.₅ base 加载 / 接口贯通 | **仿真通过**（不含能力主张） | zero-shot **0/20** 已按裁定 44.1/46 同句标注「无 normalizer stats ⇒ 不构成能力结论」；随机基线 0/20 但 `max_stage_hist` 有 `right_lift:5` ⇒ **判据非恒真成立** |
| GPU 渲染解锁 | **仿真通过** | E 权威轮 `summary_20260929_221443.json`：`egl_nvidia w=1 env_step_native=172.32`（5.80 ms = 预算 17%）vs `osmesa 10.45`（95.73 ms = **超预算 2.8×**）⇒ **16.5×** |
| env 判定层 | **仿真通过**（D 亲自复跑） | C2 `harness/env_gym_aloha.py`（579 ln, `6c4d71eb732e`）+ 闸（`c9100b3811cd`）；**D 22:52:32 复跑 offline = PASS/15/red=[]**；online 13 条 `n_red=0`；E11 实测 monkeypatch 半改 ⇒ `measured_hz=50.0` 且模块拒绝构造 |
| **normalizer 契约层（T-C2-1）** | **交付认定；主线 stats 等 B2 的 pilot 5** | `runs/vla/c2_norm_contract_20260929/`（23:25:00）：契约层 + 生成器 + 12 分支矩阵 + 闸（`verdict=RED`、`must_red_branches_all_red=true` = **正确**）；`status="waiting_for_s1_pilot_5"`、**`refused_to_substitute`** |
| **S1 双向示范** | **自验通过（80/80）；正式采集器已写成、正式采集未实施** ← **当前唯一真阻塞** | 自验 `expert_selfverify_40x2.json`（22:23:02，forward 40 + reverse 40 全 success）；采集器 `scripts/b2_s1_generate_dataset.py`（**2333 ln**，`b7e93e65d5f5`，23:29:14，**仍在编辑**）。**跑之前必须先做 15.3 的三件事** |
| **像素复现容差** | **未实测** ← **S1 验收前置（新增阻塞）** | egl 下 wrist 相机在干净基线里就不逐位可复现（现象 B）⇒ **已指派 E 量化（N≥5、对照 osmesa）**；在它落地前 B2 的 wrist 只登记不判红 |
| S4a 运行时骨架 | **进行中**（A2 的文书 23:24:16 更新） | 裁定 65-6；须含 75.5 异步最小证据字段 + 75.4 `overload_flag` |
| S4b / S5 / S6 | **未实施** | S4b 等 C2 的 stats；stats 等 B2 的 pilot 5 |

**⇒ 关键路径（23:4x）**：**B2 加 `states_14d.npz` 导出 + 按甲落地图像 + replay 闸按新范围 → pilot 5 → C2 出主线 stats → A2 的 S4b 接真帧**。**旁路（不阻塞但必须并行）**：**E 量化 wrist 容差**（S1 验收前置）、**A2 的 quiet-window 权威重测**（裁定 76.4）。**两人都会占 GPU ⇒ 错峰，A2 优先（裁定 73）。**

## 15.3 【取代 §14.3】B2 跑正式采集之前的**三件事**（裁定 82.2/82.4/82.5-3）

1. **加 `states_14d.npz` + `manifest.json` 导出**（绑定契约，字段名逐字照 C2 口径；拼接顺序 = 集序号升序；`physical_range` 臂维读 `jnt_range`、夹爪维 1.0；导出不得改变 LeRobot 数据集本体；在 `demo_manifest.json` 记 npz 的 sha256-12 + `as_of` mtime）。**D 已实测确认当前 0 命中 ⇒ 必须现在加，否则整轮返工。**
2. **图像存储按【甲】（PNG 内嵌 parquet）落地**；**丙禁止**；**实测登记 PNG 内嵌后的真实 KB/帧与总字节**（不得引用 C 线的 147 或 C2 的 1765.19/2701.04）。
3. **replay 闸按「状态逐位 + `angle` 逐位 + wrist 只登记不判红」运行**，wrist 差异像素占比如实登记进 `demo_manifest.json`（不得省略、不得写成 0）。

**裁定 80.3 的 ①②③ 已判为「在实现中闭合、待产物落地后 D 复核」**；④（pilot 5 + formal 20/方向）⑤（replay，判据已按 82.5 重定范围）仍待验证。

## 15.4 【取代 §14.6】D 文书完整性清单（`sha256-12`，23:4x）

| 文件 | 行数 | `sha256-12` |
|---|---|---|
| `work/decisions/decisions_20260929.md` | **1504** | `303250dff9d2` |
| `daily_report.md` | **4874** | `fca0bdaf6be0`（D 段：4671–4787 = 裁定 75–81；**4788–4874 = 裁定 82**） |
| `work/project_parameters.json` | **1147**（rev11、**86** 条测量） | `68cb84295f1d`（**裁定 82 尚未进参数表 ⇒ 重启后若继续，需出 rev12 把 82.4/82.5 的判据变更写进 `rendering` 与 `task`**） |
| `rl_harness_supervision/d_handoff_to_a2_20260929.md` | **748**（+§17） | `f06841e440a5` |
| `rl_harness_supervision/d_handoff_to_b2_20260929.md` | **614**（+§15、**§16**） | `7aed7d812823` |
| `rl_harness_supervision/d_handoff_to_c2_20260929.md` | **482**（+§12、**§13**） | `436822633fe7` |
| `rl_harness_supervision/d_handoff_to_e_20260929.md` | **374**（+§11、**§12**） | `c8f4697a5f49` |
| `rl_harness_supervision/supervisor_memo_20260929.md` | **2460**（增补二十四 = 裁定 75–81 的编号锚点；**裁定 82 未进 memo，全文在 decisions + 本节**） | `84f38fde4813` |
| `rl_harness_supervision/d_context_checkpoint_20260929_2130.md`（**本文件**） | 追加 §15 后 | 以 `sha256sum` 实测为准 |
| `rl_harness_supervision/d_simchain_e2emin_20260929.md` | 380 | `87de84c1bd16` |
| before 影像 | —— | `runs/vla/d_ruling_round_20260929_2255/`（9 份 `*.before` + `*.before82` + `d_context_checkpoint.before_s15`） |

**下游产物身份（重启后核对用，**引用一律带 `as_of`**）**：
- `harness/env_gym_aloha.py` 579 ln / `6c4d71eb732e` / mtime 22:09:11（**C2 审计里的 `387f78e2c49f` 已过期**）
- `harness/norm_contract.py` 437 ln / `df215ddee8b5`；`scripts/c2_build_norm_stats.py` 397 ln / **`faf7cfc6ccd4`** / mtime 23:25:16（**`matrix.json` 里的 `99159100eb59` 已过期**）
- `scripts/b2_s1_generate_dataset.py` **2333 ln / `b7e93e65d5f5` / mtime 23:29:14 —— 仍在编辑，sha 不稳**
- `scripts/b2_s1_scripted_expert.py` **不稳**（22:2x 1127 ln/`25ffe837896a` → 22:53:16 1162 ln/`952437930706`）
- `scripts/e_rawprobe_interference.py` `ae3e735a8719`；`scripts/e_mainline_render_calib.py` `72a3f98e0c8f`；`scripts/a2_egl_latency_remeasure.py` `b544f3741665`；`envs/gym_aloha_shim.py` `dc14466fcdcf`
- `scripts/c2_run_c_regression_postpatch.sh` 107 ln / **`3ba62c9567e9`（守卫版）**；旧未守卫版 `60aff102c836`；`scripts/c2_driver_output_guard.py` 417 ln / `e6e3b2c2ad30`
- `scripts/c2_gate_env_gym_aloha.py` 549 ln / `c9100b3811cd`
- **仍缺：`docs/c2_handoff_to_d_20260929.md`（C2 是四条线里唯一欠交者）**

## 15.5 【取代 §14.7】重启后 D 的接续步骤

```bash
cd /workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot
date "+%F %T"; cat /proc/loadavg; grep -E 'nr_throttled' /sys/fs/cgroup/cpu.stat 2>/dev/null || grep -E 'nr_throttled' /sys/fs/cgroup/cpu/cpu.stat
git log --oneline -1; git status --porcelain | wc -l    # HEAD 应为 c422659 或 B2 依裁定 81.2 的新提交；脏项 23:35 实测 49
sha256sum work/decisions/decisions_20260929.md daily_report.md work/project_parameters.json rl_harness_supervision/d_handoff_to_{a2,b2,c2,e}_20260929.md | cut -c1-12,65-   # 与 §15.4 对账
python3 -c "import json;d=json.load(open('work/project_parameters.json'));print('rev',d['revision_history'][-1]['rev'],'meas',len(d['measurements_and_decisions']))"   # rev 11 / 86（裁定 82 未进表 ⇒ 需 rev12）
nvidia-smi --query-gpu=memory.used --format=csv; nvidia-smi --query-compute-apps=pid,used_memory --format=csv
ps -eo pid,etime,args | grep -E 'a2_|b2_|c2_|e_|c_selfcheck' | grep -v grep    # GPU 优先权 A2 > C2 > E > B2
tail -150 daily_report.md                     # D 段 4788–4874 = 裁定 82；看各线有无新追加
ls -1t docs/*handoff_to_d* ; ls -1t runs/vla/b2_sim_demo_bidir_20260930/ runs/vla/c2_norm_contract_20260929/ runs/infra/e_mainline_calib_20260929/ | head -30
find . -path ./.git -prune -o -path ./RL_Harness_v4_20260924 -prune -o -type f -newermt '-90 minutes' -print 2>/dev/null | grep -v __pycache__ | head -60
```

**然后按优先级**：
1. **B2 是否已加 `states_14d.npz` 导出**（15.3-1，**关键路径第一优先**）；是否已按甲落地图像；是否已 git 代提交（裁定 81.2）。
2. **B2 的 pilot 5 是否落盘** ⇒ 落了就通知 C2 出主线 stats（`--s1-frames`）。
3. **E 的 wrist 非确定性量化是否落盘**（15.2 的新增阻塞、S1 验收前置）⇒ 落了就裁容差值并解 15.6-⑤ 的用户分叉。
4. **C2 的回流单 `docs/c2_handoff_to_d_20260929.md`（唯一欠交）+ 两处勘误**（`matrix.json` 的 generator sha、审计的 `387f78e2c49f`）。
5. **A2**：S4a 骨架（75.5 异步字段 + 75.4 `overload_flag`）、quiet-window 权威重测（76.4，`collected_at_run_time=true`）、两份 `WHY_ARCHIVED.md`（78.6）。**与 E 错峰占卡。**
6. **E 的两处更正**（82.5：`gate_analysis` 内部矛盾 + 现象 B 未上报）与 **§1 一行指针**（77.8 已授权）。
7. **B2 的 5 件闸务**（78.3/78.4/78.5/78.8/78.2）。
8. **裁定 82 进参数表 rev12**（`rendering` 加 `bare_renderer_same_process_ban` + wrist 非确定性 + 第 4 个渲染数字不采纳；`task` 加 replay 判据重定范围 + 图像存储甲案）。
9. **新产物巡检的七类通病**：恒真闸 / 跨口径搬用 / 否定型主张未枚举 / 闸缺 `applies_when` / 自检未执行取数路径 / **假绿（变异体没咬）** / **引用 sha 已过期**；**本轮新增第八类：产物里记录了但 `verdict` 未上报（裁定 50.1「记录 ≠ 上报」）。**
10. **治理**：追加 `daily_report.md` 的 D 小节 + **更新本断点（每次重大裁定后更新 §15.2/§15.4）**。

## 15.6 需用户裁的分叉（**5 项，D 已按「建议值 + 可推翻条件」暂行**）

1. `parallel_eval_workers_cap` 若必须单值：4 还是 8（D 已分场景定：S5/共卡=4，S1 独占+已申报=8）。**可推翻条件**：若 S1 与 S5 永不同时跑 ⇒ 单值 8 更优；若经常与 A2 推理并发 ⇒ 单值 4 更安全。
2. 是否向平台申请 `NVIDIA_DRIVER_CAPABILITIES=graphics`（D 已降级为非阻塞改善项，**申请动作本身要用户点头**）。**可推翻条件**：若新增线需在不 source 激活件的情况下直接 GPU 渲染，则变必要。
3. bf16 是否投入测试（改数值口径 ⇒ 影响所有已留档数字的可比性，须另开 `representation_version`）。**可推翻条件**：若 P4 真机延迟达标 ⇒ 不必；若 n=25 异步版在真机裕量 <20% ⇒ 必须。
4. 是否为 E 排 5 分钟稳态并发窗口（**D 目前不排**，主线阻塞不在此）。**可推翻条件**：若 S6 的在线 RL 真要与训练并发跑评测 ⇒ 变必要。
5. **【本轮新增】若 egl 下 wrist 相机的差异像素占比实测偏大（例如 >1%），是否改用 osmesa 作「数据采集/复现」后端、egl 仅作「吞吐」后端**（osmesa 实测三相机全部逐位一致，但慢 16.5×）。**D 暂按「egl 采集 + 状态逐位判据 + wrist 容差登记」执行，等 E 的量化结果再定；这是口径分叉，最终由用户裁。**

---

# §16 【2026-09-30 00:1x 更新 —— **本节取代 §15.2/§15.4/§15.5/§15.6；重启后先读本节，再按需回查 §15 与 §14/§13.1/§13.3**】

**写入时刻**：2026-09-30 00:1x CST（跨日）。**触发**：裁定 83 落盘 + 一起 GPU 互污染实时事故 + C2 自查出红线级恒真牙。
**本节只登记状态与指针**；每条都给了正文路径。

## §16.1 本轮裁定 83 的一句话结论（权威全文 = `work/decisions/decisions_20260929.md` 裁定 83 段，1504→**1672** ln，sha256-12 **`9d42c1559058`**）

| # | 结论 |
|---|---|
| **83.0** | **【URGENT】GPU 互污染第 2 起**：A2 的 `quiet_window_rep1`（PID 154563，23:57:37 起）与 E 的 `proxy_a2` ballast（PID 156355，23:58:35 起，`--cotenant-seconds 240`）同卡；D 于 **23:59:00 亲自查卡** = `29721 MiB / 100 %`。**A2 无过错**（起跑时卡空、批级闸合法通过、**运行时采样器 76 样中 20 次记到 `pid 156355/14714 MiB` 并自判 `contaminated=true` 拒绝权威** ⇒ 裁定 76.3 机制首次实战有效，D 记功）。**E 的过错是精确一处**：测量批次过了闸（`skipped_batches` 2 条），但 **ballast（注入器）本身没过闸**——`cotenant_started.gpu_after_start` 证明 E 起完 ballast 才看到 A2 在卡上。**⇒ 新立红线 `cotenant_injector_must_be_gated`。** 两边数字均不采纳（A2 自判污染；E 的 `batches[*].verdict=None`，且属第 5/6 个渲染数）。**D 自记账第 8 次同型错误**：只写「错峰、A2 优先」而没给机器可判的互斥锁 ⇒ **新立 D 自查项 `gpu_window_mutual_exclusion`**。**D 未发出任何 kill**（两线进程于 00:00:39 前自行结束）。 |
| **83.1** | **C2 用变异体逼出 `Tr1` 恒真牙（红线级）= 本轮全线最高价值发现**：`near_constant_dims()` 读 `span_q99_q01`，而 build 侧在 `widen_to_cover()` 后把展宽 span 写回同名键 ⇒ hold 相 10 个下限绑定维一个都不被判近常量 ⇒ `unprotected=[]` 恒成立。**D 独立验证修复**：修前 `mutation_floor_off` 25 行全 PASS（牙不咬）→ 修后（23:55:01）前 8 PASS / 后 **17 RED**、`verdict=RED`（牙咬了）；`mutation_no_widen` 修后 25 行全 RED。**⇒ 新立红线 `tooth_must_be_mutant_proven`**（A2 的 19/19 已是正例）。C2 的 before-image 纪律（`WHY_BEFORE_IMAGE.md` + `cp -p` + 目录改名保链）= **全线范例**。 |
| **83.2** | **D 的第 9 次同型错误：撤回裁定 82① 里「红的理由都是实质性的」**——C2 实测 `Tc_start_pose_coverage` 的红至少部分源于 `np.clip` 界反转（`need>hi-lo` 时 `a_min>a_max`，numpy 取 `a_max`）⇒ 把实现瑕疵记成契约红。**根因：D 只查「must_red 是否全红」，没查「这颗牙在什么输入下会变绿」⇒ 恒红牙与恒真牙同样无信息量。⇒ 新立 `green_witness_required`（判据设计规则 + D 自查项）**。**口径限定**：基线 `matrix.json` 已由 RED(23:41:23) 翻为 **PASS(23:55:00)**，16 PASS/9 RED；**该 PASS 的数据源是 `env_derived_diagnostic` ⇒ 不得引用为「归一化契约已通过」或「可以开始 BC」**；修前数字（越界维 `[8,9]`、`clip_ratio=0.526667`、`dims=[7,8,9,10]`）**一律作废**，修后 must-red = `Td2_clip_heldout`（最差维 **7**、`clip_ratio=0.356667`、`n_eval=600`）+ `Te2_no_illegal_bin_heldout`。**D 的 near-miss**：曾据被 `head` 截断的 `ls` 拟问责 B2「空目录」，`find -type f|wc -l` 复核 ⇒ **实为 17 个文件已落地** ⇒ **新立 D 自查项 `absence_claim_requires_exhaustive_enumeration`**。 |
| **83.3** | **用户分叉 ⑤ 解除**：E 的 `RENDER_DETERMINISM.json`（23:40:22，generator `ffc867dd2e97`）实测 egl 下 `angle` 逐位✅、`left_wrist` ❌（`n_unique_shas_per_rep=[5,4]`、`frac_diff_px=0.000179`）、`right_wrist` ❌（`[6,6]`、**跨进程 sha 不同**、`frac_diff_px=0.000717`）；**osmesa 三相机全部逐位✅（进程内+跨进程）**。**最差 0.0717% ≪ 1% ⇒ 采集后端维持 egl，osmesa 不作采集后端**。抖动比跨后端 mean 差（0.05%–0.29%）小 2–3 个数量级 ⇒ 不影响图像语义。**「现象 B」由"D 重数他人产物"升格为"E 直接实测事实"**（两法互证）。**可推翻**：若 `reps≥5` 实测 `frac_diff_px>1%` 或 `max_abs_diff>8` 或 `angle` 也不逐位 ⇒ 自动失效，改双后端并回用户裁。 |
| **83.4** | **replay 容差由 D 自定，禁把 raw-probe 的 `FID_*` 搬过来**（裁定 71）：`replay_max_abs_diff<=2`、`replay_frac_diff_px<=0.005`、`replay_mean_abs_diff<=0.005`（约实测最差 2×/7×/7×）。**`applies_when` 以实测 `GL_RENDERER=nvidia_gpu` 为键**（见 83.7）+ wrist 两相机 + 同 seed/reset/状态重复渲染 + shim `dc14466fcdcf` + 主线 env + 224×224；**`angle` 与 osmesa/llvmpipe 臂不适用，仍走逐位；状态逐位 = 硬判据**。**必须有变异体**（扰动某维状态 `1e-3` 或跳过一个 sub-step）。**E 需扩到 `reps≥5`**（`cross_process_same_sha` 现仅 2 个独立进程作证，left=✅ 可能是运气）。 |
| **83.5** | **E 覆写 `RAW_PROBE_INTERFERENCE.json` 未留前像 = 第 3 起无守卫覆写，且首起「被引用字节串灭失」**：现 mtime 23:45:24 / `generated_at=23:44:25` / generator **509 ln `74e8afe88a4d`**（原 `ae3e735a8719`）；`find runs docs -name '*before*' -newermt '-3 hours'` ⇒ **命中全是 C2 的，E 名下 0 个**。裁定 82 §2-4 明写 append-only。**后果：D 在 `daily_report.md:4822` 与裁定 82⑤ 引用的 23:23:48 版已不可恢复 ⇒ `stale_unrecoverable`**；红线 `bare_renderer_same_process_ban` **结论不变**（当前版仍载 `raw_after_is_harmful=true` + `rule` 原文 + `harmful_observations` 仅 `egl_nvidia/raw_after`），**引用改指当前版**。**⇒ 追加子条款 `unbacked_citation`**：D 引用"作者可覆写"的产物必须同时要求留前像；无前像 ⇒ 标 `unbacked_citation` 且不得作红线纪律唯一依据。E 需补 `OVERWRITE_EVENT_20260929_2345.md`，**守卫直接复用 C2 的 `scripts/c2_driver_output_guard.py`（417 ln `e6e3b2c2ad30`）**。 |
| **83.6** | **E 的两处更正实质闭合**：新版 `clean_arm_inflation_observed` **五条干净臂全部 `fidelity_ok_all=true`**、污染仅 `egl_nvidia/raw_after`（31.0%）；`fidelity_false_positives_on_clean_arms=[]`、`liveness_false_positives_on_clean_arms=[]`、`both_gates_clean=true`；**`clean_arm_noise_max_pct=4.2` < `threshold_pct=15.0` < 污染 `31.0`** ⇒ 阈值有推导，D 采纳；`FID_*`（4/0.02/0.05）在 **raw-probe regime 内**采纳。**D 的根因推断（标 `d_inference_not_measured`，待 E 确认/证伪）**：旧版 fidelity 在干净臂假红，**极可能就是因为它用逐位/sha 比对，而 egl 下 wrist 本就不逐位 ⇒ 现象 B 是 fidelity 假红的根因**；若确认，则 82 §2-4 ① 的"内部矛盾"不是文案矛盾，而是**一个真缺陷被两个产物分别记录**，且 `bare_renderer_same_process_ban` 可能需补「逐位比对本身在 egl 下不可用」（跨线影响 B2 replay 闸与 A2 图像参照）。 |
| **83.7** | **A2 的 S4a 验收通过**：`s4a_verification.json`（`generated_at=23:51:03`，generator **1282 ln `6f4ed1228a4c`**，as_of 23:50:29 ⇒ **引用 sha 与磁盘逐字一致**）：`all_ok=true`、`17/17` 闸、**变异自检 19/19 有牙**、`harness/vla_runtime.py` **772 ln `a42a3dd17c47`**、`contracts_py_modified=false`（`96c99ead93d2`）、`ledger_py` 只 import（`2a33c3f5516e`）、**`frozen_surface_touched=[]`**、`capability_claim=false`、`gpu_used=false`、`nr_throttled_delta_total=23`。**裁 5 个设计点**：① `prime_mode=hold`；② **`timeout_isolation_scope=td_only`（D 改 A2 的保守默认；附 3 条硬约束 + 变异体要求；标 `d_selfconfirmed_pending_user_ratification`；可推翻：v4 原文明确禁止则回退 `both_isolated`）**；③ `late_policy=hold`（65-3 维持）；④ `async_overlap=false`（在 76.4 权威重测 + G17 跑过真推理前**不得声称重叠/实时闭环**）；⑤ `s4b_outcome_judging=deferred`，**S4b 前置正式挂到 C2 线，排在 T-C2-1 主线 stats 之后**。**采纳 A2 两处自查并升为全线规则**：`real_env` 的 `closed_form_rederivation_by_A2` **不得被下游升格为「人手算」**；**引用 sha 必须由引用方重算，不采信上游交接值**。**采纳 A2 的口径精化（跨线）**：**渲染相关的 caveat/判据/容差，`applies_when` 必须以实测 `GL_RENDERER` 为键（`nvidia_gpu` vs `llvmpipe`），不得以 `MUJOCO_GL` 为键** ⇒ **这修正了 83.4 的 `applies_when`**。**A2 需澄清**：`latency_quiet_window_rep1.json` 的 `policy_executed=false` 与其 §9 申报「`policy_executed=true`」不一致（该臂带真权重、GPU 14990 MiB、`affected_fields` 列了 `t_infer_s`）⇒ **字段定义必须写进产物**（裁定 50.1）。 |
| **83.8** | **B2**：**D 先更正自己的误判**（拟据被截断的 `ls` 问责「`team_form` episode 空目录」⇒ 实为 **17 个文件已落地**，D 不问责）。**甲验收通过**：`selftest/pi05_lerobot/meta/info.json` ⇒ `codebase_version=v3.0`、`robot_type=aloha_bimanual_14d(gym_aloha vx300s dual-arm)`、**`fps=29.41176470588235`（精确非取整）**、`total_episodes=2`、`total_frames=514`、三个 `observation.images.*` 均 `dtype=image`/`[224,224,3]`。**需 B2 回答**：`team_form` 侧用 mp4 ⇒ **实测容器 fps**；若取整（如 30）⇒ 与 `pi05_lerobot` 时间基不一致，须登记并说明哪侧是训练真值（乙被否的理由是「mp4+取整 fps」，不是 mp4 本身）。**关键路径唯一卡点仍是 `states_14d.npz`**：`scripts/b2_s1_generate_dataset.py` **2540 ln `756a46b25984`**（+207 行 vs 裁定 82 的 2333 ln `b7e93e65d5f5`），但 `states_14d`/`savez`/`start_poses`/`physical_range`/`jnt_range` **全 0 命中**、`PNG` 7 / `parquet` 3 ⇒ **在做 82④ 没做 82②；82② 优先级更高**（只有它卡在 C2 主线 stats 上；C2 三次坚持 `refused_to_substitute`，D 三次记功）。**D 授权降阶方案**：先由 `probe/expert_selfverify_40x2_postpatch.json`（80/80、hz 全 29.411765、`n_plan_nonconverged=0`）导出**先导版 npz**（schema 逐字一致 + `manifest.json` 五元标注 + `control_hz=29.4118` + `episode_horizon_s=10.2` + 标 `provenance="expert_selfverify_40x2_postpatch"`/`is_pilot5=false`/`formal_collection_pending=true`），**让 C2 立刻验证 `--s1-frames` 通路**；**硬限制：C2 用它跑出的 stats 必须标 `stats_provenance=pre_pilot5_path_check`，不进 BC、不作主线 stats**（裁定 52/69）。**git 代提交仍欠**：HEAD `c422659`（21:2x），脏项 **51**。 |
| **83.9** | **新立/升格 5 条**：`cotenant_injector_must_be_gated`（**红线·新失败模式**）、`tooth_must_be_mutant_proven`（**红线**）、`green_witness_required`（判据设计规则 + **D 自查项**）、`absence_claim_requires_exhaustive_enumeration`（**D 自查项**）、`gpu_window_mutual_exclusion`（**D 自查项**）。**子条款**：`citation_sha_as_of_discipline` += `unbacked_citation`。**全线规则 2 条**：引用 sha 由引用方重算；渲染相关 `applies_when` 以实测 `GL_RENDERER` 为键。**用户分叉 5 → 4**（fork ⑤ 已解除）；**新增 1 项事后追认**：`timeout_isolation_scope=td_only`。 |

## §16.2 关键路径与链状态（00:1x）

```
【A2 持 GPU 窗】立即重跑 quiet-window rep1+rep2（裁定 76.4 的权威值 = 唯一还没拿到的关键数字）
        ↓（A2 销账 nvidia-smi 回 0 MiB）
【E GPU HOLD 中】reps≥5 腕部扩展轮 + OVERWRITE_EVENT + 确认/证伪 D 的根因推断 + 给 ballast 装批级闸
        ↓（并行，不占 GPU）
【B2】states_14d.npz 导出（可用降阶方案）+ team_form mp4 fps 回报 + git 代提交（脏 51）+ replay 闸重定范围+变异体 + 78.3/78.4/78.5/78.8/78.2 五件闸务
        ↓（npz 落地）
【C2】T-C2-1 主线 stats（--s1-frames）→ 然后 env_gym_aloha.py 三条硬约束（裁定 62）
        ↓
【A2】S4b 接真帧（四类判定独立于 reward==4；timeout 按 td_only）
```

**已闭合（不再需要重做）**：π₀.₅ 底模加载与接口（仿真通过）；GPU 渲染解锁（16.5×，权威吞吐 **172.32** = `summary_20260929_221443.json`）；C2 的 env 判定层（D 离线重跑 PASS/`n_checks=15`/`red=[]`）；C2 的归一化契约层 + 闸 + 变异体（**Tr1 恒真牙已修，D 已验证**）；**A2 的 S4a（17/17 + 19/19）**；B2 的双向脚本专家 80/80（`--selftest`，非正式采集）；**B2 的甲图像存储**；**E 的腕部非确定性量化（`reps=2`，解除了 fork ⑤）**；D-H1（`assets/vx300s_right.xml:3` `euler="0 0 3.1416"`）。
**未开始**：B2 的 pilot 5 / formal 20/方向；A2 的 S4b/S5/S6；C2 的主线 stats（阻塞在 B2）；RL 更新闭环。

## §16.3 D 的文书身份（00:1x 实测，引用须带 `as_of`）

| 文件 | 行数 | sha256-12 |
|---|---|---|
| `work/decisions/decisions_20260929.md` | **1672** | **`9d42c1559058`** |
| `daily_report.md` | **5131** | **`17442f41e6b8`** |
| `rl_harness_supervision/d_handoff_to_a2_20260929.md` | **804** | **`466e28adc981`** |
| `rl_harness_supervision/d_handoff_to_b2_20260929.md` | **689** | **`8951dc6cc283`** |
| `rl_harness_supervision/d_handoff_to_c2_20260929.md` | **562** | **`49386fcdfd42`** |
| `rl_harness_supervision/d_handoff_to_e_20260929.md` | **452** | **`ffa2ee3c5b5b`** |
| `rl_harness_supervision/supervisor_memo_20260929.md` | 2460 | `84f38fde4813`（**只覆盖裁定 75–81；82/83 在 decisions + 本断点**） |
| `runs/vla/d_ruling_round_20260929_2355/gpu_contamination_event_20260929_2359.md` | 63 | `038b5ac72a2b` |
| before 影像 | —— | `runs/vla/d_ruling_round_20260929_2355/*.before83`（8 个文件） |

**参数表**：`work/project_parameters.json` 仍为 **rev11 / `68cb84295f1d`** ⇒ **裁定 82 与 83 都还没进参数表，需写 rev12**（见 §16.5-⑤）。

## §16.4 关键产物身份（00:1x 实测，**取代 §15 的对应表**）

| 文件 | 行数 | sha256-12 | as_of mtime |
|---|---|---|---|
| `scripts/c2_build_norm_stats.py` | **509** | **`fcfb72a88c92`** | 23:49:55 |
| `harness/norm_contract.py` | **566** | **`9e69ee487a9f`** | 23:54:47 |
| `scripts/b2_s1_generate_dataset.py` | **2540** | **`756a46b25984`** | 23:42:58（**B2 仍在改，sha 不稳定**） |
| `scripts/b2_s1_scripted_expert.py` | 1162 | `952437930706` | —— |
| `scripts/a2_s4a_vla_runtime_verify.py` | **1282** | **`6f4ed1228a4c`** | 23:50:29 |
| `harness/vla_runtime.py` | **772** | **`a42a3dd17c47`** | 23:40:06 |
| `scripts/a2_egl_latency_remeasure.py` | **1071** | **`ded5ffa39660`**（原 `294ceb53218a`/`b544f3741665`） | —— |
| `scripts/e_render_determinism.py` | 225 | `ffc867dd2e97` | 23:35:08 |
| `scripts/e_rawprobe_interference.py` | **509** | **`74e8afe88a4d`**（原 `ae3e735a8719`） | 23:44:11 |
| `harness/env_gym_aloha.py` | 579 | `6c4d71eb732e` | —— |
| `envs/gym_aloha_shim.py` | —— | `dc14466fcdcf` | —— |
| `scripts/c2_driver_output_guard.py` | 417 | `e6e3b2c2ad30` | —— |
| `scripts/c2_gate_env_gym_aloha.py` | 549 | `c9100b3811cd` | —— |
| `scripts/c2_run_c_regression_postpatch.sh` | 107 | `3ba62c9567e9`（已加守卫） | —— |

**权威数字（不得被新数字顶替，除非按裁定重判）**：渲染吞吐 = **172.32**（`runs/infra/e_mainline_calib_20260929/summary_20260929_221443.json`）；A2 延迟 = **run1 的 38.055 / 59.176**（run2 与 E 的 4 个 `proxy_a2` 批互污染，均不权威）；**裁定 76.4 的 quiet-window 权威值 = 尚未取得**（rep1 已被污染，A2 正在重跑）。CPU 基线 = **12.88**（12.03 已 `retired_caliber`）。
**已作废的引用**：`daily_report.md:4822` 与裁定 82⑤ 对 `RAW_PROBE_INTERFERENCE.json` **23:23:48 版**的引用 = **`stale_unrecoverable`**（改指 `generated_at=23:44:25` / generator `74e8afe88a4d`）。
**仍缺失**：**`docs/c2_handoff_to_d_20260929.md`**（C2 是四条线里唯一欠交回流单者；D 于 23:56 实测仍不存在）。

## §16.5 重启后 D 的接续步骤（照顺序跑）

1. **核身份**：`sha256sum` 对 §16.3 的 8 个文书 + §16.4 的脚本表；不符 ⇒ 先查是否被截断/覆写（`find runs docs -name '*before*' -newermt '-6 hours'`）。
2. **查卡与各线进程**：`nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader`；`ps -eo pid,ppid,lstart,etime,args | grep -E 'a2_|b2_s1|c2_|e_mainline|e_render|e_rawprobe' | grep -v grep`。**若 A2 的 quiet-window 已落地 ⇒ 先判它是否 `contaminated`**（读 `cotenant_evidence.classification`）；**若卡上有非 A2 进程而 A2 在跑 ⇒ 按 83.0 处置（先固化活体证据到 `runs/vla/d_*`，再令注入方让路）**。
3. **A2**：quiet-window rep1+rep2 是否权威落地？`policy_executed` 字段定义是否澄清？两份 `WHY_ARCHIVED.md` 的绝对路径是否给出？
4. **B2**：`grep -c "states_14d\|np.savez" scripts/b2_s1_generate_dataset.py` 是否 >0（**关键路径唯一卡点**）？`team_form` mp4 容器 fps 是否回报？git 是否代提交（HEAD 是否已离开 `c422659`）？
5. **写参数表 rev12**（D 单写）：把**裁定 82 + 83** 一起写进 `rendering`（`bare_renderer_same_process_ban`、**egl 下 wrist 不逐位的实测容差与 `GL_RENDERER` 键**、第 4/5/6 个渲染数一律不采纳、权威仍 172.32）与 `task`（replay 判据重定范围、**甲 = PNG inline parquet**、丙禁止、`timeout_isolation_scope=td_only` 及其 3 条硬约束）；并登记 5 条新纪律。
6. **C2**：`docs/c2_handoff_to_d_20260929.md` 是否交到？审计勘误行（78.11）？主线 stats 是否已用 B2 的 npz 起跑（若是先导版 ⇒ 检查是否标了 `stats_provenance=pre_pilot5_path_check`）？
7. **E**：`OVERWRITE_EVENT_20260929_2345.md` 是否交到？`reps≥5` 是否落地（落地 ⇒ 裁容差终值并按 83.3 的可推翻条件复核 fork ⑤ 是否仍解除）？D 的根因推断是否被确认/证伪？两轮开轮的事后补报？
8. **治理**：任何重大裁定后 **append `daily_report.md` 的 D 段 + 更新本断点（新开 §17，声明取代关系）**；扫八类缺陷：恒真闸 / **恒红闸（83.2 新增）** / 跨口径搬用 / 否定型主张未枚举 / 闸缺 `applies_when` / 自检未执行取数路径 / 假绿 / 引用 sha 过期 / **记录但未上报** / **注入器未过闸（83.0 新增）**。

## §16.6 需用户裁的分叉（**4 项 + 1 项事后追认**；D 自确认处均已写可推翻条件）

1. `parallel_eval_workers_cap` 若 S1 与 S5 必须用同一常数，取 **4**（S5/共租）还是 **8**（S1 独占+已申报）——D 已按场景分开定。
2. 是否向平台申请 `NVIDIA_DRIVER_CAPABILITIES=graphics`（D 已降级为非阻塞改善项；**申请动作本身要用户点头**）。
3. 是否投入测试 **bf16**（改数值口径 ⇒ 影响所有已留档数字的可比性；bf16 ⇒ 另立 `representation_version`）。
4. 是否给 E 一个 **5 分钟稳态并发窗口**（D：现在不给；A2 的权威重测优先）。
5. **【事后追认】`timeout_isolation_scope = td_only`**（裁定 83.7-2，口径放宽，D 自确认执行，标 `d_selfconfirmed_pending_user_ratification`）。**可推翻条件**：若 v4 原文明确禁止把 TimeLimit 截断轨迹用于 BC（任一线给出文件-身份三元组 + 行号）⇒ D 立即回退 `both_isolated`。
- **已解除**：~~fork ⑤（wrist 差异像素占比 >1% 是否改 osmesa 采集）~~ ⇒ **裁定 83.3 实测 0.0717% ≪ 1%，解除**。

## §16.7 用户偏好（不变）

中文；证据优先（`file:line` + 身份三元组 + `as_of`）；**分叉由用户裁，D 自确认时必须写可推翻条件**；共享文书只追加；每轮更新以「D 等各线什么 + 需用户什么」收尾；**D 的自我纠错必须显式写出并升为常设规则**（本日已累计 **9 次同型错误**：最近两次 = 83.0 排程只写「错峰」不写互斥锁、83.2 采纳 RED 却未索取绿见证）；**保护"下级可以纠正 D"的通道**（接受前须核文件身份；本日 B2 的路线胜过裁定 66、C2 的 D1 证实裁定 69、E 的 4-6 修了 D 的路径错误、**C2 的变异体推翻了 D 裁定 82① 的归因、A2 的 `GL_RENDERER` 口径比 D 写的更准**）；自设门未经 v4 对撞不得获得既成地位；**服务器可能关闭 ⇒ 每次重大裁定后更新本断点**。

---

# §17 【2026-09-30 00:4x 更新 —— **本节取代 §16.2/§16.3/§16.5/§16.6；重启后先读本节，再按需回查 §16.1（裁定 83 的逐条结论）与 §15/§14/§13.1/§13.3**】

**写入时刻**：2026-09-30 00:4x CST。**触发**：**裁定 84 落盘——裁定 76.4 的权威延迟值首次取得（4 个干净窗）**；D 撤回自己裁定 75.6 的「余量 2.6%」；E 的 GPU HOLD 解除。

## §17.1 裁定 84 的一句话结论（权威全文 = `work/decisions/decisions_20260929.md` 裁定 84 段，1672→**1782** ln，sha256-12 **`3adcee607c7c`**）

| # | 结论 |
|---|---|
| **84.1** | **裁定 76.4 闭合**：A2 的 5 个 rep 全部实读。**权威 = rep4 / rep5**（generator **`7e53558498ab`**、`policy_executed=true` 且定义已进产物、provenance 无歧义 = 全程在 A2 读到裁定 83 之后）；**rep2 / rep3 = 旁证**（generator `ded5ffa39660`、改前产物；rep2 起跑于 00:00:49 在 A2 读到 83 之前）；**rep1 不采纳**（`contaminated=true`）。**D 采纳 A2 主动把 rep2/rep3 自我降级的处置（A2 本可主张 4 个都权威）⇒ 记功。** 每 rep 的批级闸与销账逐份可核（`gpu_compute_apps_before=[]`、`after=[{own_pid,14900 MiB}]`，own_pid `161636`/`175795`/`202150`/`205499`）⇒ **裁定 76.2 合规的正面样本**；`gates_all_ok=true`（**9/9**）、`gl_renderer="NVIDIA A800-SXM4-80GB/PCIe/SSE2"` ⇒ `renderer_class=nvidia_gpu`。 |
| **84.2** | **权威数字（主线 n=25）**：`budget_fraction` **0.8009（rep4）/ 0.7766（rep5）**、`mean_wall_ms_per_ctrl_step` **27.230 / 26.405 ms**、`mean_loop_fps` **36.739 / 37.873**、`mean_inference_share_of_budget` **0.5918 / 0.5719**、**`all_episodes_within_per_step_budget=true`**；旁证 rep2 **0.7703 / 38.183**、rep3 **0.7857 / 37.436**；**4 窗区间 0.7703–0.8009、相对散布 3.9%、余量 19.91%–22.97%**。n=50：`budget_fraction` 0.4906–0.5151（**比 n=25 更快，但仍按裁定 65-1 驳回，理由是结构 `H≥2n` 不是延迟**；A2 的 `gates.v4_H_ge_2n` 实测 `n=50 satisfied=false`/`n=25 satisfied=true` ⇒ **结构判据首次有机器闸承载**）。**⇒ 裁定 75 的 `n_replan=25 STANDS` 由「v4 合规（唯一依据）」升级为「v4 合规 + 实测可行（双重依据）」。** run1（38.055/77.3%）**不被推翻而是被印证** ⇒ `provisional_from_archived_run1` 改标 **`corroborated_by_clean_reps`**。 |
| **84.3** | **污染幅度首次被量化（本轮最有价值的量化教训）**：rep1（污染）vs 干净窗 ⇒ n=25 `mean_loop_fps` **25.255** vs 36.739–38.183（**压低 31.2%–33.8%**）、`budget_fraction` **1.3466** vs 0.7703–0.8009（**抬高 68.3%–74.8%**）、`all_episodes_within_per_step_budget` **false → true（结论极性反转）**；n=50 `budget_fraction` **1.0638** vs 0.4906–0.5151（**抬高 106.5%–116.8%**）。**⇒ 若采纳污染数会得出「n=25 超预算 1.35×、必须降 n」，与真相相反 ⇒ 裁定 75「预算是软约束」+ 裁定 76 的污染纪律，其价值现在有了数字。** |
| **84.4** | **D 的第 10 次同型错误：撤回裁定 75.6 的「余量 2.6% / 97.4%」。** 75.6（`decisions:1291`）写 `5.80(渲染) + 27.33 = 33.13 ms = 97.4%`；但 `decisions:1266`（裁定 74）自己记的 run1 **实测总墙钟 = 26.28 ms** ⇒ **分量之和 33.13 > 实测总量 26.28，逻辑上不可能** ⇒ 分量来自不同 run/不同口径（`27.33` 出自 75.2 的另一处测量且 run1 是 `loadavg 67–72` 最忙时；`5.80` 是 E 的渲染数）⇒ **D 违反了自己立的 `caliber_transplant_ban`，是第 7 次同型错误的重复**。**附带推翻一条旧担忧**：`budget_fraction` 在 `loadavg_1m` **25.17–72 全区间几乎不变**（0.773/0.7703/0.7857/0.8009/0.7766）⇒ **该闭环 GPU 推理受限、对宿主 CPU 负载不敏感 ⇒ 「轻载/重载并列报」的额外测量成本取消**（但 `loadavg` 三点 + `nr_throttled` 对的纪律不变，因为这条结论本身靠这些读数证明）。**⇒ 新立 D 自查项 `component_sum_must_not_exceed_measured_total`。** |
| **84.5** | **A2 的 §18-6 澄清项闭合、D 销账**：A2 改 `scripts/a2_egl_latency_remeasure.py`（1071→**1171 ln**、`ded5ffa39660`→**`7e53558498ab`**、mtime 00:22:50），在产物内落 `policy_executed_definition`：**`policy_executed` = 读法 A（「策略权重驱动的前向推理且输出用于 `env.step()`」，可机器判）；读法 B（「以产出任务结果为目的执行策略」）归 `capability_claim`/`success_metrics_collected`（本族恒 false）**；`why_not_conflate` = 若用读法 B 则 `closed_loop` 写 true 等于同时声称「在做任务、有结果」⇒ 放大能力主张误读面；`scope_semantics` = 顶层是**所有模式级同名值的 OR**、初值 false、**臂跑完后必须重算**、由 `gates.policy_executed_consistency` 看守。**⇒ D 升为两条全线规则：`boolean_field_reading_must_be_declared`、`top_level_aggregate_must_declare_semantics`。** **A2 并自发实现了 D 在 83.2 新立的 `green_witness_required`**（该闸带 `unidirectional_by_design=false` + 绿见证字段）⇒ **闸数 8→9、全绿，D 记功（规则落盘 30 分钟内被下游自发实现的首例）**。**A2 仍欠 §13 的销账读数行**（D 实测 00:33:09 卡空 ⇒ 销账事实上成立，但 **D 的实测不能替代 A2 自己的读数行**，裁定 50.1「记录 ≠ 上报」）。 |
| **84.6** | **GPU 窗口交接（`gpu_window_mutual_exclusion` 第一次正式适用）**：A2 的窗已结束（D 实测 00:33:09 compute apps 为空）⇒ **持窗者 = E**。**起点判据（两条都要）**：① E 在 `daily_report.md` 写申报行（A2 §9/§12 模板）；② E 实测 `--query-compute-apps` 为空并把读数写进产物。**终点判据**：E 写销账读数行。**窗内 A2 禁止启动任何 GPU 进程**（需上卡须写申报行并等 E 销账；A2 的批级闸 `return 4` 是硬保护）；**窗内 E 禁止启动任何共租注入器 ⇒ 本轮明令 `--cotenant` 一律不得启用**（理由：`e_render_determinism.py` 只做渲染、上轮 4 runs 的 `gpu_before` 全是 0 MiB/0%/空 ⇒ 确定性取证与共租负载在方法上无关；若必须用须先向 D 申请，且即使获批注入器启动前仍须过批级闸）。**优先级仍 A2 > C2 > E > B2；A2 需重开窗时 E 须让路，E 的批次须可在 ≤1 个批次粒度内中断。** |
| **84.7** | **实时可行性口径变更：D 解除裁定 75 对「实时闭环」措辞的禁令，但严格限定范围**。**现在可以写**（须带完整口径 + `loadavg` 三点 + `nr_throttled` 对）：「主线 `n_replan=25` 的**同步**闭环在预算内，`budget_fraction` 0.7766–0.8009、余量 19.91%–22.34%、`all_episodes_within_per_step_budget=true`、4 个独立干净窗一致、`GL_RENDERER=nvidia_gpu`、egl + prefix-only、shim `dc14466fcdcf`、`DT=0.034`/`29.411765 Hz`/`n_sub_steps=17`、`--max-steps 300`、3 集/臂、π₀.₅ 真权重 14,900 MiB」。**仍然禁止写**任何「异步重叠 / 线程并发 / async 实时闭环」（`async_overlap=false`、未实现；G17 的异步最小证据字段须在真推理下跑过一次）。**理由**：裁定 75 的禁令前提是「手上数字互不一致且口径混乱」（E 165.65 / run1 30.522 / run2 65.865），**现在 4 个干净窗彼此一致（散布 3.9%）且每窗自证 `contaminated=false` + 批级闸 + 销账可核 ⇒ 禁令的事实前提已消失**。**可推翻条件**：若后续任一干净窗实测 `budget_fraction > 1`（换 `num_inference_steps`、bf16、加相机、加物体、或真机 P4 口径）⇒ 自动失效、回到裁定 75 的禁令状态并重测。**裁定 75 其余不变**：`budget` 仍是软约束 + `overload_flag`；P4 实机豁免但必须实测；bf16 ⇒ 另立 `representation_version`。 |
| **84.8** | **权威数字台账（唯一可引用来源；参数表 rev13 已同步）**。**改标**：`provisional_from_archived_run1` → `corroborated_by_clean_reps`。**撤回**：裁定 75.6 的「余量 2.6% / 97.4%」；裁定 74 里 A2 外推的「61.6% / 余量 38.5%」仍不采纳。**不采纳**：rep1；E 的第 4/5/6 个渲染吞吐数（`179.53`、`summary_20260929_234814`、`summary_20260929_235835`）⇒ **渲染吞吐权威值仍是 `172.32`**。**新立 D 自查项 1 条**（`component_sum_must_not_exceed_measured_total`）+ **全线规则 2 条**（`boolean_field_reading_must_be_declared`、`top_level_aggregate_must_declare_semantics`）。**D 的自记账：第 10 次同型错误；本日累计 10 次 + 1 次 near-miss。** |

## §17.2 关键路径与链状态（00:4x，**取代 §16.2**）

```
【E 持 GPU 窗（HOLD 已解除）】reps>=5 腕部扩展轮（--cotenant 禁用）= S1 正式采集的验收前置
        ↓（同时，不占 GPU、不必等窗）
【B2】states_14d.npz 导出（关键路径唯一卡点，可用降阶方案先出先导版）
      + team_form mp4 容器 fps 实测回报 + git 代提交（脏 51）+ replay 闸重定范围+变异体 + 78.3/78.4/78.5/78.8/78.2
        ↓（npz 落地）
【C2】T-C2-1 主线 stats（--s1-frames）→ 然后 env_gym_aloha.py 三条硬约束（裁定 62）
        ↓
【A2】S4b 接真帧（四类判定独立于 reward==4；timeout 按 td_only）
```

**本轮已闭合（不再需要重做）**：**裁定 76.4 的权威延迟值（rep4/rep5）**；A2 的 S4a（17/17 闸 + 19/19 变异体，`frozen_surface_touched=[]`）；A2 的 `policy_executed` 定义（并已升为两条全线规则）；C2 的 `Tr1` 恒真牙修复（D 独立验证：floor_off 由全 PASS → 17 RED）；C2 的归一化契约层 + 闸 + 变异体；B2 的甲图像存储（`fps=29.41176470588235` 精确、三相机 `dtype=image`）；B2 的双向脚本专家 80/80（`--selftest`）；E 的腕部非确定性量化（`reps=2`，解除了 fork ⑤）；E 的 raw-probe 两处更正。
**仍未闭合**：**B2 的 `states_14d.npz`（关键路径唯一卡点，第 2 次催办）**；**B2 的 git 代提交（HEAD 仍 `c422659`，脏 51）**；**C2 的 `docs/c2_handoff_to_d_20260929.md`（四条线里唯一欠交回流单者）**；E 的 `reps≥5` + `OVERWRITE_EVENT` + 根因确认 + 两轮补报 + ballast 装闸；A2 的 §13 销账读数行 + 两份 `WHY_ARCHIVED.md` 的绝对路径；B2 的 pilot 5 / formal 20；A2 的 S4b/S5/S6；C2 的主线 stats；RL 更新闭环。
**注**：B2 的 `--selftest`（PID 196012，00:21:02 起）是 CPU 侧、不占卡 ⇒ 与 A2 的窗无冲突（D 实测确认）。

## §17.3 D 的文书身份（00:4x 实测，**取代 §16.3**）

| 文件 | 行数 | sha256-12 |
|---|---|---|
| `work/decisions/decisions_20260929.md` | **1782** | **`3adcee607c7c`** |
| `daily_report.md` | **5343** | **`b21431f9fa7a`** |
| `rl_harness_supervision/d_handoff_to_a2_20260929.md` | **883** | **`7f1a81075d3a`** |
| `rl_harness_supervision/d_handoff_to_e_20260929.md` | **492** | **`487e0d31a255`** |
| `rl_harness_supervision/d_handoff_to_b2_20260929.md` | **689** | **`8951dc6cc283`**（§17，裁定 83） |
| `rl_harness_supervision/d_handoff_to_c2_20260929.md` | **562** | **`49386fcdfd42`**（§14，裁定 83） |
| `work/project_parameters.json` | **见 rev13** | **见 rev13**（rev12 = 1611 ln / `23be5c0279d6`） |
| `rl_harness_supervision/supervisor_memo_20260929.md` | 2460 | `84f38fde4813`（**只覆盖裁定 75–81；82/83/84 在 decisions + 本断点**） |
| before 影像 | —— | `runs/vla/d_ruling_round_20260929_2355/*.before83`（8 个）、`runs/vla/d_ruling_round_20260930_0030/*.before84`（6 个） |
| GPU 互污染实时取证 | 63 | `runs/vla/d_ruling_round_20260929_2355/gpu_contamination_event_20260929_2359.md`（`038b5ac72a2b`） |

## §17.4 关键产物身份增补（00:4x；**与 §16.4 合并使用，冲突以本节为准**）

| 文件 | 行数 | sha256-12 | as_of mtime |
|---|---|---|---|
| `scripts/a2_egl_latency_remeasure.py` | **1171** | **`7e53558498ab`**（原 `ded5ffa39660`/`294ceb53218a`/`b544f3741665`） | 00:22:50 |
| `runs/vla/a2_egl_latency_20260929/latency_quiet_window_rep4.json` | —— | **权威**（`generated_at=00:24:38`、own_pid 202150） | 00:26:27 |
| `runs/vla/a2_egl_latency_20260929/latency_quiet_window_rep5.json` | —— | **权威**（`generated_at=00:26:29`、own_pid 205499） | 00:28:19 |
| `latency_quiet_window_rep2.json` / `rep3.json` | —— | **旁证**（generator `ded5ffa39660`） | 00:02:40 / 00:12:04 |
| `latency_quiet_window_rep1.json` | —— | **不采纳**（`contaminated=true`） | 00:00:08 |
| `runs/vla/a2_s4a_vla_runtime_20260929/s4a_verification.json` | —— | 17/17 闸 + 19/19 变异体（`generated_at=23:51:03`） | 23:40:33 → 23:51:03 |
| `runs/vla/b2_sim_demo_bidir_20260930/selftest/pi05_lerobot/meta/info.json` | —— | **甲已落地**（`fps=29.41176470588235`、三相机 `dtype=image`） | 00:2x（B2 的 `--selftest` 重跑） |
| `runs/vla/c2_norm_contract_20260929/matrix.json` | —— | **基线 PASS（23:55:00）**；**该 PASS 的数据源是 `env_derived_diagnostic` ⇒ 不得引用为「契约已通过/可开始 BC」** | 23:55:00 |
| `runs/vla/c2_norm_contract_20260929/mutation_floor_off/matrix.json` | —— | **修后 17 RED / verdict=RED（牙咬了）**；修前证据在 `mutation_floor_off_pre_Tr1_fix_EVIDENCE_vacuous_tooth/`（全 PASS） | 23:55:01 |
| `runs/infra/e_mainline_calib_20260929/RENDER_DETERMINISM.json` | —— | **解除 fork ⑤ 的依据**（最差 `frac_diff_px=0.000717`） | 23:40:30 |
| `runs/infra/e_mainline_calib_20260929/RAW_PROBE_INTERFERENCE.json` | —— | **当前版 = `generated_at 23:44:25` / generator `74e8afe88a4d`**；**原 23:23:48 版 = `stale_unrecoverable`** | 23:45:24 |

## §17.5 重启后 D 的接续步骤（00:4x，**取代 §16.5**）

1. **核身份**：`sha256sum` 对 §17.3 的文书 + §17.4/§16.4 的产物；不符 ⇒ 查是否被截断/覆写（`find runs docs -name '*before*' -newermt '-6 hours'`）。
2. **查卡与窗口归属**：`nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader`。**按 §17.1-84.6 判定当前持窗者**：若卡上有进程 ⇒ 用 `ps -o lstart,args -p <pid>` 判归属；**若 E 在跑而 A2 申报了窗 ⇒ 令 E 让路（优先级 A2>E）；若 A2 在跑而 E 也在跑 ⇒ 按裁定 83.0 处置（先固化活体证据到 `runs/vla/d_*`，再令注入方让路）**。**若卡上有 `proxy_a2`/ballast 类注入器与他线测量并存 ⇒ 直接判违反红线 `cotenant_injector_must_be_gated`。**
3. **E**：`reps≥5` 是否落地（落地 ⇒ **裁容差终值**：若实测最差 ≤0.005 则维持 D 定的 `2 / 0.005 / 0.005`；若 >0.005 则按「实测最差 ×7」重定；若 >1% 或 `max_abs_diff>8` 或 `angle` 不逐位 ⇒ **裁定 83.3 自动失效、改双后端并回用户裁**）；`OVERWRITE_EVENT_20260929_2345.md`；根因推断的确认/证伪；两轮补报；ballast 是否装闸；裁定 77.8 那一行指针的路径+行号。
4. **B2（关键路径）**：`grep -c "states_14d\|np.savez" scripts/b2_s1_generate_dataset.py` 是否 >0；`team_form` mp4 容器 fps 实测值；`git log --oneline -1` 是否已离开 `c422659`、`git status --porcelain | wc -l`。
5. **C2**：`docs/c2_handoff_to_d_20260929.md` 是否交到；主线 stats 是否起跑（若用先导版 npz ⇒ 检查是否标 `stats_provenance=pre_pilot5_path_check`、是否进了 BC）；审计勘误行（78.11）。
6. **A2**：§13 的销账读数行；两份 `WHY_ARCHIVED.md` 的绝对路径；**不必再跑 quiet-window（裁定 84.1 已闭合）**。
7. **治理**：任何重大裁定后 append `daily_report.md` 的 D 段 + 更新本断点（新开 §18，声明取代关系）+ 参数表加 rev。**扫十类缺陷**：恒真闸 / **恒红闸（83.2）** / 跨口径搬用 / **分量之和超过实测总量（84.4）** / 否定型主张未枚举 / 闸缺 `applies_when` / 自检未执行取数路径 / 假绿 / 引用 sha 过期 / 记录但未上报 / **注入器未过闸（83.0）**。

## §17.6 需用户裁的分叉（00:4x，**取代 §16.6**；**4 项 + 1 项事后追认，本轮无新增**）

1. `parallel_eval_workers_cap` 若 S1 与 S5 必须用同一常数，取 **4**（S5/共租）还是 **8**（S1 独占+已申报）。
2. 是否向平台申请 `NVIDIA_DRIVER_CAPABILITIES=graphics`（D 已降级为非阻塞改善项；**申请动作本身要用户点头**）。
3. 是否投入测试 **bf16**（改数值口径 ⇒ 影响所有已留档数字的可比性；bf16 ⇒ 另立 `representation_version`）。**注：裁定 84.7 的可推翻条件里，bf16 是会让「实时闭环」声明失效的因素之一。**
4. 是否给 E 一个 **5 分钟稳态并发窗口**（D：现在不给；且裁定 84.6 已明令 E 本轮 `--cotenant` 禁用）。
5. **【事后追认】`timeout_isolation_scope = td_only`**（裁定 83.7-2，口径放宽，标 `d_selfconfirmed_pending_user_ratification`）。**可推翻条件**：若 v4 原文明确禁止把 TimeLimit 截断轨迹用于 BC（任一线给出文件-身份三元组 + 行号）⇒ D 立即回退 `both_isolated`。
- **已解除**：~~fork ⑤（wrist 差异像素占比 >1% 是否改 osmesa 采集）~~ ⇒ 裁定 83.3 实测 **0.0717% ≪ 1%**，解除。
- **裁定 84 全部属 D 可自确认的技术口径，无新增分叉**；每条都写了可推翻条件（84.2 的结构 vs 延迟区分、84.4 的负载不敏感、84.7 的 `budget_fraction>1` 自动失效）。

---

# §18 【2026-09-30 01:2x 更新 —— **本节取代 §17.1/§17.2/§17.3/§17.4/§17.5/§17.6 的全部对应项；重启后先读本节**。§16.1（裁定 83 的逐条结论）与 §15/§14/§13.1/§13.3 仍按需回查，但其中「渲染权威值 172.32」「rep4/rep5 权威」「angle 必须逐位」三处**已被本节推翻**】

## §18.0 一句话态势

**裁定 85 已完整落地（10 节），关键路径已解锁。** 本轮四线都有实质交付且**无一起在跑进程**（01:0x 实测 GPU `0 MiB / 0%`、无 a2/b2/c2/e 脚本进程）。**用户已离开**，授权 D 自确技术口径（须写可推翻条件）、分叉留给用户；**服务器可能关闭 ⇒ 本节必须保持最新**。

## §18.1 裁定 85 的十节结论（权威全文 = `work/decisions/decisions_20260929.md` 裁定 85 段，1782→**2177** ln，`3adcee607c7c`→**`7bae37a52e69`**）

- **85.0【最重】`nvidia-smi --query-compute-apps` 对 EGL 图形负载是盲的。** E 于 **00:42:53** 实测：B2 的 pilot（PID `235015`）持 `/dev/nvidia2`+`/dev/nvidiactl`、util/mem = **11% / 102 MiB**，而 `--query-compute-apps` = **空**；A2 的探测器口径正是 `--query-compute-apps` + `ps`（`scripts/a2_egl_latency_remeasure.py:135`）⇒ **A2 的批级闸与运行时采样器对 B2 的 EGL 渲染盲**。时间重叠：B2 selftest **00:21:03–00:26:58**，A2 rep4 窗 **00:24:37–00:26:27**（全程落入）、rep5 窗 **00:26:29–00:28:19**（前 29 s 落入）。**签名匹配**：两个互相独立的 B2 GPU 作业（A2 于 00:26:29 读到、E 于 00:42:53 读到）显存**都是 102 MiB** ⇒ 按裁定 76.1 记 `inferred_strong_signature_match`，**不写 `confirmed`**。
  ⇒ **新红线 `card_busy_detector_must_include_fd_and_cmdline_nets`**（三网或自证等价，四线一律适用；牙 E 已验，复用不重造）；**rep4/rep5 的 `contaminated=false` 降为 `undetermined_detector_blind_to_egl`**（rep5 另加 `unexplained_start_mem_102MiB`）；**但延迟数值带不变（`0.7703–0.8009`，spread 3.9%）**，provenance 改为「四窗全部由一个现已知对 EGL 盲的探测器认证，无一窗持三网清洁证书」；裁定 84.7 降为 `provisional_pending_three_net_certificate`（**不撤回**）。**数值站得住的三条理由**：rep2/rep3 的窗在 00:21:03 之前不受影响；若真污染 rep4/rep5 应显著高于 rep2/rep3（对照 rep1 高 +68.3%~+74.8%），实测 rep5 落在两者之间、rep4 仅高 2.0%；`n_replan=25` 主要立在结构判据 `H≥2n` 上。**A2 无过错且记功**（它主动写的「闸以 compute apps 为键、不以显存余量为键」是 D 查出盲区的唯一线索 ⇒ 裁定 50.1 产生实际价值的第 1 个确证案例）。补测 = **1 个**三网清洁 rep（P2，排 B2 formal 间隙），**不要重跑整个 quiet-window**。
- **85.1 §E0 采纳甲案：渲染权威值 `172.32` → `136.99` ctrl-steps/s（`7.300 ms/步` = 预算 `21%`）**，出处 `summary_20260929_234814.json`（`32d15f0da3b3` as_of 23:54:08）。`172.32` 降 **`invalidated_probe_polluted`**——它出自**裁定 82.5 立为红线 `bare_renderer_same_process_ban` 的那个成因**（同进程裸 `mujoco.Renderer`，顺序 `raw_after`）。加速倍数 **`16.5×` → `12.64×`**。裁定 77.3（后端 = egl）**不翻转**（CPU 软渲染 92.374 ms = **2.72× 预算**）。**连带：裁定 77.2 的『近线性到 8』撤回**（eff 实测 `1.0/0.975/0.921/0.684`，每 worker `7.300→10.486 ms` = 预算 `21%→31%`），**`workers_cap=8` 保留 ⇒ 用户分叉① 关闭**。**任何延迟/实时性主张必须用 w=1 的 7.300 ms，不得拿聚合数除 worker 数冒充单 worker 延迟。**
- **85.2 §E11.2：条件③ 是 D 自己的判据设计缺陷；采丙案（`d_selfconfirmed_pending_user_ratification`）。** n=5（10 个独立进程）：**osmesa 三相机全逐位（进程内 + 跨进程）**；**egl 三相机全不逐位**，但 `max_abs_diff` **全为 1**、`frac_diff_px` 最差 **0.052%**（`angle` 仅 **0.002%**）。83.3 的条件①（>1%，低 19×）②（>8，低 8×）**未触发**，条件③（`angle` 不逐位）**触发**（产物机器现算 `ruling_83_3_stands=false`）。**D 的自纠**：条件①②带量级门槛、条件③是**不带量级门槛的布尔** ⇒ 等于给 1 LSB 一票否决权；与 83.1 的 `Tr1`（恒真闸）、83.2 的 `Tc`（恒红闸）是**同族第三形态**。⇒ **新规则 `criterion_must_have_magnitude_floor`**。**处置：结论保留（采集后端 = egl）、前提更正（撤回「`angle` 必须逐位一致」，它来自 n=2/n=3）、判据重修（条件③ 改为 `angle_non_bitwise_and(frac_diff_px>0.001 or max_abs_diff>2)`）；osmesa 保留为「逐位可复现」的对照后端，不用于采集。** D 自确而非等用户的理由：甲案会把**全仓唯一真阻塞**（B2 的 S1）墙钟放大 **12.64×** 去换 1 LSB，而用户本轮明令「尽快跑通仿真链」。**新红线 `render_bitwise_equality_ban_on_egl`**（E 的 `implication_for_gates` 原句升格；`applies_when` 以**实测 `GL_RENDERER`** 为键；牙 = 继续拿 `angle` 逐位当硬判据会有 ~1/5 概率的**不可复现假红 = 随机红**）。
- **85.3 §E11.3 已转 B2 并即时生效：replay 闸硬判据 = 状态逐位，仅此一条**；三相机像素一律只登记不判红（容差取 n=5 实测 `angle ≤0.002%` / `left_wrist ≤0.024%` / `right_wrist ≤0.052%` / `max_abs_diff ≤1`）。**裁定 83.4 的三个数值不需重定**（可推翻条件②未触发，余量 **9.7×** / **2×**）。**「状态逐位」为何安全 —— 三腿互证**：B2 的 `episode_replay_comparison.recorded_vs_norender.bitwise_equal=true / max_abs_diff=0.0`（n=274，B2 自注该臂作用 = 「隔离『渲染是否扰动物理』」）⇒ **EGL 的像素不确定性不泄漏进动力学**；+ E 的 n=5（≤1 LSB）+ D 的 83.4 容差。**三条牙**：绿证人（干净重放 ⇒ 绿）／必红（篡改任一维状态 1 LSB ⇒ 红）／**必红变异体（篡改像素但保留状态 ⇒ 仍绿）**——第③条是本裁定专属的牙，缺它则「像素已降级」无法被证明。
- **85.4【关键路径解锁】`states_14d.npz` 任务撤销。** B2 的先导 10 集已于 **00:46:57** 落地，D 亲读 `pilot/pi05_lerobot/data/chunk-000/file-000.parquet` schema（pyarrow 25.0.1）= `observation.state: fixed_size_list<float>[14]`、`action: [14]`、三相机 `struct<bytes,path>`、**2746 行 / 10 集**；`grep -c states_14d scripts/b2_s1_generate_dataset.py = 0` ⇒ **数据已在 parquet 里，导出任务多余**。C2 新增 `--s1-lerobot <dir>`（改自己的脚本）：按 `episode_index` 分组、组内按 `frame_index` 升序；`start_poses` 取 `frame_index==0`；`physical_range` 用 C2 自己的 `physical_range_effective`（实测夹爪行程 **0.91001 不是 1.0**）。**必须落 dtype 口径声明 `state_dtype_source=float32_parquet_upcast_to_float64`（逐位比较不可跨 dtype）**。**【同源硬闸，裁定 52/69】**：pilot-10 ⇒ `stats_provenance=pilot10_path_check`，用途**限定三项**（端到端验证契约层／实测 q01–q99 对 `ctrlrange` 的覆盖率与**饱和维数=0**／验 `Tr1` 修复后的闸在真数据上有牙），**不得进 BC**；formal-40 ⇒ **必须重算**并标 `formal40_bc_source`，`norm_contract` 层必须**拒绝**非该 provenance 进 BC（牙：喂 pilot10 的 stats 给 BC 配置 ⇒ 必须红）。**裁定 83.8 的降级路径 `pre_pilot5_path_check` 作废。** C2 的 `mainline_status.json`（as_of 00:34:47，`status=waiting_for_s1_pilot_5` / `checked_path=null`）**已过期需重生成**。
- **85.5 B2 的先导 10 集验收通过 + RR 四条全裁 + D-H1 被否证。** 闸 `PASS / 16 / 0 red / 0 warn / 0 UNJUDGED`；专家自证 **80/80 success**；重放**三臂全 `bitwise_equal=true / max_abs_diff=0.0`**、形状守恒 `286−12==274`；**`team_form` mp4 fps 三相机实测 `29.41176470588235` 精确**（裁定 83.8 欠项销账）；体积 **0.0539 GiB**（formal 40 集外推 **≈0.22 GiB**）。**RR-B2-10 反向串批准** `Transfer the red cube from the left arm to the right arm.`（正向 `reward=4`、反向 `reward=2`≠4 已核；**两串即训练/评测共用条件信号，改串 = 换 `representation_version`**，当前版本串**冻结**）。**RR-B2-11 键名：B2 正确、D 撤回自己的写法** ⇒ **`observation.images.{base_0_rgb,left_wrist_0_rgb,right_wrist_0_rgb}`**（D 的 §13.8-2 写 `{top,left_wrist,right_wrist}` **错**）。**RR-B2-12 维持甲（PNG 内嵌），不做丙（monkeypatch）**（lerobot 0.4.4 的 `video_utils.py:460`→`av/utils.pyx:51` 对非整数 fps 抛 `AttributeError`；甲体积余量 45×，丙要改第三方运行时而体积不是约束）。**RR-B2-13 确认为「每方向」** ⇒ 先导 **10 集**、正式 **40 集**（消解裁定 66 歧义）。**裁定 66 §13.5 的 EE-oracle 字面路线关闭**：B2 给了五条实测理由（weld 复位瞬间违反约束 ⇒ 第一步猛拉 **13.5 cm**；右臂解析反解残差 **0.2469 m / 2.376 rad** vs 左臂 **0.0013 m**；mocap 阶跃后 weld 残差**不收敛反变大** 0.0872→0.1359 m；EE 模型 `nu=4` 且 **4 个 actuator 名全为空串**；`tasks/sim_end_effector.py:120` 无条件渲染）。**D-H1 被 `probe4.json`（`3eaf525b67ab`）实测否证**（`verdict_status=b2_measured_falsifies_d_inference`）：B2 已逐侧读 `eq_data[6:10]`（左 `[1,0,0,0]`、右 `w≈0/z≈1`），复合后右臂残差**仍 0.2469 m** ⇒ 真因是**约束本身不一致**（无臂 actuator + 右基座绕 z 反装 180°，`assets/vx300s_right.xml:3` `euler="0 0 3.1416"`），**不是反解公式的错**。**D 判：不计入同型错误台账——这是带预登记否证判据的假设被正常否证，是制度在工作。记功 B2（第 7 次下位纠正 D）。**
- **85.6 B2 的两处纪律问题（均自报在先，D 只登记）。** ① **00:26:58 那版 selftest manifest 灭失 ⇒ `unbacked_citation` 第 2 起**（第 1 起是 E 的 83.5）：B2 §1.1 引的读数出自被 00:32 重跑覆写的那版 ⇒ **标 `stale_unrecoverable`，不得作为 rep4/rep5 污染的确证证据**（这是 85.0 只判「未定」的第二条理由）。D 已查可复原性：`recycle_bin/` 下有 `b2_s1_pi05_lerobot_20260930_002103_546094` 与 `b2_s1_team_form_data_20260930_002103_537128`（`--trash` 而非 `rm`，**合规**），但 **manifest 本体不在其中** ⇒ 不可复原。**裁定：`--trash` 必须纳入 `demo_manifest.json`；守卫复用 C2 的 `c2_driver_output_guard.py`（690 ln `6cc7b148295b`）的 `snapshot` 半段，不新写。** ② **RR-B2-18 `contaminated_by_cotenant` 恒真（缺陷类 ①，与 `Tr1` 同族）**：00:32 那次 GPU 明明空载（`verdict='gpu_idle'`、`compute_apps_parsed=[]`、`nvidia_smi_gpu_verbatim='0, 0, 37'`）而标志仍 `true`，肇事者 = 7.4 h 前的空闲 bash（PID `39153`、`pcpu=0.0`、args 含 `RL_Robot`）。**裁定三条驱动修法但第①条必须改**：①→**①′ `card_busy(strict=True)` 三网**（原「外来 compute app」按新红线单独不成立）；②「归线且 **`pcpu>1%`** 的活跃作业」批准；③「`loadavg_1m` 摆幅 ≥5」批准；被忽略的空闲进程照样落产物并写明理由。**三条牙**（含「只留 `pcpu=0.0` 空闲 bash ⇒ 必 `false`」，当前实现在这个证人上就是红的 ⇒ 它既是牙也是修复验收）。**B2 的 `gpu_preflight()` 硬闸方向认可，但判据同样只查 compute-apps ⇒ 一并升级三网**；「GL 上下文挪到硬闸之后才起」与「`ctx_quiet_window.reason` 改为由实测生成」**两处记功**。
- **85.7 GPU 窗口机制补齐。** E 报的排程缺口**成立，D 认**：裁定 84 §5 只写了「窗内 A2 的禁止动作」、**没覆盖 B2**，而 B2 的 S1 采集本来就走 GPU 渲染（`b2_s1_generate_dataset.py:69`）⇒「持窗者=E」与「B2 正在采集」可同时为真。**这是 D 的条款漏洞。** ⇒ ① 窗口条款**覆盖全部四线**：起 GPU 进程（**含渲染采集、含共租注入器**）前必须三网 + 申报行 + 销账行，**三项读数 = `compute-apps 条数 / fd 网外来 PID 列表 / memory.used MiB`**；② **优先级改为「关键路径感知」= `A2（已申报的标定窗）> B2（S1 采集）> C2 > E`**，**取代裁定 73 的 `A2>C2>E>B2`——B2 从末位升第 2**（**采纳 E 在 §E1 的判断，改的是 D 自己的旧优先级**）；A2 仍可压 B2 但须给 ≥1 个批次排空时间；③ E 的 `--cotenant` 本轮继续禁用，共租档挂起至 formal 落地；④ **E 本轮 GPU 待办清空**。**新任务 T-C2-7 · GPU 窗口登记处（P1，C2 接）**：D 授予 C2 对 `scripts/gpu_window_ledger.py` + `runs/infra/gpu_window_ledger.jsonl` 的**写入例外**（改前必须 snapshot）；接口 = `claim`（**原子占用**，被占则 `exit 3` 并打印持有者）/`release`（落终点三项读数）/`status`/**陈旧锁 TTL**（进程不在 `/proc` 或超 `est-seconds×3` ⇒ `stale`，可抢占但**必须留痕**）/`jsonl` **只追加**；**三条牙**（并发 `claim` 恰好一个成功 + 必红变异体「换成先读后写 ⇒ 必须能观察到双占」／`claim` 时卡上已有他线 fd 持有者 ⇒ 拒绝／持有者消失后 `status` 报 `stale`）。**P1 不是 P0**：三网 + 申报 + 销账的纪律已够用（E 的 §E1 就是靠它正确让位的），登记处是把「靠自觉 + 散文申报」换成「机器可判」，**不阻塞 S1**。**E 只需把 `card_busy()` 口径交 C2 复用，不自己写登记处。**
- **85.8 C2 就位声明核对（用户点名）：自述与磁盘一致，无夸大。** **T-C2-1 已交付**（`norm_contract.py` 566 ln `9e69ee487a9f` + `c2_build_norm_stats.py` 509 ln `fcfb72a88c92`；`mutation_floor_off` 修复后 **17 RED**；修复前证据留档）；**T-C2-2 已交付，本仓牙最完整的一把**（`queue_td_learner.py:145-149`，661 ln `afc9ebb92621` as_of 21:28:51，`okc.check_coverage` 在拼向量**之前**执行；探针 `DEFECT_REPRODUCED`，4 个带图像变体 `vec_sha12` 全 = `4fd32aacc677` 与 state-only 逐字节相同 ⇒ **静默丢图确证**；两个正对照：扰动 state ⇒ `d172107c367b`≠`4fd32aacc677`、`state_dim` 配错 ⇒ `14 != 13`；`all_controls_ok=true`；**D 追认批准**）；**T-C2-4 已交付**（`docs/c2_gate_polarity_audit_20260929.md`，285 ln `768d49409d76`，三起实测 D 全部认可）；**T-C2-3 / T-C2-5 未交付 → 降 P2**（容量不是当前约束：pilot 0.0539 GiB、formal ≈0.22 GiB vs 预算 10 GiB；A 线已冻结属归档完备性）；**T-C2-6 不接正确，D 本轮仍不裁**（π₀.₅ 线的闸刚改判三把，现在定并存口径会立刻过期；触发 = formal 落地 + S3 训练闸定型）；**`docs/c2_handoff_to_d_20260929.md` 仍欠但 D 不催**（C2 的实质产出已全落在产物+闸+变异体里，可追溯性已成立；改触发式）。**四个需裁项全裁**：① `transformers` 4.53.3 vs 声明下界 4.57.1 ⇒ **采 C2 建议改判这条闸**（4.57.1 是 lerobot 的**声明值不是实测必要值**，A2 已用 **812/812 张量逐位相同 + 无随机初始化键**证明 4.53.3 下加载正确）⇒ 闸改为「记实测值 + 与加载验证结果绑定」，声明区间保留 `declared_only` 非阻塞，三条牙；② `V-pi05-3` 渠道混用 ⇒ **按格式闭合不重下**（顶层 `channel="mixed"` + 指向 `channel_per_file`）；③ stats 源与 `norm_map` ⇒ 见 85.4，`norm_map` **保留 `QUANTILES`（带 `scale_floor`）**，`IDENTITY+显式缩放` 留作必红分支对照档；④ T-C2-2 补丁 ⇒ **追认批准** + 把三条牙写进闸清单便于 `registry/` 收录。**⇒ C2 队列收敛为两项：T-C2-1 主线 stats（pilot10 path-check 现在就能做）+ T-C2-7。**
- **85.9 EGL 库安装验证 → 交 E，新任务 T-E-EGL-COLDSTART 升 P0**（用户点名 + 用户明说「服务器可能会关闭」）。**已合规部分（D 亲读）**：前缀 `.codex-persist/egl-libs/590.48.01/` 在 NFS 上（331 MB，`10_nvidia.json` 190 B + 全套 `.so`）；`boundary_guard` 前后 + 末态 `ok=true`、`/usr/share/glvnd/egl_vendor.d` **仍只有 `50_mesa.json`** ⇒ **未写系统目录、未 `ldconfig`**；激活权威 `eval "$(bash scripts/e_activate_gpu_render.sh --print)"`（裁定 70）。**D 新查到的一环（E 未报）**：`/root/venvs/pi05_sim` **是符号链接** → `.codex-persist/envs/pi05_sim` ⇒ **venv 本体在 NFS 能跨重启**，A2 与 B2 引的两个路径**是同一个解释器**。**但重启后唯一会断的一环就在这里**：符号链接本身在 `/root` 下不在 NFS 上 ⇒ 重启后极可能消失；`LD_LIBRARY_PATH` / `__EGL_VENDOR_LIBRARY_FILENAMES` 是进程环境，重启后必然为空 ⇒ **现在所有「egl 可用」的结论都建立在当前 shell 会话的环境上，没有一条是冷启动验证过的**。**四项交付，每项都要有牙**：① `env -i` 冷启动自检（重建符号链接 → 激活 → 断言实测 `GL_RENDERER` 含 `NVIDIA` → 任一步失败 `exit≠0`），**必须写进 `docs/infra-gpu-render.md` 顶部**（330 ln `f873baf1bd0e`）让任何线 30 秒自恢复；② `PERSIST_MANIFEST.json`（逐 `.so` sha256 + 字节数 + 符号链接源/目标 + **机器可执行形式**的恢复步骤）；③ **静默回退必须响亮失败（核心牙）**——沙箱副本里把 `10_nvidia.json` 指向不存在的库 ⇒ 实测 `renderer_class` **必须 ≠ `nvidia_gpu`** 且 `exit≠0`（**若 mujoco 静默回退 osmesa，则 92.374 ms/步 = 2.72× 预算 会被当成 7.300 ms/步 ⇒ 整条实时性结论被静默推翻**；裁定 83 §5 规定了口径但**没规定失败要响亮**，本条补上）；④ 核实 `codex-persist watch 120` 守护进程（PID `187229`，已运行 12:13:40）的恢复语义——**恢复什么、多久一次、重启后谁把它拉起来**；若没人拉起，则 ① 是唯一保障，必须写明。**E 的 `e_rawprobe_interference.py` 拒绝闸改触发式**（E 的两条不改理由 D 认可：改它会让裁定 82 §4 的引用第 4 次过期；窗口内不能重跑会造成「代码新、产物旧」）。**E 本轮三份交付全部收下**（`OVERWRITE_EVENT_20260929_2345.md` 136 ln 六项逐条给全 / `GATE_POLARITY_RECHECK.json` 920 ln `e7635c0567b0` 纯离线、根因判 `confirmed` 6/6 / `docs/infra-gpu-render.md` 指针行**原结论一字未改**）；**E 替 D 登记了两处 D 的引用过期**（裁定 82 §4 的 `417 ln e6e3b2c2ad30`、§3 的 `225 ln ffc867dd2e97`）。
- **85.10 用户两问的回答。** ① **「解除只渲单臂不是加重渲染负担嘛？」——顾虑成立，但事实是限制没有解除、主线从来不是「双臂协调」**：用户的「先只渲染单臂」**仍然有效**，作用域由裁定 58.1 限定为 **Piper / Cobot Magic 自有资产渲染线**（`daily_report.md:4720`；该线 `arms=2` 的 5 份历史 JSON 仅留档、脚本已写 `scope="single_arm_only_per_user_directive_20260929"`）；**主线代理 `gym-aloha/AlohaTransferCube-v0` 是 14 维双臂形态**（裁定 41.4，`morphology=aloha_bimanual_14d`），因为形态必须与实机（松灵 Cobot Magic 双臂 ALOHA 类）和数据集（ABC-130k = YAM 双臂）同构，砍臂会**同时**破坏两个对齐；**而且主线任务本身就是单臂的**——v4 `:5` 首场景 =「松灵 ALOHA 类**双臂**平台上的**单臂抓放**，**另一臂暂不参与**」（`:3370`），B2 先导数据实证（正向集终态被 **left** 夹爪握住）⇒ **主线 = 双臂形态 + 单臂动作**；**渲染负担实测 w=1 `7.300 ms` = 预算 21%、w=8 每 worker `10.486 ms` = 31% ⇒ 砍臂省不下有意义的墙钟**。**裁定：维持现状**（可推翻：formal 墙钟成为约束，或用户明确要求主线也单臂 ⇒ 重开，但须先量化形态错配对 S5 可迁移性的代价）。② **「急于确认实机采集窗口有什么意义？」——成立，且 D 早已撤回、本轮零动作**：**裁定 55.5** 已撤回（`decisions_20260929.md:1181`、`daily_report.md:4195`），改**触发式延期**，触发 = **S5 通过 + S6 有方向性证据**（实机是 v4 **P4** `:349`）；**本轮 B2 的先导 10 集让 P1 第一次有了示范数据，但离 S5/S6 还差 S3 训练与 S4 接入 ⇒ 触发条件仍未满足**；用户提的「看其它成熟项目的窗口选取依据」**已预登记为触发时的交付物**（一页纸《实机窗口选取依据》= v4 `:357` 六行报表需现场采到的字段 + 成熟项目口径对照**全标 `external_unverified`** + 需先解决的硬件冲突：夹爪行程三值、J6 的 `1.0456 rad`、30/50 Hz）；**本轮不做文献检索**（裁定 54.4）。

## §18.2 关键路径与链状态（01:2x，**取代 §17.2**）

```
【P0 唯一关键路径】
[B2] S1 formal 40 集（20/方向）—— GPU 窗归 B2（优先级已改：A2 标定窗 > B2 S1 > C2 > E）
  → [C2] 用 formal-40 重算主线 stats（stats_provenance=formal40_bc_source）
       ‖ 并行、现在就能做、不等任何人：
       [C2] pilot-10 path-check stats（stats_provenance=pilot10_path_check，不进 BC）
       [C2] T-C2-7 GPU 窗口登记处（P1，复用 E 的 card_busy()）
       [E]  T-E-EGL-COLDSTART（P0，重启保障）
  → [A2] S4b 接真帧（四路判定独立于 reward==4；超时按 td_only，裁定 83.7-2 仍待用户追认）
  → [A2/B2] S3 BC 训练（硬闸：stats_provenance 必须 = formal40_bc_source）
```
- **本轮关闭**：渲染权威值冲突（§E0 甲案）；`reps≥5`（fork ⑤ 的第二次回来，采丙案）；replay 闸口径；**关键路径阻塞（npz 撤销）**；B2 先导 10 集验收；RR-B2-10/11/12/13；裁定 66 §13.5 路线 + D-H1；用户分叉①（`workers_cap=8`）；用户两问（单臂作用域 / 实机窗口）；C2 的四个需裁项；C2 就位声明核对；E 的三份补交件；`team_form` fps（裁定 83.8 欠项）。
- **01:0x 实测无在跑进程**：GPU `0 MiB / 0%`、`--query-compute-apps` 空、`loadavg 23.56 / 28.22 / 28.54`。**⇒ 重启后无持窗者，第一个起 GPU 进程的线按 §18.1-85.7-① 申报即可。**

## §18.3 D 的文书身份（01:2x 实测，**取代 §17.3**）

| 文书 | 行数 | sha256-12 | as_of |
|---|---|---|---|
| `work/decisions/decisions_20260929.md` | **2177** | **`7bae37a52e69`** | 01:1x（裁定 85 落地后） |
| `daily_report.md` | **5823** | **`4c8339fbb907`** | 01:1x |
| `work/project_parameters.json` | **2233** | **`15b6f6919efc`** | rev14、**113** 条 measurements、**11** 条 revision |
| `rl_harness_supervision/d_context_checkpoint_20260929_2130.md` | 本件（§18 追加后） | 追加前 673 ln `1f0cee197614` | 01:2x |
| `rl_harness_supervision/d_handoff_to_a2_20260929.md` | **920** | **`3d379be4adbf`** | §20 追加后 |
| `rl_harness_supervision/d_handoff_to_b2_20260929.md` | **748** | **`c064819272c2`** | §18 追加后 |
| `rl_harness_supervision/d_handoff_to_c2_20260929.md` | **625** | **`b90df1bf4bd5`** | §15 追加后 |
| `rl_harness_supervision/d_handoff_to_e_20260929.md` | **556** | **`2c50857b83e1`** | §15 追加后 |
| 前像 | `runs/vla/d_ruling_round_20260930_0105/*.before85` | 8 份 | — |

## §18.4 关键产物身份增补（01:2x；**与 §17.4/§16.4 合并使用，冲突以本节为准**）

- **渲染吞吐（权威）**：`runs/infra/e_mainline_calib_20260929/summary_20260929_234814.json`（3816 ln **`32d15f0da3b3`** as_of 23:54:08）⇒ `egl_nvidia` w=1 `env_step_native` = **`136.99` ctrl-steps/s / `7.300 ms`**。**作废**：`summary_20260929_221443.json` 的 `172.32`（`invalidated_probe_polluted`），作废登记 = `INVALIDATED_RUNS.json`（801 ln **`0ccd9b586668`** as_of 23:47:28）。
- **渲染确定性（n=5，权威）**：`RENDER_DETERMINISM_REPS5.json`（2050 ln **`767a2d984a5b`** as_of 00:49:50），生成器 `scripts/e_render_determinism.py`（289 ln **`2449fef70b93`**）。机器现算字段 `verdict.falsification_conditions_ruling_83_3`。
- **延迟（数值带不变、标签变）**：`runs/vla/a2_egl_latency_20260929/latency_quiet_window_rep{2,3,4,5}.json`；生成器 `scripts/a2_egl_latency_remeasure.py`（1171 ln **`7e53558498ab`**，探测器口径见 `:135`）。**rep4/rep5 的 `contaminated=false` 已被 §18.1-85.0 降级。**
- **S1 先导 10 集（权威）**：`runs/vla/b2_sim_demo_bidir_20260930/pilot/demo_manifest.json`（15321 ln **`cc8d5ca62227`** as_of **01:08:10**，`generated_at=00:46:57`，生成器 `d7f77aad7018`、专家模块 `f24d81d35ed8`）+ `pilot/pi05_lerobot/data/chunk-000/file-000.parquet`（**2746 行 / 10 集**，`observation.state[14]`）+ `probe/expert_selfverify_40x2_postpatch2.json`（**`d9dc8b7b9e0e`**，80/80）+ `probe/probe4.json`（**`3eaf525b67ab`**，D-H1 否证）。**注：该 manifest 的 mtime（01:08:10）晚于 `generated_at`（00:46:57）约 21 min 而内容 sha 未变 ⇒ D 只登记不解释（可能是 NFS 属性延迟或 B2 的 `os.utime`）；引用时一律带 `as_of`。**
- **B2 selftest（00:32 重跑版）**：`runs/vla/b2_sim_demo_bidir_20260930/selftest/demo_manifest.json`（`generated_at=00:33:06`，16/16 闸 PASS，`preflight_gpu_guard.ts=00:32:06` / `nvidia_smi_gpu_verbatim="0, 0, 37"`）。**00:21–00:26:58 那版已灭失（§18.1-85.6-①）。**
- **C2**：`harness/norm_contract.py`（566 ln `9e69ee487a9f`）；`scripts/c2_build_norm_stats.py`（509 ln `fcfb72a88c92`）；`harness/queue_td_learner.py`（661 ln **`afc9ebb92621`** as_of 21:28:51，T-C2-2 补丁在 `:145-149`）；探针 `runs/vla/c2_obs_key_whitelist_20260929/probe_20260929/probe_main.json`；守卫 `scripts/c2_driver_output_guard.py`（690 ln **`6cc7b148295b`** as_of 23:11:07）；审计 `docs/c2_gate_polarity_audit_20260929.md`（285 ln `768d49409d76`）；就位声明 `docs/c2_task_selfintake_20260929.md`（184 ln `e1c99b50d45a`）。
- **E**：`GPU_YIELD_INCIDENT_2358.json`（三网修法 + 牙，`fix_applied.verification`）；`OVERWRITE_EVENT_20260929_2345.md`（136 ln）；`GATE_POLARITY_RECHECK.json`（920 ln `e7635c0567b0`）；`RAW_PROBE_INTERFERENCE.json` 现行版 = gen-at 23:44:25 / 生成器 `74e8afe88a4d`（旧版 `stale_unrecoverable`）；`docs/infra-gpu-render.md`（330 ln `f873baf1bd0e`）。
- **git**：HEAD 仍 **`c422659`**，工作区 **56 项脏**（含 D 的裁定 85 三份文书、参数表 rev14、四份回流单、A2/B2/C2/E 的新脚本与文档）。**单写者 = B2（裁定 49.6），D 从不提交。`runs/` 被 `.gitignore:12` 排除 ⇒ 证据只在 NFS。**
- **仍缺**：`docs/c2_handoff_to_d_20260929.md`（**D 本轮改为不催**）；`docs/c2_a_line_freeze_inventory_*`（降 P2）；`runs/vla/c2_obs_store_image_probe_*`（降 P2）。

## §18.5 重启后 D 的接续步骤（01:2x，**取代 §17.5**）

1. **核身份**：`sha256sum` 对 §18.3 的文书 + §18.4 的产物；不符 ⇒ 查是否被截断/覆写（`find runs docs -name '*before*' -newermt '-6 hours'`）。
2. **查卡与窗口归属（口径已变，别再用旧法）**：`nvidia-smi --query-compute-apps` **单独不足以判卡空**（§18.1-85.0 的新红线）。**必须三网**：① compute-apps；② `for p in /proc/[0-9]*; do ls -l $p/fd 2>/dev/null | grep -q '/dev/nvidia' && echo $p; done`；③ 扫 `/proc/*/cmdline` 找 `scripts/{a2,b2,c2,e}_*` 或 GPU 意图关键字。**再读 `memory.used`——若非零而三网皆空，按新自查项 `unexplained_nonzero_reading_must_block_clean_claim` 处理，不得判「卡空」。** 优先级 = **A2（已申报标定窗）> B2（S1）> C2 > E**。若 T-C2-7 登记处已落地，改读 `runs/infra/gpu_window_ledger.jsonl` 的 `status`。
3. **B2（关键路径持有者）**：formal 40 集是否落地（`runs/vla/b2_sim_demo_bidir_20260930/formal/`）；`git log --oneline -1` 是否离开 `c422659`、`git status --porcelain | wc -l`（本轮 56）；replay 闸是否改判 + **三条牙是否齐**（特别是「篡改像素保留状态 ⇒ 仍绿」这条专属牙）；`contaminated_by_cotenant` 是否三网化 + 三条牙；`--trash` 是否纳入 `demo_manifest.json`。
4. **C2**：pilot-10 path-check stats 是否落地（查 `stats_provenance=pilot10_path_check`，**并确认它没进 BC**）；`--s1-lerobot` 是否实现 + dtype 口径声明；`norm_contract` 的 provenance 硬闸 + 牙；`mainline_status.json` 是否重生成；T-C2-7 登记处 + 三条牙；裁定 78.11 审计勘误。
5. **E**：T-E-EGL-COLDSTART 四项（**特别是第③项「静默回退必须响亮失败」的核心牙**）；`docs/infra-gpu-render.md` 顶部是否已写冷启动命令；`PERSIST_MANIFEST.json`。**若服务器真的重启过 ⇒ 第一件事就是跑 E 的冷启动自检，再谈任何 GPU 测量。**
6. **A2**：闸与采样器是否升级三网（红线）；三网清洁证书的 rep 是否落地（落地 ⇒ `provisional_pending_three_net_certificate` 解除、caveat 可摘）；两份 `WHY_ARCHIVED.md` 绝对路径。**不要重跑整个 quiet-window（数值带已确认不变）。**
7. **治理**：任何重大裁定后 append `daily_report.md` 的 D 段 + 更新本断点（**新开 §19，声明取代关系**）+ 参数表加 rev。**扫十二类缺陷**：恒真闸 / 恒红闸（83.2）/ 跨口径搬用 / 分量之和超过实测总量（84.4）/ 否定型主张未枚举 / 闸缺 `applies_when` / 自检未执行取数路径 / 假绿 / **引用 sha 过期或引用不完整（含散文限定割裂，85.0）** / 记录但未上报 / 注入器未过闸（83.0）/ **探测器盲区（85.0）**。**另加三条 D 自查**：`unexplained_nonzero_reading_must_block_clean_claim` / `invalidation_registry_must_be_grepped_before_adopting_authoritative` / `d_assertion_requires_artifact_or_tag`。**判据设计侧再加一条**：任何新立的可推翻条件都要过 `criterion_must_have_magnitude_floor`（连续量必须带量级下限）。

## §18.6 需用户裁的分叉（01:2x，**取代 §17.6**；**3 项挂起 + 2 项待追认，本轮关闭 1 项**）

**待追认（D 已自确并写了可推翻条件）**
1. **裁定 85.2-2 的丙案**：采集后端 = **egl**、osmesa 保留为逐位对照后端、像素侧走容差、replay 硬判据只剩状态逐位。**按 83.3 原文本应回用户裁**（条件③ 确实触发了），D 依 21:2x 授权自确。可推翻：用户要求逐位可复现的采集（像素级回归 / 对外可复现基准）⇒ 改甲案双后端并接受 S1 墙钟 ×12.64；或后续实测 `frac_diff_px>0.1%` / `max_abs_diff>2` ⇒ 自动失效回用户裁。
2. **裁定 83.7-2 的 `timeout_isolation_scope = td_only`**（沿用，仍未追认）。可推翻：若 v4 原文明确禁止把 TimeLimit 截断轨迹用于 BC（任一线给出文件-身份三元组 + 行号）⇒ D 立即回退 `both_isolated`。

**仍挂起**
3. 是否向平台申请 `NVIDIA_DRIVER_CAPABILITIES=graphics`（D 已降级为非阻塞改善项；**申请动作本身要用户点头**）。
4. 是否投入测试 **bf16**（改数值口径 ⇒ 另立 `representation_version`；**也是会让裁定 84.7「实时闭环」声明失效的因素之一**）。
5. 是否给 E 一个 **5 分钟稳态并发窗口**（D：现在不给；E 本轮 `--cotenant` 继续禁用；共租档挂起至 formal 落地）。

**本轮关闭**
- ~~分叉①（`workers_cap` 4 vs 8）~~ ⇒ **裁定 85.1-3 关闭为 `8`**（「近线性到 8」撤回，依据改为「聚合 +48% 且每 worker 延迟 10.486 ms = 预算 31% 仍在预算内」）。可推翻：formal 在 w=8 下任一 worker 每步 > 34.0 ms，或 `nr_throttled` 增速较 w=4 高 > 3× ⇒ 降回 4。
- ~~fork ⑤（wrist >1% 是否改 osmesa 采集）~~ ⇒ 裁定 83.3 曾解除；**n=5 触发条件③ 后它按 D 自己的规则回来过一次，本轮由裁定 85.2 以丙案再次关闭**（判据同时被重修，不会再被 1 LSB 触发）。
- ~~用户两问（解除只渲单臂 / 实机采集窗口）~~ ⇒ **裁定 85.10 回答完毕，均无需用户再动作**（单臂限制**没解除**；实机窗口**早在裁定 55.5 已撤回**，触发 = S5+S6）。

## §18.7 硬约束（仓库级，不变）

不用 `rm`（→ `/workspace/mnt/sppro/yhzhang91/recycle_bin/`）；**永不碰** `/workspace/mnt/sppro/yhzhang91/datasets`；`RL_Harness_v4_20260924/` 只读；run 目录按线前缀；**每个吞吐/延迟数字都带 `loadavg` 三点 + `nr_throttled` 对**（cgroup 12 核，`nproc=112` 说谎）；外部事实标 `external_unverified`；`declared_only` 永不阻塞；**跨 (venv/后端/模型/env/DT/协议/负载/run) 移植禁止**（但**同口径去缺陷重跑可取代旧值**，裁定 85.1 的 `caliber_transplant_ban_scope`）；闸须双向有牙 + `applies_when` + **绿证人** + **量级下限**；覆写自己的产物 ⇒ 前像 + sha256-12；**不写系统目录、不 `ldconfig`**；**GPU 优先级 A2 > B2 > C2 > E（裁定 85.7 改）**、>10 min 须申报、**占卡判据必须三网**；**D 从不 git 提交（B2 单写者）、从不写实现代码**；heredoc 内容含反引号/`$( )`/`$VAR` 时用 **引号式 `<<'EOF'`**；v4 只用五个状态词；v4 引用须文件-身份三元组；**所有 sha 引用带 `as_of` mtime**；**「记录在产物里 ≠ 已上报」**（裁定 50.1）；**注入器起跑前必须过闸**；**渲染口径以实测 `GL_RENDERER` 为键**；**引机器字段必须同引其旁边的散文限定**（裁定 85.0）。

## §18.8 用户偏好（不变）

中文；证据优先（`file:line` + 身份三元组 + `as_of`）；分叉由用户决（D 自确时必写可推翻条件）；共享文档只追加；每轮更新以「D 等各线什么 + 需用户什么」收尾；**D 的自我更正必须显式并升为常设规则**——累计 **12 次同型错误**（本轮 +2：第 11 次「立红线却留着它污染的数字 + 用移植禁令挡掉同口径去缺陷重跑」、第 12 次「只读机器字段没读旁边的散文限定」），另有第 13 处更正（图像键名写错）不计入同型；**保护「下位可以纠正 D」的通道**——累计 **7 次**（本轮：B2 的 probe4 否证 D-H1、E 的 §E0 推翻权威值、E 的 §E1 指出窗口条款漏洞、B2 的 RR-B2-11 指出键名错；**本轮 6 条新纪律里有 4 条是下位线的实测逼出来的**）；D 自创的闸/裁定不经 v4 对撞不得获得事实地位；**服务器可能关闭 ⇒ 每次重大裁定后更新本断点（现在到 §18）**。

---

# §19 【D 上下文检查点 · 增补于 2026-09-30 02:3x · 取代 §18 的部分内容】

**本节身份**：D。**重启后请先读 §19.0（恢复），再读 §19.2（关键路径），再读 §19.4（§18 的作废清单），最后才回头读 §1–§17。**
**before 影像**：`runs/vla/d_ruling_round_20260930_0210/d_context_checkpoint_20260929_2130.md.before19`（772 ln `27fdccd0d0f6`）。
**本轮 D 落盘**：裁定 87（`decisions:2379-2689`）+ 裁定 88（`decisions:2691-2845`）+ 四份接单附则 + `daily_report.md` 的 §D87/§D88。

## §19.0 【重启恢复说明 · 临时版 · 裁定 88.4-2 授权 D 发布】

> **这一节的存在理由**：用户已明说**服务器可能关闭**。E 的权威恢复块要等它修完一个采样竞态才能写进 `docs/infra-gpu-render.md`；**D 不允许"等修完"造成恢复指引缺位**，故在此发布临时版。E 修完后会在 `docs/infra-gpu-render.md` 最顶写权威版，并点名本节已被取代。

### 19.0-1 一条命令恢复 GPU 渲染（EGL）
```
env -i /bin/bash /workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/scripts/e_coldstart_gpu_render.sh
```
- **`env -i` 是必需的**：新规则 `restart_recovery_must_not_depend_on_interactive_shell`（裁定 87.1-3）。E 已实测该形可跑通 C1–C3。
- 它做四件事：**C1** 链路前提检查（NFS 前缀 `.codex-persist/egl-libs/590.48.01` + venv 本体 + base 解释器 `/opt/conda/bin/python3.11` 都在）；**C2** 重建 `/root/venvs/pi05_sim` → `.codex-persist/envs/pi05_sim` 的**软链接**；**C3** 激活后端（`MUJOCO_GL=egl`、ICD=前缀里的 `10_nvidia.json`、`LD_LIBRARY_PATH=前缀`）；**C4** 在**独立子进程**里实测 `GL_RENDERER` 并断言含 `NVIDIA`。
- **零系统写入**：`boundary_clean_no_system_write = true`（E 的 v1/v2 两版都实测）；不 `ldconfig`、不写 `/usr/share`。

### 19.0-2 什么会活下来、什么会死（E 实测，`chain_verify`）
- **活得下来（NFS `.codex-persist/`，`survives_container_rebuild=true`）**：**venv 本体**（`envs/pi05_sim`）、**EGL 驱动前缀**（`egl-libs/590.48.01`，34 个 .so / 339,337,693 B / 清单 `PERSIST_MANIFEST_v2.json` `da599a4c5648`）、恢复工具（`bin/`）、`~/.codex` 的镜像（`backup/`）、**以及整个仓库与 `runs/`**。
- **会死（运行期写入的部分）**：**`/root/venvs/pi05_sim` 这个软链接**、**指向 NFS 前缀的 ICD vendor json**。
- **粒度待 v2 定性（`provisional_pending_e_v2`）**：D 在裁定 87.1-3 曾把 `/root`、`/opt/conda`、`/usr/share/glvnd/egl_vendor.d` 一并说成"overlay ⇒ 一律死"，**E 自曝 v1 的 `fs_of()` 未区分「镜像只读层」与「运行期可写层」⇒ 那个粒度说法过于粗糙**。正确区分应是：**镜像里本来就有的（如 `/opt/conda`）在同镜像重建后会回来；运行期写进去的才会死。**
- **不变的结论**：**要恢复的正是运行期写入的那两样（软链 + vendor json），而 `codex-persist watch`（PID 187229）只单向镜像 `~/.codex` → NFS `backup/`、`cmd_watch` 循环里只调 `cmd_snapshot`、从不写回本地；恢复只发生在 `cmd_restore()`，由 `bootstrap` 或 `.bashrc` hook 的 `cmd_auto()` 触发。** ⇒ **若重启后没有交互式 shell 去 source `.bashrc`，就没有任何东西会自动恢复。**

### 19.0-3 【关键】在竞态修好之前，**权威判据是实测 `GL_RENDERER`，不是 exit code**
- **已知缺陷（E 自曝并定位到行）**：`scripts/e_gpu_egl_verify.py:389-394` 的采样是 **`time.sleep(1.0)` 之后**才 `while proc.poll() is None` 采样；当渲染子进程活得比 1.0 s 短（本轮实测 `wall_s = 1.001`）⇒ **采样窗为空**（`gpu_samples` 字段整个不存在）⇒ **"没采到"被当成"没有 fd / 没有占用"** ⇒ L5 / L5b / S2 三条**占用旁证**腿同时读到"空" ⇒ **自证件判 `verdict=fail` / `exit 1`，而 GPU 渲染事实上是好的**。
- **本轮实测的反证**：同一臂的 `GL_RENDERER = NVIDIA A800-SXM4-80GB/PCIe/SSE2`、`GL_VERSION = 4.6.0 NVIDIA 590.48.01`、渲染子进程 `ok=true`（400 帧 @64×64、`fps 2243`、`image_mean 75.73`）、`libnvidia-eglcore`/`libEGL_nvidia` 确实加载。
- ⇒ **临时口径（D 定）**：**判断"冷启动后 GPU 渲染是否可用"，以实测 `GL_RENDERER` 是否含 `NVIDIA`（+ `renderer_class == nvidia_gpu`）为权威，不以脚本 `exit code` 为权威。**
- **为什么必须写这一条**：那条命令自己的文案是「**exit≠0 ⇒ 不要采集任何标 egl 的数字**」。**若不写本条，重启后的运维会被一个假红卡死整条主线。**
- **边界（防滥用）**：本临时口径**只适用于 `tooth_baseline` 臂的占用旁证腿（L5/L5b/S2）**。**不适用于** `tooth_mutant` 臂（坏 ICD ⇒ `exit != 0` 是判据本身，且已实测通过），**也不适用于** B2 的渲染臂判据（那一条本来就以 `renderer_class` 为准，与本口径一致）。
- **可推翻条件**：E 修好竞态后重跑 `baseline`，**若仍 `exit != 0` ⇒ 本临时口径作废**，回到"exit code 为权威"，并按真缺陷处理。

### 19.0-4 若重启发生，D 的接续动作（照顺序）
1. 读本节 + §19.2 + §19.4。2. 跑 §19.0-1 的命令。3. 按 §19.0-3 判读结果（**看 `GL_RENDERER`，不看 exit code**）。4. 三网实测卡状态（**绝不仅用 `--query-compute-apps`**，它对 EGL 图形负载是盲的 —— 裁定 85.0 的新红线 `card_busy_detector_must_include_fd_and_cmdline_nets`）。5. 从 `daily_report.md` 的**当前尾部**读起（**不得用缓存偏移**），确认各线是否有未销账的窗口申报。6. 核 §19.7 的"D 等"清单，逐线追。

## §19.1 本轮（裁定 87 + 88）发生了什么 —— 六件事

1. **【最重】C2 在真数据上把主线档测红了，这是实质发现，不是缺陷。** held-out（集 `[4,9]`、`n_build=2196 / n_eval=550`）上：`clip_ratio` 最差维 12 = **0.0927273**（cap 0.01 的 **9.3×**）、非法 bin `dims=[7,12]`、饱和 **3 维 `[5,7,12]`**（`above_1=33`、`below_-1=100`、`abs_max_normalized=1.0849`）。**根因实测** = `widen_to_cover()` 的 `must_cover=(start_pose, build_frames)`，**按构造只保护 build 帧**。⇒ **裁定 87.3：`must_cover` 改为覆盖「声明物理区间」，附三条件（两臂变异体 / 分辨率只登记不定阈值 / 上限不赦免）。**
2. **C2 在交付绿之前自查出 3 个自线缺陷，其中缺陷 10 是"牙的名与实不符"**：主线档**根本没传 `eval_frames`** ⇒ `Td2/Te2` 名义叫 held-out、实质是 build 帧重测 ⇒ **若没修，主线档会交出一份"全绿"的 stats**。⇒ **新规则 `gate_name_must_match_gate_semantics` + 新缺陷类 ⑮。**
3. **E 自曝两件真缺陷**：① 让位闸把 DET-480 的 5 个 rep 全跳过，产物却写 **`all_bitwise_deterministic: true`**（空集上的平凡真）；② **采样窗竞态**导致 P0 反向牙**假红**（§19.0-3）。⇒ **新红线 `absence_of_measurement_is_not_measurement_of_absence`（三态：阳性/阴性/未测得）+ 新常规则 `aggregate_over_empty_set_must_be_null` + 新缺陷类 ⑯。** 本轮已累积**六个同型实例**，其中 **C2 的缺陷 11 与 B2 的 `n_unjudged` 是本仓已有的正确范式**（清单 `decisions:2762-2772`）。
4. **B2 交出本仓最强的一组牙（0/3/0，特异性由机器判定）**：`teeth1_green_witness` PASS/0红 · `teeth2_state_1lsb` RED/**恰好 `G4_replay_reproduces_bitwise` 一颗** · `teeth3_pixel_only` PASS/0红。**1 ULP（`np.nextafter`，≈1e-16）证明 G4 是 `np.array_equal` 逐位、没有偷偷带进 `atol/rtol`** —— 比上一棒的 `1e-3` 强一个层级。`mutation_verdict_*.json` 的 `expected_must_go_red` / `observed_red_ids` 逐字相符、`missed_red=[]`、`extra_red_beyond_expected=[]`、`all_expected_red_caught=true`。
5. **三网红线在 A2 与 B2 两侧都已落地，且都是复用 E 的实现、零重造**；**并在 02:22:37 与 02:26:11 两次当场自证**（compute-apps **空**、而 fd 网抓到 B2 的 PID）。**两线在 02:17 同分钟申报窗口的情况下自行完成让路协调、零抢卡** ⇒ 裁定 85.7 的窗口机制首次实战自证。
6. **D 自己的两处更正**：① 裁定 82.2 的契约文本含两个互斥半句（夹爪 `1.0` vs `c2_collect_env_states.py` 实测 `0.91001`，差 **9.889%**）⇒ **D 的第 14 号同型错误**，由 B2 登记 `OPEN_needs_d_ruling` + C2 拒绝自决发现（**下属纠正 D 第 9 例**）；修法 = **契约不得硬编码任何数值**，各维范围一律取主线同源实测（npz `physical_range_effective`）。② §D87 抬头写的追加前身份不是写入时刻的真值 ⇒ 收紧自检：**任何写进散文的 `(行数, sha, mtime)` 三元组必须在写入动作的同一时刻由机器取值。**

## §19.2 【关键路径 · 取代 §18.2 与裁定 87.13 的路径图】

**02:37 的实况**：**B2 的 formal-40 已起跑**（fd 网持有者 PID `402753`、`0 % / 12 MiB`、compute-apps **空** ⇒ 正是 12 MiB 签名）；**C2 正在实现 ①**（`scripts/c2_build_norm_stats.py` 02:28:43 已达 **1616 ln `a8d8d6e2598e`**、`harness/norm_contract.py` **775 ln `fed61d0d0e79`**）；**E 正在修竞态**（`scripts/e_gpu_egl_verify.py` 02:28:19 **640 ln `541c6dc916b9`**、`scripts/e_coldstart_gpu_render.sh` 02:30:03 **121 ln `925ec9068327`**）。**三线并行、零写入面冲突。**

```
[进行中] [B2] S1 formal-40（20/方向）—— 窗已开，≈30 min 墙钟 / ≈6 min GPU / ≈0.22 GiB
              补偿控制（裁定 88.5-1 的一次性豁免）：跑完立刻核 manifest 两端点
              renderer_class_at_start / _at_end / arm_stable
              任一非 nvidia_gpu 或两端不一致 ⇒ 整批 environment_invalid，不通知 C2、不进 BC
   → [B2] formal npz（同一导出器 scripts/b2_export_states_14d.py、MUJOCO_GL=disable、双跑 sha 一致、
          n_episodes=40 + n_frames + sha256）→ §B2-13 销账行 → 通知 C2 可重算
   → [C2] formal-40 stats（stats_provenance = formal40_bc_source）
[进行中·并行] [C2] ① must_cover → 声明物理区间 + 条件a 两臂变异体 + 条件b 分辨率只登记 + 条件c 上限不赦免
              + mainline_status.json 补 n_episodes:10 + clip_ratio_structural_floor 加"①后应≈0"注解
              + 契约文本按裁定 87.6 改用（D 已裁，可直接落）
[进行中·并行] [E] ① INVALIDATED_RUNS.json 登记（先于其它一切）② 竞态根因修（纯 CPU）
              ③ baseline 臂重跑（秒级 GPU，插 B2 formal 的批次间隙）④ COLDSTART_VERIFIED + stages_executed
              ⑤ docs/infra-gpu-render.md 顶部权威恢复块（并点名 §19.0 已被取代）⑥ DET-480（P1，清洁卡）
   → [A2] S4b（等 C2 的 formal stats；需上卡 ⇒ 申报窗；不被 env_gym_aloha 的牙阻塞）
   → [A2/B2] S3 BC（硬闸：stats_provenance == formal40_bc_source）
[P2] [A2] 三网清洁证书 rep（B2 formal 之后，≈3 min 估算）
```

**§19.2 的可证伪检查点（D 预登记，用来判"① 是否真解决了问题"）**：formal-40 的 stats 在采 ① 后，`Td2_clip_heldout` 对**物理合法**状态应为 **0**、`Te2` 应为 `dims=[]`、`Tsat` 应为 `n_dims_saturated=0`。**若三者任一非零 ⇒ 数据里存在超出声明物理区间的状态 ⇒ 判红、不许再展宽、转查采集器与契约**（裁定 87.3-2 条件 c）。
**§19.2 的可推翻条件（D 自设）**：若 ① 把任何主线维的 `bins_occupied_median` 压到 **< 8**，D 改采**逐维覆盖策略**（只对真正产生非法 bin 的维 `[5,7,12]` 与近常量维 `[3,10]` 用 ①，其余用 ②）。

## §19.4 【§18 的作废/更正清单】—— 重启后不要照 §18 行动

| §18 的内容 | 现状 |
|---|---|
| §18.1 的 85.4 条目（"npz 未交付"） | **已在裁定 86.0 撤回**：npz 于 01:08:09 早已交付（`5c4710426db2`）。**D 的第 13 号错误。** |
| §18.2 的关键路径图 | **作废**，用 §19.2。 |
| §18.3 的 b2 handoff sha `c064819272c2` | **更正为 `c064819272ce`**（裁定 86.8；手抄错误）。**现行 b2 handoff 已是 818 ln `d8d1aeb0381f`。** |
| §18 全节的四份 handoff 行数/sha | **全部过期**，用 §19.3 的表。 |
| 裁定 87.0 与 `daily_report.md` §D87.2 的排窗顺序 | **作废**（裁定 88.0-2）：两线在 D 落笔后 12 分钟内自行跑完并销账。**新顺序见 §19.2 / 裁定 88.5。** |
| 裁定 87.1-3 的"overlay 路径一律死" | **粒度降为 `provisional_pending_e_v2`**（裁定 88.4-3）；**结论不变**（没有东西会自动恢复）。 |
| `runs/infra/e_mainline_calib_20260929/RENDER_DETERMINISM_TEAM480x640_EGL_REPS5.json`（598 ln `ba1d1f56ab93`） | **D 直接判定 `invalidated_vacuous_all_reps_skipped`**（裁定 88.5-1）：5 个 rep 全被让位闸跳过、汇总在空集上算出 `all_bitwise_deterministic: true`。**任何文书不得引用它作为 480×640 的登记带。E 须把它登进 `INVALIDATED_RUNS.json`（D 02:2x 实测该表 802 ln、两个关键词均 0 命中 ⇒ 尚未登记）。** |
| 渲染权威值 | **136.99 ctrl-steps/s**（7.300 ms/step = 34 ms 预算的 21%）@ `summary_20260929_234814.json` 3816 ln `32d15f0da3b3` as_of 23:54:08。**172.32 = `invalidated_probe_polluted`，不得引用。** |

## §19.5 账目状态（截至裁定 88）

- **D 同型错误：14**（本轮 +1 = 裁定 87.6 的契约文本自相矛盾）。**另有记账类更正不计入**：§18.3 的 sha 手抄、WHY_ARCHIVED 台账、§D87 抬头的身份串。
- **下属纠正 D：9**（本轮 +1 = 同件，B2 登记 OPEN + C2 拒绝自决）。
- **D 近失：3**（#1 差一点照 `all_teeth_proven=true` 验收 P0；#2 把 E 自曝精度不足的字段升格为常量事实；#3 排窗裁定未写作废条件、12 分钟内被事实超越）。**近失不计错误账，但每条都升为常设自检。**
- **缺陷类扫描：16** —— ①恒真闸 ②恒红闸 ③跨口径搬用 ④分量之和超总量 ⑤否定型主张未枚举 ⑥闸缺 applies_when ⑦自检未执行取数路径 ⑧假绿 ⑨引用过期/不完整 ⑩记录但未上报 ⑪注入器未过闸 ⑫探测器盲区 ⑬否定型主张未复查 ⑭变异体无特异性 **⑮牙的名与实不符（`gate_name_semantics_mismatch`）** **⑯空集上的平凡真（`vacuous_truth_over_empty_set`）**。
- **本轮新增纪律**：**红线** `absence_of_measurement_is_not_measurement_of_absence`；**常规则** `partial_delivery_must_not_carry_a_whole_delivery_boolean`（87.1-2）、`gate_name_must_match_gate_semantics`（87.2-1）、`rule_transplantable_value_not_transplantable`（87.7）、`restart_recovery_must_not_depend_on_interactive_shell`（87.1-3）、`aggregate_over_empty_set_must_be_null`（88.3-2）；**D 自检** `a_top_level_boolean_must_be_read_against_the_stages_actually_executed`、`machine_field_adopted_as_constant_fact_requires_producer_confirmation`、`scheduling_ruling_must_state_its_expiry_condition`、`(行数,sha,mtime) 三元组须在写入动作的同一时刻由机器取值`。
- **量化事实（写进参数表的依据）**：主线示范数据的近常量维只有 **2 个**（`[3,10]`，两个 forearm_roll），env 诊断档 hold 相是 **10 个** ⇒ **env/YAM 在"哪些维几乎不动"上完全不代表示范数据** ⇒ 裁定 52/69 自此有量化依据。

## §19.6 用户分叉（3 项待追认 + 3 项挂起；本轮新增 0 项分叉、2 项技术性自确）

**待追认**
1. `timeout_isolation_scope = td_only`（裁定 83.7-2；A2 已核 v4 可推翻条件**未触发**）。
2. **丙案**（85.2-2：采集 egl + osmesa 保留为逐位对照后端 + 像素走容差 + replay 硬判据只剩状态逐位）—— 现已**两腿实测 + B2 的 1 ULP / pixel-only 两颗专属牙**。
3. **§87.3 采 ①**（`must_cover` → 声明物理区间）—— **本轮唯一改变主线数据表示的裁定，会换 `representation_version`**。可推翻条件见 §19.2。

**挂起（本轮未动）**：`NVIDIA_DRIVER_CAPABILITIES=graphics` 的应用 · bf16 测试（换口径 ⇒ 会作废裁定 84.7 的实时性主张）· E 的 5 min 稳态并发窗（**D 判：现在不要**）。

**本轮 D 技术性自确（均已附可推翻条件，属授权范围）**：① §19.0-3 的临时权威判据口径（`GL_RENDERER` 优先于 exit code）；② 裁定 88.5-1 对 B2 formal 的一次性豁免 + 补偿控制。

**已闭合、无需用户动作**：`workers_cap=8` · 单臂渲染范围**从未解除**（Piper 线仍单臂；主线 `AlohaTransferCube-v0` 是 14 维双臂形态、**单臂动作**，v4:5）· 实机采集窗口已在裁定 55.5 撤回、**触发条件（S5 通过 + S6 方向性证据）仍未满足**。

## §19.7 D 在落笔这一刻等什么（重启后按此逐线追）

| 线 | 待办 | 级别 | 落笔时状态 |
|---|---|---|---|
| **B2** | formal-40 → 补偿控制三字段 → formal npz（`n_episodes=40`）→ §B2-13 销账行 → 通知 C2 → `mutation_tooth_ok` 的实际路径 → git 代提交 | **P0 关键路径** | **已起跑**（PID `402753`，02:37 实测） |
| **E** | `INVALIDATED_RUNS.json` 登记（**先于一切**）→ 竞态根因修 → `baseline` 重跑 → `COLDSTART_VERIFIED` + `stages_executed` → `docs/infra-gpu-render.md` 顶部权威恢复块 → DET-480（P1） | **P0 / P1** | **正在改件**（`e_gpu_egl_verify.py` 02:28:19） |
| **C2** | ① + 三条件 → `n_episodes:10` → floor 注解 → 契约文本改用 → formal-40 stats 重算 → 行数按档参数化 + `gate_name` 牙 + `env_gym_aloha` 牙声明 + 3 变异体（P1）→ T-C2-7（P1，明确排在后面） | **P0（并行）** | **正在实现**（生成器 02:28:43 达 1616 ln） |
| **A2** | **无即时待办**（债务 ① 三网**关闭**、债务 ③ WHY_ARCHIVED **销账**）；② 三网清洁证书 rep 排 B2 formal 之后；产物补 `contamination_arm` | **P2** | 空闲 |

**给重启后的 D 的三条提醒**
1. **读 `daily_report.md` 从当前尾部读起**，不要用缓存偏移；**否定型主张在落裁定前必须重取一次**（裁定 86.0 的教训：D 曾因"find 空结果"过期而误判 npz 未交付）。
2. **GPU 状态一律走三网**（compute-apps + `/proc/*/fd` 的 `/dev/nvidia*` 持有者 + `/proc/*/cmdline`）。**`--query-compute-apps` 对 EGL 图形负载是盲的** —— 本轮 02:22:37 与 02:26:11 两次当场复现（B2 在卡上、compute-apps 空、fd 网看得见、`12 MiB`）。
3. **排窗裁定必须写作废条件**；**任何写进散文的身份三元组必须在写入的同一时刻由机器取值**。

### §19.3 身份表（机器取值，2026-09-30 02:36:03 CST，遵守 `sha_must_be_copied_by_machine_not_transcribed`）

| 路径 | 行数 | sha256-12 | as_of mtime |
|---|---|---|---|
| `work/decisions/decisions_20260929.md` | 2845 | `b62e7a7aa02e` | 2026-09-30 02:32:34 |
| `daily_report.md` | 6436 | `4aeecfc97089` | 2026-09-30 02:35:29 |
| `work/project_parameters.json` | 2233 | `15b6f6919efc` | 2026-09-30 01:38:07 |
| `rl_harness_supervision/d_context_checkpoint_20260929_2130.md` | 772 | `27fdccd0d0f6` | 2026-09-30 01:42:45 |
| `rl_harness_supervision/d_handoff_to_a2_20260929.md` | 977 | `603fce7b8567` | 2026-09-30 02:21:14 |
| `rl_harness_supervision/d_handoff_to_b2_20260929.md` | 818 | `d8d1aeb0381f` | 2026-09-30 02:18:34 |
| `rl_harness_supervision/d_handoff_to_c2_20260929.md` | 717 | `a40b1ac2775f` | 2026-09-30 02:20:11 |
| `rl_harness_supervision/d_handoff_to_e_20260929.md` | 619 | `9d6c54e67586` | 2026-09-30 02:17:28 |
| `scripts/b2_s1_generate_dataset.py` | 4333 | `b6af48fc6d58` | 2026-09-30 02:28:44 |
| `scripts/c2_build_norm_stats.py` | 1616 | `a8d8d6e2598e` | 2026-09-30 02:28:43 |
| `harness/norm_contract.py` | 775 | `fed61d0d0e79` | 2026-09-30 01:55:24 |
| `scripts/a2_egl_latency_remeasure.py` | 1820 | `7ead22591a63` | 2026-09-30 01:47:54 |
| `scripts/e_egl_coldstart.py` | 548 | `c59c02162fec` | 2026-09-30 02:17:53 |
| `scripts/e_coldstart_gpu_render.sh` | 121 | `925ec9068327` | 2026-09-30 02:30:03 |
| `scripts/e_gpu_egl_verify.py` | 640 | `541c6dc916b9` | 2026-09-30 02:28:19 |
| `scripts/b2_export_states_14d.py` | 986 | `8708d4a84d7f` | 2026-09-30 01:07:49 |
| `runs/vla/b2_states_14d_20260930/pilot5/states_14d.npz` | 851 | `5c4710426db2` | 2026-09-30 01:08:09 |
| `runs/vla/c2_norm_contract_20260929/mainline_s1_pilot5/matrix.json` | 10770 | `261dbc2192c1` | 2026-09-30 01:39:40 |
| `runs/vla/c2_norm_contract_20260929/mainline_s1_pilot5/mainline_status.json` | 40 | `c15b1b272479` | 2026-09-30 01:39:40 |
| `runs/infra/e_egl_coldstart_20260930/COLDSTART_EVIDENCE_v2.json` | 555 | `b6964d31e04c` | 2026-09-30 02:18:56 |
| `runs/infra/e_egl_coldstart_20260930/PERSIST_MANIFEST_v2.json` | 771 | `da599a4c5648` | 2026-09-30 02:18:53 |
| `runs/infra/e_mainline_calib_20260929/RENDER_DETERMINISM_TEAM480x640_EGL_REPS5.json` | 598 | `ba1d1f56ab93` | 2026-09-30 02:22:38 |
| `runs/infra/e_mainline_calib_20260929/summary_20260929_234814.json` | 3816 | `32d15f0da3b3` | 2026-09-29 23:54:08 |
| `runs/vla/b2_sim_demo_bidir_20260930/mutation_verdict_replay-state-1lsb.json` | 2632 | `3c5cb593adee` | 2026-09-30 02:21:32 |
| `runs/vla/b2_sim_demo_bidir_20260930/mutation_verdict_replay-image-pixel-only.json` | 2673 | `b852b6bb77ad` | 2026-09-30 02:22:50 |
| `harness/vla_runtime.py` | 932 | `1a75f6181a36` | 2026-09-30 00:44:01 |

**git**：HEAD `4ff31bd`、脏项 26（B2 单写者，D 不 commit）。
**GPU 三网（02:37:13 实测）**：compute-apps 0 条 / 0 %, 12 MiB / fd 网持有者 PID = `402753,` / loadavg 7.10 6.28 10.25 / nr_throttled 15574（nr_periods 583922、quota 12 核）。

---

# §20 【D 上下文检查点 · 增补于 2026-09-30 03:1x · 重启后请从本节读起，它取代 §19 的三处内容】

**本节身份**：D。before 影像 `runs/vla/d_ruling_round_20260930_0300/d_context_checkpoint_20260929_2130.md.before20`（927 ln `f54516f1ad3d`）。
**触发本轮增补的事实**：裁定 89（`decisions:2847-3010`，**3010 ln `252d1f86fd7a`**，as_of 03:09:06）—— **S1 formal-40 与 E 的 P0 冷启动在同一小时内双双交付。**

## §20.1 【取代 §19.0-3】临时权威判据口径 **已退役**

**§19.0-3 说**：「在 `e_gpu_egl_verify.py` 的竞态修好之前，判断冷启动是否成功以实测 `GL_RENDERER` 为权威，不以 exit code 为权威。」
**现状**：**竞态已根因修，且 v3 的 `baseline` 臂 `exit 0` 且 `renderer_class=nvidia_gpu`** ⇒ **该临时口径的可推翻条件已按"修好后通过"的方向解决** ⇒
> **现行口径：`exit code` 与实测 `GL_RENDERER` **同时**为权威（两者本轮一致）。重启后跑 §19.0-1 的那条命令，`exit 0` 即可采信，不必再绕开 exit code。**
**§19.0-1 的一条命令、§19.0-2 的分层事实、§19.0-4 的接续动作**全部继续有效。
**证据**：`runs/infra/e_egl_coldstart_20260930/COLDSTART_EVIDENCE_v3.json`（24,219 B，as_of **03:02:33**）：`stages=["manifest","chain","relink","mutant","baseline"]`、**`all_teeth_proven=true`**（D 已按新自检核过量程：五阶段齐、三臂齐 ⇒ 不是假绿）、`teeth_summary={tooth_relink:true, tooth_mutant:true, tooth_baseline:true}`、`boundary_clean_no_system_write=true`；`tooth_baseline` 的断言 `renderer_class_is_nvidia_gpu={ok:true,observed:"nvidia_gpu"}`、`coldstart_exit_zero={ok:true,observed:0}`。
**E 的修法证明方式（值得全线学）**：用 `scripts/e_selfcheck_gate_mutation.py` 做**两侧牙**（crosscheck GREEN + **5 个变异体全部生效**），**全程不触卡** ⇒ 变异体自检不需要 GPU 窗口。

## §20.2 【取代 §19.2 的关键路径图】现在只剩一个阻塞项

```
[B2] formal npz 导出（MUJOCO_GL=disable，不占卡，分钟级）   ← ★唯一阻塞项★
  → [C2] ① must_cover → 声明物理区间（进行中）+ 三条件（两臂变异体 / 分辨率只登记不定阈值 / 上限不赦免）
   → [C2] formal-40 stats（stats_provenance = formal40_bc_source）
    → [A2] S4b（需上卡 ⇒ 申报窗；A2 优先级最高）
     → [A2/B2] S3 BC（硬闸：stats_provenance == formal40_bc_source）

[已交付，不再阻塞]
  E：P0 冷启动 v3（三臂全通过）· T-E-DET-480 r2（measurement_status="measured"、5/5 无跳过）
  B2：S1 formal-40（40 集 = 20 forward / 20 reverse，19 闸 PASS / 0 红，状态比对 120/120 全逐位，
      0.2154 GiB，contaminated_by_cotenant=false 的干净窗）
  B2：裁定 85.5 的 replay 三颗牙（0/3/0，特异性由机器字段判定）· 裁定 85.6-1（--trash 含 manifest + 覆写守卫）
  A2：三网红线（债务 ① 关闭）· WHY_ARCHIVED（债务 ③ 销账）
  C2：T-C2-1 / T-C2-2 / T-C2-4 交付 · 主线档在真数据上测红（实质发现）

[P1/P2 · 不阻塞]
  B2：加项 1 渲染臂硬拒绝 + 牙（下一次采集之前）· authority_scope 补 does_not_apply_to · manifest 补 pilot5 命名说明行
  C2：mainline_status 补 n_episodes:10 · clip_ratio_structural_floor 加"①后应≈0"注解 · 契约文本按裁定 87.6 改用
      · 行数按档参数化 + gate_name 牙 · env_gym_aloha 牙声明 + 3 变异体 · T-C2-7 台账（排最后）
  E：daily_report 的 sha 更正框（append-only）· docs/infra-gpu-render.md 顶部权威恢复块（并点名 §19.0 临时版已被取代）
  A2：三网清洁证书 rep（P2，卡空可排）· 产物补 contamination_arm
```

**可证伪检查点（不变，裁定 87.3-2 条件 c）**：formal-40 的 stats 采 ① 后，`Td2_clip_heldout` 对物理合法状态应为 **0**、`Te2` 应为 `dims=[]`、`Tsat` 应为 `n_dims_saturated=0`。**任一非零 ⇒ 数据里存在超出声明物理区间的状态 ⇒ 判红、不许再展宽、转查采集器与契约。**
**可推翻条件（不变）**：若 ① 把任何主线维的 `bins_occupied_median` 压到 **< 8** ⇒ D 改采逐维覆盖策略。

## §20.3 【取代 §19.4 的一行】作废件已由 E 落盘处置

§19.4 里 D 写「D 直接判定 `RENDER_DETERMINISM_TEAM480x640_EGL_REPS5.json` = `invalidated_vacuous_all_reps_skipped`；E 须把它登进 `INVALIDATED_RUNS.json`（D 02:2x 实测该表两个关键词均 0 命中）」。
**现状（D 03:04:32 实测）**：该件**已改名为 `RENDER_DETERMINISM_TEAM480x640_EGL_REPS5.INVALIDATED.json`**，且 `INVALIDATED_RUNS.json` 现有 **6 处命中**（0 → 6）⇒ **裁定 88.5-1 / E 接单 §17.1 的"先于一切"事项已销账。**
**替代它的权威件** = `RENDER_DETERMINISM_TEAM480x640_EGL_REPS5_r2.json`（as_of **03:02:48**）。

## §20.4 【本轮新增的权威数字 · 重启后引用这里，不要引用更早的】

**S1 formal-40（`runs/vla/b2_sim_demo_bidir_20260930/formal/demo_manifest.json`，124302 ln `0c057e22690f`，as_of 02:57:21）**
- 40 集 = **20 forward / 20 reverse**；三 pass（`verdict_expert` / `verdict_replay_render` / `verdict_replay_norender`）**40/40 全 success**；`failure_class=None` 40/40。
- **状态比对穷举 120/120 全逐位**（`bitwise_equal=True` 且 `max_abs_diff=0.0`）：含 `recorded_vs_expert`（动作记录无损）**40/40**、`norender_vs_expert` **40/40**、**`recorded_vs_norender`（渲染不扰动物理）40/40** ⇒ **裁定 85.3 依赖的那条腿在 n=40 上成立**（此前只有先导 n=10）。
- 奖励：forward `env_reward_terminal=4` / `env_reward4_terminal=True`；reverse `=2` / `=False`（20/20 各自内部一致）。
- 任务串：恰好两条冻结串各 20 集（`Transfer the red cube from the right arm to the left arm.` / `…from the left arm to the right arm.`）；`state_dim=14`、`action_dim=14`；`n_frames` 合计 **11035**（min 271 / max 283）；`shape_accounting.identity_holds=True`。
- 体积：**231,306,695 B = 0.2154 GiB**、`n_files=207`（RR-B2-12 的可推翻条件 >2 GiB 未触发）。
- **干净窗**：`contaminated_by_cotenant=false`、`reasons=[]` ⇒ **计时数字为全口径**：逐集墙钟 **min 32.41 / median 33.24 / max 34.83 s**、合计 **1335.9 s = 22.27 min**（散布 7.5%）。**这是本仓第一份"低负载 + 无共租 + 三网清洁"的 S1 采集计时。**
- **用途限定**：以上计时**只用于产能/排期**，**不得**引用为任何 policy 的推理时延（那是 A2 的 `budget_fraction` 带 **0.7703–0.8009**，不同口径，裁定 71 禁止搬用）。
- **专家自证未过期（D 核过 mtime）**：专家模块 `scripts/b2_s1_scripted_expert.py` **1299 ln `f24d81d35ed8`** mtime **00:13:03**；自证件 `probe/expert_selfverify_40x2_postpatch2.json`（`d9dc8b7b9e0e` / 59,773 B）mtime **00:13:39** ⇒ 自证在专家模块最后修改**之后 36 s** 生成；manifest 引的 sha 与当前磁盘一致。`summary.success=80 / failure=0`（40 seeds × 2 方向）。**这不是任何 policy 的能力结论（裁定 46）。**
- **`arm_stable = inferred_from_two_machine_facts`（不是 measured）**：manifest 里**没有** `renderer_class_at_start/_at_end/arm_stable` 三字段（B2 02:32 起跑，早于 D 的 §D88.2 于 02:35:29 落盘）。**起点臂实测 `nvidia_gpu`**；**终点臂未测得**，由两条独立机器事实佐证（① `pixel_register_exceedance_slots` = 全 6 槽非空，而 osmesa 臂是逐位的 ⇒ 采集全程在 egl 臂，且双渲染逐集做、最后一集 02:54:49 完成；② 穷举 40 集超 83.4 容差 = **0**，一次后端切换会产生远大于 1 LSB 的差）。**任何引用本批"渲染臂稳定"的文书必须写 `inferred`，不得写 `measured`。**

**480×640 的 egl 登记带（`…_EGL_REPS5_r2.json`，as_of 03:02:48，生成器 `scripts/e_render_determinism.py` 418 ln `653df66aaa6b`）**
- `measurement_status="measured"`、`reps=5`（5 个独立进程）、`n_reset=3`、`n_shoot_per_state=3`、cams = `top`/`left_wrist`/`right_wrist`、**5/5 无跳过**。
- **带值**：`top ≤ 2.9e-05` / `left_wrist ≤ 9.4e-05` / `right_wrist ≤ 2.25e-04`；三相机 **`max_abs_diff_worst` 全 = 1**；三相机进程内与跨进程**均不逐位**。
- **osmesa 对照臂**：三槽 **5/5 全逐位、`max_abs_diff=0`、未触卡**。
- **裁定 83.3 三条件全未触发**：① `>1%` 未触发（最差 0.0225%，余量 **44×**）；② `>8` 未触发（`max_abs_diff=1`，余量 **8×**）；③ 按 85.2 改写后的 `angle_non_bitwise_and(frac_diff_px>0.001 or max_abs_diff>2)` 未触发（相机集不含 `angle`；`2.25e-04 < 0.001` 且 `1 ≤ 2`）。
- ⇒ **B2 的 G4d 由 `N_A` 改为 `register_only`（仍不判红）**；**裁定 83.4 的容差覆盖 480×640，余量 22× / 2×，不需重定**；**红线 `render_bitwise_equality_ban_on_egl` 在 480×640 同样适用**。
- **224² 的登记带超出率在 n=40 上已实测**：超 E 的带 = **20/40 集**（全在 `pi05_left_wrist_0_rgb`，最差 `4.3077e-04` = 带值 `2.39e-04` 的 **1.80×**）；超 83.4 容差 = **0/40**（余量 **11.6×**）⇒ **"登记带只能是登记带、不能是判据"的论据由"偶尔会超"升级为"50% 的集在某相机上会超"**（拿它判红 = 常态红 = 缺陷类 ②）。

## §20.5 【本轮新增纪律】

- **新规则 `prose_identity_must_be_verifiable_against_a_saved_artifact`**（裁定 89.7）：**散文里引用的每个身份串，必须存在一个机器保存的产物（before 影像 / cite 表）其 sha 与散文值相等；若不存在，散文只引产物路径、不引 sha。D 会抽查。**
  **起因（本仓第三例散文身份串错误，前两例都是 D 自己）**：E 的 §E12.6 写「追加前 `daily_report.md` = 6436 ln / `fb8193619e0d` / 898026 B / mtime 02:35:29」，而 D 记录的是 6436 ln / `4aeecfc97089`。**D 两条独立取证一致判定 E 的散文 sha 无支撑**：① `head -6436 daily_report.md | sha256sum` = `4aeecfc97089`、`| wc -c` = 898026；② **E 自己保存的 before 影像** `runs/infra/e_mainline_calib_20260929/before_images/round4_window2/daily_report.md.beforeE12_2` = 6436 ln / `4aeecfc97089` / 898026 B。**E 的行数、字节数、mtime、before 影像四项全对，只有散文 sha 错。**
  **关键教训**：E **自称**"按裁定 88.6 收紧后的口径"机器取值，而散文值仍与自己的机器产物不符 ⇒ **"打算机器取值"与"散文里的值确实来自机器"之间还有一道缺口。最稳的做法是 C2 那种：落笔时刻由脚本（`scripts/c2_cite.py`）生成身份表，人不碰 sha 串。**
  **记 E 一功**：**正因为 E 存了 before 影像，这个冲突才能在一条命令内判定**；若无 before 影像，两个 sha 会永久对立、无从裁决 ⇒ **before-image 纪律第三次证明其价值。**
- **新 D 自检 `single_sample_must_not_be_phrased_as_a_rate`**（裁定 89.3）：凡 D 用"会/总是/常态"这类频率词描述现象，必须有**计数证据**（n 与命中数），否则只能写"已观测到 1 例"。**起因**：D 在 §D88.4 用 teeth1 的单样本（1+1 集）写成「干净批也会超」；穷举 40 集后实测是 **20/40**（结论方向对，但论据强度被 D 低估了）。**这是 D 第 3 次"用单样本说成一般规律"**（前两次：裁定 85.1 把红线成因污染的数当权威、裁定 87.1-3 把 E 自曝精度不足的字段升格为常量事实）。

## §20.6 账目（截至裁定 89）

- **D 同型错误：14**（本轮未增）。**记账类更正 +1**（§89.3 措辞过窄，D 自行更正，未造成下游误用 ⇒ 记近失不记错误）。**D 近失：4。**
- **下属纠正 D：9**（本轮未增；§89.7 是 D 抓 E 的，不计）。
- **缺陷类扫描：16**（本轮未增类型；§89.7 属既有类 ⑨「引用过期/不完整」）。
- **验收关闭**：S1 formal-40 · T-E-EGL-COLDSTART（P0）· T-E-DET-480（P1）· 裁定 85.5 的 replay 三颗牙 · 裁定 85.6-1 · 裁定 88.5-1 的注册表登记。

## §20.7 用户分叉（**本轮减少一项**）

**待追认（3 项，与裁定 87.14 相同）**：① `timeout_isolation_scope = td_only`；② **丙案**（现已两腿实测 + B2 的 1 ULP / pixel-only 两颗专属牙 + 480×640 同 regime）；③ **§87.3 采 ①**（`must_cover` → 声明物理区间；本轮唯一改变主线数据表示的裁定，会换 `representation_version`）。
**挂起（3 项，本轮未动）**：`NVIDIA_DRIVER_CAPABILITIES=graphics` · bf16 测试 · E 的 5 min 稳态并发窗（D 判：现在不要）。
**已退役（用户不必再追认）**：§19.0-3 / 裁定 88.4-2 的**临时权威判据口径** —— 因 E 根因修好竞态、v3 的 `baseline` 臂 `exit 0` 且 `renderer_class=nvidia_gpu` ⇒ **exit code 恢复为权威**。
**已闭合（无需用户动作）**：`workers_cap=8` · 单臂渲染范围从未解除 · 实机采集窗口（裁定 55.5 撤回，触发条件 S5 通过 + S6 方向性证据**仍未满足**）。

## §20.8 里程碑口径（给用户；**不含任何能力声称**）

**仿真链的"数据腿"（S1 双向示范 40 集）与"基础设施腿"（GPU 渲染冷启动可恢复 + 480×640 登记带）在 2026-09-30 02:5x–03:0x 同时落地。**
**剩下的三步**：归一化器口径（C2 的 ①，进行中）→ S4b 运行时接口（A2）→ S3 BC（A2/B2）。
**在 BC 跑出结果之前，任何"能搬运"的说法都不成立**（裁定 46：没跑过 policy 就不许声称能力）。**本轮所有 `success=80/0` 类数字都是脚本专家的自证，不是 policy 能力。**

---

# §21 【D 上下文检查点 · 增补于 2026-09-30 04:0x · **重启后请从本节读起**，它取代 §20 的五处内容】

> **读法**：§21 → §20 → §19 → §17/§18。
> **§21 取代**：§20.2（关键路径图）· **§20.3（「改名」措辞 —— D 写错了，见 §21.3）** · §20.4（权威数字，本节为增量）· §20.6（账目）· §20.7（用户分叉）。
> **§20.1 / §20.5 / §20.8 继续有效**（退出码重新权威 · 本轮新增纪律 · 里程碑口径）。
> **§19.0-1 的一条命令仍是断点恢复入口**；§18 的 npz 相关路径已被 §20.4 / §21.4 再次更新。

## §21.1 本轮（裁定 90 + 91 + 92）发生了什么 —— 五件事

1. **【最重 · 解阻塞】裁定 90 撤回裁定 87.3-2 条件 c 的极性。** C2 撞上与 D 裁定直接冲突的实测，**按纪律不自决、把根因写进牙的 note（`harness/norm_contract.py:824`）并报 D**。D 完成条件 c 要求的「转查采集器与契约」，结论 = **采集器无缺陷、契约文本无缺陷、D 的前提错了**：`jnt_range` 是**软**边界，而 D 把它当硬界。⇒ **`Tiv_no_state_outside_declared_interval` 改判**（越界=测量、硬红移到 `headroom_consumption_max ≥ 1.0`、`Te1/Te2 illegal_bin(-1)` 保持绝对硬红）。**改判前 `Tiv` 在 formal-40 上必红且不在 `MAINLINE_ALLOWED_RED_F1` 里 ⇒ BC 被硬阻塞；这就是本轮之前全仓唯一的实质卡点。**
2. **D 记三个同型错误（14 → 17），三条全在裁定 87.3 同一轮里**：#15 软边界当硬界 · #16 用 `bins_occupied_median<8` 守逐维失效（实测 median 47.5 不触发、min 3 才是真相）· #17 以**已被裁定 85.4-3 消解的理由**否掉候选 ②。⇒ 新规则 `a_per_dim_failure_mode_must_be_gated_by_a_per_dim_statistic` + `caliber_must_not_contradict_the_single_writer_table`；**缺陷类 16 → 17**（⑰ 聚合统计量掩盖逐维失效）。
3. **裁定 91 验收 B2 的渲染臂端点复测 + formal npz；裁定 89 的 `arm_stable=inferred` 限定词解除**，升级为 B2 自己的 `post_run_independent_probe_same_caliber`（4/4 判据）。**记 B2 三功**（在「拿起点值顶一下就能交差」处如实记 `null` · 用两组间接但机器算的证据承载无法直接回测的命题 · 牙真咬了：软件臂识别为 `mesa_cpu_software`）。**加项 1 定位回到「下一次采集之前的前置」，不阻塞 formal-40 任何下游。**
4. **裁定 92 逐条答 E 的四个请示**：① **不需要 v4**（决定性理由 = 一条命令恢复路径不设 `E_SKIP_GPU`，退出码仍 0 ⇒ **恢复语义未被修法破坏**），但两个机器可读标注必须落；② **批准修悬空链接，但不许上卡、也不与①合并**（①不存在），产物只能叫 `PERSIST_MANIFEST_v4.json`、**不得叫 `COLDSTART_EVIDENCE_v4`**，C4 复验**搭 A2 的 S4b 便车**；③ **散文 sha 必须由工具生成且带算法名 ⇒ 升红线级**；④ **「改名」措辞 E 对 D 错**。
5. **【最重的一条记账】新缺陷类 ⑱ `fabricated_justification_for_a_wrong_value`**（为自圆其说而虚构依据）。E 曾写「两算法前 12 位巧合地都以 `b9cf67ab4fab` 开头」来圆一个错 sha，**而 D 亲核该件 sha256[:12] = `6a67e3796695`，与 sha1 毫无相似之处 ⇒ 那个巧合不存在**。**它比错 sha 严重一个量级：错 sha 会让核对者发现不一致，虚构的依据会让核对者得到「两算法一致」的假结论、从而放过整类算法错配 —— 它解除的是读者的检出能力。** **E 在 D 尚未看到时主动上报、并要求「不要与记账错误混计」⇒ 记 E 一大功。**

## §21.2 【取代 §20.2 的关键路径图】**B2 的 npz 已交付 ⇒ 只剩 C2 一步**

```
[C2] Tiv 改判（裁定 90.4-1）+ 三颗牙 → formal-40 stats          ← ★全仓唯一 BC 前置★
      命令口径：--s1-frames runs/vla/b2_states_14d_20260930/formal40/states_14d.npz（a84a26079550）
      ⇒ stats_provenance = formal40_bc_source
  → [A2] S4b（需上卡 ⇒ 申报窗；GPU 优先级 A2 > B2 > C2 > E）
   → [A2/B2] S3 BC（硬闸：stats_provenance == formal40_bc_source）

[本轮已交付、不再阻塞]
  B2：formal-40 npz（a84a26079550，双跑 9/9 数组逐位，40 集/11035 帧/[11035,14] float64，
      zip_entry_date_time 两跑均 [1980,1,1,0,0,0] ⇒ 逐字节可复现是结构性的）  ← §20.2 的「唯一阻塞项」已销账
  B2：渲染臂端点复测（arm_stable=true 4/4、environment_invalid=false、软件臂牙已咬）
  E ：退出码假绿的根因修（exit 5 = PARTIAL）+ 逐臂核过影响面 + 牙产物自带 PARTIAL 定位
  E ：三份 MANIFEST/身份表重生成（n_unlisted=0 / n_missing=0）
  （更早：E 的 P0 冷启动 v3 · T-E-DET-480 r2 · B2 的 S1 formal-40 · 85.5 replay 三颗牙 · A2 的三网红线）

[P1/P2 · 不阻塞 BC]
  B2：git 代提交（HEAD 仍 4ff31bd、工作区 29 项脏 ⇒ **服务器可能关闭，请提交两次**）
      · contract_conflict.status 改「已由裁定 87.6 关闭」并三跑核验（**改 sha 必须知会 C2 并对时序**）
      · authority_scope 补 does_not_apply_to · overwrite_guard 的 CPU-only 牙 · 团队 QC(validate→clean→qc) 对 formal
  C2：mainline_status.json 重生成（**它现在写着被裁定 86.0 撤回的口径，且引用了一个不存在的裁定号 85.4-2-1**）
      · --s1-lerobot 标签改 formal40_lerobot_crosscheck（**且必须加进 KNOWN_STATS_PROVENANCES、admissible_for_bc=false**，
        否则 Tp4 会把它判成假红）· n_episodes:10 · clip-floor 注解 · 契约文本按 87.6 · row-count 参数化
      · gate_name 牙 · env_gym_aloha 声明 + 3 变异体 · T-C2-7 台账（排最后）
  E ：v3 的两个机器可读标注（tooth_relink.exit_code=0 是历史值 / reproduction_caliber_gap）
      · PERSIST_MANIFEST_v4（三项 CPU 修 + link_target_exists/dangling 实测字段）
      · docs/infra-gpu-render.md 顶部权威恢复块（并点名 §19.0 临时版已被取代）
  A2：运行时「prompt 里是否出现 -1 state token」的牙（P1）· 三网清洁证书 rep（P2，别为它占卡）
```

**可证伪检查点（按裁定 90 更新，取代 §20.2 那条）**：formal-40 的 stats 采 ① 后 —— `Td2_clip_heldout = 0`、`Te2 dims = []`、`Tsat n_dims_saturated = 0`、**`illegal_bin(-1)` 不存在**、**`headroom_consumption_max < 1.0`**。
**其中「越出声明区间」本身不再判红**（裁定 90.4-1）：D 已实测 formal-40 有 **3 维 [6,10,13] 越界、最大 0.298922% 声明行程、`headroom_consumption_max = 0.765241`**，而**非法 bin = 0**。**若 `headroom_consumption_max ≥ 1.0` ⇒ 红，且不得放宽 1.0**（它是窗口逃逸的定义），改为提高 `headroom_bins` 或启用 P1 逐维覆盖 + 新建 `representation_version`。
**可推翻条件（按裁定 90.2 #16 更正）**：原 §20.2 写的 `bins_occupied_median < 8` **是错的统计量** —— 实测 median **47.5**（不触发）而 **min 3（dim3）/ 4（dim10）**。**现行口径 = 逐维**：若 `bins_occupied_min < 8` 的维**不再是**已分类近常量维（出现「信息量不低却只有个位数 bin」的维），**或** BC 首轮失败面指向 dim3/dim10 ⇒ **P1 的逐维覆盖立即升 P0**（D 已预分析完毕，无需重新论证）。

## §21.3 【更正 §20.3 与 §19.4 —— D 的第 18 号同型错误】

**§20.3 写「该件已改名为 `…EGL_REPS5.INVALIDATED.json`」——这是假的。§19.4 同源。**
**D 亲核文件系统（`ls -la` + 逐个 sha，as_of 04:0x）**：

| 文件 | 字节 | mtime | 身份 |
|---|---|---|---|
| `…TEAM480x640_EGL_REPS5.json` | **18064 B** | **02:22** | **原件原字节，名字与内容都在原地（没有改名）** |
| `…TEAM480x640_EGL_REPS5.INVALIDATED.json` | 3672 B | 02:39 | **103 ln `b5a75ef6e3f5`** = **另存的旁证标记件** |
| `…TEAM480x640_EGL_REPS5_r2.json` | 27548 B | 03:02 | **1186 ln `6a67e3796695`** = **权威有效测量** |
| `INVALIDATED_RUNS.json` | — | — | 两个关键词 **6 命中**（0 → 6，销账成立） |

**现行权威措辞（全线照此引用）**：**「原件保留原字节原名 + 另存同名 `.INVALIDATED.json` 旁证标记件 + 注册表 6 命中」**。
**D 错在哪**：把**他线报告里的说法**当成**文件系统状态**写进裁定与**权威重启入口**，没有亲自 `ls`。与 #13 同根 ⇒ **记 D 同型错误 17 → 18；下位纠正 D 10 → 11（E 的 §E12.8.4 末条）**。**特别严重**：它在 checkpoint 里 ⇒ **一个重启后的 D 会带着一个关于文件系统的错误信念开工**，这比一次引用错更重。
**采纳 E 的理由并升为全仓口径（新规则 `invalidation_never_renames_the_original`）**：那份空集件是**让位闸在真实抢卡场景下生效的唯一实证**，删名/改名会灭失证据 ⇒ **作废一个产物的正确做法 = 原件原字节原名保留 + 另存旁证标记件 + 注册表登记；永不改名、永不删除。**

## §21.4 【本轮新增的权威数字 · 与 §20.4 合并使用，冲突以本节为准】

**formal-40 npz（D 独立复核，不看日志、重算产物）**
`runs/vla/b2_states_14d_20260930/formal40/states_14d.npz` = **sha256 `a84a260795505780ca9c403d85719dd4b75921d18799ee61024d14e3ef7cd187`（12 位 `a84a26079550`）/ 1332184 B**；双跑 `formal40_dualrun_sha_verdict.json`（3996 B）`raw_file_sha_equal=true`、**9/9 数组 `bitwise_equal=true`**；`n_episodes=40`（`np.unique` 复算）、`n_frames=11035`、`frames=[11035,14] float64`、`start_poses=[40,14]`；9 个键名逐字未变。导出器 `scripts/b2_export_states_14d.py` **986 ln `8708d4a84d7f`**。
**两条读路径逐位等价（D 亲测）**：npz `frames` vs parquet `observation.state` 按 (`episode_index`,`frame_index`) 分组上转 float64 ⇒ `np.array_equal=True`、`max_abs_diff=0.0`、**双方 content sha256-12 均 `c9a72480fcb7`**、40 集/11035 帧/顺序一致、`float64→float32→float64` 逐位无损。

**归一化契约在 formal-40 上的实测（D 只读探针，用 C2 的模块、没改 C2 一行代码）**
`runs/vla/d_ruling_round_20260930_0320/probe_headroom_vs_softbound.json` = **2345 B `363aab649afb`**（+ 同名 `.txt`）；口径 = `harness/norm_contract.py` **1074 ln `0165528393d7`** 原样调用。
越界维 **[6,10,13]**（全在上方、`ex_below` 14 维全 0、`start_poses` 越界维 `[]`）· 最大越界 **0.018782**（dim10）= 声明行程的 **0.298922%** · 越界帧数 dim6 **6424(58.2%)**/dim10 **3182(28.8%)**/dim13 **2646(24.0%)** · **`illegal_bin(-1)` 不存在** · 归一化后越出 [-1,1] 的帧 **0**（`xn ∈ −0.867980…0.998180`）· `headroom_consumption_max = **0.765241**`（余量 **1.3068×**）· 头寸预算 **0.390625%** = `BIN_WIDTH 0.0078125 × HEADROOM_BINS_DEFAULT 1.0 / 2` · `cover_cap_respected=True`、violation `[]`、`n_widened=28` · 顶 bin255 帧数 dim6 **6609(59.89%)**/dim10 **3188(28.89%)**/dim13 **2708(24.54%)**，任一维命中 **9605 帧(87.0%)** · 逐维 `bins_occupied` **median 47.5 / min 3(dim3) / 4(dim10) / max 117**。
**bin255 = 真物理饱和平台**：dim6 的 6609 帧物理跨度仅 **0.001098**（`[0.974694,0.975792]`）、**119 段连续 run/最长 177/均值 55.5**；dim13 跨度 **0.000686**、67 段/最长 121 ⇒ **语义正确、不是缺陷、明令禁止用展宽消除**。

**结构不对称（四线都要知道的硬事实）**
`processor_pi05.py:77` = `np.digitize(x, bins=np.linspace(-1,1,257)[:-1]) - 1` ⇒ **`x ≥ 1` → bin 255（合法顶 bin，优雅饱和）**；**`x < −1` → bin −1（非法，静默拼进 prompt）**。⇒ **下侧覆盖 = 正确性（硬红）；上侧越界 = 分辨率/饱和（测量 + warning）。**
**钳位不可用（已核实）**：该文件**只在三个 venv 的 site-packages**（`/root/venvs/{lerobot_act,lerobot_eval,pi05_sim}/lib/python3.11/site-packages/lerobot/policies/pi05/processor_pi05.py`），**仓内无副本** ⇒ 改它属系统写（硬约束禁止）。**正确性只能由 stats 侧覆盖保证。**

**渲染臂端点复测（B2，裁定 91 验收）**
`runs/vla/b2_sim_demo_bidir_20260930/formal/renderer_arm_endpoint_probe.json` = **9248 B**，mtime **03:18:00**，`rc=0`；生成器 `scripts/b2_probe_render_arm.py` **389 ln `34da0a62c2b3`**。`renderer_class_at_start=nvidia_gpu`（运行内实测）· **`renderer_class_at_end_in_run=null`（如实记未测）** · `renderer_class_at_end=nvidia_gpu`、`measurement_kind=post_run_independent_probe_same_caliber`、`gap_s_since_run_end=1240.5` · `arm_stable=true`（4/4）· 墙钟 40 集 `min/max/mean/median=32.41/34.83/33.397/**33.24** s`、`max_over_median=**1.0478**`、`n_exceeding=0`、`llvmpipe_slowdown_reference_x=**12.64**` · 末段连渲 **40/40 集、240 槽行、G4b+G4d PASS** · `endpoints_agree=true`、`environment_invalid=false` · 牙：软件臂 → `mesa_cpu_software` / `llvmpipe (LLVM 15.0.7, 256 bits)`。
**引用口径**：不必写 `inferred`，但**必须写 `post_run_independent_probe_same_caliber` 且必须同引 `renderer_class_at_end_in_run=null`**；**「运行内连续监测」仍未测到、不得声称。**

**D 本轮文书身份**：decisions **3235 ln `226bd77fc6fb`**（裁定 90 在 `:3012` 起、91 紧随、92 在 `:3157` 起）· params **rev16 2681 ln `4e874b7b33a1`** · daily_report **7237 ln `c303bf25f249`**（§D90）· 交接 **c2 869 ln `da9730cfa15c`（§18）/ b2 929 ln `b5a82c6085c8`（§21）/ a2 1060 ln `8e5197bb0b77`（§23）/ e 715 ln `a3de25d90ca5`（§18）** · 前像全部在 `runs/vla/d_ruling_round_20260930_0320/`（`.before90` = 3010 ln `252d1f86fd7a` · `.before92` = 3156 ln `a1116bd6c403` · `.before_rev16` = 2450 ln `7b69eeb6cb42` · `daily_report.md.beforeD90` = 7067 ln `e66de1b45f5a` · `d_context_checkpoint.before21` = 1026 ln `370b917acf62` · 四份 `d_handoff_to_*.before*`）· 写参数表的脚本本身也留档：`runs/vla/d_ruling_round_20260930_0320/write_params_rev16.py`（`085eb7c0a9ef`）。

## §21.5 【本轮新增纪律】

- **`a_per_dim_failure_mode_must_be_gated_by_a_per_dim_statistic`** —— 凡失效模式是「某一维坏掉」，判据统计量**必须逐维**（min / 逐维列表 / 逐维阈值），**不得用 median 或 mean**（聚合会把恰好要抓的那一维平均掉）。与红线 `absence_of_measurement_is_not_measurement_of_absence` 同族（**聚合掩盖个体**）。**缺陷类 ⑰。**
- **`caliber_must_not_contradict_the_single_writer_table`** —— D 写任何口径前，必须核该量的**出处与语义**是否已被 `work/project_parameters.json`（D 单写者）或 decisions 记录过。
- **`invalidation_never_renames_the_original`** —— 作废产物 = **原件原字节原名保留 + 另存旁证标记件 + 注册表登记**；**永不改名、永不删除**（改名会灭失「闸曾经生效」的唯一实证）。
- **`a_wrong_value_plus_an_invented_explanation_is_two_defects_not_one`** + **缺陷类 ⑱ `fabricated_justification_for_a_wrong_value`** —— **虚构的依据比错值严重一个量级：它解除的是读者的检出能力。**
- **`prose_identity_must_be_verifiable_against_a_saved_artifact` 升红线级**，加两条硬要求：**(i) 身份串必须由工具在落笔时刻生成，人不碰；(ii) 工具必须同时落算法名与可引用口径（`citation_algo: "sha256[:12]"``）。** 全仓最低 schema = E 的 `scripts/e_write_identity_table.py`（两算法 + `n_lines`(`wc -l`) + `n_lines_splitlines` + `ends_with_newline` + `why_it_matters` + `citable`）；C2 的 `scripts/c2_cite.py` 并存、允许任一。**D 会抽查。**
- **两条全线自检（E 自定、D 采纳）**：清单/索引件生成后必须与**不跟随符号链接**的 `find -type f | wc -l` 对一次行数且差值必须可解释（**注意 `rglob` 跟随符号链接**，所以基数必须用 `find -type f`）· 含中文引号的脚本正文写完必过 `ast.parse` 再跑（**它只挡语法错、不挡语义错，不能替代上一条**）。

## §21.6 账目（截至裁定 92）

- **D 同型错误 = 18**（本轮 +4：#15 软边界当硬界 · #16 中位数守逐维 · #17 以已作废理由否掉正确候选 · #18 把他线说法当文件系统状态写进权威重启入口）。**#15/#16/#17 同在裁定 87.3 一轮 ⇒ 该轮取证深度不足。**
- **D 近失 = 4**（本轮不新增）。
- **下位纠正 D = 11**（本轮 +2：C2 的 `norm_contract.py:824` 软边界上报 = 第 10 次 · E 的 §E12.8.4「改名」措辞 = 第 11 次）。
- **缺陷类扫描 = 18**（⑰ 聚合统计量掩盖逐维失效 · ⑱ 为自圆其说而虚构依据）。
- **E 的账（D 追认 E 的自计，不增不减）**：记账错误 +2 · **另单列 1 起「虚构依据」** · 代码缺陷 +3（均自查自修且各自装牙）· 近失 +1。**E 三大功。**
- **B2 的账**：本轮**记功四项**（npz 三跑一致 + `zip_entry_date_time` 排掉「同一秒完成」的假象 · 端点复测在能顶替处如实记 `null` · 两组间接机器证据承载不可回测命题 · 软件臂牙真咬）；欠账 5 项全在 P1（§21.2）。
- **C2 的账**：**记大功一次**（不自决、上报、根因写进牙的 note）。

## §21.7 用户分叉（**本轮新增 1 项待批**）

- **[待批]** ① `timeout_isolation_scope=td_only`（83.7-2）· ② **丙案**（85.2-2）· ③ 裁定 87.3 adopt ① —— **必须按 rev16 的口径批，不要按 rev15 的原文批**：① 本身**保留**，但其**条件 c 的极性已被裁定 90 撤回**、可推翻条件已确认以**逐维**形式触发（处置排 P1）。
- **[本轮新增待批]** ④ **裁定 90.4 全部四条**（D 已自证 + 写了可推翻条件）。**最需要用户过目的是第 3 条**：D 把「逐维覆盖（dim3/dim10 从 3/4 bin 恢复到 ~200 bin）」排为 **P1 而非 P0**，依据 = 这两维已按 `Tr1` 分类为近常量（travel/span = 0.72%/1.48% < rel_tol 0.02，信息量本就低）⇒ 边际收益不确定，而重构生成器在关键路径上是确定成本。**若用户认为表示层分辨率优先于跑通速度，第 3 条应改为 P0。**
- **[悬挂]** `NVIDIA_DRIVER_CAPABILITIES=graphics` · bf16 测试（会新建 `representation_version` 并使裁定 84.7 的 realtime 口径作废）· E 的 5 分钟稳态窗口（**D 判：现在不做**）。
- **[已退役、不必再批]** 裁定 19.0-3 / 88.4-2 的过渡权威判据（**退出码重新权威**，见 §20.1）。
- **[已闭合、无需用户动作]** `workers_cap=8` · 单臂作用域从未解除（Piper 单臂；主线 `AlohaTransferCube-v0` 是 14 维双臂形态、按 v4:5 用单臂 ACTION）· 实机窗口于裁定 55.5 撤回（触发条件 S5+S6 未满足）。

## §21.8 重启后 D 的接续步骤（**取代 §18.5 / §19.7 的相应部分**）

1. **扫盘**：`git log --oneline -1`（本轮实测仍 `4ff31bd`、脏 29）· `find . -newermt '-30 min' -type f` · GPU **三网**（**绝不可只看 compute-apps**）· `daily_report.md` **先取当前行数再从上次已知行数起读**（本轮 D 从 6673 读到 7067，E 与 B2 都在快速追加）。
2. **确认 C2 是否已跑 formal-40 stats**：看 `runs/vla/c2_norm_contract_20260929/gate/run_*/`（本轮最后一次是 `run_20260930_025846`，其 `mainline_status.json` 还是 `waiting_for_s1_formal_40` / `checked_path: null` ⇒ **已过期，必须重生成**）。**若 C2 已跑，先核 `stats_provenance == formal40_bc_source` 与 `headroom_consumption_max < 1.0`。**
3. **若 C2 还没改 `Tiv`**：不要催它跑 stats（会白跑一次红），先确认它读到 `d_handoff_to_c2_20260929.md` **§18**。
4. **盯 A2 的 S4b 窗口申报**：A2 上卡时，**E 的 C4 复验搭便车**（裁定 92.2）——A2 只需照常落 `renderer_class`，若回 `nvidia_gpu` 即构成前缀改动无害的第三方证据。
5. **催 B2 的 git 提交**（**用户明示服务器可能关闭**；`runs/` 被 `.gitignore:12` 排除 ⇒ 证据只在 NFS，提交信息里必须写明）。
6. **能力声明禁令不变（裁定 46）**：BC 出结果之前，**任何「能搬运」的表述都无效**；`success=80/0` 是脚本专家自证。

## §21.9 里程碑口径（给用户；**不含任何能力声称**）

**本轮之前**：仿真链的**数据腿**（S1 双向 40 集示范）与**基础设施腿**（GPU 渲染冷启动可恢复 + 480×640 登记带）已落地。
**本轮**：**归一化契约腿被解阻塞** —— D 发现并撤回了自己写错的一条闸极性（那条闸会让 BC 永远起不来），并实测确立了 π₀.₅ 状态离散化的**结构不对称**（上溢优雅饱和 / 下溢产生非法 token），这把「哪一侧的覆盖是正确性问题」变成了一个**有物理依据、可测量**的判据，而不是一个需要反复争论的口径。同时确认了**跨线接口的唯一权威**（npz `a84a26079550`），并实测两条读路径逐位等价 ⇒ 消除「BC 到底吃了哪一份 stats」这个隐患。
**还剩三步**：**C2 的 `Tiv` 改判 + formal-40 stats → A2 的 S4b 运行时 → S3 BC**。
**在 BC 产出结果之前，「能搬运」不成立。**

## §21.10 【增补于 04:09 · 两处更正，**以本节为准**】

**1. 参数表已到 rev17（§21.4 写的 rev16 已被取代）**
`work/project_parameters.json` = **rev17 / 2770 ln `5a80462e1b12`**（rev16 = 2681 ln `4e874b7b33a1`，其前像 `…before_rev16` = 2450 ln `7b69eeb6cb42`；rev17 的前像 `…before_rev17` = 2681 ln `4e874b7b33a1`、修正前像 `…before_rev17_fix` = 2760 ln `7fe5eab2a0d9`）。
**rev17 新增单键 `operations.disciplines_rev17`**（裁定 92 的六组口径：`prose_identity…` 升红线级 + 全仓最低 schema · **缺陷类 ⑱ `fabricated_justification_for_a_wrong_value`** · **`invalidation_never_renames_the_original`** · 两条全线自检 · **`e_coldstart_v4_NOT_required`** · **`e_persist_prefix_v4_APPROVED_CPU_ONLY`**）。
**decisions 也长了**：`work/decisions/decisions_20260929.md` = **3235 ln `226bd77fc6fb`**（裁定 92 在 `:3157` 起）。

**2. D 自查纠正一处自己刚写下的错误（bookkeeping，未计入同型错误台账，但升级为一条自查项）**
- **发生了什么**：构造 rev17 时用 `d['revision_history'][-2]` 取「上一版」的 `user_ratification_pending` / `still_open_forks`，但该表达式在 `list.append(rev17)` **之前**求值 ⇒ `[-2]` 指向的是 **rev15** 而不是 rev16 ⇒ rev17 继承了两版之前的分叉清单，**丢掉了 rev16 新增的待批项 ④（裁定 90.4 全部四条）与 rev16 对 ③ 的口径更新**（实测：修前 4 项 = rev15 的 3 项 + ⑧；修后 **8 项** = rev16 的 7 项 + ⑧）。
- **谁抓到的**：**D 自己**（写入后立刻打印 `len(ratify)` 得 4、与预期 8 不符）。**未被任何下游消费。**
- **为什么值得升级成自查项**：**`user_ratification_pending` 是用户回来后唯一要读的分叉清单 ⇒ 丢一项 = 用户漏批一项 = 一个已裁定的口径失去追认。**
- **⇒ 新自查项 `derive_from_previous_revision_by_rev_number_never_by_list_position`**：凡从「上一版」派生字段，**必须按显式版本号索引**（`by_rev = {r['rev']: r for r in rh}` 然后取 `by_rev[rev-1]`），**不得用 `[-1]` / `[-2]` 这类位置索引**；且在 `append` **之后**再校验 `len` 与内容。**理由**：位置索引的正确性依赖「求值时刻列表还没被自己改动」这个隐含前提，而这个前提在**同一个表达式里构造新版本**时恰好不成立。
- **同族**：这与 #16（用 median 守逐维）是同一类思维错误的两个面 —— **都是「用一个看起来能用的间接量，替代那个真正要指的东西」**（位置 vs 版本号；中位数 vs 逐维值）。

## §21.11 【增补于 04:1x · 最终身份表 —— **§21.10 里 decisions 的身份已过期，以本节为准**】

**为什么需要本节**：§21.10 写「decisions = 3235 ln `226bd77fc6fb`」，而 D 随后又往 decisions 追加了 §92.6 ⇒ **那一行在写下时就已经过期**。这正是 #18 的同族形态（把一个读数当权威身份写进重启入口），所以**不留隐患，就地更正**。

**D 的四份文书（as_of 2026-09-30 04:09:11 实测）**

| 文件 | 行数 | sha256-12 |
|---|---|---|
| `work/decisions/decisions_20260929.md` | **3244** | **`7e693313480b`**（裁定 90 在 `:3012` 起 · 91 紧随 · 92 在 `:3157` 起 · §92.6 自查纠正在末尾） |
| `work/project_parameters.json` | **2770** | **`5a80462e1b12`**（**rev17**，`measurements_and_decisions` = 117） |
| `daily_report.md` | **7237** | **`c303bf25f249`**（§D90 = 裁定 90/91/92 广播） |
| 本文件（checkpoint） | — | **不可自引**（自引会产生悖论）⇒ **重启时用 `wc -l` + `sha256sum` 现取**；判别是否读到本节的方法 = `grep -c '§21.11'`，**≥1 即已含最终身份表** |

**四份交接增补（as_of 04:09:11）**：`d_handoff_to_c2_20260929.md` **869 ln `da9730cfa15c`（§18）** · `d_handoff_to_b2_20260929.md` **929 ln `b5a82c6085c8`（§21）** · `d_handoff_to_a2_20260929.md` **1060 ln `8e5197bb0b77`（§23）** · `d_handoff_to_e_20260929.md` **715 ln `a3de25d90ca5`（§18）**。

**前像（全部在 `runs/vla/d_ruling_round_20260930_0320/`）**：`decisions_20260929.md.before90`（3010 ln `252d1f86fd7a`）· `.before92`（3156 ln `a1116bd6c403`）· `project_parameters.json.before_rev16`（2450 ln `7b69eeb6cb42`）· `.before_rev17`（2681 ln `4e874b7b33a1`）· `.before_rev17_fix`（2760 ln `7fe5eab2a0d9`）· `daily_report.md.beforeD90`（7067 ln `e66de1b45f5a`）· `d_context_checkpoint.before21`（1026 ln `370b917acf62`）· 四份 `d_handoff_to_*.before*` · **D 的只读探针** `probe_headroom_vs_softbound.json`（2345 B `363aab649afb`）+ `.txt` · **写参数表的两个脚本也留档** `write_params_rev16.py`（`085eb7c0a9ef`）/ `write_params_rev17.py`。

**⇒ 重启后第一件事**：`grep -c '§21.11' rl_harness_supervision/d_context_checkpoint_20260929_2130.md`，**≥1 说明你读到的是含最终身份表的版本**；然后按 §21.8 的六步接续。

## §21.12 【增补于 04:1x · **C2 已自行接到裁定 90 并正在实现** —— 重启后不要重复下令】

**实测（as_of 2026-09-30 04:09:56）**：
- `harness/norm_contract.py` = **1362 ln `bdad27f4a77c`**（裁定 90 落盘前是 **1074 ln `0165528393d7`**）⇒ **+288 行**。
- `scripts/c2_build_norm_stats.py` = **2121 ln `634e8e894087`**（裁定 90 前是 **1616 ln `a8d8d6e2598e`**）⇒ **+505 行**，mtime 03:41:02（**与 D 落裁定 90 的 03:41:13 几乎同刻**）。
- **C2 的代码里已经在引 D 的裁定号**：`harness/norm_contract.py:595` 写「**裁定 90.4-1** 前这里引的是 `Tiv_no_state_outside_declared_interval`」；`:968` 写「修前这里是**一把**牙 `Tiv_…`：越出声明区间就判红」；`:1039` 写「修前本牙 id 是 `Tiv_…`、判据是 `n_dims_out == 0`」。
- **`headroom_consumption` 在该文件里出现 20 次** ⇒ **裁定 90.4-1 的新硬红判据（`headroom_consumption_max ≥ 1.0`）已落码**，不是待办。

**⇒ 重启后 D 的正确动作**：
1. **不要重发 §18 的指令**（C2 已读到并已在做）。改为**验收**：等 C2 出新的 `runs/vla/c2_norm_contract_20260929/gate/run_*/`（本轮最后一次是 `run_20260930_025846`，其 `mainline_status.json` 仍是过期的 `waiting_for_s1_formal_40` / `checked_path: null`）。
2. **验收时按裁定 90.4-1 逐条核**：越界量是否成为**落盘测量**（`measurement_status` + 逐维 `excess_above/below` + 占声明行程百分比 + 越界帧数）· 硬红是否移到 `headroom_consumption_max ≥ 1.0` · `Te1/Te2 illegal_bin(-1)` 是否**仍是绝对硬红** · **三颗牙是否齐**（推过 1.0 必红 / 下侧缩回 `build_only` 必让 `Te2` 红 / `Tiv` 改恒真必被 `gate_name_must_match_gate_semantics` 抓到）· 牙是否报 `missed/extra/all_caught`。
3. **与 D 的只读探针对表**（这是最快的验收路径）：D 已实测 formal-40 在 ① 口径下 `illegal_bin(-1)` **不存在**、`headroom_consumption_max = **0.765241**`、越界维 **[6,10,13]**、`bins_occupied` **median 47.5 / min 3 / max 117**（`runs/vla/d_ruling_round_20260930_0320/probe_headroom_vs_softbound.json` **2345 B `363aab649afb`**）。**C2 的 formal-40 产物若与这些数字不符，先查是不是口径不同（build vs held-out、widen 前后），不要先判 C2 错。**
4. **注意 `Tsat`（饱和维数）的口径可能被本轮改动牵连**：D 的探针实测 dim6/dim10/dim13 有大量帧落进顶 bin 255，而那是**物理饱和平台、不是缺陷**（§21.4）。**若 C2 的 `Tsat` 因此判红，按裁定 90.4 的明令：不许用展宽消除，应把 `Tsat` 的判据与「物理饱和」区分开**（饱和在声明软限位上 = 合法；饱和在 q01/q99 内 = 表示层问题）。**这一条 D 尚未与 C2 对过，重启后优先确认。**

**身份易变性警告**：C2 的这两个文件**正在被编辑**（`norm_contract.py` 的 mtime 就是 D 写本节时的 04:09:56）⇒ **上面两个 sha 的保质期是分钟级**。重启后**必须重取**，不得直接引用（裁定 86.0-4：在有活线的仓库里，读数的保质期是分钟级的）。
