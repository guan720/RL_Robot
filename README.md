# RL_Robot

机械臂强化自学习的最小起点：先在一个几十行的 Reach 环境里把 RL 闭环跑通，再逐步接抓取、接 harness、接真机平台。

完整路线与依据见 [`docs/ROADMAP.md`](docs/ROADMAP.md)，概念解释见 [`docs/notes_stage0.md`](docs/notes_stage0.md)。

## 快速开始

> **先激活环境，否则所有脚本都会报 `ModuleNotFoundError`。**
> 终端提示符是 `(base)` 就是错的（conda base 里没装 py_trees / gymnasium / robosuite / SB3）；
> 激活后应该变成 `(rlrobot)`。
> 所有脚本已内置检查，忘了激活会直接打印修法而不是甩 traceback（见 `scripts/_venv.py`）。

```bash
# 1. 激活环境（已用 --system-site-packages 复用 base 的 torch 2.4.1+cu124）
source /root/venvs/rlrobot/bin/activate
#    不想 activate 也行，直接用绝对路径的解释器：
#    /root/venvs/rlrobot/bin/python scripts/xxx.py

# 2. 自检：版本 / GPU / MuJoCo 离屏渲染 / RL 接口
python scripts/env_check.py

# 3. 阶段 1a：robosuite 随机策略冒烟 + 录视频（看懂 obs 和 action 的语义）
python scripts/smoke_random_policy.py --task Lift --episodes 1

# 4. 阶段 1b：第一个真正的 RL 实验（Reach + SAC）
python scripts/train_reach.py --steps 5000                      # 冒烟，几分钟
python scripts/train_reach.py --config configs/reach_sac.yaml   # 全量 50000 步，实测 54.6 分钟
#    本机是共享节点，长任务请后台跑：
#    setsid nohup python -u scripts/train_reach.py --config configs/reach_sac.yaml \
#        > /tmp/train.log 2>&1 < /dev/null & disown

# 5. 看曲线（不需要 tensorboard）
python scripts/show_curve.py --latest

# 6. 独立复评（换一批 seed，验证不是过拟合评测集）
python scripts/eval_policy.py --ckpt runs/<刚才的 run>/model_final.zip --episodes 100 --seed 999

# 7. 严酷探针：把成功圈收紧到 2cm、步数上限砍到 50，再看一遍
#    （默认条件下随机策略就有 ~19% 成功率，只看「涨了」说明不了学到东西）
python scripts/eval_policy.py --ckpt runs/<刚才的 run>/model_final.zip --episodes 100 \
       --max-steps 50 --goal-radius 0.02

# 8. 阶段 3 预览：harness 到底长什么样（py_trees 行为树，不需要 ROS / 仿真器）
python scripts/demo_harness_tree.py --ticks 8

# 9. 把结果「看见」：4 张结果图 + Reach 动画 + 真实物理仿真里的抓取成功
python scripts/plot_results.py --run runs/20260922_170720_sac_reach --explain
python scripts/render_reach_video.py --run runs/20260922_170720_sac_reach --steps 45
MUJOCO_GL=egl python scripts/demo_scripted_lift.py --episodes 2 --verbose

# 10. 阶段 3：把已训好的模型过门禁、发布进版本库（只增不覆盖）
python scripts/publish_skill.py --ckpt runs/20260922_170720_sac_reach/model_final.zip \
       --skill-name reach_sac
python scripts/publish_skill.py --list          # 看版本库里有什么

# 11. 阶段 3：跑一次完整的自学习闭环（采集->诊断->训练->独立评测->门禁发布）
python scripts/run_harness_loop.py --mode diagnosed --budget-steps 2500 \
       --steps-per-round 600 --episodes 5 --rounds 3        # 冒烟，约 30 秒

# 12. 阶段 3：A/B 对照——诊断+针对性采样 是否比固定均匀采样学得更快
python scripts/compare_harness_ab.py --budget-steps 2500 --steps-per-round 600 \
       --episodes 5 --rounds 2                              # 冒烟
python scripts/compare_harness_ab.py --seeds 0 1 --out runs/ab_stage3/run1 \
       --aggregate-only                                     # 跑崩了不用重跑，直接重算

# 13. 标定扰动环境（找一个手写控制器不满分、RL 有活可干的基准）
python scripts/calibrate_perturbed.py --episodes 50

# 14. 阶段 3 自检：8 项，不训练不联网，几秒钟。改完任何一层先跑它
python scripts/selfcheck_stage3.py -v
```

**阶段 2（正反向交替 / reset-free）的命令与结果在下面单独一节，或直接看 [`docs/notes_stage2.md`](docs/notes_stage2.md)。**

