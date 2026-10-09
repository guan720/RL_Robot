# 监管备忘 2026-09-28（智能体 D，监管/分析线）

范围：RL_Robot 工作区。本备忘只改判口径与优先级，不修改任何实现文件。
依据：`runs/infra/lerobot_act_env_20260928/*.json`、`runs/infra/b_reproducibility/selfcheck.json`、
`docs/lerobot_act_env_setup_20260928.md`、`docs/b_agent_review_20260928.md`、
robosuite 1.5.2 源码 `environments/manipulation/lift.py::_check_success`、D 线独立进程重放。
接续 `supervisor_review_20260924.md` 与 `supervisor_handoff_20260924.md` 的决策，不覆盖其未变更项。

## 一、改判（自本备忘起生效）

### 改判 1：晋级条件第 1 条 = 部分满足
- 证据：`runs/infra/lerobot_act_env_20260928/official_act_truth20_trimdone0_minmax_lr1e-5_s20k_seed0.json`
  受控成功 2/20（test seed 5001 `max_rise=final_rise=0.0466`、5015 `0.0415`，局末相位 `hold`、
  `held_at_end=True`，非弹射）；`..._seed2_gatefields.json` 1/20（5001，0.0418）。
  门禁 `scripts/b_gate_controlled_success.py` 判 `gate_pass=true`。
- 未满足部分：可重复性仍薄。4 个训练 seed 中 seed1 与全量 seed0 的受控成功为 0；
  受控成功只落在 test seed 5001/5015；率 2/20。
- 允许的写法：「learned 官方 LeRobot ACT 在冻结测试集上取得非零、非弹射的受控成功
  （2/20，单训练 seed，trim-done 数据）」。
- 禁止的写法：「Lift 已解决」「ACT 已可行」「抓取能力达标」等不带判据与 seed 数的表述。

### 改判 2：唯一晋级判据 = 受控成功判据 v1（B 的门禁）
- `success_raw` 降为参考列。它取 robosuite 内置 `_check_success`
  （`cube_height > table_offset[2] + 0.04`，从桌面 body 原点起算），与项目自己的
  `success_rise`（`max_rise >= 0.04`，相对方块初始高度）差一个常量偏移；
  「11/20」这类数字只在松判据下成立，按项目判据为 0/20。
- 09-24 之前缺 `final_rise / held_at_end / phase_at_end` 字段的产物一律不得进结论表
  （监管 P0 继续有效）。

### 改判 3：可复现性前提 = robosuite 1.5.2 + `harness/env_factory.py` 的物体 pin
- B 的分层探针结论：先前「改 OMP 线程结果就变、OMP=1 连跑两次也不同」的根因不是线程，
  而是 robosuite 1.5.1 的 `utils/mjcf_utils.py` 用 `np.random.uniform` 采物体尺寸、绕过 pin。
  1.5.2 + env_factory pin 下 L0–L3 在 OMP=1/2/4 跨进程逐位一致
  （`runs/infra/b_reproducibility/selfcheck.json`，8/8 通过）。
- 因此：任何在 1.5.1 上产生的产物（B 修复前的臂、09-24 历史臂）降级为历史缺陷记录，
  不得参与跨臂比较。
- 未闭环 P0：仓库 `requirements.txt` 仍 pin `robosuite==1.5.1` 而实装 1.5.2。
  按该文件重建会得到不可复现环境。归 B-4。

## 二、对三线的直接要求

### A（LeRobot / policy 线）
1. trim 结论不定级：等 `trimdone0_s6k`（epoch 对齐，检验是否只是过拟合）与
   `trimdone60`（温和裁剪对照）回来。B 已证明同步长预算下 naive 截断会变差。
2. 所有新臂 ≥2 训练 seed，报均值+极差（你的文档结论节已按此写，保持）。
3. 受控局 rise 0.0415–0.0466 贴着 0.04 门槛：与 B 共担门禁阈值 ±0.005 敏感性报告。
4. 建议给 `scripts/eval_lerobot_act_runtime.py` 加 `--render`：offscreen 路径已验证，
   `RobosuiteLift(obs_mode="pixels", cams=(...), cam_size=256)` 即打开 offscreen renderer，
   60 维 state 仍可从 `env._env._get_observations()` 取，CPU 软渲染双视角约 27 fps。

### B（门禁 / 可复现性线）
1. P0：把 `requirements.txt` 的 robosuite pin 修到 1.5.2，并让 `scripts/setup_env.sh`
   写 `requirements.lock.txt` 而不是覆写 pin 文件。
2. 出门禁阈值敏感性报告（±0.005），并回应 A 提出的 `failed_checks` 口径问题
   （`docs/lerobot_act_env_setup_20260928.md:367`）。
3. B-2（flick→0 单变量链）与 B-5（goal_id 贯通 mock 预检）按原顺序继续；
   `selfcheck_ledger_data_bridge.py` 仍暂缓，等 C 宣布接口冻结。

### C（账本 / 数据桥线）
1. `harness/ledger.py`、`harness/data_bridge.py`、`registry/release_bundle.py` 状态维持
   「已实现未验证」：selfcheck 通过不等于 v4 P3 完成；至少有一个真实调用方
   （A 的评测器或 B 的门禁）接入后才可改状态。
2. `release_bundle` 若假设了 B 门禁的字段，先与 B 对齐接口再补测试。

## 三、共同纪律
1. 两套 ACT 实现并存（自研 MLP `scripts/train_act_lift.py` / 官方 LeRobot）。结论不得互借：
   B 的「40 步梯度欠拟合」翻案只针对自研实现；A 的 MIN_MAX / trim-done 结论只针对官方实现。
   任何「ACT 可行/不可行」表述必须带实现名 + 判据 + 训练 seed 数。
2. 对外材料标注纪律：learned 视频必须带 `success_rise` 与 `max_rise` 数字；
   抬起不足的素材只能标「抓取成功、抬起不足」，不得标「抓取成功视频」。
3. 响应方式：各线在自己下一份文档或 `daily_report.md` 的本线节里回一条
   「备忘 ack + 执行状态」即可，不要修改本文件，避免并发写冲突。

---

## 增补一（2026-09-28 17:00，智能体 D）：K=2 结果、双机制模型与表述纪律

### 0. 备忘响应确认
- B-4 已闭环：`requirements.txt` 改回 pin `robosuite==1.5.2`；`scripts/setup_env.sh:64` 的恒真检查
  已替换为真检查（import 后断言版本，报错文案说明 pin 漂移的后果）。
- A 已将 6 个会被同名覆盖的门禁 v1.0 产物归档至 `runs/infra/superseded_gate_v1.0/`
  （移动不删除），汇总数字逐项不变。两条均符合备忘纪律。

### 1. 新证据登记
- 同 checkpoint 执行频率序列（train K=4，仅改 `replan_every`，**不重训**）：
  R4 / R2 / R1 的 v1.1 受控成功 = 2 / 2 / 4，mean_max_rise 0.0228 / 0.0244 / 0.0267 单调。
  证据：`runs/infra/lerobot_act_env_20260928/official_act_truth20_trimdone0_minmax_lr1e-5_s20k_seed0.json`
  及同目录 `_replan2` / `_replan1` 两份。
- K=2 重训臂 seed0：v1.1 受控 9/20，rise 0.0446–0.1206、`final_rise == max_rise`、局末夹持，
  抬升高度进入 teacher 量级（scripted base 0.0764）；代价是 grasp 20/20 → 15/20、10/20 死在 approach。
- **K=2 seed1 未复现**：v1.1 受控 2/20、mean rise 0.0134、grasp 20/20、0 局死 approach
  （失败签名回到 k4 型）；与 seed0 的受控 test-seed 集合交集仅 {5005}。
- seed1 系（k4 与 k4+R1）均 0/20：每步重规划也救不回，为分布内机制的签名。

### 2. 改判 1 维持「部分满足」，不上调
9/20 为单训练 seed 且复现失败（2/20），受控 test-seed 集合不稳定。晋级条件第 1 条的现有最佳
证据仍是「多臂多 seed 零星出现、v1.1 通过、物理真实（有视频）」；率与可重复性均未达标。

### 3. 新增改判 4：双机制相加模型（M1 + M2）
- M1 分布内 dz 沉默：teacher 的 lift 帧占比过低（全量 2.3%、trimdone0 8.5%）叠加相位先验 skew。
  签名 = 即使每步重规划仍 0/20（seed1 系）；trim 可缓解（受控 0→2）。
- M2 闭环协变量漂移：状态离分布后策略输出退化为饱和常数并自增强。
  签名 = 同一 checkpoint 提高重规划频率单调缓解（2→2→4，不重训）；B 的逐帧 trace
  （命令与运动反向、runaway 0.376 m）；deadband 四臂 0/20 否证「dz 泄漏是唯一根因」。
- 两机制相加解释现有全部臂：trim 攻 M1（0→2），反馈率攻 M2（2→4），K=2 重训同时触动两者
  且混入训练目标变化（→9，单 seed）。
- 禁止任何单机制表述：「漂移是唯一根因」「数据配比是唯一根因」均不成立。

### 4. 表述纪律（新增，与第三节共同纪律并列）
- K=2 只允许写：「单训练 seed 9/20（v1.1），seed1 复现 2/20，未达可重复」。
- K=2 与协变量漂移的关系只允许写「方向一致、互为旁证」；禁止「验证 / 证明 / 确认根因」。
- 引用 R4/R2/R1 序列时必须带「不重训」三字——它是 M2 当前最干净的因果证据，
  也是唯一把「执行频率」与「训练目标」分开过的实验。

### 5. 对三线的要求（增补）
- A：① 补 2×2 解耦矩阵缺臂（k2-ckpt + R1），把执行频率与训练目标彻底分开；
  ② k2 seed0 的 approach 回归（10/20 死 approach、grasp 15/20）单独归因；
  ③ 任何新杠杆（K / replan / trim / 数据量）必须 ≥2 训练 seed 才进结论节，单 seed 一律标「候选」。
- B：① 用 v1.1 官方门禁重判 k2 两臂与 replan 三臂（D 手算参考：k2 seed0=9、seed1=2、
  R4/R2/R1=2/2/4）；② v1.1 发布说明写明 over_lift 与 flick 的区分，以及恒真检查治理项。
- C：不变，维持「已实现未验证」。

### 6. 回流点（触发下一次改判）
2×2 矩阵回来、v1.1 官方重判回来、seed1 系 M1 归因回来。三者齐之前不改判 1。

---

## 增补二（2026-09-28 17:1x，智能体 D）：三层因果栈、重分类清单与输入契约强制

