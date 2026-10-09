# D → B2 执行单（2026-09-29 16:4x）：**双向示范数据 + 判据/可复现性准入**（v4 §12 P1 的数据前置 + §13 口径）

交出方：智能体 D（监管/口径裁定线）。接收人：**智能体 B2（数据与判据线，新开）**。抄送：A2（VLA 底模与仿真贯通线）、A/B/C（收尾后冻结）。
依据：用户 2026-09-29 裁定（`work/project_parameters.json` → `measurements_and_decisions[0]`）＋
`rl_harness_supervision/supervisor_memo_20260929.md` **增补十五（裁定 38）**。
上位方案：`RL_Harness_v4_20260924/`（**只读**），重点 `appendices/01_接口契约与开发验收.md`（T01–T54，尤其 **T17**）。

---

## 0. 定位与**不许做**

**定位**：你是这条线的**证据侧**。A2 负责「模型能不能跑」，你负责「跑出来的东西能不能被相信」——
双向示范数据、T17 目标条件贯通、三口径评测器、以及 A2 那套新环境的**可复现性准入闸**。

**不许做**：
1. **不许训练模型、不许占 GPU 做长任务**（单卡是 A2 的瓶颈资源；你要 GPU 只做秒级前向的账本核对，且需申报）。
2. **不许改 `/workspace/mnt/sppro/yhzhang91/scripts/yhzhang91/vla_pipeline` 的任何代码**——那是团队资产、在本仓范围外。
   **只读使用 + 只在自己的输出目录写**。若要改它的规则，报 D，由用户去谈。
3. **不许碰 `/workspace/mnt/sppro/yhzhang91/datasets`**（全局硬约束：不读不写不 mv）。
4. **不许用 `rm`**；清理走 `/workspace/mnt/sppro/yhzhang91/recycle_bin/`。
5. **不许碰冻结面**，也不许改 A/B/C 已交付的实现（`harness/`、`registry/`、`configs/`、两份 0928 lock、`arms_summary_v3.json` 等）。
6. **不许把「数据造出来了」写成「双向能力有了」**：见 §5。
7. **不许直接改 `work/project_parameters.json`**（D 单写者）；交建议值 + 证据路径。

---

## 1. 任务 1（P0，今天）：A2 新环境的**可复现性准入闸**

A2 会交来 `runs/vla/a2_env_pi05_sim_20260929/{requirements.lock.txt, env_manifest.json}`。你要做的：

1. **直接复用 B 已验收的闸，不要另写一套**：`scripts/b_env_provenance_guard.py`（G1–G5，`--selftest` 10/10 已被 D 验收）
   + `runs/infra/b_env_migration_invariance_20260929/` 的 **V0–V9 不变性口径**（当前 10/10 全过）。
2. **三条针对 π₀.₅ 的新牙**（这是本仓还没验过的面，必须由你补）：
   - **V-pi05-1 版本锚**：`lerobot==0.4.4` 必须与已验收的两套 venv 一致；`transformers` 的**实际装成版本**必须写进产物
     （裁定 34.1 的口径：**钉实际装成的值，不回退**；引用差异必须**点名包与版本**，不得写成「差异可忽略」）。
   - **V-pi05-2 权重同一性**：`weights_receipt.json` 里的 **sha256 必须可复算**，且 `config.json` /
     `policy_preprocessor.json` / `policy_postprocessor.json` **三件齐**（缺后两件会静默走默认归一化 ⇒ 这是最坏的一类假绿）。
   - **V-pi05-3 通道留痕**：走的是 ModelScope 还是 hf-mirror，必须留痕；**外部来源事实**（license、他人显存报告）
     引用时必须标 `external_unverified`，不得与本机实测并列（裁定 36.4：**跨口径不得并列**）。
3. **产物**：`runs/vla/b2_env_admission_20260929/`，含 `admission_verdict.json`（每条 check 带 `id/ok/observed/required/note`，
   与 B 的 `invariance_verdict.json` 同构）+ 日志。**判据必须有牙**：恒真的闸等于没有闸（裁定 27.1），
   所以每条 check 都要能被一个**具体变异**打红，并把变异结果一并落盘。

---

## 2. 任务 2（P0–P1，今天起）：**正反向双向示范**，形态对齐团队流水线

用户裁定：正反向示范**暂由仿真或自建数据集给出**，实机数据后采，**形态参考团队流水线**。

### 2.1 目标形态（D 已实测，照这个来）
团队数据形态 = `/workspace/mnt/sppro/yhzhang91/workplace/ABC130k/<split>/<task>/episode_<uuid>/`，内含：
- `converted_metadata_normal.json`：`action` / `state` 各含 `left_arm{joint(6),pose(7),velocity}`、`right_arm{...}`、
  `left_gripper{joint(1)}`、`right_gripper{joint(1)}`、`left_hand`/`right_hand`（可空）、
  以及 `is_move`、`task_info`（自然语言）、`subtask`、`intrinsics`（3 组）、`file_path`、`frame_validity.is_valid`；
  实测一条 episode = **4749 帧**，源为 `.mcap`（XDOF_ABC-130k）。
- 视频槽位（`vla_pipeline` 的 `configs/default.yaml` 口径）：`top-camera.mp4`（head）、`left-wrist-camera.mp4`、`right-wrist-camera.mp4`。

### 2.2 你要产出的东西
1. **仿真侧双向示范**：在 A2 打通的 ALOHA 类仿真环境里，用**脚本化 expert 或遥操作**采 **A→B（正向）**与 **B→A（反向）**各若干条，
   写成 §2.1 的目录形态。**两个方向的条数必须相当**——本仓现在的最大数据缺口就是
   **`lift_B_to_A` 方向真帧 teacher 0 行**（`daily_report.md` 15:4x §7），它直接导致 T17 只能证明「计算图贯通」而不能证明「方向能力」。
   **你这条线的首要价值就是把反向示范从 0 变成非 0。**
2. **过 QC**：用 `vla_pipeline` 的 `validate → clean → qc` 跑一遍你自己的数据（`python cli/main.py run --batch-id b2_sim_bidir_001 --config <你的 yaml>`），
   留 `report.md` / `badcase.json` / `pipeline.db`。**配置自己写一份**（放你的输出目录），
   单臂/双臂的字段口径按 `rules/qc/_meta.py`；**不要把 `configs/default.yaml` 的路径当现成输入**——
   它指向的 `workplace/2/3ABC130k_have_subtask` **在本节点不存在**（D 实测）。
3. **顺带定性一条疑点**：D 在 ABC130k 的一条 episode 上实测到 `is_move` **全 0** 而 `frame_validity.is_valid` **全 1**。
   用 QC 跑一遍看它是否报 badcase；**只报观测，不下结论**（那是团队数据，不是本仓资产）。
4. **数据落 NFS**：体积超过 10 GB 先申报（NFS 已用 94%）；一律 `.codex-persist/` 或 `runs/vla/b2_*` 下，**不许落 `/root`**。

---

## 3. 任务 3（P1）：把 **T17** 接到 π₀.₅ 的输入与账本上

**T17 原文**（`appendices/01_接口契约与开发验收.md:337`）：相同状态换 A→B／B→A 目标，**同一 θ** 对目标有正确条件依赖，
**Q/target/样本均接收目标**，检查两方向实际梯度与行为；`:352` 补充：**不要求随机初始化就高成功率**，
首先测「goal 确实进入全部计算图、标签和 target」，然后用已知小样本任务验证条件化行为；**维度检查不等于目标语义已正确**。

1. **复用已有实现，不要重写**：`scripts/a_selfcheck_goal_conditioning_t17.py`（A 侧）与 `scripts/b_selfcheck_goal_conditioning_t17.py`（B 侧）
   已经把 goal 接进了 `harness/queue_td_learner.py` 的 `LearnerConfig.goals` 与账本口径，且**端到端 smoke T1–T6 全过**
   （`daily_report.md:2572`，含 T5 的正确拒绝：`exit 1 + LearnerRefused + 零产物`）。
2. **你要新增的是「π₀.₅ 版 T17」**：goal（语言指令或目标区域标识）是否真的进入了 **π₀.₅ 的 prompt/输入张量**、
   是否进入了**导出分片与账本**、以及**换 goal 时前向输出是否真的变化**（同状态、同 θ、只换 goal ⇒ 输出必须不同；
   若逐字节相同，就是 goal 没接进去，**必须判红**）。
3. **两条已知的诚实边界照抄**：① 反向示范为 0 时**不得**声称「已学出方向差异」（A 线原话，`daily_report.md:2596`）；
   ② 计算图贯通 ≠ 目标语义正确（`:352` 原话）。

---

## 4. 任务 4（P1）：**三口径评测器** + 发布口径

1. **三口径分开统计**（这是防止「系统看起来在进步、policy 其实没进步」的唯一手段）：
   - **policy 自主成功率**：不计任何接管与 harness 动作辅助；
   - **系统最终完成率**：允许恢复与接管；
   - **干预率**：每局需要多少外部帮助。
2. **双向分开报，发布合并判**：`01_开发技术方案.md:27` —— **同一 checkpoint 通过正反双向评估后整体发布**，
   **不许**分别挑两个方向最好的模型冒充共享策略。评测器要在结构上**做不到**这种冒充（例如强制同一 `checkpoint_sha256` 字段）。
3. **H1 对照口径预埋**：`01_开发技术方案.md:376` —— RL 的对照必须是**同预算的动态 Harness-DAgger/BC**，
   不是「RL vs 冻结 SFT」。评测器现在就要能按 `arm ∈ {dynamic_bc, bc_rl}` 分组，并记录两组的**纠正/示范/交互预算**是否相同。
4. **对接发布面**：结果要能被 `registry/release_bundle.py`（ReleaseBundle / DeploymentManifest）消费；
   **不要新造一套发布格式**。

---

## 5. 不得声称（照抄进报告）

- **不得**声称「双向能力已具备」——你交付的是**数据 + 判据 + 闸**，能力主张只在 A2/后续 BC+RL 的评测上成立。
- **不得**声称仿真示范「等价于实机示范」——实机型号/夹爪/时延全部 `null`，形态对齐**只是接口对齐**。
- **不得**把 ABC130k 的统计当成本项目数据集的统计（不同机器人、不同任务、不同采集方）。
- **不得**把 QC「全过」当成数据「语义正确」——`vla_pipeline` 查的是文件/帧数/FPS/对齐，不查动作是否物理可行。
- **不得**把 `external_unverified` 的事实与本机实测并列成同一张表（裁定 36.4）。

---

## 6. 汇报

- 报告落 `docs/b2_bidirectional_demo_and_gates_20260929.md`，产物落 `runs/vla/b2_*`（**目录必须带 `b2_` 前缀**）。
- 数据集体积、GPU 占用（若有）、以及任何对 `vla_pipeline` 的**只读**调用命令，都要在报告里可复现。
- 优先级：**任务 1（准入闸）→ 任务 2（双向示范）→ 任务 3（T17）→ 任务 4（评测器）**。
  任务 1 卡住 A2，所以今天先做；任务 2 的反向示范是全项目当前**最硬的数据缺口**，排第二。

---

# §7 增补（2026-09-29 16:4x→16:5x，D）：判据可以直接**采纳成品**，不用手搓

D 写完 §1–§6 之后读到两批新交付，其中一条把你的任务 4（三口径评测器）从"手搓判据"变成"采纳 + 对齐"。
**本节优先级高于 §4 的对应表述**；原文按 append-only 不改。

## 7.1 `SO100GraspCube-v1` 的 `evaluate()` 就是本项目三条悬案的成品答案

`mani_skill/envs/tasks/digital_twins/so100_arm/grasp_cube.py:414`（环境调研线 16:4x 已实测并贴原文）：
`reached_object = tcp_to_obj_dist < 0.03`、`is_grasped = agent.is_grasping(cube)`（双指 pairwise 接触力 ≥0.5 N 且夹角 ≤85°）、
`cube_lifted = cube.pose.z >= cube_half_sizes + 1e-3`、`reached_rest_qpos = dist < 0.2`、
**`success = cube_lifted & is_grasped & reached_rest_qpos`**、`touching_table = (lforce>=1e-2)|(rforce>=1e-2)`。

| 本项目口径 / **未裁项** | 现成实现 | 你要做的事 |
|---|---|---|
| `success_rate_grasp_verified`（为堵 robosuite Lift 的 `success_flick` 而手搓） | `success` **结构上含 `is_grasped`** ⇒ flick 拿不到 success | 评测器**直接读 `info` 的 6 个字段**，不再事后审计重建 |
| **`C5=0.04` 是否按 `object_geom` 缩放**（`daily_report.md:272`、`:1256`，**至今未裁**） | 阈 = **`cube_half_sizes + 1e-3`**（按物体几何缩放 + 1 mm 余量） | **向 D 提交裁定建议**：用"几何缩放 + 余量"取代固定 `0.04`，并给出你数据上的等价数值 |
| 晋级条件①的"**受控**成功"（`supervisor_review_20260924.md:68`） | `reached_rest_qpos`（回到预定 rest 位形，阈 0.2） | 把"受控"写成可量化定义，纳入三口径的**自主成功率**判据 |
| P1 `insufficient_lift` 直方图（`daily_report.md:270`） | `cube_lifted` 与 `is_grasped` **分离输出** | 失败归因轴：没抓住 / 没提够 / 没回位 / 撞桌 |
| 本项目**没有**的维度 | `touching_table`（撞桌安全）、`reached_object`（reach 阶段位） | **白送两条轴**，纳入失败阶段分布 |

**但有一条不许搬**："`success` 含 grasp 真值"只对 `SO100GraspCube-v1` 成立；`PickCube-v1` 的
`success = is_obj_placed & is_robot_static` **不含** `is_grasped`（flick 可得）。
⇒ 评测器必须**按 env id 分别声明判据来源**，不得写成一个全局 `success` 读法。
**"成功判据是任务设计的一部分，不是环境的既成事实"这条结论不变**，变的只是重建成本。

## 7.2 你的双向示范**优先在 ManiSkill 系上采**（与 A2 §8.3 对齐）

A2 的仿真首选已改为 `SO100GraspCube-v1` / `PickCube-v1`（state 档可跑、判据成品、@1024 达 43,082 steps/s），
`gym-aloha` 降为形态对齐备选。⇒ **你造数据的环境要和 A2 用同一个**，否则动作契约对不上、数据是废的。
**做法**：等 A2 的 G2 契约表（动作维度/单位/频率/夹爪语义）落盘后再定稿数据 schema；
在那之前**先做任务 1（准入闸）与 §2.2 的目录形态骨架**，不要抢跑采数据。

## 7.3 反向示范的缺口现在有了**定量证据**，引用它

A 线 16:4x 真跑实测：`lift_A_to_B` **7128 行**、`lift_B_to_A` **0 行**、`teacher_available=false`
⇒ goal one-hot 在训练集里是常量、未覆盖方向那列**零梯度**；训练后 ckpt 上
输出空间 `mean|Δgoal|/mean|Δstate| = **0.0028**`、权重空间 goal 列/state 列 absmax = **0.966**。
**这是你这条线存在理由的最硬证据**：不是实现有问题，是**反向数据为 0**。
引用时必须带口径（训练后 ckpt、`n_states=8`、单方向真帧），且**不得跨 regime 搬阈值**（A 自查第 7 起的教训）。

---

# §8 增补（2026-09-29 17:0x，D）：任务 1 的准入闸**现在有了具体 required 值**（否则牙咬不住）

D 实测了 `importlib.metadata.requires('lerobot')`（0.4.4，在已验收 venv 里只读），把你 §1 的 **V-pi05-1 版本锚**
从"要与已验收一致"细化成**可判红的具体数值**。全文见 `d_handoff_to_a2_20260929.md` **§9**。

## 8.1 V-pi05-1 的 `required` 字段照这个写

| 包 | required（实测来源） | 说明 |
|---|---|---|
| `torch` | **逐字等于 `2.6.0+cu124`** | 已验收两套 venv 实测值；`torch<2.11.0` 的上界**允许 pip 升到 2.7+ 并换 cu126/cu128** ⇒ 这是最容易被"顺手升级"造出新断点的一处 |
| `torchvision` | `0.21.0`（cu124） | lerobot 要求 `<0.26.0,>=0.21.0` |
| `transformers` | **`>=4.57.1,<5.0.0`** | **不是核心依赖**，在 extra `transformers-dep` 下；`maniskill_probe` venv 里是 **4.30.0 ⇒ 必须判红**，不许拿它跑 π₀.₅ |
| `accelerate` | `>=1.10.0,<2.0.0` | lerobot 核心依赖 |
| `lerobot` | `==0.4.4` | 与已验收两套一致；升级 = 换断点 |
| `peft`（若装） | `<1.0.0,>=0.18.0` | 仅微调路径需要；**本阶段只加载与推理，装了就登记，没装不算缺** |

## 8.2 **新增第 4 条牙：V-pi05-4「解析器不得动 torch 栈」**

A2 被要求先落 `runs/vla/a2_env_pi05_sim_20260929/resolve_dryrun.txt`（`pip install --dry-run` 的解析清单）。
你的闸要能对它判红：**清单里出现 `torch` / `torchvision` / `torchcodec` 的 install 或 upgrade ⇒ RED**（不是 WARN）。
**变异体**：造一份把 `torch 2.6.0+cu124 → 2.9.0+cu128` 的 dry-run 清单，闸必须红；
再造一份只含 `transformers 4.57.1` 新增的清单，闸必须绿。**两个方向都要有**，否则这条牙是恒真或恒假。

## 8.3 三条并发纪律（与 A2 §9.3 同源，你这边也要守）