**「怎么看见学习、成功到底怎么判定」的完整讲解见 [`docs/notes_stage1_visual.md`](docs/notes_stage1_visual.md)。**

每一步在做什么、输出怎么读，见 [`docs/notes_stage1.md`](docs/notes_stage1.md)。

**阶段 3（自学习闭环）的设计、实测数字与踩坑见 [`docs/notes_stage3.md`](docs/notes_stage3.md)。**

## 两条并行的线

| 线 | 目标 | 现状 | 入口 |
| --- | --- | --- | --- |
| A · RL 自学习地基 | 环境 / 奖励 / 策略 / 参数更新 / 独立评测 | 阶段 0-1 已跑通，Reach 100% | 本页 + `docs/notes_stage1.md` |
| B · RoboRSI harness | 看懂并试跑上层自进化框架 | 独立 conda 环境 `roborsi` 已装，`libero doctor` 退出码 0 | `docs/roborsi-trial-log.md`、`scripts/install_roborsi_minimal.sh` |

两条线**环境完全隔离**（A 用 `/root/venvs/rlrobot` py3.11 + torch 2.4.1+cu124；
B 用 `/opt/conda/envs/roborsi` py3.12 + torch 2.6.0+cpu + robosuite 1.4.0），
依赖版本互斥，**绝对不要合并**。最终在阶段 4 才把 B 的上层框架套到 A 的策略层外面。

## 当前最好成绩（2026-09-22 实测）

`runs/20260922_170720_sac_reach/model_final.zip` —— Reach + SAC，50000 步，54.6 分钟。

| 策略 | 成功率 | 平均步数 | 平均末距(m) |
| --- | --- | --- | --- |
| 随机策略 | 16.0% | 91.6 | 0.2115 |
| 未训练的网络 | 6.0% | 95.2 | 0.2768 |
| 训练后 | **100.0%** | **2.6** | **0.0083** |

换 3 个不同 seed、再收紧到「50 步 / 2cm 成功圈」的严酷探针，都仍是 100%。
直接复评：

```bash
python scripts/eval_policy.py --ckpt runs/20260922_170720_sac_reach/model_final.zip \
       --episodes 100 --seed 999
python scripts/show_curve.py --run runs/20260922_170720_sac_reach
```

## 阶段 2 · 正反向交替 / reset-free（2026-09-22 实测）

一个点当末端，在 30cm×30cm 桌面上把物体在 A 区（左）和 B 区（右）之间来回搬：
A→B 成功后自动切 B→A，**用反向任务本身当复位**，同时用 6×6 网格统计覆盖率。

```bash
# 对照实验：不需要训练，~5 分钟出三张表（成本 / 覆盖 / 可靠度扫描）
python scripts/compare_reset_modes.py --recovery-modes resample,home

# 两条课程各训一个 SAC（各 ~14 分钟，长任务记得 setsid nohup ... & disown）
python scripts/train_transport.py --mode alternate     # reset-free：起始状态由策略自己造成
python scripts/train_transport.py --mode fixed         # 对照：每个 task 人工复位

# 图与视频
python scripts/plot_stage2.py --latest --open
python scripts/render_transport_video.py --run runs/20260922_205625_sac_transport_alternate
python scripts/render_transport_video.py --policy biased --easy-radius 0.09 --recovery-mode home --steps 2000 \
       --out runs/20260922_205020_stage2_compare/transport_biased_home.mp4   # 看覆盖塌缩
```

`runs/20260922_205625_sac_transport_alternate/model_final.zip` —— SAC 60000 步 / 13.5 分钟 / 89736 参数。
冻结评测 = 3 seed × 20000 步、确定性推理（`eval/transport_eval.py`，与对照实验同一把尺子）：

| 策略 | 完成任务 | 每任务成功率 | 正/反 | 规则式救场 | 起始覆盖 | 吞吐(任务/千等效步) |
| --- | --- | --- | --- | --- | --- | --- |
| 随机策略 | 13.3 | 6.6% | 11 / 2 | 140 | 29.0/36 | 0.55 |
| 未训练的网络 | 0.0 | 0.0% | 0 / 0 | 150 | 18.0/36 | 0.00 |
| **训练后（交替课程）** | **3637.0** | **98.6%** | **1830 / 1807** | **0** | **36.0/36（熵 0.994）** | **181.85** |
| 手写比例控制器（上界参照） | 3627.3 | 98.6% | 1825 / 1802 | 0 | 36.0/36 | 181.37 |

