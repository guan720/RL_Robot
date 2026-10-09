# RL_Robot 学习与研究路线图

> 生成时间：2026-09-22 · 基于对本机与团队已有仓库的实际核对，不是通用模板。

## 0. 结论先行

**第一个项目不是 RoboRSI，也不是先读完论文，而是在轻量仿真里跑通一个"能看到参数变化"的 RL 闭环。**

顺序：`最小 RL 闭环` → `正反向交替 / reset-free` → `py_trees harness + 技能版本化` → `迁到 Genie Sim + Genie G2` → `LLM 诊断 / 干预学习`。

理由：harness 的价值只有在下面已经有一个可训练、可独立评测的策略层之后才成立。先上多智能体自进化框架，会把「环境问题 / 模型 API 问题 / 框架问题」混在一起，出问题时无法定位。

补充：RoboRSI 源码已在本地 `../RoboRSI`（commit `9b644d2`），逐项核对结论见 [`docs/notes_roborsi.md`](notes_roborsi.md)。它需要**独立的 py3.12 环境**（`[libero]` extra 钉死 `robosuite==1.4.0` / `gym==0.25.2` / `mujoco==3.3.0`，与本项目环境互斥）和一个 OpenAI 兼容的 LLM 端点，所以排在阶段 4，不是第一步。

## 1. 本机环境核对结果（2026-09-22 实测）

| 项目 | 实际情况 | 对计划的影响 |
| --- | --- | --- |
| 节点 | Ubuntu 22.04.4，112 core，~2 TB RAM | 不是 Windows，**不需要 WSL2** |
| GPU | 1 × A800-SXM4-80GB（CUDA 13.1 driver，torch cu124） | 单卡足够做 Reach / PickPlace 级别 RL；并行采样优先 ManiSkill3 |
| Python | conda base `/opt/conda`，Python 3.11.9，torch 2.4.1+cu124，jax 0.10.2 | 用 venv `--system-site-packages` 直接复用 torch，省一次大安装 |
| ROS | **未安装**（`/opt/ros` 为空） | MoveIt / BehaviorTree.CPP / ROSA 暂时都用不了，先不碰 |
| Docker | **本节点没有 docker，也没有 nvidia-container-toolkit** | Genie Sim 官方主路径（Isaac Sim 5.1 + ROS 2 Jazzy 容器）**在这台机上跑不起来**，需要另找节点 |
| pypi.org | 直连失败 | 已配 USTC/aliyun 镜像，`pip` 可用（实测 `mujoco 3.13.0` / `robosuite 1.5.2` / `gymnasium 1.3.0` / `stable-baselines3 2.9.0` / `py-trees 2.6.0` / `mani_skill 3.0.1` 均可拉到） |
| huggingface.co | 直连失败，**hf-mirror.com 返回 200** | 任何 HF 下载前必须 `export HF_ENDPOINT=https://hf-mirror.com` |
| github.com | 200，可 clone | 框架源码可直接拉 |
| 现有 RL 依赖 | 9 个 conda env 里**都没有** mujoco / robosuite / gymnasium / lerobot | 必须新建环境，别在 base 里乱装 |

### 团队已有、应当复用的资产