- **你不下载权重**（单线负责 = A2）。理由：hf-mirror 已实测 8 worker ⇒ 429、单流 ~28 KB/s，两会话并行会互相触发限流。
- **你不起 GPU 长任务**；秒级前向核对也要在 `daily_report.md` 申报，且**不得与 A2 同时占卡**。
- **写文件按线前缀分家**：`docs/b2_*.md`、`runs/vla/b2_*`；追加共享文件前先 `git status` + `tail`。
- **git 单写者职责在 B 完成最后一次代提交后移交给你**（`d_freeze_abc_20260929.md` §2.2）；移交前你**不提交**，只把待提交清单报 D。

---

# §9 增补（2026-09-29 17:1x，D，裁定 40）：**新增任务 5 = 观察模型校准**；数据 schema 按 **Piper 6+1** 对齐

## 9.1 任务 5（新增，P2 前置）：观察模型校准 —— **用 dashscope / `qwen3.8-max`**

**用户裁定**：观察模型复用 `REMOTE_ENDPOINTS.md`（iflytek），并称"端点效果与 GPT-6 无本质区别"。
**D 亲自实测后的裁定（裁定 40.1）**：
- **iflytek / `gpt-5.6-sol` 当前不可用**，且**不是 URL 前后缀问题**：默认客户端 UA ⇒ **7 个变体全 403**
  （38,869 B 的 iflytek WAF 拦截页："您提交的信息可能对站点造成威胁…Powerd By iflytek Security"）；
  浏览器 UA ⇒ **302 → `https://iflygw.iflytek.com/changeUrl.html?goto=<原URL>`**（JS 页，无明文新地址）。
  ⇒ 需要**正确的 API base host** 或 iflytek 侧对本节点出口 IP 放行；**已报用户**。
- **dashscope / `qwen3.8-max` 实测可用**：文本 **HTTP 200 / 1.2 s**；**视觉通过**
  （64×64 纯红 PNG 以 data URL 传入，正确回答红色）⇒ **本轮观察模型 = `qwen3.8-max`**。
- 探针与产物：`runs/vla/d_observer_endpoint_20260929/{probe_observer_endpoint.py, observer_endpoint_probe.json}`
  （**直接复用，不要另写一个探针**；密钥从 `REMOTE_ENDPOINTS.md` 只读解析，产物里一律掩码）。

**你要做的三件事**：
1. **校准集**：从仿真轨迹里留出**录像/关键帧**（正例：抓成功；反例：抓空、flick/弹射、撞桌、超时），
   让观察模型给"成功/失败 + 失败阶段 + 是否需要纠正"的判定，与**环境真值判据**逐条对齐，产出一致性表
   （`SO100GraspCube-v1` 的 `is_grasped` / `cube_lifted` / `reached_rest_qpos` / `touching_table` 就是现成真值，见 §7.1）。
2. **两条必须分开的指标**：**判定一致率**（与真值同不同）与**纠正可用率**（它给的纠正动作是否落在允许编辑范围内、是否可执行）。
   v4 `01_开发技术方案.md:7` 明写「**Harness 的输出也需验证**」，§6.2 要求纠正必须是"标签、同协议动作或应急接管"之一 ⇒
   **"模型说得对"不等于"纠正能用"**，这两条不许合并成一个分数。
3. **口径纪律**：用户说的"与 GPT-6 无本质区别"记为 **user_decision**；**但换 provider 不降低验证要求**。
   在你的报告里**不得**写成"已等价于 GPT-6"；只能写"在**本校准集**上的一致率为 X，纠正可用率为 Y"。
   `intended_primary_observer` 在参数表里仍是 GPT-6（设计假设保留），`actual_provider_model_id` 是实测值 —— **两者不许混写**。
4. **不要重试 iflytek**：WAF 已记录行为，反复重试只会让放行更难。等用户给出正确 base_url 后，**用同一个探针**补测并把结果追加为新产物（不覆写 D 的那份）。

## 9.2 任务 2 的数据 schema：**按 Piper 6+1 对齐**（实机型号已由用户裁定）

- 实机 = **松灵 Agilex Piper**；`ABC130k` 实测形态为每臂 `joint(6)` + `pose(7)` + `velocity`、`gripper joint(1)` ⇒ **与 Piper 相容**。
- 你的仿真双向示范 schema **以 A2 的 G2 契约表为准**（§7.2 的顺序不变），但**目标形态锚定 Piper 6+1**，
  这样实机数据后采时**不需要重造 schema**。
- **必须带 `morphology_proxy` 字段**：本机没有 Piper 数字孪生（D 实测 `mani_skill` 内 `*piper*`/`*agilex*` **0 命中**），
  仿真用的是 **SO-100** ⇒ 数据与结论都要标 `morphology_proxy: "so100"`，**不得**写成 Piper 上成立（裁定 40.3）。
- **`is_move` 疑点照旧**：D 在 `ABC130k` 一条 episode 上实测 `is_move` 全 0 而 `frame_validity.is_valid` 全 1；
  你自己造数据时**必须显式定义 `is_move` 的语义并真的填**（否则 QC 过了也没意义）——这条写成你数据 schema 的一条牙。

---

# §10 增补（2026-09-29 17:3x，D，裁定 41）：**iflytek 关闭**；**ABC130k 身份已确证 = YAM（不是 Piper）**；反向示范缺口有了现成解；**新增任务 6**

用户补充：整体真机平台 = **松灵分体式 ALOHA 具身遥操平台 Cobot Magic**（多臂），被控臂 = **Piper**；
**iflytek 被公司拦截 ⇒ 直接关掉**；数据采样来源用户不确定，**交 D 对照判断**（已判，见 §10.2）。

## 10.1 任务 5 修正：**iflytek 补测项删除**

用户裁定"被公司拦截，不要用，直接关掉"。⇒ §9.1 第 4 条（"等用户给出正确 base_url 后补测"）**作废**：
- **观察模型固定 = dashscope / `qwen3.8-max`**（D 实测：文本 200/1.2 s、视觉通过）。
- **不要再打 iflytek 端点**（WAF 明写"相关行为已记录"）。
- **复活条件**（写进你的报告，别让它变成永久沉默）：用户给出未被拦截的端点/base host ⇒ 用 D 的同一探针补测，**追加为新产物不覆写**。
- 任务 5 的其余部分**不变且更重要**：校准集、**判定一致率与纠正可用率必须分开**、`intended_primary_observer`(GPT-6) 与
  `actual_provider_model_id`(实测值) **不许混写**。

## 10.2 任务 2 的数据源**改判**：ABC130k 不是 Piper 采的，但它**恰好解掉了你最硬的那个缺口**

**D 的对照判断（用户交办）**：本机 `ABC130k` = HuggingFace **`xdof/ABC-130k`**（`amazon-far/abc`，`license: apache-2.0`），
README 的 Dataset Statistics 明写 **Robot = "Bimanual station, 2x 6-DoF YAM arms, parallel-jaw grippers"**，
`docs/YAM_DATA_FORMAT.md:7` 同证 ⇒ **机器人是 YAM，不是 Piper，也不是 Cobot Magic**。
**原始数据在本机**：`/workspace/mnt/sppro/yhzhang91/yfw_input/0730/XDOF_ABC-130k/data/{train,val}/`
（train **129,032** episodes / **3,541.1 h** / 197 任务，annotated 42,980 = 33.3%）。

**为什么它仍然极有用**：YAM 站与 Cobot Magic **动作空间同构**——都是 **14 维 = 2×(6 关节 + 1 夹爪)**、平行夹爪、
top + 2 wrist 相机、640×480、**30 Hz**（D 实测 29.76 fps，团队 QC 的合格区间 [29.0,31.0] 印证）。
⇒ **可作 P1「同一 θ 双目标 BC」的离线形态代理**，产物必须标 **`morphology_proxy="yam"`**。
⇒ **但不得当作 Piper 的动作契约来源**：关节零位/限位/连杆/夹爪行程都不同（契约表第三列归 A2，取不到留 `null`）。

**头号发现（这是你任务 2 的新第一优先）：数据集里有天然的正反任务对**，同一动作空间、同一 station：

| 正向 | 条数 | 反向 | 条数 |
|---|---|---|---|
| `put_the_credit_cards_into_the_card_holder` | 2574 | `take_the_credit_cards_out_of_the_card_holder` | 2732 |
| `put_the_keys_on_the_keyring` | 2805 | `remove_the_keys_from_the_keyring` | 745 |
| `put_the_photo_into_the_frame` | 898 | `take_the_photo_out_of_the_frame` | 257 |
| `put_the_phone_into_the_phone_case` | 584 | `take_the_phone_out_of_the_phone_case` | 734 |
| `put_the_pillow_into_the_pillowcase` | 538 | `remove_the_pillowcase_from_the_pillow` | 664 |

（搬运/分拣类单向大盘：`put_the_plastic_bottles_in_the_bin` 3793、`sort_the_legos_into_containers_by_color` 4458、
`sort_the_stationery_into_containers` 2079、`place_and_organize_*_onto_the_shelf` 70~434 各。）

⇒ **本仓"反向示范 0 行"（`lift_B_to_A` teacher 0 行，A 线已量化成 0.0028/0.966 两个数）这个最硬缺口，现在可以用离线正反对立刻补上。**
**任务 2 的优先级因此调整为**：**(a) ABC-130k 离线正反对（第一优先，量大、真实、同构）** →
(b) 仿真双向 teacher（第二优先，形态更接近 Piper 但量小）→ (c) 实机 Cobot Magic 遥操作采集（正规源，窗口由用户定，见 §10.4）。
**口径纪律**：(a) 只能支撑「**同一 θ 对目标有条件依赖**」（T17）与 BC 冷启动，**不得**声称"Piper 上的双向能力"；
引用时**必须同时给出 `morphology_proxy="yam"` 与所用任务对的条数**。

## 10.3 用之前必须处理的两处实测缺陷（别踩）

1. **缺 top 相机**：D 抽查 4/4 个 `workplace/ABC130k` 的 episode，**只有 `left-wrist-camera.mp4` 与 `right-wrist-camera.mp4`，没有 `top-camera.mp4`**；
   而 `docs/YAM_DATA_FORMAT.md` 明写原始 station **有固定 top 相机** ⇒ **这是转换/配置缺口，不是源缺口，可从原始 mcap 重转补回**。
   **你要做的**：先定相机方案（补 top，还是先用双腕两路），并在数据 schema 里显式声明；
   **π₀.₅ 是多相机模型，少一路要说明怎么补（占位/复制/改配置），不许静默。**
2. **团队 QC 对 val 的 847 条 100% 报 badcase**（`workplace/ABC130k/result/robot_clean_20260817/report.md`）：
   `A` 字段缺失(intrinsic) **847**、`N/O/V09/V10` subtask 空 **847**、`J/V04` fps 不在 [29,31] **27**、`C03` 连续帧跳变 **11**、`I` 异常静止 **1**。
   **注意 D 的一条更正**：`converted_metadata_normal.json` 里的 `intrinsics` **是一个 3×3 矩阵**（fx 431.88 / fy 431.38 / cx 324.26 / cy 240.97），
   **不是三组相机内参**（D 上一轮误读，现更正）⇒ 规则 `A` 报的"字段缺失: intrinsic"很可能是**字段名/结构不匹配**，不是数据真的没有内参。
   **你要做的**：定位规则 `A` 期望的字段名，给出"是数据缺还是 schema 不匹配"的结论；**只报观测，不改团队管线代码**。
3. **体积纪律**：该数据集 README 标 `size_categories: n>1T`，train 3,541 h ⇒ **只许按需取子集**（按任务对取若干 episode），
   **不许整集拷贝或整集转换**（NFS 已用 94%）；取了多少条、多少 GB 要在报告里写清。

## 10.4 **新增任务 6（P1 前置，产出草案交 D 裁）**：实机 Cobot Magic 遥操作采集协议

理由：Cobot Magic 是 **leader–follower 遥操平台** ⇒ v4 `:5` 假设的「已有遥操作与少量示范采集能力」**成立**；
用户已说"实机数据后续会采集"。**采集窗口一旦打开，protocol 没定就会采回不能用的数据**，所以**现在就写**。
草案至少要定这 9 项（每项给"建议值 + 依据 + 未定项"）：
1. **动作空间**：14 维（2×(6 关节 + 1 夹爪)）；关节还是末端位姿；**commanded 与 observed 是否都录**（ABC-130k 是分开录的，建议照做）。
2. **频率**：30 Hz（对齐团队 QC 的 [29,31] 合格区间）；若 Piper 实际控制频率不同，**以实测为准并说明重采样方案**。
3. **相机**：top + 左腕 + 右腕；分辨率/内参/时间戳同步方式；**是否录标定**。
4. **任务与正反对**：首场景 = 同一物体在 A/B 两区之间搬运；**正反两向各采多少条**（v4 只要求"少量示范"，给一个可辩护的数）。
5. **初始分布**：物体位置/朝向的采样范围（`forward_init_set` / `reverse_init_set`，参数表里现在是 `null`）。
6. **成功/失败/未知判据**：与环境真值同构（参照 `SO100GraspCube-v1` 的 `is_grasped`/`cube_lifted`/`reached_rest_qpos`/`touching_table` 四条轴）。
7. **数据格式**：mcap（对齐团队流水线，可直接过 `vla_pipeline` 的 validate→clean→qc）还是 lerobot 数据集格式；**二选一给理由**。
8. **干预/接管记录**：遥操作里的失败与重试怎么标（v4 §6.2 的纠正要能进学习闭环）。
9. **另一臂状态**：v4 `:5` 说"另一臂暂不参与"⇒ 它是保持位形、零力矩、还是入观测？**必须写明**（参数表 `inactive_arm_state` 现在是 null）。
**边界**：这是**草案**，交 D 裁后再给用户；**不许假设实机可用时间，不许承诺成功率或采集时长**（`:355`）。

---

## 11. 追加（19:5x，D）：渲染口径已定对你的四项影响 + 一个**新发现的频率冲突**

**用户指令**：「尽量在渲染下跑验证」＋「**先只渲染单臂，不要弄双臂渲染**」。D 已完成基础验证，产物在 `runs/vla/d_render_probe_20260929/`，裁定 42–44 全文见 `supervisor_memo_20260929.md` 增补十九 §72–§75。

### 11.1 **新发现（P0，请纳入你的判据线）：控制频率与示范数据频率不一致**

- **示范数据侧实测 = 30 Hz**（参数表 `timing.control_hz`：4749 帧 ÷ 159.58 s = **29.76 fps**；团队 QC 规则 J/V04 的合格区间 **[29.0, 31.0]**，847 条中 27 条越界）。
- **D 的渲染基准用的是 31.25 Hz**（物理 500 Hz ÷ decimation 16）——这是 D 为了整数 decimation 取的 convenient 值，**不是契约值**。
- **风险**：若仿真控制频率与示范频率不一致，**策略 action chunk 的时间尺度就和训练数据不一致**（同样的 chunk 长度覆盖不同真实时长），SFT 后动作会整体偏快或偏慢，且这种偏差**不会在任何单点检查里报错**，只会表现为"接近了但抓不准"。
- **裁定口径（写给 A2 执行、写给你判据）**：**仿真控制频率必须锚定 30 Hz**。实现建议：物理 `timestep=1/480`（480 Hz）+ **decimation=16 ⇒ 恰好 30.0 Hz**（吞吐与 500 Hz/16 基本相同，渲染开销占比 >99%，改 timestep 不影响渲染成本）。
  **若目标 VLA 的原生控制频率不是 30 Hz**（π₀.₅ / ALOHA 生态常见 **50 Hz**）⇒ **必须显式声明重采样方案**（是重采样示范到 50 Hz，还是把 chunk 按 30/50 缩放），**报 D 裁，不许静默选一个**。
- **给你的牙**：建议新增一条判据 —— 产物里出现「控制频率」字段时，**必须同时给出 (a) 仿真 decimation 与 timestep、(b) 折算后的 Hz、(c) 与示范数据 30 Hz 的关系（相等 / 重采样方案）**；缺任一项判**黄**，折算值与声明值不符判**红**。

### 11.2 任务 6（采集协议草案）的**动作空间**项，现在有实测支撑了

你写第 1 项时可以直接引用（都是 D 实测，出处 `runs/vla/d_piper_assets_20260929/piper_import_smoke.json`）：
- **模型级 8 DOF/臂**（MuJoCo `nq=nv=nu=8`，8 个 position 执行器，kp 10000/2000/500/200…）；**指令级 7/臂** ⇒ 双臂**模型级 16、指令级 14（ALOHA 相容）**。
- **夹爪是 `joint7`/`joint8` 两个独立 slide 关节**，官方模型**无 `<equality>`**、URDF **无 `mimic`** ⇒ **两指不自动联动**。协议里必须写明**采集时夹爪是记 1 维（指令级，两指耦合后）还是 2 维（模型级）**——这直接决定 schema 是 14 还是 16。
- **夹爪行程三套值：URDF 50 mm / MJ joint 35 mm / MJ ctrl 47.5 mm** ⇒ 协议里**行程与归一化方式写"待实机校准"，不许选定一个**；参照数据（YAM）的夹爪是**归一化 [0,1]**（实测 0~0.998）。
- **跨形态禁令**：**YAM J3 实测为正值区间 31.6~104.5 度，Piper J3 的 MJ 限位是 −2.967~0 弧度（全负）** ⇒ 协议里的关节零位/符号约定**必须按 Piper 实机写**，不得沿用 YAM 参照数值（承接裁定 41.2 / 43.4）。

### 11.3 任务 6 的**相机**项

