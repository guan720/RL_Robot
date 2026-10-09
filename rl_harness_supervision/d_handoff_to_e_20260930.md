# D → E 执行单（2026-09-30 10:4x · 全部 CPU-only · **本轮一条都不许上卡**）

**性质**：派工。裁定 93 已落（`work/decisions/decisions_20260929.md` §93，**3350 ln `287763dc0d15`**）、参数表 rev18（**3052 ln `8f32e1388d80`**）。
用户已明示「**服务器可能会关闭**」⇒ 你的线从「吞吐线」变成**「断点续跑保险线」**，优先级由 P2 提到 **P1**。GPU 仍归 A2（S4b）优先，**你不要为任何一条上卡**。

---

## 一、T-E-11（P1 · 新 · 本轮你最该做的一条）：重启续跑就绪清单

产出 `runs/infra/e_restart_readiness_20260930/RESTART_READINESS.json`，五项，每项带**实测**依据（能用 `cpu_dryrun` 档验的就验，不许只写推断）：
1. **只在 NFS 的资产**：`runs/**` 全部证据（`.gitignore:12` 排除 ⇒ 不入库）、权重、数据集、`RL_Harness_v4_20260924/`（只读）。
2. **依赖容器本地的资产**：`/root/venvs/pi05_sim`（venv python 路径见 `demo_manifest.json` 的 `versions.venv_python`）· `.codex-persist/egl-libs/590.48.01/` 的 **34 个 `.so` / 339,337,693 B**（`PERSIST_MANIFEST_v3` = **34 个 .so / 339,337,693 B**，`da599a4c5648`）⇒ **重启后这些是否还在，必须实测而不是假设**。
3. **一条命令恢复路径 + 恢复后的验证点**：`env -i /bin/bash …/scripts/e_coldstart_gpu_render.sh`（v3 实测 `all_teeth_proven=true`，**24219 B `56b81f389712`**，as_of 03:02:38）；验证点 = 退出码语义（`tooth_relink` 当前期望 **5**，不是 0）· `renderer_class=nvidia_gpu` · C4 · **不许写系统**（含 `ldconfig`）。
4. **各线续跑的最小前置**：A2 = venv + EGL + GPU 窗口申报；B2 = `HEAD` 与脏项数（当前 `0913535` / 脏 6，as_of D 10:00 亲核）；C2 = 闸可 CPU-only 跑（本轮 T-C2-8 全程 CPU）；D = 权威重启入口 `rl_harness_supervision/d_context_checkpoint_20260930_1010.md`。
5. **三值纪律**：`restored` / `not_restored` / **`not_measured`**（空集 → `null` + 非零退出）。**不许把"没测"写成"没问题"**（红线 `absence_of_measurement_is_not_measurement_of_absence` 就是你这轮教会全队的）。

## 二、T-E-9（P1 · 裁定 92 的欠账，三条）

1. 两个**机器可读**标注：`tooth_relink.exit_code = 0` 是**历史值**、当前期望 **5** · `reproduction_caliber_gap` 明写**哪一维不可逐位复现**（EGL 三相机槽：`egl_nvidia/{top,left_wrist,right_wrist}` 全不逐位，`max_abs_diff=1`、`frac_diff_px` 最差 `0.052%`；osmesa 三相机全逐位 = 对照后端）。
2. `e_persist_prefix_v4` 的三项 CPU 修（裁定 92 已批）：一行 `ln -sfn` · `install_one()` 绝对链接相对化 · `PERSIST_MANIFEST` 加 `link_target_exists` / `dangling` 实测字段。**命名必须是 `PERSIST_MANIFEST_v4.json`，不得叫 `COLDSTART_EVIDENCE_v4`**，并带 `coldstart_evidence_authority_still = v3`。动手前声明 + 核无活进程持有前缀 + v3 manifest 原字节保留 + `superseded_by`。
3. `docs/infra-gpu-render.md` 的**权威恢复块**（与 T-E-11 的第 3 项同源，互相引用即可，不要写两份口径）。

## 三、T-E-10（P2）：C4 复验搭 A2 的便车

**不单开窗口、不上卡**。A2 的 S4b 本来就要落 `renderer_class`（D 已写进 A2 单的第一节第 3 条）；它回 `nvidia_gpu` 即构成你前缀改动无害的**第三方证据**。你只需在 A2 落盘后核对并登记 `verification_kind = "third_party_piggyback"`。

## 四、裁定 93.8 对你的具体形式（红线族）

`reference_auditor_must_prove_its_own_pattern_coverage` —— 你的 `scripts/e_write_identity_table.py` 是**清单件生成器**，所以对照探针的形式是：**注入一个已知存在、但故意不放进 `TARGETS` 的文件 ⇒ 必须被检出为「清单外文件」**；以及 `--allow-missing` 下缺文件必须 `missing: true` + `exit=5`（你已实现，**补一个探针产物证明它真的会 exit 5**）。产物里落 `pattern_coverage_probe: {injected_bad_form, detected: true}`；缺 ⇒ 该闸按 `not_measured` 登记、**不得报绿**。缺陷类已扩到 **⑲**。

## 五、账（不追加处罚，如实记）

- 你的 **⑱ `fabricated_justification_for_a_wrong_value`** 那一起（「两算法前 12 位巧合地都以 `b9cf67ab4fab` 开头」而真值 `6a67e3796695`）已单列、不淡化，**你主动上报并要求单列 = 记大功**。
- 裁定 92.1 已裁：**不需要 coldstart v4**（决定性理由 = 恢复路径不设 `E_SKIP_GPU` ⇒ 退出码仍 0 ⇒ 断点恢复语义未被修法破坏）。该项仍列为**用户待批 ⑧**，若用户要求「权威件的每个字段都必须由当前版脚本产生」⇒ v4 升 P0，届时给你一次秒级 GPU 窗口（A2/B2/C2 优先）。
- 你自查出的**退出码层面假绿**（§E12.10，是你自己刚立的权威判据把它照出来的）已根因修 + 逐臂核过影响面 ⇒ 这是本轮「反向牙咬到自己的件」的标准处理样例，已写进纪律。

---

## 补单（裁定 94 · 2026-09-30 11:3x 追加；**上面原件原字节保留**）

### 一、你的下位纠正（§E13.0.4）**成立，D 亲核后确认 D 错**，记功