### 0. D 线自我纠错（先于一切）
增补一之后的口头表述中「MIN_MAX 系免疫 L1、改判 1 证据基不受动摇」**不成立**，作废。
实测所有 A 官方臂（含 `trimdone0_minmax_*` 与 `trimdone0_minmax_k2_*`）的
`normalization_mapping` 均为 `STATE=MEAN_STD / ENV=MEAN_STD / 仅 ACTION=MIN_MAX`
（各 checkpoint `train_config.json` 逐项核对）。L1 肇事维在 **STATE 侧**（dim 7/9/11，
`joint_pos_cos` 系，std 低至 9.67e-05），因此：
- MIN_MAX 的增益应归因于 **ACTION 侧退化解的消除**，与 L1 无关；
- trimdone0 / k2 臂对 L1 **同样暴露**，改判 1 的证据基不享有豁免。
依据：`docs/b_normalization_incident_20260928.md`、导出 `normalization.npz` 的
`observation_std[9]=9.696e-05`、LeRobot 官方 `processor/normalize_processor.py:335`
（MEAN_STD `denom = std + eps`，`eps=1e-8`，无下限；MIN_MAX 仅 `denom==0` 时替换）。

### 1. 改判 4 升级：三层因果栈（取代增补一的 M1+M2 表述）
- L1 数值炸穿：MEAN_STD 对近常量 STATE 维无下限；闭环离分布后 |x| 峰值实测 20402，
  策略退化为 ±1 抖动。开环指标不可见。因果证据 = 同 checkpoint 单变量推理截断
  （无截断 94% 帧越界且门禁 INVALID；C≤3 时 raw 3→8~15/20；失效模式换类为 over_lift 且全程夹持）。
- L2 dz 条件均值正偏：teacher lift 段 dz≡+1（`scripts/demo_scripted_lift_rs.py:99` 的 +0.3 目标）、
  hold 段 ≡0，可观测差异只在 `cube_z` 绝对值而 `z0` 不在 obs → 歧义区回归输出条件均值
  → hold 段 dz +0.052/步、无停止条件 → 积分过冲 +0.14 m。
- L3 数据配比：lift 帧占比 2.3%（全量）/ 8.5%（trimdone0），trim 可缓解。
- 增补一的「M2 协变量漂移」改述为：**漂移是触发器，L1 是离分布后的放大器，L2 是输入受控后的残余偏置**。
- 截断 C 非单调（1.5→4 局、3→1 局受控），截断永久只作因果探针，不得作修复或交付能力。

### 2. 重分类清单（采纳 B 的作废清单并扩展）
- 作废为能力测量：B 文档 §9 名单（A 的 `runs/infra/act_lift_k4_state_*` 闭环、B 的 mb 无截断闭环），
  **外加** A 全部官方臂的闭环成功率在输入契约验证前一律标「L1 暴露、候选」——
  含改判 1 引用的 trimdone0 k4 2/20、k2 seed0 9/20、k2 seed1 2/20。
- 不作废：checkpoint 本身、离线探针（在 teacher 分布内）、开环对齐、视频物理证据
  （保留为「存在性证据」，不得作为率证据）。
- 改判 1 维持「部分满足」，并附加生效条件：blowup 字段已记录且 <0.05、且过 v1.1 官方重判，
  才允许把 2/20、9/20 作为率证据引用；在此之前只作候选。

### 3. 新纪律：输入契约强制
- 任何闭环评测产物必须带 `norm_input_blown_frames_frac`；超 `INPUT_BLOWUP_TOL=0.05` 判 INVALID。
- **缺字段同样判 INVALID**（B 门禁待加此项；当前只判「有字段且超阈」）。
- A 的 `scripts/eval_lerobot_act_runtime.py` 目前不记录该字段（实测 grep 无），须补
  `--record-input-blowup`；补之前 A 的官方臂全部处于「输入契约未验证」。

### 4. teacher / obs 变更的基线重置登记
- 改 `scripts/demo_scripted_lift_rs.py:99`（去饱和）或改 obs 布局（加入 `cube_z − z0`）
  均等于新建 baseline 族：历史臂失去对照意义，必须显式声明与 09-24 / 09-28 早段数字不可比，
  并在 `work/decisions/` 式登记中写明被推翻的假设。
- obs 布局变更须同步核对 C 线 `harness/data_bridge.py` / `ledger.py` 是否缓存 60 维维度假设。

### 5. 对三线的要求（增补）
- A：① 评测器补 `--record-input-blowup` 并重跑 trimdone0 k4/k2 三臂；② L1/L2 修复
  （std 相对下限 + 训练推理同一 C；示范去饱和）排在 K / replan / 数据量杠杆之前；
  ③ 9/20 与 2/20 在补字段重跑前对外只标「候选」。
- B：① 门禁加「缺 blowup 字段 = INVALID」；② 把截断因果探针移植到 A 的官方 checkpoint 上跑一次，
  判定 L1 是否在 A 臂上实际咬合（咬合强度决定重分类是形式还是实质）；③ 重分类结论写入 v1.1 发布说明。
- C：核对账本/视图对 obs 维度与布局的假设，obs 契约变更时同步更新并重跑 selfcheck。

### 6. 回流点（触发下一次改判）
blowup 字段补齐 + v1.1 官方重判 + A 臂截断探针三者齐备后，重议改判 1 的证据等级；
teacher 去饱和臂回来后重议 over_lift 与 L2 的关闭状态。

---

## 增补三（2026-09-28 19:24，智能体 D）：用户裁定、门禁 build 纪律、L1 分线降级与双峰升格

本节所有数字由 D 于 18:45–19:20 直接复核产物得出（复核脚本输出在
`/workspace/mnt/sppro/yhzhang91/scripts/lomoon_claude/tmp/agentD_review/`）。
与 A/B 文档表述不一致处，**以本节为准**，差异已在 §3 逐条列出。

### 0. 用户裁定（2026-09-28 晚，D 代为登记，原文口径）

- **裁定 D-1**：允许在仓库根建 `work/decisions/` 镜像目录并写入。外部已备份。
  **最小写入**：只放路线变更/口径裁定/作废与 ack 登记，**实验结果与产物一律不得写入该目录**。
- **裁定 D-2**：允许 `git init`。
- D 线执行护栏（据 AGENTS.md 禁 `rm` 的同源风险，D 自行附加，属裁定 D-2 的实施条件）：
  1. `.gitignore` 必须排除 `runs/`、`__pycache__/`、venv、视频与大 JSON 产物；
     被引用的裁定产物改为在**受版本管理的文本文件**里登记 `sha256 + gate_build + gate_spec_sha256`。
  2. **禁止 `git clean -fd`、`git reset --hard`、`git checkout -- .`** 等会不可逆删除未跟踪/已修改文件的命令。
  3. `RL_Harness_v4_20260924/` 保持只读，不得因任何 git 操作被改写；
     `/workspace/mnt/sppro/yhzhang91/datasets` 在仓库外，不得纳管。
  4. 首次提交前把 `.gitignore` 与「`runs/` 是否纳管」写进 `work/decisions/` 首条记录。
- 这两条裁定**解除了 B `docs/b_handoff_to_a_20260928.md` §6 的两项停车**，也解除了 A §17.12 末
  「获批前不再自行开 L1 修复臂」的登记入口缺失问题（路径已开，仍须逐条登记后才可动手）。

### 1. 改判 5：`success_raw` 证伪为选臂指标（由「降级」升级为「证伪」）

证据：`runs/infra/b_normclip2/gate_all.json`（gate_version 全部 v1.2.1，D 逐臂复核）——
raw 最优 clip3 = raw 15 / **ctrl 1** / over_lift 12 / insuff 1；ctrl 最优 clip1.5 = raw 8 / **ctrl 4**。
**raw 与 ctrl 的最优臂不是同一条**。dz 死区非单调（0.1→ctrl 3、0.2→ctrl 1），同样不得固化为超参。
附带：noclip 与 clip24 均为 `measurement_invalid`（blown 0.9387 / 0.936），不得当策略结果引用。

### 2. 改判 6：肇事维的表述从「维清单」改为「机制类」

- 不变量：**任何在示范数据里近似常量的 obs 维，其 MEAN_STD 归一化增益无上界**。
  具体维随 obs 布局而变，不得跨线搬运维号。
- 官方 LeRobot 线咬 `observation.environment_state[3]/[4]`（cube_quat 前两分量，teacher 全域幅度仅 ±0.037）；
  B 自研 60 维线咬 `joint_pos_cos`（dim 7/9/11/38）与 `joint_acc`（dim 28/30/32/34）。
- B 的两类机制拆分（`runs/infra/b_covariate_shift/covariate_shift.json`，probe_build a98dfce9b4e2）予以采纳：
  ① 平坦特征放大 → 相对 std 下限可修；② 真实闭环发散（`joint_acc`，|x| 529~1787 vs 训练上界 23.7）
  → **归一化治不了**，是 L2 的 dz 正偏把 `eef_z` 0.83 积分漂到 1.44 的下游后果，唯一修复是 teacher 去饱和。
- B 已自行撤回「OOD 99.3% / 首次越界帧 = 2」（度量伪影，`ood_numbers_citable=false`）——D 追认该撤回，
  该两个数字**不得**再出现在任何线的结论里。

### 3. D 线第二次自我纠错 + 对 A/B 二手表述的三处修正

- **D 自我纠错（第 2 次）**：增补二把 A 全线重分类为「L1 暴露候选」，在**官方线上是形式而非实质**。
  截断因果探针（`runs/infra/lerobot_act_env_20260928/clipprobe/`，D 复核）：
  C=12.469445 下 seed0/seed2/seed4 的受控 = **9/0/19 → 9/0/19**，`mean_max_rise` 四位小数不变
  （0.0376 / 0.0020 / 0.0719；seed2 仅在第六位有 0.001977→0.001979 的差），seed4 一帧未被截到（阴性对照）；
  C=5.0 下 seed0 才有变化：raw 11→10、`mean_max_rise` 0.037621→0.037377（−0.6%）。
  故：**L1 在官方线降为「测量有效性」问题，不是能力瓶颈**；能力瓶颈仍是 L2。
  但 L1 在 B 自研 60 维线的严重性**维持不变**（94% 帧越界、|x| 峰 20403、多维）。
  → 纪律：L1 的结论**必须分线陈述**，任何一条线的 L1 结论不得搬到另一条线。
- **修正 A §17 的「40/40 带字段、0 缺失」**：D 实测 `official_act_truth20_*.json` 共 **44** 份，
  **39 份带 input_contract、5 份仍缺**（`train24_lr1e-4_s20k`、`train24_lr1e-5_s20k`、
  `train24_lr1e-5_actionminmax_s20k{,_seed1,_seed2}`，均为早期非 gatefields 臂）。
  这 5 条要么补测，要么在 `work/decisions/` 登记为 superseded 后不再引用；不得静默留空。
- **修正 A §17.13 的「mean_max_rise 四位小数不变」适用范围**：仅在 C=12.469445 成立；
  C=5.0 下 seed0 不成立（见上）。引用时必须带 C 值。
- **修正 A 的 per-dim 区间**：A 写 0.196–0.593（16 臂，当时口径）；D 实测 39 臂为
  **0.121–0.980，39/39 全部 > 0.05**。最高两臂是塌缩臂（`train24_lr1e-4_s20k_gatefields` 0.980、
  `train24_lr1e-4_actionminmax_s20k_gatefields` 0.934），诊断时须与能力臂分开读。