- **官方 Piper MuJoCo 模型 `ncam=0`**（一个相机都没有）⇒ 仿真侧相机全由使用方注入；协议里的相机布局**必须按实机 Cobot Magic 写**，不能从仿真模型反推。
- **参照布局**（ABC-130k / YAM 双臂站）：**top 1 + 左右腕各 1**；RealSense 站 640×480 mono top + H.264，ZED-X 站 stereo top + H.265；参照内参 **fx=431.88 fy=431.38 cx=324.26 cy=240.97 @640×480**。
- **一条反直觉的实测结论，请写进协议理由**：**分辨率不是算力杠杆**（受控 27 次独立进程：112²/224²/480×640 的每帧耗时**无单调关系**，高分辨率反而更快，机制未定）⇒ **不许以"省算力"为由在采集协议里压低分辨率**。分辨率的选择理由只能是**与目标 VLA 的输入规格和实机相机一致**。

### 11.4 任务 6 的**另一臂状态**项（第 9 项）

**双臂渲染已按用户指令停用** ⇒ 当前首场景是**单臂**，但**这不免除你写第 9 项的义务**：`inactive_arm_state` 在参数表里仍是 `null`，而它**影响数据 schema**（另一臂的关节是否入观测、是否占 action 维度）。协议草案里请给出**候选与各自对 schema 的影响**，由用户/D 裁定，**不要替用户选定**。

### 11.5 你的**评测排产口径**要按这套数字算（不要自己另估）

- **像素档评测可行**：单臂 3 相机 224² = **12.88 控制步/秒**（0.41× 实时），10 秒回合 = **24.3 秒墙钟**。
- **并行度硬上限 = 4 个渲染进程**：4 进程效率 **0.98**（`nr_throttled_delta=71`）；8 进程效率 **0.54**（`nr_throttled_delta=407`）⇒ **4→8 只 +9% 吞吐、节流涨 5.7×**。
- **吞吐估算**：4 进程聚合 **50.61 控制步/秒** ⇒ **≈583 回合/小时**，100 回合一轮约 **10 分钟墙钟**。**注意这不含 π₀.₅ 推理延迟（仍是 null）**，A2 回填后此数须下修。
- **训练/评测双轨**：**训练走 state 档、评测走像素档**（不渲染时物理 **20,415 步/秒**，渲染开销占比 **>99%**）。任何像素档主张**必须同时给出「回合/小时」与「4 进程上限」**，缺一判黄。
- **不许引用的数据**：`arms=2` 的一切吞吐结果（`piper_ctrl_serial.json`、`piper_ctrl_conc4.json`、`piper_render_sweep.json`、`lowpoly_proxy_osmesa.json`、`piper_bench_osmesa.json`）**仅留档**。若你的闸发现有人在判据里引用双臂吞吐 ⇒ 建议直接判**红**。

### 11.6 你的准入闸已被 D 只读复核确认（不用重做）

`mutation_verdict.json`：`all_ok=true`，**37 条变异全 ok、9 条反向、baseline 全绿**；`A1_missing_tooth` 能兜住"第 5 条牙只在自检跑、现场没跑"（ADR-C-014 同型）；**M1 能点名 lerobot 0.4.5 vs 0.4.4 漂移**；`admission_verdict.json` 在 `collect()` 时点对四份交件做**一次性 sha256+mtime 快照**，并**实测到 A2 在闸运行中重写 lock（19:04:54）**⇒ `A2_inputs_stable_during_run` 会显式判黄。**这套设计符合"闸必须有牙"（裁定 27.1 / 39.1），予以确认。**
**下一批交件（D 等你的）**：① 闸对 **A2 兼容目录 `pi05_base_compat_lerobot044`** 的最终判定（A2 删了两个 registry 里不存在的 processor 步骤，裁定 44.2 要求其自证等价，**你的闸应当能识别"删步骤"这类改动**）；② **11.1 的频率牙**是否加进去；③ 任务 6 草案 9 项。

---

## §11 追加（21:0x，D，裁定 53/54/55）：**你的优先级重排 —— S1 示范生成升为全仓第一阻塞；git 代提交仍未落**

**权威文书**：`rl_harness_supervision/d_simchain_e2emin_20260929.md`（218 行）。**与本单冲突处以该文书为准。**

**1. 【最高优先】S1 · 仿真双向示范生成（你现在是这条链的唯一上游）**
- **D 的判断**：E2E-min 的关键路径是 **B1 示范 → B2 stats → B3/B4 → S3 BC → S5 评测 → S6 一次 RL 更新**，而**当前唯一真正卡住全链的就是"仓内没有一集主线示范数据"**（你现有的 `runs/vla/b2_bidir_demo_form_20260929/` 是**形态夹具**：8 干净 + 22 负对，是格式不是数据）。
- **D 已替你实测出的可行通道（用前请自己复核一次）**：`gym_aloha` 0.1.4 **不含任何 expert**（`grep -rn expert site-packages/gym_aloha --include=*.py` **命中 0**，21:0x，命令与时刻同批落）；**但** `tasks/sim_end_effector.py:36`–`:55` 的 `BimanualViperXEndEffectorTask.before_step` 走 **`mocap_pos/mocap_quat` + `unnormalize_puppet_gripper_position`**，且 `assets/bimanual_viperx_end_effector_transfer_cube.xml` **含 2 处 `<equality>`（weld）**（关节空间版 `bimanual_viperx_transfer_cube.xml` **含 0 处**）⇒ **在 EE 空间给"接近→合爪→抬→搬→放"航点序列，weld 负责解算，录到的 `qpos` 就是 14 维关节动作示范，不必自己写 IK**；`env.py:120`–`:124` 支持 `task="end_effector_transfer_cube"`（未注册为 gym id，但可直接构造 `AlohaEnv`）。
- **三个已知障碍（先告知，别踩）**：① `env.py:150`–`:164` 的 `reset()` 只对 `transfer_cube`/`insertion` 播种全局 `BOX_POSE`，**其它 task 直接 `raise ValueError`** ⇒ 需子类覆写 `reset()` 或旁路 `AlohaEnv` 直接用 `dm_control.rl.control.Environment`；② `env.py:139`–`:140` `obs_type="state"` 是 `NotImplementedError` ⇒ **状态档只能用 `pixels_agent_pos` 的 `agent_pos`**；③ `env.py:174`–`:180` `terminated = is_success = (reward == 4)` **只覆盖"右→左"正向** ⇒ **反向（左→右）必须自建判据**，且需含**几何真值 + flick/弹射检出**（v4 `:357`「评分可事后核验」）。
- **频率口径已改判（裁定 53，与你 §10 的数据 QC 直接相关）**：主线仿真 = **29.4118 Hz（`DT=0.034` = 17×0.002）**，**落在你的 QC 合格区间 [29.0, 31.0]**。**原「恰好 30.0 Hz（1/480+decim16）」在 dm_control 下不可实现**（`dm_control/rl/control.py:168`–`:194` 对非整数倍是 `raise ValueError`）。⇒ **示范生成、BC 训练、评测、RL 采样必须同一个实测 Hz**，每集带 `(DT, n_sub_steps, model timestep, shim sha256-12, 实测 Hz)`。
- **出口判据（有牙）**：正/反各 ≥N 集（**N 由你提议、D 裁；建议先 5 集打通格式与 QC，再扩到 50/方向**）；**专家自证成功率必须报告**（含失败原因分类，`proposed` 阈值 <50% 先修专家再扩量）；**3 条变异体**：`DT` 改回 0.02（50 Hz）⇒ 帧率闸必红；反向判据方向写反 ⇒ 必红；喂随机动作当"示范"⇒ 专家自证闸必红。
- **产物**：`runs/vla/b2_sim_demo_bidir_20260930/`（数据集 + `demo_manifest.json` + `qc_report.json` + `mutation_verdict.json`）。**stats 由 C2 造（裁定 52：主线 stats = 与你的示范同源），你只提供数据与闸。**

**2. 【立即】git 代提交仍未落（裁定 49.6）**：D 实测 **HEAD 仍 `e6c661e`**，脏 **48 项（20:31）/ 52 项（21:0x）**，含 D 的 4 份新文书（`d_simchain_e2emin_20260929.md`、`d_handoff_to_e_20260929.md`、备忘增补二十、决定 DR-D48–D51）、A2/C2 的新文档与 11+ 脚本。**提交信息须写明 `runs/` 被 `.gitignore:12` 排除 ⇒ D 的渲染证据（44 文件/388 KB）只在 NFS、不进 git。**

**3. 其余旧账不变**：`V-pi05-1` 按裁定 48.4 重锚（锚 git commit `dcddb970…` + `siglip.check` 返回 True）+ **3 条变异体**；`V-pi05-3` 顶层渠道填 **`mixed`**；A2 兼容目录的判定；**频率闸按裁定 53 改 required 值（29.4118 Hz，不是 30.0）**；任务 6（实机采集协议草案）**降级为触发式延期**（裁定 55.5：触发 = S5 通过 + S6 有方向性证据），**现在不要花工时在它上面**。

**4. 新增（S4 段你的责任）**：`harness/vla_runtime.py`（A2）+ `harness/env_gym_aloha.py`（C2）这一段的**闸与三版本记录**（policy version / stats version / shim version 必须写进每条轨迹）归你；**不许改 `harness/contracts.py`（冻结面）**。

---

## §12 追加（21:3x，D，裁定 57/61）：**S1 更正 —— D 给你的 EE 通道那条"可直接构造"是错的；ABC-130k 产物必须加禁用标记**

**1.【更正，最高优先，先看这条】`task="end_effector_transfer_cube"` 在 gym-aloha 0.1.4 里是死代码**
D 在 §11-1 说「`env.py:120`–`:124` 支持该 task，未注册但可直接构造 `AlohaEnv`」——**错了**。逐字原文：`env.py:120` 是 `elif task_name == "end_effector_transfer_cube":`，**`:121` 紧接着就是 `raise NotImplementedError()`**，`:122`–`:124`（xml_path / Physics / `TransferCubeEndEffectorTask()`）**不可达**；`end_effector_insertion` 同型（`:126`）。**D 真跑复现**：构造即抛 `NotImplementedError`，抛点 `gym_aloha/env.py:121`。
⇒ **正确做法**：**绕开 `AlohaEnv._make_env_task`，在本仓自有代码里直接构造** `control.Environment(mujoco.Physics.from_xml_path(EE_xml), TransferCubeEndEffectorTask(), time_limit=float("inf"), control_timestep=DT)`（= `env.py:122`–`:124` + `:133`–`:135` 本来要做的事，约 5 行），并自行复刻 `_format_raw_obs` 与 `BOX_POSE` 播种（`env.py:150`–`:164` 的 `reset()` 对该 task 仍会 `raise ValueError`）。
**mocap+weld 通道本身仍然有效（这部分 D 逐字核过）**：EE 版 xml `:5`–`:8` 是两条 `<weld body1="mocap_left" body2="vx300s_left/gripper_link" …>` / `mocap_right`；`:15`、`:20` 有 `<body mocap="true" name="mocap_left" pos="0.095 0.50 0.425">` / `mocap_right pos="-0.095 0.50 0.425"`；**关节空间版 xml 里 `mocap` 命中 0**。
**备选**：若 EE 通道实测专家成功率太低，就在**关节空间**自写脚本专家（分阶段 PD 目标位姿 + `sim.py` 的夹爪归一化），**不用 mocap**；**自行评估后报 D，不要两条同时铺**。

**2. 频率口径已定，你的示范生成必须用它（裁定 53/58.2）**：**29.4118 Hz（`DT=0.034`）**，A2 已交付 shim `envs/gym_aloha_shim.py`（`sha256-12 dc14466fcdcf`，`representation_version=gym_aloha_dt0.034_29.4118hz_shim_v1`，`site_packages_modified=false`）⇒ **直接复用，不要自己再写一份**（两份 shim 会让 S1/S3/S5 不同频）。**注意 A2 抓到的坑**：`env.py:7`–`:12` 是 `from gym_aloha.constants import (…, DT, …)` ⇒ **只改 `constants.DT` 会静默保持 50 Hz**，必须两个绑定都改（shim 已做，且带变异实验）。**每集 manifest 必须带 `episode_horizon_s=10.2`（300 步 @29.4118 Hz，裁定 58.3）。**

**3.【渲染提速，直接降低你 S1 的成本】GPU 渲染已解锁（裁定 59）**：`gym_aloha` 480×640 **7.91 → 109.09 steps/s（13.8×）**，图像 `mean 39.892 → 39.869`（语义不变）。**合规用法 = prefix-only + `MUJOCO_GL=egl`**（`LD_LIBRARY_PATH` / `__EGL_VENDOR_LIBRARY_FILENAMES` 指向 `.codex-persist/nvidia-gl-590.48.01/`；**禁止系统写入、禁止 `ldconfig`**；**`osmesa` 即使装了库也永远走 CPU**）。⇒ **等 E 的 `scripts/e_activate_gpu_render.sh`（E3-1）再开大批量像素示范**；**先跑 5 集打通格式与 QC 用 CPU 也够**。GPU 与 A2 训练共卡，**渲染并行度由 E 重测、D 裁，你不要自行开多进程**。

**4.【ABC-130k 产物必须加禁用标记】（裁定 61）**：D 只读复核 `runs/vla/b2_abc130k_pairs_20260929/`（20:44）—— `dataset_card.json` 的 `morphology_proxy="yam"`、源目录 `write_policy="一律只读"`、license 标 `external_unverified`，**这三条做得对**。但该目录里有 **`normalizer_stats.json`** 与 `run1_no_saturation_metric`，而 **ABC-130k(YAM) 的 stats 是主线禁用项**（裁定 43.4/49.1/52：YAM 与 ViperX300 零位/符号不同，**搬 stats = 把饱和换成错配**）。
⇒ **要求**：① 在 `dataset_card.json` 与 `normalizer_stats.json` 顶层各加 **`"not_for_mainline_normalizer": true`** 与 **`"allowed_use": "form_reference_and_qc_metric_only"`**（追加式，留 before 影像 + `sha256-12`）；② 该 stats 若用于任何闸，只能作**"必红"分支的输入**（C2 的 T-C2-1 已立这条牙：**用 YAM stats 喂 ViperX300 ⇒ 红**）；③ **主线 stats 一律等 S1 示范落地后由 C2 从示范数据算**（裁定 52）。

**5. 旧账不变（裁定 49.6 的 git 代提交仍是第一优先）**：D 21:2x 实测 **HEAD 仍 `e6c661e`**，脏项 **55**；新增待提交的有 D 的 5 份文书（`d_simchain_e2emin_20260929.md`、`d_handoff_to_e_20260929.md` 及三份执行单追加）、`envs/gym_aloha_shim.py`、`scripts/a2_hz_shim_verify.py` 等。**注意 `runs/` 被 `.gitignore:12` 排除 ⇒ E 的 GPU 渲染证据（`runs/infra/e_gpu_egl_verify_20260929/`，15 个 JSON）与 D 的渲染证据只在 NFS、不进 git，提交信息里要写明。**
**6. S1 的两个 D 裁项等你提案**：① **N（每方向集数）**——D 建议先 5 集打通格式与 QC、再扩 50/方向，**你给数 + 依据**；② **专家自证成功率阈值**（D 的 `proposed` 是 <50% 先修专家再扩量）+ **反向判据草案**（几何真值 + flick/弹射检出，`reward==4` 只覆盖右→左）。

---

## §13 【22:0x · D 裁定 66 / 67 / 68 —— S1 路线定稿 + probe2/3/4 验收 + 你欠的六项】

> **B6 已销账**：`git log -1` = **`c422659`**（21:2x，你代提交）⇒ D 的等待项 ① 关闭。**但 21:2x 之后又有 23 项脏**（含 D 的 6 份文书追加、C2 的 `harness/queue_td_learner.py` +17/−1 与 `harness/obs_key_coverage.py`、A2/C2/E 的 11 个新脚本）⇒ **本轮结束后请再代提交一次**（提交信息注明 `runs/` 被 `.gitignore:12` 排除，故 E 的渲染证据与 B2 的 probe 产物只在 NFS）。

### 13.1 你的 probe2 / probe3 / probe4 —— **验收通过，且记功两处**

- **方法正确**：probe2 的 `supersedes` 字段明写「`probe.json` 的 `replay_tracking`（映射错误）与 `joint_replay_box_left`（注入被覆盖）」⇒ **自己推翻自己的前一轮结论并留痕**，这是本仓最该有的做法。
- **记功 1**：**probe3 崩了，你把整段 traceback 如实留在 `error` 字段里，没有藏、没有改成"跳过"**。崩溃本身产出了一条**跨线硬事实**（见 §13.4）。
- **记功 2**：probe4 把"右臂不收敛"从**现象**推进到**可判定的三个假设 + 一套解析标定**，并且**左臂已经收敛到 1.3 mm**。这是 S1 从"卡住"到"有明确下一步"的转折点。

### 13.2 【D 的第六次同型自我纠错 —— 你的实测推翻了 D 的推断】

- D 在 `d_simchain_e2emin_20260929.md:100` 写「EE 空间给航点、**weld 解算**、录 `qpos` 即 14 维关节示范」。
- **这是从资产声明（XML 里存在 `<weld>`）推出的行为断言，D 没有实测。**
- **你的 probe2 实测推翻它**：`mocap_right` 阶跃 `[0,-0.05,+0.05]` 后，`vx300s_right/gripper_link` 残差 **step1 0.0872 m → step50 0.1359 m，不收敛反而变大**。
- **处置**：D 的原表述**作废**，升级为纪律 —— **凡"某机制能解算 / 能收敛 / 能自动处理"类主张，入文书前必须实测，或读到求解器的实现原文；只凭资产声明（XML/配置里存在某元素）一律标 `declared_only`，且不得作为路线依据。** 这与本日第五次事故（裁定 64：D 未核 A2 引用的文件身份就接受更正）同根因：**读了声明，没读实现。**

### 13.3 D 实测补充的三条硬事实（`MjModel.from_xml_path` 直读，21:5x，`MUJOCO_GL` 未设）

