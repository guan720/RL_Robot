# D → A2 执行单（2026-09-30 10:4x · S4b 与 S3 BC 入口 · 裁定 93 之后）

**性质**：派工。E4 已裁（`work/decisions/decisions_20260929.md` §93，**3350 ln `287763dc0d15`**）、参数表 rev18（**3052 ln `8f32e1388d80`**）。
用户 10:0x 明示「**速度优先**」⇒ **BC 前置已清零**（C2 的 T-C2-8 已预授权一次通过）。
**S4b 不依赖 C2 的极性改判 ⇒ 现在就开工，与 C2 并行**（顺序约束 `params:497` 的前三步都已落地：B2 的 npz ✓、C2 的主线 stats ✓、C2 的 env 判定层 ✓ 且经 D 亲跑复验接受）。

---

## 一、T-A2-6（P0 · 需 GPU）：S4b = 四类判定接 `ledger`

**判据（照 `params:1047` 的 S4 拆段原文，不重新解释）**：四类判定接 `ledger`，**独立于 `reward==4`**，不一致即红。
**必须复用、不得自造**：`harness/env_gym_aloha.py`（**579 ln `6c4d71eb732e`**，`MODULE_REPRESENTATION_VERSION='c2-env-gym-aloha-v1'`）+ 闸 `scripts/c2_gate_env_gym_aloha.py`（`c9100b3811cd`）—— 该模块经 D 亲自复跑 offline 档 `PASS/15/red=[]`，**已被指定为 S4b/S5 的 env 判定层**；自造判定层 = 与 J1–J15 分叉。

**同批必须做的三件（都是一次上卡就能顺带完成的，不要为它们单开窗口）**
1. **运行时 `-1` prompt 牙**（§23.2）：`processor_pi05.py:77` 的结构不对称 —— `x ≥ 1 → bin 255`（合法饱和），`x < −1 → bin −1`（**非法 token 静默进 prompt**）。牙必须在**运行时**（不只是离线 stats）证明：任一维出现 `-1` ⇒ 红。
2. **`pad_vector` 的缺口按 `not_measured` 登记**：D 未测过这一维，**不得假设安全**（三值纪律：空集 → `null` + 非零退出，不许写 `false`/`0`）。
3. **照常落 `renderer_class`**（起点 + 运行内 + 终点三处，终点若未在运行内测就写 `null` 并标 `measurement_kind`，**不许拿起点值顶替**）⇒ 这构成 E 的 **C4 复验第三方证据**（`params:1412`：搭便车、不单开窗口）。若回 `nvidia_gpu`，即证明 E 的前缀改动无害。

**GPU 纪律（照旧，一条都不豁免）**：事前申报 quiet window（裁定 73 模板）· **A2 优先级最高（A2 > B2 > C2 > E）** · 三网占用判定（GPU util+memory / fd 网 / compute-apps）· `per_batch_gpu_yield_gate` · 每个吞吐/延迟数字成对引 `loadavg`(3 点) + `nr_throttled`（cgroup 12 核，`nproc=112` 是假象）。

---

## 二、T-A2-7（P0 · 紧随 C2 的 T-C2-8）：S3 BC 入口按裁定 93.4 落

**硬要求（D 会亲核代码，不采信文书）**
1. **不得只读** `admissible_for_bc` / `not_for_bc`。这两个字段是**纯标签派生、对数据质量盲**（`harness/norm_contract.py:478` 的 `bc_admission()` 只判 `prov in BC_ADMISSIBLE_PROVENANCES`，`:134`）。本轮**实测存在过**「`admissible_for_bc=true` 而同一批数据 matrix=RED」的状态。
2. **必须 AND** C2 新增的 `gate_verdict_green`，并**自己复算一次**闸产物（`gate_verdict.json`）的 `sha256[:12]` 与 C2 声明值对账。
3. **不一致 ⇒ `LearnerRefused`**（不是继续、不是只告警）。变异体两向：喂一个 `verdict=RED` 的 run 目录 ⇒ 必须拒；喂 C2 本轮权威跑 ⇒ 必须放行。

**数据口径（不许混）**
- **权威读路径 = `npz + --s1-frames`**（裁定 86.0/86.1/90.4-4）：`runs/vla/b2_states_14d_20260930/formal40/states_14d.npz`（**1332184 B `a84a26079550`**，40 集 / 11035 帧 / `[11035,14] float64`）；frames content sha **`c9a72480fcb7`**（D 亲测 + C2 独立复算相符）。
- `--s1-lerobot` 档标签 = `formal40_lerobot_crosscheck`，**`admissible_for_bc=false`**，**只作交叉核对**，喂进 BC ⇒ `Tp5` 必红（这是设计，不是 bug）。
- **同源硬闸**（裁定 85.4-3）：pilot 10 集与 formal 40 集不是同一批数据，stats 不得互替。
- **同频纪律**（`params:119`）：S1 示范 / S3 BC / S5 评测 / S6 RL 采样**必须同值 `29.4118 Hz`**（`DT=0.034` = 17 × 0.002），跨值不得并列。
- `timeout_isolation_scope=td_only` 的三条硬约束（裁定 83.7-2）：① 每条被保留的 BC 记录带 `truncated_by_timelimit=true` 且 `representation_version` 里出现 `timeout_bc=kept_flagged`；② **不得**把 truncated 末帧当 terminal；③ **必须有变异体**证明「把 truncated 当 terminal」会被判红。

---

## 三、T-A2-8（P1 · **必须在 BC 开跑之前落盘**）：结果口径预登记

**跑完再定判据 = 无效判据。** 开跑前先把下面五件写进 `runs/vla/a2_s3_bc_*/CRITERIA_PREREGISTERED.json`：
1. **三分开统计**（v4 要求，缺一个都不算跑通）：**策略自主成功率**（不计接管）· **系统最终完成率**（允许恢复与接管）· **干预率**（每任务需多少外部帮助）。
2. **双向独立评测**：同一个目标条件模型跑正、反两个方向，**分别报数**，不许合并成一个成功率。
3. **对照臂**：与**同预算、持续吸收纠正数据的动态 BC** 比较（v4 明确要求；否则无法回答「RL 是否真的比继续 SFT 更好」）。
4. **失败面归因分类**：识别 / 接近 / 抓取 / 搬运 / 释放（v4 第一阶段闭环的入口是「抓空 → Harness 同协议纠正 → 数据+BC → 一次 RL 更新 → 双向无动作辅助评估」，没有归因就接不上后面三步）。
5. **裁定 46 解禁点**：BC 出结果**之后**才允许出现任何能力表述；表述必须带 **n、seed、区间、`loadavg` + `nr_throttled`**，单样本不许写成率。

---

## 四、边界与账

- 不改 C2 / B2 / E 的文件；发现缺陷**报 D 与所属线**，不代改（C2 的 E2 就是这么来的，记了大功）。
- 不 `git commit`（单写者 B2）；不用 `rm`（走 `recycle_bin`）；`RL_Harness_v4_20260924/` 只读。
- **能力声明禁令不变（裁定 46）**：`success=80/0`（先导）与 formal-40 的专家自证都是**脚本专家自证**，不是 policy 能力。你手上的 zero-shot **0/20**（`runs/vla/a2_pi05_zeroshot_20260929/summary_pi05.json` **1641 ln `53be865bbb22`**）已按「非能力结论」登记，**不许被引用成"模型不行"或"模型行"**。
- 延迟带权威值不变：主线 n=25 `budget_fraction` **0.8009(rep4) / 0.7766(rep5)**、`ms_per_ctrl_step` **27.230 / 26.405**、`all_episodes_within_per_step_budget=true`；rep1（1.3466）`contaminated` 不采纳。BC 之后若改 chunk/推理步数 ⇒ **另立 `representation_version`**，不许沿用这条带。

---

## 补单（裁定 94 · 2026-09-30 11:3x 追加；**上面原件原字节保留**）

### 一、GPU 仍空转，**你的窗口优先级最高**（as_of 11:19:56：GPU `0 %` / `0 MiB`、`compute-apps` **0** 行）

**过渡协议即刻生效（登记处脚本还没落地，但 S4b 不等它 —— 缺下面 ③④ ⇒ D 不认该窗口的延迟/吞吐数字，裁定 84.7 同族）**
1. 起跑前在 `daily_report.md` 申报（裁定 73 模板）。
2. **起跑那一刻**实测三网：`nvidia-smi --query-compute-apps` + **fd 网**（持 `/dev/nvidia*` 的外来进程）+ **cmdline 网**（按脚本前缀归线）。
3. 在自己 run 目录落 **`GPU_WINDOW.json`**：`start` / `end`、三网原文、`loadavg` **三点**、`nr_throttled`（**cgroup v1 路径 `/sys/fs/cgroup/cpu/cpu.stat`**；v2 路径本机不存在）、外来进程清单、`contaminated` 判定。
4. **必须有起跑前拒绝逻辑**（B2 的 `gpu_preflight()` 是参考实现）：`n_foreign_gpu_processes > 0` 且未显式给 `--allow-cotenant` ⇒ **拒绝起跑 `exit 3`** + 落 `refused_gpu_busy_<ts>.json`。**「起跑前已实测 GPU 空载」这类写死的字符串一律无效**（裁定 50.1/72）。
- 顺带：本机现有两个遗留 `find /` 在跑（PID **39199** `etimes ≈ 18.2 h`、PID **128128**），D 已判由 B2 / 发起线终止。**你自己不要跑 `find /`**（新纪律 `no_root_filesystem_scans`：扫描限定前缀，>60 s 视同上卡作业须申报）。

### 二、你已经在盘的那件，D 认可（`harness/prompt_bin_guard.py` **678 ln `ab5bbc4768ba`**）

- **写入面划分正确**：明写不改 `harness/contracts.py` / `ledger.py` / `norm_contract.py`（C2 的写入面）/ `lerobot/**`；bin 常量与 `norm_contract.py:63/:93/:94`（`N_BINS=256` / `SAT_BIN_HIGH=255` / `SAT_BIN_LOW=-1`）**同值不另立**；自带裁定 93.8 的 `pattern_coverage_probe()`。
- ⇒ 与 C2 的**离线**牙（`Te1`/`Te2` 判归一化后的数组）是**互补而非分叉**（你判的是真正拼进 prompt 的文本）。**要求**：在移交件里给 C2 一个指针，并在产物里登记一句「本件不另立 bin 常量口径」。

### 三、身份口径更正（外部分析有一半说错了，别照着改）

- **npz 身份不受 E4/裁定 94 影响**：`runs/vla/b2_states_14d_20260930/formal40/states_14d.npz` = **1332184 B `a84a26079550`**（40 集 / 11035 帧 / `[11035,14] float64`），frames content sha **`c9a72480fcb7`**。**这是 B2 的数据，不是 C2 的 stats。**
- **会变的是 C2 的产物**（T-C2-8 重跑后）：stats 档（现 **823 ln `b8d825dfaa6b`**）、`matrix.json`、`mainline_status.json`、`gate_verdict.json`（现 **1534409 ln `ae4e16c33743`**）。⇒ **T-A2-7 的 BC 输入清单必须指向 C2 重跑后的新 stats，并自己复算 sha 对账（93.4）**；**npz 那一行不要换**。

### 四、T-A2-7 / T-A2-8 的两点补充

