# D → A / B / C 收尾与冻结单（2026-09-29 16:5x，裁定 38.4）：**跑完当前任务 → 结果文件分析收尾 → 冻结**

交出方：智能体 D（监管/口径裁定线）。接收人：**A、B、C**。抄送：A2、B2（新开两线，见各自执行单）。
依据：用户 2026-09-29 裁定（原文口径：「可先冻结当前 ABC 线，VLA 测试可先在新开的智能体 A2/B2 进行初步测试，
ABC 先当前任务自行跑完，完成结果文件分析收尾再进行冻结最好」）＋ `supervisor_memo_20260929.md` **增补十五（裁定 38）**。

**冻结 ≠ 作废，也 ≠ 停摆。** 准确含义是三条：
1. **不再新开任务**：三线不再启动新的训练、新的探针、新的闸；
2. **产物转为回归基线**：ACT/Lift 线的环境、判据、溯源、评测纪律**全部保留**，作为路线无关资产被 A2/B2 复用；
3. **可复活**：若 π₀.₅ 路线在 P0/P1 预检失败（A2 的 G0.5 丙案、显存不足、权重不可得、视觉通道完全不通），
   ACT/Lift 线可被重新启用为**对照或退路**，但必须 D 登记 + 用户确认，**不许三线自行复活**。

---

## 0. D 先确认三线**已经完成**的部分（依据 = mtime / sha256 / rc / 产物，不是自述）

| 线 | 本轮已闭合（D 只读复核） |
|---|---|
| **A** | 环境重建 + 验收；**T17 A 侧 2 项**；**(甲) 训练侧验证**（真跑规模：goal 路与对照路各 24/8 episodes、7128/2376 样本、`R1_EXIT=0`/`R2_EXIT=0`）；新闸 `scripts/a_verify_t17_train_side.py` **OPEN 8/8 + 变异自检 9/9**；终验五项 16:35–16:38 **全部复跑**；自查第 7/8 起同型缺陷并留档 |
| **B** | **P0-1…P0-6 全部落地**（含 `setup_env.sh` 15:35 已改：新增 `backup_lock()` 事前逐字节留档 + 不可确认即 `refuse`）；**P0-6 git 代提交完成**（HEAD 从 `fe526d8` → `e6c661e`，11 个提交，工作区从 35+ 项降到 11 项）；门禁迁移不变性 **V0–V9 = 10/10**；自查第 9 起（牙自检自身崩） |
| **C** | P0-3 + C-F1 + C-F2；三条断点齐；`work/decisions/decisions_20260929_C.md`（16:24）与 `work/decisions/registry/`（内容寻址 + 撤销有牙，selfcheck 8 案全过，index 16:27）；verdict identity 自检 |
| **环境调研线**（无智能体前缀） | 零资产任务矩阵 **11/12**；`SO100GraspCube-v1` 判据发现；三条下载通道实测坑 + 两个工具（`hf_mirror_fetch.py` / `hf_mirror_snapshot.py`）；`MS_ASSET_DIR` 已迁到 NFS |

**⇒ 用户要求的「先当前任务自行跑完」在三线上实质已满足。** 剩下的只有下面的**收尾清单**。

---

## 1. A 的收尾清单（**今天内**，全部是分析与登记，不再跑训练）

1. **(乙) 48 臂跨断点重跑：取消。** 理由：它服务的是官方 LeRobot ACT on Lift 这条线，而
   `01_开发技术方案.md:5` 明文「**不使用 ACT**」；跨断点重跑只会让一条被排除的路线获得"已复现"的地位，
   **反而增加后来者的误读成本**。GPU 让给 A2 的 G0.5/G2。
2. **产物清单 + 冻结时状态**：把你名下所有现行产物列成一张表（路径、sha256、mtime、结论边界、是否跨断点有效），
   特别是 `t17_train_side_verify_v2.json`（**现行为 v2**；v1 的 `CLOSED` 是被缺陷判据判的，**留档不删**）。
3. **未销账项按"冻结时状态"登记，不追做**：P0（D8 补 `historical_meta_is_v121` + 变异 `S13`）、
   P1（迁移断言产物带 `baseline_meta`、sidecar 加 `imageio` 生效版本）、P2（E6 `note`/`:404` 静态散文）。
   **注意**：`S13` 未补前，**任何人**（含 A2/B2）都不得引用「D8 立即变红」这句话。