| 事实 | 关节版 `bimanual_viperx_transfer_cube.xml` | EE 版 `bimanual_viperx_end_effector_transfer_cube.xml` |
|---|---|---|
| `ncam` / 相机名 | **7** | **7**（**完全相同的名字与父体**） |
| 腕部相机 | **`left_wrist` 父 = `vx300s_left/gripper_link`；`right_wrist` 父 = `vx300s_right/gripper_link`** | **同上，也有** |
| `nu` / `neq` | **16 / 0** | **4 / 2**（4 个 actuator 名**全为空串**） |
| `nq` / `nv` | 23 / 22 | 23 / 22（**相同**） |
| `<equality>` / `<weld>` 元素数 | 0 / 0 | **1 个 `<equality>` 含 2 个 `<weld>`** |

- **对你和 A2 的更正**：A2 §2.3 的结论要精确化 —— **不是"模型没有腕部相机"，而是"`AlohaEnv` 的 observation 只把 `top` 交给 agent"**。**两个模型都能直接渲出 3 相机**（`physics.render(camera_id="left_wrist")`），路径就是 A2 的 `scripts/a2_pi05_zeroshot_eval.py:190`、`:249`–`:250`。
- **你和 A2 对 D 的更正成立**：EE 版是 **1 个 `<equality>` 元素含 2 个 `<weld>`**，D 原文"含 2 处 `<equality>`"**不准**；编译后 `neq=2` 与你的 probe3 `constraints.neq=2` 一致。
- **你的 H2 在结构上成立**：EE 版 **`nu=4` 且臂关节无 actuator** ⇒ 整条臂只靠 soft weld 吊着（你实测 `solref=[0.01,1]`、`solimp=[0.25,0.25,0.001,0.5,2]`）。

### 13.4 probe3 的崩溃升为一条硬事实（**跨线相关，直接改变你的采集方式**）

```
gym_aloha/tasks/sim_end_effector.py:120
  obs["images"]["top"] = physics.render(height=480, width=640, camera_id="top")
```
⇒ **`get_observation` 无条件渲染** ⇒ **EE 通道在 `MUJOCO_GL=disable` 下不可用，必须有可用 GL 后端。**

**这正是 E 线解锁 egl 的直接下游收益，你现在就能用**（裁定 67 已采纳 E 的数字）：

| 口径 | osmesa | **egl_nvidia（prefix-only）** | 加速 |
|---|---|---|---|
| **gym-aloha 双臂 3cam 224²** | 14.01 ctrl-steps/s | **165.65** | **11.82×** |
| 换算成 300 步/集 | **21.4 s/集** | **1.81 s/集** | 20 集：**7.1 min → 36 s** |

- **激活方式必须是 prefix-only**（裁定 59.4）：`LD_LIBRARY_PATH` + `__EGL_VENDOR_LIBRARY_FILENAMES` 指向 `/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist/egl-libs/590.48.01`。**禁止任何系统写入（含 `ldconfig`）**。E 正在做 `scripts/e_activate_gpu_render.sh`；**在它落地前你可以照 E 的 `runs/infra/e_egl_probe_20260929/MANIFEST.json → prefix` 自己 export，但要在产物里记 `boundary="prefix-only"` 并自证 `forbidden_paths_present=[]`（E 的 `boundary_guard` 是现成范例）。**
- **因为要渲染 ⇒ 你要遵守 GPU 申报纪律**：单卡优先权 **A2 > C2 > E**，你（B2）在这三条之后；**>10 min 占用必须事前在 `daily_report.md` 申报**（预计时长 / 显存 / 可否 kill），跑完销账。按上表，20 集只需 ~36 s，**大概率不触发申报门槛，但先导 5 集 + 调试请自己算一下墙钟**。

### 13.5 【S1 路线裁定 —— 定稿，不再改】

**采纳：EE 模型只作 IK oracle → 录 `qpos` → 在关节模型（`AlohaTransferCube-v0`，`nu=16`）里用它自己的 actuator 重放，并在关节模型里采 3 相机图像与 14 维动作。**

**不允许"在 EE 模型内直接采示范"**。理由（这是本轮最重要的一条口径）：EE 模型的重力下垂 + soft-weld 滞后与关节模型的 actuator 动力学**不是同一套动力学**，而 **S5 评测必然在关节模型里跑** ⇒ 在 EE 模型内采的示范会带**训练/评测动力学错配**，正是附录一 `:346`（T26：同形状但 normalizer／n／rubric 版本冲突）与 D 的口径搬运禁令所禁的那类问题。**你 probe2 已经在做 mapping + replay，方向正确，继续。**

### 13.6 右臂发散：D 的假设（**标 `d_inference_not_measured`，你去实测判定，不需要再问 D**）

你的 probe4 实测：**左臂残差收敛到 `0.0013 m`（1.3 mm，<3 mm 判据绿）；右臂发散到 `0.2469 m`、姿态残差 `2.376 rad`**。而 `weld_rows` 显示**两侧 weld 不是同构镜像**：

| 侧 | `relpose_quat_wxyz_raw` | `anchor2_body2_frame` |
|---|---|---|
| 左 | **`[1, 0, 0, 0]`（单位四元数）** | `[-0.134706, 0, 0.00205]` |
| 右 | **`[-3.67e-06, 0, 0, 0.99875]`（w≈0, z≈1 ⇒ 绕 z 轴 180°）** | `[+0.134706, -3.15e-06, 0.00205]`（**x 反号**） |

- **假设 D-H1**：`calibration_analytic` 对右臂沿用了左臂的**单位 `qrel`** 公式，**未逐侧复合 `qrel`** ⇒ 反解出的 mocap 姿态差了约 180°，soft weld 因此产生一个把臂甩开的力矩（与你实测"位置残差 `0.2469` > 锚点偏置 `0.13472`"一致：多出来的位移是姿态力矩拖出来的，不是纯偏置）。
- **判据（能红）**：按**逐侧 `qrel` 复合**后，右臂位置残差应降到与左臂同量级（**<3 mm**）。**若仍 >3 mm ⇒ D-H1 被否**，转你的 H2（无 actuator 稳态下垂）/ H3（不可达、限位、奇异）继续判，**并把 D-H1 的否证结果写进产物**（D 的推断被否也是要留痕的）。

### 13.7 S1 的四条附加实测要求（数字全部取自你的 probe4，不要另测）

1. **方块必须先沉降**：你实测 seeding `z=0.05` → **12 步后 `z=0.0200`**（自由落 0.03 m）⇒ **示范的第 0 帧必须在沉降之后**，否则前 12 帧教的是"方块凭空下落"。manifest 记 `box_settle_steps=12`、`box_z_seeded=0.05`、`box_z_at_rest=0.0200`。
2. **夹爪标定用你的表，不要另测**：cmd→`finger_spread_m`：`0.0→0.01833`、`0.25→0.02828`、`0.5→0.0465`、`0.75→0.06605`、`1.0→0.08412`；方块宽 **0.04 m** ⇒ **张开取 `cmd≈1.0`（0.084 ≫ 0.04）、闭合取 `cmd≈0.0`（0.0183 < 0.04 ⇒ 接触受限的稳抓）**，**开合阈值 `cmd≈0.45`（spread=0.04）必须写进 manifest**。
3. **存 14 维动作，不存 16 维 `qpos`**（A2 §7 的点名成立）：你实测 `qpos16` 的 `[6],[7]` 与 `[14],[15]` 是 **±同值对**（`+0.02239 / -0.02239`）⇒ **14 维的夹爪位 ↔ qpos 对 `(+v, −v)`**，这个映射**必须写死并进 `representation_version`**。
4. **指尖偏置用你的实测值**：`tip_rel_gripframe = [0.09346, 1.16e-05, 0.00208]` ⇒ 航点→指尖换算照此，**不要用 `gripper_link` 原点当指尖**。

### 13.8 【S1 出口判据 —— D 定稿：任务级，不是残差级】

**N 集（N 由你提案、D 批；D 的先验建议 = 先导 5 集 + 正式 20 集，与 C2 T-C2-1 的 stats 时刻对齐）满足全部五条：**

1. **方块从右侧起始区被搬到左侧目标区并保持** —— **几何真值判定，独立于 `reward==4`**；**两者不一致 ⇒ 红**（与 S4 的 C2 判据同源，别做两套）。
2. **每集带 3 相机 224² 图像 + 14 维动作**（键名走 π₀.₅ 契约：`observation.images.{top,left_wrist,right_wrist}`；**C2 的 obs 键覆盖闸已落地，未声明图像键会被点名拒绝**，见裁定 68）。
3. **每集带 `episode_horizon_s=10.2` + `control_hz=29.4118` + 三件套版本**（policy / stats / shim）。
4. **重放该 14 维动作序列在关节模型里能复现同一结果**（否则示范与执行动力学脱节 —— 这是 §13.5 那条裁定的验收形式）。
5. **反向同理**，且**反向判据必须自建**（`env.py:174`–`:180` 的 `reward==4` 只覆盖右→左）。**反向成功判据草案由你出，D 批。**

### 13.9 你仍欠的六项（本轮未销账，按优先级）

| # | 欠项 | 说明 |
|---|---|---|
| ① | **S1 开工**（§13.5–§13.8） | **全链唯一真阻塞**；右臂按 §13.6 判定后即可动 |
| ② | **N 集数提案 + 反向判据草案 + 专家成功率阈值** | 一次报齐，D 一次批 |
| ③ | **ABC-130k 产物加禁用标记**（裁定 61） | `dataset_card.json` 与 `normalizer_stats.json` 顶层各加 `not_for_mainline_normalizer=true` + `allowed_use="form_reference_and_qc_metric_only"`；追加式 + before 影像 + `sha256-12` |
| ④ | **`V-pi05-1` 重锚** | 改 **commit 判据**（git `dcddb970176382c0fcf4521b0c0e6fc15894dfe0` + `siglip.check`）；`transformers 4.53.3` 的实测事实已由 A2 的 **812/812 张量逐位相同 + 无随机初始化键**支撑 ⇒ **那条声明下界 `>=4.57.1` 标 `declared_only`、不得 blocking**（C2 也提了同一条，D 一并裁：**改判为"记实测值 + 与加载验证结果绑定"**） |
| ⑤ | **`V-pi05-3` 渠道填 `mixed`** | receipt 已有逐文件渠道记录，只按格式闭合，**不必重下** |
| ⑥ | **频率闸 required 改 `29.4118 Hz`** | 裁定 53/57 |
| ⑦ | **git 代提交（本轮结束后）** | 见 §13 开头 |

**新增一条（裁定 68 的连带要求）**：你维护 `registry/`，**C2 的 `c2_gate_obs_key_coverage` 是一把新闸** ⇒ 按 `verdict_identity` 的登记规则处理；**`registry/verdict_identity.py:47` 的 `GATE_MODULE_PATH` 钉死在 ACT 门禁，多门禁并存（ACT 冻结基线 + π₀.₅ 新线）的口径 C2 已报"需 D 裁"⇒ D 现予裁定：`GATE_MODULE_PATH` 改为按 `gate_id` 查表（ACT 基线与 π₀.₅ 新线各一条），不许再钉单值；改动由你做（`registry/` 单写者 = 你），改完跑 `c_selfcheck_verdict_identity` 并附三个变异体（钉死旧值必红 / 查表命中错门禁必红 / 未知 gate_id 必红）。**

---

## §14 【22:2x · 三条更正（裁定 70 / 71 / 73）—— 影响你 S1 的排期与激活方式】

### 14.1 【更正 D 自己 · 裁定 70】渲染前缀目录名 D 写错了

- **D 在 §12-3 与裁定 59.4 写的 `.codex-persist/nvidia-gl-590.48.01/` 不存在**（D 实测 `stat` → `No such file or directory`；A2 与 E 双证人）。
- **正确前缀 = `/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist/egl-libs/590.48.01/`**。
- **但你不要硬编码任何目录名**：**一律走 E 的激活件**（已落盘，D 已核）：
  ```bash
  eval "$(bash scripts/e_activate_gpu_render.sh --print)"
  ```
  这是 A2 本轮的做法，**D 采纳为全仓规范**。你的 S1 采集脚本照此激活，并在产物里落 `activation_env`（含 `prefix_paths_verified` 三条布尔，A2 的 `latency_mainline_egl_gpu.json` 是现成范例）。

### 14.2 【更正 D 自己 · 裁定 71】§13.4 那张成本表**降级**，规划改用保守端

D 在 §13.4 用 E 的 `165.65 ctrl-steps/s` 算了"300 步/集 ≈1.81 s、20 集 ≈36 s"。**这是跨口径搬运**（E 的档位是 **stock `DT=0.02`/10 子步 + 5 s 窗口 + `loadavg 47–50`**，而主线是 **shim `DT=0.034`/17 子步**），**D 自己在同一轮里写下禁令又违反它，已记为第七次同型事故。**

**A2 在主线口径（shim `DT=0.034`、3cam 224²、egl prefix-only、`MUJOCO_GL` + `GL_RENDERER` 双证）下的实测**：

| 负载 | `env_step_fps` | 300 步/集 | **先导 5 集** | **正式 20 集** |
|---|---|---|---|---|
| **`loadavg_1m 67.4→72.0`（本日最忙，`nr_throttled Δ63`）** | **30.522** | 9.83 s | **≈49 s** | **≈3.3 min** |
| **`loadavg_1m 51.4`（`Δ20`）** | **65.865** | 4.55 s | ≈23 s | ≈1.5 min |
| osmesa（同口径 CPU，`loadavg 37.9`） | **9.577** | 31.3 s | ≈2.6 min | **≈10.4 min** |

- **规划一律取最慢的那一档（3.3 min / 20 集）**；**两个负载端都要在你的产物里并列，不许只报好看的。**
- **⇒ 结论不变但更稳**：**20 集在 egl 下 ≈3.3 min，仍在 GPU 10 min 申报门槛以下**；**osmesa 下 ≈10.4 min 会越过门槛 ⇒ 不要用 osmesa 采主线示范。**
- **负载摆动是实测事实**：`loadavg_1m` 在 21:5x–22:1x 一小时内 **37.58 → 71.98**（12 核 cgroup 配额，宿主 112 核与其它租户共享）⇒ **同一口径差 2.16× 已实测**，所以**任何吞吐数字必须成对带 `loadavg` 三点 + `nr_throttled` 增量，单点数字不得当口径**。

### 14.3 【裁定 73 · 新制度】"静默窗口"——你申请 GPU 长作业时要走这个

- **单卡优先权：A2 > C2 > E > B2**（你排最后，因为你的 S1 采集可以按窗口排期，不像 A2 的延迟测量那样怕干扰）。
- **A2 在 22:16 起有一个 `closed_loop --n-action-steps 50,25 --n-episodes 3` 的 GPU 作业持有当前优先权**；**E 的权威标定臂已被令重跑并会申请静默窗口**。
- **⇒ 你的 S1 采集开工前，先看 `daily_report.md` 有没有生效中的静默窗口**；**若有，等窗口结束**；**若你要连续跑 >10 min GPU，自己也申请一个窗口**（格式照 A2 的 22:0x 申报：做什么 / 激活方式 / 预算时长 / 显存峰值 / 可否 kill / 起点 `nvidia-smi` 读数 / `nr_throttled` 与 `loadavg` 起点）。
- **跑完必须销账**：`nvidia-smi` 回到 **0 MiB / 无进程**，并把读数写进产物。

### 14.4 你的欠项清单更新（替换 §13.9）

- **⑦ `V-pi05-3` 顶层渠道 → 撤下**：A2 已用 `runs/vla/a2_env_pi05_sim_20260929/weights_receipt_channel_sidecar.json` 闭合（`channel_top_level="mixed"`、C1–C5 绿、自检 3/3、receipt `sha256-12 11267d5b…` 未变）⇒ **你只需在闸里引用这份 sidecar，不必自己再填。**
- **④ `V-pi05-1` 重锚 → 依据已备齐**：A2 的 `env_manifest.json`（**10/10、`env_usable=true`**，20:50:14，负载对 `loadavg 47.25/49.20/50.67`）+ V10 六条检查 + `--selftest` **6/6 变异体被抓**；卫语句原文（A2 用 `inspect.getsource` 取的，**读实现不读声明**）= `return __version__ == "4.53.2" or __version__ == "4.53.3"`。**并且 A2 点名你：你那次吃的是假红 run2 快照，必须用新 manifest 重过闸。**
- **新增 ⑧（裁定 72-2 的连带）**：你的闸要能判 **`late_policy=hold` 下迟到帧被重标为 `activated`** 这件事**红**（附录一 `:111`「异常事实保留，不重标成"准时"」）。
- **新增 ⑨（裁定 73）**：你的闸聚合器（`gate_build` / `verdict_identity`）在读别的线的 `gates_all_ok` 时，**必须能区分 `ok=false` 与 `n_a`** —— A2 的 run1 就是因为一道**不适用的闸**（`retro_label_valid` 在 GPU 臂必然红）而整体 `gates_all_ok=false`。**若你的聚合器把 `n_a` 当红，会持续产生假红。**
- **①②③⑤⑥ 不变**（S1 开工 / N 集数与反向判据与专家阈值 / ABC-130k 禁用标记 / `GATE_MODULE_PATH` 改查表 / 频率闸 required 改 29.4118 Hz / git 代提交）。

---

## §15 D 执行单（2026-09-29 23:0x）｜裁定 80：**你的双向专家 80/80 已解锁主线**；D 更正自己的裁定 66

### 15-1 先说两件对你有利的事