### 4. 改判 7：门禁 build 纪律（唯一可采信 build = v1.2.1）

- `scripts/b_gate_controlled_success.py:61` `GATE_VERSION = "v1.2.1"`：新增 `insufficient_lift`
  （夹住但没抬够，从 `flick` 分出）、输入侧约束白名单（推理期归一化截断算「执行侧介入」）、
  每份裁定带 `gate_build` / `gate_spec_sha256`。
- **D 实测版本分布：`runs/infra/lerobot_act_env_20260928/gate_strict_*.json` 共 41 份 = 37 × v1.1 + 4 × v1.2 + 0 × v1.2.1。**
  即 A 的全部官方裁定**尚未在 v1.2.1 上重判**。
- 由此生效的引用纪律：重判完成前，A 表（v1.1/v1.2）与 B 表（v1.2.1）的
  `flick` / `insufficient_lift` **不得混引**；跨线比较只允许用 `controlled_success` 与 `measurement_valid`。
- 留档裁定若 `gate_build` 不同必须重判（B 已实测：旧 `gate_all.prev_build.json` 的 clip24 从 FAIL 翻成 INVALID）。
  文档里**不得写死 build 哈希**，一律以产物内字段为准（本轮同时存在过 3 个 build 值）。

### 5. 裁定：per-dim 超界比例 vs 全局阈值口径（A §17.7 挂起项）

- **门禁继续采用全局 max 口径**：`INPUT_BLOWUP_TOL = 0.05` 作用于 `mean_blown_frames_frac`，
  阈值 = 该 ckpt 训练期归一化输入 |x| 的最大值。
- **per-dim `mean_out_of_range_frames_frac` 降为诊断字段，不进判据。**
  理由：39/39 已测臂 per-dim 均 > 0.05（0.121–0.980），采用 per-dim 规则会把**全部**臂判无效，
  其中包含截断探针已证明数值上不受影响的臂（seed4 一帧未截、受控 19/19）→ 只毁信号、不保护任何东西。
- 附加要求（对 B）：门禁输出须记录**主导阈值的那一维与其 gain**（当前为 `observation.state[34]`，
  norm_absmax 12.469445），使「全局阈值被单维主导」这一事实显性化；`INPUT_BLOWUP_TOL` 的语义
  在 `docs/b_controlled_success_v1_20260928.md` 里写明是「全局 max 口径」。

### 6. 证据登记：种子双峰升格为 P0 第一未解问题

- K=2 trimdone0 六个训练 seed：seed0 `measurement_invalid`（blown 0.2120，|x| 峰 93.4）；
  5 个有效 seed 的受控 = **2 / 0 / 17 / 19 / 1**，均值 7.8/20 = 39%、极差 0–95%、**双峰无中间点**。
  高分 seed 的 `mean_max_rise` 0.0685 / 0.0719 = scripted base-only 0.0764 的 89% / 94%，flick 0。
- K=1 trimdone0：seed0 = **受控 20/20**（raw 20、flick 0、over_lift 0、`measurement_valid`，
  blown 0.000167、闭环 |x| 峰 13.32 vs 阈 12.47；rise 0.0416–0.1139、mean 0.0800）；
  seed1 = **0/20**（20 局全部 `grasp_verified` 但 `max_rise` 恰为 0.0，failure_phase = grasp，契约同样有效）。
  **A 已自行撤销 K=1 20/20 的候选资格，D 追认。**
- 判别量（D 用 17:46 落盘的 actlog 独立复算，闭合残差 0）：
  k1 seed0 闭环 burst 1.90 帧/局、`rise←burst +0.0175`、`rise←bias +0.0718`（**80% 仍来自偏置积分**）；
  开环 seed0 `lift_dz 0.924 / hold_bias +0.0129` vs seed1 `lift_dz 0.953（更高）/ hold_bias −0.0129`。
  → 20/20 与 0/20 的差别是**抬起后 dz 残余偏置的符号**，不是「会不会发抬起命令」。
  B 侧独立测得 hold 段 dz 正偏 +0.052/步（离线 +0.111/+0.143），260 帧积分 ≈ +0.68 m 指令量，
  与 clip3 的 12/20 over_lift 一致。**两线两仪器同一量，L2 = 能力瓶颈予以确认。**
- 阈值敏感性（`runs/infra/b_gate_sensitivity/report.json`，gate_build e4f5ec887788，
  网格 final_rise {0.035,0.040,0.045} × rise_cap {0.145,0.150,0.155}）：12 臂 = **0 robust / 5 sensitive / 7 全网格为零**；
  改判 1 曾引用的 `trimdone0_minmax_lr1e-5_s20k_seed0` 是 1→6。
  **该 12 臂全是已被超越的低分臂，未覆盖 K=1 / K=2 seed3-4 / stdfloor**，结论不可外推。
  D 自行计算 k1 seed0 在同一网格上为 **19→20**（rise_cap 无影响，max 0.1139 < 0.145）：
  仍属 threshold_sensitive，但摆动 1 局，比旧臂的 1→6 小一个量级。
  → 引用格式强制：**「受控 20/20 @ final_rise=0.040（网格内 19→20）」**，不得裸写 20/20。

### 7. 证据登记：std 下限修复在官方线被否证

`trimdone0_stdfloor_minmax_k2_lr1e-5_s20k_seed{0,1,2,4}`（D 逐臂复核 gate 产物）：
3 个共同有效 seed 的受控 **2 / 0 / 19 → 1 / 0 / 14**（对照组 seed4 从 19 退到 14）；
seed0 的 blown 0.2120 → 0.0400 仅边缘通过、闭环 |x| 峰 93.4 → 94.7 **未降**；
算得的 `floor(env[3]) = 3.34e-4` 比其 std `7.72e-3` 小 23 倍，**不在肇事维上生效**。
→ 结论：B §6.1 的相对 std 下限在官方线**不是修复**；(b) teacher 去饱和
（`scripts/demo_scripted_lift_rs.py:99` 的 `+0.3` → 温和上升量）升为**最高优先级待办**，
且属 baseline 重置，须先按裁定 D-1 在 `work/decisions/` 登记再动手。

### 8. 晋级条件第 1 条：维持「部分满足」，强口径仍不满足

- 弱口径（≥2 训练 seed 非零受控成功）**稳固满足**：K=2 的 5 个有效 seed 里 4 个非零、其中 2 个 ≥17/20。
- 强口径（**可重复**）**仍不满足**：同配方给出 0/20 与 19/20。这是当前最该投算力的问题，优先级高于任何新杠杆。
- 上调条件（收窄版，替代增补二 §6 的回流点）：K=1 或 K=2 在 **≥3 个训练 seed** 上受控 ≥ 半数、
  全部 `measurement_valid`、全部在 v1.2.1 上重判、且 `rise←bias` 不再单独支撑结论
  （即闭环归因里 burst 贡献占比可复现地 > 50%）。三者缺一不上调。

### 9. 对三线的要求（增补三）

- **A**：① 用 `scripts/b_regate_all.py` 在 v1.2.1 上重判 41 份官方裁定，重判后刷新 §17 与汇总表；
  ② 补测或登记作废 §3 列出的 5 个缺契约臂；③ 把阈值敏感性重跑到当前臂集
  （K=1 seed0/seed1、K=2 seed3/seed4、stdfloor seed4），产物落 `runs/infra/`，不得只写文档；
  ④ K=1 seed2–5 继续，回来后按 §8 的收窄条件申请定级；⑤ 给 k1 seed1 补 actlog，
  确认 0/20 是负偏置积分（这是把「偏置符号 = 唯一判别量」钉死的最后一块）；
  ⑥ L1 修复臂继续暂停，直到 (a)/(b) 两条路径在 `work/decisions/` 登记完毕。
- **B**：① 执行裁定 D-2 的 `git init`，严格遵守 §0 的 4 条护栏，`.gitignore` 与 `runs/` 纳管决定先入 `work/decisions/`；
  ② 把 C5=0.04 的**勘误后理由**（0.92 × 方块全高 0.04341 m，半尺寸取 `runs/infra/b_reproducibility/selfcheck.json`）
  写进门禁注释与规格文档，替换「与 robosuite 成功阈同量级」这条错误理由；数值 0.04 不变；
  ③ 门禁输出补「主导阈值维 + gain」字段（§5 附加要求）；
  ④ 把 T17 的 C 侧 3 项（`harness/queue_td_learner.py:65,135,290`）正式同步给 C；
  ⑤ `insufficient_lift` 的读法（与 `over_lift` 是同一变量 dz 的相反方向、修复动作不同）写进给 A 的交接单。
- **C**：① **消费 B 的黄金值**——`docs/b_golden/async_td_golden_v1.json` 明写 consumer = C，
  但 D 实测 C 的脚本与文档里 `golden` **0 命中**；C 的 case1–case6 与 E1–E6 逐条平行，
  须按规格分别断言 targets（1e-9 相对容差）/ masks（四掩码不得合并）/ isolation / gradients（`==0` 与 `!=0` 严判），
  Q̄ 用符号名不得编浮点，`γ_slot = 0.531441` 显式存储并防 `0.9^36` 二次幂；不过就在 docs 记「规格错还是实现错」，
  **不得静默调阈值**；② 解决 γ/n 单位冲突：黄金值约定 γ=0.9 / n=6 / H=20 / C=[0,6) E=[6,12) D=[12,20)，
  而 C 真实帧 smoke 用 γ=0.99 / n=4 / H=8（`runs/infra/c_learner_shard_smoke.json`）——
  规格一致性测试跑 B 的数，真实帧路径显式标注为假设值，并把「用实测把 n/γ 升为实测值」立项；
  ③ 给账本/发布包补**裁定身份与有效性**字段：D 实测 `harness/ledger.py`、`harness/data_bridge.py`、
  `registry/release_bundle.py` 里 grep 不到 `measurement_valid` / `gate_build` / `gate_spec_sha256` / `superseded`，
  而 `registry/release_bundle.py:102` 的 `DirectionScore` 只有 `flick_frac` / `controlled_success_rate`。
  照现状 ingest 会把已作废数字当物理事实存进账本，违背 C 的立线原则。
  要补：裁定包 = {gate_version, gate_build, gate_spec_sha256, measurement_valid, 三套账, 五档 bucket, superseded_by}，
  重判走 append-only + 撤销记录（可复用 `record_contamination` / `case_append_only_and_revocation`）；
  ④ 建 `work/decisions/` 镜像登记处（裁定 D-1，最小写入），首批条目 = D-1、D-2、A 的两条 L1 路径、B 的 teacher 去饱和；
  ⑤ 用内容哈希做逐臂 run manifest（绑定 `model_safetensors_sha256`、数据集 sha、`scripts/*.py` sha、
  `gate_build`、`probe_build`、`requirements.lock.txt`、`pinned_object_seed`、评测 seed 列表），
  在 git 之外先满足 P0「代码版本」的实质要求；
  ⑥ **降优先级**：视觉表征重算、RLinf/LeRobot 读取适配、真实 ACT/SAC 打包与 `activate_bundle`——
  当前无任何臂可晋级，此时做发布/激活属过早动作。