1. **BC 入口的 AND 现在还没有码**：D 亲核 `harness/norm_contract.py:478` 的 `bc_admission()` **当前仍只判 provenance 标签**（`prov in BC_ADMISSIBLE_PROVENANCES`），C2 的 `Tbcad_admission_requires_green_gate` 也还没落。⇒ **你不得只读 `admissible_for_bc`**；等 C2 的四个新字段（`gate_verdict` / `gate_verdict_green` / `gate_run_dir` / `gate_verdict_sha256_12`）落盘后 AND 上它 + **自己复算** `gate_verdict.json` 的 `sha256[:12]`，不一致 ⇒ `LearnerRefused`。
2. **任何 BC / 评测结论都必须带这句限定**：正确性族（held-out 口径）在 **`[0,3,5,7,10,12]` 六维上是 `not_measured`**（裁定 94.3/94.5 的代价，写在脸上）。**偿清之前不得写「归一化器已通过正确性验证」**（红线 `absence_of_measurement_is_not_measurement_of_absence`）。
- **T-A2-8 的预算问题**：SFT 预算上限（建议 1×A800、≤24 h）**仍待用户**，但**BC 开跑前不需要** ⇒ **不要等它**；预登记里把预算写成参数（`budget_gpu_hours: null` + `measurement_status="not_measured"`）即可。

---

## 补单二（**裁定 95 + 96** · 2026-09-30 12:1x 追加；**原件与补单一原字节保留。凡与补单一冲突，以本节为准**）

### 一、方向已重排：旧关键路径（S4b → S3 BC）**让位**给用户的六步序列

用户 11:4x 的方向输入 = 本轮最高权威。**新关键路径 = 六步，顺序不许重排**（细节在 `decisions_20260929.md` §95.2，机器可读在 `work/project_parameters.json` rev20 的 `ruling95_critical_path_six_steps_rev20`）：
**1** 小量示范过拟合 + 动作/夹爪/时间对齐 + **从示范初态闭环执行** → **2** **标准同步执行**下的正式 BC/SFT、**≥3 种子**、正反向**分别**评估 → **3** **同 ckpt、同初态**配对比较（标准执行 vs 现有 Harness 调度）→ **4** 加受限脚本恢复、分开统计自主/救场 → **5** 用纠正数据更新、**关闭恢复**重测 → **6** **同预算**动态 BC vs BC+RL。**你是第 1–3 步与第 6 步的主责，第 4–5 步与 C2 共担。**

### 二、你的停点（**本轮不发新单**）

- **把 S4b 的准备收到「标准同步执行通路能跑」这一件** —— 它是第 1–3 步的**共同前置**，也是本轮唯一必须新增的运行时能力。
- **不要为旧关键路径上卡跑长作业**；`harness/prompt_bin_guard.py`（Ⅰ 类）继续完成。
- **第 1 步开跑前只等两件**：① C2 重跑后的新 stats 身份（完整路径 + sha + `as_of`）· ② E 修完 `card_busy()` 的文本误触发（裁定 96.1-③，P0.5，**就是为了让你的第一个上卡窗口不被误判 `contaminated`**）。**两件都不需要用户裁定、不需要新单。**
- **上卡前必须按 94.9-1 的过渡协议申报**（申报 + `GPU_WINDOW.json` + 起跑前拒绝逻辑）。**协议不冻结**（它是 Ⅰ 类），冻结的只是 T-B2-21 那个脚本。

### 三、**裁定 95.3-④：第 1–2 步一律用标准同步动作块执行**（这条直接改你的运行时口径）

现运行时 `execution_mask = bc_mask = [0,0,1,1]`，模型输出 50 步而**只执行 idx 25–49**、帧 0–24 是 prime hold。**问题不在时间对齐、在状态对齐**：**f=25 时的真实状态是「保持了 25 步」的状态，不是「执行了 idx 0–24」的状态**，而 idx 25–49 是对后者预测的。⇒ **`H ≥ 2n`、索引正确、账本一致只证明调度符合自己定义的规格，不证明策略预测与实际轨迹一致。**
**记录里没有「模型以已承诺动作前缀为条件」的证据 ⇒ D 不断言实现一定有错**，但：**第 1–2 步用标准同步执行**；**第 3 步才把「标准执行 vs 现有后半段调度」做配对比较**（同 ckpt、同初态、同 seed 序列，差值与每种子散布一起报，**两种执行的数字不得互搬**）。若第 3 步显示后半段调度显著更差 ⇒ 登记为 `v4_deviation` 并给修法。**不许让「策略训练失败」与「运行时改变执行语义」混在一个结果里。**

### 四、**裁定 95.3-①：四个字段分开记，不许再合并成一个 VALID/INVALID**

`measurement_reliable`（记录/计时/判定是否可信）· `interface_conformant`（接口是否符合预期方法）· `out_of_distribution`（**只标注、不剔除**）· `task_success`。**能力统计必须包含 OOD 样本**并单独报其比例。**旧口径「输入越界 ⇒ 测量无效、成功率不得引用」是错的**（它造成选择偏差：表现差、越界多的策略被剔除，留下的统计更好看）；**只有 (a) 输入预处理错/动作单位错配才该判无效**。**ACT 线的那条规则不得再被引用**（其历史判词不改，作废永不改名同族）。

### 五、**裁定 95.5：数据与统计纪律五条（全部 Ⅰ 类）**

① **按整条 episode 划分训练/验证**，**最终测试用新的物体初始状态**；② **stats 与阈值一经第 1 步开跑即冻结**（94.4 的留出集升级排第 2 步之后，换完必须重划一份从未被看过的 test split）；③ **模型选择用验证集、最终报告用另外的测试集**，**不得从多个 checkpoint 里挑最高成功率再把同一批评测当最终成绩** ⇒ **checkpoint 选择规则必须在开跑前预登记（与 T-A2-8 同批）**；④ **全量 bin 占用数只描述覆盖，不能证明每维信息足以支撑控制、也不能替代闭环评估**（低 bin 数可能只是任务不需要该关节运动）⇒ **94.3 的 blind dims 属 Ⅱ 类，不得当能力判据**；⑤ **行为级目标条件对照（第 2 步必须带）**：正反任务初态如果天然不同，模型可能只靠图像判断方向、**完全忽略语言目标** ⇒ 必须在**同一场景**下**交换 prompt**，检查行为是否相应改变（现有的 T17 goal 贯通自证只证明 `goal_id` 在契约里流通，**不等于行为级受目标控制**）。

### 六、**裁定 96.1-④：T-A2-7 的对账口径收紧**

**只对 C2 声明的那一条完整路径复算对账**，对不上 ⇒ `LearnerRefused`；**不许自己 `glob` 后挑一份**。实测已存在**两份同名 `mainline_status.json`**（顶层 `fc3f049753bf` vs 臂内 `82fc52f60782`，**行数与字节数全同、sha 不同**），T-C2-8 重跑后还会再变一轮。**BC 消费口径 = 最新一次 PASS 闸跑的臂内件**。**第二道锁已在码里**：C2 的 `Tbcad_admission_requires_green_gate`（准入必须 AND 闸 verdict）。

### 七、账

- **主任务纠偏（裁定 95.4）**：`AlohaTransferCube-v0` 与 formal-40 **保留为冒烟基准**（不重采、不作废，第 1–3 步就在它上面跑）；**能力里程碑回到「单臂把物体从 A 放到 B、再从 B 取回 A，另一臂固定」**（B2 的新示范排第 2 步之后）。⇒ **交接任务上的任何数字不得写成「单臂区域抓放能力」**；**reset-free 必须实测**（正向实际终态、不经摆物体或 reset，能否直接作反向起点）排在第 4 步；**14 维动作空间相同 ≠ 形态等价**（新红线 `same_action_dim_does_not_imply_same_morphology`）。
- **汇报格式改为六问**（裁定 95.6）：① 本轮验证了什么假设？② 相比哪个固定基线、只改了什么？③ 正反向独立成功率分别多少？④ 失败主要发生在哪一步？⑤ Harness 接管了多少次？⑥ 更新后关闭接管是否变好？**日报增量 ≤120 行/轮**（94.9-3 已升为硬口径），超出落你自己的 `docs/` 或 run 目录、日报只留指针。
- **能力声明禁令不变（裁定 46）**：**≥3 种子是开发阶段最低要求、不是统计充分性声明**；每个种子单独报数，不许只报均值、不许挑最高。**policy 指标目前仍 = 0，第 1 步出结果前不得出现任何能力表述。**

---

## 补单三（裁定 97 + §97.7 · 2026-09-30 13:1x · 前像 `runs/vla/d_ruling_round_20260930_1205/before_images/d_handoff_to_a2_20260930.md.before_r97` = 123 ln `8b08e087763a`）

### 一、**闸已转 PASS，且 D 亲核为「修前向」**（补单二 §六 里「重跑后还会再变一轮」的那一轮已经发生）

- **当前权威闸跑 = `runs/vla/c2_norm_contract_20260929/gate/run_20260930_125721`**：`gate_verdict.json` = **PASS / `n_checks=54` / `n_red=0` / `n_warn=0` / `n_n_a=0`**，**94,852,438 B / 1,896,737 ln / `fbf80622259f`**（`generated_at = 2026-09-30T13:04:45+08:00`；D 本机取值 as_of 13:07:35）。
- **D 的合规核查**：12:53(RED) 与 12:57(PASS) 两轮**全部 54 条 check** 的 `required`/`red_when`/`note`/`blocking`/`applies_when`/`triage_class`/`mutant_that_proves_it` 逐字段比对 ⇒ **差异 = 0、无增删**（`runs/vla/d_ruling_round_20260930_1205/d_verify_gate_pass_1304.json`）。**⇒ 不是弱化判据换来的绿**；`G14` 已拿到实测翻转（`flip_measured=True` 38 → 39）。
- **你等的两条身份（等 C2 广播确认后以广播为准）**：臂内件 `…/run_20260930_125721/arm_mainline/mainline_status.json` = **`4d7489b80d83` / 6714 ln / 208021 B**（12:57:48）**∧ 同轮** `gate_verdict.json` = `fbf80622259f`。

### 二、**T-A2-7 的对账口径再加一条（裁定 97.7）**：**必须成对，缺一 ⇒ `LearnerRefused`**

- **D 实测**：臂内件的 `bc_admission` = `gate_verdict: null` / `gate_verdict_measurement_status: "not_measured"` / `gate_verdict_green: null`。**这不是 C2 的过失**（臂内件在 `gate_verdict.json` 之前产出，顺序所致），**三值纪律也是对的**（没有静默当绿）。**后果：臂内件自己证明不了「闸绿」。**
- **⇒ 你不得只凭臂内件里的 `admissible_for_bc=true` 开跑**；对账要同时校验「臂内件身份」与「同轮 `gate_verdict.json` 身份 + `verdict`」。**顶层 `runs/vla/c2_norm_contract_20260929/mainline_status.json` 目前是 06:04 的旧件（`fc3f049753bf` / 6445 ln），与臂内件已分叉 ⇒ 一律不消费顶层件**（裁定 96.1-④；C2 正被要求补标记）。
- **数据身份未变（D 复算，不是转抄）**：`runs/vla/b2_states_14d_20260930/formal40/states_14d.npz` = **`a84a26079550`**，与两份记录里的 `checked_path_sha256_12` 一致（40 集 / 11035 帧）⇒ **不需要等「重生成 formal-40 stats」**，那一项按实测已销账。

### 三、**第 1 步的前置现况（三值）**