**① 你的 probe4 独立证实了 D 的 D-H1 假设。** D 在裁定 66 里把右臂问题标成假设 `D-H1`（`d_inference_not_measured`）：weld 非镜像同构、右臂 `qrel≈[~0,0,0,~1]` = **180° 绕 z**、`anchor2` x 符号相反 **±0.134706**。你的实测完全对上：`assets/vx300s_right.xml:3` 的 `euler="0 0 3.1416"` ⇒ **右臂基座绕 z 装反 180°**；`eq_data[3:6]` 的 `anchor2=±0.134706 m`（左右镜像）+ 上游 `initialize_robots` 把 mocap 设成等于复位后 `gripper_link` 位姿 ⇒ **复位瞬间即违反 0.1347 m** ⇒ 第一步臂被猛拉 13.5 cm（≈4 m/s）；反解「一致 mocap」后**左臂零瞬变成立（30 步残差 ≤1.3 mm）、右臂不成立（残差 0.247 m、姿态偏 2.376 rad）**。**D-H1 判定为「证实」。**

**② 你的路线比 D 的裁定 66 更好 ⇒ D 更正自己的原判。** 裁定 66 要求「EE 模型只做 IK oracle → 记录 qpos → 到关节模型 replay + 采集」。你实际做的是：**完全不用 EE 模型、不用 weld**，在**部署 env（关节模型）自己的 `MjData`** 上用**雅可比阻尼最小二乘 IK 做 plan-then-replay**。这**更好地满足了裁定 66 的意图**（绝不在 EE 模型采集、训练/评测动力学一致），而且**少一层机器**（不需 EE 模型、不需 weld 标定、不需跨模型 qpos 搬运）。
⇒ **裁定 66 的「EE oracle」步骤作废。** 其余全部继续有效：不在 EE 模型采集、几何真值判据独立于 `reward==4`、horizon+版本三元组、replay 可复现、反向自建、**N = pilot 5 + formal 20（每方向）**。
⇒ **你那条教训被 D 采纳为全线纪律 `actuator_dynamics_before_control_law`**：第一版「每控制步一次闭环 IK」实测失败（正向 0/2），因为关节 env 是 **position actuator（kp 800/1600）**，逐步 `q+dq` 被执行器滞后吃掉；改 plan-then-replay 后**滞后只影响跟踪误差、不影响路径长度**。规定：在 position/velocity actuator 的 env 里设计控制器前**必须先读执行器增益与滞后**，不得假设「下发即到达」。（你脚本里那条「第一版写 0.15 ⇒ 越界、carry/place_lower 相位 IK 不收敛」归入同一纪律。）

### 15-2 D 的独立复核结果（不采信 `summary`，逐行统计）

`runs/vla/b2_sim_demo_bidir_20260930/probe/expert_selfverify_40x2.json`（22:23:02）：`--direction both --n-seeds 40 --seed0 5000` ⇒ **forward 40 + reverse 40 = 80 行**；`verdict=success` **80/80**、`env_reward4=True` **80/80**、`on_goal_side_diag=True` **80/80**、`hz` 全 = **29.411765**、`failure_class=None` 80/80、`n_plan_nonconverged=0` 80/80、`timeouts` 全空、`budget_exceeded=None` 80/80。forward `n_steps` 中位 **273.5** / `displacement_m` 中位 **0.1769** / `max_held` 最小 **31**；reverse **274.0 / 0.1799 / 31**。⇒ **与 `summary={success:80,failure:0,unknown:0,total:80}` 一致，D 接受。**
**判据形态合规**：几何真值（终态被目标侧夹爪握住 + 离桌 + 低速 + 连续持稳 ≥ 阈值 + 水平位移 ≥0.05 m）与 `env_reward4` **交叉核验一致** ⇒ 满足裁定 66「几何真值独立于 `reward==4`」。`max_box_speed_phase=settle`（最大速度出现在 settle 相位而非搬运相位）⇒ **反 flick 的牙在起作用**。

### 15-3 **但这是自验（`--selftest`），不是 S1 正式采集。正式采集前必须补齐 5 项（裁定 80.3）**

**① 渲染与渲染器身份（最重要）**
你的脚本 `:53-54` 是 `if "MUJOCO_GL" not in os.environ: os.environ["MUJOCO_GL"]="disable"` ⇒ **80/80 是无渲染的纯状态自验**。正式采集要出 **3 cam 224²** 像素，必须：
- 按**裁定 72** 落**渲染器身份证据**：`GL_VENDOR / GL_RENDERER / GL_VERSION` **三串** + `renderer_class` + `identity_source`；且**自检必须真的调用采集函数**（不能喂理想字符串 —— 裁定 72 `selftest_must_execute_acquisition_path`）。
- 后端按**裁定 77.3** = **`MUJOCO_GL=egl` + prefix-only NVIDIA vendor**；`osmesa` 只作对照/退路。
- 激活**一律** `eval "$(bash scripts/e_activate_gpu_render.sh --print)"`，**不得硬编码 prefix 路径**（裁定 70/77.6）。**权威 prefix = `.codex-persist/egl-libs/590.48.01/`**（旧名 `nvidia-gl-590.48.01/` **已作废、不存在**）。
- ⚠ **不得再用 `scripts/check_gpu_render.py` 当「能不能 GPU 渲染」的闸**（裁定 77.9：它的 `gpu_render_possible` 是静态启发式，prefix-only 下**仍返回 False**，属 `known_false_negative_under_prefix_only`）。

**② 负载对缺失（本仓硬约束）**
产物有 `wall_s`（0.288 s/局、40 局合计 11.98 s）但**没有 `loadavg`(3 点) + `nr_throttled` 对** ⇒ **任何由 `wall_s` 推出的产能/排期数字（如「回合/小时」）在补齐前一律 `declared_only`，不得进参数表、不得用于排期。** 正式采集产物必须每局或每批带负载对。

**③ 五元组 + 版本三元组**
产物需带 `(venv, backend, mujoco 版本, 模型 XML, DT)` + `env_id` + `morphology` + shim sha + 模块 sha。**你的脚本正在编辑**（D 读取时 1127 ln / sha `25ffe837896a`；22:53:16 已 1162 ln / 64655 B / sha `952437930706`）⇒ 正式采集产物必须记录**当时**的脚本 sha 与 `as_of` mtime（**裁定 78.11 新纪律 `citation_sha_as_of_discipline`**：引用自己写入面内、仍在编辑的文件时，sha 必须在**落笔时刻重读**，不得沿用早先 run 的值）。
- **建议直接复用 C2 的 env 判定层**：`harness/env_gym_aloha.py`（579 ln，sha **`6c4d71eb732e`**）+ 闸 `scripts/c2_gate_env_gym_aloha.py`（sha `c9100b3811cd`）。**D 已亲自复跑 offline 档**（22:52:32）：`verdict=PASS`、`n_checks=15`、`red=[]`；在线档 `n_checks=13`、`n_red=0`、`with_render=true`。它的 `MODULE_REPRESENTATION_VERSION="c2-env-gym-aloha-v1"`（`:79`）、manifest 带 `module_sha256_12` + shim sha（`:500-508`）⇒ **直接满足裁定 66 的 horizon+版本三元组**。**不要自己再造一套判定层**（会与 C2 的 J1–J15 分叉）。

**④ 规模**：按裁定 66 = **pilot 5 + formal 20（每方向）**。**80/80 是自验规模，不得当作 formal 20 的替代。**

**⑤ replay 可复现**：同一 seed 重跑必须**逐位一致**（裁定 66 出口第 4 条）。

### 15-4 **git 代提交（裁定 81.2，请在开始 S1 pilot 之前先做）**

HEAD 仍 `c422659`（21:2x 快照），**脏项已从 ~23 增至 `39`**（D 22:44 实测）。新增含：A2 的 `scripts/a2_egl_latency_remeasure.py`（`b544f3741665`）+ `docs/a2_s4_vla_runtime_interface_20260929.md`（451 ln）；E 的 `docs/e_handoff_to_d_20260929.md`（269 ln）/`docs/e_egl_feasibility_20260929.md`（338 ln）/`docs/infra-gpu-render.md`（327 ln）/`scripts/e_mainline_render_calib.py`（`72a3f98e0c8f`）；C2 的 `docs/c2_gate_polarity_audit_20260929.md`（260 ln）/`harness/env_gym_aloha.py`（`6c4d71eb732e`）/`scripts/c2_gate_env_gym_aloha.py`/`c2_driver_output_guard.py`（`e6e3b2c2ad30`）/`c2_run_c_regression_postpatch.sh`（`3ba62c9567e9`）/`c2_probe_obs_key_drop.py`/`c2_gate_obs_key_coverage.py`；你的 `scripts/b2_s1_scripted_expert.py` + `b2_s1_probe*.py`。
- **提交信息须点名裁定 75–81 与各线新增文件。**（裁定 49.6：git 单写者 = B2；**D 从不提交**。）
- ⚠ **`runs/` 被 `.gitignore:12` 排除 ⇒ 全部实测证据只在 NFS、不在 git。服务器重启后 NFS 是唯一证据载体 ⇒ NFS 路径不得改动。**

### 15-5 裁定 78 落到你身上的 5 件（准入闸与委托闸）

1. **`V-pi05-1` 的 RED 必须按裁定 69 + 78.8 改判后清除。** C2 独立读码证实：真卫语句是 `modeling_pi05.py:576-584` 的 siglip `check_whether_transformers_replace_is_installed_correctly()`，**不是版本区间**；A2 的 `transformers 4.53.3` 是 git 构建（commit `dcddb970…`、branch `fix/lerobot_openpi`），其 `check.py` **只接受 4.53.2 / 4.53.3** ⇒ **装 `>=4.57.1` 会让 π₀.₅ 直接加载失败**。故 `extra` 声明下界 `>=4.57.1` 属 **`declared_only`、不得 blocking**；`required` 改为「实测 `4.53.3` + commit `dcddb970…` + **卫语句真跑通过** + `all_bitwise_equal`（812/812）」。**这是第二重证据（D 裁定 + C2 独立读码带 file:line），不得再以声明下界判红。**
2. **`V-pi05-3` 渠道混用（`['hf_mirror','modelscope']`）判定为 `mixed`、按格式闭合即可，不必重下**（A2 的 receipt 已有逐文件渠道记录，只是顶层 `channel=None`）⇒ 裁定 69 已定，此处确认关闭。
3. **委托闸补 `id`（裁定 78.3，必做）**：`delegated_g1_g5_*` 的 **45 条 check `id=null`**（a2env 4 份 ×5、freeze 5 份 ×5）⇒ D 的执行单无法精确引用到条；任何 `if c["ok"] is True` 的汇总会把 PASS 读成不合格（**假红**）；任何 `if c["status"]=="RED"` 对这两把闸**永远为假**（**恒真**）。补 `id`（如 `G1_freeze`/`G3_a2env`）并让 `ok` 与 `status` **同源**。**附带必修**：`"  G2_rebuild_lockout_not_default[a2env]"` 的 id **带两个前导空格**（三份产物一致）⇒ 精确匹配/去重/建索引都会漏。
4. **`G2` 的 WARN 极性错（裁定 78.5，必修）**：期望**已被满足**（`same_as_0928=false`、`lock_diff` 已逐包枚举）却报 WARN ⇒ 极性/文案反了（D 已独立复核成立）。
5. **`delegated_g1_g5_freeze` 二选一（裁定 78.4）**：5 份产物 / 25 条 check **从未非绿**且**无变异体记录** ⇒ 裁定 27.1「恒真的闸等于没有闸」。① 补 **≥1 个反向变异体/G**（证明能红）后恢复「闸」称谓；② 或接受**降级为「清单核对」**、产物 `kind` 改标 `checklist_not_gate`，下游不得当保护层引用。`delegated_v0_v9`（50/50 全 `ok=true`）标 **`teeth_delegated_to_upstream`**（牙在被转述的 B 门禁 `V3: n_mutations=15 n_caught=15` 上），**不得当独立闸引用**。
6. **最小公共 check schema（裁定 78.2）**：`id / ok / status / required / observed / red_when`；**顶层 `ok` 是唯一失败判据**；**`UNJUDGED` 必须计入非绿**（F1：你的闸曾在 `status` 直方图 `{'PASS':18,'UNJUDGED':5}`、**RED=0** 的情况下 `ok=false` ⇒ 任何按 "RED" grep 的下游会把这次失败读成干净）。产物顶层写 **`n_red / n_warn / n_unjudged / ok`** 四元组。**你的 8 字段 schema（`id/ok/observed/required/note/status/ruling_ref/red_when`）+ 60 变异体（`n_ok=60/n_reverse=18/baseline_all_green=true`）是本仓最完整的一把 ⇒ 以它为基准，只需补 `UNJUDGED` 计入与顶层四元组。**

### 15-6 GPU 与并行（裁定 73 / 76.2）

- **你优先级最低（A2>C2>E>B2）**。S1 正式采集要带渲染 ⇒ **会占 GPU**：**开跑前必须在 daily_report 申报窗口**（>10 min），并按**新纪律 `per_batch_gpu_yield_gate`** 在**每个** GPU 批次开跑前重查 `nvidia-smi --query-compute-apps`，有他线进程即让路（不允许只在任务级查一次）。
- **A2 即将做 quiet-window 权威重测（裁定 76.4）** ⇒ **先与 A2 的窗口错开**。
- 并行上限 **2**（A2/B2/C2 的生产工作）。当前建议顺序：**你先做 15-4 的 git 代提交（不占 GPU）→ 再做 15-3 的 ①②③ 补齐 → 然后 pilot 5**；A2 并行做 S4a 骨架（CPU-only）；C2 等你的正式示范落盘后做 T-C2-1。

---

## §16 D 执行单（2026-09-29 23:4x）｜裁定 82：**跑正式采集之前必须做的三件事**（全文见 `daily_report.md` 23:4x 段 §0–§1 与 `decisions_20260929.md` 裁定 82）

**16-1【最高优先·关键路径】加 `states_14d.npz` + `manifest.json` 导出（裁定 82.2）。** C2 的接口请求已被 D 采纳为 **S1→T-C2-1 的绑定契约**：`frames=[N,14] float64`（按集拼接、集序号升序）、`start_poses=[E,14]`、`physical_range=[14]`（**臂关节读 `jnt_range`、夹爪维 = 1.0**，同 `scripts/c2_collect_env_states.py` 口径）+ `manifest.json`（五元标注 + `control_hz=29.4118` + `episode_horizon_s=10.2`）。**C2 的生成器 `--s1-frames` 直接吃它、不需改代码。** D 实测 `grep -n "states_14d\|np.savez" scripts/b2_s1_generate_dataset.py` ⇒ **0 命中**（脚本 sha `b7e93e65d5f5`、2333 ln、mtime 23:29:14）⇒ **你现在不导出它。若先跑完正式采集再补，就要重跑整轮（pilot 5 + formal 20/方向 × 带渲染）⇒ 关键路径一次完整返工。** 导出**不得改变 LeRobot 数据集本体**（两条出口并存）；在 `demo_manifest.json` 里记 npz 的 sha256-12 + `as_of` mtime。

**16-2 图像存储 = 【甲】（PNG 内嵌 parquet）；【丙】被明确禁止（裁定 82.4）。** 理由：无损（不引入压缩伪影混淆 normalizer stats 与 SFT）+ `fps` 字段诚实（29.4118 Hz 非整数）+ 时间戳精确（S6 的 TD 时序前提依赖）+ 不碰第三方运行时。**丙禁止**：monkeypatch lerobot 编码器 = 改第三方运行时，与裁定 78.7、57.4 及**你自己 `:62` 的硬边界「只读 lerobot site-packages、一个字节都不改」直接冲突**。**乙**（若为 mp4 + 取整 fps）**驳回** = 口径谎言；**若你的乙案不是这个形态，请补原文 D 再裁。** **体积口径**：甲属 **PNG 压缩**族（与 C 线 `147 KB/帧` 同族），**与 C2 的 `np.savez` 未压缩 `1765.19/2701.04 KB/帧` 不同族**（裁定 78.9）⇒ **必须实测登记 PNG 内嵌后的真实 KB/帧与总字节，不得引用上述任何数字代替。**

**16-3 replay 判据已重定范围（裁定 82.5，主线判据变更）。** D 逐 run 复核 E 的 12 个 run 发现：**egl 下 wrist 相机在【没有任何裸探针的干净基线 `no_raw`】里就不逐位可复现**（seed1000 右腕 sha 变、seed1001 双腕都变，而 **mean/std 一致到 3–4 位小数**）；`angle` 始终逐位一致；**osmesa 下三相机全部逐位一致**。⇒ ① **状态量（`qpos`/`states`/动作序列）必须逐位一致 = 硬判据**，**你的 `cmp_states`/`norender_vs_expert`/`recorded_vs_norender`/`verdicts_all_equal`（`:629-640`）已经就是这个形态 ⇒ D 采纳并钉为强制项**；② **像素逐位一致【不得】作为 egl 下的验收判据**（实测不成立，当判据会造成永久假红）；③ 像素改为 **`angle` 必须逐位一致 + 两个 wrist 的 `mean/std` 在登记容差内、且差异像素占比与最大绝对差被实测登记**。**在 E 量化出容差之前（裁定 82.5-2，已指派 E、N≥5），你的 replay 闸按「状态逐位 + `angle` 逐位 + wrist 只登记不判红」运行**，并把 wrist 差异像素占比**如实登记进 `demo_manifest.json`**（不得省略、不得写成 0）。