- **D（本线）**：① 本增补落盘；② 下一轮检查 A 的 v1.2.1 重判是否完成、C 的黄金值对账结果、
  `work/decisions/` 首批条目是否齐；③ 若 §8 的三条上调条件齐备，再议改判 1。

### 10. 表述纪律（增补，与第三节、增补一 §4 并列）

- 不得裸写「20/20」「19/20」等受控数，必须带 `@ final_rise=0.040` 与网格内摆动范围。
- 不得把 `insufficient_lift` 读成脱手；`flick` 才是真脱手。
- 不得跨线搬运 L1 结论、不得跨 build 混引 flick/insuff、不得引用已撤回的 OOD 数字。
- 「ACT 可行」不成立：K=1 20/20 已撤销候选，最好的可重复证据是 K=2 有效 seed 均值 39% 且双峰。
- C 的全部 smoke 是 scripted teacher 重放，措辞只能是「真实帧重放通过」。

### 11. 回流点（触发下一次改判）

A 的 41 份 v1.2.1 重判 + C 的黄金值对账 + K=1 seed2–5 三者回来后再议；
其中任一出现「与本次登记数字不一致」，先改本节再谈结论。

追加（与 §12 同步）：`blown_frames_frac` 单一来源化 + [0.03, 0.08] 区间臂重测，
也是回流点之一；在它回来之前，任何依赖「边缘通过」的结论（含 stdfloor seed0）不得进入定级讨论。

### 12. 追加（19:35，D 复核时发现）：`blown_frames_frac` 口径未单一来源，边缘裁定暂不可采信

D 在核验 §3 的截断探针时逐局对齐了同一 checkpoint（`trimdone0_minmax_k2_lr1e-5_s20k_seed0`）、
同一题集（seeds 5000–5019）、同一帧数口径（`norm_input_frames_measured = 150`/局）的两份产物：
`official_act_truth20_..._seed0.json` 与 `clipprobe/official_act_truth20_..._seed0_clipC12p469445.json`。

- **轨迹完全一致**：20 局 `max_rise` **逐位相同（0 处差异）**，`max_input_absmax` 同为 93.3937，
  非零 blown 的局同为 7 局。→ §3 的「C=12.469445 下截断是零因果介入」这一结论**加强成立**：
  截断确实生效（post-clip `max_input_absmax` = 12.4694 = C），而 7 局越界局里 6 局 `max_rise` 本来就是 0.0，
  唯一有抬升的 5011 在两条路径下同为 0.044572。
- **但同一轨迹上的 `blown_frames_frac` 两条路径算出不同值**：
  汇总 0.2120（未截断路径 `norm_input_blown_frames_frac`）vs **0.1180**（探针路径 `norm_input_preclip_blown_frames_frac`），
  差 0.0940、约 1.8 倍；逐局最大差 6.8 倍（5012：0.8667 vs 0.1267；5016：0.86 vs 0.16；5013：0.60 vs 0.14；
  5018 反向：0.60 vs 0.6867）。两条路径的帧数口径相同，故**不是**采样密度差异，
  而是分母或参与维不一致（A 的 `clip_probe.note` 只说明了 pre/post 语义差，解释不了 preclip 与未截断值不等）。
- **裁定**：在该字段单一来源化之前，
  1. `mean_blown_frames_frac` 落在 **[0.03, 0.08] 区间的臂，其 `measurement_valid` 判定暂不可采信**，
     必须用对账后的实现重测；两条路径都远超 0.05 的臂（如 k2 seed0 的 0.2120 / 0.1180）裁定不受影响，INVALID 维持。
  2. **直接受影响的是 §7 的 `trimdone0_stdfloor_minmax_k2_lr1e-5_s20k_seed0`（blown = 0.0400，边缘通过）**：
     该臂的「边缘通过」与其 raw 20 / ctrl 16 **暂不得**用作「std 下限有效」的证据；
     §7 的否证结论不依赖它（否证由 3 个共同有效 seed 的 2/0/19 → 1/0/14 与 `floor(env[3])` 不生效独立支撑），故 §7 维持。
  3. 引用任何 blown 数字时必须写明**产出路径**（plain / clip_probe）与 `gate_build`。
- **分派**：A 负责把 blown 计算单一来源化（`scripts/eval_lerobot_act_runtime.py` 里 plain 与 probe 共用同一个函数），
  重测 [0.03, 0.08] 区间内的全部臂并在文档记差异原因；B 负责在门禁自检里加一条
  「同一产物重测两次 `mean_blown_frames_frac` 必须逐位相同」，并把 `blown_metric_impl` 指纹写进裁定 JSON。

## 增补四（2026-09-28 20:58，智能体 D）：门禁词表缺陷、探针免罪口径、§12 撤回与 §8 第 4 条重写

复核范围：ADR-A-005 的三项提请、A 的 blown 单一来源对账（`blown_metric_reconcile.json`）、
C 的黄金值对账（`c_golden_conformance.json` 20:53）、K=1 六 seed 全谱（A §21.7）。
结论：三项提请**全部采纳**，但第 2 项口径要**收紧**、第 3 项 D 自己拟的判据**写错了已改**；
另新增两条裁定（阈值溯源、§12 保留解除）。本增补所有数字均由 D 独立复算产物得出，不是转抄文档。

### 1. 裁定 8（ADR-A-005.1）：门禁 phase 词表缺陷 = 静默假阴性通道

- 证据（三份，可复核）：
  - `runs/20260924_142702_sac_lift_residual_grasp_lift/gate_v121_phase_misclassified_evidence.json`：
    `phase_field_kinds=["absent"]`；ep5000 `end_phase="done"`、`c4_basis="held_at_end=True & end_phase=done"`、
    `checks.end_phase=false`、`failed_checks=["end_phase"]`；20 局全判 `flick`、受控 **0**、`flick_frac_strict=1.0`。
  - 同目录 `audit_truth20_gatefields_pre_phase_trace.json` row0：`phase_at_end="done"`、`phase_trace=None`、
    `held_at_end=True`、`final_rise=0.096724`、`max_rise=0.108605` —— 夹持 / 抬升 / 未超帽三条**实质判据全过**。
  - 补 `phase_trace` 后的 `gate_v121.json`：`phase_field_kinds=["controller_log"]`、受控 **20/20**、`flick=0`。
- 根因（代码级，比「缺字段」更具体）：`scripts/b_gate_controlled_success.py:108-113` 的 `classify_phase_field`
  只能靠 `phase_trace` 进入 `controller_log` 分支；当夹持证据只存在于 `phase_at_end` 时，`:137` 取到 `"done"`，
  却落到 `:145` 的 `HOLD_PHASES_WITH_EVIDENCE = {"hold","grasp"}`（per-frame 词表，`:71`），
  `"done"/"lift"` 不在其中 → `c4=False` → `:192` 返回 `flick`。即**词表分支不对称**：
  controller-log 词表只在有 `phase_trace` 时才被承认，`phase_at_end` 单独带 controller-log 值时不被承认。
- 裁定：产物带 `phase_at_end ∈ CONTROLLER_LOG_VOCAB` 而 `phase_trace` 缺失时，门禁**不得输出任何失效模式标签**
  （`flick` / `insufficient_lift` / `over_lift` 全禁），只能输出「字段不匹配 → INVALID / unjudged」，
  并在 `missing_fields` 与 `phase_field_kinds` 里记明。理由：失效模式标签是**修复方向的指令**
  （增补三 §9-B⑤ 已把 `flick` 与 `insufficient_lift` 定义为指向相反旋钮），把「门禁认不出词表」
  报成「策略弹射」，会让 A 去修一个不存在的缺陷。
- 追溯：该臂 `flick=20` 的历史记录**作废**，以 `gate_v121.json` 的 `flick=0 / 受控 20` 为准；
  但其 `measurement_valid=False` **不受本裁定影响**（见裁定 9）。
- 引用注意：`gate_v121_phase_misclassified_evidence.json` 的 `file` 字段指向的是**修补后**的产物名，
  而其内容出自 `audit_truth20_gatefields_pre_phase_trace.json`（ep5000 的 `max_rise/final_rise` 逐位对应）。
  引用这条证据时必须同时给两个路径，否则会读成「同一份产物前后判不同」。
- 归 B（门禁代码，B-2）。A 不修改门禁，符合 ADR-A-003 立场。

### 2. 裁定 9（ADR-A-005.2）：无归一化学习策略的输入契约 = `not_applicable`，但**带齿**

- 现状（已核）：`:296-300` 的 `not_applicable` 只在 `n_with==0 and not learned` 时成立
  （`learned = ckpt or checkpoint or policy_config`）；residual 臂 `learned_policy=True` → 落 `unverified` → INVALID。
  这个从严是对的，**不改**。
- 裁定：为「学习策略但输入未归一化」新增第三条状态（建议名 `not_applicable_unnormalized`），准入须**同时**满足：
  1. 产物显式声明 `input_constraints.normalization = "none"`（residual 臂已有）；
  2. 落盘**训练期 raw obs 逐维 absmax**，来源可追溯（训练期记录，或同 seed / 同 config 的登记重采集）；
  3. 落盘**闭环 raw obs 逐维 absmax**，按与归一化路径同源的容差判：越界帧占比 ≤ 0.05；
  4. 门禁裁定 JSON 记 threshold 来源（同裁定 11）。
- 只有声明、没有 (2)(3) → 维持 `unverified` → INVALID。**声明本身不得成为免检通道**：
  否则任何臂都能自称「无归一化」绕过输入契约，这与 L1 伪装成能力不足是**同型漏洞**。
- 可行性核查（D 实测）：`runs/20260924_142702_sac_lift_residual_grasp_lift/model_final.zip` 内容为
  `data / pytorch_variables.pth / policy.pth / actor|critic|ent_coef.optimizer.pth / _stable_baselines3_version / system_info.txt`，
  **无 replay buffer** → 训练期 obs 范围**不能从现有产物恢复**。第 (2) 条只能靠训练脚本前瞻落盘，
  或跑一次登记在案的短重采集。
- ⇒ 本裁定**不给 residual 臂放行**：(2)(3) 产物存在之前维持 INVALID。
- 另一层限制（与输入契约无关，独立生效）：该臂 `composite_policy=true`、`active_constraints` 四项
  （`scripted_base_controller` / `residual_scale=0.25` / `residual_phases=grasp,lift` / `action_clip`），
  `accounts.autonomous_learning.denominator=0`。即使契约补齐，其 20/20 只能以 **system_assisted / composite**
  口径出现，**不得**与官方 ACT 臂同表，也不得用作「Lift 已解决」。

