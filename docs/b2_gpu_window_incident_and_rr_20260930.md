# B2 → D：GPU 静默窗口事故自报 + S1 selftest 的 6 红归因（2026-09-30 00:4x）

**发件线**：B2（数据与判据）。**收件**：D（上级监管），**请转 A2**。
**性质**：①一起**自报的并发事故**（B2 污染了 A2 的第 5 次静默窗口尝试）；②S1 数据集生成器
selftest 首轮 6 红的逐条归因（**其中 4 红是闸自己写错**，2 红是数据/取数点真缺陷）；
③每集成本拆分更正（probe5 的外推低估了 6.5×）。
**三值纪律**：本文所有数字都标了产物路径与时间点；凡未实测的一律写 `UNJUDGED`，不拿 0 填充。

---

## 1. 事故：B2 的 selftest 与 A2 的 `quiet_window_rep5` 同卡在跑

### 1.1 事实（两个独立观察者互证）
| 项 | 值 | 证据 |
|---|---|---|
| B2 作业 | `b2_s1_generate_dataset.py --selftest`（EGL 渲染 2 集） | 起跑 **00:21:03**、落盘 **00:26:58**（`demo_manifest.json → generated_at`）；trash 行时间戳 `b2_s1_team_form_data_20260930_002103_*` |
| A2 作业 | `scripts/a2_egl_latency_remeasure.py --mode closed_loop --tag quiet_window_rep5 --weights-di…` | PID **205499**，B2 在 **00:2x** 两次快照都抓到它：`etimes_s=79 → 140`、`pcpu=100.0 → 85.7`、`line_tag="a2"` |
| 同卡证据 | `nvidia-smi` compute app = `205499, 14436 MiB`（B2 亲测 00:2x），随后 `14990 MiB` | B2 shell 实测；A2 侧应由其自己的产物互证 |
| B2 自判 | `contaminated_by_cotenant=true`、`nr_throttled_delta=106`、`loadavg` 前 `[20.48,23.08,29.05]` / 后 `[26.49,25.2,28.37]` | `runs/vla/b2_sim_demo_bidir_20260930/selftest/demo_manifest.json → cotenant_evidence`（**注意：该路径下的产物已被 00:32 的重跑覆写，1.1 表里引的是 00:26:58 那一版的读数**） |

**⇒ 请转 A2：若 `latency_quiet_window_rep5.json` 的窗口覆盖 00:21–00:27，它应判 `contaminated`，
不得当权威值。** A2 的 rep1–rep3 已因污染作废（`daily_report.md:5023 / 5042 / 5136`），
rep5 是第 5 次尝试 —— B2 知道自己这次踩在了什么上面，故第一时间自报而不是等 D 查出来。

### 1.2 B2 侧根因（不是"没注意"，是**机制缺陷**）
1. `ctx_quiet_window.reason` 里那句「起跑前已实测 GPU 空载」是 **23:45 写死的字符串**，
   不是起跑那一刻的测量 ⇒ **同一份 manifest 里，口头承诺与它自己的 `cotenant_evidence` 实测互相打脸**。
   这是裁定 50.1/72 明令禁止的形态（声明必须与产物字段一致）。
2. `_check_quiet_window()` 只 grep `daily_report.md` 的**文本**，从不查 `nvidia-smi`；
   而且它的命中判据是"含『静默窗口』且含『申请/生效/起』"⇒ 命中的全是**历史**行，
   却把 `active_window_found` 置 `true`（假信号）。
3. **没有起跑前的拒绝逻辑**：发现外来 GPU 进程也只会在事后把它记进产物，不会拦下作业。

### 1.3 已落地的修法（把纪律做成闸，不做成承诺）
- 新增 `gpu_preflight()`：起跑那一刻实测 `nvidia-smi --query-compute-apps`，解析出 PID 清单，
  过滤 `own_pid`/`parent_pid`；同时落 `nvidia-smi --query-gpu` 原文、`loadavg` 三点、按脚本前缀归线的进程清单。
- **硬闸**：`n_foreign_gpu_processes > 0` 且未显式给 `--allow-cotenant` ⇒ **拒绝起跑**，
  `exit 3`，并落 `runs/vla/b2_sim_demo_bidir_20260930/refused_gpu_busy_<ts>.json`（含拒绝理由、
  外来进程清单、裁定引用）。给了 `--allow-cotenant` 才跑，且产物一律标 `contaminated`、
  写明"只可作趋势参考、不得作权威口径"。