**16-4 D 对你本轮的三项认定（都是正面）**：① 你的「一处偏离裁定 66 字面路线（EE 模型一个字节都不加载）」= **裁定 80.2 已批准**，且你**自行声明偏离 + 留痕 + 报 D** 而不是静默改路线 ⇒ **「下位纠正 D」通道的标准形态**；你新提供的第三处硬伤（`sim_end_effector.py:120` 无条件渲染 ⇒ `MUJOCO_GL=disable` 下 EE 不可用）D 采纳记入。② **`box_settle_steps=12` 且沉降 12 步不进数据集**（否则前 12 帧教的是「方块凭空下落」）⇒ **比裁定 66 原文更严，D 特别肯定。** ③ **你已自行闭合裁定 80.3 的 ①②③**（`:69` 走激活件且注明裁定 70；`:211` `loadavg3()`；`:303` 注明裁定 72-1 + `:305-330` 完整身份探针）⇒ **判为「已在实现中闭合，待产物落地后由 D 复核」**；`verify_lerobot`（`:879-924`）读回自己写的数据集逐字段核 = 裁定 72 `selftest_must_execute_acquisition_path` 的形态，`:924` 把「lerobot 自己算的 min/max/mean/std」口径归属写清、不与 C2 的 stats 混淆 ⇒ **正确**。

**16-5 git 代提交仍欠（裁定 81.2）**：脏项 23:35 实测 **49**（21:2x 时 ~23）。**请在开始 pilot 之前提交**，信息点名裁定 75–82。⚠ **`runs/` 被 `.gitignore:12` 排除 ⇒ 全部实测证据只在 NFS；服务器重启后 NFS 是唯一证据载体 ⇒ NFS 路径不得改动。**

---

## §17 D 执行单（2026-09-30 00:0x）｜裁定 83：**D 先更正自己对你的误判** · 甲已验收 · **`states_14d` 仍是关键路径唯一卡点（附降阶方案）**

**权威全文**：`work/decisions/decisions_20260929.md` 裁定 83（1504→**1672** ln，`9d42c1559058`）；`daily_report.md` 00:0x 段（5019→**5131** ln，`17442f41e6b8`）。

### 17-1 D 更正自己的误判（**不问责你**）

D 于 23:43 用被 `head` 截断的 `ls -ltR` 看到 `runs/vla/b2_sim_demo_bidir_20260930/selftest/team_form/data/train/transfer_cube_right_to_left/episode_bd6e73ce-.../` 为**空目录**，一度拟据此问责「留空目录当已做过」。**D 于 00:0x 用 `find -type f | wc -l` 复核 ⇒ 实为 17 个文件已落地**（写入正在进行中 + D 的列表被截断）。**⇒ D 不问责，撤回该疑点。**

D 据此新立自查项 **`absence_claim_requires_exhaustive_enumeration`**：D 在把「缺失 / 为空 / 没有」写进裁定前，必须用穷举计数（`find -type f | wc -l`、`grep -c`）复核，**不得依据被 `head`/`tail` 截断的列表**。（与红线 `regression_driver_output_enumeration` 同族。）

### 17-2 甲（PNG inline parquet）**验收通过**

实测 `runs/vla/b2_sim_demo_bidir_20260930/selftest/pi05_lerobot/meta/info.json`：`codebase_version=v3.0`、`robot_type=aloha_bimanual_14d(gym_aloha vx300s dual-arm)`、**`fps=29.41176470588235`（精确值，非取整）**、`total_episodes=2`、`total_frames=514`、`splits={'train':'0:2'}`、`observation.state` / `action` 均 `float32 [14]` 且 `names` 为 `left_arm_j0..`、三个 `observation.images.*` 均 **`dtype=image`、`shape=[224,224,3]`** ⇒ **符合裁定 82④ 的甲，且规避了乙被否的原因（取整 fps）。丙（monkeypatch lerobot）D 已禁止，你未走丙 ⇒ 合规。**

### 17-3 需你回答的一个口径问题（**D 不预设答案、不推断**）

`team_form` 侧用的是 **mp4**（`top-camera.mp4` / `left-wrist-camera.mp4` / `right-wrist-camera.mp4`，双向各 1 集）。**乙被否的理由是「mp4 + 取整 fps」**，不是"mp4 本身"。

**请实测 mp4 容器写入的 fps 并回报**：
- 若是**精确 `29.41176470588235`**（或团队流水线约定的等价表示）⇒ 与乙不是一回事、**可保留**；
- **若写了取整 fps（如 30）⇒ `team_form` 与 `pi05_lerobot` 之间存在时间基不一致**，必须显式登记，并说明**哪一侧是训练真值**。

D 不推断容器里是什么值——这属实测事项，按裁定 71 不得跨口径搬用。

### 17-4【关键路径唯一卡点】`states_14d.npz` **仍未导出**，D 第二次催办

- D 实测（23:45）：`scripts/b2_s1_generate_dataset.py` = **2540 ln / `756a46b25984` / mtime 23:42:58**（裁定 82 时为 2333 ln / `b7e93e65d5f5`）⇒ **你在改（+207 行）**。
- 但 `grep -c` ⇒ **`states_14d` 0、`savez` 0、`start_poses` 0、`physical_range` 0、`jnt_range` 0**；`PNG` 7 命中 / `parquet` 3 命中 ⇒ **你在做 82④（图像存储），没做 82②（npz 导出）。**
- **82② 优先级高于 82④**：只有 82② 卡在 C2 的主线 stats 上。**C2 的 `mainline_status.json` 于 23:41:23 / 23:42:54 / 23:55:00 三次都写 `waiting_for_s1_pilot_5` + `refused_to_substitute=[env_derived_diagnostic, yam_abc130k]`** ⇒ **C2 三次拒绝用手上的诊断档顶替，D 三次记功；C2 的主线 stats 完全卡在你这一条上。**
- **契约原文（裁定 82.2，C2 提、D 采纳为绑定契约）**：`frames=[N,14] float64`（按集拼接、集序号升序）、`start_poses=[E,14]`、`physical_range=[14]`（**臂关节读 `jnt_range`、夹爪维 = 1.0**，同 `scripts/c2_collect_env_states.py` 口径）+ `manifest.json`（五元标注 + `control_hz=29.4118` + `episode_horizon_s=10.2`）。**C2 的生成器 `--s1-frames` 直接吃它、不需改代码。** 导出**不得改变 LeRobot 数据集本体**（两条出口并存）；在 `demo_manifest.json` 里记 npz 的 sha256-12 + `as_of` mtime。

### 17-5 降阶方案（**D 授权，避免你因追求完整而卡死关键路径**）

`states_14d.npz` **可以先由已落地的 40×2 自检轨迹导出一个先导版**：数据源 = `runs/vla/b2_sim_demo_bidir_20260930/probe/expert_selfverify_40x2_postpatch.json`（D 已逐行复核 80/80 success、`hz` 全 29.411765、`n_plan_nonconverged=0`、`timeouts` 全空）。条件：

1. **schema 与契约逐字一致**（同上：`frames` / `start_poses` / `physical_range`，臂关节读 `jnt_range`、夹爪维 = 1.0）；
2. `manifest.json` 带**五元标注** + `control_hz=29.4118` + `episode_horizon_s=10.2`；
3. **显式标** `provenance="expert_selfverify_40x2_postpatch"`、`is_pilot5=false`、`formal_collection_pending=true`。

**收益**：C2 可**立刻**验证 `--s1-frames` 通路并跑通全流程（契约层 → stats → 闸 → 变异体），不必等你的 pilot 5；等 pilot 5 落地再换真数据重算一次即可。

**硬限制（D 同时已写给 C2）**：该先导版**不得**作为主线 stats 的正式数据源（裁定 52/69：主线 stats 必须与 BC 训练数据同源）⇒ **C2 用它跑出的 stats 必须标 `stats_provenance=pre_pilot5_path_check`，不进 BC。** 这是**通路验证**，不是主线交付。

### 17-6 replay 闸的判据已由 D 重定范围（**依 E 的直接实测**）

E 的 `RENDER_DETERMINISM.json`（23:40:22，generator `ffc867dd2e97`）实测：**egl 下 `angle` 逐位可复现、两个 wrist 相机不逐位**（`n_unique_shas_per_rep` = left `[5,4]` / right `[6,6]`，最差 `max_abs_diff=1`、`frac_diff_px=0.000717`）；**osmesa 三相机全部逐位一致（进程内 + 跨进程）**。

**⇒ 你的 replay 闸必须按下列判据（裁定 82⑤ + 83.3/83.4）**：
- **状态逐位 = 硬判据**（必须逐位相等）；
- **`angle` 相机逐位 = 硬判据**；
- **wrist 两相机：禁止用逐位/sha 作 egl 判据**（会误杀干净批），改用 D 定的容差 **`replay_max_abs_diff<=2` / `replay_frac_diff_px<=0.005` / `replay_mean_abs_diff<=0.005`**，并**登记实测差异像素占比**（不是"必须为 0"）；
- **`applies_when` 以实测 `GL_RENDERER=nvidia_gpu` 为键**（不是 `MUJOCO_GL`；这是 A2 提出、D 采纳的全线规则）+ shim `dc14466fcdcf` + 主线 env + 224×224。**只跑 llvmpipe 的臂不适用该容差，仍走逐位。**
- **必须有变异体**（把 replay 的某一维状态扰动 `1e-3`，或跳过一个 sub-step）证明该牙会红 ⇒ **D 本轮新立红线 `tooth_must_be_mutant_proven`**：只写 `red_when` 文案不算牙。**否则 0.5% 的容差可能吞掉真实的小发散。**
- **不得把 E 的 `FID_*`（4 / 0.02 / 0.05）搬进 replay 闸**——那是"区分污染臂/干净臂"口径（裁定 71 `caliber_transplant_ban`）。

### 17-7 GPU 排程（**现在不要上卡**）

- **A2 现在持 GPU 窗**（重跑裁定 76.4 的权威 quiet-window，rep1 已被 E 的 ballast 污染）；**E 已被 D 下令 GPU 全线 HOLD**。
- **优先级 A2 > C2 > E > B2（裁定 73）** ⇒ **你的 pilot 5 / formal 20 请等 A2 销账后再上卡**，且**开跑前在 `daily_report.md` 申报**（用 A2 §9 的模板：做什么 / 激活方式 / 预算时长 / 显存峰值 / 可否 kill / 起点读数 / 窗口判据 / 销账）。
- **你的批级闸必须在每个 GPU 批次前重查**（裁定 76.2 红线）；**若你要用任何共租假体，D 本轮新立红线 `cotenant_injector_must_be_gated`：注入器启动前也要过同一把闸。**

### 17-8 你现在的欠账（D 侧口径，00:0x）

| # | 项 | 状态 |
|---|---|---|
| ① | **`states_14d.npz` + `manifest.json` 导出**（17-4，可用 17-5 降阶方案） | **未做（关键路径唯一卡点）** |
| ② | 图像存储按**甲**落地 | **已闭合**（17-2 验收通过） |
| ③ | `team_form` mp4 容器 fps 实测回报（17-3） | 未交 |
| ④ | replay 闸按 17-6 重定范围 + **变异体** | 未交 |
| ⑤ | **git 代提交**（裁定 81.2） | **仍欠**：HEAD 仍 `c422659`（21:2x），脏项 00:0x 实测 **51**（23:35=49 → 23:43=50 → 00:0x=51）。**`runs/` 被 `.gitignore:12` 排除 ⇒ 全部实测证据只在 NFS**，服务器重启后 NFS 是唯一载体 |
| ⑥ | 裁定 78.3（委托闸补 `id` + 去前导空格）/ 78.4（`delegated_g1_g5_freeze` 二选一）/ 78.5（`G2` WARN 极性修）/ 78.8（`V-pi05-1` 改判后清 RED）/ 78.2 | 未交 |
| ⑦ | 然后 **pilot 5 → formal 20/方向** | 阻塞在 ①④⑤ |

---

## §18【裁定 85 · 2026-09-30 01:1x】B2：**你成为关键路径持有者**；先导 10 集验收通过；npz 任务撤销；RR 四条全裁；**你的 probe4 否证了 D 的 D-H1，记功**

**权威全文**：`work/decisions/decisions_20260929.md` 裁定 **85.0 / 85.3 / 85.4 / 85.5 / 85.6 / 85.7 / 85.12**（2177 ln `7bae37a52e69`）。**本段取代 §17 的待办清单。**

### §18.1 先导 10 集 **验收通过**（D 亲读 `pilot/demo_manifest.json`，15321 ln `cc8d5ca62227` as_of 01:08:10，`generated_at=00:46:57`）

- **闸** `verdict=PASS / n_checks=16 / n_red=0 / n_warn=0 / n_unjudged=0`；**专家自证 80/80 success**（`n_steps 283–295`、`n_over_registered_horizon=0`、`n_plan_nonconverged_total=0`、`evidence_matches_current_module=true`）；**重放三臂全 `bitwise_equal=true / max_abs_diff=0.0`**、形状守恒 `286−12==274` 成立、状态对齐约定显式声明。
- **裁定 83.8 的欠项销账**：`team_form` mp4 fps 三相机实测 **`29.41176470588235` 精确**、`fps_rational_requested="500/17"`、`nb_read_frames==n_input_frames==274`。
- 体积 **0.0539 GiB** ⇒ **formal 40 集外推 ≈0.22 GiB**（预算 10 GiB，余量 45×）；诚实标注 `policy_executed=false / capability_claim=false`。

### §18.2 【关键路径解锁】**`states_14d.npz` 任务撤销**

D 亲读 `pilot/pi05_lerobot/data/chunk-000/file-000.parquet` 的 schema（pyarrow 25.0.1）：`observation.state: fixed_size_list<float>[14]`、`action: [14]`、三相机 `struct<bytes,path>`、**2746 行 / 10 集**。**数据已经在 parquet 里**，`grep -c states_14d scripts/b2_s1_generate_dataset.py = 0` ⇒ 你从未实现该导出，**也不需要实现**。C2 改吃 lerobot 目录（新增 `--s1-lerobot`），`start_poses` 从 `frame_index==0` 切、`physical_range` 用 C2 自己的 `physical_range_effective`。
**⇒ 关键路径上不再有任何你的待办阻塞 C2。你的下一步就是 S1 formal 40 集。**

### §18.3 RR 四条逐条裁

- **RR-B2-10 反向串：批准** `Transfer the red cube from the left arm to the right arm.`（主/宾精确镜像）。一致性 D 已核：正向落 `transfer_cube_right_to_left`、终态被 **left** 夹爪握住、`reward=4`；反向 `reward=2`（**≠4**，满足 G1 的必红条件）。**两串一经采用即训练/评测共用条件信号，改串 = 换 `representation_version`**；当前 `b2-s1-sim-bidir-aloha14d-dt0.034-29.4118hz-grip14_to_qpos_pair(+v,-v)-team480x640+pi05x224-v1` **冻结**。
- **RR-B2-11 键名：你正确，D 撤回自己的写法。** 正确 = **`observation.images.{base_0_rgb,left_wrist_0_rgb,right_wrist_0_rgb}`**（A2 实测自 π₀.₅ processors）；D 的 §13.8-2 写 `{top,left_wrist,right_wrist}` **错**。你「读实现不读声明」**记功**，pilot parquet 列名已合规。你点名的后果成立（若按 D 字面写 ⇒ A2 的 S3 与 C2 的 obs 键覆盖闸对不上 ⇒ 假红或静默丢图）⇒ D 已立自查项 `d_assertion_requires_artifact_or_tag`。
- **RR-B2-12 维持甲（PNG 内嵌），不做丙（monkeypatch）**：甲无损诚实且体积已实测可承受（formal 0.22 GiB vs 10 GiB，余量 45×）；乙让 fps 字段说谎违反裁定 53；丙要 monkeypatch 第三方运行时而体积**不是**约束 ⇒ 风险大于收益。**旁证你自己给的**：`team_form` 走直接 ffmpeg 时 `500/17` 拿到精确 fps ⇒ 非整数 fps 本身没问题，问题只在 lerobot 的 PyAV 路径。可推翻条件：formal 实测 > 2 GiB，或训练侧改为直接消费 `team_form` 的 mp4。
- **RR-B2-13 确认为「每方向」**：先导 **10 集**（5/方向）、正式 **40 集**（20/方向）。消解裁定 66 的歧义——S3 要求同一 θ 学双向，若按「总共 5 集」拆成 2/3，任一方向都不够跑 q01–q99。**formal 40 集 = BC 的 stats 源，落地后需通知 C2 重算。**

### §18.4 **D-H1 被你实测否证 —— 记功，第 7 次下位纠正 D**

`probe4.json`（`3eaf525b67ab`）：`calibration_analytic` **已逐侧**读了 `eq_data[6:10]` 的 relpose（左 `[1,0,0,0]`、右 `w≈0/z≈1`），复合后右臂残差**仍 0.2469 m / 2.376 rad** ⇒ D 预登记的否证判据（「< 3 mm 则成立，仍 > 3 mm 则被否」）**判定 D-H1 falsified**，真因转 H2/H3 = **约束本身不一致**（EE 模型 `nu=4` 且 4 个 actuator 名全为空串 + 右基座绕 z 反装 180°（`assets/vx300s_right.xml:3` `euler="0 0 3.1416"`）），**不是反解公式的错**。
**D 的判定**：这**不计入**同型错误台账——它是**带预登记否证判据的假设被正常否证**，是制度在工作。**记功你，并记功裁定 66 §13.6 那条「D 的推断被否也要写进产物」的要求**（`verdict_status=b2_measured_falsifies_d_inference` + `how_to_reproduce` 让否证可追溯）。**裁定 66 §13.5 的 EE-oracle 字面路线就此关闭**，其立法目的由你的实现满足（示范动力学 = 关节模型自己的 actuator 动力学 = 与 S5 评测同一套）。你原样留档 probe3 的 traceback 也记功。

### §18.5 【即时生效，不等回】**replay 闸改判：硬判据只剩「状态逐位」**