| 路径 | 内容 | 怎么用 |
| --- | --- | --- |
| `../Agibot_path_IK/genie_sim` | AgiBot **Genie Sim 3.2.0** 源码：Isaac Sim 5.1 + ROS 2 Jazzy，机器人是 **Genie G2**（含 MoveIt 2 + WBC），benchmark 200+ 任务、VLM 自动评测、RoboColiseum 排行榜，技术报告 arXiv:2601.02078 | 阶段 4 的落地平台。`geniesim_benchmark` 已有 `BaseEnv.reset/step/get_observation` 与 `tasks/base_task.py` 的成功判定 → 天然是 gym 风格，可包成 RL env |
| `../Agibot_path_IK/ik_motion_planner.py`、`batch_episode_ik.py` | G2 上已验证的 IK / RRT 与跨机器人 SE(3) 相对位姿重定向（结论：直接搬绝对 TCP 位姿 0/8 成功，相对重定向后可行） | 阶段 4 的动作接口与恢复动作直接复用，别重写 IK |
| `genie_sim/.../utils/ikfk_utils.py` | `IKFKSolver`、`get_shared_ikfk_solver` | 同上 |
| `../../yhzhang91/vla_pipeline` | 团队 VLA 数据/训练流水线（含 tests、dags、docs） | 需要模仿学习基线（ACT / DP）时的数据来源与工程范式 |
| `../../lomoon_claude/robosuite-master` | robosuite 源码副本 | 读 action space / 成功判定实现时离线参考 |
| `../Subtask_dec`、`../rep_ego2robot` | VLM 子任务决策、ego→robot | 阶段 4 的 LLM 诊断 / Planner 侧可对接 |
| `../RoboRSI` | RoboRSI 多智能体自进化 harness（commit `9b644d2`）。内嵌 LeRobot 分支，已带 `policies/sac/`（含 `reward_model/`）、`rl/buffer.py`、`examples/tutorial/rl/hilserl_example.py`、`reward_classifier_example.py`；技能分层含 `reset_success` / `reset_failure` 相位 | 阶段 4 的上层框架；HIL-SERL 与奖励分类器的参考实现直接读它的 examples |

**目标机器人已经明确是 Genie G2**，不是通用 Franka。所以：学习阶段用通用仿真（robosuite/ManiSkill）打基础，评测与 sim2real 终局用 Genie Sim + G2。

## 2. 五个阶段

### 阶段 0 · 环境与仓库骨架 ✅ 已完成（2026-09-22）

- 建 venv（复用 base 的 torch），固定 `requirements.txt`。
- 建目录骨架（见 §3），约定「一次实验 = 一个 run 目录」，记录 config + seed + git commit。
- **产出**：`scripts/env_check.py` 打印版本、跑 100 步随机策略、存一张观测图。
- **验收**：能在不联网的情况下重跑成功。
- **实测结果**：`bash scripts/setup_env.sh` 可复现；`python scripts/env_check.py` EXIT=0 全绿（EGL 渲染成功、平均像素 108.5 非黑屏、Reach 跑通、robosuite 19 个任务、CUDA True）。踩坑与版本钉全部记在 [`notes_env.md`](notes_env.md)。

### 阶段 1 · 最小 RL 闭环 🔄 进行中（1a 已完成，1b 已跑通）

- 环境：**robosuite**（MuJoCo，资产自带、无需 HF 下载，抓取语义接近真机）；需要大规模并行采样时再上 **ManiSkill3**（SAPIEN，GPU 并行，A800 上吞吐高，但资产要走 hf-mirror）。
- 任务：`Reach` → `Lift` → `PickPlaceCan`。**先用状态观测，图像放后面**。
- 算法：直接用 `stable-baselines3` 的 SAC/PPO，不要自己实现。
- 必须写进 `docs/notes_stage1.md` 的 5 个问题：obs 是什么 / action 是关节角还是 EE 增量还是绝对位姿、哪个坐标系、单位 / reward 谁给 / 终止条件 / 训练前后到底哪份参数变了。
- **产出**：学习曲线 + 固定 seed 的 20 回合评测（训练前 vs 训练后成功率）+ 一段视频。
- **验收**：`success_after > success_before`，且能指着曲线解释为什么。
- **实测结果**：1a 冒烟通过（robosuite 1.5.2 `Lift`+`Panda`，1000 步随机策略，录出 1000 帧 256×256 视频，成功率 0%——符合预期）；1b SAC 训练见 [`notes_stage1.md`](notes_stage1.md)。
- **顺手做的阶段 3 预览**：`scripts/demo_harness_tree.py` 用 py_trees 把「正向/反向/恢复/接管」搭成了一棵能跑的行为树，不需要 ROS 和仿真器，先用它理解 harness 是什么。