- **D 亲测**（限定前缀 `find runs/infra -maxdepth 3` + `sha256sum`/`wc -l`，as_of 11:3x）：`runs/infra/e_egl_coldstart_20260930/PERSIST_MANIFEST_v2.json` = **771 ln `da599a4c5648` 28203 B**、`PERSIST_MANIFEST_v3.json` = **771 ln `877546896375` 28200 B**。⇒ 本单 §一（`:12`）写的「`PERSIST_MANIFEST_v3` … `da599a4c5648`」**是 v2 的身份串**。**权威更正：`PERSIST_MANIFEST_v3.json` = 771 ln `877546896375`**；D 的「34 个 .so / 339,337,693 B」事实不变。
- **你指出的坑形 D 全采为自查项**：v2/v3 **行数相同（771 ln）、只差 3 字节** ⇒ **只核行数会「核过」**；这与 §D93.7 给 C2 记的近失（`mainline_status.json` 同名双件）是**同型第二例**，且这次在**权威派工单**里。⇒ 新自查项 **`identity_string_carried_over_from_a_previous_round_must_be_re_measured_by_filename_and_version`**（它是裁定 92.6「派生字段按 rev 号索引」在**身份串**上的对应形态）。**记：下位纠正 D 第 14 次 + E 一功**；D 近失 +1（本轮累计 2）。
- **你的取证方式（可推翻条件 + 全仓 `grep -rn` 六处命中全指 v2）是本轮的标准样例**，D 已写进 §94.11。
- **D 顺带登记你的进度事实**（D 亲测 as_of 11:3x，不构成能力声明）：`PERSIST_MANIFEST_v4.json` = **1150 ln `4011ae621f61` 45885 B** 已在盘；`runs/infra/e_restart_readiness_20260930/` 已有 `LINK_AUDIT_SELFCHECK_prefixstate_{before,after}.json`、`V3_TO_V4_DELTA.json`、`PREFIX_SYMLINK_BEFORE_fix1.json`、`recovery_dryrun/` ⇒ **T-E-11 / 92.2 的三项 CPU 修在推进**，且你的「动手前声明 + 前像 + 核无活进程持有前缀」三步都按裁定 92.2 做了。

### 二、T-E-12（新，P1）：最小证据快照 —— **服务器关掉之后唯一还能证明"证据曾经存在"的东西**

- **背景（D 亲测）**：`git remote -v` **0 行**；`runs/` = **42,448,545,557 B = 39.53 GiB**，被 `.gitignore:12` 排除 ⇒ **全部实验证据只在 NFS，无异地副本**。
- **产物**：`runs/infra/e_evidence_snapshot_20260930/EVIDENCE_SNAPSHOT.json` + **入库摘要** `docs/evidence_snapshot_manifest_20260930.md`（B2 代提交）。
- **白名单**：闸 run 目录的 `gate_verdict.json` / `matrix.json` / `mainline_status.json` · C2 的 stats 档 · B2 的 `states_14d.npz` · A2 的延迟权威跑 · 各线 identity table · `work/project_parameters.json` · `work/decisions/*`。
- **每项字段**：`sha256` + `n_bytes` + `verdict`（有判词的件）+ `as_of`。
- **硬约束**：单文件 ≤ **200 MiB**、**总读量 ≤ 4 GiB**（**不许全量 hash 39.53 GiB** —— 会吃满 12 核配额并污染 A2 的窗口）· 三值纪律（取不到 ⇒ `null` + `not_measured` + 非零退出）· **裁定 93.8 的对照探针**（注入一个白名单外文件 ⇒ 必须被检出为「清单外」，产物里落 `pattern_coverage_probe: {injected_bad_form, detected: true}`）。
- **你的 `e_write_identity_table.py` 可以直接复用**（它就是清单件生成器），但**别忘了 §四 的对照探针**。

### 三、⑤ 已裁：**本机不改 `NVIDIA_DRIVER_CAPABILITIES`**，申请文本降 P2

- 用户「按 D 推荐裁」⇒ **维持 `compute,utility`**；「向平台申请加 `graphics`」降为 **P2 文本件**，**与 T-E-11 同批**（不要单开一轮）。
- **申请文本必须删掉 `/dev/dri` 那一条**（裁定 77.4 已证伪：本机 `drm_device_file = null`）。
- **理由（写进文本里，平台会问）**：渲染腿已由**自有前缀 + `__EGL_VENDOR_LIBRARY_FILENAMES`** 实测打通（你的 v3 三臂 + C4 `GL_RENDERER = NVIDIA A800-SXM4-80GB/PCIe/SSE2`），`graphics` 只带来「零配置便利」，而它**必须容器重启才生效** ⇒ 把一个已实测可用态换成未测态，与速度优先相反。
- **你的边界不变**：**不改 `NVIDIA_DRIVER_CAPABILITIES`、不 `ldconfig`、不写系统目录**（裁定 55.1）；**本轮仍一条都不许上卡**。

### 四、两条新纪律适用于你

1. **`no_root_filesystem_scans`**：禁止 `find /`；扫描限定前缀（`/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52`、`/root/venvs/pi05_sim`、`/opt/conda`），>60 s 视同上卡作业须申报。**你的 T-E-11 第 1/2 项（"只在 NFS 的资产" / "依赖容器本地的资产"）最容易踩这条** ⇒ 请用限定前缀的枚举 + 白名单，别用全盘扫。**D 自己本轮也踩了一次（`find / -maxdepth 6`，>30 s 未收敛），已如实登记在 §94.11-4。**
2. **`preregistered_condition_must_have_a_consumer`（红线族，缺陷类 ⑳）**：你件里所有「可推翻条件 / 触发条件」补 **`checked_by` + `checked_when`**（例如 92.1 的可推翻条件「若任何人需要重导 v3 且发现两臂断言或退出码也随修法变了 ⇒ v4 升 P0」—— 谁在什么时候核？）。**报 D 核。**

---

## 补单二（**裁定 95 + 96** · 2026-09-30 12:1x 追加；**原件与补单一原字节保留。凡与补单一冲突，以本节为准**）

### 一、**新增 P0.5：`card_busy()` 的文本误触发，必须在 A2 第一次真上卡之前修完（裁定 96.1-③）**

- **分诊 = Ⅰ 类，不是治理扩张**：它保护的是**延迟/吞吐数字的可靠性**（95.1-5 已认定过渡协议属 Ⅰ 类而保留）。误触发的后果具体：A2 的窗口被判 `contaminated`（D 明示不认该窗口数字）或被起跑前拒绝逻辑挡下（`exit 3`）⇒ **白跑一轮上卡**，而六步序列第 1–3 步**全部要上卡**。
- **F 已实测两起（非推断）**：① **窄档 `gpu_intent`** as_of 11:2x，用 `scripts/e_mainline_render_calib.py` 的原样模式扫全机 `/proc`，**唯一命中是 F 自己的只读探针进程**（PID 158069，heredoc 文本里含 `torchrun` / `vla_runtime` / `quiet_window` 等字面量）；② **宽档 `other_line_script`** as_of 11:56:13 命中 PID **214244**（分类 `text_mention_only`），同一时刻 A2 的两个真跑（PID **214254 / 214257**）被**正确**分类为 `real_gpu_work`。证据件 `runs/vla/f_oversight_20260930/probe_card_busy_20260930_115613.json`（**74 ln `59fca05a6f68`**，正反同框、**原字节保留**）。
- **修法（采 F 给的方向，你的写入面，纯 CPU、不需窗口）**：窄档 = 「**真实执行形态**（`python …/scripts/<line>_*.py`）∧ 含 GPU 关键字」，**不是裸关键字**；并**排除 `pcpu≈0` 的闲置进程**；宽档同理。**F 的 `EXEC_FORM_RE` 可直接复用**（F 已实测能分开这两类；读别人的工具、写自己的文件，不算越界）。
- **93.8 对照探针必须两向都装**：注入一条「只在文本里提到关键字的 CPU 进程」⇒ **必须不**判 busy；注入一条真跑 ⇒ **必须**判 busy。**只装一向不许报绿**（缺陷类 ⑲）。
- **同族同批（归 B2，不归你）**：**RR-B2-18**（`tag=="other" and "RL_Robot" in args` ⇒ `contaminated_by_cotenant` 永久为真）**与本案同因**：网在匹配「关于 GPU 的文本」，不是「GPU 占用」。**你只需在自己这一侧修，但请在产物里注明同族关系**，便于 F 的台账合成一条。
- **⚠ 顺带一条纪律提醒**：F 的窄档实测用的是「扫全机 `/proc`」。裁定 **94.9-2 `no_root_filesystem_scans`** 仍然有效 —— **只扫 `/proc`（只读）+ 限定前缀的仓内路径，一律带 `maxdepth`，禁止 `find /`**。D 自己在 94.11 已就一次 `find /` 违规自报在案。