三个验收问题的答案（完整证据与图表见 [`docs/notes_stage2.md`](docs/notes_stage2.md)）：

| 问题 | 结论 |
| --- | --- |
| **交替是否更快/更省？** | 省，且省下的复位数 = 成功任务数。可靠策略：0 次 vs 2727 次复位，含复位成本吞吐 181.4 vs 26.8（6.8×）；每任务步数 5.5 vs 7.3。策略不可靠时优势消失（150 vs 232） |
| **代价是什么？** | 起始状态多样性可能塌缩，但需要「策略只在部分区域可靠」+「救场摆回固定 home 点」两个条件叠加（起始格子 25.0/36、熵 0.609 vs 对照 33.3/36、0.690）。策略处处可靠时零代价（36/36、0.994） |
| **两者都失败时谁复位？** | 规则式救场：连续 120 步无 task 完成 → 摆回源区域并记账 `manual_resets`。**救场把物体摆哪，本身就是 reset-free 的学习分布设计变量**（resample 熵 0.937 vs home 0.609） |

两个必须记住的提醒：SAC 只是**打平**了 20 行手写控制器的上界 → 这个抽象环境已到天花板，下一步要加难度（视觉 / 接触物理）；
覆盖率和起始熵要**一直记着** → 98.6% 的成功率可以与 0.994 的起始熵共存，也可以与 0.6 共存，只看成功率发现不了「学会了但学窄了」。

### 加难度重跑（2026-09-23 实测）

理想环境里 SAC 打平脚本上界（98.6% vs 98.6%）→ 问题不可判定。于是新增
`envs/transport_perturbed.py`（**继承**基类，只覆写五个钩子，指标口径不变）+
`configs/transport_perturbed.yaml`，难度由 `scripts/calibrate_transport.py` 标定出来：
随机 0%、最强脚本 85.5%（1 步执行延迟 + 每局增益抽签 ±50% + 常值漂移 + 负载降速 +
进圈限速撞飞 + 搬运滑落，六旋钮互相拉扯，固定增益控制器表达不出增益调度）。

```bash
python scripts/calibrate_transport.py --filter D                 # 难度标定（~20 分钟/轮）
python scripts/compare_reset_modes.py --config configs/transport_perturbed.yaml \
       --policies perfect,biased,random,pd,ckpt                   # 扰动版三张表
python scripts/train_transport.py --config configs/transport_perturbed.yaml \
       --steps 60000 --demo-steps 10000 --demo-policy pd          # 示范预填 + SAC
```

| 策略（扰动环境 · alternate · 冻结评测 3 seed × 20000 步） | 完成任务 | 成功率 | 规则式救场 | 起始覆盖 |
| --- | --- | --- | --- | --- |
| 随机 | 0.0 | 0.0% | 150 | 18/36 |
| 手写 PD 控制器（脚本上界） | 565.3 | 84.1% | 57 | 36/36（熵 0.989） |
| SAC 从零 150k 步 | 118.7 | 40.7% | 122 | 36/36（熵 0.966） |
| **SAC + 示范预填 10k 步，训 60k 步** | **132.7** | **43.2%** | 123 | **35.7/36（熵 0.966，内生起始 43%）** |

三条新结论：**交替不再免费**——处处可靠的控制器在扰动环境里也要付 ~55 次 stall 救场
（理想环境是 0 次）；**随机探索完成 0 个任务** → 相变从 7.5k 步推迟到 65k 步，
用 pd 控制器预填 10k 步示范（SERL 式最小闭环）把样本效率拉回约 3×，而预填 40k 步反而更差、
拿旧环境满分模型 naive fine-tune 会先退化（83% → 33% → 59%）；**策略只有四成可靠也没有覆盖塌缩**
——塌缩的开关始终是「救场把物体摆哪」（同一策略换 home 救场，起始熵 0.966 → 0.790）。
完整证据、标定表与坑见 [`docs/notes_stage2.md`](docs/notes_stage2.md) §9。

## 目录