4. **能力结论口径照抄，一个字不许松**：能声称的是「goal **贯通**」（计算图 + 采集分组 + 账本换向 + 拒绝语义，真跑规模成立）；
   **不能**声称「共享 πθ 已学出 A↔B 方向差异」。根因是**数据不是实现**（`lift_B_to_A` 真帧 teacher **0 行**）。
5. **移交 A2**：`scripts/a_env_manifest.py`（manifest 口径，`probe_kind=semantic`）、`scripts/a_env_readiness_gate.py`、
   `scripts/a_env_provenance.py`、`scripts/a_selfcheck_goal_conditioning_t17.py`、`scripts/a_verify_t17_train_side.py`，
   以及两条一般规则（**搬阈值前先问它是在什么数据/训练状态下立的，换 regime 必须分空间并为新分支补专属变异体**；
   **凡依赖 rc / 异常类型 / "没写出文件"这类负证据的判据，必须同批落 meta**）。

## 2. B 的收尾清单（**今天内**；B 是冻结前的关键路径，因为 git 与闸都要交接）

1. **最后一次代提交**：把本轮全部未跟踪产物入库（含 D 的 `d_handoff_to_a2/b2_20260929.md`、本文件、
   `work/project_parameters.json`、A2/B2 的产物目录）。**提交后核 `git log` 与 `b_git_size_guard.py`**。
2. **单写者职责移交 B2**：DR-003 决定 8 的 git 单写者纪律**不因冻结而消失**，冻结后由 **B2** 承接（B2 继承你的 provenance/闸线）。
   移交内容：`scripts/b_env_provenance_guard.py`（G1–G5 + `--selftest`）、迁移不变性 **V0–V9** 口径、
   `golden_values`、`scripts/b_source_anchor.py`（行号锚）、以及**你自己那 9 起同型缺陷的一般规则**（这是本仓最贵的资产之一）。
3. **P0-3 / P0-5 若未闭合**：按"冻结时状态"登记，不追做；但**必须写清哪几条锚点是语义变更**（P0-5 里有 1 条），
   否则 B2 接手时会把语义变更当成排版变更。
4. **P1 的四项**（v1.6 / `C5=0.04` 预登记双阈值 / 饱和率表 / `golden_values` 加 `--json-out`）：
   **`C5=0.04` 一项由本单 §5.1 直接裁定，B 不用再出双阈值表**；其余三项登记为冻结时状态。
5. **饱和率进 warn**：维持**未裁**（等实测表），冻结后不再推进。

## 3. C 的收尾清单（**今天内**）

1. **P0-4**：确认 `work/decisions/decisions_20260929_C.md` 已把 C-F1/C-F2 修法、三条断点、import 面实测登记进去
   （D 看到 16:24 的文件，但**未逐条核对内容** ⇒ C 自查后在日报里点名"已登记"并给出对应小节号）。
2. **两个探针目录补申报**：`runs/infra/maniskill_state_probe_20260929/`、`runs/infra/robosuite_throughput_probe_20260929/`
   （目录无智能体前缀）。**D 的裁定见 §5.3**：批准作为**基础设施事实**引用，**目录名保持不改**（D 的引用已按此路径写），
   但必须在 README §0 补齐**作者、写入面、边界**三行。
3. **P1-5 / P1-6**：登记为冻结时状态，不追做。
4. **交付一份「A2/B2 复用清单」**（**这是 C 收尾里最有价值的一件**）：逐个模块写清
   「可直接接 π₀.₅ / 必须改 / 已知缺口」——`harness/contracts.py`、`harness/runtime_adapter.py`、
   `harness/data_bridge.py`、`harness/ledger.py`、`harness/obs_store.py`、`harness/queue_td_learner.py`、
   `registry/release_bundle.py`、`registry/verdict_identity.py`。
   已知缺口至少四条（`docs/ledger_data_bridge_20260928.md:211`）：**视觉表征缺失**（`x_ref` 只重算 flat 状态向量）、
   真实 ACT/VLA 主干未接、多 worker 签名、真 Gateway 独占租约（`lease_generation` 目前只是账本字段）。
   **⇒ 其中"视觉表征缺失"在 π₀.₅ 路线下从 P2 升为 P0**：π₀.₅ 的输入主体就是图像。
5. **`registry/` 的维护权移交 B2**（内容寻址 + 撤销事件的机制由 B2 继续用，C 不冻结后失联）。

## 4. 三线的共同纪律（冻结后依然生效）