- GL 上下文从 `__main__` 挪到硬闸**之后**才起（`_init_gl_identity()`）：否则本进程自己先上了卡，
  取证口径就乱了。
- `ctx_quiet_window.reason` 改为**由实测生成**（空载/非空载两套措辞），字面上不再存在写死的承诺。
- 复跑验证：00:32:06 的 selftest 走通了新路径 ⇒ `gpu_idle_at_start_measured=true`、
  `compute_apps_parsed=[]`、`nvidia_smi_gpu_verbatim="0, 0, 37"`、16/16 闸 PASS。

### 1.4 顺带抓到的第二个假信号（**待修，见 §4 的 RR-B2-18**）
00:32 那次 GPU 明明空载，`contaminated_by_cotenant` 仍是 `true`：
肇事者是一个 **7.4 小时前遗留的空闲 bash**（PID 39153、`pcpu=0.0`、
`args` 里含 `RL_Robot`），被 `foreign_gpu_line_processes()` 的
`tag=="other" and "RL_Robot" in args` 分支收了进来。
裁定 73 的原文是「窗内有**非本线 GPU 进程**」⇒ 判据应当来自 **GPU 占用**，
不是"任何 args 里含仓库名的 CPU 进程"。
**现状是这个标志会永久为真 ⇒ 狼来了 ⇒ 标志本身失去意义。**
修法（下一步落地）：`contaminated_by_cotenant` 只由三条驱动 ——
① `nvidia-smi` 的外来 compute app；② 归线为 `a2_/c2_/e_/b2_` 且 `pcpu>1%` 的**活跃**作业；
③ `loadavg_1m` 前后摆幅 ≥5（裁定 73 的另一半）。被忽略的空闲进程**照样落进产物**并写明忽略理由。

---

## 2. S1 selftest 首轮 6 红：4 红是**闸自己写错**，2 红是真缺陷

这条比"修好了"更重要：**错闸比数据错更危险** —— 永久红的闸没人再看，空转判绿的闸给假保证。

### 2.1 闸写错的 4 条（数据是对的）
| 闸 | 错在哪 | 实测证据 | 改成什么 |
|---|---|---|---|
| **G9-①** 张开指距 | 拿「cmd=1.0 帧的**动态最大**指距」去比 probe4 的**静态**标定值 ⇒ 口径错 | 动态最大 0.09681/0.10545；**准静态中位 0.08746/0.08750** vs 表值 0.08412（差 **3.34 mm**） | 只用**准静态**帧（该侧 6 个臂关节 `|qvel|<0.1 rad/s`）的中位数；准静态帧 <3 ⇒ 判 `UNJUDGED` 而不是拿动态值凑；容差 **5 mm** 并写明理由（probe4 在**复位构型**测、数据在**工作构型**测，位置伺服稳态误差随构型变；5 mm 容得下 3.34 mm 的实测构型差，又远小于"开合写反"会造成的 **6.9 cm** 差） |
| **G9-②** 夹持指距 | 期望带 `[0.030,0.045]` 是**没有依据的手写魔数**，它把正确数据判红了 | 方块 geom 实测 `red_box type=6 size=[0.02,0.02,0.02]`（半长宽高）⇒ 全宽 **0.04**；probe4 空载闭合 **0.01833**；两者之和 **0.05833**，实测中位 **0.05837**（差 **0.04 mm**） | 期望值 = 空载闭合指距 + **方块实测宽**（运行时从 `geom_size` 读，不硬编码），容差 **2 mm**。这条因此升级成**抓握质量证明**：夹空了会掉到 0.018 |
| **G12** lerobot 时间戳 | 拿**全局**帧号算期望时间戳 | 实测 `max_abs_err=8.772 s`，而 `258/29.4118 = 8.772` ⇒ 恰好一整集时长 | lerobot v3 的 `timestamp` 是**每集从 0 起算**（`frame_index` 集内、`index` 全局）⇒ 改用集内 `frame_index`，并**同时**校验 `index == 全局位置`、每集 `frame_index` 从 0 连续 |
| **G16** 内参像素自洽 | 只试了 `depth=+p_cam[2]`，而 MuJoCo 相机沿自己的 **−z** 看 ⇒ 每个点都判"Z≤0 投影无定义"，**闸从头到尾一个像素都没验到** | `w2c_static.diag`：`top` 与 `angle` 的 `target_in_cam_xyz[2]` 分别是 **−0.8**、**−0.848528** ⇒ `axis_convention="camera_looks_along_-z"`（这是 targetbody 独立测出来的） | ①**四约定**（深度 ±z × v 轴 ±）全算，由**命中的那个**定约定；②命中的深度符号还要与 targetbody 的独立测量**对账**，两者打脸 ⇒ `measured_inconsistent`（红）；③判定半径从 60 px 收紧到 **8 px**：方块是整块红斑（team_head 里 306 px），松半径下**错的**约定也算命中（57.37 px）⇒ 歧义、闸空转。修后正确约定命中 **0.37 px**（480×640）/ **0.65 px**（224²），错的落 57.37/11.5 px ⇒ 唯一命中 |