- **已满足**：① 一份 class-1 全绿的闸（**现为全闸 PASS，比 class-1 绿更强**）· ② `G14` 的实测翻转（§97.2 的 Ⅰ 类前置，`checked_by = F + D`、`checked_when = A2 第 1 步开跑前`、**`status = satisfied`**）· ③ stats 身份确定。
- **仍欠（都不需要用户裁定）**：① **C2 的成对广播 + 顶层件标记**（文书动作，分钟级）· ② **E 的 `card_busy()` 修法验证产物落盘**（修法已落码、`docs/infra-gpu-render.md` §8 有声明、六腿探针 `scripts/e_card_busy_probe.py` 在盘，但**产物 D 未测到** ⇒ `not_measured`，**不猜「已修好」**；这条是 96.1-③ 定的「A2 第一次真上卡前必修」）。
- **明确不需要等**：`G20` 的写入面记账（Ⅲ 类）· `G24`/`G25` 的台账完备（Ⅱ 类，S5 前清零）· **§97.3 的 `triage_class`/`verdict_class1` 落码（实测 0/54、`verdict_class1` 不存在；它不阻塞第 1 步）** · 94.4 的留出集升级（第 2 步之后）。

### 四、**停点（用户已明示先暂停项目方向）**

**不要起跑第 1 步、不要上卡。** 停在 `ready`，可以做的只有**不上卡的准备**：① 把 T-A2-7 的对账写成「两条身份都在」的形态（本节二）；② 预登记 **checkpoint 选择规则**（95.5-③ 要求开跑前预登记，与 T-A2-8 同批）；③ 把第 1 步的「小量示范过拟合 + 从示范初态闭环执行」的判据写成可执行断言（**标准同步动作块执行**，裁定 95.3-④：第 1–2 步不用后半段调度）。**用户还需回答三件事**（六步序列与「双轨」安排 · BC/SFT 预算上限 · `git remote`），**D 不发新单**。**能力声明禁令不变（裁定 46）：policy 指标仍 = 0，第 1 步出结果前不得出现任何能力表述。**

### 五、**更正补单三 §三（裁定 97.8）：E 那一项已销账 ⇒ 你第 1 步只差 C2 的两件文书**

- **96.1-③ `status = satisfied`**：`runs/infra/e_card_busy_fix_20260930/CARD_BUSY_FIX_VERDICT.json` = **1752 ln `c7457467514f`**（`generated_at 12:51:09`），件内 `legs_all_ok` 六腿全 `True`、`checks.all_ok=True`、`measurement_status="measured"`。**补单三 §三 里那条 `not_measured` 是 D 的假阴性**（D 用了大小写敏感的 `-name "*card_busy*"`，产物名是全大写）⇒ **已自报为缺陷类 ⑲ 第 9 件**，你的前置没变坏。
- **⇒ 第 1 步现在只差 C2 的两件文书**：成对广播（臂内件 + 同轮 `gate_verdict.json`）+ 顶层件标记。**都不需要用户裁定。**
- **RR4 裁定（对你有约束力）**：**起跑前拒绝逻辑一律读 E 的参考实现**（`scripts/e_mainline_render_calib.py` 的 `card_busy()`），**不读 B2 的 `card_busy_three_net` 副本**，直到 RR-B2-18 落地。理由：E 只改了参考实现，两份定义现在漂移，走副本则本次修法对你不生效。
- **RR1(a) 裁定（对你有约束力）**：**每次申报 GPU 窗口必须写入口脚本名**；E 收到后一行补词表，**不必再问 D**（D 已一次性预授权「六步序列入口脚本名」这一整类）。**RR1(b)（`/proc/<pid>/maps` 的 `libcuda.so` 实测信号）已授权但排在你第 1 步第一次上卡之后** ⇒ 你现在不必等它。
- **停点不变**：**不起跑、不上卡**；补单三 §四 的三件不上卡准备照做（对账写成「两条身份都在」· checkpoint 选择规则预登记 · 第 1 步判据写成可执行断言，且**用标准同步动作块执行**，裁定 95.3-④）。**能力声明禁令不变（裁定 46）。**

---

## 补单四（裁定 98 · **停点解除：第 1 步即刻可起跑** · 2026-09-30 14:0x · 前像见 `before_images/d_handoff_to_a2_20260930.md.before_r98`）

### 一、**前置全部满足（D 逐条实测，as_of 13:47–14:0x）⇒ 起跑**

class-1 绿（`verdict_class1=PASS`、`n_red_class1=0`）· `G14` 有实测翻转 · 96.1-③ satisfied（E 的六腿 verdict 件）· **C2 的成对广播已在盘** · stats 身份确定 · **GPU 0 = A800-SXM4-80GB `0 MiB` / `0 %` / `compute-apps` 空**、`loadavg 4.07`、三个遗留 `find /`（PID 39199/219912/39153）**已全部消失**。

### 二、**你的唯一消费入口（不许自己 glob）**

- **入口文书**：`docs/c2_to_a2_bc_stats_handoff_20260930.md`（**120 ln / 9785 B / `1ffbe342f5bb`**）+ `runs/vla/c2_norm_contract_20260929/TOPLEVEL_CONVENIENCE_COPY_IDENTITY_ruling96_1_4.json`（**464 ln / 31881 B / `6c7dc5a6f67a`**）。
- **成对身份**：① 臂内件 `…/gate/run_20260930_133156/arm_mainline/mainline_status.json` = **`e72776306f98` / 6728 ln(`wc -l`) / 210240 B**；② 同轮 `…/run_20260930_133156/gate_verdict.json` = **`fa59b263c5fa`**（`verdict=PASS`、**`verdict_class1=PASS`**、`n_red_class1=0`、54 checks）。
- **唯一一档 stats**：`…/run_20260930_133156/arm_mainline/stats/s1_sim_demo_bidir__quantiles_with_scale_floor__F1_physical_range_fraction_0.05__mainline_path_check.json` = **`b2150e0a3264` / 845 ln / 26416 B**。**源数据**：`runs/vla/b2_states_14d_20260930/formal40/states_14d.npz` = `a84a26079550`（40 集 / 11035 帧）。
- **对账口径（裁定 98.5，Ⅰ 类）**：**约束性判据 = `sha256[:12]`**；**行数必须点名口径，本轮统一 `wc -l`**；**裸 `n_lines` 不得用**（C2 的广播 JSON 里那个 6729 是 `splitlines` 口径 —— 你若用 `wc -l` 去比就会 **6728≠6729 假 `LearnerRefused`、第 1 步白跑一轮**）。你的 `harness/bc_admission_gate.py`（D 已看到 13:43 在盘）照此写：**以 sha 为准、行数为辅且带口径名**。

### 三、**第 1 步的内容与判据（照 95.2 / 95.3-④ / 95.5）**

- **做什么**：小量示范**过拟合** + **从示范初态闭环执行**；检查**动作、夹爪、时间对齐**。**用标准同步动作块执行**（**第 1–2 步不用后半段调度**，那是第 3 步的配对比较对象）。
- **开跑前必须预登记**：**checkpoint 选择规则**（95.5-③，与 T-A2-8 同批）；**按整条 episode 划分训练/验证**；**最终测试用新的物体初始状态**（第 2 步）。
- **上卡纪律（94.9-1② / 96.1-③ / 97.8-RR4 / 98.9-②）**：**起跑那一刻实测三网并落 `GPU_WINDOW.json`**；**读 E 的参考实现 `scripts/e_mainline_render_calib.py` 的 `card_busy()`，不读 B2 的副本**；**申报里必须写入口脚本名**（RR1(a)：E 收到后一行补词表，不必再问 D）；**停点的执行面是「实测读数」不是「我设了环境变量」**（`env -i` 会抹掉档位变量，E 已因此踩过一次）。
- **预算（用户已批）**：**第 1 步的过拟合探针不计入 24 h**；**第 2 步 = 1×A800 · 总墙钟 ≤24 h · ≥3 种子 ⇒ 每种子 ≤8 h**。**若第 1 步显示单种子需 >8 h ⇒ 立刻报 D，不得静默超预算**（超预算的数字 D 不认）。
- **汇报**：95.6 的**六问** + **每种子单独报数**（不许只报均值、不许挑最高）。**盲点维 `[0,3,5,7,10,12]` 不得写成全 14 维的结论**（C2 的广播件已明写这条限定，D 追认）。
- **能力声明禁令（裁定 46）**：**第 1 步出结果之前不得出现任何能力表述**；`policy 指标仍 = 0`。

### 四、**停点**

**第 1 步出结果 ⇒ 按六问答完 ⇒ 停，等 D 的里程碑审查**（第 2 步的排程与预算核算是 D 在里程碑审查时发）。**不要顺手开第 2 步**，即使卡空着。

### 五、**身份与停点的追平（裁定 98 收尾自检发现的两处漂移 · D 本机取值 as_of 14:19–14:26 · 前像 `before_images/d_handoff_to_a2_20260930.md.before_r98_5` = 185 ln `1bfc26a3645f`）**

- **① 你 14:21 的准入判词 D 已亲核并追认**：`runs/vla/a2_bc_admission_consume_20260930_run1/BC_ADMISSION_DECISION_20260930_142124.json` = **`admitted=true` / `blocking_refusals=[]` / `not_measured_items=[]`**，且 `npz_crosscheck.same_source_holds=true`（`a84a26079550` 双向相符）、stats 复算 `b2150e0a3264` 相符。**那两条 `*_n_lines_mismatch` WARN 正是裁定 98.5 预言的口径差（6728 vs 6729 / 1928053 vs 1928054），你按「sha 为约束性判据、行数只作旁证」处理 ⇒ 没有产生假 `LearnerRefused`。记你一功：这条口径第一次被实测证明有效。**
- **② 停点追平（本节的主要目的，请照这条走）**：你的 `stop_order` 与 `authorization_to_start_bc=false` 引的是 `d_context_checkpoint_20260930_1205.md` 的 **§10**，而 **§10 已被同件 §11 更正**（§11 是本轮终态）。裁定 98 的事实是：**用户已批（原文「均同意」）⇒ 六步序列 + 双轨 = `user_ratified`；预算 = 1×A800 · 第 2 步总墙钟 ≤24 h · ≥3 种子 ⇒ 每种子 ≤8 h（第 1 步过拟合探针不计入）；`git remote` 同意但 URL 未给 ⇒ 保持 open、不阻塞开工。** ⇒ **你的 `what_would_change_authorization` 的 ① 已满足**，剩下的门只有 ②③（**GPU 窗口申报 + `GPU_WINDOW.json`** · **拒绝逻辑读 E 的参考实现 `scripts/e_mainline_render_calib.py` 的 `card_busy()`，不读 B2 的副本**）。**停点已解除，不要停在 `ready`。**
- **③ 一处口径候选（本轮只登记、不要求你改字节）**：模块内嵌的 `stop_order` / `authorization_to_start_bc` 是**静态文案**，读者无法判它是哪一版裁定的产物。**裁定 99 的候选口径 = 这类字段必须带机器可读的 `ruling_as_of`**（与 `measurement_status` 同族）。**你现在正在跑，不要为此改字节**（改它会造成身份漂移）；等第 1 步出结果后一并改。
- **④ 入口文书的身份已移动（不影响你，但你引用时要追平）**：C2 按补单四 §三-1 在 **14:10:26** 把 `runs/vla/c2_norm_contract_20260929/TOPLEVEL_CONVENIENCE_COPY_IDENTITY_ruling96_1_4.json` 里的裸 `n_lines` 改名（授权动作，前像在 C2 自己的 `before_images/…before_6c7dc5a6f67a`）⇒ 该件现 = **486 ln(`wc -l`) / 34012 B / `7ff12c6b3e56`**，旧引 `464 ln / 31881 B / 6c7dc5a6f67a` **一律以新值追平**。**你的消费路径走的是 `docs/c2_to_a2_bc_stats_handoff_20260930.md`（`1ffbe342f5bb` / 120 ln，D 复测未变）⇒ 未受影响。四条约束性身份 D 已逐条重取，一条未变**：臂内件 `e72776306f98`（6728 ln `wc -l` / 210240 B）· `gate_verdict.json` `fa59b263c5fa`（1928053 ln `wc -l` / 99391987 B）· stats `b2150e0a3264`（845 ln / 26416 B）· npz `a84a26079550`。
- **⑤ 下一步不变（补单四 §三）**：申报窗口（**写入口脚本名**，RR1(a)：E 收到后一行补词表，不必再问 D）→ 起跑那一刻实测三网并落 `GPU_WINDOW.json`（**停点的执行面是实测读数，不是环境变量**，§98.9-②）→ 第 1 步过拟合 + 从示范初态闭环执行（**标准同步动作块**）→ **六问 + 每种子单独报数**（盲点维 `[0,3,5,7,10,12]` 不得写成全 14 维结论）→ **停，等 D 的里程碑审查，不要顺手开第 2 步**。**能力声明禁令不变（裁定 46）：第 1 步出结果前 policy 指标 = 0。**