裁定 82⑤-3 / 83.4 的过渡期 replay 闸是「状态逐位 + **`angle` 逐位** + wrist 只登记」，其依据「`angle` 必须逐位一致（实测成立）」**来自 n=2/n=3**。E 的 n=5（`RENDER_DETERMINISM_REPS5.json`，2050 ln `767a2d984a5b`）实测 **egl 三相机 `cross_process_same_sha` 全 false**，`angle` 是 **4/5 逐位、1/5 不逐位** ⇒ 继续拿 `angle` 逐位当硬判据会有 **~1/5 概率的间歇性假红且不可复现 = 随机红**。
- **改为**：**硬判据（判红）= 状态逐位相等，仅此一条**；**三相机像素一律只登记不判红**，登记容差取 E 的 n=5 实测（`angle ≤0.002%` / `left_wrist ≤0.024%` / `right_wrist ≤0.052%` / `max_abs_diff ≤1`）。
- **裁定 83.4 的三个数值不需重定**（可推翻条件②未触发：最差 0.000518 vs 阈值 0.005，余量 **9.7×**；`max_abs_diff` 1 vs 2，余量 **2×**）。
- **「状态逐位」为何安全 —— 你自己的数据是决定性的一腿**：你的 `recorded_vs_norender.bitwise_equal=true / max_abs_diff=0.0`，你自注该臂作用 = 「**隔离『渲染是否扰动物理』**」⇒ **EGL 的像素不确定性不泄漏进动力学**。E 的 n=5 + 你的 `recorded_vs_norender` + D 的 83.4 容差 **三腿互证，本条不需再补测**。
- **三条牙（随改判一起交）**：① 绿证人（干净重放 ⇒ 绿）；② 必红（篡改任一维状态 1 LSB ⇒ 红）；③ **必红变异体：篡改像素但保留状态 ⇒ 仍绿**——第③条是本裁定专属的牙，**缺它则「像素已降级」无法被证明**。
- **相关新红线**：`render_bitwise_equality_ban_on_egl`（egl 上任何闸不得以渲染帧 sha 逐位相等为判据；`applies_when` 以**实测 `GL_RENDERER`** 为键，不以 `MUJOCO_GL` 为键）。osmesa 臂不受约束（n=5 三相机全逐位）。

### §18.6 两处纪律问题（**你都自报在先，D 只登记不定性为隐瞒**）

1. **00:26:58 那版 selftest manifest 灭失 ⇒ `unbacked_citation` 第 2 起**（第 1 起是 E 的 83.5）。你 §1.1 引的读数出自被 00:32 重跑覆写的那版 ⇒ **标 `stale_unrecoverable`，不得作为 rep4/rep5 污染的确证证据**。D 已查可复原性：`recycle_bin/` 下有 `b2_s1_pi05_lerobot_20260930_002103_546094` 与 `b2_s1_team_form_data_20260930_002103_537128`（`--trash` 移走而非 `rm`，**合规**），但 **manifest 本体不在其中**。**裁定：`--trash` 必须把 `demo_manifest.json` 一并纳入**；守卫**复用 C2 的 `scripts/c2_driver_output_guard.py`（690 ln `6cc7b148295b`）的 `snapshot` 半段，不新写**（E 已示范该用法并写明为何不跑 `restore`：C2 守卫的 `is_owned()` 只处置 `c_*` 前缀）。
2. **RR-B2-18 `contaminated_by_cotenant` 恒真 ⇒ 狼来了**（缺陷类 ①，与 C2 抓到的 `Tr1` 同族；你自己已点明「这个标志会永久为真 ⇒ 标志本身失去意义」）。**裁定你的三条驱动修法，但第①条必须改**：①「外来 compute app」**按新红线单独不成立**（对 EGL 盲）⇒ 改为 **①′ `card_busy(strict=True)` 三网的外来命中**（复用 E 的实现口径）；②「归线 `a2_/c2_/e_/b2_` 且 **`pcpu>1%`** 的活跃作业」**批准**（`pcpu>1%` 正是排除 PID 39153 的正确键）；③「`loadavg_1m` 前后摆幅 ≥5」**批准**；被忽略的空闲进程**照样落进产物并写明忽略理由**。**三条牙**：起持 `/dev/nvidiactl` 的进程 ⇒ 必 `true`；只留 `pcpu=0.0` 空闲 bash ⇒ **必 `false`**（当前实现在这个证人上就是红的 ⇒ 它既是牙也是修复验收）；起 args 含 `b2_s1_generate_dataset.py` 且 `pcpu>1%` 但不碰 GPU 的进程 ⇒ 必 `true`。
   **你新装的 `gpu_preflight()` 硬闸（`n_foreign>0` 且无 `--allow-cotenant` ⇒ `exit 3` + 落 `refused_gpu_busy_<ts>.json`）D 认可方向，但它的判据同样只查 `compute-apps` ⇒ 一并升级为三网。GL 上下文挪到硬闸之后才起（`_init_gl_identity()`）这一改是对的，记功。**

### §18.7 GPU 窗口：**优先级改了，S1 期间窗归你**

E 报的排程缺口成立：裁定 84 §5 只写了「窗内 A2 的禁止动作」**没覆盖 B2**，而你的 S1 采集本来就走 GPU 渲染（裁定 80.3 核到 `b2_s1_generate_dataset.py:69`）⇒「持窗者=E」与「B2 正在采集」可同时为真。**这是 D 的条款漏洞，不是你的执行问题。**
**裁定（即时生效）**：① 窗口条款**覆盖全部四线**，起 GPU 进程（**含渲染采集、含共租注入器**）前必须三网 + 申报行 + 销账行，三项读数 = `compute-apps 条数 / fd 网外来 PID 列表 / memory.used MiB`；② **优先级改为「关键路径感知」= A2（已申报的标定窗）> **B2（S1 采集）** > C2 > E**——**你从裁定 73 的末位升到第 2 位**，因为 S1 是全仓唯一真阻塞；A2 仍可压你但须给 ≥1 个批次的排空时间（你的批次可在集边界中断）；③ E 本轮 `--cotenant` 继续禁用、GPU 待办已清空 ⇒ **formal 期间不会有人抢你的卡**。
**⇒ 你现在就可以开 formal 40 集，按 ① 写申报行即可。**

### §18.8 B2 的待办（按优先级）

1. **S1 formal 40 集（20/方向）** —— **关键路径 P0**，GPU 窗归你。
2. **git 提交** —— HEAD 仍 `c422659`，工作区 **56 项脏**（含 D 的三份新单、参数表 rev13→rev14、A2/C2/E 的新脚本与文档）。`runs/` 被 `.gitignore:12` 排除 ⇒ 证据只在 NFS，**提交信息里写明**。
3. **replay 闸改判 + 三条牙**（§18.5）。
4. **RR-B2-18 三网化 + 三条牙** + `gpu_preflight()` 升级三网（§18.6-2）。
5. **`--trash` 纳入 `demo_manifest.json`** + 复用 C2 守卫 snapshot（§18.6-1）。
6. 裁定 78.3 / 78.4 / 78.5 / 78.8 / 78.2 五个闸任务（未销账，顺延）。

---

# §19 【裁定 87 附则 · 2026-09-30 02:1x · B2 读这一节就够】

**权威原文**：`work/decisions/decisions_20260929.md:2379-2689`（2375 → **2689 ln**、`30daafe78879` → **`348797eff63f`**、as_of 02:16:12）。本节是摘录 + 派工，冲突以原文为准。
**你的 §B2-10 与 `selftest_g4b2/`、两个 `mutant_replay_*/`、`mutation_verdict_*.json` D 已全部核实在盘**（01:28–01:35）。

## §19.1 【P0 · 关键路径 · 授权立刻起跑】S1 formal-40

**排窗（§87.0）**：GPU 三网 02:00:17 实测**全空**（compute-apps 空 / fd 网 0 / 他线 cmdline 0；`0 % / 0 MiB`；`loadavg 19.42/18.76/20.39` 是宿主他租；`nr_throttled=15176`）。
**顺序 = E 的秒级 C4 先，你紧随。** E 的 C4 是 P0 重启保险、秒级；**若 E 超过 2 min 未结束，你不必等，直接起跑并写申报行**（这是 §87.0 的可推翻条件，E 让路，因你在关键路径上）。
**A2 已主动声明不插队**（`daily_report.md` §15.1-②）⇒ 你不必顾虑 A2。A2 的三网清洁证书 rep（P2）排在**你 formal 完成之后**。

**为什么不被 C2 的主线红阻塞（§87.9）**：C2 修的是**归一化器**（`widen_to_cover` 的覆盖目标），**不在数据里**。串行会白白浪费空卡窗，且与用户北极星冲突。**"更多集"本来就是 formal-40 的目的之一。**
**成本口径照你自己的实测**：双渲染 **≈34–35 s/集** ⇒ 40 集墙钟 ≈23 min、**GPU ≈5.5 min** < 裁定 73 的 10 min 门槛 ⇒ **只需申报行，不需长窗**。体积 ≈0.22 GiB（远低于 10 GiB 线）。

## §19.2 【强制加项 1 · 必须在起跑前补】渲染臂**硬拒绝**，不是登记项

**D 核实你的现状**（`scripts/b2_s1_generate_dataset.py` **3977 ln `3827d9039f88`**，02:0x 实测）：
- `:818-845` **已实测** `renderer_class`，而且那句「**裁定 72-1：`MUJOCO_GL` 只表达意图，`GL_RENDERER` 才表达事实**」是**你自己写的，D 记功**。
- `:2318-2320`、`:3349` 用它决定 **G4b/G4c/G4d 的 `applies_when`**（nvidia 臂 vs osmesa 臂）。
- **但没有任何一处硬拒绝。** ⇒ 若 EGL 软链在采集中途死掉，你的闸会**静默切到 osmesa 臂继续跑**，产出一份**渲染口径不同、墙钟 12.64×** 的数据，而**没有人会停下**。

**这不是假设，是唯一依据**：E 的 `chain_verify` 实测 `/root`、`/root/venvs`、`/root/.bashrc`、`/usr/share/glvnd/egl_vendor.d` **全在 overlay（重启即死）**，而 `codex-persist watch`（PID 187229）**只单向镜像、从不恢复**。用户已明说**服务器可能关闭**。
**E 自己在 `scripts/e_egl_coldstart.py:13` 也点了这个缺口**：「裁定 83 §5 规定了以实测 `GL_RENDERER` 为键，**但没规定失败要响亮** ⇒ 本件补上。」

**要求（改动很小，一个 preflight + 一个收尾复测，不构成重写）**：
1. **起跑前**实测 `renderer_class`；**若 ≠ `nvidia_gpu` 则 exit ≠ 0 响亮拒绝**，错误文本里写明恢复命令（`env -i /bin/bash …/scripts/e_coldstart_gpu_render.sh`）。
2. **结束时复测一次**；**若中途换臂 ⇒ 整批判 `environment_invalid`**，不得产出 manifest。
3. 两项读数都进 manifest（`renderer_class_at_start` / `renderer_class_at_end` / `arm_stable`）。
4. **配一颗牙**（`tooth_must_be_mutant_proven`）：把 `MUJOCO_GL=egl` 但不带前缀跑一次 ⇒ 必须 exit ≠ 0，**不许静默落到 llvmpipe 继续采**。

**缺陷类归属**：⑧ 假绿 + ⑫ 探测器盲区的合体，**落在关键路径上**。

## §19.3 【强制加项 2】formal npz 的 provenance 三元组由**构造**满足

- **同一导出器** `scripts/b2_export_states_14d.py`（**947 ln `8708d4a84d7f`**）、**`MUJOCO_GL=disable`（不占卡）**、**双跑 sha 一致**（先导就是这么做的，照做）。
- npz / manifest 必须携带 **`n_episodes = 40`** + `n_frames` + `sha256` ⇒ 让裁定 86.1 的三元组**由构造满足**，不靠事后补。
- manifest 须写**每方向计数 20/20**（裁定 85.5 RR-B2-13）。
- **补一行命名说明**：`pilot5` = **"每方向 5 个 seed"**，共 10 集（裁定 86.1 已要求，D 本轮核实**尚未落**）。**理由**：目录名 `pilot5` 与内容（10 集 / 2746 帧）不符，已经让 D 在裁定 86 栽过一次。
- **C2 会用 `--s1-frames` 直接吃这份 npz** ⇒ 键名保持 `frames / start_poses / physical_range_effective / observed_travel / episode_index / episode_boundaries / direction_code` **不变**。C2 已实测 `contract_conformant=true`（逐维复算 `max_rel_diff ≤ 1e-9`），**不要改这个契约面**。

## §19.4 【强制加项 3 · 仍欠】`--trash` 必须包含 `demo_manifest.json`

裁定 85.6-① 未销账。上一轮 00:26:58 的 selftest manifest 被销毁 ⇒ `unbacked_citation` 第 2 例、读数 `stale_unrecoverable`，**这直接导致 §85.0 只能判 `undetermined` 而不能判 `contaminated`**。复用 C2 的 `snapshot` 守卫。

## §19.5 【已闭合，若已排入队列可撤】

- **§B2-9.1（angle 同进程非逐位 2/274、17/271）** ⇒ 裁定 86.2 已收：**常态红而非随机红**，`hard_criterion_would_have_fired=true` 由机器算出 = **加强了 85.3**。你请求的「甲/乙/丙选一个」**已关闭**（丙案，裁定 85.2-2）。
- **85.3 的三颗牙齐了**：牙③（只改像素、状态不动 ⇒ 仍绿）由**干净批本身**闭合（`selftest_g4b` 19 闸/0 红/2 N_A）；牙①② 由 `mutant_replay_state/`（rc=3，G4 红）与 `mutant_replay_image/`（rc=3，G4b 红）证明，`expected_red==observed_red`、`missed=[]`、只有目标闸红。
- **`selftest_g4b2` 的 schema 修正收下**：把 N_A 的实测量从 `observed_measured` **并进 `observed.measured`**、给 G4c/G4d 补 `red_when` ⇒ **符合裁定 78.2 的最小公共 check schema**（第一版下游只读 `observed` 会看到"只有理由、没有数"—— 你这个修法是对的）。
- **RR-B2-21（480×640 的 G4d 登记带）已转 E** 为 **T-E-DET-480（P1）**，**你不必自测**，G4d 保持 `N_A`。**你拒绝把 224² 容差移植过去 = 裁定 71 的正确执行，D 记功。**
- **RR-B2-18 的三网升级**（裁定 85.6-②）：`contaminated_by_cotenant` 恒真（空闲 bash PID 39153 pcpu=0.0）⇒ 三驱动已批（① 三网 ② 线标签 + pcpu>1% ③ loadavg 摆动 ≥5）。**注意 A2 已用 `importlib` 复用 E 的 `card_busy()`（`scripts/e_mainline_render_calib.py` `2d1320672224`），零抄写 ⇒ 你走同一路径，别写第三份。**
- **git**：HEAD `4ff31bd`、脏 **20**（02:00:17 实测）。**单写者纪律完好，D 不再催第二次。** 本轮 D 又写了 5 份文件（decisions / 4 份 handoff）+ 即将写 daily_report / checkpoint / params ⇒ **会再脏，等你 formal 跑完一并提交**。

## §19.6 【一条口径变化，与你有关】夹爪契约文本 **D 已改**（§87.6）

裁定 82.2 的契约文本里「夹爪维 = **1.0**」与「同 `scripts/c2_collect_env_states.py` 口径」**互相矛盾**（该文件实测 **0.91001**，差 **9.889%**）。**你登记 `OPEN_needs_d_ruling` 是正确的，C2 拒绝自决也是正确的。**
**D 的裁定（根因修法，不在两个数之间选）**：**契约文本不得硬编码任何夹爪数值。**
> 各维取值范围 = **主线数据的同源实测值**（你的 npz `physical_range_effective`，与 `frames` 同源）。`c2_collect_env_states.py` 是**诊断专用源**，数值不得移植进主线。契约里出现的任何具体数字（含旧文本的 "1.0"）**一律为登记项、不是判据**。
**对你的影响 = 0**（你的 npz 已经是权威源）⇒ **不必返工**。**这是 D 的第 14 号错误，由你和 C2 发现。**

## §19.7 D 等你的
1. **起跑申报行**（三读数）→ **formal-40（20/方向）** → **销账行**。**（P0，关键路径）**
2. **加项 1 的渲染臂硬拒绝 + 牙**（起跑前必须补）。**（P0）**
3. **formal npz**（`n_episodes=40` + sha + 双跑一致）+ manifest 的 `pilot5` 命名说明行。**（P0）**
4. **加项 3 `--trash` 含 manifest**。**（仍欠）**
5. RR-B2-18 三网升级（复用 E 的实现）。**（P1）**
6. **git 代提交**（本轮 D 的 8 份写入 + 你的 formal 产物 + A2/C2/E 的增量）。**（P1）**

---

# §20 【裁定 88 附则 · 2026-09-30 02:3x–02:4x · B2 · 你的 §B2-11/§B2-12 已读，formal 照跑、D 不叫停】

**权威原文**：`work/decisions/decisions_20260929.md:2691-2845`（**2845 ln `b62e7a7aa02e`**，as_of 02:32:34）。广播版见 `daily_report.md` §D88。

## §20.1 【裁定 85.5 的三颗牙】**验收通过 —— 本仓最强的一组牙**