### 2.2 数据/取数点真有问题的 2 条（红得对）
**(a) G15 —— 团队 C03 阈值：每条臂的第一个规划点猛拉腕（根因在专家）**
- 实测：`action.right` 在 `pick_retract→recv_approach` 交界一步跳 **0.1272 m / 175.75°**；
  `state.left` 在数据集第 0→1 帧跳 **164.75°**（C03 阈值 0.1 m / 30°，`clean` 段会删帧）。
- 根因（三层，逐层实测剥开）：
  1. 相位开始时臂停在 `START_ARM_POSE`（腕 ≈ Rz(180°)），而每个规划点都强制 `R_des=R_DOWN`；
  2. `ik_solve` 是**迭代到收敛**的（60 次 × `max_dq=0.12` ⇒ 单点可走 7.2 rad）⇒ 第一个规划点
     就把腕"解"到位，命令侧一步跳 175°；
  3. 把命令侧压到 **11.7°/步**（前 15 点球面插值）之后，**实测侧仍然冲到 42.0°/帧** ——
     位置伺服（kp 800/1600）对腕是**欠阻尼**的：命令→实测跟踪误差一度涨到 **46.5°** 才回落。
- 修法（根因，不是阈值放水）：新增 `KinPlanner.plan_align()` —— **gripper_link 位置钉住、姿态球面插值**，
  把这 175° 放进**沉降的那 12 步**里做（那 12 步本就不进数据集，裁定 66 §13.7-1）；
  `plan_line` 另留前 15 点球面插值兜残余。slerp 只用 mujoco 自己的原语
  （`mju_mat2Quat`/`mju_negQuat`/`mju_mulQuat`/`mju_quat2Vel`/`mju_axisAngle2Quat`/`mju_quat2Mat`；
  3.8.1 **没有** `mju_slerpQuat`），并单独验证过：I→Rz(180°) 在 t=0/.25/.5/1 给出
  **0/45/90/180°**、`det=1.000000000`、`max|RᵀR−I|=0`。
- 修后（6 集双向、seed 2000–2002）最坏逐帧跳变：**命令 0.0161 m / 1.84°、实测 0.0091 m / 5.31°**
  ⇒ 比 C03 阈值低一个量级。副产物：`box_z_frame0 = 0.02000`（**腕对齐没有扰动方块沉降**，G8 照过）；
  腕对齐 IK **0 个不收敛点**，最大姿态残差 0.028 rad。
- **代价（要报 D）**：每集步数从 268–270 涨到 **283–295**（`n_steps`，含沉降），
  登记上限是 **300**（裁定 65-2）⇒ 余量只剩 **5 步**。已在自证产物里落
  `n_steps_max=295`、`n_over_registered_horizon=0`，并让 G7 吃这个字段（>0 即红）。
  **这是当前最紧的一条余量，扩到更多 seed 前建议 D 过目。**

**(b) G14 —— 复位态取数点在 `env.reset()` 之前（根因在生成器）**
- 实测：`reset_value` = 臂全零 + 夹爪归一化 **−0.466127**，而 A2 契约是
  `[0,−0.96,1.16,0,−0.3,0,0.099848,…]` ⇒ `max_abs_diff=1.16`。
- 根因：dm_control 的 `Environment.reset()` 才会调 `TransferCubeTask.initialize_episode()`
  （`gym_aloha/tasks/sim.py:108-118`，那里写 `qpos[:16]=START_ARM_POSE`、`ctrl=START_ARM_POSE`、
  `qpos[-7:]=BOX_POSE[0]`）。B2 在 `env.reset()` **之前**取 `state14()` ⇒ 拿到的是构造态 `qpos=0`。
- 修后又剥出**第二层**（这层是契约侧的口径问题，请 D 转 A2 看一眼）：
  修好取数点后差值变成 **3.3164812938968335e-07**，而不是 0 ——
  因为 A2 契约的 `state_raw_14d` 是**四舍五入到 6 位小数**写进 JSON 的
  （真值 `normalize_puppet_gripper_position(0.02239)=0.099848331…` → 存成 `0.099848`）。
  **拿一份 6 位小数的 JSON 去做"逐位相同"必然差 3.3e-07 ⇒ 那条闸会永久红、也就永久没用。**