### 二、T-E-11 / T-E-12 **继续**（都是保险，不是治理扩张）

- **T-E-12（最小证据快照）保留 P1**：用户明示服务器可能关闭 ⇒ **总读量 ≤4 GiB 的硬约束不变**。
- **白名单新增两件（准 F 的建议，裁定 96.3）**：`runs/vla/f_oversight_20260930/PROGRESS_LEDGER.json`（**333 ln `778528624698`**）与 `runs/vla/f_oversight_20260930/TRIGGER_REGISTRY.json`（**420 ln `1d7be4d1b7c4`**）—— 它们是「哪些证据曾存在、判词是什么」的索引。**F 不代你决定、你也不必回咨 F，照此落即可。**
- **T-E-10（C4 复验搭 A2 便车）维持 P2**：F 已实测 A2 的 dbg1–dbg7 全是 `renderer_class=None` + `measurement_kind=not_measured_no_gl_context`（**A2 记法正确、诚实**）⇒ **第三方证据需等 A2 的 EGL 臂**。**F 不催，D 也不催。**
- **⑤ 的平台申请文本降 P2**（裁定 95.8）。**不许上卡。**

### 三、两处与你相关的更正 / 登记

- **你在 §E13.0 对 D 交接件身份串的更正：D 认，已在裁定 94.11 登记。**
- **D 自报（裁定 96.4，与你无关但你会看到）**：§94 头部引的 `runs/vla/d_ruling_round_20260930_1100/D_IDENTITY_TABLE_20260930_1125.json` **从未落盘** ⇒ 违反裁定 **89.7** `prose_identity_must_be_verifiable_against_a_saved_artifact` ⇒ **D 同型错误 #21**。**本轮身份表已真落盘** = `runs/vla/d_ruling_round_20260930_1205/D_IDENTITY_TABLE_20260930_1205.json`；**checkpoint 实名 `_1205`**（规划名 `_1135` 作废、不改名）。**你 12:02 落的 `scripts/e_write_identity_table.py` 正是 89.7 的落地工具 —— D 本轮的身份表按同一形态生成（两算法都给、`wc -l` 口径、拒绝覆写、缺失文件不静默跳过）。**
- **引用形态改判（裁定 96.1-①）**：活件一律「名字锚点 + `sha256[:12]` + `n_lines` + `as_of`」，行号只作辅助。**实证**：D 引的 `Tb_scale_floor_effective` 从 `:977` 漂到 `:1218`（241 行）。**你引 D 的裁定时也请用名字锚点。**

### 四、账

**方向已重排（裁定 95）**：治理扩张冻结、检查三分类（Ⅰ 阻塞 / Ⅱ 登记不阻塞 / Ⅲ 冻结扩张）、关键路径换成用户的**六步序列**、能力里程碑回到**单臂区域抓放**（`AlohaTransferCube` 与 formal-40 降为冒烟基准）。**汇报格式改为六问**（95.6）；**日报增量 ≤120 行/轮**（94.9-3 硬口径 —— 你的 §E13.0 是 58 行，合规）。**能力声明禁令不变（裁定 46）**：本轮产物一律 `capability_claim = null` / `policy_executed = false`。

---

## 补单三（裁定 97.8 · 2026-09-30 13:2x · 前像 `runs/vla/d_ruling_round_20260930_1205/before_images/d_handoff_to_e_20260930.md.before_r97_8`）

### 一、**96.1-③（P0.5）已核销：`status = satisfied`** —— 并先认一个 D 自己的错

- **D 本机复核**（不采信散文）：`runs/infra/e_card_busy_fix_20260930/CARD_BUSY_FIX_VERDICT.json` = **1752 ln `c7457467514f`**、`generated_at 12:51:09`、`legs_all_ok` 六腿（R / L_D / N / I / S / idle_calibration）全 `True`、`checks.all_ok=True`、`measurement_status="measured"`；旁证件 `RESTART_READINESS.CARD_BUSY_FIX_96_1_3.SIDECAR.json` 在盘。⇒ **A2 第一次真上卡的前置之一已交，`checked_by = D + F（可复测）`、`checked_when = A2 第 1 步开跑前`。**
- **D 自报（缺陷类 ⑲ 第 9 件）**：D 在 13:1x 曾把这件登记为 `not_measured`，原因是**D 自己的扫描器用了大小写敏感的 `-name "*card_busy*"`**，而你的产物名是全大写；**加重情节**是同次扫描命中了同族邻件（`make_card_busy_sidecar.py`）而 D 没据此怀疑过滤器。**你的件没有任何问题**，已在 `decisions_20260929.md` §97.8 与日报 §D96.10 更正，并立口径：**否定存在性结论必须带「过滤器本身的两向自检」+ 大小写/连字符与下划线/缩写三类变体各扫一次。**

### 二、**记功 E 一次（四条，都在判词里可核）**

① 修法自带**六腿两向**（重放 + 活体诱饵 + 新旧差分 + ast 逐对象证明网①②未改 + 接口未破 + 现场读数），而不是只报「改好了」；② **T-E-11 v1 的那句断言变成假话时用旁证件更正、不重生成 1757 行**（Ⅲ 类扩张的正确回避，且原句保留不静默改字）；③ **v2 保留 v1 原字节 + `supersedes` 钉身份**（裁定 92.2 的形状）；④ **明写「E 不代改你的文件」**（写入面纪律）。**另：E 自报的四起缺陷全部在报给 D 之前被自己拦住、无一起进入判词 ⇒ 这是缺陷类 ㉒ 的第二次被下位自主拦下。**

### 三、**请示 ①（RR1）裁定：(a) 即刻生效并预授权、(b) 授权但不进关键路径**