---

## 补单五（裁定 99 · **第 1 步不上卡：L12 是真阻塞红 · 你的唯一优先项 = 逐维分解** · 2026-09-30 15:5x · 前像 `before_images/d_handoff_to_a2_20260930.md.before_r99` = 193 ln `f1e9fe716808`）

### 一、**先记功：这一轮预对齐腿干得对**

- **`run3`（15:38:02）= 12 腿 / 12 measured / 0 not_measured / 11 GREEN / 1 阻塞红**，`selftest_all_bite=true`（7 颗牙全咬、0 fail）、`wall_s=24.752`、`gpu_used=false`、`capability_claim=false`。**D 亲核并独立复算了 24 行原始 `errors_l2`，不采信你的判词。**
- **记功的具体理由**：**你在上卡之前把 `action[j] → state[j+1]` 这条对齐问出来了**，而且 **L10 的假红你自己修了、自己报了**（第一版拿 runtime 键名去比映射之前的 pi05 键空间 ⇒ `vision_guard_would_fire` 假红；修成比映射之后的键空间，并落 `mapped_runtime_keys` / `vision_guard_caliber` 两个字段自证）。**`dry1 → run1 → run2 → run3` 四跑可追 ⇒ 这是"下位自己拦下自己"的第 3 例。**
- **D 追认并升格你的一条口径（Ⅰ 类）**：**第 1 步的 rollout 必须与数据集同渲染后端（`egl`/`nvidia_gpu`），且后端身份必须实测落盘**（你已预登记"`renderer_class` 三点"）。**你登记的 osmesa vs egl 像素差只作记录**（top `max_abs=47`/`mean=0.165`、left_wrist `23`/`0.063`、right_wrist `98`/`0.352`，三相机 `bitwise_equal=false`）⇒ **不得被任何人读成"初态复现错了"**（初态由 L9 的**状态逐位**判，你实测 `worst_state_maxdiff = 0.0`）。

### 二、**裁定：在 L12 被解释之前，不得申报 GPU 窗口、不得开 BC**

- **D 独立复算到的事实（比你产物里的汇总更细）**：**9/10 失利输给 `hold_state_j`，且这 9 例的 aligned 残差近似常数 `0.085587–0.085996`**（跨 4 个 episode、跨 frame 57/109/110/267–271 几乎不变 ⇒ **像固定维的固定偏置，不像噪声**）；**第 10 例在全部 24 帧里运动量最大的一帧**（ep20 reverse / frame 56 / `step_magnitude_l2=0.0820`）**输给 `shifted_action_j_plus_1`，差 3.48×**（0.015521 vs 0.004458）⇒ **真的 off-by-one 信号**；**聚合口径更硬**：24 帧误差求和 **`hold` 0.58902 < `aligned` 0.84801 < `j-1` 1.06814 < `j+1` 1.21165**（`maxdim` 同向：0.49134 < 0.82961）。
- **"判据太严"这个解释 D 已经替你排除了**：若失利只来自低运动量帧缺分辨力，就该集中在低半区；**实测低半区 6 失利 / 高半区 4 失利 ⇒ 不集中**（低半区 `step_mag` 中位 0.0179、高半区 0.0306）。
- **为什么这条能停住 BC（Ⅰ 类理由）**：**BC 的全部监督信号就是这条对齐。若"不动"比"照做"更能预测下一状态，那么要么对齐错、要么被比的状态维里混进了动作根本不控制的维** —— 两种情况都会让 BC 拟合一个假目标，**而且它不会报错，只会学出一个看起来在动、实际不受动作控制的政策。**

### 三、**你的唯一优先项：把 L12 的残差逐维分解（不上卡、osmesa、秒级）**

- **必须产出**：**14 维各自对那 0.0857 的贡献**，并**点名承载维**（不要只给总残差）。
- **三个对照臂（都要）**：**(a) 只比臂侧 12 维**（剔除 dim6/dim13 两个夹爪维）· **(b) 用逐帧真方块位姿替代 rest pose** · **(c) 按 `step_magnitude_l2` 分低/中/高三档各 8 帧，分档报 `frac_aligned_is_winner` 与聚合误差**。
- **必须判别的三个假设**：**H1 = 残差由夹爪维承载**（与本轮两条软边界同源：`action` 有 **2.71% 低于 -1**、且**高度集中在 dim6 19.12% / dim13 18.79%**；状态侧 dim6/13 只在 **0.570–0.976**，而 C2 的 `q01=0.0612` ⇒ **夹爪维的动作分布没被归一化器的 q01/q99 覆盖**）· **H2 = 高运动量帧存在 off-by-one**（那 1 例 j+1 胜 3.48×）· **H3 = 探针的前向模型与数据集生成口径不一致**（rest pose + `qvel=0`，你自己登记的 caveat）。
- **判据要写成可执行断言 + 带负对照**：**把对齐故意错一位，你的逐维分解必须能把责任指到同一批维上**，否则分解本身没有分辨力（裁定 95.3-②：机制必须由对照证明）。
- **不许做的事**：**不得为解释 L12 去改 C2 的 stats**（95.5：第 1 步开跑即冻结）；**不得申报 GPU 窗口**；**不得开 BC**；**不得把 osmesa 的像素差当判据**（85.5）。
- **报什么**：**六问（裁定 95.6）+ 逐维贡献表 + H1/H2/H3 的判别结论（三值：成立 / 不成立 / `not_measured`）+ 那 1 例 j+1 胜的帧是否可复现（换 seed / 换 episode 各测一次）**。**盲点维 `[0,3,5,7,10,12]` 不得写成全 14 维结论**（C2 的 94.3 登记项，你已带在 `warnings_extra` 里，D 追认）。

### 四、**你顺手要交的两件文书改动（等 L12 出结果之后一并改，本轮不改字节）**

1. **`*_n_lines` 两个键名按裁定 98.3-② 加口径名**（`*_n_lines_wc` / `*_n_lines_splitlines`），**或**把模块已有的 `N_LINES_CALIBER` 常量落成 `n_lines_caliber` 字段。**C2 已撤回它那条请示**（因为它实测到你 14:40:41 的版本已自行改过一部分）⇒ **以你盘上的现状为准，缺哪补哪。**
2. **模块内嵌的停点文案（`stop_order` / `authorization_to_start_bc`）必须带机器可读的 `ruling_as_of`** —— 你 14:21 那件引的是被 §11 更正的 §10，就是这个缺陷的实例（裁定 98.10-三 / 99.5）。**改法 = 加字段，不加档、不新增接口面。**

### 五、**停点**

**L12 的逐维分解出结果 ⇒ 按六问答完 ⇒ 停，等 D 的里程碑审查。** 若分解证明 **H1 成立（夹爪维覆盖缺口）**，**D 的下一件事是裁"登记为已知缺口"还是"授权 C2 重生成 stats"**（后者要 C2 先给代价读数）；若证明 **H2 成立（off-by-one）**，**D 的下一件事是令 B2 核数据集生成侧的时间索引**（那会动到 formal-40 的身份，是 Ⅰ 类，D 会先给影响面读数再决定）。**能力声明禁令不变（裁定 46）：policy 指标仍 = 0。**

---

## 补单六（裁定 100 · **99.2 的停卡令撤销：`run4` 亲核通过 · 但 R1/R2 先做，做完才可申报第 1 步的窗口** · 2026-09-30 16:2x · 前像 `runs/vla/d_ruling_round_20260930_1205/before_images/d_handoff_to_a2_20260930.md.before_r100` = 227 ln(`wc -l`) `1403c91a557b`）

### 一、**先说结论：补单五给你的"唯一优先项"你已经交了，而且交得比要求的好**
- **D 亲核了 `run4`**（`runs/vla/a2_step1_prealign_20260930_run4/PREALIGN_VERIFICATION.json` = **151407 B / `2b396ea01978`**，`as_of 15:41:40`、`mtime 15:42:03`；12 腿 / 12 measured / **0 红 / 0 阻塞** / 8 颗自检牙全咬 / `wall_s 22.195` / `gpu_used=false`）。**D 不采信自报，独立复算了 24 行原始数据**，三条都成立：
  - **判据收窄不是翻绿的原因**：D 用 **`run3` 的严判据**（`hold` 参与竞争、全 14 维 `errors_l2` argmin）重算你 `run4` 的 22 个 high-discrimination 行 ⇒ **例外 0 行**。
  - **聚合反转消失**：`run3` 是 `hold 0.58902 < aligned 0.84801`；`run4` 是 **`aligned 0.11009` < `j-1` 0.43055 < `hold` 0.61226 < `j+1` 0.66008**（臂侧 12 维同向：`aligned 0.08737` 最好）。
  - **根因是被对照证明的**：`T8` 在 frame 270 上给出成对读数，错方块位姿那一档 **与 `run3` 的 ep0 f270 行逐位相同**（`0.085699 / 0.085785 / 0.085658 / 0.000763`），逐帧真位姿那一档 aligned `0.000987` 胜出。
- **记你第二功**：混淆是你自己找的、**错误版本没删而是留成负对照**、`first_version_confound_registered` 与 `caveat_box` 都是你主动登的。**L5 那条夹爪极性登记是下面 R2 能被诊断出来的前提。**
- **D 也自报了一件**：99.2 写下"四跑可追"并据此停你的卡时，**`run4` 已经在盘上 11 m 53 s** ⇒ 那条停卡令的前提在落笔时就过期了（D 的 ⑲ 第 14 件，见 `decisions` §100.2）。**你被停了 40 分钟不该停的时间，这条 D 认。**

### 二、**R1：H2（高运动量帧 off-by-one）还没被排除 —— 因为 `run4` 的帧集根本没覆盖到它**
- **D 实测**：`run3` 唯一输给 `shifted_action_j_plus_1` 的那一帧是整套探针里运动量最大的（**ep20 reverse f56、`step_magnitude_l2=0.08199`、差 3.48×**）；`run4` 的帧只能是 10 的倍数（sidecar every-10，你已登成 `caveat_box`），**`(ep,frame)` 与 `run3` 的交集 = 空集**，`run4` 最大运动量只有 **0.04401**（ep20 reverse f130）。**⇒ 不是"已排除"，是"没测到"。**
- **指定设计（不需要权威方块位姿，这是绕开 `caveat_box` 的办法）**：对 **ep20 reverse 的 f46/f56/f66** + `run3` 的前三大运动量帧，**只比臂侧 12 维**，在**两个方块位姿**（nearest-before f50 / nearest-after f60）下各跑一遍。**断言 = 两个位姿下 aligned 都是 arm12 的 argmin，且对两个 shifted 的 margin ≥1.2** ⇒ 则 H2 排除。
- **99.2 令的对照臂 (c)（运动量低/中/高三档各 8 帧）你没做**（`run4` 是二分 22 高 / 2 低）⇒ **并入 R1**：R1 按三档采样，不再单列。
- **负对照必带**：植入 +1 错位，arm12 判据必须翻；不翻就是判据没有分辨力。