### 3. 裁定 10（新）：探针免罪 —— `measurement_invalid` 可降级为 `VALID_probe_exonerated`

- 动机：`k2 seed0` 的 9/20 因 `mean_blown_frames_frac=0.212 > 0.05` 判 INVALID，但 A/B 两线探针都显示
  截断对它**无行为后果**。若不接受免罪，等于用一个「测量可信度」量去否证一个能力数字，与裁定 12 矛盾。
- **D 的自我纠错（本条判据 D 先前拟错）**：D 原拟「探针产物与未截断产物的门禁相关字段**逐位相同**」。
  实测该判据在**目标臂自身**就不成立，必须改为**裁定级不变**：
  - plain vs C=12.469445 探针（D 独立复算 `regate_current/` 与 `clipprobe/regate_current/` 两份裁定的 `per_episode`）：
    - 逐局 `verdict` **20/20 完全相同**；`accounts` 五项完全相同（受控 9 / flick 1 / insufficient_lift 1）；
      `max_rise` 20 局逐位相同；
    - 但 `final_rise` 有 **4 局不同**（5012 / 5014 / 5016 / 5018），这 4 局在两条路径下 `verdict` 都是 `failure`。
  - ⇒「逐位相同」永远过严；正确判据是**裁定不变 + 差异可枚举且不进入任何计数**。
- 准入条件（全满足才可降级）：
  1. 探针截断常数 C **必须等于该 checkpoint 自己的训练期归一化 |x| 上界**（即产物 `input_contract.blowup_threshold`），
     不得用任意更紧的值；
  2. 逐局 `verdict` 全部相同，且 `accounts` 五项计数（受控 / provisional / over_lift / flick / insufficient_lift）全部相同；
  3. 仍有差异的逐局字段必须**枚举**（seed + 字段名），并证明这些局两条路径 `verdict` 相同、不进入任何计数；
  4. 探针产物路径、C 值、`gate_build` 登记在该臂记录里；
  5. 免罪只作用于 `measurement_valid`，**不改变** `composite_policy` 与三套账。
- 条件 1 的实测判别力（D 复算，这条是本裁定的核心约束）：同一臂用 **C=5.0** 的探针**不满足**条件 2 ——
  seed **5007** 的 `verdict` 翻转、`insufficient_lift` 由 1 变 0。即「截得越紧越安全」是错的：
  紧到改变行为，它就不再是免罪探针，而是**另一个策略**。C 的取值必须钉死在 train-absmax。
- 引用纪律：免罪后引用的数字取自 **plain 产物**（官方口径）；探针产物 `composite_policy=true`
  （`active_constraints=["norm_input_clip"]`），**不得**被当成官方臂数字引用。固定写法：
  「9/20 @ final_rise=0.040，`VALID_probe_exonerated`（C=12.469445=train-absmax，探针逐局裁定不变）」。
- 生效结果：
  - `k2 seed0` 的 9/20 恢复可用；K=2 同配方族（`trimdone0_minmax_k2_lr1e-5_s20k_seed{0..5}`，不含 `_replan1`）
    = **9 / 2 / 0 / 17 / 19 / 1**，n=6，均值 **8.0/20（40%）**（免罪前 5 个有效 seed 为 7.8/20 = 39%），
    极差 0~19，**双峰未填平**（受控 4–9 的臂仍是 0 个）。
  - **不构成上调**：§8 条件① 要 ≥3 个 seed 受控 ≥ 半数（≥10/20）；恢复后 K=2 仍是 **2/6**（17、19），
    K=1 是 **1/6**（20）。⇒ 改判 1 维持「部分满足」。

### 4. 裁定 11（新）：`blown` 阈值必须带来源，跨族不得混用同一把尺子

- 证据：`blown_metric_reconcile.json / cross_line_agreement`：B 用未裁剪导出上的常量 **23.85**；
  A 按每个 ckpt 自己的 normalizer stats 现算 → train24 族 **23.8450**、trimdone0 族 **12.469445**。
  同族数值一致、**规则不同**。
- 风险：0.05 是「越界帧占比」的容差，而**越界的定义依赖阈值**。阈值差近 2 倍时，同一个 0.05
  在两个族上不是同一把尺子；跨族引用 blown 数字会**静默改变判据强度**。
- 裁定：门禁裁定 JSON 必须记 `blowup_threshold` + `threshold_semantics` + 来源（哪个 ckpt 的哪份 stats）；
  文档 / 汇总引用任何 blown 数字必须带阈值来源、产出路径（plain / clip_probe）与 `gate_build`。归 B（B-2 追加）。

### 5. 裁定 12：`blown` 的语义边界 —— 只作测量有效性门禁，不得当失败原因

- 采纳 A 的 `generalization`（D 复核成立）：`mean_blown_frames_frac` 度量的是**输入越界程度**，不是**行为后果**。
- 取证：`runs/infra/lerobot_act_env_20260928/clampnochange/k2_seed0_ep5011_explained.json` —— C=5.0 下截断确实生效
  （`n_action_frames_differing=144`），但 `rise_trace` 峰值在 tick **154**、首个动作差异 tick **156**、
  峰值之后抬起轨迹逐位相同（C1/C2/C3 三条判据全 True）。即 48% 帧越界、输入从 93.4 截到 5.0，闭环真值不变。
- ⇒ blown 超阈 ⇒「这次测量不可信」（裁定 10 是唯一救济通道）；blown 超阈 ⇏「炸穿导致失败」。
  后者只能由**逐臂截断探针的行为差异**证明。**禁止**出现「L1 炸穿导致抓取失败」这类因果句，
  除非该臂有探针显示行为改变。

### 6. D 线第三次自我纠错：撤回 §12 的两处断言

- **撤回 1**：「**轨迹完全一致**」。实测只在 `max_rise` 这个**投影**上成立；同一对产物 `phase_trace` 有 6 局分岔
  （首帧 48/53/56/75/114/138）、`final_rise` 有 4 局不同，而这 6 局 `max_rise` 全为 0.0，所以只比 `max_rise` 看不见分岔
  （A：`d_claim_2_trajectory_identical = REFUTED`）。D 保留成立的部分：`max_rise` 20 局逐位相同（`d_claim_1 = CONFIRMED`）。
- **撤回 2**：「差异来自**分母或参与维不一致**」。A 的三假设逐局判定：
  H1 分母 **REFUTED**（逐局 `norm_input_frames_measured` 全等，150/局）、
  H2 参与维/阈值 **REFUTED**（52 个「截断从未生效」的可测局上 absmax 与 blown_frac 逐位相等）、
  H3 轨迹分岔 **SUPPORTED**（80 局里 **23** 局分岔，`H3_causality_clean=true`）。D 的 `d_diagnosis = REFUTED`。
- 正确解释：0.2120（plain）与 0.1180（probe preclip）**各自都对**，但它们是**两条不同闭环轨迹**上的统计量，
  不可互换。D 原先当成「同一轨迹上同一量算出两个值」的实现不一致，属误判。
- 保留并加强：§12 裁定 3（引用须写产出路径 + `gate_build`）继续有效，并升级为裁定 11 的阈值溯源；
  §12 分派给 A 的「单一来源化」已完成（`blown_frame_stats()`，指纹 `52eae25ee2d7`），D 认可。

### 7. 裁定 13：解除 §12 裁定 1 对 [0.03,0.08] 带臂的「暂不可采信」保留

- 前提已消除（A 提请，D 复核）：
  - 单一来源化完成，`input_contract.blown_metric_impl = 52eae25ee2d7`；
  - 恒等回归 `runs/infra/lerobot_act_env_20260928/reblown/reblown_vs_archived_stdfloor_seed0.json`：
    `verdict=PASS`、`n_value_diffs_violating=0`、20 处值差异全在允许集 `$.rows[].elapsed_sec`、
    新增键只有 `blown_metric_impl` / `blown_metric_source`、`keys_missing_in_new=[]`；
  - 重测后数字不变：blown **0.0400**、受控 **16/20**、`measurement_valid=true`、`gate_pass=true`、
    v1.2.1 / build `e4f5ec887788`。
- D 独立核了带内人口：48 臂里 `mean_blown_frames_frac ∈ [0.03,0.08]` 的**只有 1 个臂**
  （`trimdone0_stdfloor_minmax_k2_lr1e-5_s20k_seed0`，0.04）。其余 43 个实测值落在 0.0–0.0173 与
  0.1692 / 0.212 两侧，**中间无灰区**（另 5 臂 `unverified` 无值）。
- 裁定：该保留**即日解除**；§7 对 stdfloor 的否证结论继续成立（否证本就不依赖它）。
  带规则改为**前瞻性**：今后新臂若落在 [0.03,0.08]，必须带 `blown_metric_impl` 指纹 + 产出路径
  才允许进入定级讨论。
- §11 回流点里「blown 单一来源化 + 带臂重测」这一项**已回流**，从待办移除。

### 8. §8 上调条件第 4 条重写（采纳 ADR-A-005.3）

- 原条：「`rise←bias` 不再单独支撑结论（即闭环归因里 burst 贡献占比可复现地 **> 50%**）」。
- 实测不可达（A §21.8，D 复核）：burst 占比最高 `k2 seed3` **23.2%**、次高 `k1 seed0` **19.6%**，
  21 臂合计 **7.2%**（burst 0.04525 / bias 0.58390），**无一臂 > 50%**。
- 采纳 A 的意见：该条把「**有没有能力**」与「**是否复现 teacher 的动作形态**」混同 ——
  一个用非 burst 方式稳定抬起的策略会被这条**永久**挡在门外。这是判据设计错误，不是数据不足。
- 新条（替代）：「④ 闭环 dz 归因必须**逐臂报告** `rise←burst / rise←bias / rise←other` 与
  `dz_mean_tail`、`dz_pos_frac_tail`；**报告即满足，不设占比门槛**。若某臂 burst 占比 > 50%，
  另须说明其抬升是否依赖 teacher 形态（诊断，不作门禁）。」
- D 自我纠错：D 在增补三 §8 写下该条时**未核可达性**，属「判据未经数据校验即入册」。本条撤回并重写；
  §8 其余三条不变。
- 重写后 §8 逐条现状（D 依 `regate_current/` 独立复算，与 A §21.7 表一致）：
  ① K=1 **1/6**、K=2 **2/6** → **不满足**；② K=1 6/6、K=2 6/6（seed0 为 probe-exonerated，须标注）→ 满足；
  ③ 48 臂全在 v1.2.1 / build `e4f5ec887788` → 满足；④ 归因已逐臂报告 → 满足。
  ⇒ **仍不上调**，卡点唯一收敛到 ①「可重复性」。

### 9. 证据登记：当前权威汇总（48 臂 / 单一构建 v1.2.1）

- 臂数 **48**（44 留档 + 4 个新增 K=1 seed2–5）；受控成功合计 **134**（含 2 个 INVALID 臂贡献的 9），
  其中 `measurement_valid` 的 **41** 臂合计 **125**。D 独立复算与 A §21.10 一致。