### 阶段 2 · 正反向交替 / reset-free ✅ 已完成（2026-09-22，详见 [`notes_stage2.md`](notes_stage2.md)）

- 自己写 `BidirectionalPickPlace` 包装：A→B 成功后自动切 B→A，用反向任务本身当「复位」。
- **覆盖率统计**：把 A/B 的目标位置离散成网格，记录访问过的格子数 → 直接验证「交替 ≠ 遍历」。
- 恢复流程先用**规则式**（超时/掉落 → 回 home → 重置物体），不要一上来就 LLM 接管。
- **产出**：`覆盖率 vs 训练步数` 图 + 正/反向各自成功率曲线 + 对照实验（固定复位 vs 交替复位，相同交互预算）。
- **验收**：能回答「交替是否更快？代价是什么？谁负责当两者都失败时的复位？」
- **实测结果**（`envs/bidirectional_pickplace.py` + `eval/transport_eval.py` + `scripts/compare_reset_modes.py` / `train_transport.py` / `plot_stage2.py` / `render_transport_video.py`）：
  - **Q1 交替更省**：省下的复位数 = 成功任务数。可靠策略下 0 次 vs 2727 次复位，含复位成本吞吐 **181.4 vs 26.8** 任务/千等效步（6.8×）；每任务步数 5.5 vs 7.3（物体就停在上一轮放置点，空行程更短）。策略不可靠时优势消失（150 vs 232 次复位）。
  - **Q2 代价 = 起始状态多样性**，但**塌缩需要两个条件叠加**：策略只在部分区域可靠 + 救场把物体摆回固定 home 点。此时起始格子 25.0/36、起始熵 0.609（对照组 33.3/36、0.690）。策略处处可靠时交替**零代价**（36/36、熵 0.994 vs 0.991）。可靠度扫描（8%→83% 舒适区）显示：越可靠，交替的收益越大、代价越小。
  - **Q3 兜底复位 = 规则式救场**：连续 `stall_limit=120` 步无 task 完成 → 摆回源区域并记账 `manual_resets`（随机策略下每 20000 步触发 ~140 次）。**救场把物体摆哪，本身就是 reset-free 的学习分布设计变量**（resample 起始熵 0.937 vs home 0.609）。
  - **SAC 两条课程各训 60000 步（13.5 分钟 / 74 步每秒）**：alternate 课程 3637 任务、98.6% 成功率、正/反 1830/1807、救场 0、起始覆盖 36/36（熵 0.994）；相变在 7500–10000 步。跨模式冻结评测显示两条课程收敛到**可互换**的策略（98.6% vs 98.1%），说明本环境里交替没有牺牲泛化——但训练后策略恰好打平 20 行比例控制器的上界，**说明该抽象环境已到天花板，下一步必须加难度**。
  - **留下的三个插槽**（阶段 3 直接接）：救场复位 → 恢复技能子树；`start_cell_counts` → 主动采样/复位位置选择；`evaluate_transport()` → 发布门禁（阈值必须同时含成功率、起始熵、救场次数）。
  - **加难度重跑（2026-09-23，✅ 抽象 2D 版完成）**：`envs/transport_perturbed.py` 继承基类只覆写五个钩子（1 步延迟 / 每局增益抽签 / 常值漂移 / 负载降速 / 进圈限速撞飞 / 搬运滑落），难度由 `scripts/calibrate_transport.py` 标定（随机 0%、最强脚本 85.5%）。扰动下**交替不再免费**（处处可靠的控制器也要付 ~55 次救场）、**随机探索 0 任务**导致相变从 7.5k 推迟到 65k 步、pd 示范预填 10k 步把样本效率拉回 ~3×（预填 40k 反而更差；旧环境模型 naive fine-tune 先退化 83%→33%→59%）；策略四成可靠也没塌缩，塌缩开关仍是救场摆法（home 下起始熵 0.966→0.790）。SAC 43.2% vs 脚本上界 84.1% → RL 终于有了可测量的差距。详见 [`notes_stage2.md`](notes_stage2.md) §9。