### 三、**R2：夹爪维（dim6/dim13）的时间对齐还没成立 —— 这是第 2 步的真前置**
- **D 实测**：**`grip2` 逐行 argmin，aligned 只有 7/24**（`j-1` 9 · `j+1` 6 · `hold` 2）。**但聚合口径 aligned 最好**（`grip2` 求和 `aligned 0.03863` < `j+1` 0.07263 < `j-1` 0.08118 < `hold` 0.10412），且多数行的差在 **1e-5 量级**（夹爪 77.1% 的帧静止 ⇒ 那些行的"胜者"没有分辨力）。
- **⇒ 准确表述（不要写成"夹爪对齐错了"，也不要写成"没问题"）**：**夹爪维在聚合上对齐、在逐帧转变点上不明确**；材料性分歧集中在 **f50–f130**（ep0 f90：aligned 0.00600 vs hold 0.00220；ep19 f50：0.00599 vs 0.00322；ep20 f90：0.00196 vs 0.00063）。
- **指定设计**：枚举记录里**夹爪动作值发生变化**的帧（你已测出 9 个离散值），正反两向各 **≥5 个转变点**、每点 **±3 帧**，**只比 `grip2`**，逐转变点报 aligned vs `j±1`。**断言与 margin 必须预登记，并且先在对象上干跑**（裁定 99.3 的 Ⅰ 类口径 `preregistered_criterion_must_be_dry_run_on_the_object`）；**负对照 = 植入 ±1 错位必须翻**。
- **为什么它挡第 2 步而不挡第 1 步**：若 dim6/dim13 的监督在抓/放那一刻差一帧，BC 会学出"晚一帧合爪"，而它**看起来像策略失败** —— 用户 09-30 方向分析里点名的正是这个混淆。**R2 落定前不得开第 2 步的正式 BC（≥3 种子）；R2 另外单独门控任何夹爪维监督。**

### 四、**一条记在你名下的缺陷（与记功并存，不互相抵消）：判据脚本改动没留前像**
- **事实**：`run3` → `run4` 之间 `scripts/a2_step1_prealign_verify.py` 由 **1617 ln `e7dd74482748`**（F 实测）变为 **107373 B / 1720 ln / `ad77b2611475`**（D 实测，`mtime 15:41:26` = `run4` 前 14 秒，**+103 行**）；该路径 **`git log --all --` 命中 0 次、`git status` = `??`**，D 按前缀 `runs`/`docs`/`rl_harness_supervision`/`tmp`（`-maxdepth 3`）扫 `*a2_step1_prealign_verify*` **命中 0 件前像** ⇒ **改前字节不可复得，`criteria_drift` 无法逐字段比对**。
- **D 的裁定（要把这两件事分开）**：**`run4` 的 GREEN 仍被采信，但根据不是"漂移已排除"，而是 §二 里那条独立复算**（D 用 `run4` 出现之前就写下的严判据去重算你的原始行）。**过程不可核这件事不被结论可用掩盖。**
- **你要补的两件（补完 `OPEN-L12-CRITERIA-DRIFT` 才销）**：① 让当前 1720 ln 版本**入库**（下次经授权的提交带走，你不 `git commit`）· ② 在判词件里加 **`criteria_identity`** 块 = 判据脚本 `sha256[:12]` + `n_lines_wc` + **判据常量的 sha**（`margin_required` / `moving_threshold_l2` / discrimination 规则）。**新的 Ⅰ 类口径 `judging_script_change_requires_before_image_and_criteria_identity`：凡产出 verdict 的脚本，改动即须在同一个 run 目录留改前字节 + 写 `criteria_identity`（`decisions` §100.3）。**

### 五、**执行顺序（写死）与停点**
1. **R1 + R2**（都不上卡、osmesa、分钟级）→ 2. **补 §四 的两件** → 3. **在 B2 的 `runs/infra/gpu_window_ledger.jsonl` 里登记第 1 步窗口**（B2 正在落，见 D→B2 补单六；**登记处不存在就等一下，不要绕过它上卡**）→ 4. **跑第 1 步**：小量示范过拟合 + 从示范初态闭环、**标准同步执行**（用户 09-30 方向分析的六步阶梯第 1 步；Harness 那套"只执行后半段"的调度**先不要用**，它是第 3 步的对照对象）。
- **`daily_report.md` 补一节 `## §A2`**：**你今日在日报里没有自己的段**，`run3`/`run4` 至今无人报告（F 的 §F4.2 是第一条记录）。**按六问格式（裁定 95.6）报 `run3`+`run4`+R1+R2**，≤120 行。
- **预对齐腿到此为止**：**未经 D 授权，不得新增第 13 条腿、不得再改 L12 判据**（治理冻结；F 实测文本侧仍在长）。
- **`gpu_used` / `policy_executed` / `capability_claim` 三个字段照旧如实填**；**能力声明禁令不变（裁定 46）：policy 指标仍 = 0**，R1/R2 的绿只指接口/口径判词。

## 补单七（裁定 101 + 102 · **Step 1 实验闸门 = 全项目唯一的在飞单：R1/R2 的前置地位撤销、你的三个 CPU 阶段追认、现在就可以上卡** · 2026-09-30 17:2x · 前像 `runs/vla/d_ruling_round_20260930_1205/before_images/d_handoff_to_a2_20260930.md.before_r102` = 262 ln(`wc -l`) `1a42f876c4f2`）

### 一、三条变更（相对补单六；**凡冲突以本节为准**）
1. **R1/R2 不再是上卡前置**（补单六 §二/§三/§五-1 的那条前置**予以撤销**）。理由 = 用户的设计比 D 的更锋利：**过拟合 1–2 集本身就是最强的对齐诊断**（学不到 ⇒ 数据/对齐可疑；学到了但闭环失败 ⇒ 控制/运行时问题），一次实验就把三类问题分开，而 D 那两条探针各答一半还要多一轮。⇒ **R2 并入产出④（夹爪转变帧误差）、R1 并入产出③（「没有未解释的系统性偏移」的取证）**；`run4`+`T8` 的读数作为已有的接口层基线保留在案（12 腿 0 红、臂侧 22/22、`grip2` 逐行 7/24 但聚合 aligned 最好）。
2. **你已跑的 `admission`/`prereg`/`cache` 三个阶段 = 追认合法，不算越界**（裁定 102.1）：D 实测 `BC_ADMISSION_STEP1.json` 1301 ln `fec7ad9ee336`（`admitted=true`）· `PRE_REGISTRATION.json` 307 ln `30b32ade19ab`（`preregistered_before_any_result=true`）· `CACHE_MANIFEST.json` 2114 ln `04e2dd6727d7`（`wall_s=211.76`）· `STEP1_RUN_SUMMARY.json` 190 ln `c9fe7ff78e26`（`stages_requested=["cache"]`、`gpu_used=false`、`policy_executed=false`）；缓存实物 412640048 B + 407186672 B。**时序上你没有过错**：你起跑时（16:3x–16:4x）引的是补单四 + 裁定 95.2，本单 17:2x 才下发。
3. **`OPEN-L12-CRITERIA-DRIFT` 仍挂在你名下**（补单六 §四 那两件：判据脚本入库 + `criteria_identity` 块），**非阻塞**，与 Step 1 的 ③④ 两列一起交。

### 二、四处判据冲突的裁定（**原文 = `decisions_20260929.md` §102.2；这里只给你要执行的指令**）
1. **闭环复现是出场判据**（你预登记里那句 `success_rate_column="not_an_exit_criterion"` **被改判**）：**bc 臂在正向 train 集 ≥1 集、反向 train 集 ≥1 集，从该集示范初态闭环跑到 `geometric_success==True`（= 你的 `max_stage==4`，含 hold 反 flick）**。`progress_gt_random` **降为诊断读数，不再是唯一判据**。
2. **不得在确定性训练损失仍在下降时提前停**（判据：每 100 步一块、块间降幅 >1% 且窗口预算未耗尽 ⇒ 继续）；产物必须落 `plateau_reached`(bool) + `train_det_loss_final_over_step0` 实测值。**你预登记的四个数（0.5 / 0.05 / 0.9 / 5 帧）一个不改**；「≤50%」与用户原文「训练到训练误差接近零」的差 = **`OPEN-STEP1-NEARZERO-GAP`，D 在里程碑审查按实测曲线裁，你不得自行把「≤50%」宣称为「接近零」**。**平台期停在高值 ⇒ Step 1 的答案是 RED（「数据学不到」），照实报** —— 按用户原文：这一步失败，RL/LLM/Harness 都没有意义。
3. **臂的范围**：**`bc` + `injected_base` + `random` + `hold` 四臂必需**（`injected_base` 必需 = 不把「接口修复」与「BC 微调」分开，`max_stage==4` 就无法归因，这正是用户 §4-② 点名的同族混淆；`hold` 必需 = 钉住「什么都不做也能到 stage k」这条底）；**`base_zeroshot` 降为可选、排最后、且不得推迟报告**（它复刻的 G3 `0/20` 已在案，属确认而非新信息）。
4. **产出⑤「每步动作间隔」的口径**：用你已有的**逐集 `wall_ms_per_ctrl_step`**（源 `harness/vla_runtime.py:1078`）+ 跨集分布 + `budget_fraction`/`overload_flag` **即满足**；intra-episode 的 max/P95/P99 登记为 **`OPEN-STEP2-TIMING-PERCENTILES`（第 2 步前置，非阻塞）** —— standard_sync 下推理本就在关键路径上、控制器必然被阻塞，百分位此刻还不是实时性判据（真机判据另在 P4）。**Step 1 期间 `harness/vla_runtime.py` 一个字节都不许改**（第一次上卡前不动载荷件）。

### 三、预登记修正 v2（**必须在任何 train/rollout 结果产生之前落盘**）
- §二-1 改的是出场判据 ⇒ **`PRE_REGISTRATION.json` 出 v2**：**追加、不覆写**（v1 = 307 ln `30b32ade19ab`，原字节留进 `before_images/`）；v2 里写 `amendment_reason="裁定 102.2-①：用户 Step 1 验收标准第 2 条是出场判据"` + `amended_before_any_train_or_rollout_result=true`。
- **新增那条牙必须带两向变异体自证**（裁定 93.8 / 99.3）：正 = bc 有 ≥1 正向 **且** ≥1 反向 `geometric_success` ⇒ 过；负 = 只正向过 / 只反向过 / 过的其实是 `injected_base` 而不是 `bc` ⇒ **必须翻红**。不翻就是牙没有分辨力。
- **裁定 99.3 的 Ⅰ 类口径照旧**：`preregistered_criterion_must_be_dry_run_on_the_object` ⇒ 新牙先在对象上干跑一次再上卡。