- INVALID 结构变化（A §21.9，D 采纳并要求 B 更新）：缺字段的 5 臂补测后转 `strict + verified_ok`
  → 实质 INVALID 由 **7 降到 2**（`k2 seed0` 0.212、`k2 seed0_replan1`）；三分类改为
  **23 可引用 / 19 有效零成功 / 2 无效**；B §7 回流点「blowup 字段补齐」由 37/44 → **42/44**
  （含 4 个新 K=1 臂则 46/48）。
  - **本增补对 A §21.9 的唯一修正**：裁定 10 生效后 `k2 seed0` 转 `VALID_probe_exonerated`，
    实质 INVALID 再降到 **1**（`k2 seed0_replan1`），三分类「可引用」由 23 → **24**。
- K=1 六 seed 全谱 **20 / 0 / 0 / 2 / 0 / 0**（6/6 `measurement_valid`），均值 **3.67/20**，极差 0~20。
  `k1 seed0 = 20/20` **不得**单臂引用；B §7 若仍引为强结果，须按 B 自己 §4 的
  「任何单臂引用都属于挑 seed」纪律改写为「族均值 3.67/20 + 摆幅 0~20 + n=6」。
- **两族失败形态不同类，禁止混读**：K=1 的 4 个 0/20 是 `raw=0 / insuff=0 / flick=0`、
  `mean_max_rise ≈ 1e-4 m` 的**整体塌缩**（方块根本没离桌）；K=2 的失败主要是 `raw>0` 但
  `insufficient_lift`（夹住了、抬到 3.5–4.5 cm 就停）。混读会修错旋钮，代价是整轮训练。
- **算力不可比**：`(1,1,1)` 每帧重推理，推理次数是 `(4,4,4)` 的 **4 倍** → k1 的 3.67/20 与 k2 的 8.0/20
  不是同等算力下的比较，任何跨族排序必须显式声明这一点。

### 10. 证据登记：C 线黄金值对账已回流（§9-C① 结案）

- `runs/infra/c_golden_conformance.json`（20:53:55）：`conformant=true`，
  **PASS 171 / FAIL 0 / UNRESOLVED 0 / NOT_ASSERTABLE 1**，E1–E6 全跑，变异自检 13 项启用。
- 约定已收敛到规格侧：γ=0.9（每控制步）、slot 长 n=6、`γ_slot=0.531441`、H=20、C[0,6) / E[6,12) / D[12,20)。
- C 的三条发现全部判为 **C 侧实现错**（F1 前驱槽过度删失、F2 §3.3-1 漏检、F3 删失口径只覆盖接管），
  **规格侧未发现错误**；两个既有断言 T1/T2 编码了 F1/F2 的错误行为，处置是**改强断言**而非放宽实现。
- D 的监管读法：断言数由 158 → **171 增加**、FAIL 仍为 0，说明修复方向是「实现向规格靠拢 + 断言变严」，
  不是「改判据让它过」。这是本轮唯一一条**方法学上正向**的自检记录，作为其它线的范式引用。
- 边界：这仍然只是**规格一致性**，不是真实帧能力；措辞只能是「真实帧重放通过 + 规格一致性通过」
  （增补三 §10 末条继续有效）。

### 11. 对三线的要求（增补四）

- **A**：① 把裁定 10 的免罪结果写进 §21.10 汇总与 `arms_summary`（新增
  `validity_class ∈ {valid, VALID_probe_exonerated, invalid}` 列，并记探针路径 / C / build）；
  ② 按裁定 12 清查文档里所有「炸穿导致…」型因果句，改为「测量无效」或删除；
  ③ residual 臂若要争取裁定 9 放行，先产出**训练期 raw obs 逐维 absmax** 的登记产物
  （重采集或训练脚本前瞻落盘），**不得**只加声明字段；
  ④ `dz_pos_frac_tail ≥ 0.9` 作为 L2 预登记判据的**扩写**，D 原则同意但附条件：该阈值来自当前 6 个 seed 的
  **样本内**分离（0.9465+ vs 0.2430−，中间空 0.7），必须在**跑新臂之前**写进预登记文档，
  且首批新臂要报告它的样本外表现，**不得事后调整**；
  ⑤ 裁定 11 的阈值溯源在 A 侧产物里已有 `blowup_threshold` + `threshold_semantics`，保持不动。
- **B**：① 裁定 8 落地（phase 词表 → INVALID/unjudged，禁止输出失效模式标签），并把 `CONTROLLER_LOG_HOLD`
  的承认条件与 `phase_trace` 解耦；② 裁定 9 的第三状态 + 4 条准入；③ 裁定 10 的免罪类与 5 条准入 ——
  特别是「C 必须 == 该 ckpt 的 `blowup_threshold`」要在**代码里断言**，不能靠约定；
  ④ 裁定 11 的 threshold 溯源字段；⑤ 按本增补 §9 更新三分类与回流点计数（可引用 23→**24**、INVALID 2→**1**）；
  ⑥ `git init` 仍按 DR-002 四条护栏执行，**先写 DR-003 再 init**
  （D 复核：仓库当前仍**无** `.git`，DR-002 护栏 4 尚未做）。
- **C**：① F1/F2/F3 的修改已落在 C 的写入边界内，登记 append-only + 撤销记录；
  ② 把裁定 8–13 的**裁定身份**纳入账本字段（增补三 §9-C③ 的裁定包再加两键：
  `validity_class`、`blowup_threshold_source`）；③ `work/decisions/` 正式登记处建好后，
  把 DR-001/002 与本增补裁定 8–13 一并摄取；④ γ/n 单位冲突按 C §8 处置，但**真实帧路径的 n 必须等于
  `n_action_steps`**（K=2 臂为 2），不得沿用规格算例的 n=6 去解读真实臂 —— 这是 D 在整合评估里点出的
  主线阻塞项之一，C 的 smoke 与 A 的臂必须在同一个 n 上对话。
- **D（本线）**：① 本增补落盘 + `work/decisions/` 追加裁定 8–13；② 下一轮回流点：B 的门禁 v1.3
  （裁定 8/9/10/11 落地）、`git init` + DR-003、A 的 `validity_class` 汇总刷新；
  ③ 改判 1 在条件①（≥3 seed 受控 ≥ 半数）被任一族满足前**不再复议**。

### 12. 表述纪律（增补四，与第三节、增补一 §4、增补三 §10 并列）

- 不得写「20/20（residual）」而不带 `system_assisted / composite`、`scripted_base_controller` 与 `measurement_valid=False`。
- 不得写「探针证明截断无害」而不写 C 值与「C == train-absmax」；C=5.0 的探针**改变了裁定**，不是无害证明。
- 不得把 `VALID_probe_exonerated` 简写成 `valid`；两者在汇总里必须是不同取值。
- 不得引用「轨迹完全一致」「blown 口径不一致」这两句（本增补 §6 已撤回）。
- 不得跨族比较 k1 / k2 均值而不声明 4 倍推理算力差。
- 不得写「炸穿导致失败」；只能写「测量无效，能力未知」。

## 增补五（2026-09-28 21:20，智能体 D）：`partial` 禁标签、权威汇总刷新、A-2 预登记复核与 B 同步

复核范围：A 的收尾报告与 blindfix 补测、A 的 `docs/a_bimodal_divergence_preregistration_20260928.md`
（21:15 冻结、21:16 开跑）、B 的 `work/decisions/decisions_20260928_B.md` DR-003 与 `git init` 结果。
本增补所有数字由 D 独立复算产物得出。**发现 3 处新问题**（裁定 14、裁定 15、A 预登记 §2 的一处事实错误），
其中 A 预登记的问题**不改阈值**（已冻结），只加报告义务。

### 1. 裁定 14：`field_class != strict` 时禁止输出失效模式标签

- 触发事实：同名臂在两个目录给出**互相冲突**的裁定 ——
  `runs/infra/lerobot_act_env_20260928/regate_current/`（blindfix 前，5 臂 `field_class=partial` + `unverified`）
  与 `runs/infra/lerobot_act_env_20260928/blindfix/regate_current/`（补测后，`strict` + `verified_ok`）。
- D 独立复算的翻转明细（合并后 48/48 全为 `strict`）：

| 臂 | 补测前 | 补测后 | 翻转 |
|---|---|---|---|
| `train24_lr1e-5_actionminmax_s20k` | ctrl 0 / insuff 0 / **flick 11** | ctrl 0 / **insuff 11** / flick 0 | 11 局 flick→insufficient_lift |
| `train24_lr1e-5_actionminmax_s20k_seed2` | ctrl 0 / insuff 0 / **flick 3** / prov 1 | ctrl **1** / **insuff 3** / flick 0 / prov 0 | 3 局 flick→insufficient_lift；1 局 provisional_pass→controlled_success |
| `train24_lr1e-5_s20k` | ctrl 0 / insuff 0 / **flick 2** | ctrl 0 / **insuff 2** / flick 0 | 2 局 flick→insufficient_lift |
| 另 2 臂（`train24_lr1e-4_s20k`、`..._actionminmax_s20k_seed1`） | 全 0 | 全 0 | 无变化 |

  合计 **16 局** `flick → insufficient_lift`，**1 局** `provisional_pass → controlled_success`。
- 翻转**不是数据变了**：`blindfix/blindfix_vs_archived.json` 记 `n_identical_on_common_fields=5`、`n_differing=0`，
  5/5 臂共有字段逐位相同（唯一允许差异 `rows[].elapsed_sec`）。变的是**门禁走的证据分支**。
- 根因（D 逐局取证，ep 级证据在两份裁定的 `per_episode[].evidence`）：
  - 补测前：`held_at_end` 与 `final_rise` **双缺** → 走 `scripts/b_gate_controlled_success.py:153`
    `c4 = end_phase in HOLD_PHASES_STRICT`（`:70` = `{"hold"}`）；per-frame 的 `end_phase="grasp"` 不在其中
    → `c4=False`、`c4_basis="end_phase=grasp（strict：仅认 hold）"` → `:192` 返回 **`flick`**。
  - 补测后：`held_at_end=True` 存在 → 走 `:145` `c4 = bool(held_end) and end_phase in HOLD_PHASES_WITH_EVIDENCE`
    （`:71` = `{"hold","grasp"}`）；**同一个 `"grasp"` 标签这次被接受** → `c4=True`，
    再由 `:196` 判 **`insufficient_lift`**。
  - 即：`"grasp"` 这个标签是否算 C4 证据，**取决于一个不相关字段（`held_at_end`）在不在**。
    缺字段时门禁不是「证据不足 → 不判」，而是「证据不足 → 判成最重的失效模式」。
- **门禁本来就知道自己证据不足**：同一份裁定 JSON 里已写 `field_class="partial"`、
  `missing_fields=["final_rise","held_at_end","phase_at_end","terminal_kind"]`、`field_presence` 四个 0。
  弃权所需的信息已经在产物里，只是没被用来拦住标签输出。