### 阶段 2.5 · robosuite 物理分辨任务 🔄 进行中（2026-09-23 新设，详见 [`notes_vision.md`](notes_vision.md) 与 [`plan_alignment_2026-09-23.md`](plan_alignment_2026-09-23.md)）

- 定位：抽象环境已冻结机理结论；接触物理 + 真实成功判定是下一档分辨力。当前主战场。
- 队列：V0 state（稀疏 vs shaped 两臂在跑）→ 脚本式 pick-place 控制器 + 示范预填（RLPD 式混合比扫描）→ 残差三臂对照（base-only / 从零 / base+有界残差）→ V1 像素同预算对照。
- 纪律：成功只用 `info["success"]`；每臂同预算冻结评测；一次只换一层（策略/数据/环境/算法）。

### 阶段 3 · harness 上层 + 技能版本化（2–3 周）

- `py_trees` 行为树：`正向搬运 →(成功)→ 反向搬运 →(失败)→ 恢复 →(恢复失败)→ 记录并请求接管`；黑板存物体位姿、当前技能版本、失败类型。
- 策略封装成 skill 接口：`skill(obs) -> action` + `meta`（版本、训练配置、评测分数）。
- 最小 CI：`train.py` → `eval.py` → 通过才写入 `registry/<skill>/<version>/`，否则保留旧版本。
- **两种学习分开记账**：技能代码/规则变更 vs 策略参数变更，各自留消融，否则永远说不清提升来自哪。
- **产出**：一次全自动运行日志，能沿调用链解释一次成功、一次失败、一次版本回滚。
- **验收**：旧任务回归不掉点（同时保留「累计覆盖」和「冻结版本单次成功率」两种指标）。

### 阶段 4 · 接 RoboRSI 与真实平台（之后，按需展开）

前置条件：阶段 3 稳定 + 一个能用的 OpenAI 兼容 LLM 端点 + 一台**有 docker 和 nvidia-container-toolkit 的 GPU 节点**。

1. **单独建 py3.12 环境跑 RoboRSI**，与本项目 `rlrobot` 环境并存、绝不合并（依赖版本互斥）。第一步三条命令：`pip install -e ".[dev,web]"` → `roborsi onboard` → `roborsi status`，然后 `roborsi web` 看 `:8787` / `:8795` 两个面板。
2. **RL 训练栈直接用它内嵌的 LeRobot 分支**：`roborsi/embodied/engine/src/lerobot/policies/sac/`（含 `reward_model/`）+ `examples/tutorial/rl/hilserl_example.py`（SACPolicy、online/offline 双 ReplayBuffer、learner/actor 双进程 mp.Queue）。注意示例里 `device="mps"` 要改 `cuda`，默认机器人是 SO100，换 Genie G2 要自己实现 `make_robot_env`。
3. **训练触发方式照抄**：`roborsi/embodied/command/builder.py` 把「manifest + params」翻译成 `lerobot-train` 的 CLI argv —— 这就是阶段 3「训练触发器」的成熟形态。
4. **技能分层对齐它的 taxonomy**：`base/<robot>/<primitive>` → `atomic/<task>/{zeroshot,train,eval,reset_success,reset_failure}` → `long_horizon/<task>/{plan,progress_judge,posttrain}`。其中 `reset_success` / `reset_failure` 正是我们「正反向交替 + 失败救场」的现成插槽。
5. **评测纪律照抄 `docs/EVALUATION.md`**：`evolve` / `eval` 双模式；成功标签只认仿真器判定；append-only journal + 独立 `roborsi eval-audit` 重算；失败分三类（任务失败 / `infra_count` / `implementation_error_count`）不混算。
6. **Genie Sim + Genie G2**：走 `geniesim docker build/up/into`，用官方 benchmark 的成功判定；动作接口复用 `Agibot_path_IK` 的 IK 与相对位姿重定向结论（绝对 TCP 位姿直搬 0/8 失败）。
7. **感知先摘出去**：`../RoboRSI/docs/capx-pickplace-lessons.md` 的结论是纯视觉抓取成败首先取决于定位可靠性（LIBERO-PRO 上 OpenVLA/π₀ = 0%，π₀.₅ ≈ 13%，CaP-Agent0 = 18%，ASPIRE ≈ 72%）。所以阶段 2 先用仿真真值观测，等 RL 闭环跑通再单独引入视觉并做对照。
8. VLM 评分必须单独做校准实验（与仿真真值对比，统计误判率），否则一定出现 reward hacking。真机阶段保留人工安全监督。