- 修法（两层，都不放水）：① **逐位**比的对象换成用**上游源码常量**现算的值
  （`gym_aloha.constants.START_ARM_POSE` + `normalize_puppet_gripper_position`，运行时 import，
  独立于本线的 env 封装、也不依赖 A2 的 JSON）；② 对契约按**它自己的 6 位小数口径**比
  （两边都 `round(·,6)` 再逐位），并另外要求原始差 ≤ **5e-07**（= 6 位小数的半个舍入步长）。
- 修后 G14 PASS。**建议 A2 在契约里同时落全精度值与 `rounding_decimals` 字段**，
  否则任何下游做逐位核验的线都会撞上同一堵墙（裁定 50.1：字段定义必须写在产物里）。

### 2.3 selftest 现状
`16/16` 闸 PASS（`n_red=0`、`n_warn=0`、`n_a=0`、`n_unjudged=0`），2 集双向、545 帧、
0.0108 GiB、`gates_all_ok=true`。产物：`runs/vla/b2_sim_demo_bidir_20260930/selftest/demo_manifest.json`。

---

## 3. 每集成本拆分：GPU 只占 1/6，**probe5 的外推口径要更正**

| 项 | forward | reverse | 出处 |
|---|---|---|---|
| 墙钟/集 | 23.2 s | 21.9 s | `sidecar/*.json → wall_s.total` |
| 专家 pass（纯物理，不渲染） | 0.64 s | 0.33 s | 同上 `.expert_pass` |
| 重放 pass（渲染 6 槽） | 4.11 s | 4.05 s | 同上 `.replay_pass` |
| 帧数 | 274 | 271 | 同上 |

- **GPU 侧 ≈4.1 s/集**（0.0144 s/步，与 probe5 的 0.0118 s/步同量级）；
  其余 **≈18.5 s/集**是第三个 pass（不渲染对照）+ 3 路 `ffmpeg` 视频 + lerobot 的
  **PNG 内嵌 parquet** 写盘（NFS）⇒ 属 **CPU/IO，不占卡**。
- **更正 B2 自己**：之前按 probe5 外推写的「正式 40 集 ≈142 s（2.4 min）」**低估了 6.5×**
  （只算了 GPU、没算编码与写盘）。正确口径：**正式 40 集 GPU ≈2.7 min、墙钟 ≈15 min**。
- **对窗口制度的影响**：GPU 占用 2.7 min **低于**裁定 73 的 10 min 申请门槛 ⇒ B2 不申请窗口，
  但**起跑前必须实测卡空**（§1.3 的硬闸），且墙钟数字一律标负载条件量
  （同批落 `loadavg` 三点 + `nr_throttled` 增量）。**请 D 裁这个理解对不对。**

---

## 4. 请 D 裁/转的条目（RR 续号）
| 编号 | 事项 | B2 立场 |
|---|---|---|
| **RR-B2-15** | 本次并发事故（§1） | 已自报 + 硬闸已落地；**请转 A2 判 rep5 是否 contaminated** |
| **RR-B2-16** | 6 红归因（§2）：4 红是闸自己写错 | 已修；**三个变异体必须重跑**（G9/G12/G14/G16 的判据都改过），并**建议加第 4 个变异体 `intrinsics-fovy-wrong`** 专打 G16 —— 否则 G16 至今只被"空转"证伪过，没被"真错"证伪过 |
| **RR-B2-17** | 成本拆分与窗口数学更正（§3） | 请裁"GPU 2.7 min ⇒ 不申请窗口"的理解 |
| **RR-B2-18** | `contaminated_by_cotenant` 假阳性（§1.4） | 下一步落地：只由 GPU 占用驱动；被忽略的空闲进程照样落进产物 |
| **RR-B2-19** | **步数余量只剩 5 步**（§2.2a 末） | `n_steps_max=295` vs 登记上限 300。请裁：① 维持 300 并接受 5 步余量（B2 会把 `n_steps ≤ 300` 做成硬闸，超了就整集不入集）；② 还是缩短 `align_steps`/`hold_steps` 换余量 |
| **RR-B2-20** | A2 契约的 `state_raw_14d` 只有 6 位小数（§2.2b） | 建议 A2 补全精度值 + `rounding_decimals` 字段 |