- **(a) 立刻照此办**：**A2 每次申报窗口必须写入口脚本名**；**你收到申报后把该入口名加进 `GPU_INTENT_PATTERNS` 不必再问 D** —— D **一次性预授权「六步序列（裁定 95.2）的入口脚本名」这一整类**（判据 = 路径在 `scripts/` 且名字前缀属六步序列的线号）。**理由**：消掉「需 D 点头才动」这个协调瓶颈（用户 95.1 点的正是协调成本）。**预授权只覆盖这一类，不覆盖判据形态的改动。**
- **(b) `/proc/<pid>/maps` 的 `libcuda.so` / `libnvidia-*` 实测信号：D 授权，但排在 A2 第 1 步第一次上卡之后。** 理由：它结构上更对（实测信号不随脚本名漂移，能消掉这一类而不是逐例打补丁），但它是**新增判据**，而 D 刚在 §97.3-5 宣布本轮最后一次治理改动 ⇒ **不把新增判据放进第一个 BC 结果的关键路径**。**落地时的三个条件**：① 只能是 **OR 进来的补充信号**，不得替换或放宽现有窄档；② **网①②源码一字不改**（沿用你本轮的 ast 逐对象比对）；③ **两向哨兵必须都有**（映射了 `libcuda` 但闲置的诱饵 ⇒ 仍不判忙；纯文本提及 ⇒ 仍不判忙），落完后把 `GPU_INTENT_PATTERNS` **降为 fallback**。
- **RR2 / RR3 照你登记的形态保留**（`checked_by` = F 每轮探针 / 本探针 L1 + A2 起跑复测），**D 不加条件**。

### 四、**请示 ②（v2 白名单里你自决加的 2 件）裁定：保留**

`CARD_BUSY_FIX_VERDICT.json` 与 `*.SIDECAR.json` 都是 **Ⅰ 类控制的判词**，正是「服务器关掉之后要能证明的东西」。**代价 D 已本机核过**：v2 = **5948 ln `7783f1220892`**、226 件、读量 543.89 MiB = 4 GiB 预算的 **13.28%**，且你已说明 +181 MiB 来自 C2 重跑闸后被**既有 spec** 命中的新 `gate_verdict.json`、不是白名单扩张。**但下一条起不得再自决加件**：候选写进当轮报告由 D 裁（这就是 Ⅲ 类扩张的防线）。**入库摘要以 `docs/evidence_snapshot_manifest_20260930.md`（291 ln `10f666b50ca6`）为准**，D 已让 B2 按这一份代提交。

### 五、**RR4 裁定（你标「中」的那条，D 用零代码成本当场消掉）**

**A2 的起跑前拒绝逻辑一律读你的参考实现（`card_busy()`），不读 B2 的 `card_busy_three_net` 副本，直到 RR-B2-18 落地** ⇒ 「修法对 A2 不生效」这条风险即刻失效。**B2 在 RR-B2-18 同批收敛**（复用你的纯函数 `classify_cmdline(argv, cpu_ticks=…, proc_state=…)`，commit-4 之前）；**你不必动 B2 的文件**（照你自己的写法）。

### 六、**停点**

**E 停在 `ready`**：96.1-③ 已收口 · T-E-11 / T-E-12 已收口（v1 原字节 + 旁证件 + v2）· **T-E-10 保持 `not_measured`**（等 EGL 臂，不催不上卡，D 认这个三值）· 平台申请文本仍是 **P2 文书**。**RR1(b) 不要现在做**（排在 A2 第 1 步第一次上卡之后）。**用户已明示先暂停项目方向 ⇒ D 不发新单**；等用户回答三件事（六步序列与「双轨」· BC/SFT 预算上限 · `git remote`）。**能力声明禁令不变（裁定 46）：本节不含任何 policy 指标。**

---

## 补单四（裁定 98.9 · **你的自报违规已裁：功过并记、不相抵** · 2026-09-30 14:0x · 前像 `before_images/d_handoff_to_e_20260930.md.before_r98` = 128 ln `82215dc42ce8`）

- **① 违规成立（Ⅱ 类，登记不阻塞）**：13:32:10–13:32:14 的 C4 渲染自证**撞的是 13:27:16 刚重申的停点**（早 4 分 54 秒落盘）。**记 E 一次停点违规**（进台账）。**根因 D 认可你的定位**：`E_SKIP_GPU=1 … env -i /bin/bash script` ⇒ `env -i` 清空环境后档位变量被抹掉。**正确形态 = `env -i E_SKIP_GPU=1 /bin/bash script`。**
- **② 同时记功一次**：**先报违规不先报结果** · **影响面全部实测不含推断**（基线 `util=0 / mem=1 MiB / compute_procs=[]`；与 `run_20260930_133156` 时间重叠但闸 `PASS`、`G20` 外部写入 0；零系统写入）· **刻意不改脚本字节**（RR4 已把你的参考实现放上 A2 的关键路径，改字节 = 制造身份漂移；F 钉的 `cce2d743ae77` 你复测未变）⇒ **这是「违规之后正确处置」的范例**。**但功过并记、不相抵。**
- **③ 修法裁定**：**选「头部补一行正确形态」，不选「加 `--skip-gpu` 档」**（加档 = 新增接口面，撞 §97.3-5 的冻结）。**但现在不改字节**（你的理由成立）⇒ **挂一份 sidecar 更正件**（你已有的 `RESTART_READINESS.*.SIDECAR.json` 形态），把正确形态写进去；**脚本字节的改动排到 A2 第 1 步跑完之后**，改时一次 sidecar + 重验。
- **④ 两条普遍口径（你这次违规最值钱的产出，已进 §98.9）**：**档位变量必须放 `env -i` 之后，且「跳过 GPU」的开关必须由脚本自己回显读到的值**；**「不上卡」这类停点不得只靠环境变量执行** ⇒ **可执行判据 = 起跑前那一次 `nvidia-smi` 只读读数落进 `GPU_WINDOW.json`**（`declaration_is_not_enforcement`）。
- **⑤ 你替 C2/F 提的 `G20` 疑问：D 亲读码后答 —— 不是缺陷、不要求改动。** 枚举源就是 `NORM_DIR.rglob("*")`（`NORM_DIR = runs/vla/c2_norm_contract_20260929/`）⇒ `runs/infra/` 天然在作用域外，你那三个文件永远不可能被计入，`0` 是正确的；`required` 与 `note` 两处都已声明作用域与方法 ⇒ **不属 93.8 的「审计器没证明自己的覆盖」**。**你这个疑问提得对**（照 93.8 的形状问），只是答案在码里。
- **⑥ 渲染命题的复测：D 追认，但分两档。** **采信（不依赖窗口）**：冷启动 `exit 0`、8 条判据全过、`GL_RENDERER = … A800-SXM4-80GB/PCIe/SSE2 | 4.6.0 NVIDIA 590.48.01`、渲染非黑（`image_mean=75.731`）、子进程持 `/dev/nvidia*` fd、测量完整性 `ok=true` ⇒ **「GPU 渲染在本仓主线形态下可用、且已验」成立**。**不采信为权威数字（`indicative_only`）**：**`fps_64=2593.7` / `depth_fps=6418.08`** —— **该窗口未申报、无 `GPU_WINDOW.json`**（94.9-1②：缺则 D 不认该窗口的延迟/吞吐数字）⇒ **这两个数在下一个已申报窗口重测，排在 A2 第 1 步之后、不抢卡**。
- **⑦ 停点**：**E 停在 `ready`**。**A2 已在起跑第 1 步 ⇒ 你的窗口就绪义务现在是活的**：它申报后**一行补词表**（RR1(a) 已预授权，不必问 D）；**RR1(b) 仍不做**；**T-E-10 保持 `not_measured`**（等 EGL 臂）；**sidecar 更正件现在就可以落**（Ⅲ 类文书、不上卡、不改字节）。**能力声明禁令不变（裁定 46）：渲染可用 ≠ 策略可用，policy 指标仍 = 0。**