## 3. 目录骨架与约定

```
RL_Robot/
├─ docs/          # 本文件 + notes_stage*.md + 论文笔记
├─ configs/       # 每个实验一个 yaml，禁止把超参写死在代码里
├─ envs/          # 环境包装（BidirectionalPickPlace 等）
├─ skills/        # 技能接口实现 + meta
├─ policies/      # 训练脚本 / 模型定义
├─ harness/       # py_trees 行为树、调度、恢复
├─ registry/      # 已发布技能版本（带评测分数，只增不覆盖）
├─ eval/          # 独立评测脚本（与训练解耦）
├─ scripts/       # env_check / 冒烟测试 / 一次性工具
└─ runs/          # 每次运行的日志、曲线、视频（按日期+来源命名，便于回收）
```

工作区硬性约定（继承 yhzhang91 全局规则）：**禁止 `rm`**，清理一律 `mv` 到 `/workspace/mnt/sppro/yhzhang91/recycle_bin/`；不碰 `.../yhzhang91/datasets`。

## 4. 常用命令

```bash
# --- 阶段 0：建环境。别手敲 pip install，版本钉有讲究，直接跑脚本 ---
bash scripts/setup_env.sh                 # 建 venv + 按钉好的版本装 + 自动自检
source /root/venvs/rlrobot/bin/activate
export HF_ENDPOINT=https://hf-mirror.com  # HF 资源（ManiSkill 资产 / LeRobot 数据集）必须走镜像
export MUJOCO_GL=egl                      # 离屏渲染用 GPU；失败改 osmesa

# --- 阶段 1a：冒烟（看懂 obs / action 语义 + 录视频）---
python scripts/env_check.py
python scripts/smoke_random_policy.py --task Lift --episodes 1

# --- 阶段 1b：第一个 RL 实验（本机实测 54.6 分钟，CPU 被共享任务占满）---
python scripts/train_reach.py --steps 5000                 # 先冒烟，几分钟
python scripts/train_reach.py --config configs/reach_sac.yaml   # 全量 50000 步
python scripts/show_curve.py --latest                      # 不开 tensorboard 也能看曲线
python scripts/eval_policy.py --ckpt runs/<run>/model_final.zip --episodes 100 --seed 999
python scripts/eval_policy.py --ckpt runs/<run>/model_final.zip --episodes 100 \
       --max-steps 50 --goal-radius 0.02                   # 严酷探针：收紧条件再看一遍

# --- 阶段 2：正反向交替 / reset-free（对照实验不需要训练，~5 分钟）---
python scripts/compare_reset_modes.py --recovery-modes resample,home      # 表 A/B/C + 可靠度扫描
python scripts/train_transport.py --mode alternate                        # reset-free 课程，~14 分钟
python scripts/train_transport.py --mode fixed                            # 人工复位对照课程
python scripts/plot_stage2.py --latest --open                             # 覆盖热力图 / 扫描 / 学习曲线
python scripts/render_transport_video.py --run runs/<刚才的 run>            # 交替 vs 人工复位 并排视频

# --- 阶段 3 预览：harness 长什么样（不需要 ROS / 仿真器）---
python scripts/demo_harness_tree.py --ticks 8
python scripts/demo_harness_tree.py --tree                 # 只看树结构
```