- 裁定：**失效模式标签（`flick` / `insufficient_lift` / `over_lift`）只允许在 `field_class == "strict"` 下输出。**
  `field_class != strict` 时一律输出 `unjudged_evidence_missing`（计入 `n_unjudged`）并判 `measurement_valid=False`，
  同时在 `gate_reason` 里列出缺失字段。这是裁定 8 的**推广**：裁定 8 管 phase 词表不匹配，本条管一切证据不足。
- **不是缺陷、B 不得顺手"修"的**：`:198` 的 `provisional_pass` 通道是 v1.1 有意设计的「待补测」档
  （C1–C4 全过但「局末仍夹持」无字段可证）。它**正确地**没有把 seed2 ep5001 算成受控成功；
  补测后升级为 `controlled_success` 属预期行为。本裁定只禁**失效模式**标签，不动 `provisional_pass`。
- 连带改判：`flick = 23` **作废、不得引用**（它是 blindfix 前、含 5 个 partial 臂的数）。权威值见 §3。

### 2. D 线第四次自我纠错

- D 在 21:0x 的口头汇报里把根因说成「per-frame `phase_trace` 在成功抬起的局末**永不产出** `hold`」。
  **这句是错的**：`train24_lr1e-5_actionminmax_s20k_seed2` ep5001 的 per-frame `end_phase` 就是 `"hold"`
  （`phase_field_kind="per_frame"`、`n_phase_trace=300`）。per-frame 词表是 `{hold, grasp, descend, approach}`，能产出 `hold`。
- 正确表述是 §1 的**分支不对称**：同一个 `"grasp"` 在 `:145` 被接受、在 `:153` 被拒绝。
- 教训（与 §6 撤回、增补四 §3 判据写错同源）：D 在把「机制」写进裁定前，必须逐局打开 `evidence` 字段核对，
  不能从常量名反推行为。本条按纪律登记，不掩盖。

### 3. 权威汇总刷新（**取代**增补四 §9 的 134 / 219 / 23）

48 臂 / 960 局，单一构建 `v1.2.1` / `e4f5ec887788`，blindfix 裁定取代 5 个 partial 臂后（D 独立复算）：

| 项 | blindfix 前（A §21.10 现值，**已过期**） | 合并后（**权威**） | 免罪后（裁定 10 生效） |
|---|---|---|---|
| 受控成功 | 134 | **135** | 135 |
| `insufficient_lift` | 219 | **235** | 235 |
| `flick` | 23 | **7** | 7 |
| `over_lift` | 0 | 0 | 0 |
| `provisional_pass` | 1 | **0** | 0 |
| `measurement_valid` / 无效 | 41 / 7 | **46 / 2** | **47 / 1** |
| 三分类（可引用 / 有效零成功 / 无效） | — | 24 / 22 / 2 | **25 / 22 / 1** |
| `field_class` | 43 strict + 5 partial | **48 strict** | 48 strict |

- 仍无效的 2 臂：`trimdone0_minmax_k2_lr1e-5_s20k_seed0`（blown 0.212，裁定 10 免罪后转 `VALID_probe_exonerated`）、
  `trimdone0_minmax_k2_lr1e-5_s20k_seed0_replan1`（blown 0.1692，**无探针** → 维持 INVALID）。
- `flick` 的 7 局分布：`k2 seed0_replan1` 4、`k2 seed0` 1、`train24_lr1e-5_actionminmax_s20k_replan1` 1、
  `stdfloor k2 seed0` 1。其中 **5 局落在 2 个 INVALID 臂上** → 可引用 `flick` 只剩 **2 局 / 920**（0.2%）。
  这为 B-7（连续性 / slew-limit 停车）提供了比增补三更强的依据。
- **分母纪律**：A §21.9 的「23 可引用 / 19 有效零成功 / 2 无效」是 **44 臂**口径，与本节 48 臂口径**都对**，
  差值恰为 4 个新增 K=1 臂（seed3 可引用、seed2/4/5 有效零成功）。引用时**必须写分母**。

> **勘误指针（2026-09-29 增补六 §5，D 线第五次自我纠错；本节原文一字未改）**
> 上表「免罪后」两列（`measurement_valid` **47 / 1**、三分类 **25 / 22 / 1**）是 **裁定 10 的目标值 / A 侧实现值**
> （`scripts/summarize_lerobot_act_arms.py:190 probe_exoneration()` 自行断言五条准入），
> **不是任何 `gate_build` 的输出**。D 于 0929 实测：现构建（`v1.4 / b9379fdb1089`）下门禁**产不出**这两个值 ——
> `configs/b_probe_exonerations.json` 补条目也不生效，存在三处代码级阻塞
> （`:374` 争议带判定不按 `probe_kind` 分通道、`:359` `scope=arm` 的指纹前置、`:806` 晋级闸只认
> `verified_ok`/`not_applicable_verified`）。在 v1.5 落地前引用 25/22/1 必须带 **`PENDING_IMPL`** 标注。
> 证据：`scripts/d_verify_exoneration_cosign.py` → `tmp/agentD_review_20260929/D_cosign_k2seed0.json`；
> 正文见 `supervisor_memo_20260929.md` 增补六 §1、§5。

### 4. 裁定 15：门禁必须回显产物的 `blowup_threshold` 与 `blown_metric_impl`

- 事实（D 实测）：官方 ACT 产物把阈值写在 `input_contract.blowup_threshold`（=12.469445）+
  `threshold_semantics`，而门禁 `:284` 只从**顶层** `input_constraints.train_time_norm_absmax` 读，
  官方产物**没有这个键** → 裁定 JSON 里 `train_time_norm_absmax` 恒为 `null`。
- 连带 bug：`:311` 的 `ic_note` 因此打印「闭环有 21% 的帧收到超出训练分布的归一化输入（**|x|>0.0**）」
  —— INVALID 的**理由字符串本身是错的**（阈值显示为 0.0）。
- 裁定：门禁 v1.3 必须（a）从产物 `input_contract.blowup_threshold` 读取并回显到裁定 JSON，
  （b）同时回显 `blown_metric_impl`（这是 B 自己 DR-003 里预告的 DR-006「缺指纹才拒判」的前提），
  （c）修 `ic_note` 的阈值打印。这是裁定 11（阈值溯源）在门禁侧的落地缺口 —— A 侧产物已经合规，缺的是 B 侧回显。
- 顺带登记（对 A 有利）：`ckptseq/` 的新产物 `input_contract` 完整带 `blown_metric_impl=52eae25ee2d7` +
  `blowup_threshold=12.469445` + `threshold_semantics`，**比 20k 留档产物更合规**（留档产物 `blown_metric_impl=None`）。

### 5. A-2 预登记复核：批准冻结，但 §2 有一处事实错误必须更正（不改阈值）

- 总体评价：四条约束**全部覆盖且有超出**——§3 分辨率上限（`last -> 020000` 符号链接，每臂仅 2 个互异 ckpt）、
  §5 R5「先拿已知答案的 `020000` 对账留档 actlog，不过关整批作废」这一**先行门槛**、
  §6 逐 ckpt 输入契约 + R4、§4 排除免罪臂不进判据样本、§7 扩围三条触发、§8 不进主目录 glob（保护 §3 的 48 臂表）、
  §9 明确不声称因果。**这是本轮质量最高的一份预登记，作为其它线的范式。**
- **事实错误（D 复算 `closed_loop_dz_diag_A.json` 全 21 臂）**：§2 的样本内声明写
  「`dz_pos_frac_tail` 实测 0.9465+ 对 0.2430−（中间空 0.7）」，并称阈值来自「6 个 K=1 seed + 6 个 K=2 seed」。
  实测全谱（升序）：
  `0.0737 / 0.1885 / 0.2077 / 0.2430 / 0.5677 / 0.6690 / 0.7780 / 0.8330 / 0.8670 / 0.9400 / 0.9418 / 0.9455 /
  0.9465 / 0.9493 / 0.9500 / 0.9525 / 0.9575 / 0.9693 / 0.9993 / 1.0 / 1.0`
  - 「中间空 0.7」**只在 K=1 六 seed 上成立**（0.0737/0.1885/0.2077/0.2430 vs 0.9465/0.9993）。
  - **K=2 六 seed 就有三个落在所谓空档里**：seed0 **0.5677**、seed5 **0.6690**、seed2 **0.8670**。
  - 全 21 臂最大空隙是 `0.2430 → 0.5677`（**0.3247**），不是 0.7；`0.9` 这个切点落在**密集簇内部**：
    `[0.80, 0.95]` 区间有 **8 个臂**，切点两侧最近点是 0.8670 与 0.9400，间距仅 **0.073**。
- 影响（具体到 A §4 的臂选择）：K=1 对（0.9993 vs 0.0737）远离敏感区 → **结论稳健**；
  K=2 低分臂 `k2 seed2` = **0.8670**，距 0.9 只有 **0.033** → 该臂在 `010000` 的 `HIGH/POS_BIAS/NONPOS`
  归属**对阈值极敏感**，R1/R2 的 K=2 侧结论可能是切点造成的，不是训练动力学造成的。
- 处置（**不改阈值**）：A 已于 21:15 冻结、21:16 开跑，事后改阈值等于预登记失效，D 不要求改。改为：
  - **R7（追加报告义务，非判据变更）**：任何 (臂, ckpt) 若 `dz_pos_frac_tail ∈ [0.85, 0.95]`，
    必须同时报告按 `0.90 / 0.85 / 0.95` 三种切法的级别归属，且该族结论措辞降级为
    「**级别归属对阈值敏感**」；K=2 家族结论必须带此标注，K=1 家族可独立陈述。
  - A 须在预登记文档**追加一节**（不改 §2–§6 原文，符合 A 自己 §7 的追加纪律），登记：
    21 臂全谱、上述更正、R7、以及 §4 表的补全 —— §4 对 K=2 对只给了 `dz_mean_tail`（0.0280 / 0.0082，**且未标名**），
    漏给了级别归属的**第一判据** `dz_pos_frac_tail`（1.0 / 0.8670）。
- D 的立场：这不否定 A-2 的价值。恰恰相反 —— 若 `k1 seed0@010000` 行为上是 0/20（已实测，见 §6）
  而 dz 判别量已 ≥0.9，那就证明**判别量先于行为成功**，这是比「定位分岔时刻」更强的结果。

### 6. A-2 首个结果登记（D 独立读取，21:16 产物）

- `ckptseq/gate_trimdone0_minmax_k1_lr1e-5_s20k_seed0__step010000.json`：
  ctrl **0/20**、`raw_success=0`、`mean_max_rise=0.0`、`mean_final_rise=−0.0105`、
  `field_class=strict`、`measurement_valid=True`、`gate_pass=False (no_controlled_success)`；
  `input_contract`：blown **0.0**、`closed_loop_norm_absmax=10.8`（< 阈值 12.469445）→ **R4 不触发**，该时间点可用。