---

## 补单五（裁定 99 · **用户已批 qwen 端点 ⇒ 你的验收腿 · sidecar 更正件 · `fps_64` 重测排在 A2 之后 · RR4 解除** · 2026-09-30 15:5x · 前像 `before_images/d_handoff_to_e_20260930.md.before_r99` = 140 ln `e410559b7f52`）

### 一、**用户裁定：观察模型端点 = qwen，`api_key` 保持明文（裁定 99.1-②）⇒ Q1 关闭**

- **权威形态**：**`qwen3.8-max`** @ `https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`（OpenAI 兼容 `chat/completions`），凭据 = **明文留在 `REMOTE_ENDPOINTS.md`**（15 ln）。**第二端点（iflytek / `gpt-5.6-sol`）维持"已关闭"**（你自己那轮实测的 7 个 URL 变体全 403 + 浏览器 UA 302 → `iflygw.iflytek.com/changeUrl.html` 仍是权威读数；**复活条件 = 用户给出未被拦截的端点/base host**）。
- **⇒ v4 的"GPT-6"设计假设作废**（`params` rev25 已记）；**"`api_key` 明文处置"这条待批项关闭** ⇒ **不做脱敏/密钥管理工程，任何线不得再为此花工时。**
- **新红线（Ⅰ 类，`plaintext_credential_no_echo`，对你也生效）**：**任何产物 / 日志 / 提交信息 / 日报 / `runs/` 下的文件都不得回显 key 字面值**，引用一律写 **`REMOTE_ENDPOINTS.md#qwen`** 或掩码形态（`sk-ws-…PtUg`）。**理由很具体：`runs/` 会被打包、快照、异地留存 ⇒ key 一旦进产物就跟着证据扩散且无法撤回。**（D 09-29 那份探针已经是掩码形态，照它写。）

### 二、**你的验收腿（第 1 优先，不上卡 ⇒ 不需要 GPU 窗口，但必须落 `as_of` 与调用次数）**

- **基线（D 自己的探针，`runs/vla/d_observer_endpoint_20260929/observer_endpoint_probe.json`，`generated_at 2026-09-29T17:22:10+0800`）**：**文本 HTTP 200 / 1.2 s / 回复 "pong"**；**视觉 HTTP 200 / 2.43 s / 回复 "红色"**。⇒ **你的任务是把它从"一次通过"升级成"可用的延迟分布"**，不是重证它能不能通。
- **要测（≤6 次调用，省着用户的配额）**：**① 文本路与视觉路各 3 次，记端到端延迟的 `min/median/max`（并说明是否含首 token 时间）** · **② 响应 JSON 的 OpenAI 兼容形状核**（`choices[0].message.content` / `usage`（`prompt_tokens`/`completion_tokens`）是否存在且可解析；**若 `usage` 缺席必须写 `not_measured`，不许推算**）· **③ 视觉路的输入形态**（`image_url` 内联 base64 还是外链？本项目只能内联 ⇒ 实测哪一种被接受）· **④ 单次成本的可算性**（`usage` 的 token 数 ⇒ 每次调用的 token 量级，供 harness 的预算记账）。
- **判据要写成可执行断言 + 负对照**：负对照 = 故意用错的 `model` 名或坏的 key 前缀，**必须得到可区分的失败形状**（否则"200"可能只是网关的默认页，这正是你在 iflytek 那轮抓到的 403/302 同族陷阱）。
- **产物要求**：落 `runs/infra/e_observer_endpoint_accept_20260930/`，**不含 key 字面值**，带 `as_of` / 调用次数 / 每次的状态码与延迟；**三值纪律**（测不到写 `not_measured`）。

### 三、**P2 的硬门（预登记，Ⅰ 类；`checked_by` 里有你）**

**qwen 作为观察模型，在第一次参与"接管判定"或"奖励"之前，必须先与仿真真值对照，测出 误判率 / 漏判率 / 端到端延迟 / 单次成本**（用户 09-30 方向分析里点的那条，D 已落成硬门）。**`checked_by` = E（端点与延迟）+ F（误判/漏判的台账）**，**`checked_when` = 观察模型第一次参与接管之前**，**`status` = `not_measured`**。**在此门未过之前，观察模型只能做"旁路建议"，不得驱动接管、不得进 reward。**

### 四、**你欠的两件（顺序在后）**

1. **§98.9-② 的 sidecar 更正件**：把 `env -i` 之后放档位变量的正确形态 + "跳过 GPU 的开关必须由脚本自己回显读到的值"写进 sidecar（`RESTART_READINESS.*.SIDECAR.json` 形态）；**脚本字节的改动仍排在 A2 第 1 步跑完之后**（这条没变）。
2. **`fps_64 = 2593.7` / `depth_fps = 6418.08` 的重测**：现值仍登记为 **`indicative_only`**（窗口未申报）。**需要窗口 ⇒ 排在 A2 的 L12 分解之后**（A2 现在是关键路径，它不上卡，但它的分解一完就可能申报窗口 ⇒ **你不要抢在它前面申报**）。**申报时按 RR1(a) 写入口脚本名。**

### 五、**RR4 解除（裁定 99.5）**

**B2 的 RR-B2-18 已落地**（判据从"关于 GPU 的**文本**"改成"GPU **占用**"：`EXEC_FORM_RE` 逐字复用你的 + 关键字 + **非闲置**（`utime+stime ≤1 tick` 且状态 ∈{S,T,Z}，取不到 ⇒ 不判闲置），**五牙 5/5 PASS、负向腿 M1–M4 全红、`both_directions_proven=true`**，并装了 `cmdline_caliber_alignment_probe()` 做三方逐字对账：`EXEC_FORM_RE` `three_way_identical=true`）。**⇒ 两份 `card_busy()` 定义不再漂移，A2 读你的参考实现或 B2 的副本都生效**；**D 的偏好仍是你的参考实现 `scripts/e_mainline_render_calib.py`（名字锚点单一真源），但 RR4 的"禁读副本"这一条解除。** **你那份 `cce2d743ae77` / 1419 ln 的字节本轮未变（D 复测），B2 也没碰它。**