## 5. 风险与红线

- **本机无 docker** → Genie Sim 阶段 4 之前不要尝试，先确认能拿到合适的 GPU 节点。
- **HF 被墙** → 所有下载走 `hf-mirror.com`，否则会在阶段 1 之后卡住。
- **指标混淆** → 「累计覆盖 95/120」≠「冻结策略单次成功率」。两种指标都要留，否则会用累计覆盖掩盖旧任务退化。
- **一条轨迹 ≠ N 次独立交互** → 看到「1 条纠正轨迹 → 2432 样本」这类数字要问清楚是切片还是独立交互。
- **不要在 base env 装包**，也不要动别人 env；`runs/` 按来源命名便于以后回收。
- **延迟队列 off-by-one（2026-09-23 发现）**：`deque(maxlen=k)` 的实际延迟是 k-1，`action_delay=1` 会退化成无延迟。`envs/transport_perturbed.py` 已修（`maxlen=k+1`）；**`envs/reach_perturbed.py` 同款未修**（阶段 3 文件），阶段 3 任何「长延迟」结论重跑前先修它。

## 6. 本周进度

1. ✅ 阶段 0：建 venv + 目录骨架 + `env_check.py`（全绿）。
2. ✅ 阶段 1a：robosuite `Lift` 随机策略跑通 + 录视频；obs/action/reward 笔记见 `notes_stage1.md`。
3. ✅ 阶段 1b：SAC 训 Reach，拿到学习曲线 + 训练前/后固定 seed 对比。
4. ✅ 阶段 2：`BidirectionalTransport2D`（正反向交替 + 36 格覆盖统计 + 规则式救场）、对照实验（3 策略 × 2 复位模式 × 2 救场方式 × 3 seed + 可靠度扫描）、两条课程的 SAC 训练与跨模式评测、5 类图 + 4 段视频。结论见 [`notes_stage2.md`](notes_stage2.md)。
5. ✅ 给阶段 2 的环境加难度（抽象 2D 版）：扰动环境 + 难度标定 + 三张表重跑 + 从零/示范预填/微调/速度观测四组训练对照，结论见 [`notes_stage2.md`](notes_stage2.md) §9。
6. ⬜ 下一步：把加难度搬到 robosuite `PickPlaceCan` / Genie Sim + 视觉观测，指标口径不变地重跑三张表；同时补「示范预填 × 固定复位课程」的干净 A/B（`runs/20260923_125608_*_fixed60k`）。
7. ✅ 视觉路线探针与最小闭环（2026-09-23）：`scripts/probe_pickplace_can.py` 量出渲染成本（state 94 fps / 单相机 64² 8.5 fps / 双相机 84² 5.7 fps）与 robosuite 1.5 接口坑；发现并绕开「TF × llvmpipe 同进程 segfault」红线；`envs/robosuite_pickplace.py` + `scripts/train_pickplace_sac.py` 搭好 state/pixels 双观测 SAC 入口，V0（state 100k）在跑。详见 [`notes_vision.md`](notes_vision.md)。
8. ✅ 方案对齐分析（2026-09-23）：对照 `research-survey-2026-09-23.md` 逐项判断借鉴/改造/缓行，重切分阶段（新增 2.5、阶段 3 按 ENPIRE 两阶段重切、阶段 4 改序），见 [`plan_alignment_2026-09-23.md`](plan_alignment_2026-09-23.md)。

论文按阶段配给（不要一次读完）：阶段 1 → Gymnasium 文档 + SAC；阶段 2 → reset-free RL / forward-backward 策略；阶段 3 → SayCan、Code as Policies、VoxPoser，此时再重读 RoboRSI 的 TSR 分层；阶段 4 → ACT / Diffusion Policy、SERL / HIL-SERL、Genie Sim 技术报告（arXiv:2601.02078）。