| 目录 | 作用 |
| --- | --- |
| `envs/` | 环境包装。`reach_env.py` 是手写的 6 维 Reach，用来看清 RL 接口；`bidirectional_pickplace.py` 是阶段 2 的正反向交替搬运（reset-free + 36 格覆盖统计 + 规则式救场）；`reach_perturbed.py` 加了执行延迟/增益噪声/漂移——默认 Reach 上手写比例控制就满分，A/B 问题不可判定，必须改动力学（理由见 `configs/reach_perturbed.yaml` 注释）；`transport_perturbed.py` 是阶段 2 加难度版（继承基类、只覆写五个钩子：延迟/增益抽签/漂移/负载降速/进圈限速/搬运滑落），难度由标定脚本定，指标口径与理想版完全一致；`robosuite_pickplace.py` 是 PickPlaceCan 的 gymnasium 包装（state/pixels 双观测、任务计数向阶段 2 看齐、成功只用 `info["success"]`），视觉路线见 `docs/notes_vision.md` |
| `configs/` | 每个实验一个 yaml，超参不写死在代码里。`reach_sac.yaml`(默认) · `reach_hard.yaml`(只收紧判定口径，已废) · `reach_perturbed.yaml`(阶段3对照基准) · `transport_sac.yaml`(阶段2：env/compare/train/eval 四段) · `transport_perturbed.yaml`(阶段2加难度：候选D 六旋钮 + 标定表注释) |
| `scripts/` | 可执行入口：自检 / 冒烟 / 训练 / 评测 / **画图 `plot_results.py`** / **录动画 `render_reach_video.py`** / **真仿真抓取演示 `demo_scripted_lift.py`** |
| | 阶段 2 入口：`compare_reset_modes.py`(交替 vs 人工复位对照 + 可靠度扫描) · `train_transport.py`(SAC + 训练中冻结评测 + 跨模式评测) · `plot_stage2.py`(覆盖热力图/扫描/学习曲线) · `render_transport_video.py`(动作 + 覆盖率积累视频) · `calibrate_transport.py`(难度标定：扰动预设 × P/PD 脚本基线族扫描) · 视觉路线：`probe_pickplace_can.py`(渲染成本探针+相机帧) / `train_pickplace_sac.py`(PickPlaceCan SAC，state/pixels 同入口) |
| | 阶段 3 入口：`run_harness_loop.py`(自学习闭环) · `publish_skill.py`(发布门禁) · `compare_harness_ab.py`(A/B 对照) · `calibrate_perturbed.py`(基准标定) |
| `eval/` | 独立评测模块（与训练解耦）+ `results/` 打分记录。`transport_eval.py` 是阶段 2 **唯一的指标定义处**（对照实验、训练评测、将来的发布门禁都调它） |
| `skills/` | ✅ 阶段 3 已实现：`base.py`(Skill / SkillMeta / EpisodeRecord / run_episode) · `reach_skills.py`(SB3 策略 / 比例控制 / 随机，三种来源同一个接口) |
| `harness/` | ✅ 阶段 3 已实现：`tree.py`(真 env + 真技能的行为树) · `diagnose.py`(失败标签→采样计划) · `sampling.py`(对照实验的唯一变量) · `trainer.py`(固定训练程序) · `loop.py`(闭环+预算记账) · `env_factory.py` |
| | 概念预览仍看 `scripts/demo_harness_tree.py`（假机械臂，讲控制流最清楚） |
| `registry/` | ✅ 阶段 3 已实现：`publish.py`(独立评测 + 严酷探针 + 门禁 + append-only)。已有 `reach_sac@v1`（标准 1.000 / 严酷 1.000） |
| `runs/` | 所有运行产物（日志、曲线、视频、result.json） |
| `docs/` | 路线图（`ROADMAP.md`）· 阶段笔记（`notes_stage0.md` 概念 / `notes_stage1.md` 实测 / **`notes_stage2.md` 正反向交替与覆盖率** / **`notes_stage3.md` 自学习闭环**）· 环境踩坑（`notes_env.md`）· RoboRSI（`notes_roborsi.md` 核对、`roborsi-callchain.md` 源码调用链、`roborsi-trial-log.md` 本机试跑记录） · 可视化与成功判定（`notes_stage1_visual.md`） · **训练内部机制（`notes_stage1_internals.md`）** |

## 本机注意事项

- pypi 直连不通，已配 USTC/aliyun 镜像；HuggingFace 直连不通，下载前 `export HF_ENDPOINT=https://hf-mirror.com`。
- 本节点没有 docker 也没有 ROS，Genie Sim（Isaac Sim 容器）暂时跑不了。
- 录视频依赖 MuJoCo 离屏渲染，默认 `MUJOCO_GL=egl`（GPU）；失败就换 `MUJOCO_GL=osmesa`。
- 本机是共享节点，`load average` 常在 600–1200，CPU 争抢是主要瓶颈；小网络训练已默认单线程（`OMP_NUM_THREADS=1`），GPU 对这个规模没用。
- 跑长任务用 `setsid nohup ... </dev/null & disown`，普通 `nohup ... &` 会被杀。
- 工作区规则：禁止 `rm`，清理一律 `mv` 到 `/workspace/mnt/sppro/yhzhang91/recycle_bin/`。