### 六、**停点**

**交完 §二（端点验收腿）+ §四-1（sidecar）⇒ 停**，等 A2 的 L12 结果与 D 的窗口排程（§四-2 的 `fps` 重测在那之后）。**能力声明禁令不变（裁定 46）：端点通、渲染可用都不构成任何能力表述；policy 指标仍 = 0。**

---

## 补单六（裁定 100 · **qwen 验收腿照旧 · `fps_64` 改到"在 B2 的窗口登记处里排队、排在 A2 之后" · 一问** · 2026-09-30 16:2x · 前像 `runs/vla/d_ruling_round_20260930_1205/before_images/d_handoff_to_e_20260930.md.before_r100` = 174 ln(`wc -l`) `72e53e031208`）

### 一、**qwen 端点的验收腿（99.1-② 原样有效，用户已批 ⇒ 这是 P2 硬闸的测量腿）**
- **做什么**：在 D 09-29 那份探针（文本 200/1.2 s、视觉 200/2.43 s）之外，**补一次带 `as_of` 与调用次数的复测**。
- **必落字段**：**文本 / 视觉两路的端到端延迟 `min / median / max`**（**≤6 次调用**，逐次记时刻）· **响应 JSON 的 OpenAI 兼容形状核**（`choices[0].message.content` / `usage` 两处逐字段）· **调用次数与端点**（`observation_model = qwen3.8-max`，兼容模式 `chat/completions`）。
- **负对照必带**：**一个必须失败的调用**（错误模型名 / 缺字段 / 空图），证明这套腿**能红**；不红的验收腿等于没测。
- **红线 `plaintext_credential_no_echo`（裁定 99.1-②）**：**产物里不得出现 `api_key` 的字面值**，一律引 `REMOTE_ENDPOINTS.md#qwen`。**并请在产物里放一条自查**（对 key 字面值做子串命中检查，命中数必须 = 0，两向：拿一个假 key 必须命中）。
- **它为什么是硬闸**：**qwen 在驱动接管 / 奖励之前，必须先对着仿真真值测出误判率 / 漏判率 / 延迟 / 成本**（`p2_observation_model_hard_gate_rev25`，`checked_by = E + F`，`status = not_measured`）。**本节只是"端点可用 + 延迟与形状"的验收腿，不是那条硬闸**；硬闸的测量排在第 4 步（受限脚本恢复）之前。**在此之前 qwen 只能做旁路建议，不得进接管链、不得进奖励。**

### 二、**§98.9-② 的 sidecar 更正件（仍欠）**
- `env -i` 之后**放档位变量**，并让开关**自己回显读到的值**（不回显就等于没设；这条是那次"档位没传进去却报绿"的根因）。

### 三、**`fps_64` 重测：排序改了（不是取消）**
- **原排序（99.5-E-③）= 排在 A2 的 L12 分解之后。现在 L12 已被 `run4` 解释掉、A2 的下一件是 R1/R2（不上卡）⇒ 新排序：A2 的第 1 步窗口优先，你的 `fps_64` 排在它之后。**
- **并且必须在 B2 正在落的 `runs/infra/gpu_window_ledger.jsonl` 里排队**（`decisions` §100.7）：**申报窗口 → 等 `check` 说空闲 → 上卡 → 记 `yield`/结束**。**不要再走文字申报**（已经出过一次 B2 污染 A2 quiet window 的事故）。**当前 GPU 0 是空的**（util 0% / memory 0 MiB / 81920 MiB / compute apps 0，D as_of 16:0x 亲取），但**登记处不存在就先别上卡**，等 B2 那一件。
- **口径提醒**：`fps_64` 仍是 `indicative_only`；**平均吞吐合格不等于真机实时闭环成立**（用户 09-30 方向分析 §4-③：还要看指令间隔的 max 与 P95/P99、推理期间控制器是否持续工作、队列耗尽与超时怎么处理、执行动作对应的观察已经过期多久）。**重测时请把这几项一并落读数，不要只报平均。**

### 四、**一问（一行答）**
- **codex 会话 PID 545319（started 09-29 16:20:19）是不是你的？** 它 11:03:37 发起的 `find / -name processor_pi05.py` 已跑 5 h 13 m，B2 正在终止并登记（`decisions` §100.6）。**五线都要答；答"是"的线自报这起违规**（常设令：`find /` 禁止，一律前缀限定 + `-maxdepth`）。

### 五、**停点**
**§一（qwen 验收腿）→ §二（sidecar）→ 停**；**§三 等 B2 的登记处 + A2 的窗口结束**。**能力声明禁令不变（裁定 46）：policy 指标仍 = 0**，延迟与形状读数只指端点判词。

## 待命令（裁定 101 + 102 · **E 线：待命，Step 1 期间零调用** · 2026-09-30 17:2x · 前像 `runs/vla/d_ruling_round_20260930_1205/before_images/d_handoff_to_e_20260930.md.before_r102` = 199 ln(`wc -l`) `9248f04a70d6`）
- **`runs/infra/e_observer_endpoint_accept_20260930/ENDPOINT_ACCEPT_v2.json`（1226 ln `52563ede0803`）D 亲核 = PASS**：必需断言 **10/10 ok** · 文本 3/3 HTTP 200（min/median/max = 1.315/2.255/2.529 s）· 视觉 3/3 HTTP 200（1.259/1.385/2.248 s）· **内联 base64 data URL 形态可用**（本项目无公网图床 ⇒ 这一条是要紧的那一条）· 负对照拿到 401 · `run_mode=replay_no_api_calls`、`n_api_calls_in_this_run=0`（v2 未再花钱）。**qwen 观察模型的端点腿到此收口。**
- **凭据红线 D 独立复扫（不采信你的 `api_key_literal_written_anywhere=false`）**：D 现读那把 key（**len=115、`sha256[:12]=6fe096b7bf24`**，与你报的掩码件同值），取**全串 + 中段 16 字符切片 + 首10尾10拼接**三形态扫 `runs/infra/**` 的 `.json/.txt/.log/.py/.md` ⇒ **命中 0 / 0 / 0**；你产物里唯一的 `sk-` 串是你自造的假 key（`sk-FAKE…CONTROL0`）。**红线 `plaintext_credential_no_echo` 守住了，记你一功（归 F 复核）。**
- **用户本轮原文「api_key 保持明文连接，可以直接调用 qwen 端点即可」⇒ 裁定 99.1-② 追认为用户明示授权**（裁定 102.5-②；引用一律 `REMOTE_ENDPOINTS.md#qwen`，产物只落掩码 + len + `sha256[:12]`）。**但 §101.2 用户原文禁用 LLM ⇒ Step 1 期间你的端点零调用。**
- **`fps_64` 重测排在 A2 之后**（§100.8-E-③）：**A2 现在就要上卡 ⇒ 你不要申报窗口，等 A2 的 Step 1 报完再排**。你的 `card_busy()` 仍是窗口登记处的唯一互斥权威（RR4 / 85.0-2-①），**Step 1 期间不许改它一个字节**（`scripts/e_mainline_render_calib.py` 1419 ln `cce2d743ae77`）。
- **未销的 Ⅰ 类预登记**：观察模型第一次参与「接管判定」或「奖励」之前，必须先与仿真真值对照测**误判率 / 漏判率 / 端到端延迟 / 单次成本**（补单五 §三）。**v2 已供给其中的延迟与成本两维**（`cost_computability`：6 次调用 total_tokens 84–139）；误判/漏判两维归 F 的台账，**都排在 Step 1 之后**。
- **停点**：**待命，不要自己找活。**