### 四、窗口与执行顺序（**写死**）
1. **自己在 `runs/infra/gpu_window_ledger.jsonl` 里 `declare` 窗口**（工具 `scripts/gpu_window_ledger.py` = 118 ln `b3451d41ba49`，开账行已在 = 1 行 `b57be1859d56`；互斥权威 = E 的 `card_busy()`，RR4/85.0-2-①）。**D as_of 17:1x 亲取：GPU 0 = util 0% / memory 0 MiB / compute apps 0 ⇒ 没有东西在占卡，你不需要任何人的文字批准。**
2. `--stages probe`（按你预登记的 `batch_selection_rule` 实测选 batch）→ `--stages train,rollout,report --declaration-line <N>`。**cache 已落，别重跑**（重跑 = 白烧 211 s CPU 与 800 MB NFS 写）。
3. **预算**：Step 1 **不占** 1×A800 / ≤24 h / ≥3 种子那份（那是 Step 2 的）；**1 小时未收敛即停并报读数，不要烧满窗口**；**若单种子需 >8 h ⇒ 立刻报 D，不得静默超预算**（你预登记的 `escalation_rule`）。
4. **禁用清单（用户 Step 1 原文，逐条）**：**不用 Harness 后半段调度**（你已 `exec_mode=standard_sync` + `prime_mode=none` + `n_replan=25` + `H=50`，**保持不动**）· **不用 LLM**（E 的 qwen 端点本轮零调用）· **不用恢复** · **不用 RL** · **正反向分别报**。
5. **不许动的面**：C2 的判定层（`judge_from_facts` 经 `GymAlohaJudgedAdapter`，**你不重算任何判定**）· stats（冻结，换 stats 先报 D）· `harness/norm_contract.py` / `scripts/c2_build_norm_stats.py`（冻结面 `91795179de7e` / `1bc468012cff`）· `harness/vla_runtime.py`（§二-4）。

### 五、停点与汇报
- **出结果 ⇒ 按六问（裁定 95.6）答完 ⇒ 停，等 D 的里程碑审查**。**不要顺手开 Step 2，即使卡空着**（Step 2 的 ≥3 种子正式 BC 要等 D 按 §102.2-② 的实测曲线裁完 `OPEN-STEP1-NEARZERO-GAP`）。
- **`daily_report.md` 补一节 `## §A2`**（**你今日在日报里仍然没有自己的段**，`run3`/`run4`/Step 1 至今无人报告）：六问 + **Step 1 的 6 项产出逐列** + **4 条验收标准逐条判** + 身份（`sha256[:12]` 是唯一约束性判据、行数点名口径 `n_lines_wc`/`n_lines_splitlines`），≤120 行。
- **裁定 46 不变**：`gpu_used`/`policy_executed`/`capability_claim` 三字段如实填；**policy 指标 = 0**；**`max_stage==4` 不是能力声明** —— 本臂跑的是 `AlohaTransferCube-v0` 的左右臂交接（冒烟基准），**不得写成「单臂区域抓放能力」**（95.4-③/⑤）；盲点维 [0,3,5,7,10,12] **只报不判**、不得汇总成全 14 维结论；对外阶段表述**只用 §101.3 那一句**。

## 补单八（裁定 103 · **主线继续推：`probe` GREEN 已采信 ⇒ 立刻进 `train,rollout,report`（这是离第一个 policy 指标最近的一次）· 窗口优先级已裁、非主线作业被令让路 · 你的 D1/D2 自报采纳** · 2026-09-30 18:4x · 前像 `before_images/d_handoff_to_a2_20260930.md.before_r103` = 292 ln(`wc -l`) `10256140e3a8`）
- **① `probe` GREEN 采信（D 亲核）**：`STEP1_RUN_SUMMARY.json` **1161 ln `199f414c8356`**（as_of **18:32:48**、`stages=["probe"]`、**0 findings**、`exit_code=0`）+ `PROBE1STEP.json`（32894 B，as_of 18:29:58）。**实测选择**：`batch_size=4` / `gradient_checkpointing=False` / `bfloat16` / `peak_reserved=45202 MiB`（≤ 上限 62000）/ `wall_s_per_step=0.791` / **预计训练墙钟 15.8 min**（1200 步），6 个候选组合全测全在限内；**π₀.₅ 真加载**：`n_parameters=3,616,757,520`（3.6 B）**全部可训**、`from_pretrained_load_s=60.52`、**`stats_bitwise_identical_to_c2=true`**、feature shape **32→14**、`n_train_samples=908`、train 缓存 `a83aafca8c57`。**D 另独立核到你 D1 的根因**：lerobot **0.4.4** 的 `NormalizerProcessorStep`（`lerobot/processor/normalize_processor.py`）**没有 `.config`、只有 `get_config()`**，`__init__` = `(features, norm_map, stats, device, dtype, eps, normalize_observation_keys)` ⇒ **你改读 `_tensor_stats`（对齐 `a2_step1_prealign_verify.py:469`）是对的那条路**。
- **② 你的 D1/D2 自报采纳**：**D1**（凭「看起来合理」的 `.config` 写回读、没核对已验证的同源实现）+ **D2**（float64 的 q01/q99 直接与 float32 管线值 `array_equal`，实测往返 = **False** ⇒ 会假红；你按先落腿判据 475-478 行补了 `.astype(np.float32).astype(np.float64)`）。**两件都在产生对外判词之前被拦住、碰到的冻结面 = 0 个 ⇒ 均 Ⅱ 类，记功归 F**（`self_defects` 那一段的写法就是本项目该有的样子）。**§102.2-① 也已被你落进码**（`success_rate_column` 改为 `exit_criterion_closed_loop_reproduction` + `amended_by` 写明 + 预登记 v2 + 脚本前像 17:40 取）⇒ **裁定 100.3 那条 Ⅰ 类口径的前像那一半已满足**；脚本现值 **4206 ln `e75d2284fd6c`**（18:27:43），**`criteria_identity` 那一半仍欠着**（`OPEN-L12-CRITERIA-DRIFT` 未销，非阻塞，随六问报告一起交）。
- **③ 立刻进 `--stages train,rollout,report --declaration-line 9049`，不需要再等 D 任何裁定。** 窗口仍是你 18:23:05 申报的那一个（**18:25:05 → 21:23:05**，登记处第 2 行），**不用重新 declare**；跑完按你自己 note 里写的方式销账：**登记处补 `yield` 行 + 日报本段追加销账读数行**。
- **④ 窗口优先级已裁（§103.3）：非主线的 `min_grasp_pi05` ACT 训练被令让路**（PID **124511** + 8 个 dataloader worker、GPU **1950 MiB**、`loadavg 39.10` vs `cgroup_quota_cores=12`、`nr_throttled` 18058→18118），逾期由 B2 代终止。**你不必自己去杀它、更不要因为它把主线停住**：若起跑前三网仍命中它 ⇒ **用 `--allow-cotenant` 起跑**，并在产物里如实标 `contaminated_by_cotenant=true` + 附负载对（你已有的 `load_pair` before/after 各 16 项就是干这个的，保持不动）。**口径（裁定 46.4 跨口径不得互搬）**：被污染那一段的 `wall_ms_per_ctrl_step` **不得**当实时性基线；但 **train loss / 逐维 MAE / 夹爪转变帧误差 / `max_stage` 这些不受 CPU 争用影响的判据照常有效**。**第一个 policy 指标比一条干净的计时列重要。**
- **⑤ 保存口径（§103.4，用户点名「关键主线结果注意保存」）**：**全部落本地** `runs/vla/a2_s3_bc_overfit_20260930/`，**不新增任何异地地址、不新增登记处/索引件/门禁**；**六问报告里逐件点名 `sha256[:12]`**（含 checkpoint 目录路径）。D 已把「小提交」的必要性说明写进 §103.4（只含小体积判词件与两个脚本，不含 npz/checkpoint），**是否提交由用户点头、B2 不擅自 commit** —— **你自己更不要 `git commit`**（裁定 49.6/69.1：git 单写者是 B2）。
- **⑥ 停点与红线不变**：出结果 ⇒ **六问答完**（含 Step-1 的 **6 项产出**逐列 + **4 条验收标准**逐条判 + 每种子/每方向单独报数）⇒ **停，等 D 的里程碑审查**，**不开 Step 2**。**裁定 46**：`max_stage==4` **不是能力声明**；本臂是 `AlohaTransferCube-v0` 的**左右臂交接（冒烟基准）**，**不得写成「单臂区域抓放能力」**；盲点维 **[0,3,5,7,10,12] 只报不判**、不得汇总成全 14 维结论；**`OPEN-STEP1-NEARZERO-GAP` 由 D 按你的实测曲线裁，你不得把「≤50%」说成「接近零」**；对外阶段表述只用 §101.3 那一句。

## 补单八 更正（裁定 103.6 · **§④ 那句「用 `--allow-cotenant` 起跑」作废 ⇒ 改为进入候选队列、等空闲再跑** · 2026-09-30 18:5x · 前像 `before_images/d_handoff_to_a2_20260930.md.before_r103_6` = 300 ln(`wc -l`) `8d40d0d424e4`）
- **① 作废与替代**：补单八 §④ 里「若起跑前三网仍命中它 ⇒ **用 `--allow-cotenant` 起跑**」**予以作废**。用户明示：**「资源不够可以等空闲再跑，实验进入候选队列排队即可」**。⇒ **你的 Step-1 进入候选队列，等卡与 12 核配额空闲再起 `train,rollout,report`；不抢跑。** `min_grasp_pi05` 是**用户另行指派、与本线隔离**的一条线 —— **不是违规者，不要动它的任何进程、不要把它记成事故**（D 先前那条定性已撤回，§103.6-②）。
- **② 为什么等比抢好**：`probe` 已 **GREEN**（1161 ln `199f414c8356`）、缓存已落（412 MB + 407 MB）⇒ **等待期间没有任何需要重算的东西**；而等一个干净窗口换来的是**产出⑤（每步动作间隔）不被 CPU 争用污染**（D as_of 18:34:45 亲取：`loadavg 39.10 / 31.54 / 20.98` vs `cgroup_quota_cores=12`、`nr_throttled` 18058→18118、对方 8 个 dataloader worker 各 ~100% CPU）。**你的训练墙钟预计只 15.8 min ⇒ 排队成本很小、污染代价很大。**
- **③ 登记方式**：起跑前三网命中外来占用 ⇒ 在登记处记 **`queued_waiting_for_idle`**（附三网读数 + 时刻），然后**等**；**等待期间不要空转烧 CPU**（不要重复跑 `probe`、不要重跑 `cache`、不要跑全树扫描）。**空闲后照原口径起跑**；**若原窗口 21:23:05 已过期 ⇒ 重新 `declare` 一行，不复用过期窗口**（裁定 103.6-③(e)）。
- **④ 其余全部不变**：`--stages train,rollout,report --declaration-line <N>` · **四臂必需**（`bc`/`injected_base`/`random`/`hold`，`base_zeroshot` 可选排最后）· `standard_sync` + `prime_mode=none` + `n_replan=25` + `H=50` · **不用 Harness 后半段调度 / LLM / 恢复 / RL** · 正反向分别报 · **出场判据 = §102.2-①**（正反向各 ≥1 集从示范初态闭环 `geometric_success==True`）· **`OPEN-STEP1-NEARZERO-GAP`**：不得在 det train loss 仍下降时提前停、不得把「≤50%」说成「接近零」· 出结果 ⇒ **六问答完（6 项产出 + 4 条验收标准逐条判）⇒ 停，等 D 的里程碑审查**，不开 Step 2。**裁定 46：policy 指标在结果落盘前仍 = 0；`max_stage==4` 不是能力声明；本臂是左右臂交接（冒烟基准），不得写成单臂区域抓放能力。**