| 牙 | 实测 | D 的定性 |
|---|---|---|
| ① 绿证人 `teeth1_green_witness` | `rc=0 @02:20:15`、`verdict=PASS`、19 闸、`n_red=0`、`n_warn=0`、`n_unjudged=0`、`n_a=1`（G4c 已降级） | 干净重放必须绿 ⇒ **成立** |
| ② `replay-state-1lsb` | `rc=3 @02:21:33`、`verdict=RED`、`red_ids=["G4_replay_reproduces_bitwise"]`、`missed_red=[]`、`extra_red_beyond_expected=[]`、`tooth_verified=true` | **1 ULP（`np.nextafter`，≈1e-16）证明 G4 用的是 `np.array_equal` 逐位、没有偷偷带进 `atol/rtol`** ⇒ **比上一棒的 `1e-3` 强一个层级**（`1e-3` 只能证明"看得见的扰动会红"）。**特异性由机器字段判定，满足裁定 86.6-3 的 `mutant_specificity_required`。** |
| ③ `replay-image-pixel-only` | `rc=0 @02:22:51`、`verdict=PASS`、`n_red=0`、`must_stay_green=true`、`stay_green_observed=true`、`tooth_verified=true` | **关键不是"绿"，是"注入真的发生了却仍然绿"**：`mutation_injected=true`、`max_abs_diff=3`、`frac_diff_px=0.02968`（= 83.4 容差 `0.005` 的 **5.9×**）、机器现算 `would_have_been_red_under_ruling_17_6=["pi05_base_0_rgb"]` ⇒ **「像素已降级」自此有产物级证据，不是文案。** |

⇒ **裁定 85.5 的三颗牙全部有专属变异体支撑。裁定 86.2 时 D 说"牙③由干净批本身闭合"那是推定，本轮你交的是专属变异体 ⇒ 推定升级为实证。**
**一条登记项（不判红、不阻塞）**：D 只查了 `gates.*` 层级，读出 `gates.mutation_tooth_ok = None`，而你 §B2-10.1 说 `rc=3` 也表示 `mutation_tooth_ok=false`。⇒ **请在 §B2-13 写明该字段的实际路径**，以便 CI 引用。**在写明之前，D 引用牙②③的依据是 `expected_must_go_red` / `observed_red_ids` / `missed_red` / `extra_red_beyond_expected` 四元组（已足够），不依赖该字段。**

## §20.2 【对 §B2-11.2 的答复】`authority_scope` **追认**，附一条边界

**追认**：`contaminated=true` **只降吞吐/时延类数字的口径**（`wall_s`、`s_per_episode`、`nr_throttled_delta` 及由其推出的产能/排期），**不使数据集内容失效** —— 内容由 G4「状态逐位」+ `recorded_vs_norender`（渲染不扰动物理）承载，**与主机负载无关**。teeth2 的红因只有信号③（`loadavg_1m` 摆幅 11.24 ≥ 5.0，19.73 → 8.49 = **主机在这 84 s 里变安静了**），三网零命中、`foreign_active_gpu_line_procs=[]`。
**你不改判据、而是把覆盖范围写进产物（`authority_scope` + `authority_scope_why_written`）= 正确处置。**
**D 加一条边界**：`authority_scope` **不得被套用到任何"以计时量为判据"的闸上**。若未来某闸把 wall-clock/步时当判据，则 `contaminated=true` **必须**使其失效。⇒ **请在 `authority_scope` 里显式写 `does_not_apply_to: ["任何以计时量为判据的闸"]`。**
**为什么这条重要（你自己的话，D 采纳）**：「若不写，下游很容易把『teeth2 是 contaminated』读成『那颗牙的证据不可用』，甚至读成『formal 数据被污染』⇒ 那就是把一个**纯计时口径**的标志误用成**数据质量**判据（裁定 27.1 的同型毛病）。」**你提前堵住了，记功。**

## §20.3 【对 §B2-11.1 那条如实登记的答复】两个字段分开是对的，**而且它下调了 DET-480 的定位**

你如实登记：干净批里 `left_wrist` 的 `frac_diff_px = 4.07e-04` **超了 E 的 n=5 登记带（`2.39e-04`）**，但**没超**裁定 83.4 的容差（`0.005`，余量 **12×**）；并为此把顶层拆成 `pixel_register_exceedance_slots`（含"只是不到全帧逐位"，**egl 上非空是常态**）与 **`slots_exceeding_ruling_83_4_tolerance`**（严子集，干净批应为空）。
**裁定：追认。这是三态纪律（新红线 `absence_of_measurement_is_not_measurement_of_absence`）的正确实现** —— 把"超登记带"与"超容差"分成两个字段，就是不让一个弱信号塌缩成强判据。
**下游影响（D 的推论）**：**E 的 n=5 带已紧到"干净批也会超" ⇒ 只能是登记带、不能是判据。⇒ T-E-DET-480 的 480×640 带同样只是登记带，你的 G4d 在它之后仍是 `register_only`、不升为判据。**（D 已把这条写进 E 的 §17.5。）

## §20.4 【对 §B2-12 的答复】**formal-40 照跑，D 不叫停**；§19.2 的加项 1 改为**零延迟的补偿控制**

**当前是本轮最好的窗口**：D 02:26:11 三网实测卡全空、`loadavg 4.44/8.72/14.96`（宿主他租已退）；你 02:27:36 同口径复测 `busy=false`、三网零命中、`loadavg3=[5.41,8.02,14.22]`。**你的 34.5 s/集是在 `loadavg 27.77` 下实测的 ⇒ 当前只会更好。**

**但加项 1（渲染臂硬拒绝）不在 `b6af48fc6d58`（4333 ln）里。D 的处置（裁定 88.5-1，一次性有条件豁免）**：
- **不叫停。** 理由：① 窗口最好；② 软链 12 分钟前（02:18）由 E 实测存活、你三跑 `renderer_class` 全 = `nvidia_gpu`；③ **风险不是"静默"而是"事后可检"** —— 你已经在起点（`gl_identity`）与终点（`:3349` 的 `nvidia_arm_now`）都测了 `renderer_class`，只是没把它变成硬失败。
- **补偿控制（强制，零延迟）**：formal 跑完后**立刻核 manifest 的两个端点**；**若起点或终点任一 `renderer_class != nvidia_gpu`，或两端不一致 ⇒ 整批登记 `environment_invalid`、不得通知 C2 重算、不得进 BC。** 请把三个字段落进 manifest：**`renderer_class_at_start` / `renderer_class_at_end` / `arm_stable`**。
- **加项 1（硬 preflight 拒绝 + 它的牙）转为"下一次采集之前必须落地"**，不阻塞本批。**牙的形态照 §19.2-4**：`MUJOCO_GL=egl` 但不带前缀 ⇒ 必须 `exit != 0`，不许静默落到 llvmpipe 继续采。
- **可推翻条件**：**若本批 formal 的任一端点不是 `nvidia_gpu` ⇒ 豁免作废、加项 1 立即升为重跑前置。**
- **这条为什么值得写这么多**：E 的 `chain_verify` 实测「运行期写入的软链 + vendor json 重启即死，而 `codex-persist watch` 只单向镜像、从不写回」⇒ 一次静默换臂会让整个 23 min 的 run 产出**口径不可用**的数据，而 **formal-40 是 BC 的唯一数据源**。

## §20.5 【§B2-11.3 / §B2-11.4 收下】

- **3 处改动收下**（`8c12122b4391` → `b6af48fc6d58`）：① `sidecar.mkdir` 顺序错（在 `--trash` 之前建 ⇒ 每次重跑把一个常为空的 `sidecar/` 倒进回收站）—— **自查自修，无数据影响**；② RR-B2-10/11/12/13 的 `status` 按裁定 85.3 改 CLOSED 并逐条写入 D 的裁定要点（含 RR-B2-12 的可推翻条件「formal 实测 > 2 GiB」、RR-B2-13 的「formal 40 集 = BC 的 stats 源，落地后通知 C2 重算」）；③ `contaminated_by_cotenant` 补 `authority_scope`。
- **`REPRESENTATION_VERSION` 维持 `-v1` 冻结**：反向串用的是 D 批准的逐字串 ⇒ **裁定 85.3「改串才等于换版本」的正确执行，收下。**
  **但请注意一个即将发生的变化**：D 在裁定 87.3 已裁 **C2 的 `must_cover` 改为覆盖「声明物理区间」⇒ C2 侧的 stats `representation_version` 会变**。**你的数据集 `REPRESENTATION_VERSION`（动作/任务串口径）与 C2 的 stats 版本是两个不同的版本串，不要混用**；BC 的硬闸认的是 **`stats_provenance == formal40_bc_source`**，不是版本串相等。**若你发现两者在你的产物里被当成同一个字段，请报 D。**
- **`--trash` 纳入 `demo_manifest.json` + 只读复用 C2 的 `snapshot` 半段、不新写一份 ⇒ 裁定 85.6-1 销账。** 你的根因确认（manifest 写在 `ds_root/demo_manifest.json`，而旧 `--trash` 只移走 `team_form/data` 与 `pi05_lerobot` 两个子树 ⇒ manifest 在两者之外被就地覆写）**准确**。
  **本轮三跑都是新目录 ⇒ `overwrite_guard.status="N_A_no_preexisting_manifest"`（如实记 N_A、不假装跑过）= 三态纪律的正确执行。** **真正的验收点在 formal**（你自己也这么写）⇒ **D 会在 §B2-13 核这一条。**
  **只跑 `snapshot`、不跑 `restore`（C2 守卫的 `is_owned()` 只处置 `c_*` 前缀）⇒ 写入面纪律正确。**

## §20.6 D 等你的
1. **formal-40 跑完 → 补偿控制三字段 → §B2-13 销账行**（含 `mutation_tooth_ok` 的实际路径、`overwrite_guard` 的实际状态、体积实测、`representation_version`）。**（P0 关键路径）**
2. **formal npz**：同一导出器 `scripts/b2_export_states_14d.py`（986 ln `8708d4a84d7f`）、`MUJOCO_GL=disable`、双跑 sha 一致、**`n_episodes=40` + `n_frames` + sha256**、每方向 20/20。**（P0）**
3. **通知 C2「formal 40 集 = BC 的 stats 源，可以重算」**（裁定 85.3 RR-B2-13；你已写进产物，照做）。**（P0）**
4. **`manifest.json` 补一行 `pilot5` = "每方向 5 个 seed"**（共 10 集）。**（P0，小改）**
5. **加项 1 的硬拒绝 + 牙**：下一次采集之前落地，不阻塞本批。**（P1）**
6. **`authority_scope` 补 `does_not_apply_to`**。**（P1，小改）**
7. **git 代提交**（HEAD `4ff31bd`、脏 26 @02:37；本轮 D 又写了 decisions/4 份 handoff/daily_report/checkpoint，params 待写）。**（P1）**

---

# §21【2026-09-30 03:5x · 裁定 90/91 —— **formal npz 验收通过、唯一阻塞项已解除**；渲染臂端点复测**验收通过 + 记功三项**】

**as_of 2026-09-30 03:51:42** · 本节之前本文 = **877 ln `46d4c607c223`**（前像 `runs/vla/d_ruling_round_20260930_0320/d_handoff_to_b2.before`）
**权威出处**：裁定 90 / 91 = `work/decisions/decisions_20260929.md`（**3156 ln `a1116bd6c403`**）；参数表 **rev16 = 2681 ln `4e874b7b33a1`**。

## §21.1 【验收通过】formal-40 npz —— D 独立复核，**不是看你的日志、是重算你的产物**

`runs/vla/b2_states_14d_20260930/formal40/states_14d.npz`：

| D 的独立复核项 | 结果 |
|---|---|
| sha256 | **`a84a260795505780ca9c403d85719dd4b75921d18799ee61024d14e3ef7cd187`** ⇒ 与你 §B2-13.6 通知 C2 的 `a84a26079550…cd187` **逐字相符** |
| bytes | **1332184**（两跑同值） |
| 双跑 | `raw_file_sha_equal=true`、**9/9 数组 `bitwise_equal=true`** |
| 三元组 | `n_episodes=40`（D 用 `np.unique(episode_index)` 复算 = **40**）、`n_frames=11035`、`frames=[11035,14] float64` |
| 键名 | 9 个键**逐字未变** ⇒ C2 的 `--s1-frames` 契约面没动 |

**记功一项（你顺手排掉了一个假象）**：你在 verdict 里落了 `zip_entry_date_time` 两跑均 `[1980,1,1,0,0,0]`，并据此写 `raw_sha_diff_explained_by_zip_entry_mtime=false` ⇒ **把「逐字节可复现」从「两跑恰好在同一秒完成」这个可疑解释里摘出来，证明它是结构性的**。这正是「负证据必须同批落 meta」的样子。

**一处澄清（对你有利）**：D 在 §D89.7 要你导这份 npz，**不是**把一个已撤销的任务重新压给你 —— 裁定 **86.1 末条**原文就是「B2 的下一步不变：S1 formal 40 集；落地后**同时导出 formal 版 npz**（同一导出器、同一 `MUJOCO_GL=disable` 口径），**C2 用它重算 `formal40_bc_source`**」。**你照裁定做的，做得对。** 反而是 C2 的 `mainline_status.json` 走在了被 86.0 撤回的口径上（D 已在 §18.5 纠正它，并实测两条读路径逐位等价 ⇒ C2 不需重算）。

## §21.2 【验收通过 + 记功三项】渲染臂端点复测（裁定 91）

产物 `runs/vla/b2_sim_demo_bidir_20260930/formal/renderer_arm_endpoint_probe.json`（**9248 B**，mtime 03:18:00，`rc=0`）；生成器 `scripts/b2_probe_render_arm.py`（**389 ln `34da0a62c2b3`**）。D 复核：`arm_stable=true`（**4/4 判据、逐条带实测值**）、`endpoints_agree=true`、`environment_invalid=false`、`ruling_88_5_1_exemption_void=false`。

1. **`renderer_class_at_end_in_run = null`** —— 在「拿起点值顶一下就能交差」的地方**如实记未测**，并引红线 + 明写拒绝顶替。这是红线 `absence_of_measurement_is_not_measurement_of_absence` 落地以来**第一次被下位线主动、无提示地执行**。
2. **用两组间接但机器算的证据**承载「运行中途没换臂」这个**无法直接回测**的命题：墙钟 `max_over_median = 1.0478` vs 换臂参考 **12.64×**（`n_exceeding=0`）、末段连渲 **40/40 集 / 240 槽行 / G4b+G4d PASS**；并在 `caveat` 里写清它证明什么、**不**证明什么。
3. **牙真的咬了**：软件臂被识别为 `mesa_cpu_software` / `llvmpipe (LLVM 15.0.7, 256 bits)`，不是声明有牙。

⇒ **裁定 89 对 S1 formal-40 的 `arm_stable = inferred_from_two_machine_facts` 限定词 hereby 解除**，升级为你自己的字段值 **`post_run_independent_probe_same_caliber`**。
**此后引用口径**：不必再写 `inferred`，但**必须写该 `measurement_kind`**，且**必须同引 `renderer_class_at_end_in_run = null`**（裁定 85.0）；**「运行内连续监测」仍然没有被测到，不得声称。**

## §21.3 【定位变更 · 对你有利】加项 1 不再是补偿控制

本批两端一致 ⇒ **不需要重跑 formal-40**。加项 1（渲染器硬 preflight 拒绝 + `MUJOCO_GL=egl` 无前缀必须 `exit != 0` 的那颗牙）**定位回到裁定 88.5-1 的原意：下一次采集之前的前置**，**不阻塞 formal-40 的任何下游**（C2 stats / A2 S4b / S3 BC 全部照走）。

## §21.4 D 等你的（顺序即优先级）

1. **【P0 · 关键路径已不在你这里】** 无。你的 formal-40 + npz + 端点复测三件都已验收 ⇒ **BC 的唯一前置现在是 C2 的 `Tiv` 改判 + formal-40 stats**（裁定 90.4-1，已交 C2）。
2. **【P1】§B2-13.4 的陈旧状态串**：`contract_conflict.status` 仍写 `OPEN_needs_d_ruling`，而裁定 **87.6** 已关闭它 ⇒ 按你自己的计划改成「已由裁定 87.6 关闭」并**重跑双跑核验**（只改状态串、不动任何数组；改完 sha 若变，**以新 sha 为准并在 daily_report 登记**，同时**知会 C2**，因为 C2 的 BC 硬闸认的是这个 npz 的 sha）。
3. **【P1】`manifest.json` 补 `pilot5` = 「每方向 5 个 seed」一行**（裁定 86.1 的命名口径）；`authority_scope` 补 `does_not_apply_to`。
4. **【P1】`overwrite_guard` 的 CPU-only 牙** —— 四次都是 `N_A_no_preexisting_manifest`，**一个从没咬过的守卫等于没有守卫**（裁定 27.1）。
5. **【P1】团队 QC（validate→clean→qc）对 formal 跑** —— 跑完才有资格说「过了团队流水线」。
6. **【P1 · 全仓欠账】git 单写者**：HEAD 仍 **`4ff31bd`**，工作区 **29 项脏**（as_of 03:15:43），含 D 的裁定 90/91、参数表 rev16、四份交接增补、你与 C2/E 的新脚本与产物。`runs/` 被 `.gitignore:12` 排除 ⇒ **证据只在 NFS，务必在提交信息里写明**。**用户已明示服务器可能关闭 ⇒ 这一条的优先级高于它在 P1 里的排位。**

## §21.5 一条与裁定 90 有关的新事实（**会影响你未来的采集**）

D 实测确认了 π₀.₅ 状态离散化的**结构不对称**：`processor_pi05.py:77` = `digitize(x, linspace(-1,1,257)[:-1]) - 1` ⇒ **`x ≥ 1` → bin 255（合法饱和）**、**`x < −1` → bin −1（非法，静默拼进 prompt）**。
⇒ 对你的意义：**采集器把状态顶到软限位上方是安全的（优雅饱和），顶到下方是危险的（非法 token）**。formal-40 实测 `ex_below` **14 维全 0**、越界全在上方 ⇒ **你这批数据在这一点上是干净的**，这不是巧合也不是运气，请在下一批（尤其带 harness 纠正 / RL 探索的批次）**继续保证下侧不越**，或至少在 sidecar 里落一条下侧越界的测量。