- **禁 `rm`**，清理走 `/workspace/mnt/sppro/yhzhang91/recycle_bin/`；`RL_Harness_v4_20260924/` **只读**；
  `/workspace/mnt/sppro/yhzhang91/datasets` **不碰**。
- 引用旧产物必须带**断点 + sha256**；跨断点的主张必须重跑（`BP-20260929-lerobot-envs-wiped.invalidates` 的口径不变）。
- **吞吐/延迟/成本数字必须成对引用 `loadavg` 与 `cpu.stat:nr_throttled`**（本批 746→1612；同一任务两轮差 1.94×）。
- 外部来源事实（论文、issue、他人报告）引用时标 `external_unverified`，**不得与本机实测并列成同一张表**（裁定 36.4）。

---

## 5. 本单附带的**三项裁定**（都是悬案，趁冻结一起结）

### 5.1 裁定 38.5：`C5=0.04`（lift 高度阈）**改为按物体几何缩放**，固定 `0.04` 降为对照
**证据**：`SO100GraspCube-v1` 的 `cube_lifted = cube.pose.z >= (cube_half_sizes + 1e-3)`
（`mani_skill/envs/tasks/digital_twins/so100_arm/grasp_cube.py:414`，环境调研线 16:4x 贴原文实测）。
**裁定**：采纳「**几何缩放 + 显式余量**」为首选口径，`C5=0.04` 保留为**对照列**（不删，便于与 0928/0929 的历史产物可比）。
**执行**：由 **B2** 在本项目仿真任务上给出等价数值与两列对照，报 D 正式登记；
**在 B2 给出数值前，任何人不得声称"已按新口径重评"**。
**可红条件**（防止这条被读成恒真）：若某任务的物体几何不可得（无 `cube_half_sizes` 等价量），
必须**回退固定阈并显式标注 `c5_mode=fixed`**；静默混用两种口径 ⇒ 判红。

### 5.2 裁定 38.6：**不开** ManiSkill-HAB（MS-HAB）线；**停** ReplicaCAD 资产下载
环境调研线问「是否值得开这条线」。**裁定：不开。** 理由四条：
① 官方仓库 `haosulab/ManiSkill-HAB`、`mani-skill/ManiSkill-HAB`、`haosulab/ms-hab` 全 **404**，公开只有匿名双盲镜像
`anonsubmit0/maniskill-hab`（ICLR 2025 投稿版）⇒ **来源可追溯性不足**，与 v4「不把文献背书当本项目实测」的口径冲突；
② 装法是 ManiSkill **fork** + py3.9 + `git-lfs`（本机不在）+ `coacd` + `fast_kinematics==0.1.11` ⇒ **换整套运行时**，
而 §10.2-4 要求"先完成最小联调再锁定运行时"，现在锁它是本末倒置；
③ 示范数据集约 **500 GB**，且本节点下载通道限速（1.49 GB 单流 27 KB/s ⇒ 15 h）；
④ 它服务的是"真实失败结构"研究，而**本项目当前需要的是 VLA 主线贯通**，不是更多失败结构。
**替代**：`SO100GraspCube-v1` 已经把"真实接触失败结构 + grasp 真值判据"以**零资产、43k steps/s**的成本给到了（§5.1、B2 §7.1）。
**同时裁定**：`ReplicaCADRearrange`（1.49 GB）资产下载**停**，已下的 0.16 GB 余量留档不删；
`ReplicaCAD_SceneManipulation-v1` 不再作为候选任务。

### 5.3 裁定 38.7：两个无智能体前缀的探针目录 —— **批准作为基础设施事实引用**，名字不改，但要补申报
`runs/infra/maniskill_state_probe_20260929/`、`runs/infra/robosuite_throughput_probe_20260929/`。
**裁定**：① 其**基础设施事实**（12 核 CPU 配额、`nproc=112` 不可用作分母、state 档可跑 / 像素档 ❌、
零资产任务矩阵 11/12、`SO100GraspCube-v1` 判据、三条下载通道坑）**准予引用**，D 本轮已在
`work/project_parameters.json` 与 A2/B2 执行单中引用；② 其**能力结论一律不采信**（它没跑过任何 policy）；
③ **目录名保持不改**（D 的引用已按此路径写；改名会让引用悬空）；④ 作者须在 README §0 补**作者 / 写入面 / 边界**三行；
⑤ 该线**冻结**，与 A/B/C 同批；其两个下载工具（`hf_mirror_fetch.py` / `hf_mirror_snapshot.py`）**移交 A2**（G1 直接用）。