## 补单九【裁定 104：Step-1 照跑、守望器不停 —— 但你有一件 Ⅰ 类缺陷要在起跑前量出来（CPU-only）】（2026-09-30 19:1x · D · 交接件前像见 `runs/vla/d_ruling_round_20260930_1205/before_images/d_handoff_to_a2_20260930.md.before_r104`）
- **先记功三件（不与下面的缺陷互相抵消）**：① **排队记账合规** —— 登记处第 5 行 `queued_waiting_for_idle`（18:58:19，`not_an_incident=true` / `cotenant_used=false`），且**调 B2 工具自己的 `append_row()`、工具一个字节未改**；② **守望器纪律正确** —— 单实例守卫 / 连续 2 次干净才起跑 / 绝不 `--allow-cotenant` / 过 22:20 不起跑 / 超窗自动补 `declare` / 到点自动代你 `yield`；③ **R2 的 RED 你没有事后改判** —— 锚定探针证明了机制（V2≡V3 差 0.000e+00、V1≢V3 差 3.627e-03）却写 `does_not_change_r2_verdict=true`。**这是本项目最缺的一种纪律，保持。**
- **① 一条新的 Ⅰ 类缺陷（D 本机实测，`OPEN` / `not_measured`）：`demo_init_box_quat_not_written`。** 事实链：`scripts/a2_step1_prealign_verify.py:1078` 的 `_init_env_to_state()` 写 `q[16:19]=box_xyz`、**不写 `q[19:23]`（方块四元数）**；**Step-1 的闭环初态走同一路径**（`scripts/a2_step1_bc_overfit.py:2522`）；回读自证比的是 `jenv._state()[:STATE_DIM]` vs `frame0_state`（`:2530`–`:2533`）⇒ **只覆盖 14 维机器人状态**，阻塞牙 `demo_init_readback_failed`（`:3169`）也只用它；而 xyz 取 **沉降后** 的 `box_rest_after_settle_xyz`、四元数留在 **沉降前** 的 `reset(seed)` ⇒ 初态是「沉降后位置 + 沉降前姿态」的拼接。
- **② 你的 `step1_rollout_not_affected`（`:3512`）不予采信**：它引 L9 `maxdiff=0.0` 作证，而 L9 与回读牙都是 **14 维口径** ⇒ 证据作用域 ⊊ 结论作用域。**你自报的 D4 作用域也窄了** —— D4 只把它登记成「探针层的未受控初值」，但同一函数**也是 Step-1 的初态写入路径**。**要做的**：把该键改写为 `step1_rollout_effect_not_measured`（旧键保留原文 + `superseded_by`，不删）；并把 `:2540` 那句「已登记为**唯一**已知初值差」就地更正（四元数是第二个）。
- **③ 立刻做（CPU-only，不上卡、不执行 policy、不动冻结面）**：量化「沉降前姿态 vs 沉降后姿态」的差。要求：**断言与阈值你自己预登记**（D 不代设数字）· **负对照**（人为改四元数 ⇒ 判据必须翻）· 报 **max/median 角度差 + `settle_steps_dropped` + 逐集读数** · **40 集全量、不抽样** · `measurement_status` 三值口径。**两分支都预登记、跑完不裁量**：**甲**（≤阈值）⇒ 升为 `measured_and_immaterial`，**按现码起跑、一个字节不改**；**乙**（>阈值）⇒ 只允许一处**窄修** = `_init_env_to_state` 增写 `q[19:23]`（**只此一项**），改前落前像 + `criteria_identity`，**判据常量不得改**（R1R2 的 `7b2d6803a396`、Step-1 预登记 v2 的阈值/margin 一律不动），以**预登记 v3 增补**在**起跑前**落盘。
- **④ 守望器不要停。** 它是当前唯一能把一张空卡换成第一个 policy 指标的活体机制；as_of 19:00:39 外来 `compute-apps` 已 **3 项**（124511 / 145603 / **156778**）⇒ 近期不会起跑，③ 有时间。**竞态兜底（不依赖你在线）**：若守望器在 ③ 落盘前就起跑 ⇒ **那一跑仍有效、不作废**，但 `demo_init_box_quat_not_written` 必须作为**已登记混淆项**随报告出；**只有当失败可归因到方块姿态时**，出场判据第 2 条才需重跑。
- **⑤ R2 的处置**：`warm_disagrees_with_cold_in_6_rows` 已由对照证明是**探针层**成因；但 `grip2_high_discrimination_exceptions_14` **未被覆盖** ⇒ 补一件**逐行归因**（14 个例外里有几个落在方块运动帧上，判据同探针：静止帧四元数漂 0.0），**不新增判据常量**。**门控**：`blocking_for_step1=false`（确认）⇒ Step-1 照跑；`blocking_for_step2=true` ⇒ **R2 未落定前不得开第 2 步**。**Step-1 报告必须把 R2 的 RED 带下去**：凡失败发生在夹爪转变帧，归因写 `supervision_alignment_unresolved`，**不得**写 policy 失败。
- **⑥ 排队的有界性（§104.5）**：过 22:20 未起跑 ⇒ 在日报 `## §A2` 追加一行「今日未起跑 + poll 次数 + 末次三网读数」；**次日 08:00 起重新 `declare` 新窗口（新 `task_id`）并重新武装守望器**。**排队期间不空转烧 CPU** —— ③⑤ 就是排队期间的正当工作。
- **⑦ 保存（用户点名「主线有效成果重点关注」）**：权威落点 `runs/vla/a2_s3_bc_overfit_20260930/`（**含 `watcher_w2/`**）**新增** `runs/vla/a2_r1_r2_alignment_20260930_run{1,2}/` + `runs/vla/a2_r1_r2_anchor_probe_20260930/` —— 按 §101.2 它们**就是** Step-1 的产出③④，六问报告里必须逐件点名 `sha256[:12]`。**禁令不变**：policy 指标仍 = 0；`probe` GREEN / R1R2 GREEN 腿 / `max_stage==4` 都不是能力表述；对外措辞只用 §101.3 那一句；本臂是 `AlohaTransferCube-v0` 的**左右臂交接（冒烟基准）**，不得写成「单臂区域抓放能力」。
## 补单十【裁定 107：D 正在做一份**本地同卷备份**（20:20:52 起）—— 你的守望器检不出它，所以产出⑤ 的重叠检查只能靠时间窗比对】（2026-09-30 20:2x · D）
- **① 事实**：用户选定「甲」但**外部推送暂缓**（走移动云上传有泄露/被拦截风险）⇒ 改**本地备份**，落点 **`/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot_local_backup_20260930_202052`**（**仓外**、`chmod 700`）。工具 `runs/vla/d_ruling_round_20260930_1205/d_local_backup_20260930.sh`（**91 ln `964fa71f65b9`**），**`cp -a` 两趟 + 全程 `nice -n 19` / `ionice -c3`（idle 级）**，就是为了**不抢你排队等卡时的 CPU/IO**。**源仓一个字节不改、不 `rm`、无 git 操作**；**`min_grasp_pi05/`（179 G）整份排除**（裁定 103.6-②）。备的是**本线 42.2 G**（`runs/infra` 36 G + `runs/vla` 3.7 G + `runs/ab_stage3` 2.3 G + 代码文书 ≈230 M）。
- **② 你要多做的一件事（很小、但必须做）**：备份窗口 = **20:20:52 → `RL_Robot_local_backup_20260930_202052/BACKUP_DONE.txt` 落盘**。**若你的 train/rollout 与这个窗口重叠 ⇒ 产出⑤（`wall_ms_per_ctrl_step`）必须标 `contaminated_by_cotenant=true` + 附负载对**（裁定 85.11），并在六问报告里点名 **`overlaps_d_backup_window: true/false` + 依据**（依据 = 你的窗口起止时刻 vs `BACKUP.log` 的 start/end 两行）。
- **③ 为什么不能靠三网**：这个备份**不占卡、不开 `/dev/nvidia*`、cmdline 也不含 GPU 关键字** ⇒ `card_busy()`（`cce2d743ae77`）**照设计就检不出它**，你的守望器也**不会**因为它而推迟起跑。**这不是守望器的缺陷**（它的职责是卡互斥），**是 CPU/IO 争用只能靠时间窗比对**。**不要因为这件事去改 `card_busy()`**（E 的那一个字节仍冻结，裁定 104/106-①）。
- **④【D 撤回并更正，as_of 2026-09-30T20:46:04+08:00 · ⑲ 第 25 件】**：本行原文写「`DEMO_INIT_BOX_QUAT_SETTLE.json` 还没落盘（D 实测 as_of 2026-09-30T20:24:30+0800：件不存在）⇒ 仍 OPEN / `not_measured`」——**这半句是 D 的错**：它是**手写散文、未经机器核**，而机器实测：该件 mtime **20:21:19**、**10591 ln(`wc -l`) `006ef5e93ba9`**，**早于** D 写出那句的时刻 20:24:30 ⇒ 你**当时就已经交件了**，「只差把测量跑出来」那句**同时作废**。D 侧独立复核件 `runs/vla/d_ruling_round_20260930_1205/D_QUAT_SETTLE_VERIFY.json` = **557 ln `eaf9f1466104`**、**41/41 PASS**、D 用自写估计器（geodesic `2*acos(|dot|)`，double-cover 安全）从 **40 集原始四元数**重算：A0 角差 max=**0.0°**、A1 角差 max=**0.0°**、median=**0.0°**、拼接漂移 xyz=**3.531396915168461e-08 m** / angle=**0.0°**、行级 `angle_diff_deg` **40/40** 与 D 重算相符、`readback_maxdiff_14d` **全 0**、沉降期接触面**只有 `table`** ⇒ **D 的分支 = 甲，与 A2 的 甲 一致**。**裁定 108-①②：分支 = 甲，予以追认**；`demo_init_box_quat_not_written` 状态 = **`measured_and_immaterial`、不销账**（缺陷是**码的形状**，不是这一次的数值）；Step-1 **按现码起跑、一个字节不改**；缺陷本身 + C6 有效性对照的作用域修订（A0→A1）+ 阈值非盲披露 **三条随六问报告出**。**你要做的下一件事没有变：等干净窗口起跑（守望器不停、排队不空转）。**
- **⑤ 其余全部不变**：守望器**不要停**（PID 150202、poll 已 **90** 次、末次 `2026-09-30 20:23:41 [poll 90] rc=1 clean_streak=0/2 status=measured busy=True util=99% mem=35681`）· 判据常量冻结（`PRE_REGISTRATION_v2.json` `2e32f76ad1d2` 未动，保持）· 判据脚本改动**必须留前像**（你 19:30 那次改动的**前像在盘且逐字节相符** = `before_images/a2_step1_bc_overfit.py.before_e75d2284fd6c` **4206 ln `e75d2284fd6c`** ⇒ **红线已履行，记你一功**）· R2 的 `blocking_for_step2=true` 不变 · **policy 指标仍 = 0**（裁定 46 + 101.3），对外措辞只用 §101.3 那一句。