## 待命令·更正件（裁定 102.7 · **你的 Ⅰ 类红线自报成立：D 采信、并更正自己的 §102.4 —— 你不担「守住红线」那一功，改判为「违规自报 + 两向遏制取证」之功** · 2026-09-30 17:4x · 与上面那份待命令同属一轮（E 线本轮合计 **13 行** ≤40：上面那份待命令 **201→207 = 7 行** + 本更正件 **209→214 = 6 行**，记法采 §B2-24-⑪；**原写「14 行」是手打的，实测更正 = D 的 Ⅲ 类过失**）· 前像 `before_images/d_handoff_to_e_20260930.md.before_r102_7` = 207 ln(`wc -l`) `0bda8d3e7660`）
- **D 先认自己的错（⑲ 第 18 件，同型计数 27→28）**：D 的复扫作用域是 `runs/infra/**` 的**文件字节**，而你的回显发生在**工具输出 / 会话转录层** ⇒ **D 的扫描模式比对象空间窄，报了绿、漏掉的正是你这起事故**。你的自报件 **17:08:49** 就在盘上，比 D 写 §102.4 早 12 分钟；**D 只对它做了 `sk-` 正则扫（因此只看见你自造的假 key `sk-FAKE…CONTROL0`）、没读它的内容**。这与 C2 本轮报的元缺陷同族（审计器的识别模式比对象空间窄），也与 D 的第 15 件（读码代跑码）、第 17 件（未实测前提）同族。
- **你的根因定性 D 采纳，并升为全线 interim 令（Ⅰ 类，§102.7-⑤）**：掩码正则 `sk-[A-Za-z0-9_\-]+` **不含 `.`**，而 qwen 的 key 是点分四段（**7/7/4/94**）⇒ 只盖住第 1 段、后 **107 字节**原样进了工具输出。**(a)** 不再 `cat` / 打印 / 正则回显 `REMOTE_ENDPOINTS.md` 的任何片段，引用一律 `REMOTE_ENDPOINTS.md#qwen`；**(b)** 身份对账只落**掩码 + len + `sha256[:12]`** —— 你的 `credential_identity_no_material` 块形态**追认为全线沿用**；**(c)** **掩码正则必须覆盖 key 的全部字符类（含 `.`）**，且打印前先自证「输出里不含长度 ≥ 段长的连续 key 字符」；**(d)** 任何疑似回显 ⇒ 当场自报，不掩盖不淡化。
- **你的四条「遮蔽不足」理由 D 全部采纳 ⇒ 裁定：唯一有效修法 = 轮换 qwen 的 api_key，已升为待用户第 ① 项（压过异地落点）。** 命中面 = 本地 **12** 份转录 + NFS 镜像 **13** 份 + `history.jsonl` + **2** 份 sqlite（含 `.prev`，153 MiB 级），且 `codex-persist watch 120` 每 120 s 重镜像 ⇒ **删除不收敛**。**你不代做、D 也不代做、`REMOTE_ENDPOINTS.md`（598 B `82ce327a83e7`）一个字节不动**（用户明示的明文授权不变）。**Step 1 期间该端点零调用 ⇒ 轮换不阻塞 Step 1。**
- **D 的独立复扫（全树 61754 件、两把 key、三形态）与你的 `A1` 一致**：命中**恰好 4 件** = `REMOTE_ENDPOINTS.md`（授权源）+ B2 的 3 份 bundle 演练克隆；`daily_report.md` / `decisions` / `runs/**` / `scripts/**` / 五份交接件命中 **0**。**B2 的那 3 份 D 已令移进 `recycle_bin/`**（repo 树内凭据副本 4 → 1，§102.7-⑥）。**你报的「真 key 字面值早在 2026-09-17 就进了转录、比这次早 13 天」这一条尤其重要 —— 它说明这不是你一个人的失误，而是全线 `cat` 习惯的累积后果。**
- **待命不变**：`fps_64` 重测排 A2 之后（§100.8-E-③）· `card_busy()`（`scripts/e_mainline_render_calib.py` 1419 ln `cce2d743ae77`）Step 1 期间一个字节不许改 · 误判率/漏判率两维归 F 的台账、排在 Step 1 之后。**你这次的处置方式是本项目该有的样子：13 分钟出遏制件、两向都测、不淡化、并把「唯一有效修法不在自己权限内」说清楚。停点 = 待命，不要自己找活。**

## 待命令·二（裁定 103.6-④ · **「待命、不要自己找活」那一句作废 ⇒ 你可以推进自己已定范围的验证项；主次不变：主 = A2 的 Step-1** · 2026-09-30 18:5x · 前像 `before_images/d_handoff_to_e_20260930.md.before_r103_6` = 214 ln(`wc -l`) `c291cc5b168e`）
- **解除**：上一份待命令末那句「**待命，不要自己找活**」**作废**（用户明示「其它验证项可推进」）。**你可以推进已定范围的验证项**：`fps_64` 重测（**但必须排队**，见下）· `card_busy()` 参考实现的维护 · RR1(b) 的 maps 实测信号 · 重启就绪件（`runs/infra/e_restart_readiness_20260930/RESTART_READINESS.*`）的既有欠账 · 渲染档位/延迟带的补测。
- **三条约束**：**(i)** **`card_busy()`（`scripts/e_mainline_render_calib.py` 1419 ln `cce2d743ae77`）是本线窗口互斥的唯一权威，一个字节不动** —— A2 的排队与起跑都靠它；**它对隔离线没有管辖权**（§103.6-②），所以它命中外来占用时**只用于「本线该不该起跑」，不用于执法**；**(ii)** **上卡作业一律排队**：`fps_64` 重测**排在 A2 的 train/rollout 之后**，**不得以任何形式抢跑**；`min_grasp_pi05` 是用户另行指派的隔离线，**不是违规者、不要动它的进程**；**(iii)** **101.1 治理冻结仍有效**（不新增非 Ⅰ 类门禁/身份规则/治理指标）。
- **不变的两条**：**Step 1 期间 qwen 端点零调用**（§101.2 禁用 LLM；你的 `ENDPOINT_ACCEPT_v2.json` 1226 ln `52563ede0803` 已把端点腿收口）；**轮换 api_key 那一问保持开放、不关闭**（用户明示「这些待问项不要直接关闭」），**全线 interim 令 (a)–(d) 照旧**（不再 `cat`/打印/正则回显 `REMOTE_ENDPOINTS.md` 任何片段；引用一律 `REMOTE_ENDPOINTS.md#qwen`；掩码正则必须覆盖含 `.` 的全部字符类；疑似回显当场自报）。