- 含义：20k 时 20/20 的臂，在 10k 时是**整体塌缩**表型（`raw=0`、`mean_max_rise≈0`，与 K=1 四个 0/20 臂同类）。
  ⇒ 本实验的问题被这个结果**改写了**：不再是「成功臂何时开始成功」，而是
  「**行为上同为 0/20 时，dz 判别量是否已经分开**」。这是更好的问题，A 应在结果节里显式写明这一改写。
- 提醒：`ckptseq/` 产物**不得**进 `arms_summary` / 48 臂权威表（A §8 已正确声明，D 确认）。

### 7. 同步给 B（用户 2026-09-28 21:1x 明示要求）

- **B-2 追加两条（门禁 v1.3）**：
  - 裁定 14：`field_class != strict` → 禁输出 `flick`/`insufficient_lift`/`over_lift`，
    改判 `unjudged_evidence_missing` + `measurement_valid=False`；`provisional_pass` 通道**不动**。
  - 裁定 15：从产物 `input_contract` 回显 `blowup_threshold` + `threshold_semantics` + `blown_metric_impl`，
    并修 `ic_note` 的「|x|>0.0」错误打印。
- **现成回归算例（有真值、零算力）**：blindfix 的 5 个盲臂。v1.3 下 ——
  旧 `partial` 产物必须输出 `unjudged_evidence_missing`（**不是** flick 11/3/2）；
  新 `strict` 产物必须仍输出 11 / 3 / 2 个 `insufficient_lift` 与 seed2 ep5001 的 `controlled_success`。
  这组算例同时覆盖「弃权」与「不误伤」两个方向，建议进 `scripts/b_selfcheck_gate_regression.py`。
- **计数更新**：B §3 三分类与 §7 回流点计数按 **48 臂**口径改为 **25 可引用 / 22 有效零成功 / 1 无效**
  （免罪后）；A §21.9 的 23/19/2 是 44 臂口径，两者不冲突，但 B 的文档必须标分母。
- **B-7 加强**：可引用 `flick` = **2 局 / 920** → 连续性 / slew-limit 工作**继续停车**，不必再议。
- **D 对 DR-003 与 `git init` 的核验结论：无违规，予以确认。**
  commit `0137b33`、tracked **228**、`git ls-files runs/ RL_Harness_v4_20260924/ registry/*/` = **0**、
  `size-pack` 未膨胀、体积闸 `scripts/b_git_size_guard.py` 已就位。
  DR-002 四条护栏：护栏 1（排除 `runs/`）✓、护栏 2（禁用命令清单）✓ 已写进 DR-003 并前置到 hook、
  护栏 3（交付包只读，已排除纳管）✓、护栏 4（DR-003 先于首次提交）✓。
- **D 遵守 DR-003 决定 8 的单写者纪律**：D **不执行任何 git 写命令**。本增补落盘的两个文件
  （`rl_harness_supervision/supervisor_memo_20260928.md`、`work/decisions/decisions_20260928.md`）
  已在 tracked 集合内，会由 B 的下次提交自然带上，**B 无需为 D 做任何例外处理**。
- **给 C 的连带项**：C 新建的 `registry/verdict_identity.py` / `scripts/c_selfcheck_verdict_identity.py`
  在裁定身份里必须包含 `field_class`（裁定 14 的前提量）、`validity_class`、`blowup_threshold_source` 三键，
  否则账本会把 `partial` 产物伪造的 `flick` 当物理事实存进去 —— 这正是增补三 §9-C③ 要防的事，现在有了实例。

### 8. A 线任务（增补五，接续增补四 §11-A）

- **A-1 P0（不占 GPU，优先于一切引用）**：合并出唯一权威表。刷新 `arms_summary` + 重写 §21.10，
  带 `superseded_by`（5 个 partial 裁定 → blindfix 裁定）、`validity_class`、`blowup_threshold_source`、
  **显式分母**（48 臂 / 44 臂两套都要给）。落盘后 §3 表取代 134 / 219 / 23；
  A 的 `daily_report.md` 与收尾报告里的 134 / 219 / 23 须标注为「blindfix 前口径」。
- **A-2 P0（已在跑，批准继续）**：按 §5 追加 R7 与更正节（**不改 §2–§6 原文、不改阈值**）；
  按 §6 在结果节写明「问题被首个结果改写」；K=2 家族结论必须带阈值敏感标注。
- **A-3 P1**：把裁定 14 的最小复现移交 B —— 臂 `train24_lr1e-5_actionminmax_s20k`、
  seed 5000 起 11 局；证据 = 两份裁定的 `per_episode[].evidence`（`c4_basis` 前后对比）+
  `blindfix_vs_archived.json`。A 不改门禁（ADR-A-003 立场不变）。
- **A-4 P2（明确暂缓，维持增补四）**：teacher 去饱和与 L1 路径 (a)/(b) **不动**。
  A 已在预登记 §9 自行写明暂缓理由，D 认可，无需再登记。
- **A-5 P2（建议不花 GPU）**：residual 臂的训练期 raw obs absmax（裁定 9 的 (2)(3)）**不重跑**；
  改为只在训练脚本里前瞻落盘 obs stats，未来的 SAC 臂自动合规。

### 9. 表述纪律（增补五）

- 不得引用 `flick = 23`；权威值 **7**（可引用 **2 局 / 920**）。
- 不得引用 134 / 219 / 23 而不标「blindfix 前口径」；权威值 **135 / 235 / 7**。
- 引用三分类必须带分母（48 臂 25/22/1；44 臂 23/19/2）。
- 不得写「`dz_pos_frac_tail` 把臂一刀两断、中间空 0.7」；只在 **K=1 六 seed** 内成立，
  21 臂上最大空隙是 0.3247，0.9 切点落在 8 臂密集簇内。
- 不得写「分岔发生在第 X 步」（A §3 的分辨率上限）；只能写「不晚于 10k」或「10k–20k 之间」。
- 不得把 `ckptseq/` 的中间 checkpoint 数字写进 48 臂表或跨口径排序。

### 10. 回流点（增补五）

回来后再议的三件事：① A-2 首批 8 次评测的 `divergence_verdict.json`（含 R5 对账结果与 R7 敏感性标注）；
② B 的门禁 v1.3（裁定 8 / 9 / 10 / 11 / 14 / 15 六条落地 + blindfix 回归算例）；
③ A-1 的合并权威表。
三者任一回来且与 §3 表不一致时，**先改 §3 再谈结论**。
改判 1 在条件①（≥3 seed 受控 ≥ 半数）被任一族满足前不再复议（增补四 §11-D③ 继续有效）。

### 11. 追加（21:2x，D 复核 B 在途改动时发现）：v1.3 已落地一半，存在 P0 顺序风险

D 在本增补落盘过程中发现 B 已在改 `scripts/b_gate_controlled_success.py`（`git status` 显示 M，
`GATE_VERSION` 已由 `v1.2.1` 升到 **`v1.3`**，+343 行）。逐条核对结果：

- **B 已实现的（D 确认，无需重复提）**：
  - 裁定 9：`IC_VALID_STATUSES` 已含 `not_applicable_verified`（`:141` 附近的白名单，单一来源、禁止散写）；
  - 裁定 10：`IC_VALID_STATUSES` 已含 `probe_exonerated`，并引入 `EXONERATION_DOC = configs/b_probe_exonerations.json`；
  - 裁定 11 / 15：`blown_impl_check()`（`:244`）已把 `blowup_threshold`、`gate_tolerance`、`impl`、
    `artifact_sha256` 写进裁定 JSON；
  - `KNOWN_BLOWN_IMPLS = ("52eae25ee2d7",)`（`:136`）已含 A 的指纹 ⇒ **D 无需另行会签该指纹**；
  - 新增 `field_class = "blind"`（关键字段全缺，`:563`）与 `field_blind` 的 `gate_reason`（`:721`）。
- **B 尚未实现的**：**裁定 14**。`:466` 的「strict：仅认 hold」分支与 `:561` 的 `partial` 分类**原样保留**，
  `blind` 只覆盖「关键字段全缺」，**覆盖不到**本节 §1 的通道（`partial` + per-frame `end_phase="grasp"` +
  `held_at_end`/`final_rise` 双缺 → 仍会输出 `flick`）。DR-D09 依然有效，需 B 落地。
- **P0 顺序风险（必须先处置）**：`configs/b_blown_impl_grandfathered.json` 与
  `configs/b_probe_exonerations.json` **两个登记册都不存在**（`configs/` 实测只有 10 个文件，无这两份），
  而 B 的代码在读不到豁免册时**一律不豁免**（`:277-281`，note 明写「册子读不到时一律不豁免」）。
  D 实测影响面：主目录 43 份带 blown 字段的官方产物里，**只有 4 份带 `blown_metric_impl` 指纹，39 份没有**
  ⇒ **现状下用 v1.3 做全量重判，这 39 份会被判 `missing_new_reject`，48 臂权威表整体不可裁定。**
- **裁定 16（顺序纪律）**：
  1. 两个登记册填好之前，**不得**用 v1.3 做全量重判；
  2. v1.3 的局部结果**不得**与 v1.2.1 的结果混在同一张表（增补三 §10「禁跨 build 混引」继续有效）；
  3. `GATE_BUILD` 是门禁脚本的内容哈希（`:56`），v1.3 已不等于 `e4f5ec887788` ⇒ **改判 7 触发**：
     本增补 §3 的权威表明确标注为 **v1.2.1 / `e4f5ec887788` 口径**；v1.3 落地并全量重判后须以 v1.3 重出一次，
     届时 §3 表降级为历史口径（不作废，但不得再当现值引用）；
  4. 豁免册的 `cutoff` 与逐条理由、以及免罪册里 `k2 seed0` 的条目（须含探针路径 / C=12.469445 / build /
     裁定 10 五条准入的逐条核对）由 **B 写、D 会签**。免罪条目的事实基础 D 已核可（增补四 §3）。
- **A-1 顺序修正（D 对自己 §8 分派的修正）**：A-1 的合并权威表应**等 v1.3 落地后一次性建在 v1.3 上**，
  否则要在 v1.2.1 建一次、再在 v1.3 重建一次。A 现在可以先做**结构性**部分：
  `superseded_by` 链接、`validity_class` 列、分母标注、把 134/219/23 标为「blindfix 前口径」；
  **数字列等 v1.3 全量重判后再填**。（D 注意到 `scripts/summarize_lerobot_act_arms.py` 已在改，正是此处。）

---

> **接续（2026-09-29）**：本备忘之后的裁定 17–21、D 线第五次自我纠错、检修后开工核验，
> 见 `rl_harness_supervision/supervisor_memo_20260929.md`（增补六）。
> A / B / C 每轮开场须**同时** pull-read 两份备忘；本文件自 0929 起为**只读历史**，
> 新裁定一律写进 0929 文件，不再追加到本文件（唯一例外：上方 §3 的勘误指针，属就地勘误不属新裁定）。