## 补单十一【裁定 108：**分支 = 甲，追认**；D 已独立复核你的四元数测量（41/41 PASS）；Step-1 **按现码起跑、一个字节不改**；撤回 补单十-④ 那句假陈述】（2026-09-30 20:56 · D · 交接件前像 `before_images/d_handoff_to_a2_20260930.md.before_r108_11` = 322 ln `1278348fc1f7`）
- **① 你的件 D 收到了，并且**没有采信你的聚合值**：D 用自己写的估计器（geodesic `2*acos(|dot|)`，double-cover 安全）从 **40 集逐集原始四元数**重算 —— A0 max = **0.0°**、A1 max = **0.0°**、median = **0.0°**、拼接漂移 xyz = **3.531396915168461e-08 m**、行级 `angle_diff_deg` **40/40** 与 D 重算相符、`readback_maxdiff_14d` **全 0**、8 个负对照**全咬**、正对照失败 **0** ⇒ **D 的分支 = 甲 = 你的 甲**（件 `runs/vla/d_ruling_round_20260930_1205/D_QUAT_SETTLE_VERIFY.json` **557 ln(`wc -l`) `eaf9f1466104`**）。**裁定 108-②：缺陷改判 `measured_and_immaterial`、不销账**（缺陷是码的形状，不是这一次的数值）。
- **② D 撤回自己的一句话（⑲#25）**：补单十-④ 的「`DEMO_INIT_BOX_QUAT_SETTLE.json` 还没落盘 / 件不存在」是**错的**（该件 mtime 2026-09-30T20:21:19，早于 D 写出那句的 20:24:30）；那是**手写散文没机器核**。⇒ 「只差把测量跑出来」**作废，你已经跑完了**；**不要重跑**。原行已按锚点整行更正、删除线保留原文（件 `runs/vla/d_ruling_round_20260930_1205/r108_false_absence_fix_result.json`）。
- **③ 记你五功**：阈值盲设且跨三版一个数字未动 · **主动披露自己不是盲测**而没有假装盲 · 把「数值相等」与「逐位相同」分开报（`n_exact_zero=40` vs `n_quat_bitwise_identical_A0=0`，成因 -0.0/次正规）· **没有**因为量出 0.0 就事后去动 R2 的 RED / 14 个 `grip2` 例外 · 冻结面 0 触碰（D 用 mtime 独立核）。另：你自己写明 **1.0° 不是亚像素**（base 相机 1° 下 [15, 43, 60] px 变）⇒ 这处诚实 D 记在裁定 108-⑤。
- **④ C6 的作用域修订（A0→A1）D 接受了，但附一条条件**：它是**有效性**控制、不是甲/乙判据；A0 在 `reverse` 上带一个**先前已登记**的常量 x 偏移（**0.20000438825779476 m**），而 Step-1 **不消费** `reset(seed)` 的方块位置 ⇒ 不进初态；A0 残差**未删**、镜像不变对照 **3.6488177822951995e-08 m** 覆盖同一物理问题。**条件**：这次修订**必须**在你的六问报告里作为**「已披露的有效性对照事后作用域修订」**出现（连同你的非盲披露），不能只留在判词件里。
- **⑤ 报告必须带的三条（缺一 ⇒ 里程碑审查不通过）**：**(a)** `demo_init_box_quat_not_written` 作为**已登记混淆项**（`must_appear_in_step1_report=true`）；**(b)** C6 作用域修订 + 阈值非盲披露；**(c)** 补单九-⑤ 仍欠的那件 —— R2 的 **14 个 `grip2` 例外逐行归因**（几个落在方块运动帧上）。**另外**：夹爪转变帧上的失败一律记 `supervision_alignment_unresolved`，**不得**写成 policy failure（裁定 104.1）。
- **⑥ 排队纪律与停点（全部不变）**：守望器 PID 150202 **不要停**（现 poll **122** 次、末次 `2026-09-30 20:56:05 [poll 122] rc=1 clean_streak=0/2 status=measured busy=True util=100% mem=34759MiB apps=1 fd=9 cmd=0 loadavg=33.54 33.59 34.35 nr_t`）；卡由隔离线进程持有（PID 236200、34752 MiB）—— **裁定 46.4：这只是排程事实，不构成对隔离线的判定，你不要去动它**；等待期**不空转烧 CPU**（不重跑 `probe`/`cache`/全树扫描）；**22:20 后不起跑** ⇒ 日报 `## §A2` 追加一行「今日未起跑 + poll 次数 + 末次三网读数」，次日 08:00 重新 `declare` 新窗口并重新武装（补单九-⑥）。判据常量继续冻结（`PRE_REGISTRATION_v2.json` **805 ln(`wc -l`) `2e32f76ad1d2`**；判据脚本前像 **4206 ln(`wc -l`) `e75d2284fd6c`** 在盘）。
- **⑦ 备份窗口（D 已替你预登记，你不用补）**：D 的本地备份 20:20:52 起（pass A done 20:37:03 / pass B done 20:41:21 / `BACKUP_DONE.txt` 已落盘）；你的四元数测量 2026-09-30T20:17:57+08:00→2026-09-30T20:21:19+08:00 与它**重叠约 27 s**，但该测量 `gpu_used=false`、不产出 GPU 窗口件 ⇒ **不影响产出⑤**，此事实已写进裁定 108-⑦。**补单十-② 的义务照旧**：train/rollout 若与备份窗口重叠 ⇒ 产出⑤ 标 `contaminated_by_cotenant=true` + 报告点名 `overlaps_d_backup_window: true/false` + 依据；**不得为此改 `card_busy()`**。
- **⑧ 出结果就停**：六问答完（含 Step-1 的 6 项产出逐列 + 4 条验收标准逐条判 + 每种子/每方向单独报数）⇒ **停，等 D 的里程碑审查，不开 Step 2**。**裁定 46**：`max_stage==4` / GREEN **不得**写成能力；阶段话术只用「主线已成功纠偏，实验基础正在收敛；已有对齐和接口诊断产出，但策略学习结果仍为零」。

## 补单十二【裁定 110：**路线未偏离**（跑前审计 route 12/12 全过）；**里程碑审查延后到你本轮跑完**；开跑前只有**一件**事要做（判据身份件重发，CPU-only）】（2026-09-30 22:44 · D · 交接件前像 `before_images/d_handoff_to_a2_20260930.md.before_r110_12` = 332 ln `a09942996688`）
- **① 先给你结论：路线没偏，申报态质量高。** D 只读审计 59 项（A2 字节零改动）：57 PASS、**1 项实质 FATAL**、1 项记账 WARN；**route 12/12**、**冻结输入 9/9**、**准入耦合 13/13**、**能力声明禁令 3/3**、**作废键卫生 5/5**、**常量重复 0**。件 = `runs/vla/d_ruling_round_20260930_1205/D_STEP1_PRERUN_AUDIT.json` **705 ln(`wc -l`) `77fa75270b05`**。特别记功三处：`checkpoint_selection_rule` 用 `val_det_loss` 而**明令禁止**用 rollout 成功率挑 ckpt · 推进度取 C2 的 `JudgmentFacts` 而**避开**方向写死的 `env reward==4` · 准入是 **AND**（C2 的 `consume_c2_broadcast().admitted` ∧ 你自己的先落腿牙 A2T1 GREEN 12/12），消费的是 **class1=PASS 的那一跑** `run_20260930_133156`（裁定 97.5 口径，不再拿顶层 verdict 当停训理由）。
- **② 审查延后（用户排序）：D 不在你跑中介入。** 等你 **train/rollout/report 跑完 + 六问报告落盘**，D 再做里程碑审查（F 到场）。期间 D 只轻巡检 + 只读审计，**不催、不打断**。理由：跑中插裁定会让两套判词/上下文交错 ⇒ 正是用户担心的「结果混乱」。
- **③ 开跑前只做这一件（CPU-only、不占卡、今晚排队期做最合适）**：把 `CRITERIA_IDENTITY.json` **对将要执行的那一份字节重发**。事实：身份件（as_of 2026-09-30T19:13:06）引 `e75d2284fd6c`（4206 ln），而判据脚本现值 = `2ec02373d3f6`（4327 ln，mtime 2026-09-30T19:30:00）⇒ 红线 §100.3-(d) **只履行一半**（前像 ✔ / 身份件未重发 ✗）。**D 已经替你把 diff 做完了**：5 hunk、**+123/−2 行**、**0 处判据常量变化**，删的那一行正是裁定 104.2 点名「『唯一』现在是错的」那句，新增只有 `box_quat_defect_status` 管线 ⇒ **判据中性**；9 个冻结码面 declared==now 全 OK。**但 D 事后证明中性 ≠ 红线履行**，所以要你重发。**重发时带两样**：判据脚本现值身份 + **生成器现值身份**（`tmp/a2_step1_criteria_identity.py` 已于 20:24:55 变过 —— 别又产出一件「描述的不是产它的那份字节」的身份件）。
- **④ 竞态兜底（不需要任何人在线）**：若守望器在你重发之前就起跑 ⇒ **那一跑仍有效、不作废**；把 D 的审计件 `runs/vla/d_ruling_round_20260930_1205/D_STEP1_PRERUN_AUDIT.json`（`77fa75270b05`）作为**桥接证据**随六问报告出，并在报告里登记为**已披露混淆项**（形状同裁定 104.3 的兜底）。
- **⑤ 今晚不起跑，而且你的排队机制现在是空的（既有规则的执行结果，不是新令；读数机取自 D 的探针件 `runs/vla/d_ruling_round_20260930_1205/D_LIVE_STATE_20260930.json` **192 ln(`wc -l`) `3d88bb4d9cc4`**）**：有界等待线 **22:20** 已到 —— 你的守望器（PID 150202）**已自行退出 0**：poll **204** 次（2026-09-30 18:53:41 → 2026-09-30 22:19:02）、**2026-09-30 22:20:02** 在登记处 `yield` 窗口 2（**从未起跑**）；登记处你的末事件 = `yield`(`step1_bc_overfit_w2`)。卡仍由隔离线进程持有（**PID 388024**、33792 MiB）。**你必做两件**：**(a)** 在日报 `## §A2` 追加**一行**「今日未起跑 + poll 次数（**204**）+ 末次三网读数」—— 截至 2026-09-30T22:44:41+08:00 **尚未追加**（别以为写过了：D 按段作用域核过，全文同名字样只在 §D104-⑥ 的规则原文里）；**(b)** **次日 08:00 重新 `declare` 新窗口（新 `task_id`，不得复用已 yield 的 `step1_bc_overfit_w2`）+ 重新武装守望器** —— 裁定 104-⑥ 明写「此后没有任何机制会在次日重新武装 ⇒ 主线会静默死掉一夜」，**这一件只有你能做，D 不代做**。**排序**：把 ③ 的身份件重发放在今晚排队期做完 ⇒ 明早窗口一开即起跑、不带前置阻塞。**裁定 46.4**：那个 PID 只是排程事实，**不构成对隔离线的判定，也不要去动它**。
- **⑥ 六问报告的三条硬要求（防你自己上下文过长导致语义漂移；不是新门禁，是判词质量要求）**：**(a)** **每个数字由脚本从件里读出**并附 `path` + `sha256[:12]` —— **不得凭记忆或从对话历史转写**（D 自己刚犯过：⑲#25 把草稿散文带进了判词）；**(b)** **不得复用旧轮的措辞与数字** —— 特别是 G3 的 `0/20`、probe 阶段读数、以及任何已被超越的结论（例：早上有分析说 `matrix=RED`，**现值 13:32:02 已 PASS**；引旧值就是语义漂移）；**(c)** **判词只由判据脚本产**（`STEP1_REPORT.json` / `STEP1_RUN_SUMMARY.json`），六问报告是**指针不是副本**；两者冲突 ⇒ **以件为准**，并把冲突本身报 D。
- **⑦ 报告必带的清单没变（补单十一-⑤ 三条 + 本条两项）**：`demo_init_box_quat_not_written`（已登记混淆项，`measured_and_immaterial`、**不销账**）· C6 作用域修订（A0→A1）+ 阈值非盲披露 · R2 的 **14 个 `grip2` 例外逐行归因**（补单九-⑤，仍欠）· **新增**：③ 的身份件重发结果（或 ④ 的桥接登记）· **新增**：产出⑤ 的 `overlaps_d_backup_window`（备份窗口 **20:20:52 → 20:48:43 已结束**、判据 `bigkey_bad=0` 已达成 ⇒ 你今晚之后起跑**不会**与它重叠，照实写 `false` 即可）。夹爪转变帧上的失败一律记 `supervision_alignment_unresolved`，**不得**写成 policy failure（裁定 104.1）。
- **⑧ 停点不变**：出结果 ⇒ 六问答完（Step-1 的 6 项产出逐列 + 4 条验收标准逐条判 + 每种子/每方向单独报数）⇒ **停，等 D 的里程碑审查，不开 Step 2**（即使卡空着）。**裁定 46**：`max_stage==4` / GREEN **不得**写成能力；阶段话术只用「主线已成功纠偏，实验基础正在收敛；已有对齐和接口诊断产出，但策略学习结果仍为零」。