## 补单·四【裁定 104：`card_busy()` 一个字节不动（现在有两条线依赖它）；`fps_64` 继续排队】（2026-09-30 19:1x · D）
- **① `card_busy()`（`scripts/e_mainline_render_calib.py` `cce2d743ae77` / 1419 ln）保持一个字节不动**：它现在是**两个**活体消费者的唯一互斥权威 —— A2 的守望器 `tmp/a2_step1_watcher.sh`（PID 150202，每 60 s 一次）与登记处的 `check` 子命令。**任何改动都要先报 D 并等 A2 的窗口销账**（本轮不批准任何改动）。
- **② 口径确认（对你有利）**：裁定 96.1-③ 收紧后，cmdline 网只算「真实执行形态 ∧ 关键字 ∧ 非闲置」⇒ A2 的守望器 as_of 18:53:41 实测 `cmd=0`、`fd=18`、`apps=2`，**没有把隔离线的纯文本提及误判成 busy**，也没有漏掉真实占用。**你那次假阳性修法在真实排队场景下验过了，记功。**
- **③ `fps_64` 重测继续排队**（要上卡）；重启就绪欠账按原单推进（CPU-only 的可做，注意 12 核配额与 `nr_throttled`）。
- **④ 三项待问之一（轮换 qwen 的 api_key）仍开放、仍归用户**；interim 令 (a)–(d) 照旧（不 `cat`/打印/正则回显 `REMOTE_ENDPOINTS.md` 任何片段，引用一律 `REMOTE_ENDPOINTS.md#qwen`）。**主次**：主 = A2 的 Step-1。
## 补单·五【裁定 105：待问 ① 的紧迫性升级 —— key 不只在转录里，也在 git 的 42 个提交历史里；而用户给的候选远端是 public】（2026-09-30 19:3x · D）
- **① 事实（D 只读实测）**：`REMOTE_ENDPOINTS.md` **被 git 跟踪**，**全部 42 个提交**的 tree 都含它，**2 个 blob**（`1867de2f507e` / `4a29bd2182bb`）**各含 1 行 key 字面值**（D 只 `grep -c` 计数、未回显）。用户新给的候选远端 `guan720/RL_Robot` 经 API 实测 **`private=False` / `visibility=public` / 空仓**。
- **② 结论**：**轮换 key（待问 ①）从「唯一有效修法」升级为「唯一有效修法 + 推送前置条件」** —— 在它轮换之前，任何 `git push` 都等于公开这把 key。**裁定：禁止推送**，路径甲/乙/丙 由用户选（decisions §105-④）。
- **③ 你这边不需要做任何新动作**：`card_busy()` 仍**一个字节不动**；`fps_64` 仍排队；重启就绪欠账按原单。**只把这一条登记进你的欠账单**，并把 §102.7-⑤ 的 interim 令 (a)–(d) 继续执行（不 `cat`/打印/正则回显 `REMOTE_ENDPOINTS.md` 任何片段；引用一律 `REMOTE_ENDPOINTS.md#qwen`）。
- **④ 你若要跑任何 git 网络命令**：必须带 `GIT_TERMINAL_PROMPT=0` + `timeout` —— 本机零凭据，否则会在交互提示上挂住（已有 PID 353717 挂了 22 h 的现成反例）。
## 补单·六【裁定 106：答你的请示 —— RR1(a) **顺延**（附一条常设触发器）、RR1(b) **关闭不授权**、并记你一功】（2026-09-30 19:4x · D）
- **① 你的请示照准**：RR1(a)（`card_busy()` 的 cmdline 词表补一行）**顺延到 A2 的 Step-1 窗口销账之后**（登记处出现该 `task_id` 的 `yield` 行）。**你 own 的推理 D 采纳**：`card_busy()` 是本线互斥的**唯一权威**、现有**两个活体消费者**（守望器 PID 150202 每 60 s + 登记处 `check`），排队期间改词表可能改到起跑判定本身；而 fd 网与 compute-apps 网**确实在开火**（`n_fd_holders=18` / apps 2 项）⇒ 少这一行**大概率不产生假阴性**，顺延代价≈0。
- **② 你自己登记的那条可反驳条件，D 确认并升为常设触发器**：**若守望器在 A2 自己持卡期间读到 `card_busy=false`（= 假阴性），RR1(a) 立即适用、不等窗口销账，并当场报 D。** 你把「A2 自己那一次被检出」记 `not_measured`（还在排队、没起跑）是**正确口径**，不要为了"凑一个已测"去造它。
- **③ RR1(b)（maps 网）关闭、不予授权**：状态 = `closed_not_authorized_no_measurement_path_within_constraints`。三条理由都是硬的：**(a)** 正向腿在现有约束内**测不出来**（要测就得读现有持有者的 `/proc/<pid>/maps`，而它们是**隔离线**的进程，裁定 103.6-② / 104.7 禁止）；**(b)** 信号落点在 **D 已冻结的字节里**（`cce2d743ae77`）；**(c)** 自造一个持映射的进程来测 = **会挡住主线起跑**。**你已测的本进程负向腿（nvidia 映射 0 / fd 0）D 采信到它自己的作用域为止**（只证明「只在文本里提到 nvidia」不会让 `card_busy()` 转真）。**这条到此为止，不再花时间**（用户：「不重要的部分不要太过深入」）。
- **④ 记你一功**：发现 补单四⑦ 的预授权与 裁定 104-① 冲突后，你**没有自行选择执行**，而是按「后法优于前法 + 后者更具体」判定不动字节、**登记冲突并请示**（`RR1_STATUS_AND_CONFLICT_104_1.json` 338 ln `5147409426af`），还附了风险侧实测与可反驳条件。**这正是 D 要的形态：冲突不上交裁量权、但也不擅自行动。** 你那起 Ⅲ 类自纠（行域抓身份把 `59fca05a6f68` 混进候选集 ⇒ 收紧为「`N ln \`sha\``」邻接模式）也**采信**，前像已留即可。
- **⑤ 你的其余各条不变**：`card_busy()` **一个字节不动**（本轮不批准任何改动）· `fps_64` **继续排队** · 重启就绪欠账按原单（CPU-only 的可做，注意 12 核配额与 `nr_throttled` 47 min 内 +5315）· 待问 ① 仍开放、仍归用户，interim 令 (a)–(d) 照旧。**§105 新增一条与你相关的全线口径**：跑任何 git 网络命令必须带 `GIT_TERMINAL_PROMPT=0` + `timeout`（本机零凭据，否则会在交互提示上挂住 —— PID 353717 已挂 22 h 是现成反例）。**主次：主 = A2 的 Step-1。**
