# 最小抓取链路（min_grasp_pi05）

**这一轮只回答一个问题**：π₀.₅（或一个简单 BC policy）能不能从**一条固定示范的初态**出发，
把 can 抓起来并放进目标篮格？

范围刻意压到最小：单臂、单物体、固定初姿、同步执行、无 RL、无 LLM 评分/接管、无异步 chunk 调度、
无多门禁、无真机接口。双臂 / 正反向交替 / 多 seed / Harness / 纠正数据 / RL 微调都排在后面。

## 隔离边界（与仓内其它智能体对话互不干扰）

| 面 | 做法 |
| --- | --- |
| 代码 | 全部在本目录 `code/`，**不 import 仓内任何其它模块**（只 import 第三方库） |
| 环境 | 独立 venv `/root/mg_venvs/min_grasp`（从 `pi05_sim` 物理拷贝后改 shebang/activate，再装 robosuite），共享 venv 一律只读不写 |
| 数据 | 只用本目录 `code/mg_expert.py` 现采的示范，**不读仓内任何既有数据集**；只保留严格成功的 episode |
| 产物 | `data/` `runs/` `logs/` 都在本目录内 |
| 借用的只读公共设施 | EGL 驱动库前缀 `.codex-persist/egl-libs/590.48.01`、π₀.₅ 基座权重（硬链接进 `weights/pi05_base`，inode 不变）、torch hub 的 ResNet18 权重 |

## 目录

```
code/env.sh              # source 它：EGL 渲染 + HF 离线 + 本 venv 优先的 PATH
code/mg_env.py           # 单臂仿真包装（robosuite PickPlaceCan/Panda）+ 契约唯一真源
code/mg_expert.py        # 脚本专家（十段状态机，示范源 + 链路上界）；resume() = 档 5 接管用的「从当前状态续跑」
code/mg_probe.py         # 契约探针：确定性/动作轴向与增益/夹爪语义/图像/计时/专家/重放
code/mg_collect.py       # 采示范 -> LeRobotDataset(PNG, 非视频) + 原始 npz + 数据集卡片
code/mg_train.py         # 训练启动器（act / pi05 两条臂，同一份数据、同一评测口径）
code/mg_eval.py          # 闭环评测（从示范初态出发，成功率 + 视频 + 动作分布对照）
code/mg_smoke_pipeline.py# 假数据冒烟：数据集->训练->检查点->重载，不碰仿真
code/run_stage1.sh       # 阶段 1 一键跑通（6 步，每步是下一步的前置闸）
code/mg_sweep.sh         # 检查点扫描：每出一个检查点就按统一口径评一次，画过拟合曲线
code/run_pi05_r1.sh      # π₀.₅ 第 1 轮微调（fixed10 / batch4 / 3000 步）
code/run_pi05_r2.sh      # π₀.₅ 第 2 轮微调（fixed30n / batch8 / 4000 步）

# ── 档 1 起新增（多初始位姿 / 正反向 / 三 seed / 消融）──
code/mg_env_reverse.py   # 反向任务环境（can: bin2 象限 -> bin1 托盘，含自写成功判据）
code/mg_expert_reverse.py# 反向脚本专家（九相位 + 落定仪式；同时是反向链路上界）
code/mg_diag_miss.py     # 抓空几何定位（H1 横向偏 / H2 深度偏 / H3 时机偏），需重建初态
code/mg_tax_fail.py      # 失败分类账（A 没抓起 / B 没送到 / C 没落定），只读产物、不碰 GPU
code/mg_ceiling.py       # 专家上界（同一批 seed，训练前钉死，免得事后拿「专家也做不到」当挡箭牌）
code/mg_select_ckpt.py   # 关门检查点选择（只用 val，规则写死 + 曲线落盘，见坑 26/27）
code/mg_report.py        # 把所有读数汇总成一张 markdown 表
code/mg_probe_crossinstr.py # 交叉指令探针（语言 vs 视觉捷径）；--rescore 只重算标志位
code/mg_sweep_bidir.sh   # 档 2 双向检查点扫描（val 10 局，历史口径）
code/mg_sweep_rev.sh     # 档 2c 反向单任务扫描（val **20 局**，坑 27 换来的）
code/mg_verdict_s2.py    # 档 2 判定汇编（门1/2/3 + Fisher 记忆对照 + 六节修正口径），--selftest 8 项
code/mg_verdict_s2c.py   # 档 2c 判定（R1/R2/R3 + 护栏 G1/G2），--selftest 7 项
code/mg_lift_profile.py  # 抬升/松手高度画像（纯 CPU）：夹爪闭合段状态机 + 阳性对照 +
                         #   rule-of-three 二项检验，--selftest 61 项（见坑 31）
code/mg_g2_supp.sh       # 护栏 G2 加功效补读（40 局真训练 seed 5062..5071，发车前逐 seed 核对，坑 32）
code/mg_epoch_curve.py   # 跨 run 的 val 曲线按 **epoch** 对齐（steps/epoch 从 meta.json 反查并打印出处），
                         #   --selftest 35 项；只报趋势、不出判定（见坑 33）
code/mg_check_superset.py# 新数据集是不是旧集的**严格超集** + 留出 seed 碰撞闸，--selftest 18 项
code/chain_s2e_data.sh   # 档 2e 数据侧：重收 60 正向 + 120 反向 -> data/mix60f120r（R1/R2/R3 三个分支都要）
code/mg_verdict_s2e.py   # 档 2e 判定（P1/P2/P3 + 护栏 GA/GB/GC + GD 归一化漂移），--selftest 31 项
code/run_pi05_s2e.sh     # 档 2e 训练启动器：STEPS 按**等 epoch** 从 info.json 现算，不给就不发车
code/chain_s2e_train.sh  # 档 2e 训练+关门链；发车闸要求档 2c 判定「可用」（作废/悬空/矛盾一律 exit 6）

# ── 档 5 起新增（Harness 接管 / 纠正数据）──
code/mg_harness.py       # 检测器 + 接管器 + 片段缓冲（GraspDetector / SegmentBuffer / TakeoverHarness），
                         #   一局只许接管一次；档 5.1 起可选 hand_back=True（专家认输 ⇒ 关片段记账、交还策略、
                         #   本局不再二次接管；**默认关**，保护排队中链路的出身）；--selftest **261** 项
code/mg_eval_harness.py  # 档 5 评测入口（接管 / --observe-only / --detector-off），落 correction_segments_raw.npz；
                         #   只 **import** mg_eval.py 的 load_policy/to_tensor_obs，一个字都不改（它被档 3r 链 exec）
code/mg_calib_detector.py# 检测器阈值**离线**标定（拿已落盘 npz 复算 21 格网格，不占 GPU）-> runs/_diag/harness_calib.{md,json}
                         #   档 5.1 只加了**默认关闭**的 guard_w 参数（守卫已被标定否决，坑 50）；加完重跑对账：
                         #   runs/_diag/harness_calib_recheck_postguard.* 与锚除时间戳外逐字节相同
code/mg_resume_probe.py  # resume() 的真物理预检：carry / T1 抓空 / T3 滑脱，量「接管后还要多少步才成功」
code/mg_expert_resume_selftest.py # resume() 相位推断 + descend 停滞阶梯的纯 CPU 自测（假 env 桩），**86** 项
                         #   阶梯时间线钉在 BlockedDescendEnv 上：restage1@26 / restage2@61 / give_up@96
code/mg_g1_expert_regression.sh   # G1 护栏：改完 mg_expert.py 必须逐比特复现专家上界 20 局（本项目唯一可复现锚）
                         #   ⚠️ 它「有产物就跳过」⇒ 改完专家必须换 G1_NEW 输出目录，否则 PASS 是旧代码的（坑 49）
code/mg_g0a_equiv.py     # G0a 护栏：CPU 确定性（7 项）+ GPU **噪声地板**对照（坑 44 之后逐比特判据不成立）
code/mg_verdict_s5.py    # 档 5 判定（H1/H0/部分有效 + 按 (rep,seed) 配对的误接管/救回 + 归因分支），--selftest **37** 项
code/chain_s5_harness.sh # 档 5 链：G0a -> G0b 3×20 -> 正式 3×20 -> 判定；门禁全看盘上产物、每读「有产物就跳过」⇒ 可断点续跑
code/mg_diag_resume.py   # 档 5.1 诊断：接管段逐步落 can 真值 + 判据残差 + 「命令了多少 vs 实际动了多少」，
                         #   --selftest **45** 项；**不判门**，只为把「卡在 xy 还是 z」定案（见 S5_SUPPLEMENT 第五节）；
                         #   --reanalyze = 在**同一份 trace** 上离线重算统计口径（不重跑仿真、不占 GPU，原版自动留档）
code/mg_probe_stall_calib.py # 档 5.1 停滞窗长标定：干净专家跑（正/反各 20 局）+ 档 5 接管 trace 上扫 (T,W) 网格，
                         #   --selftest 12 项 -> runs/s5_1_stall_calib_{clean_rev,clean_fwd,trace}/；**不判门**，只定常数
code/mg_calib_guard.py   # 档 5.1「松手后守卫」窗长标定（结论 = **否决**，坑 50），--selftest 21 项 -> runs/_diag/guard_calib.{md,json}
code/mg_verdict_s5_1.py  # 档 5.1 判定：出身核对（坑 41/42）+ 机理门 M1~M5/G1/G2 + 配对四类拆账 + McNemar 精确 p，--selftest **32** 项
code/mg_probe_handback_ceiling.py # 档 5.2 · hand-back 杠杆的**算术天花板**（离线读盘上产物，不占 GPU、**不判门**）：
                         #   策略完成所需步数 S / 接管段三类结局 / 死循环覆盖诊断 / 「400−接管步−延迟 ≥ S」可救段数 + 敏感性，
                         #   --selftest **23** 项 -> runs/s5_2_handback_ceiling/handback_ceiling.{md,json}
code/chain_s5_1.sh       # 档 5.1 链：7 道发车闸（全看盘上产物，含 G1 产物 sha 对齐）-> 4×20 读数（--hand-back）-> 判定；
                         #   S51_GATES_ONLY=1 只验闸不开跑
code/chain_s5_timing.sh  # 档 5 实时性门（≤50 ms/step）的**隔离**读数；等 s5.done + s3r.done + GPU compute 表为空
code/chain_s3r_sweep_seed2000.sh # 档 3r FAIL 处方第 1 步：seed 2000 的 val 曲线（11 格 × 20 局）+ 与档 2e 的 epoch 对齐对表
code/chain_s3r_sweep_seed3000.sh # 档 3r FAIL 处方第 2 步：seed **3000** 的 val 曲线 + 与 seed1000/seed2000 的 epoch 对齐对表

# ── 档 6 起新增（失败机理归属 / 几何常数实测）──
code/mg_geom_taxonomy.py # 档 6 · A 类失败的**机理分桶**（纯离线、零 GPU），--selftest **65** 项。
                         #   六节：专家同口径参照 / N·L·H·D·X·F 六桶 / 各桶几何读数 / 可修上限 /
                         #   方向性（系统性偏置 vs 随机不准，concentration + 符号检验）/
                         #   空间分布（覆盖漏洞 vs 全局精度）+ x 方向增益回归（**判定只认按位置取均值那行**）。
                         #   合爪口径 import 自 `mg_diag_miss.close_transition`、A/B/C 口径 import 自
                         #   `mg_tax_fail`，**一个都不重写**（坑 54）。
code/mg_probe_grasp_geom.py # 档 6B · 从**真环境**测抓取几何常数（can 直径 / 全开 / 空合 / 手掌宽 / 支撑面 /
                         #   can 顶面 / 单侧指隙 vs `XY_TOL`），--selftest **11** 项 -> `runs/s6_grasp_geom/`。
                         #   不跑策略、不扫 D_CRIT（F 桶=0 ⇒ 测了也改不了决策）。
code/chain_s6_geom_a.sh  # 档 6 格 6A：三 seed 各 4 rep × 20 局的几何定位（复用 `mg_diag_miss.py`，零 GPU）
code/mg_seedcurve.py     # 多 run **配对**比较（零 GPU）：val 曲线符号检验 + 训练日志噪声画像 + 早筛回溯，
                         #   自测 **87** 项；epoch 网格与最近邻对齐**复用** `mg_epoch_curve`（冻结文件，只 import）
code/mg_probe_batch.py   # 档 7A · batch / gradient-checkpointing 的**代价探针**（s/step + 峰值显存 + 等 epoch
                         #   投影 + LR 自动缩放对账），自测 **68** 项 -> `runs/s7_probe/timing.md`
code/mg_probe_gradnoise.py # 档 7A-2 · **逐步**梯度噪声探针（`log_freq=1` + lr 1e-6 冻住参数点），
                         #   解 `E‖g_b‖²=G+C/b` 得 η_b，自测 **69** 项 -> `runs/s7_probe/gradnoise.md`
code/run_pi05_s7b.sh     # 档 7B 训练启动器：steps/save_freq/log_freq 由 `equal_epoch_plan` **现算并断言**，
                         #   传错就 FATAL（坑 33/60）；不给 STEPS 只打印换算过程
code/chain_s7_probe.sh   # 档 7A 发车链（含 GPU 余量闸 ≥60 GB，不抢别的实验的卡）
code/chain_s7b.sh        # 档 7B 发车链：10 条发车闸 -> 7A-2 -> 机理闸(MECH_NO 就 HOLD 不烧 7h) ->
                         #   训练 -> `last` 软链核对(坑 38) -> 11 格扫描 -> TEST+护栏 -> 配对分析 -> 判定
code/mg_verdict_s7.py    # 档 7B 判定（M1~M5 + 预注册 5 行判定表 + 出身核对），自测 **68** 项
code/mg_verdict_s7c.py   # 档 7C 判定（C1 极差**只读方向** / C2 使命门 / C3 早筛的**前瞻**验证），自测 **43** 项
code/mg_early_sentinel.py # 训练**在飞**时的早期哨兵（零 GPU）：按同样本窗逐点比 loss/grdn，阈值全部取自
                         #   预注册 M3（grdn 1.0 / 0.05、比值 1.5），连续 5 点才触发 ⇒ 只回答「这一发还要
                         #   不要继续烧」，**不产出判据读数**，自测 **37** 项
code/chain_s7c.sh        # 档 7C **条件发车**链：等 s7b.done -> 拿 S7_VERDICT.md 的命中行当闸 -> seed 1000/3000
                         #   各一发（同配方）-> 扫描 + TEST + 6 条曲线总览 -> S7C_VERDICT.md；闸不过写 s7c.SKIPPED
code/mg_verdict_s7f.py   # 档 7F/7G 判定（**一个工具两个模式**）：`--mode f` -> runs/S7F_DIAG.md（F1/F2 回溯表 +
                         #   触发判定 + 机器可读行 `7G_TRIGGER=YES|NO|UNKNOWN` + F3/F4 三分支归因 + 出身核对）；
                         #   `--mode g` -> runs/S7G_VERDICT.md（G1 主门 / G2 护栏 / G3 极差 + 行 `G1=PASS|FAIL`）。
                         #   常数全部写死自预注册（TRIGGER=40/80、无差别带 11 pp、有差别下限 12 pp、G_SEEDS=4000/5000/6000）；
                         #   `collect`/`ci`/`fisher_two_sided`/`spread` 一律 import 复用，**一个都不重写**（坑 54）。自测 **36** 项
code/chain_s7f.sh        # 档 7F 发车链：8 条闸 -> F1(坏 seed@018000) -> F2(另两个 seed 同格) -> 早期触发读数(_diag)
                         #   -> F3(bs8/5500 步，与 7B **同更新数**) -> S7F_DIAG.md -> 仅 `7G_TRIGGER=NO` 才续跑
                         #   F4(bs32/5500/lr1e-4，与 7B **唯一差 lr**) + 11 格扫描 -> 诊断重跑 -> s7f.done
code/chain_s7g.sh        # 档 7G **条件发车**链：等 s7f.done -> 闸读 S7F_DIAG.md 的 `7G_TRIGGER=YES` + 步数现算对账
                         #   (18000 = round(5803.25×3.102/2000)×2000) -> 新 seed 4000/5000/6000 各一发
                         #   (bs8/18000 步/save 2000) -> `last` 核对 -> 9 格扫描 -> TEST 4×20 + 正向 20
                         #   -> S7G_VERDICT.md -> s7g.done；不触发写 s7g.SKIPPED（坑 62）
code/chain_*.sh          # 各档自动发车链（预检 -> 训练 -> 扫描 -> 关门 -> 判定），完成判据一律是磁盘产物
code/chain_watchdog.sh   # 链路看门狗：每 10 min 一行心跳；链既不在跑、产物又没出现 => 写 logs/ALERTS.log
data/fixed10/            # 10 条固定初态示范（2290 帧）+ MG_DATASET_CARD.json
data/fixed30n/           # 30 条固定初态 + 专家噪声 0.05 的示范（6779 帧）
data/rand60/             # 档 1：60 条随机初姿正向示范（14415 帧）
data/mix60f60r/          # 档 2：正向 60（与 rand60 逐比特同源）+ 反向 60 = 120 条 / 30447 帧
data/mix60f120r/         # 档 2e（收集中，23:05 发车）：60 正向（与 mix60f60r 逐比特同源）+ **120** 反向 = 180 条
weights/pi05_base/       # π₀.₅ 基座（14.47 GB，硬链接，已按 HF 元数据校验）
weights/pi05_base_lr044/ # 基座的 lerobot 0.4.4 兼容副本（只改 3 份 JSON，权重是同 inode 硬链接）
weights/paligemma-3b-pt-224/  # π₀.₅ 的 tokenizer（HF 上 gated，只能本地化）
runs/                    # 探针证据、采集视频、训练与评测产物
runs/S2_VERDICT.md       # 档 2 判定（自动生成，源数据是 runs/s2_gate_* 与 runs/s2fix_*）
runs/_diag/tax_rev_test.md # 档 2 反向失败分类账（100 局）
runs/_diag/lift_profile.md # 档 2 松手高度画像：A 类=空合、B/C=松手太高（两种病）
runs/S5_PREREG.md        # 档 5 预注册（阈值 / 可行性天花板 / 归因分支 / 检查点为何不换，**先落盘后跑数**）
runs/_diag/harness_calib.md # 检测器标定报告（21 格网格、失败覆盖 25/25、T2 本轮不做的理由）
runs/_diag/tax_relaxed_summary.md # 三臂放宽口径失败分类账（档 5 的靶子：s2e 残余 25 = A10+B13+C2）
runs/S5_VERDICT.md       # 档 5 判定（自动生成：护栏 / G0b / 正式读数 / 归因分支 / 逐局明细）
runs/S5_SUPPLEMENT.md    # 档 5 **事后**补充分析（未预注册）：配对净收益 0、23 次接管结局分解、根因排除、档 5.1 处方
runs/S5_TIMING.md        # 档 5 实时性门的隔离读数判定（`chain_s5_timing.sh` 生成，等 GPU 独占）
runs/S5_1_PREREG.md      # 档 5.1 预注册（主判据 = **配对净收益 > 0**、机理门 M1~M5、功效表、四条分支；23:23 **先落盘后跑数**）
runs/S5_1_VERDICT.md     # 档 5.1 判定（`chain_s5_1.sh` 调 `mg_verdict_s5_1.py` 生成）
runs/_diag/guard_calib.md # 「松手后守卫」窗长标定（结论 = 否决：副门 4→≤1 一个窗长都没满足，坑 50）
runs/s5_1_stall_calib_clean_rev/ # 干净反向 20 局：T=0.1 mm 时最长停滞游程 **9** 步 ⇒ W=25 触发 **0/20**（阶梯不误伤）
runs/s5_1_stall_calib_trace/     # 档 5 接管 trace：死循环局停滞游程 **79 / 152** 步 ⇒ 稳稳触发；走到 grasp 的段最长只 14 步
runs/s5_1_g1_ceiling_rev_test20_n05/ # 停滞阶梯之后的 G1 逐比特回归锚（专家 sha16 `317c2b29…`，严格 14/20 ∧ 放宽 20/20）
runs/s5_diag_resume/     # 档 5.1 诊断产物（**重算版**，原版留档 `.pre_reanalyze_*`）：7015 = Z 被接触阻挡、7014 = XY 对不上且 can 静止
runs/s5_1_handback_rev_test20_k10{,_rep2,_rep3,_rep4}/ # 档 5.1 正式读数（4×20 = 80 格，出身全 ✅；npz 新增 `handback_at`/`n_restages`）
runs/S5_1_VERDICT.md     # 档 5.1 判定（自动生成）：**M1/M4 ❌ ⇒ 成功率不采信**；净收益 −2（救回 13/毁掉 15，p=0.8506）
runs/S5_1_SUPPLEMENT.md  # 档 5.1 **事后**补充分析（未预注册）：两个根因、因果足迹 3/80、算术天花板、留档偏离、三条处方
runs/s5_2_handback_ceiling/ # hand-back 的算术天花板（可救 **0/31**；AUC 0.573 = 时间预算不可分；上界 14/31 < 检出下限）
runs/s5_1_gates_FAILED   # 档 5.1 关门标记（printf 写、断言非空；**不是** `.done`：机理门未过）
runs/S3R_VERDICT.md      # 档 3r 判定：❌ FAIL（最差 seed2000 放宽 **41.2%** < 门 50%）；seed1000 68.8% / seed**3000** **80.0%**（严格 67.5%）
runs/_diag/epoch_curve_s3r_seed2000.md   # 档 3r FAIL 处方第 1 步：seed2000 的 val 曲线 = **「整条都低」**（5→35%，全程压在 seed1000 下）
runs/_diag/epoch_curve_s3r_seed3000_vs_seed{1000,2000}.md # 处方第 2 步：好 seed 是不是全程都好（决定能否用早期 val 探针筛坏 seed）
runs/_diag/tax_fwd_seed{1000,2000,3000}.md # 正向护栏的失败分类账：seed2000 = **A 类 16/16 = 100%**、16/20 局跑满 400 步
runs/S6_GEOM_PREREG.md   # 档 6 预注册（12:07 **先落盘**；第五节 12:50 追加并诚实标注「假设来自已读到的 r，斜率判据先钉」）
runs/S6_GEOM_A.md        # 档 6 主产物：三 seed 合并 **240 局**的机理分桶（A 类 41：X 26 / L 8 / H 6 / N 1 / **F 0**）
runs/_diag/geom_s3r_seed{1000,2000,3000}_rev.md # 同上，按 seed 拆开（seed2000 的 A 类 24 局里 L 桶占 8 = 接近段就崩）
runs/_diag/miss_s3r_seed{1000,2000,3000}_rev.json # 格 6A 的逐局几何读数（`mg_diag_miss.py` 产物，兼作 can 初态真值来源）
runs/s6_grasp_geom/geometry.{md,json} # **真环境实测**的几何常数：can 直径 50.17 mm / 全开 79.36 mm ⇒ 指隙 **14.59 mm = 1.82× XY_TOL**
runs/S6_VERDICT.md       # 档 6 判定：几何矛盾**不成立**、A 类 98% 是横向没对准、无覆盖漏洞、无可白修偏置 ⇒ 取消 10 h 重采方案
runs/s6_geom_a.done      # 格 6A 完成标记（printf 写 + `[ -s ]` 自检）
runs/_diag/seedcurve_sign_{strict,relaxed}.md # 三 seed 的**配对**符号检验 + 训练日志噪声画像 + 早筛回溯（坑 59 的出处）
runs/S7_PREREG.md        # 档 7 预注册（**13:55 先落盘**）：H7 与三条可检验预测、M1~M5 判据与 5 行判定表、
                         #   功效表、预算表、10 条发车闸、以及「本档明确不做什么」
runs/s7_probe/timing.md  # 档 7A：grad-ckpt 关掉必 OOM；bs8 1.374 s/step ↔ 历史 1.366；bs32 4.491 s/step、41.7 GB
                         #   ⇒ 等 epoch 墙钟 8h23m → **6h51m**；四档 batch 的 epoch 网格都是每格 0.3446
runs/s7_probe/gradnoise.md # 档 7A-2：**η₈ = 54.19%**、η₃₂ = 22.83%（G=86.34、C=817.2）⇒ 分支 `MECH_YES`
runs/s7_probe.done       # 档 7A 完成标记
runs/_diag/seedcurve_s7b_m1.md # M1 的配对读数（7B vs batch8-seed2000，放宽口径，9 格）
runs/_diag/seedcurve_s7.md     # 7D：batch8×3 + bs32 的曲线总览（同一组 epoch 格）
runs/S7_VERDICT.md       # 档 7B 判定（10-03 22:54 产出）：❌ **不采信（配方退化）** —— M1 0胜/7负/2平（H7 的 P2 被证伪）、
                         #   M2/M4 TEST 放宽 13/80=16.2%、M5 正向 1/20=5%，而 **M3 过了**（loss 0.0330）⇒ 坑 59 最强实证
runs/pi05_mix60f120r_s7b_bs32_seed2000/ # 档 7B 的 run（bs32 / 5500 步 / lr 2e-4 / log_freq 25 / seed 2000）
runs/s7b_bs32_seed2000_{rev,fwd}_test_rand20_k10* # 档 7B 的 TEST 关门读数（反向 4×20 + 正向护栏 1×20）
runs/_diag/s7b_early_sentinel.md # 7B **在飞**的哨兵读数（epoch 0.34 / 20 点）：state=OK、loss 比值 1.051、grdn 末值 0.224
runs/S7C_GATE.md         # 档 7C 发车闸读数（命中行 + M1~M5 抄件 + 决定；`chain_s7c.sh` 自动生成）
runs/s7c.done / runs/s7c.SKIPPED # 档 7C 的两种**终态**（坑 62：看门狗两个都认）。**实际走的是 SKIPPED**
                         #   （10-03 22:55，原因 = S7_VERDICT.md 含「不采信」）⇒ S7C_VERDICT.md 与
                         #   _diag/seedcurve_s7c{,_relaxed}.md **没有产出**，这是预注册分支，不是漏跑
runs/S7F_PREREG.md       # 档 7F/7G 预注册（**10-04 10:22 先落盘**）：7B 为什么崩的三个候选解释(H-A lr / H-B 步数 /
                         #   H-C 大 batch 本身)各配一个便宜的判别读数 + 决策树写死（F1∧F2 的 MIN3102 ≥40/80 才发 7G）
runs/s7f_seed{1000,2000,3000}_ep3102_{rev,fwd}_test_rand20_k10* # F1/F2：三个 batch8 seed 的 **018000（epoch 3.102）**
                         #   在 TEST 上（零训练、**回溯**诊断 ⇒ 只决定 22.4 h 值不值得花，不是使命门证据）
runs/_diag/s7f_trigger_interim.md # F1/F2 一齐就写的**早期**触发读数（比等 F3 早 ~2.5 h 知道 7G 发不发）
runs/pi05_mix60f120r_s7f_bs8_5500_seed2000/  # F3：bs8 / 5500 步 = 0.948 ep（与 7B **同更新数**）⇒ 只用于**排除** H-B
runs/s7f_bs8_5500_seed2000_{rev,fwd}_test_rand20_k10* # F3 的 TEST 读数（反向 4×20 + 正向 20）
runs/pi05_mix60f120r_s7f_bs32_lr1e4_seed2000/ # F4（**仅 7G 未触发时**）：bs32 / 5500 步 / lr **1e-4** = 与 7B 唯一差 lr ⇒ 判 H-A
runs/s7f_bs32_lr1e4_seed2000_{rev,fwd}_test_rand20_k10* # F4 的 TEST 读数
runs/S7F_DIAG.md         # 档 7F 诊断（`mg_verdict_s7f.py --mode f`）：F1/F2 表 + `7G_TRIGGER=` + F3/F4 归因 + 出身核对
runs/pi05_mix60f120r_s7g_seed{4000,5000,6000}/ # 7G：bs8 / **18000 步 = 3.102 ep** / **新 seed**（预算是回溯挑的 ⇒ 必须前瞻验证）
runs/s7g_seed{4000,5000,6000}_{rev,fwd}_test_rand20_k10* # 7G 的 TEST 关门读数（关门一律 `last`=018000，不做 val 选点）
runs/S7G_VERDICT.md      # 档 7G 判定（`--mode g`）：G1 主门（最差 seed 放宽 ≥50%，与档 3r/7C 同一条）/ G2 护栏 / G3 极差
runs/s7f.done / runs/s7g.done / runs/s7g.SKIPPED # 档 7F/7G 的终态（看门狗 done 与 SKIPPED 都认）
runs/S8_PREREG.md        # 档 8 预注册（**10-04 12:25 先落盘**，§9 增补 13:15）：纠正数据能不能把坏 seed 2000
                         #   从 41.2% 抬过 ≥50% 使命门。决策树 8A-0→8A→8B→8C→8C-ctl→8D 与全部阈值写死
runs/s8a_probe/append_probe.{md,json} # 格 8A-0（**零 GPU**）：「复制 + 追加」建集路线的四条断言，10-04 12:25 判 ✅ 过
runs/_smoke_s8_collect/{smoke_report,merge_report}.{md,json} # 采集器的 **stub 零 GPU 端到端预演**（10-04 13:00）：
                         #   采集（T1@8 触发→专家 249 步做完→截断 242 帧收下→回读自证）+ 合并（B1/B2/B3/逐比特）全过；
                         #   预演数据集已 rmtree 清理，不污染 data/
runs/_diag/s8a_yield_forecast.{md,json} # 格 8A 产出率的**事前**预测（10-04 14:15，`code/mg_forecast_s8a.py`，
                         #   零 GPU、只读档 5.1 的 80 局语料）：A2 三个点估计 35.7/15.2/17.0% 全低于门 40% ⇒
                         #   预测 `s8a.HELD`；机理读数「未到 grasp 且步数足够 = 0/12」⇒ 事前排除「抬 horizon」候选
runs/_diag/diagchk/VERDICT.md # `descend_diag` 改动的**零影响**验证（10-04 14:25~14:33，两版并跑 + **同版本两遍当基线**）：
                         #   结构量全等、`state`/`action`/索引列**逐比特相等**；图像不等但**基线同样不等**（702 vs 698 张、
                         #   最大差 2 灰阶、不随帧号增长）⇒ 渲染跨进程不确定（坑 70），非本改动引入；merge 五闸全 ✅
code/mg_diag_nograsp.py  # 「专家为什么到不了 `grasp`」的**离线**分类账（10-04 15:15，自测 **65/65**，零 GPU 推理）：
                         #   盘上 npz 的 `state[:,0:3]=eef` + 20 次 `env.reset(seed)` 重建 can 初态（交叉核对
                         #   `max|Δcan_z0|=1.11e-16`）⇒ 逐步几何区 S0~S4 + 相位无关归因 R0~R4/**RX**。**只透明、不进任何门**
runs/_diag/nograsp_corpus.{md,json} # 上面那个工具的产物（语料 = 档 5.1 的 4×20，**好 seed 1000**）：
                         #   ⚠️ 效度门剔掉 15/20 局（can 在接管前已被策略移动）⇒ 只剩 **5 局**可信；这 5 局里
                         #   「xy 对准 ∧ z 在带内」同时成立只有 **4/1197 步 = 0.33%**（详见里程碑 45）
code/mg_s9_rescue.py     # CPU-only「**重放接管台**」（10-04 16:25 建 / 17:06 加两字段后**全部重跑**，自测 **95/95**，**零 GPU 推理**）：把盘上已录的
                         #   `(state, action)` 逐帧重放进真 env，用 `mg_harness` 的**原样**检测器/接管/过滤语义接上
                         #   v1 专家 ⇒ 不做一次策略推理就量到 8A 那晚才有的读数。地基已自证：300 局
                         #   `max|Δ| = 0.0e+00`（逐比特）、接管步 vs 原 harness 记录 **18/18 相符**、
                         #   接管局数 vs 增补 6 语料 **35 vs 35**。对 TEST 窗口有**硬闸**（坑 73）
runs/_diag/s9_rescue/{FINDINGS,REPORT}.md # 上面那台的**主组**产物（坏 seed 2000 / val 8000..8019 / 11 格 / 220 局）：
                         #   8A 三条门的事前**实测**全过 —— A2 **109/175 = 62.3%** [54.9,69.1]（022000 单格
                         #   **11/16 = 68.8%** [44.4,85.8]，Wilson 下界已过门）、A1 折算 **6902 帧**/80 局、A3 中位 **233**
runs/_diag/s9_validate/  # 上面那台的**验证组**（好 seed 1000 / TEST 窗口，🚨`TEST_WINDOW_CONTAMINATION`）：
                         #   **只用于验证工具本身**，不许用来定专家的修法。A2 = **12/35 = 34.3%** ⇒ 与增补 6 的
                         #   模型 M（35.7%）几乎重合 ⇒ 模型算术没错，错在「拿好 seed 外推坏 seed」（坑 73）
runs/_diag/s9_rescue/_gen_findings.py # `FINDINGS.md` 的**渲染器**（每个数字从盘上 json 重算，不许手抄）；10-04 17:25 修掉
                         #   4 处口径 bug（3 处把 `takeover.n`（局数）当成 `.k`（接管数）当分母、§五 拿**池化**总体当 8B 的构成、
                         #   §六「只贡献十几帧」说过头）并加 **assert**：重算的 A2 分子 / A1 帧数必须与工具自己存的字段相等，不等就崩
code/chain_s8mech.sh     # 档 8 的**机理读数旁链**（10-04 17:36 `setsid` 发车 PID=SID=28867；零 GPU、**不是门**）：等 8C 的
                         #   11 格 val 扫描齐 → 重放台量「接管率 / 状态类构成 / A2」并与坏 seed 原臂**逐格配对** → 末格跑
                         #   `--mode fidelity` 自检（纯重放的放宽成功必须与该格 `eval_summary` 逐字相同）⇒ D1 落盘前 ~1 h 出账
runs/_diag/s8_mech/COMPARE.md # 上面那条链的产物（+ `rescue/REPORT.md`、`fid/`、终态标记 `MECH.{done,SKIPPED,FAILED}`）：
                         #   口径与判读规则**事前**写在 `runs/S8_PREREG.md` §9 **增补 11**（跨数据集有 normalizer 混杂 ⇒ 只读方向与机理）
runs/_diag/tax_s3r_seed2000_rev.md # 坏 seed 2000 的反向 TEST 失败分类账（放宽口径 **A 24 / B 17 / C 6**），
                         #   8A 靶子构成校正的输入（A⇒T1、B/C⇒T3）
runs/s8a_calib/collect_report.{md,json} # 格 8A：80 局产出率标定（接管率 / A2 放宽成功率 / 可用帧 / 每局墙钟）+ A1/A2/A3 三门
runs/s8b_collect/collect_report.{md,json} # 格 8B：续采到 ≥7000 可用帧（seed 9080..，与 8A 不重叠）
data/corr_r1/ + data/corr_r1_raw.npz # 纠正集（**只含专家接管段**，task 串 = 反向那一句）+ 原始 npz（出身可查）
data/mix60f120r_c1/      # 合并集 = `cp -a data/mix60f120r` + 追加纠正 episode（8C/8C-ctl **共用**它 ⇒ normalizer 逐比特相同）
runs/s8b_merge/merge_report.{md,json} # 格 8B 建集对账：B1 集/帧数、B2 原有负载 sha256 全不变、B3 tasks 恰好 2 句 + stats 覆盖并集
runs/pi05_mix60f120r_c1_s8c_seed2000/      # 格 8C 主实验：全集 / bs8 / **22000 步**（等步数不等 epoch）/ lr1e-4 / seed2000
runs/pi05_mix60f120r_c1_s8c_ctl_seed2000/  # 格 8C-ctl（**条件发车**）：同数据集 + `--dataset.episodes=0-179` ⇒ 1:1 归因
runs/s8c_seed2000_{rev,fwd}_test_rand20_k10* # 8C 的 TEST 关门读数（反向 4×20 seed7000.. + 正向 1×20 seed2000..）
runs/S8_VERDICT.md       # 档 8 判定：D1 主门 ≥40/80 / D2 正向掉幅 ≤15pp / D3 配对净胜 ≥+8∧p≤0.05 / D4 三 seed min ≥50%
runs/s8a.done / runs/s8a.HELD / runs/s8c.done / runs/s8c.SKIPPED # 档 8 的终态（HELD = 预注册分支「产出率不够，停下等人」）
code/chain_s8d.sh        # 格 8D（**条件发车**：D1∧D2∧D3 全过）：新 seed **4000/5000** × 配方与 8C **逐项相同**（`mix60f120r_c1` 全集 /
                         #   bs8 / 22000 步 / lr1e-4 / save2000 ⇒ 11 格）；每 seed：11 格反向 val 扫描（与 8C **同数据集同 stats** ⇒ 干净配对）
                         #   + TEST 反向 4×20 + 正向 1×20（**副读数、不是门**）⇒ 重出 `runs/S8_VERDICT.md` 的 **D4**；10-05 20:45 `setsid` PID=SID=**334638**
runs/pi05_mix60f120r_c1_s8d_seed{4000,5000}/ # 8D 两臂（串行，不抢卡）；关门格 = `checkpoints/022000`（链里核对 `readlink last`，坑 38）
runs/s8d_seed{4000,5000}_{rev,fwd}_test_rand20_k10* # 8D 的 TEST 读数（与判定工具的 `ARMS_D` 逐字对上，坑 63）
runs/_diag/s8_mech_d{4000,5000}/COMPARE.md # 8D 两臂的机理旁读（`chain_s8mech.sh` 参数化后双发；对照臂 = **8C**，同数据集 ⇒ 唯一差 = seed）
runs/s8d.done / runs/s8d.FAILED # 档 8D 的终态（链**不自动降门、不自动重跑**；D4 ❌ 的处方写在 `runs/S8_PREREG.md` §3）
runs/S7H_PREREG.md       # 档 7H 预注册（10-05 **21:04** 落盘，**早于 8D 的 D4** ⇒ 阈值不可能被 D4 污染）：便宜配方（bs32/lr1e-4/5500 步 = 3.791 ep）
                         #   × **3 个新训练 seed 11000/12000/13000**；H1 主门 = min ≥ 40/80（与档 3r/7C/7G/8D 同一条）、H2 正向掉幅 ≤15pp、H3/H4 只读方向
code/mg_verdict_s7h.py   # 档 7H 判定（自测 **43/43**）：复用 `mg_seedcurve.sign_test_exact`/`read_cells`、`mg_verdict_s2f.collect/ci/pct`、
                         #   `mg_verdict_s7f.prov/rev_dirs/fwd_dirs`（坑 54：同一个量不重写第二遍）；出身核对不过 ⇒ rc=3、判定**不采信**
code/chain_s7h.sh        # 档 7H 链（189 行，10-05 21:12 `setsid` PID=SID=**346154**）：**等 `runs/s8d.done`** 才开工（上限 48 h、不抢卡）；
                         #   上游写 `s8d.FAILED` ⇒ 写 `runs/s7h.SKIPPED` 停下等人；配方逐字照抄 F4（`run_pi05_s7b.sh` 自己现算并对账 STEPS/SAVE_FREQ/LOG_FREQ）
runs/S7H_VERDICT.md / runs/s7h.{done,SKIPPED,FAILED} # 档 7H 的判定与终态（机器可读行 `S7H_H1=`/`S7H_H2=`/`S7H_TRUST=`）
code/mg_prov_s8d.py      # 档 8D 的**独立出身核对器**（只读、自测 **19/19**）：核两个新 seed 的 5 个 TEST 读 + 11 格 val ——
                         #   ckpt 尾串 == `checkpoints/022000/pretrained_model`、权重路径含**本臂 run 名**（防读隔壁臂）、`task_mode`/K/seed 窗口/局数、
                         #   口径不变量 `严格 ≤ 放宽 ≤ 局数`、val **格号与权重逐格对上**（坑 38/42 的独立复查）；rc=0 可采信 / 2 读数不齐 / **3 🚫不采信**
                         #   对照实测：**正对照** = 已知good 的 8C 臂 5/5 + 11/11 全对；**三条负对照** = 尾串改 020000、run 名换成隔壁臂、
                         #   伪造「格名 22000 装 002000 权重」的坑 38 坏格 ⇒ **全部被抓、好格不误伤**
code/chain_s8d_prov.sh   # 上面那台的旁链（59 行、零 GPU、**不是门**、10-05 21:32 `setsid` PID=SID=**354312**）：等 `runs/s8d.done` ⇒ 出 `runs/s8d_prov.md`
                         #   + `runs/s8d_prov.done`（含 `PROV_RC=`）；上游 `s8d.FAILED` ⇒ 写 `s8d_prov.SKIPPED`。**不改 `runs/S8_VERDICT.md` 一个字**
runs/s8d_prov.md / runs/s8d_prov.{done,SKIPPED,FAILED} # 8D 出身核对的报告与终态（D4 那一行能不能当结论，看这里的 `PROV_RC`）
```

## 契约（`code/mg_env.py` 是唯一真源，探针逐条自证）

| 项 | 值 | 怎么证的 |
| --- | --- | --- |
| 任务 | robosuite `PickPlaceCan`（= `single_object_mode=2, object_type="can"`，物体恒为 can）+ `Panda` 单臂 | 源码 + 探针 |
| 动作 | 7 维 OSC_POSE：`[dx,dy,dz, droll,dpitch,dyaw, gripper]`，∈[-1,1]，姿态三维恒 0 | `--axes` |
| 动作有效增益 | **11.1 mm/控制步**（控制器 `output_max=0.05` × `ramp_ratio=0.2` + kp=150 阻抗）；`action=0.5` 实测正好一半 | `--axes` |
| 夹爪语义 | **+1 = 闭合，-1 = 张开**（与 robosuite 老文档注释相反！）；宽度 `sum(abs(gripper_qpos))`：张开 0.0788 / reset 0.0417 / 空合 0.0010 / 夹住 can ≈0.05 | `--gripper` |
| 状态 | 8 维：`eef_pos(3) + eef_quat wxyz(4) + gripper_width(1)`；只含本体感知，**不含物体真值**（物体靠相机看） | 契约 + 数据卡片统计 |
| 图像 | `agentview`→`observation.images.base_0_rgb`，`robot0_eye_in_hand`→`observation.images.left_wrist_0_rgb`；224²，已上下翻转（robosuite 原始渲染是倒的） | `--images` |
| 图像键名 | 沿用 π₀.₅ 基座的相机命名，换基座不用改数据集；第三路 `right_wrist_0_rgb` 缺失时由模型补 -1 + mask=0（openpi 单臂惯例） | 源码 `modeling_pi05._preprocess_images` |
| fps / horizon | 20 Hz 控制 / 400 步（20 s） | `--timing`（单步 9.6 ms 含两路 224² 相机） |
| 固定初态 | 每次 reset 前把 **env.rng + 每个 placement sampler 的 rng + np.random** 都钉到同一 seed | `--determinism` |
| 成功判定 | `env._check_success()`（环境真值）**且**物理落定（can 中心离篮底静止高度 <25 mm、速度 <0.05 m/s、夹爪张开、末端离 can >5 cm）**且**连续保持 10 步 | `--expert` 同时报宽/严两个口径 |

## 链路状态

| 步 | 内容 | 结果 |
| --- | --- | --- |
| 1 | 契约探针 14 项 | ✅ 14/14（`runs/probe/probe_summary.json`） |
| 2 | 脚本专家自证（链路上界） | ✅ 3/3 严格成功，229 步，零滑脱，九相位全走完 |
| 3 | 采集示范 | ✅ 10/10 成功局，2290 帧，90 s（`data/fixed10`） |
| 4 | 重放对齐验证 | ✅ 2/2：数据集里的动作喂回环境仍然成功 |
| 5 | ACT 小数据过拟合 | ✅ `runs/act_fixed10_r1`：20000 步 / 70 epoch，loss 0.73@2K → 0.033@19K |
| 6 | 闭环评测（从示范初态） | ✅ **π₀.₅ 17/20 = 85%**、**ACT 10/10 = 100%**（均 K=chunk_size） |
| 7 | π₀.₅ 微调 + 闭环评测 | ✅ 4000 步 / 4.7 epoch 到 85%；r3（9.4 epoch）在跑，详见「结果」 |
| 8 | **档 1 · 多初始位姿（未见泛化）** | ✅ **70%**（K=10，test seed 2000..2019，**三次独立读数 80% / 65% / 65%**，单读 1σ ≈ 10 pp）。头条数字从「80%」下修为「70%（65~80%）」，见下「结果（第 2 轮）」的复跑小节 |
| 8c | 档 1 · 失败性质定位（本轮复跑带出来的，比成功率本身更有用） | ✅ 三次读数逐 seed 对齐：**20 个未见 seed 里没有一个是 0/3 恒失败**（每个都至少成功过一次），3/3 恒成功 7 个（35%），1~2/3 摇摆 13 个（65%）⇒ 剩下那 30% 的失败**不是「某些初姿覆盖不到」的数据缺口，而是「同一初姿有时做得到有时做不到」的执行抖动**。这条直接决定后续该往哪投：不是加位姿多样性，是提高合爪瞬间的精度（与坑 17 的横向偏差机理同源），以及档 6 的纠正数据（对**失败的那次** rollout 接管，正是对症的） |
| 8b | **档 4 · K 曲线（四点已扫完，02:36）** | ✅ 同检查点/同未见 seed/各 20 局：**K=1 85% ≈ K=10 80% ≫ K=25 25% ≈ K=50 30%**（≤10 与 ≥25 之间一道 ~55 pp 悬崖；两两之差都在二项噪声内，别多读）。墙钟拆解：单次推理 ≈**0.323 s**、仿真 31.6 ms/步、20 fps 预算 50 ms/步 ⇒ **K=1 超预算 6.5×不可部署，K=10 摊到 32 ms/步（0.65×预算）⇒ K=10 是唯一「又准又实时」的工作点**。这也**推翻了档 4 原先「确认 K=chunk_size 为部署工作点」的预期**，并给 README 坑 14 划了适用边界（K=1 崩是 ACT 的 CVAE 毛病，π₀.₅ 相反）。详见 STAGE_PLAN 档 4 |
| 9 | 档 1 · 零样本对照（H1a） | ✅ 0/20 = 0% ⇒ 档 0 的 85% 是记忆不是泛化 |
| 10 | 档 1 · 失败机理定位 | ✅ 抓空的横向偏差 5.4 cm vs 专家 0.31 cm（`code/mg_diag_miss.py`） |
| 11 | **档 2 · 正反向数据** | ✅ `data/mix60f60r` 120 条 / 30447 帧；正向半边与 rand60 **逐比特相同**；反向 60 局重放 **逐比特 + 全部成功** |
| 12 | 档 2 · 专家上界（训练前钉死） | ✅ 正向 20/20 = 100%、反向 **14/20 = 70%**（缺口全是「搬运后侧躺」） |
| 12b | 档 2 · 语言条件对账（本轮补的独立复核） | ✅ `data/mix60f60r/meta/tasks.parquet` 恰好 2 个 task（index 0/1），`episodes` 里 **60/60** 分属两句；两句与 `mg_env.TASK` / `mg_env_reverse.TASK_REVERSE` **逐字符相同**，而 `mg_eval.py:141` 直接 import 这两个常量并把用到的串写进每份 `eval_summary.json` ⇒ 训练侧与评测侧不可能各说各话。**这条必须单独查**：上界是用脚本专家测的，专家不看 task 串，所以上界测不出串错位；串一旦错位，反向只会得 0% 并被误读成「策略学不会反向」。 |
| 13 | 档 2 · 正反向联合微调 | ✅ `runs/pi05_mix60f60r_s2` 14400 步 = 3.79 epoch（01:39→07:52）。进度看 `runs/pi05_mix60f60r_s2_meta/train.log`（**不是** `logs/train_pi05_s2.log`，后者被缓冲，训练结束前一直是 0 字节） |
| 14 | 档 2 · 双向检查点扫描（早收信号） | ✅ 14/14 个点收完 → `runs/pi05_mix60f60r_s2/sweep_bidir/step_*_{fwd,rev}/`。**正向 val 9000 步 6/10 → 11000 步 8/10 → 14000 步 5/10；反向 val 11000 步 5/10 → 13000 步 0/10** ⇒ 两个方向都在 ~2.9 epoch 见顶后回落（坑 26） |
| 15 | 档 2 · 关门评测（7 组） | ✅ 已收（`runs/s2_gate_*`）。**01:36 曾 FATAL 自杀**（坑 22(e)），02:05 重新武装后正常收门。判定见 `runs/S2_VERDICT.md` |
| 16 | 自动化链看门狗（本轮新增） | ✅ `code/chain_watchdog.sh`（02:17 起，每 10 min 一行心跳 → `logs/chain_watchdog.log`；链既不在跑、产物又没出现 ⇒ 写 `logs/ALERTS.log` 报 `MISSING`）。存在的理由就是坑 22(e) 那种死法：凌晨静默自杀、没人知道 |
| 17 | 档 2 · 训练后四项预检 | ✅ 语言条件对账 / **反向+`--video` 组合**（门的反向 TEST 组带 video，此前从未测过）/ 反向评测在真检查点上端到端 / **档 3 发车预检 7 项断言**（seed 2000 与 3000 各 0 miss）。详见 STAGE_PLAN「档 2 发车后的四项预检」 |
| 18 | 档 2b · 交叉指令探针 | ⚠️ 跑完了但**不出结论**：两个交叉格 40 局里 **39 局是「行为冻结」**（can 抬不过 1 cm，手臂根本没去碰）。原实现把「can 纹丝不动」算成「照指令字符串走（不搬运）」，会把一次停摆读成「π₀.₅ 真在做语言条件化」⇒ 已修（坑 28），`probe_conclusive=False` |
| 19 | **档 2 判定** | ❌ **未通过**。门1 正向未见 **63.7%**（51/80）PASS；门2 反向未见 **37.5%**（30/80）FAIL；门3 回退 −6.2 pp PASS。专家上界 正 100% / 反 **70%**（6 局失败全是 can 侧躺 tilt≈90°） |
| 20 | 档 2 · 关门检查点修正（val 选点 011000） | ❌ **选点不是杠杆**。同批 TEST seed：正向 55%/60%（23/40 = **57.5%**）、反向 35%/30%/15%（16/60 = **26.7%**）。反向 val 峰值（011000 的 5/10=50%）在 TEST 上**反序** ⇒ val n=10 选不出点（坑 27）。两个选点规则的反向读数合并 **29/100 = 29%**，说明这就是模型的真实水平 |
| 21 | 档 2 · 反向失败分类账（100 局，`code/mg_tax_fail.py`） | ✅ **A 没抓起 44% / B 抓起了没送到 39% / C 送到了没落定 17%**（`runs/_diag/tax_rev_test.md`）。C 类平均举高 **18.0 cm** vs 成功局 **11.7 cm** ⇒ 举太高、放下时侧躺（专家也栽在同一条上）。逐 seed：只有 5/20 从未成功，其中 4 个专家能成（真差距），1 个专家也成不了 |
| 22 | **档 3 · 三个训练 seed** | ✅ **PASS（已补到 60 局/seed，`runs/s3_confirm.done` 21:26）**。seed1000 **42/60 = 70.0%**（80/65/65）/ seed2000 **38/60 = 63.3%**（55/75/60）/ seed3000 **42/60 = 70.0%**（80/50/80），最差 63.3% ≥ 门 50% ⇒ 档 1 的结论**不依赖训练 seed 的运气**。（K=50 并列读数 30/25/30%，与坑 17 一致） |
| 23 | **档 2c · 反向单任务消融**（干扰 vs 任务本身难） | ❌ **判定 R2「不是干扰」**（`runs/S2C_VERDICT.md` 00:50）。单任务 @last 反向未见 **37/80 = 46.2%** vs 档 2 联合 **30/80 = 37.5%** ⇒ 差 +8.8 pp、Fisher **p=0.336 不显著**、未过 50% 门。护栏 **G1 ✅ 正向零样本 0/20**（子集过滤生效、normalizer md5 与档 2 逐比特相同 ⇒ 消融干净）；**G2 ⚠️ 报警**：训练 seed **9/10=90%** vs 未见 46.2%（+43.8 pp，p=0.015），而档 2 联合模型同一道护栏只有 50% vs 37.5%（p=0.50）⇒ **瓶颈是泛化不是能力**。⚠️ 功效说明：n=80 要判出 37.5%→50% 需 ≥55%，所以 R2 应读作「**没测出干扰**」而非「证明了没有」 |
| 24 | 档 2 · 联合基线补读（反向 TEST 40→80 局） | ✅ `runs/s2c_jointbase_rev_test_rand20_k10_rep{3,4}`。补读理由：同检查点同 seed 三读实测 **30% / 35% / 55%**（坑 29），40 局判不了 50% 的门 |
| 25 | 档 2 · **松手高度画像**（新增，纯 CPU、不占 GPU） | ✅ `code/mg_lift_profile.py`（61 项自测）→ `runs/_diag/lift_profile.md`。把「举太高」从推断变成测量：专家松手中位 **1.9 cm**（60 局全域 [1.3,2.7]），策略成功局 **2.1 cm**（= 阳性对照，尺子准），**A 类 21/31 一次都没夹住（空合率 74%，专家 0/60）** ⇒ A 与 B/C 是**两种病**；C 类 4/7 越过专家全域（p=1.9e-04）；**排掉了 normalizer 假设**（详见坑 31） |
| 26 | 档 2c · 先行指标**工具化** + 档 2e 数据侧准备 | ✅ `code/mg_epoch_curve.py`（**43 项自测**）把「epoch 对齐」从手算变成可复现读数 → `runs/_diag/epoch_curve_s2c.md`：epoch 对齐后 2.00 ep 处 30%（6/20）vs 20%（2/10）、**2.50 ep 处 40%（8/20）vs 20%（2/10）**，Fisher 分别 p=0.682 / p=0.419 ⇒ **差仍在噪声内**（n=20/10 太小；坑 33：按步号比会整整错位一倍）。✅ `code/mg_check_superset.py`（18 项自测）+ `code/chain_s2e_data.sh`（23:05 发车，自己等 `s2c.done`）→ 重收 60 正向 + **120** 反向 = `data/mix60f120r`，这是 **R1/R2/R3 三个分支都要**的无regret 动作（2:1 配比就是 R1 的处方本身，反向翻倍就是 R2 的处方）；三道护栏：集数真收满 / 正向逐比特复现 / 反向是旧 60 条的**严格超集**且不撞留出 seed |
| 27 | 档 2c · 失败分类账里**自己冒出来**的两条（`runs/_diag/tax_s2c_rev.md`，80 局） | ⚠️ **两条都指向判据、不指向策略**：① 把成功判据从「立着保持 10 步」放宽到「can 曾进过 ±9 cm 方框」，同一检查点同一批 80 局 = **47/80 = 58.8% ≥ 门**（多出的 10 局全是 C 类：送到了、放下翻了）——这与第 3 轮排除#4「判据不是瓶颈」**冲突**，那条是在联合模型上量的（放宽几乎没涨），**不能推广**到单任务；② 20 个 TEST seed 里 6 个专家自己也 100% 失败（tilt=90° 侧躺），占样本 30%；剔掉后策略 **29/56 = 51.8% ≥ 门**。③ 20 个 seed 里策略**至少成功过一次**的有 14 个，从未成功的 6 个中 3 个专家也失败 ⇒ **真差距只有 3 个 seed**（7005/7012/7016）⇒ 加数据的作用是**压抖动/抗过拟合**，不是「覆盖更多位姿」。单任务反向达专家上界的 **66.1%**，与正向达其上界的 **63.7%** 持平。**改口径须单独立一档、预注册、不追溯改历史门** |
| 28 | 档 2e · 训练收工 + **双口径评测**落地（2026-10-02 10:18） | ✅ 22000 步 / 3.79 epoch / 8 h53 m，rc=0，`last -> 022000`（等 epoch 与档 2、档 2c 对齐；数据集 180 集 46426 帧，`total_tasks=2`，预检 10 项全过）。✅ 判据改动落地方式：`mg_env_reverse.reverse_settled()` 抽成纯函数 + 严格/放宽**并行**判定，`mg_eval.py`、`mg_ceiling.py` 同时输出 `pc_success`（严格，语义未变）与 `pc_success_relaxed` + `delivered_tipped` 标记 ⇒ **档 2e 的 160 局关门读数顺带把放宽口径白捡了**，不用重跑。⚠️ 同批读到坑 38（扫描终点格拿 020000 冒充 22000）与坑 39（评测不可复现，同权重两读 6/20 与 10/20），两者都只影响 val 曲线那一格，**主门读数用的是训练结束后解析的 `last`，没受影响**。✅ 11:25 坑 38 的**选点侧**余波已查清并更正：误标格让 `ckpt_selection.json` 把 10/20 当成 22000 的分、argmax 选中 22000（恰好 == last，所以没触发并列读数）；用真 022000 补测后是 **7/20**，更正后 val argmax = **18000（9/20）**，两者 Fisher **p=0.7475** 分不开 ⇒ **坑 27 又一次实测复现**。**不重新选点、不去测 18000 的 TEST**（看过 test 再换点 = 把 test 当第二个 val）；**P1 PASS 不受影响**（门只认 @last）。全文 + 根因修复见 `runs/S2E_VALCORR_NOTE.md`，坑 42 |
| 29 | **档 2f · 放宽口径复判**（用户 2026-10-02 授权：送到目标区为首要条件，侧躺算送到但打标） | ✅ **RX1 PASS**（`runs/S2F_RELAX_VERDICT.md` 11:14，`runs/s2f_relax.done`）。三臂同口径各 80 局（TEST 反向 7000..7019，K=10）：**档2e 2:1 放宽 55/80 = 68.8%**（Wilson [57.9,77.8]）/ 严格 42/80 = 52.5%；**档2c 单任务 放宽 44/80 = 55.0%** / 严格 36/80 = 45.0%（历史原测 46.2% 仅对照）；**档2 联合 放宽 33/80 = 41.2%** / 严格 29/80 = 36.2%（历史 37.5%）。⇒ 只有档 2e 两口径都过门，且它的 **P1 PASS 是按严格口径独立判的**（`runs/S2E_VERDICT.md`）⇒「反向过门」**不依赖**这次放宽。**剂量-反应单调**（反向 60→60→120 条：严格 36.2→45.0→52.5%、放宽 41.2→55.0→68.8%），按 seed 拆分显示加数据是把**抖动局变稳过局**（稳过 2→5→11、抖动 13→11→6、从不 5→4→3），不是覆盖新位姿。⚠️ 上界同时从严格 70% 抬到**放宽 100%**（专家 6 局侧躺失败 min_dist ≤0.52 cm，早在框内）⇒「这 6 个 seed 专家也做不到」的借口**消失**；「占上界」可能变差而绝对值变好，门看绝对值。纪律见坑 40 |
| 30 | **三臂失败分类账（双口径）· 判据红利已吃完** | ✅ `code/mg_tax_fail.py` 加 `--criterion strict/relaxed/both`（**31 项自测**，缺字段判 `UNK` 取消资格、**不当 0 计入**）→ `runs/_diag/tax_{s2joint,s2c,s2e}_rev_both.md` + 对表 `runs/_diag/tax_relaxed_summary.md`（纯 CPU、只读产物）。**放宽口径下残余失败里 A+B 占 91~94%**（档2e：A 没抓起 10 / B 没送到 13 / C 没落定 **2**）⇒ **再改判据不会有收益**，只能提能力。两口径交叉表在三臂 240 局上**零违例**「严格 ⊆ 放宽」，且「严格失败→放宽成功」**100% 来自 C 类**（13/13、8/8、4/4）⇒ 放宽没被写宽。数据杠杆的机理被定死：**A 类 27→27→10，Fisher p=0.0024 显著**（B 类 7→13，p=0.2315 不显著）⇒ 加反向数据买的是**合爪瞬间不抓空**，不是位姿覆盖。⚠️ 档2e 的 68.8% 里 **13/80 = 16.2 pp 是「送到了但躺着」**（`final_tilt` 全 90°）⇒ 严格口径必须一直并列报（真机验收大概要求立着） |
| 31 | **val 选点更正 + 选点脚本根因修复（坑 42）** | ✅ `runs/S2E_VALCORR_NOTE.md`。坑 38 的误标格曾把 val 10/20 当成 22000 的分、argmax 选中 22000（恰好 == last，所以没触发并列读数）；用真 022000 补测是 **7/20** ⇒ 更正后 argmax = **18000（9/20）**，两者 Fisher **p=0.7475 分不开** ⇒ **坑 27 又一次实测复现**（val n=20 选不出点）。**不重新选点、不测 18000 的 TEST**（看过 test 再换点 = 把 test 当第二个 val）；**P1 PASS 不受影响**（门只认 @last）。根因修复：`mg_select_ckpt.py` 逐格核 `policy_ckpt` 格号 == 目录名 step（记 `last` 就现场 `readlink`），对不上 ⇒ 剔除并报原因；顺带修「缺方向读数按 0 记分」；新增 `--out` 保留历史 + `--selftest`（**51 项**，含一条反向断言钉住「历史 `ckpt_selection.json` 必须仍是 22000/10 分」，谁覆盖就红）。回归：新版重算 档2 = **11000/13 分**、档2c = **5000/8 分**，与历史逐个数字相同、剔除格 0 |
| 32 | **档 4r · 反向 K 曲线**（用户阶梯第 4 步在反向侧的补做） | ✅ `runs/S4R_VERDICT.md` 11:48（`runs/s4r.done`）。检查点 = 档 2e `last`(022000)，唯一变量 K，TEST 7000..7019：**K=1 严格 55.0% / 放宽 70.0%**（n=20，348.9 ms/step ❌ 超实时预算 7.0×）、**K=10 52.5% / 68.8%**（n=80，41.9 ms/step ✅ 工作点）、**K=25 40.0% / 50.0%**（n=20，29.7 ✅）、**K=50 60.0% / 60.0%**（n=20，30.8 ✅）。对 K=10 的放宽口径 Fisher：K=1 Δ=+1.2 pp p=1.0000、K=25 Δ=−18.8 pp p=0.1256、K=50 Δ=−8.8 pp p=0.5955 ⇒ **预注册的「掉 ≥20 pp」一格都没触发，反向没看出正向那道 ~55 pp 悬崖**。⚠️ 但 n=20 ⇒ 1σ~18 pp，只能读作「没测出塌陷」，**不是**「证明了不塌」；且与正向档 4 的对表**混淆了任务方向/数据量/训练量三个变量** ⇒ 另立档 4x 做对照。判定：**档 5 仍按 K=10 / 50 ms 预算设计**（K=1 不可部署，见坑 36） |
| 33 | **档 4x · K≥25 塌陷的机理对照**（回答档 4 未答问题 3：加数据/训练量能不能把 K=50 抬起来） | ✅ 12:24 关门（`runs/S4X_VERDICT.md` + `runs/s4x.done`；预注册 `runs/S4X_PREREG.md` 11:56:56 **先落盘再跑**）。2 臂 × 3 K，同任务(forward)/同 TEST seed 2000..2019/同初态/同 K，唯一变量 = 模型（臂A `007200`：60 条正向 / 7200 步；臂B `022000`：**逐比特相同的那 60 条**+120 条反向 / 22000 步，4 个数组 md5 全等已断言）。**预注册判定 = 「部分支持」**（H1 要 A率≤25% ∧ 成功≥45%，实测 32.5% / 35.0%；H0 要 A率≥40%，实测 32.5% ⇒ 两边都没命中）。主指标 **A 类率 A 57.5% vs B 32.5%，Δ=−25.0 pp，Fisher p=0.0424 显著**；成功率 20.0% vs 35.0%，p=0.2101 不显著。🔎 **事后探索**（`runs/S4X_SUPPLEMENT.md`，明确标注未预注册）：**崖挪了一格、没消失** —— 臂A K=10→K=25 从 80%→25%（**p=0.00123**，档 4 那道 ~55 pp 悬崖现在有 p 值了），臂B 同格 75%→65%（**p=0.5449，平地**）；臂B 的崖被推到 K=25→K=50（65%→35%，p=0.0526）。跨臂 K=25：A 25.0% vs **B 65.0%**，**p=0.0248 显著** ⇒ **开环塌陷是模型的属性、不是执行器/任务的内禀属性**，加数据/训练量把它**推后一整格**但没消除。⚠️ 关键格 B@K25 只有 n=20（1σ≈11 pp）且两臂 K=10 的 A 率不齐（10.0% vs 22.5%，p=0.3069）⇒ 升级为结论需 2臂×3K×n≥60 的完整网格（≈1.5 h GPU），**本轮不抢档 3r 的 GPU，记为待决**。🚫 预注册写死**本档不改工作点**：K=10 仍是档 5 的设计点 |
| 34 | **档 3r · seed 2000 读数**（用户阶梯第 3 步在反向侧的补做，第 1 个 seed；20:21 收） | ❌ **双 FAIL**（预注册门；`logs/chain_s3r_seed.log`，正式判定等 seed 3000 收工后由 `mg_verdict_s3r.py` 出 `runs/S3R_VERDICT.md`）。反向 TEST 7000..7019 / K=10 / **4×20**：放宽 **33/80 = 41.2%**（四读 50/35/30/50%）、严格 29/80 = 36.2% ⇒ 门「最差 seed 放宽 ≥50%」**不过**（差 8.8 pp）。正向护栏 seed 2000..2019 / 1×20：**4/20 = 20.0%** vs 基线 193/300 = 64.3% ⇒ **掉 44.3 pp**，门 ≤15 pp **不过**（2:1 配比在这一 seed 上确实拆了东墙）。🔎 与 seed 1000 逐点对表：训练 loss 曲线两点之差 **≤0.0012**（`runs/pi05_mix60f120r_s3r_seed2000_meta/train.log` vs s2e）⇒ **不是训崩**，是纯 seed 敏感性；FAIL 处方按预注册走「**先补它的 val 曲线**（`mg_sweep_rev.sh`），别急着加数据」。seed 3000 20:21 开训，ETA 明日 ~05:30 训完 / ~06:10 出判定 |
| 35 | **档 5 · Harness 接管开工**（预注册 `runs/S5_PREREG.md` 20:33 **先落盘后跑数**；链 `code/chain_s5_harness.sh` 20:55 发车，与档 3r 训练并发） | ✅ 20:55 发车、21:41 关门（判定与机理见下一行 36）。开工四件已关门：① **G1 专家回归 PASS**（`code/mg_g1_expert_regression.sh` → `runs/s5_g1_ceiling_rev_test20_n05` 与参考产物 `runs/s2f_ceiling_rev_test20_n05` **20/20 局逐比特相同**，严格 14/20 ∧ 放宽 20/20）⇒ `resume()` 确认是纯增量；② **`resume()` 真物理预检**（`code/mg_resume_probe.py` → `runs/s5_resume_probe{,_slip}`）：carry@t=100 → 140 步 **5/5**、T1 抓空@t=100 → 209~220 步 **4/5**（@t=160 → 0/5，纯步数预算不够）、T3 滑脱 剩余 280 → **7/8**、剩余 220 → 3/8 ⇒ 触发点必须留 ≥~250 步；③ **检测器离线标定**（`code/mg_calib_detector.py`，21 项自测 → `runs/_diag/harness_calib.{md,json}`）：`W_EMPTY=0.020`（= `mg_expert.GRASP_HELD_WIDTH`）/ `N_EMPTY=3` / `HOLD=[0.045,0.060]` / `N_HOLD=25`，s2e 臂失败覆盖 **25/25**、误触发 4/55 = 7.3%、接管率 36.2%（T2 本轮不做，理由见标定报告第五节）；④ **G0a 外壳等价 PASS**（`code/mg_g0a_equiv.py`，判据因**坑 44** 从「逐比特」改成「CPU 确定性 + GPU 噪声地板对照」；旧 `mg_g0a_bitcmp.py` 已 `.superseded`）。**预读数在跑数前写死**（`S5_PREREG.md` 第六节）：(55+13.0)/80 = **85.0%** ⇒ H1 门（≥85%）**正贴刀刃**，三条归因分支已预注册。检查点仍用 `s2e/022000`，**不**因档 3r seed 2000 FAIL 而换（理由三条见 `S5_PREREG.md` 第五节：标定、失败分类账、配对分母全绑在 s2e 臂上） |
| 36 | **档 5 · Harness 接管判定 + 机理定案**（21:41 关门：`runs/S5_VERDICT.md` + `runs/s5.done`；事后补充分析 `runs/S5_SUPPLEMENT.md` 21:56，明确标注**未预注册**） | ⚠️ **「部分有效」**：放宽 **46/60 = 76.7%**（Wilson [64.6,85.6]），落在 H0(≤75%) 与 H1(≥85%) 之间 ⇒ 按预注册只报点估计、不下强结论。三道护栏全过（**G1** 专家 20 局逐比特 / **G0a** 噪声地板对照 / **G0b** 观察模式 40/60 = 66.7% vs 基线 39/60 = 65.0%，**+1.7 pp、Fisher p=1.0000**）；接管率 **23/60 = 38.3% ≤50%** ✅、误接管 **9/39 = 23.1% ≤25%** ✅（只富余 1 局）、在线触发率 36.7% 与离线标定 36.2% 对得上、专家段 **0.03 ms/step**。🔎 **配对拆账才是关键**：救回 **6** 局、把「基线会成功」做成失败 **6** 局 ⇒ **净收益 0 局**；那 +11.7 pp（对同 3 rep 基线，Fisher p=0.2280）**不能归因给 harness**。归因命中预注册**分支 2**（剩余 ≥250 步的接管只救回 2/7 = 28.6% < 70%）。**病根定位**：23 次接管里 **11 次从未离开 `approach`/`descend`**，原地打转 162~305 步、爪子全程张开 —— `code/mg_expert.py` 的 `grasp` 相位有 `MAX_GRASP_TRIES=3` 的下降重试阶梯，**`descend` 一条退路都没有**，判据（xy ±8 mm ∧ z ±10 mm）一旦长期不成立就是死循环到 horizon（坑 46）。已排除两条：腕姿态（卡死组接管瞬间 138~177°，而专家自己 120 条示范就是 139.8~179.6°）、步数预算（6 次卡死时手里有 251~333 步）。**对档 6 的直接影响**：4506 步纠正片段里只有 **922 步（20.5%）**来自成功救回，其余是专家死循环或把成功局做坏的动作 ⇒ 档 6 必须按「片段所属局放宽成功」过滤，且过滤后原料量远不够 ⇒ **档 6 暂缓，先做档 5.1**。处方（诊断→修专家→修检测器尾巴→重新预注册）见 `runs/S5_SUPPLEMENT.md` 第八节；实时性门（≤50 ms/step）已排队隔离测（`code/chain_s5_timing.sh` 等 GPU 独占）；档 3r FAIL 处方的 seed 2000 val 曲线也排好队（`code/chain_s3r_sweep_seed2000.sh`） |
| 37 | **档 5.1 · descend 停滞阶梯 + 认输交还（hand-back）开工**（诊断定案 22:34 / 标定 22:44~23:04 / 预注册 `runs/S5_1_PREREG.md` **23:23 先落盘** / 链 `code/chain_s5_1.sh` 23:39 发车） | 🔄 **读数在跑**（4 rep × 20 = 80 格，`--hand-back`，ckpt 仍是 `s2e/022000`、K=10、seed 7000 random、reverse，与档 5 同口径 ⇒ 可按 (rep,seed) 配对）。**机理已定案**：指隙 (0.0805−0.066)/2 ≈ **7 mm** < 容差 8 mm；7015 典型 = can 立着（tilt 0.1°、dcan≈0）、`eef_z` 卡在 0.900、命令下降 25~33 mm/步而实测 **0.03 mm/步** ⇒ **接触阻挡**；7014 是另一类（can 侧躺 90°、离位 255 mm ⇒ 出流形，坑 48 的单位 bug 修正后改判）。**改动只有两处**（`mg_expert.py` 停滞 25 步 ⇒ restage ≤2 次 ⇒ `unrecoverable` + `give_up`；`mg_harness.py` `hand_back=True` 交还策略），自测 261 + 86 + 32 + 21 + 12 项全绿；**G1 逐比特回归换目录重跑通过**（新锚 `runs/s5_1_g1_ceiling_rev_test20_n05`，专家 sha16 `317c2b29…`，严格 14/20 ∧ 放宽 20/20）；**G2 阶梯不误伤**（干净正/反各 20 局在 T=0.1 mm ∧ W=25 上触发 **0/20**，最长停滞游程 9 / 0 步；档 5 接管 trace 上死循环 79 / 152 步稳稳触发）。**检测器一个字没动**：守卫窗长标定把「松手后守卫」**否决**（坑 50，`runs/_diag/guard_calib.md`），`scan()` 只加默认关闭的 `guard_w`，对账产物与锚除时间戳外逐字节相同。主判据 = **配对净收益 > 0**（坑 47），预测 +3 [0..+6] ⇒ 预注册已写明大概率落在「方向对、功效不足」，那**不算失败** |
| 38 | **档 5.1 · hand-back 判定 + 关门**（4×20 = 80 格 00:17 收工、判定 `runs/S5_1_VERDICT.md` 00:20:46、事后补充 `runs/S5_1_SUPPLEMENT.md` + 天花板 `runs/s5_2_handback_ceiling/` 00:24、关门标记 `runs/s5_1_gates_FAILED` 00:27） | ❌ **关门（读数不采信）**。机理门 **M1 ❌**（没到 grasp ∧ 片段 ≥100 步的接管局 = **17**/35，档 5 = 9）、**M4 ❌**（认输延迟实测 191/208/271、中位 **208** > 门 110 —— 那个 110 是**桩件**时间线给的，坑 52）；M2/M3/M5/G1/G2 全 ✅、4 rep 出身全 ✅。主判据 80 格配对：救回 13 / 毁掉 15 ⇒ **净 −2**、McNemar p=**0.8506**；副判据放宽 **53/80 = 66.2%**（基线 55/80 = 68.8%，Fisher p=0.8661）、接管率 43.8% ✅、误接管率 19/55 = 34.5% ❌。🔎 **归因**：阶梯的因果足迹只有 **3/80 格**、其中只有 1 格结局被改 ⇒ 净 −2 里能归因给改动的最多 −1 格，其余是坑 39 的采样噪声（逐 rep +2/−4/+3/−3）。**根因 A** 覆盖缺口：31 段死循环里「蠕动型」22 段（中位 \|dz\| = **1.292 mm** ≫ 阈值 0.1 mm）、「XY 型」5 段（游程 128~184 步却被 `z_err>Z_TOL` 合取项挡住）⇒ 只覆盖 3 段；**根因 B** M4 常数来自桩件。**算术天花板**（`code/mg_probe_handback_ceiling.py`，23 项自测）：策略做完反向任务最少 **224** 步（55 局基线成功局 min）、认输延迟中位 208 ⇒ 交还时只剩 **3/17/96** 步 ⇒ **原则上可救 0/31**；纯时间预算也分不开（死循环段 vs 专家做完段 AUC = **0.573**）；即使把延迟压到 25 步且覆盖全部机理，可及上界 14/31 × 历史救回率 28.6% ≈ **净 +4 < 检出下限 +8** ⇒ **这条杠杆的天花板低于 n=80 的检出下限**。⚠️ 预注册「有害」分支的第 ② 步（`DESCEND_STALL_MAX` 25→40）**留档跳过**：抬 W 只会增大延迟（延迟是唯一关键参数），且它想修的「误伤」在盘上不存在（G2 干净跑 0/20、足迹 3 格）⇒ 直接落第 ③ 步：档 5/5.1 作为**成功率杠杆**关门，代码保留但 `--hand-back` 默认关、阶梯常数不动（G1 锚仍有效）；主线回**档 3r**（seed 3000 训练 ETA ~05:00，读数链已排队）；档 6 仍暂缓，入口条件加到三条（按所属局放宽成功过滤 / 认输局片段整段丢弃 / 开档前先把延迟砍到 ≤25 步）。新增坑 **51**（辅助函数没类型门）、**52**（机理门常数来自桩件）、**53**（发车前先算因果足迹）|
| 39 | **档 3r 补充第 2 步 + 档 6 收工 + 档 7 开工（run 间方差归因）**（13:14 seed3000 反向 val 11 格收工、12:07~12:57 档 6 预注册/6A/6B/判定落盘、**13:55 `runs/S7_PREREG.md` 先落盘**、14:04 `code/chain_s7b.sh` setsid 发车） | 🔄 **7B 训练中（14:19 起，ETA ~21:10）**。四条已定案的读数：① **「好 seed 全程都好」成立** —— epoch≥1.03 的 9 个配对格上符号检验：seed3000 vs seed2000 严格 **8胜0负1平 p=0.0078**、放宽 **9胜0负 p=0.0039**；seed3000 vs seed1000 **8胜1负 p=0.0391**；seed1000 vs seed2000 **8胜1负 p=0.0391** ⇒ 排序 3000>1000>2000 在整条轨迹上一致，不是「终点掉坑」也不是抽到一格好读数（新工具 `code/mg_seedcurve.py` 自测 **87/87** → `runs/_diag/seedcurve_sign_{strict,relaxed}.md`）。② **训练日志筛不出坏 seed（重要阴性）** —— 三 run 都是 log_freq=100/22000 步 ⇒ 220 个记录点逐点同 epoch、同 800 样本窗；崩掉的 seed2000 末点 loss **0.0280 是三条里最低**、grdn 残差 sd **0.0578 最小**（好 seed3000 = 0.0270 / **0.0842 最大**）⇒ BC loss 在最优附近**简并**（三者末点 loss 只差 7%，闭环成功率差 38.8 pp），**不存在零 GPU 的早筛**（坑 59）。③ 早筛回溯（n=3，**回溯挑的阈值、未前瞻验证**）：能完美分类的 (step,T) = **21/81**；最便宜点 step 6000 = 全程 **27.3%** 但 T 窗口只有 1 格宽（脆）；窗口 ≥3 格的最早点 = step 10000 = **45.5%**、T∈(0.05,0.30]。④ **档 6 收工（四句）**：几何矛盾**不成立**（真环境实测 can 直径 **50.17 mm**、全开 **79.36 mm** ⇒ 单侧指隙 **14.59 mm = 1.82× XY_TOL**；`mg_expert.py:59` 的 0.066 真身是手掌宽 63.11 mm）；A 类 41 局分桶 **X26 / L8 / H6 / N1 / F0** ⇒ 98% 是横向没对准；无可白修偏置（concentration 0.33）、x 增益斜率差 0.171 < 门 0.30、无覆盖漏洞（0/12）⇒ **「收紧 XY_TOL → 重采 180 条 → 重训 10 h」方案取消**（`runs/S6_VERDICT.md`）。⑤ **档 7A 代价探针**（`code/mg_probe_batch.py` 自测 **68/68** → `runs/s7_probe/timing.md`）：**grad-ckpt 一关 bs16/32/64 全 OOM**（80.9 GB）；bs8+ckpt **1.374 s/step**（历史真值 1.366，差 0.6% ⇒ 探针口径可信）、峰值 33.8 GB；bs32+ckpt **4.491 s/step**（只涨 **3.27×** 而非 4×）、峰值 41.7 GB ⇒ **等 epoch 墙钟从 8h23m 降到 6h51m**，同时每步梯度噪声 ÷2；四档 batch 的等 epoch 网格都是每格 **0.3446 epoch**（bs32 = 5500 步 / save_freq 500 / 11 格）⇒ 与 batch8 逐格可配对。⑥ **档 7A-2 机理探针**（`code/mg_probe_gradnoise.py` 自测 **69/69** → `runs/s7_probe/gradnoise.md`）：`--log_freq=1` + lr 1e-6 冻住参数点（drift 哨兵 0.34% / 0.88%）测**逐步** grdn，解 `E‖g_b‖²=G+C/b` ⇒ **G=86.34（‖ḡ‖≈9.29）、C=817.2**，**η₈ = 54.19%**、η₃₂ = 22.83%，‖g‖ 相对真值超出 **+47.8% → +13.8%** ⇒ 预注册分支 **`MECH_YES`**（η₈ ≥ 0.40）⇒ **batch 8 的每步梯度过半是采样噪声**，H7 的必要条件成立（坑 58/60）。⑦ **档 7B 主实验**：bs32 / seed **2000**（batch8 三 seed 里唯一崩的那个）/ 5500 步 = 3.79 ep / save_freq 500 / **log_freq 25**（=25×32=800 样本窗，与 batch8 的 100×8 同窗 ⇒ grdn/loss 可比）/ **lr 2e-4**（sqrt 缩放；Adam 每步位移量级 ≈ lr，步数少 4× 而 lr 不变会系统性欠拟合）/ 其余逐项照抄档 3r。五条判据 **M1**（9 格配对符号检验 ≥8胜0负）、**M2**（TEST 放宽 ≥41.2%，防「方差小是因为全塌到 0」）、**M3**（末点 loss ≤0.042，欠拟合哨兵）、**M4**（TEST 放宽 ≥50%，与档 3r 同一条使命门）、**M5**（正向护栏掉幅 ≤15 pp）+ 5 行判定表全部写死在 `runs/S7_PREREG.md` §3；判定工具 `code/mg_verdict_s7.py`（自测 **68/68**）。新增坑 **58**（AverageMeter 窗长=log_freq）、**59**（loss 简并、日志筛不出坏 seed）、**60**（换 batch 必须同时换 lr）、**61**（两套 Fisher 签名不同）|

| 40 | **档 7C 链武装 + 7B 在飞的早期哨兵**（14:51 `code/chain_s7c.sh` 落盘、14:55 `setsid` 发车 PID=SID=217128；14:55 看门狗换清单重启 PID=SID=217254、上限 48h→66.7h；15:00 哨兵读数落盘） | 🔄 **等 7B 收工（ETA ~23:00）**。① **7C 是条件发车**：闸读 `runs/S7_VERDICT.md` 的命中行，必须是 `M1✅ M2✅ M3✅ M4✅` 或 `M1✅ M2✅ M3✅ M4❌`、且全文不含「不采信 / 无法判定」（= 预注册 §3 的 **M1∧M2∧M3**；M4 过不过都发、**M5 只记录不当闸**，坑 40）⇒ 闸逻辑用**真判定文件**（当前的「读数不齐，无法判定」）+ 4 份合成判定件实测 **6/6** 与预注册判定表一致，闸读数留档 `runs/S7C_GATE.md`；闸不过写 `runs/s7c.SKIPPED` 后 exit 0（坑 62）。② **发车内容**：seed 1000/3000 各一发（同配方 bs32 / 5500 步 / lr 2e-4 / save 500 / log 25，步数由 `equal_epoch_plan` 现算并断言）→ `last` 软链核对（坑 38）→ 11 格反向 val 扫描 → TEST 反向 4×20（seed 7000..）+ 正向护栏 20（seed 2000..）→ 6 条曲线总览（batch8×3 + bs32×3、15 对配对符号检验，`--test` 的 k/n 一律从盘上 `eval_summary.json` 现算）→ `runs/S7C_VERDICT.md`（C1~C3，门是 **C2：最差 seed 放宽 ≥50%**）；串行 ≈17.4 h，ETA **2026-10-04 ~16:40**（原写 10-05 是日期算错，见坑 62 末的更正）。③ **新工具** `code/mg_early_sentinel.py`（自测 **37/37**）：训练在飞时按**同样本窗**逐点对比 loss/grdn（解析复用 `mg_seedcurve.parse_train_log`，不重写；日志在 `<run>_meta/train.log`，收工才搬进 run 目录），阈值全部取自预注册 M3（grdn 1.0 / 0.05、比值 1.5），**连续 5 点**才触发 ⇒ 只回答「这一发还要不要继续烧」，不产出判据读数。④ **哨兵读数（step 500 / epoch 0.34 / 20 点）**：`state=OK` —— 20 个点的 epoch 差**全为 0.0000**（⇒ log_freq 25 ↔ 100 的「同 800 样本窗」设计逐项对上，坑 58 的换算在真日志上验过）；loss 比值末点 **1.051**、末尾 5 点均值 1.088（门 1.5）；grdn 末值 **0.224**、全程最大 2.868 出现在第一个 800 样本窗且**低于**参照臂同点的 3.869 ⇒ lr=2e-4 的 sqrt 缩放**既没训崩也没欠拟合**，M3 目前走在过门轨道上（参照末点 0.0280 × 1.09 ≈ 0.031 ≪ 0.042）。⑤ 新增坑 **62**（看门狗必须认 SKIPPED 这一终态）。|

| 41 | **档 7B 关门 = ❌「不采信（配方退化）」+ 7C 按预注册正确跳过 + 档 7F/7G 武装并发车**（10-03 22:54 `runs/S7_VERDICT.md`、22:55 `runs/s7c.SKIPPED`；10-04 10:22 `runs/S7F_PREREG.md` 先落盘、10:41 `code/chain_s7f.sh` `setsid` 发车 PID=SID=442494、10:42 `code/chain_s7g.sh` PID=SID=442950、10:44 看门狗换清单重启 PID=SID=443707） | 🔄 **7F 在跑（F1 起，ETA ~14:30 出触发决定）**。① **7B 的四条读数**：**M1 = 0 胜 / 7 负 / 2 平**（9 个配对格、放宽口径、vs batch8-seed2000，Δrate 中位 **−10.0 pp**、符号 p=0.0156）⇒ **H7 的 P2「降梯度噪声 ⇒ 降 run 间方差」被证伪，而且方向相反**；M2/M4 TEST 反向放宽 **13/80 = 16.2%**（门 41.2% / 50%，Wilson [9.7, 25.8]）；M5 正向护栏 **1/20 = 5%** vs 基线 193/300=64.3% ⇒ 掉 **59.3 pp**（Fisher p=1.1e-07），侧躺 **0** 局、严格=放宽=13/80 ⇒ 不是「差一点送到」，是彻底做不出来；**而 M3 过了**（末点 loss **0.0330** ≤ 门 0.042、grdn 0.080 正常）⇒ 处方里的「查 M3 诊断」查不出东西，**闭环塌陷在训练日志里完全看不见 = 坑 59 最强的一次实证**。② **机理财账必须改口**：在飞哨兵 180 个同样本窗配对点（`runs/_diag/s7b_early_sentinel.md`）给出收敛期 grdn 比值 bs8/bs32 = **1.77**（epoch≈0 时是 1.298），固定 C=817.2 反解 **η₈≈91%、η₃₂≈71%** ⇒ 「batch8 每步梯度过半是采样噪声」这句话仍然为真，但**把它当缺陷是错的**：降噪声（bs32）在等 epoch 下全面更差 ⇒ 这些噪声在这个任务上像**正则/探索**。③ **7C 闸按预注册正确拦下**（`S7_VERDICT.md` 含「不采信」⇒ 不发车），**坑 62 的 SKIPPED 兜底当场生效、零假警**，闸读数留档 `runs/S7C_GATE.md`。④ **零 GPU 的曲线复盘**给出唯一还没检验过的便宜杠杆：三条 batch8 的 11 格 val 曲线里**两条在 epoch 3.102 见峰后回落**（seed1000 严格 峰 45%→末 35%、seed2000 放宽 峰 50%→末 **30%**、seed3000 单调升到 **75%** 且在 3.102 已 70%），而 7B 全程压在 20% 以下 ⇒ 「3.79 ep 这个预算可能已经过了峰」是**有盘上证据、且从未被检验过**的假设（⚠️ 单格 n=20、1σ≈11 pp ⇒ 形态本身不构成结论）。⑤ **档 7F/7G 预注册**（`runs/S7F_PREREG.md`，决策树与阈值全部写死）：**F1/F2** = 三个 seed 的 `018000` 在 TEST 上（**零训练**、1.5 h、**回溯**诊断 ⇒ 只回答「22.4 h 值不值得花」，不是使命门证据、不改档 3r 的 FAIL）；触发规则 **`MIN3102 = min(三 seed 反向放宽) ≥ 40/80 = 50%` ⇒ 发 7G、F4 不跑**，否则写 `runs/s7g.SKIPPED` 改跑 F4；**F3** = bs8 / 5500 步 / lr1e-4（与 7B **同更新数**、同时差 batch 与 epoch ⇒ 只能**排除** H-B，不给效应量，坑 57），判读带写死（|Δ|≤11 pp = 无差别 ⇒ H-B 成立；≤1/80 ⇒ 步数不是原因；≥23/80 ⇒ H-C）；**F4** = bs32 / 5500 步 / **lr 1e-4**（与 7B **唯一差 lr** ⇒ 判 H-A），4e-4 臂**有意省略**（理由写在预注册）；**7G** = bs8 / **18000 步 = 3.102 ep** / **新 seed 4000、5000、6000**（预算是回溯挑的，同 seed 验证有选择偏差 ⇒ 必须前瞻）+ 9 格 val 扫描 + TEST 反向 4×20 + 正向 20，主门 **G1 = 最差 seed 放宽 ≥50%**（与档 3r/7C **完全同一条**使命门）；G1 ✅ ⇒ 档 3r 的 FAIL 被推翻、使命证据链补齐、回用户阶梯第 6 步（纠正数据）；G1 ❌ ⇒ 转档 8，**不再烧配方实验**。⑥ **新工具** `code/mg_verdict_s7f.py`（一个文件两个模式，自测 **36/36**；出身核对按 `policy_ckpt` **尾串**逐条断言数字格 ⇒ 见新坑 63）。⑦ **预算/ETA**：F1+F2+F3 ≈3.7 h ⇒ **~14:30** 出 `S7F_DIAG.md` 与触发决定；触发 ⇒ 7G 三发串行 22.4 h，ETA **10-05 ~13:00**；不触发 ⇒ 续跑 F4（6.9 h 训练 + 1.2 h 扫描），**~23:20** 收后转档 8。显存守卫按 7A 实测峰值取（bs8 ≥36000 / bs32 ≥45000 / 评测 ≥9000 MiB），与预注册 §7 第 7 条的 20000 不一致 ⇒ 见新坑 64。⑧ 新增坑 **63**（关门评测的 ckpt 路径必须写**数字格**，写 `last` 会让出身核对判「不采信」）、**64**（预注册里的资源门槛必须从探针峰值表**复制**，不能凭记忆写）、**65**（自测的期望值必须由定义独立算 + 专测边界；这次是期望写错、代码是对的，而发车闸调 `--selftest` ⇒ 一条错期望能把 12 h 的链堵死）。|

| 42 | **档 7F 的 F1/F2 落地 ⇒「epoch 预算」这条杠杆也死了 + 转数据侧（档 8 纠正数据）全武装发车**（10-04 12:00 `runs/_diag/s7f_trigger_interim.md`、12:25 `runs/S8_PREREG.md` **先落盘**、12:25 格 8A-0 探针判 ✅、13:15 §9 增补落盘、13:13 `code/chain_s8a.sh` `setsid` 发车 PID=SID=512402、13:14 `code/chain_s8c.sh` PID=SID=512582、13:13 看门狗换清单重启 PID=SID=512110） | 🔄 **两条链在等 `runs/s7f.done`（认产物不看进程表）**；7F 的 F3 在跑（bs8/5500 步，13:13 时 3194/5500、~1.37 s/步 ⇒ 训练 ETA ~14:06、`runs/S7F_DIAG.md` ~14:40），F4 收工 ETA **~23:15**。① **F1/F2 的核心读数（零训练、回溯诊断）**：三个 seed 在 `018000`（epoch 3.102 = 两条 val 曲线的峰）vs 末点 `022000`（epoch 3.791），在**同一批 n=80 的 TEST seed** 上差 = **−2.5 / +2.5 / −1.3 pp**、Fisher p = **0.8661 / 0.8730 / 1.0000** ⇒ `MIN3102 = 35/80 = 43.8%`（Wilson [33.4, 54.7]）**< 触发门 40/80** ⇒ 机器可读行 `7G_TRIGGER=NO` ⇒ **22.4 h 的 7G 前瞻验证不发车、省下**；val 曲线上「见峰后回落 −10/−20 pp」的形态**在 n=80 上不存在**（新坑 66）。② **战略含义**：配方侧两条便宜杠杆 —— **batch**（档 7B 全面退化，13/80=16.2%）、**epoch 预算**（本条，Δ≤2.5 pp、p≥0.87）—— **都试完且都不够** ⇒ 按 `runs/S7F_PREREG.md` 写死的分支「G1 ❌ ⇒ 转档 8，不再烧配方实验」**转数据侧**（用户阶梯第 6 步）。档 3r 的 ❌ FAIL（41.2 / 68.8 / 80.0%，极差 38.8 pp）**原样保留**，只有 7G 的 G1 在新 seed 上过门才能推翻它。③ **档 8 预注册**（`runs/S8_PREREG.md`，**12:25 落盘早于本档任何 8A/8B 读数**）：唯一问题 = 让脚本专家在**策略自己访问到的失败状态**上接管（HG-DAgger 风格），把片段（含图像）追加进原数据集重训**坏 seed 2000**，能不能把反向 TEST 放宽从 **41.2%** 抬到 **≥50%**（与档 3r/7C/7G **完全同一条**使命门）。门写死：8A 三门 **A1 ≥2000 可用帧 / A2 接管局放宽成功率 ≥40% / A3 片段步数中位 ≤300**、合并三闸 **B1/B2/B3**、8C 判定 **D1 主门 ≥40/80 / D2 正向掉幅 ≤15 pp / D3 配对净胜 ≥+8 ∧ 单侧 p≤0.05 / D4 三 seed min ≥50%**；设计是「**等步数不等 epoch**」（两臂 `STEPS` 都 22000）⇒ 8C-ctl 用 `--dataset.episodes=0-179` 做 1:1 归因（**条件发车**：D1∧D2 过才发）。④ **§9 五条增补**（13:15 落盘，**没有任何一条阈值被改**，改的都是「同一个门槛该量在哪个总体上、截到哪一步」）：**增补1（承重）** 采集片段必须在「**放宽成功**」闩锁那一步截断 —— `code/mg_env_reverse.py:235` 的 `terminated` 只认**严格** success，放宽成功**不终止** ⇒ 侧躺送达的局（正是用户 2026-10-02 授权的主口径成功局）在 `horizon=800` 下会一路空转，尾巴全是 `retreat`/原地保持的垃圾帧，而 `seg_len = 800−接管点` 通常 400~730 ⇒ **过滤3「段长≤300」会把主口径成功局整段误杀**（盘上实证：`runs/s5_1_handback_rev_test20_k10_rep2` 有 `takeover_step=200 / seg_len=201 / steps=400 / 放宽=True`）；帧与相位用**同一个索引口径**一起截（`trim_index()`），保留 `seg_steps < succ_step_rlx` 的帧（**含**造成成功的那一帧 —— 那一步的动作最该学）。**增补2** A3 中位的总体 = 「**放宽成功**的接管片段」（= 过滤3 真正作用的那批），全部接管的中位另存 `seg_len_median_all_takeover` 只透明不进判据 —— 否则把采集 horizon 从 400 抬到 800（本档有意为之）会**必然挂门**，那是口径走样不是质量变差。**增补3** 8C 的 epoch 派生数字更正：目标 M=7000 ⇒ 全集 **53426** 帧 ⇒ 22000 步 = **3.294 ep**（对照臂只采 0-179 集 = 46426 帧 ⇒ **3.791 ep** 不变），设计与判据一字不改。**增补4** 8A-0 已判过。**增补5** 零 GPU 端到端预演 + 当场抓到的三个真 bug。⑤ **格 8A-0（零 GPU 探针）✅ 过**（`runs/s8a_probe/append_probe.md`，12:25、4.2 s）：原**数据负载**（`data/` parquet + `images/` png）**逐比特改写 0 个**、删除 0 个、meta 只改白名单内 2 个、10→11 集 / 2290→2302 帧、`state[0].max` **0.1912→0.4522**（⇒ stats 确实按**全集**重算，这是两臂共享 normalizer 的前提）、追加集 12/12 帧回读逐比特相同 ⇒ **建集走「复制 + 追加」，B 计划（全量重编码）不发车**。⚠️ 探针**自身**在跑之前修过一处自相矛盾（**不是**看完数改门）：原断言1 把 `meta/` 也算进「原有文件不许改写」，与断言3「stats 必须重算」直接冲突 ⇒ 拆成两口径（`data/`+`images/` 逐比特不变 / `meta/` 只许白名单改写且一个都不许删），自测 23→**32** 条，备份 `.bak_pre_metascop`/`.bak_pre_synfix`。⑥ **新工具三件（自测全绿）**：`code/mg_collect_corr.py`（1141 行、自测 **94/94**；`--mode collect` = 策略 rollout→检测器触发→`ScriptedExpert.resume` 接管→三过滤→写 `data/corr_r1`；`--mode merge` = 追加进 `data/mix60f120r_c1` + B1/B2/B3 + 逐比特）、`code/mg_verdict_s8.py`（461 行、自测 **42/42**；出身核对要求 `policy_ckpt` 尾串是**数字格** `checkpoints/022000/pretrained_model`，坑 63）、`code/mg_ds_append_probe.py`（430 行、自测 **32/32**）。**零 GPU 端到端预演全过**（`runs/_smoke_s8_collect/`，stub 策略不加载模型）：检测器 T1@8 触发 → 专家 249 步做完 → 截断后 **242 帧**收下 → 回读自证全过（**3 s/局**）；合并 2 集/493 帧 ⇒ B1（10→12 集、2290→2783 帧）/ B2（负载改写 0）/ B3（tasks 恰好 2 句、stats 覆盖并集）/ 逐比特（抽查 61 帧 × 5 字段全等）**全过**，预演数据集已 `shutil.rmtree` 清理 ⇒ 预注册估的「8A ~35 min / 8B 1.5~2.5 h」是**上限**。⑦ **两条链 + 看门狗小手术**：`code/chain_s8a.sh`（205 行、**9 道闸**，终态 `runs/s8a.done` / `s8a.HELD`（产出率不够 ⇒ 停下等人）/ `s8a.FAILED`）、`code/chain_s8c.sh`（204 行，D1∧D2 过才条件发车 8C-ctl）；看门狗备份 `chain_watchdog.sh.bak_pre_s8` → manifest +s8a/s8c、**新增 HELD 终态**（坑 62 家族：「合法地决定不做」也算终态，且只报一次警）→ 重启 **PID=SID=512110**；13:13:16 那两条 MISSING 假警（看门狗先于链重启）已在 `logs/ALERTS.log` 补注。⑧ 新增坑 **66**（n=20 的 val 曲线**形态**不能用来选 epoch 预算 —— 坑 27/42 在「选预算」这个新用途上的第三次复现）、**67**（夹爪语义是**反的**：+1=闭合，而 `mg_env.contract()` 里那句 `"-1 = close"` 是**错的**；冻结文件只记不改）、**68**（lerobot v3.0 读写口径不对称 + 空数据集会去连 HF，两者都会把真读数埋进堆栈）。⑨ **ETA / 预算**：8A 标定+三门 ~**10-05 00:10** → 8B 采集+合并 → 8C 训练（22000 步 bs8 ≈8.3 h）→ **D1 使命门读数 ~10-05 15:00**（`runs/S8_VERDICT.md`）；磁盘一个检查点 20 GB、档 8 全链最多 ~865 GB，`/workspace/mnt/sppro` 余 20 TB。|
| 43 | **档 8 · 8A 产出率的事前预测（零 GPU、只读旧语料）⇒ 预测「A2 大概率不过」+ 事前排除一个 HELD 候选 + 两条链逐闸预检**（10-04 14:15 `code/mg_forecast_s8a.py`（798 行、自测 **61/61**）→ `runs/_diag/s8a_yield_forecast.{md,json}`、`runs/S8_PREREG.md` §9 **增补 6**、`runs/_diag/tax_s3r_seed2000_rev.md`） | ⚠️ **风险预警（不是读数；门一条都没改）**。① **三条门的事前预测（两把尺并列，不许只报好看的那把）**：**A1**（≥2000 帧/80 局）grasp 尺 2619 帧 / 触发尺 **1117** 帧 ⇒ 跨在门两侧；**A2**（≥40%）grasp 尺 **35.7%** / 触发尺 **15.2%** / 靶子构成校正 **17.0%** ⇒ **三个点估计全部低于门**，模型区间 L 22.9% / M 35.7% / **U 上界 42.9%**（只有上界刚碰到门）；**A3** 中位 209.5 ≤300、handback 恒 0、窗口闸 9 已断言 ⇒ **稳过** ⇒ **`s8a.HELD` 的概率明显高于 `s8a.done`**。② **承重的机理读数（比门本身重要）**：语料（档 5.1 的 80 局、horizon=400、**好 seed** 的末点）里 **27 个失败接管全部跑满 400 步** ⇒ 「失败」与「步数不够」在 400 步窗内**完全混淆**；按「到不到 grasp」分层后 —— **「未到 grasp 但步数足够」12 局成功 0 局**、**「到 grasp 且步数足够」6 局成功 5 局（83.3%，Wilson [0.44, 0.97]）** ⇒ **瓶颈是脚本专家从「策略访问到的状态」到不了 grasp（approach/descend 的实现），不是步数预算** ⇒ 预注册 §3 的三个 HELD 候选里「**抬 horizon**」被**事前排除**（再加步数没有用），「降目标帧数」仍可行。③ **功效警告（新坑 69）**：A2 是在 **~35 个接管**上判 40% 的门 ⇒ **1σ≈8.1 pp** ⇒ 一次 HELD 只能读成「n=80 局的标定分不开 32% 与 40%」，**不能**读成「产出率确定不够」。④ **靶子特异的证据**：坏 seed 2000 的反向 TEST 放宽失败 **A 24 / B 17 / C 6**（A 占 **51%**，分类用 `mg_tax_fail.klass(...,'relaxed')`，**import 不重写**）⇒ 按 A⇒T1、B/C⇒T3 映射（**映射不是测量**，出处写在工具头）得靶子触发构成 T1 51% / T3 49%，而语料里 **T3 的 with-room 只有 3 局且 0 成功**（Wilson [0.00, 0.56]，工具按 `LOW_POWER_N=5` 打 ⚠️ **低功效**标 ⇒ 触发尺应读作偏下界）。⑤ **HELD 处置顺序事前写清**（免得半夜现编）：**(a) 首选** 另立一档修专家的 reach-grasp（新预注册、新档号；**前置条件是出身可比性** —— `mg_expert.py` 冻结、`mg_expert_reverse.py` 是 180 条示范的生成器 ⇒ 只能在纠正采集里用 v2 专家、示范保持 v1，差异写进数据卡片）；**(b) 次选** 接受较低 A2、按实际帧数走 8B/8C，但必须打 `A2_BELOW_GATE` 标并写明「语料只覆盖**可救回**的那部分失败状态 ⇒ D1 的效应量被低估」—— **这是改门，必须由人显式批准并留档（坑 40），链不许自己做**；**(c) 兜底** 认定杠杆产出率不够 ⇒ 转阶梯 7（RL）。⑥ **一处资源参数差**（坑 64 惯例：记在这里、不回改正文）：§3 写 8B 上限 **400** 局，`chain_s8a.sh` 的 `B_MAX_EPS` 默认 **320**；承重的是 A1 门口径（25 帧/局 ⇒ 7000 帧需 **280 局 ≤320**）⇒ 够用，设计与判据一字未改。⑦ **顺带把两条链的 9+6 道闸逐条对盘上现实预检了一遍**（纯只读、零风险）：闸2 分母 180 集/46426 帧 ✅、闸3 `checkpoints/last → 022000` 且 `model.safetensors` 在 ✅、闸4 两个示范 npz ✅、闸5 三个自测 **94/42/32** 全绿 ✅、闸9 现算 8A=9000..9079 / 8B=9080..9399 与 5 个评测窗口**零冲突**且互不相交 ✅、`data/corr_r1` 与 `data/mix60f120r_c1` 均不存在（不会撞半成品）✅、`mg_verdict_s8.py` 无产物时优雅返回 `S8_*=UNKNOWN` 且 rc=0 ✅、判定工具的 `ARM_C`/`ARM_CTL`/`rev_dirs` 与链产出的目录名**逐个对上**（坑 63 的契约两侧）✅、磁盘余 20 TB ✅。⑧ 新增坑 **69**（门的分辨率必须匹配它的样本量；A2 在 ~35 个接管上判 40% ⇒ 1σ≈8 pp，一道分辨率不够的拦路闸会以「看起来客观」的方式随机决定整条链走不走）。|
| 44 | **档 7F 的 F3 归因落地 ⇒ 命中 `HIGHER` 分支、`H-C`（大 batch 本身有害）拿到 p=0.004 的证据；采集器的 descend 盲区诊断零影响已验证**（10-04 14:34 `runs/S7F_DIAG.md`、14:25~14:33 `runs/_diag/diagchk/VERDICT.md`、14:35 `runs/S8_PREREG.md` §9 **增补 7**） | ① **F3 读数（判读表出自 `runs/S7F_PREREG.md` §3，**事前**写死；阈值 ±11 pp / ≥12 pp 一字未改）**：`bs8 / 5500 步（=0.948 ep）/ lr1e-4 / seed2000`（与 7B **同更新数**）的反向 TEST 4×20 放宽 = **30/80 = 37.5%**（Wilson [27.7, 48.5]；逐 rep 40 / 45 / 30 / 35%、严格 17/80=21.2%、侧躺 13 局）vs 7B 的 **13/80 = 16.2%** ⇒ **Δ = +21.25 pp、Fisher 双侧 p = 0.0040** ⇒ 命中 **`HIGHER`** 分支 ⇒ **H-C（大 batch 本身有害、梯度噪声在这个任务上是正则）**。这是档 7 系列**第一个 p<0.05** 的读数（此前 F1/F2 的 Δ 全在 ±2.5 pp、p≥0.87）。口径出处：`code/mg_verdict_s7f.py:175` 收的是 `n_success_relaxed`（放宽 = 主口径），`S7B_REV=(13,80)` 是 7B 的**放宽**（7B 严格==放宽，故无歧义）。② **两条护栏不许越**：F3 与 7B **同时**差 batch 与 epoch ⇒ 它只能**排除 H-B**（更新步数），**不能**给 batch 的效应量（坑 57）；且 H-C 按预注册要「**F3 与 F4 都排除不了时**才成立」⇒ **F4**（`bs32 / 5500 步 / lr1e-4`，与 7B **唯一差 lr**，判 H-A）**14:34:22 已发车**（41.7 GB / 100% util；ETA 训练 ~21:30 + 评测 ⇒ `runs/s7f.done` ~**23:15**，`runs/S7F_DIAG.md` 届时按 `--mode f` **重跑覆盖**成 F1~F4 全量版）。F3 正向护栏 **3/20 = 15.0%**（7B 5.0%、seed2000 末点 20.0%）⇒ 坏 seed 的正向本就低、F3 无正向门 ⇒ 无新信息。③ **一条事后观察（不是门、不改任何设计）**：F3 与档 3r-seed2000 构成**干净单变量**对照（同 bs8 / lr1e-4 / seed，只差步数 5500 vs 22000）⇒ 30/80=37.5% vs 33/80=41.2%、**Δ = −3.75 pp、Fisher p = 0.746**（对 `018000` 是 −6.25 pp、p = 0.520）⇒ **本任务上 4× 的训练步数买不到可测收益**（0.948 epoch 就到 37.5%）。⚠️ 这是**看完数才注意到的**、n=80、单 seed，且是「**无差别**」证据（p=0.75 只说明分不开、不说明等价）⇒ **不许**据此改 8C 的 `STEPS=22000`：D1 要与档 3r/7C/7G 的 **41.2%** 基线**同口径**可比，改步数等于换尺（坑 27/42/66 家族）。留档为「若 8C 之后还要再训，先做一档**预注册**的步数消融」。④ **descend 盲区诊断零影响已验证**（§9 增补 7）：两版并跑 + **同版本跑两遍当基线** ⇒ 结构量全等（2 局/493 帧、ep0=242/ep1=251、`T1@8`、相位串、`steps=249/258`）、`observation.state`/`action`/5 个索引列**逐比特相等**、merge 五闸在 `--target-frames 493` 口径下全 ✅ 且读数与增补 5 那次预演**逐字相同**、`[diag]` 行 + npz 正常产出（493 专家步 / 2 局）、stub 局 `n_blind=0`（**无假阳性**：那两局近垂直下探、`z_err` 恒在带外 ⇒ 停滞判据看得见）、自测 **94→111 全绿**。⑤ 新增坑 **70**（渲染跨进程不确定 ⇒「逐比特复现」不是合法验收口径；任何「改动前后对比」必须配一次「改动前 vs 改动前」的地板）。⑥ 临时产物**全清**（6 个 `data/tmp_diagchk_*` / `tmp_merge_dst_*` + 3 个 `*_raw.npz` + `code/_tmp_cc_pre_diag.py`）⇒ `data/` 回到 7 项、`code/` 无 `_tmp*`；备份 `code/mg_collect_corr.py.bak_pre_diag`、`runs/S8_PREREG.md.bak_pre_addendum7`、`README.md.bak_pre_pit70` 留档。|
| 45 | **档 8 的事前病因诊断：离线分类账 + 一条把离线路线判死的效度门 ⇒「descend 盲区」被证实存在，但最锋利的读数是「进 grasp 的两个条件几乎从不同时成立（0.33%）」**（10-04 15:15 `code/mg_diag_nograsp.py`（729 行、自测 **65/65**）→ `runs/_diag/nograsp_corpus.{md,json}`、15:25 `runs/S8_PREREG.md` §9 **增补 8**） | ⚠️ **只透明、不进任何门**；门一条没改。① **口径为什么可信**：`mg_eval_harness.py:183` 存的是 `env.step()` **之前**的 obs，与 `mg_expert.__call__` 读的 `env.eef_pos` 同源 ⇒ 盘上 `state[i,0:3]` 就是专家算第 i 步时看到的 eef；can 初态由 seed 决定 ⇒ 20 次 `env.reset(seed)` 重建，交叉核对 **`max|Δcan_z0| = 1.11e-16`**（机器精度）。② **效度门（本条最重要，新坑 71）**：20 局「从未到 grasp」的接管里 **15 局（75.0%，Wilson [53.1,88.8]）逻辑矛盾** —— 相位串含 `descend`（⇒ 对**真** can 必然 `xy_ok` 过）而按初态重建的 `xy_err` 从未 <8 mm（个别达 **667 mm**）⇒ **can 在接管前就被策略撞走/夹起又掉了**；独立佐证 `max_lift_cm` 12~20 cm。第一版结论（「75% 卡在 approach、xy 从未对准」）**因此被撤回** —— 数值核对全过、逻辑对撞才发现（坑 71）。盘上 npz **没有逐步 can 位姿** ⇒ 离线路线只能**检测**不能**修正** ⇒ 几何统计只按剩下 **5 局**算（`LOW_POWER`）。③ **可信子集（5 局 / 1197 专家步 / 放宽成功 0/5）的读数**：归因 `R2_descend_blind` **3/5**、`R4_visible_not_rescued` 2/5、`R1_approach_stuck` **0**、`R3_ladder_exhausted` **0**；逐步几何区 S1 737(61.6%) / S3 262(21.9%) / S2 166(13.9%) / S4 28(2.3%) / **S0 4(0.33%)**；**无论相位都看不见**（S2+S3）= **35.8%** 的步。④ **最锋利的一条**：xy 对准过的步只占 **2.7%**、z 在带内的步占 14.2%，而**两者同时成立**（S0 = 真正能进 grasp 的窗口）只有 **4/1197 = 0.33%**（xy 对准的 32 步里高度也对的 4 步；高度在带内的 170 步里 xy 也对的 **4 步 = 2.4%**）⇒ **增补 7 猜的 descend 盲区被证实存在，但它不是主症**：主症是「`descend` 的进入条件是 xy 已对准，可下降过程中 xy 会漂出去，而漂出去之后**没有任何机制能在 z 带内重新对准 xy**」。⑤ **对档 9（若 8A 写 HELD）的设计含义，事前写下**：光给 descend 补一个「带内停滞」判据只能让它**认输**、**不能**让它抓到；要改的是**解耦** —— (i) z 带内新增横向微调相位 `align`、(ii) 先降到略高于带→对准 xy→再垂直下探、(iii) 放宽 `XY_TOL/Z_TOL`；**三者优先级留给档 9 的预注册，本条不选**（拿 5 局 LOW_POWER 数据定设计 = 坑 27/42/66/69 家族）。⑥ **增补 7 的价值因此升级**：采集器的 `descend_diag()` 每步读**当时**的 `env.object_pos`（不是初态）⇒ 它是**唯一**能给出无偏版本这份分类账的仪器 ⇒ 8A 若 HELD，当晚就能定因。⑦ 顺带查到 A2 的一条**有界污染**并算过量级 ⇒ 决定不再动采集器（新坑 72）。⑧ 新增坑 **70 / 71 / 72**。⑨ 备份：`code/mg_diag_nograsp.py.bak_pre_validity`、`runs/S8_PREREG.md.bak_pre_addendum8`、`README.md.bak_pre_pit71`。|
| 46 | **CPU-only「重放接管台」⇒ 8A 的三条门拿到**事前实测**（不是模型外推）：全部过门；并把增补 6 的偏差方向纠正过来**（10-04 16:25 `code/mg_s9_rescue.py`（845 行、自测 **89/89**）→ `runs/_diag/s9_rescue/{FINDINGS,REPORT}.md`、`runs/_diag/s9_validate/`；`runs/S8_PREREG.md` §9 **增补 9**） | ⚠️ **只诊断与事前预测，不改任何门**（A1/A2/A3、B1-B3、D1-D4 一字未动）；`mg_expert.py`/`mg_harness.py`/`mg_collect_corr.py` 全是 **import**，冻结文件一个没碰。① **为什么重放是合法的**：`env.reset(seed)` 钉住全部随机源、物理与渲染尺寸无关 ⇒ 把录像里的 action 原样喂回去轨迹**逐比特**复现；实测 **300 局 `max|Δeef| = max|Δwidth| = 0.0e+00`**（语料是 `img_size=224` 录的、重放用 8 ⇒ 顺带证明渲染尺寸不扰动物理），被保真门剔出 **0 局**。② **三条外部对账**：接管步 vs 原 harness 跑的 `takeover_step` **18/18 逐局相符、0 不符**；接管局数 vs 增补 6 语料实测 **35 vs 35**（逐格 7/11/8/9）；纯重放（检测器关掉）复现放宽成功 **14/20 = 70.0%**，与 `eval_summary.json` 的 `pc_success_relaxed` 逐字相同。③ **8A 三门的事前实测**（主组 = 坏 seed 2000 / **val 窗口 8000..8019** / horizon **800** = 采集口径）：池化 11 格 220 局、接管 **175**（79.5%）⇒ **A2 = 109/175 = 62.3%** [54.9, 69.1] ✅、**A1 = 18980 帧/220 局 ⇒ 折算 6902 帧/80 局** ✅、**A3 中位 233** ✅；单看 8A 真正要用的那条检查点 `022000`：**A2 = 11/16 = 68.8%** [44.4, 85.8]（**Wilson 下界就已过门**）、A1 4500 帧、A3 251 ⇒ **三门全过**；`unrecoverable` **0 次**、删失仅 8/220 局。⇒ **增补 6 预测的 `s8a.HELD` 大概率不会发生**（本条早于 8A 任何读数落盘）。④ **增补 6 错在哪：偏差方向判反了**。同一份好 seed 语料抬到 horizon 800、换成采集器的 `hand_back=False` 后实测 **A2 = 12/35 = 34.3%** [20.8,50.8] ⇒ 与它的模型 **M（35.7%）几乎重合 ⇒ 模型算术没错**；错的是「拿好 seed 的语料外推坏 seed 的产出率」这一步，而增补 6 自己标注的偏差方向（「坏 seed 更难 ⇒ 本预测偏乐观」）是**反的**，实测**偏悲观 28 pp**。⑤ **机理（无偏 can 真值，逐步取自重放 ⇒ 不需要增补 8 那道效度门）**：两组初态倾角都是 **0.00°**、`can_z0` 都是 0.8603 ⇒ 接管瞬间的 `TILT`（>10°）是**局内被撞倒的**。构成 —— 坏 seed **CLEAN 53.7% / MOVED 20.6% / TILT 25.7%**，好 seed **CLEAN 8.6% / MOVED 25.7% / TILT 65.7%**；分类 A2 —— CLEAN **72.3%**、MOVED 63.9%、TILT **40.0%**（好 seed 的 TILT 只有 21.7%）。⇒ **策略越强，留下的接管状态越难**：好策略真去抓、抓起来又掉 ⇒ can 倒地；差策略在 can 上方空挥、根本没碰着它 ⇒ can 还立着。⑥ **顺带修正增补 8 的 LOW_POWER 诊断**：175 个接管上重算，descend 步 34722 里带内盲区 3925（11.3%）+ 显著低于抓取面 10451（30.1%）⇒「停滞判据看不见」合计 **41.4%**（与增补 8 的 35.8% 同量级，盲区**确实存在**），**但**「未到 grasp」的 63 局里 `blind_dominant` 只有 **3 局**、`unrecoverable` **0 次** ⇒ **盲区不是主因**；到 `grasp` 的 112 局成功 **90.2%**、未到的 63 局只有 **12.7%** ⇒ 瓶颈仍是「到不到 grasp」，而到不了的主因是 **can 已被撞倒**（专家的 `can 中心 + GRASP_OFFSET_Z` 几何假定 can 立着）。⑦ **档 9 的优先级因此事前重排**（若 8A 仍 HELD）：(1) **侧躺 can 的抓取几何**第一优先、(2) 增补 8 的带内横向对准 (i)/(ii) 降为第二、(3) 放宽 `XY_TOL/Z_TOL` 最不优先；出身可比性前置条件不变（纠正采集可用 v2、**180 条示范保持 v1 逐比特**）。⑧ **纪律**：重放台吃的是**评测窗口**的录像 ⇒ 对 D1 的 TEST 窗口 7000..7019 有**硬闸**（指过去直接拒绝执行，除非显式 `--allow-test-window` 并打 🚨`TEST_WINDOW_CONTAMINATION`）；主组一律用 **val 8000..8019**，验证组只用于验工具。⑨ 新增坑 **73**。⑩ 备份：`code/mg_s9_rescue.py.bak_pre_a3fix`/`.bak_pre_selftest2`、`README.md.bak_pre_pit73`、`runs/S8_PREREG.md.bak_pre_addendum9`。|
| 47 | **重放台第二遍（确定性再证）+ 两条新读数 ⇒「8B 那份纠正数据教的是什么」拿到事前实测；坑 72 的量级被两个总体夹住；渲染器 4 处口径 bug 修掉**（10-04 17:06 `runs/_diag/s9_rescue/DRIVE2.done`、17:25 FINDINGS 由渲染器重出 127→162 行、`runs/S8_PREREG.md` §9 增补 10） | ✅ **零 GPU、不改任何门**。① **确定性**：主组 11 格 + 验证组 4 格**全部重跑**，接管数 / A2 / 可用帧 / 状态类计数与上一遍**逐字相同**（主组池化 175 接管、A2 109/175 = 62.3%、18980 帧、A3 233.0；验证组 35 接管、12/35 = 34.3%）⇒ 重放台是**可复现的实测**，不是一次性随机数；增补 9 的结论原样有效。② **新读数一 `frames_by_state_class`（= 8B 的数据构成）**：总体必须是 `022000`（8A/8B 的唯一接管源）⇒ **CLEAN 0 帧 / MOVED 726（64.5%）/ TILT 399（35.5%）**，而池化 11 格是 70.9/18.4/10.8 ⇒ **增补 9 那张池化表不能读成 8B 的构成**（新坑 74）。含义：8B 里**没有**「策略空挥、can 还在原位」的教材（唯一的 CLEAN 接管段长 396 > 300 被过滤 3 砍掉），教的是**搬运途中/末期**（MOVED，该类 A2 6/7 = 85.7%）与**被撞斜/撞倒**（TILT，A2 4/8 = 50.0%）的救球，接管步中位 **150/800**；且 8 局 TILT 里 **6 局**段长 323~715 被过滤 3 砍掉 ⇒ 最难的救球进不了数据集（设计使然：只收高效完成）。**对 D1 的事前含义**：若 D1 不过，第一个查**覆盖偏差**（教材在晚段救球，失败可能在早段第一次抓取的精度）—— 这条本台在 val 上答不了（TEST 窗口有硬闸），只能等 8C 的 11 格 val 曲线与 D1 一起读。③ **新读数二 · 坑 72 直接测量**：宽口径（xy 已在框内）`022000` 2/16 = 12.5% / 主组 12/175 = 6.9% / 好 seed 2/35 = 5.7%，但宽口径混了「真·已赢只差落定」（段长 18/19）与「已进框但侧躺」（105~187、2 局倾角 90°）；按段长 ≤30 分开后真·已赢 = **1/16 = 6.2% / 8/175 = 4.6% / 1/35 = 2.9%**（与坑 72 原记录一致）⇒ A2 三口径 **68.8→66.7→64.3%**（`022000`）、**62.3→60.5→59.5%**（主组）全部远高于门 40%，真·已赢的帧只占 **0.8%/1.6%** ⇒ **门不是坑 72 的假象；结论不变：不改门、不动采集器**。④ **工具卫生**：渲染器 `_gen_findings.py` 4 处口径 bug（对账② 与坑 72 表两处分母把 `takeover.n`（局数）当成 `.k`（接管数）；§五 拿池化总体当 8B 构成；§六「只贡献十几帧」在 `022000` 上说过头 —— 宽口径是 205 帧 = 18.2%）已修 + 加 assert；备份 `.bak_pre_popfix`、`FINDINGS.md.bak_pre_drive2render`、`README.md.bak_pre_pit74`、`runs/S8_PREREG.md.bak_pre_addendum10`、`STAGE_PLAN.md.bak_pre_eta2`。⑤ **F4 在跑**：17:12 到 `002000`/5500、~4.8 s/步（40 min/500 步）⇒ 训练 ~**21:52**、11 格 val 扫描 + F4 TEST ⇒ `runs/s7f.done` ~**23:45**（比 16:30 那版 ETA 早 ~1 h）⇒ 8A ~**00:30**、8B+合并 ~**01:30**、8C 训练 8.3 h ⇒ **D1 使命门读数 ~10-05 12:30~14:00**。⑥ 顺手核过 **8C 的两处静默失效点**：`mg_verdict_s8.py --selftest` **42/42** 全绿；链里 `test_block` 的目录前缀（`s8c_seed2000` / `s8c_ctl_seed2000`）与判定工具的 `ARM_C`/`ARM_CTL` **逐字对得上**；`--dataset.episodes=0-179` 不重算 stats（出处 STAGE_PLAN 档 2e 的 md5 对账）⇒ 8C-ctl 的 normalizer 与 8C 逐比特相同、D3 归因干净。 ⑦ **8C 的机理读数已事前定口径并自动化**：新旁链 `code/chain_s8mech.sh`（17:36 `setsid` 发车 PID=SID=**28867**、`WAIT_H=30`、零 GPU、**不是门**）+ `runs/S8_PREREG.md` §9 **增补 11** —— 等 8C 的 11 格 val 扫描齐（它跑在 TEST 之前）⇒ 重放台量「放宽成功率 / 接管率 / 状态类构成 / A2」并与坏 seed 原臂**逐格配对**，末格再跑 `--mode fidelity` 做**自检**（纯重放的放宽成功必须与该格 `eval_summary` 逐字相同，不过 ⇒ `COMPARE.md` 打 🚨、链写 `MECH.FAILED`、读数全部作废）⇒ **D1 落盘前 ~1 h** 就有「纠正数据到底改了什么」的账，且判读规则（D1 ✅/❌ 各两种分支该查什么）已写死；冒烟用对照臂自比过：11 格 Δ 全 **+0.0**、逐格放宽成功率 5/10/10/10/15/15/20/40/50/45/30（%）与预注册 §1.2 那张 seed2000 val 曲线**逐字相同**。|
| 48 | **使命门第一次关上：D1∧D2∧D3 三门全过（8C = 65/80 = 81.2%），归因成立（净胜 +17、p=0.0038）；机理账「教的是搬运、不是防撞」；8D 两个新 seed 已发车；7H 新提案已武装**（10-05 19:53 `runs/s8c.done` + `runs/S8_VERDICT.md`、09:42 `runs/_diag/s8_mech/COMPARE.md`、20:45 `code/chain_s8d.sh` `setsid` PID=SID=**334638**、21:04 `runs/S7H_PREREG.md`、21:12 `code/chain_s7h.sh` PID=SID=**346154**；`runs/S8_PREREG.md` §9 **增补 12**） | ✅ **D1 ✅ 65/80 = 81.2%** Wilson [71.3,88.3]（严格 51/80、四格 18/15/18/14）≥ 门 40/80 ⇒ **标准配方最差的那个 seed（2000）第一次过使命门**；**D2 ✅** 正向 16/20 = 80.0%、掉幅 **−15.67 pp**（比基线 193/300 = 64.3% 还好）；**D3 ✅** 8C vs 8C-ctl（同数据集 `--dataset.episodes=0-179`、同 stats/同步数/同 lr/同 seed，唯一差 = 纠正帧在不在被采样）配对 **80 对**：净胜 **+17**（27/10/38/5）、单侧 **p=0.0038** ⇒ **抬升是纠正帧的功劳**，不是重训/新 normalizer 的副作用；8C-ctl = 48/80 = 60.0%。**D4 ⏳**（缺 seed4000/5000）⇒ `S8_MISSION_GATE=CLOSED`（n=1 个训练 seed）、`S8_TRUST=YES`。 ① **8A 三门实测全过**：A1 **4788 帧/80 局**、A2 **31/49 = 63.3%** [49.3,75.3]、A3 中位 **216**/handback **0**/窗口不相交；接管 49/80 = 61.3%、收下 25 段、9.3 s/局 ⇒ 与**重放台的事前实测**对账：预测 62.3%（同总体）/68.8%（`022000`）vs 实测 **63.3%** ⇒ 差 **1.0/5.5 pp**，而增补 6 那个「拿好 seed 外推坏 seed」的模型 M 预测 35.7% ⇒ 实测高 **27.6 pp** ⇒ 坑 73 的偏差方向错误被实测钉死。8B：`data/corr_r1` **39 集/7212 帧**、合并集 `data/mix60f120r_c1` **219 集/53638 帧**、B1/B2/B3 `all_pass`。 ② **机理账（`COMPARE.md`，保真自检 ✅ 纯重放 13/20 == `eval_summary` 13/20、`max|Δ|=0.0e+00`）**：池化 11 格 220 局/臂 ⇒ 放宽成功率 22.7%→**55.5%**（+32.7 pp）、接管率 79.5%→**50.9%**、A2 62.3%→50.0%，但 **`TILT` 绝对局数 45→47（几乎没变）**、占比升只是分母减半 ⇒ 按增补 11 写死的判读规则命中「D1 ✅ ∧ 接管率↓ ∧ TILT 没降」的混合分支 ⇒ **机理部分证实：教的是「搬运途中别失手」（非 TILT 接管 130→65、正好减半），没教「别把 can 撞倒」**；A2 下降与坑 73「策略越强、留下的接管状态越难」一致 ⇒ **档 9 第一优先级维持「侧躺 can 的抓取几何 / 防撞」，而且现在有了正面证据（TILT 是唯一没被纠正数据动过的失败类）**。⚠️ 两臂跨数据集 ⇒ 只读方向、不进任何门。 ③ **8D 已发车**（`code/chain_s8d.sh`，175 行；闸 1-7 全过：`s8c.done` 含 D1∧D2 PASS、`S8_VERDICT.md` 含 `^S8_D3=PASS`、合并集 ==219/53638、merge `all_pass`、npz、verdict 自测 **42/42**、8C 四格 TEST 产物齐、GPU free 81153 ≥ 36000）：配方与 8C **逐项相同**（`mix60f120r_c1` 全集/bs8/22000 步/lr1e-4/save2000 ⇒ 11 格），唯一差 = seed **4000、5000** 串行；每 seed：11 格 val 扫描（与 8C **同数据集同 stats** ⇒ 干净配对）+ TEST 反向 4×20 + 正向 1×20（**副读数、不是门**）⇒ 主读 **D4 = min(2000,4000,5000) ≥ 40/80**；**不自动降门、不自动重跑**。**ETA 按 8C 的实测分段算**（8C-ctl 那一臂：训练 **8.55 h** + 11 格扫描 **1.09 h** + TEST 5 读 **0.43 h** ⇒ **每臂 10.07 h**）⇒ 2 臂串行 ≈ **20.2 h** ⇒ ~**10-06 17:00（±0.5 h）**；起步对账 21:22 到 1611/22000、tqdm 剩 `7:43:38`、显存 33799 MiB = 坑 64 峰值 ⇒ 与 8C 同速率。⚠️ 两个在飞脚本（`chain_s8d.sh`/`chain_watchdog.sh`）头注里的旧估「15:30~16:30」按坑 22(d) 不改，就地更正留痕。 ④ **机理旁读已参数化并双发**：`code/chain_s8mech.sh` 加 `TAG/TITLE/CTL_DESC/CTL_DESC2/RULES_NOTE/LOG/EXTRA_MARKS/UPSTREAM_HINT`（**默认值逐字保留 8C 行为**；**冒烟对账**：默认参数重出 8C 的 `COMPARE.md` 与归档版**只差有意新增的那一行**），两个实例 20:52/20:53 发车（PID=SID=**337904/338238**、`WAIT_H=40`），对照臂 = **8C**（同数据集 ⇒ 唯一差 = seed）。⚠️ 等待行的 echo 文案仍写「等 8C」（旧文案）—— 实例在飞 ⇒ 按坑 22(d) 不编辑运行中的 .sh，就地更正留痕（增补 12 §4）。 ⑤ **新提案 · 档 7H（新假设 ⇒ 预注册先落盘，可被否）**：动机 = **F4**（bs32/5500 步 = **3.791 ep**/lr1e-4/**原数据集无纠正帧**/seed2000）= **60/80 = 75.0%**，而标准配方在**同一个 seed** 上只有 41.2% ⇒ 「等 epoch 下换 batch/lr」可能是关闭 seed 稳健性缺口的**第二条**路线；但 F4 是 **n=1 且正好落在标准配方最差的 seed 上** ⇒ 必须新 seed 前瞻（继承 7G 纪律）。设计：3 个从未用过的训练 seed **11000/12000/13000** × 配方**逐字照抄 F4**（`code/run_pi05_s7b.sh` 自己现算并对账 STEPS/SAVE_FREQ/LOG_FREQ），**H1 主门 = min ≥ 40/80**（与档 3r/7C/7G/8D 同一条）、H2 正向掉幅三个都 ≤15 pp、H3/H4（极差、与 F4 的 11 格配对符号检验）**只读方向不是门**；**阈值在 D4 落盘之前写死**（21:04 < D4）⇒ 不可能被 D4 污染，且预注册 §6 明写「不因为 D4 的结果调整本档任何阈值」。落地件：`code/mg_verdict_s7h.py`（自测 **43/43**；出身核对不过 ⇒ rc=3 不采信）、`code/chain_s7h.sh`（189 行，21:12 发车，**等 `runs/s8d.done`**、上限 48 h、上游 `s8d.FAILED` ⇒ 写 `s7h.SKIPPED` 停下等人）；预算 ~**26 h** ⇒ ETA ~**10-07 晚间**。 ⑥ 看门狗清单 **+3**（`s8d`/`s8mechd`/`s7h`）并两次重启（20:54 PID=SID=**338744**、21:14 PID=SID=**346574**），备份 `.bak_pre_s8d`/`.bak_pre_s7h`；心跳已显示三条 `RUN`。 ⑦ 新增坑 **75**（清理循环里的 `pgrep -f` 会匹配到自己的命令行 ⇒ 自杀；房规：模式里用字符类 `chain_s8[d]\.sh`）、**76**（参数化共用链脚本必须做「默认值逐字复现归档产物」的冒烟对账；`bash -n` 抓不到 `printf` 续行被拆断这种语义错）。 ⑧ 备份：`runs/S8_PREREG.md.bak_pre_addendum12`、`code/chain_s8mech.sh.bak_pre_s8d`、`README.md.bak_pre_pit75`。|
| 49 | **使命判定书落盘 + 档 9B「设计阶段关闭」（零 GPU 判死）+ 档 9C 配方收口发车**（10-07 15:39~16:1x） | ✅ 五件：① **`runs/MISSION_VERDICT.md`**（原始使命的交付物，187 行）：档 0→9 逐档证据链（每行带出处）、部署配方（`mix60f120r_c1` 219集/53638帧 · bs8/22000步=3.28ep · lr1e-4 · `last`=022000 · K=10=41.9 ms/步）、机理账、**8 条已知极限**、审计轨迹、复现命令；结论 = **π₀.₅ 能做单臂抓取**，使命门（反向 TEST 放宽 min ≥ 40/80）**已关上 = min 64/80 = 80.0%**（`S8_MISSION_GATE=CLOSED`，三 seed 65/65/64，极差 1.25 pp）。② **档 9B 关闭**：v1(`ceilhold`) 与 v2(`ceilpred`) 在 **Z0b 前置闸**上都是 **0/12**（加限位后 13.50~14.83 cm vs 门线 cap+1.0=13.15），val 确认台 3/12 ⇒ 增补 3 ④ 的 **2 次重设计预算用尽** ⇒ 合法终态 `runs/s9b.SKIPPED`（**不是** FAILED：Z0 保真门**未测**=UNKNOWN、Z1–Z6=NOT_RUN，坑 40③）；根因 = 侧躺局的升程是**接触/动量弹射**（`8D_s4000` seed7002 ep2：t=159 策略 dz=+0.70 ⇒ 末端**单步 +3.65 cm**；t=171–175 策略 dz ≤−0.02、限位器已**饱和** −0.81~−0.91，末端**4 步仍涨 +3.45 cm**）⇒ 只改 `dz` 的部署侧外壳物理上按不住；**本档因此只花 ~0 h GPU**（可行性台是纯 CPU 重放）。③ **档 9C 发车**：`code/chain_s9c.sh`（215 行，15:45 `setsid`，**PID=SID=PGID=13236**，坑 37 核过）= 2×2 因子表**唯一缺格**（bs32/5500 步=3.2813 ep × 纠正数据，seed **21000/22000/23000**，采样预算 176000 与档 8 **逐位相同**），闸 0–6 已**干跑验证全过**（临时把上游标记换成 `s8d.done`、终态标记指向 `/tmp` ⇒ `runs/` 零污染），门 = **同一条使命门**（C1 min ≥ 40/80）+ C2 正向掉幅 ≤15 pp，C3/C4 只读方向；**C4 配对臂事前写死 = 8D seed4000**（同一张 epoch 网格：每格 `500/1676.1875 = 2000/6704.75 = 0.2983 ep`，增补 4）⇒ ETA ~**10-08 23:00**。④ **工具与钉子**：`mg_verdict_s9c` **30/30**（修好 C4 自测夹具——`bad` 网格与本档网格数学上**本来就相同**，是**夹具错不是实现错**；另加一条真实网格一致性钉子）、`mg_verdict_s9b` **45/45**（报告主体补齐：`off/hold/hold_lo` 标签、Z0b 段 + `S9B_STAGE/Z0b/Z0b_val` 机器行、Z4 补**受控量** `filter.max_rise_cm` p95、决策树加「Z0b ❌ ⇒ 设计阶段关闭」分支、`S9B_Z0=UNKNOWN` 而非 FAIL、TRUST 语义澄清）、`mg_eval_zlim` 54/54、`mg_zlim_replay` 24/24、`mg_s9b_gain` 17/17、`mg_verdict_s8` 42/42。⑤ **文档回填**：`runs/S9_PREREG.md` **增补 4**（15:39 落盘，早于任何 9C 读数，声明不改任何门）、坑 **77/78/79/80/81** 一并补进本文件（77/78 之前只在代码注释里被引用、正文缺失）、`STAGE_PLAN.md` 档 8 翻 ✅ + 档 9 立项/关闭段。⑥ 7H seed13000 在训（16:0x ckpt 4500+/5500）⇒ `runs/s7h.done` ETA ≈ **18:40**；**interim 2/3 seed = 69/80 = 86.2%、67/80 = 83.8%**（正向各 13/20 = 65.0%，H2 掉幅 −0.7 pp）⇒ 已写进 MISSION_VERDICT §八并**标注「未关门、不许当最终值引用」**。 ⚠️ **本条 interim 已于 10-07 18:22:06 作废**（7H 三 seed 齐、全绿关门：min **67/80 = 83.8%**）⇒ 最终值一律看**里程碑 51** 与 `runs/S7H_VERDICT.md`。⚠️ 9C **不进看门狗清单**（坑 78：`chain_watchdog.sh` 在飞不许编辑）⇒ 靠自身 `s9c.{done,FAILED,SKIPPED}` + 人工巡检；看门狗窗口覆盖到 ~10-08 21:3x。⚠️ 自伤未遂一枚：`pkill -f chain_s9c_dry.sh` 把执行它的 shell 自己也匹配上（exit 143）⇒ 坑 22(a)/75 的第四次复现，改用字符类 `chain_s9c_[d]ry` 才清干净。备份：`README.md.bak_pre_ms49`、`runs/S9_PREREG.md.bak_pre_addendum4`、`code/mg_verdict_s9b.py.bak_pre_reportfix`、`code/mg_verdict_s9c.py.bak_pre_c4fix`。|
| 50 | **B 类失败的一手机理复核：夹爪通道「有检测量、无成因杠杆」⇒ 档 9D 不立项**（10-07 16:35~17:5x，**零 GPU**、纯读盘，与在飞的 7H/9C 不抢卡） | ✅ 六件：① **新工具 `code/mg_bclass_grip.py`**（自测 **40/40**：q1–q3 / c1–c16 / g1–g5 / s1–s3 / r1–r3 / k1–k3 / p1–p4 / w1–w3）→ `runs/_diag/s9_tax/grip_mech_400.{md,json}`（TEST 窗 5 臂×4×20=400 局）+ `grip_mech_val.{md,json}`（val 窗 100 局，低功效只判方向）+ **`grip_labels_{400,val}.json`**（逐局归因标签表，TEST 400 行／val 100 行，按 `(arm,dir,ep,seed)` 可 join 回任何既有产物）；三条不变量（relax⊇strict / TIP 口径 / 分组一致性）违例全 **0**。② **夹爪符号实测**（坑 82）：专家 3729 个开合步里 `sign(act)==sign(Δwidth)` 仅 **3.27%** ⇒ **+1=闭合**；`mg_env.py:11/305` 的注释与此**相反**（冻结文件不改、登记为坑）。据此**推翻**初稿的因果话术：B 的 `act_mean` 中位 **+0.7785 低于** OK **+0.8875**，而专家夹住段 act 中位 **+1.000**／均值 **+0.858** ⇒ 指令是**饱和 bang-bang**、专家一路 +1 而开口仍稳在 ~0.049 m ⇒ **「闭合指令过强挤飞罐」不成立，「给闭合指令限位」没有作用对象**。③ **B 不是一个桶是两个**（坑 83）：用 `mg_env.GRIP_HOLD_WIDTH=0.012`（**专家假阳 0/120**）切 ⇒ B 69 局里 **31 局（44.9%）空合**（`w_min` 中位 **0.00316 m** ≈ 空合到底）却 can 抬升中位 12.9 cm ⇒ 罐是**接触弹射**顶飞的、从没在指间；另 **38 局（55.1%）真夹住**（`w_min` 0.04335）却离目标 58.3 cm ⇒ 真放置失败只占全体 **9.5%**。**9A 的 `max_lift_cm≥8cm` 代理在 B 上有 42.6% 假阳** ⇒ `runs/_diag/s9_tax/SUMMARY.md` 已加 **§⓪ 更正**（就地留痕、逐臂计数不追改、不动任何门，坑 40）。④ **删失被消掉后结论翻转**（坑 85）：搬运步数中位 专家 174／OK 189／**B 107**；换成等长同相位前缀窗（前 `K_MATCH=40` 步）后 `m_act_mean` **p=0.4965**、`m_spd_p95` **p=0.9721**、`m_acc_p95` **p=0.8652** ⇒ **三项全不显著**，整窗上那些「显著」全是窗口长度差与后果；绝对步数 `loss_after_steps` 给出真死因：**B 的中位丢罐 = 夹住后第 1 步**（≤10 步占 91%；专家假阳局第 164 步、OK 第 78 步）⇒ 不是「搬运途中掉了」而是「闭合那一刻就没夹上」。⑤ **修掉一个恒空表 bug**（坑 84）：`delivered_tipped` 蕴含放宽成功，初稿的 `cls` 表达式把侧躺局吞进 OK ⇒ TIP 组**结构性恒为 0**、§三 整张 `—` 且不报错；抽成纯函数 `classify` + 加 `invariant_cls` 纳入非零退出码后，TEST 窗 = **OK 261 / TIP 69 / B 69 / A 1**，与 9A 独立工具公布的 **261/69/70 逐位吻合**（两条独立实现互验）。侧躺的夹爪侧对照也活了：**TIP 空合率 2.9% < OK 5.4%** ⇒ 侧躺不是抓取阶段的问题，**9B「放下冲击」结论得到独立支持**。⑥ **统计口径**：`W_LOSS`（专家 p05）自带**逐集假阳地板 16.7%**（p01→2.5%、p10→66.7%）⇒ 报告已把地板印出来、按「减地板」读（B 84.1%/OK 40.6% ⇒ +67.4/+23.9 pp）；双峰量改用**发生率 + 比例置换检验** `rate_perm_test`（test：B 44.9% vs OK 5.4%，**+39.6 pp，p=0.0001**；val：B 27.6% vs OK 11.3%，+16.3 pp，**p=0.0687**，n_B=29 功效不足 ⇒ **只认方向**，坑 33）。**结论/决策**：夹爪通道交出的是**零成本逐局归因标签**（`held = w_min ≥ GRIP_HOLD_WIDTH`，只读已落盘 npz、零重放），**交不出成因侧可调量** ⇒ **档 9D 不立项**（候选①无作用对象；候选②「教材侧补轻夹慢运」需重采+重训 ≥20 h，而真放置失败仅 9.5%、使命门已有 30 pp 余量）⇒ **主线不动，仍是档 9C**。⚠️ 本档**全程回溯、不进任何门、不产出成功率结论**；要动判据/干预必须先写预注册（坑 40）。⚠️ 另发现 `carry_400.json`／`slip_400.json` 是 ad-hoc 残留（后者 83 字节截断、已隔离为 `*.CORRUPT_TRUNCATED_83B`）⇒ **不得作机理证据**，本次全部从一手 npz 重算。备份：`README.md.bak_pre_pit82`、`runs/_diag/s9_tax/SUMMARY.md.bak_pre_gripmech`、`runs/MISSION_VERDICT.md.bak_pre_gripmech`、`STAGE_PLAN.md.bak_pre_gripmech`、`code/mg_bclass_grip.py.bak_pre_selftestfix`。新增坑 **82/83/84/85**。|
| 51 | **档 7H 全绿关门（第二条独立路线成立）+ 9C 接卡开训 + 档 10「标准 chunk 执行 K=50」预注册并排队发车**（10-07 17:43~18:3x） | ✅ 六件：① **档 7H 关门**（`runs/s7h.done` **18:22:06**、判定 `runs/S7H_VERDICT.md`、`S7H_TRUST=YES`）：便宜配方 bs**32**/**5500** 步 = 3.791 ep / lr1e-4 × **无纠正**数据集 `mix60f120r`，3 个**新**训练 seed 的 TEST 反向放宽 = seed11000 **69/80 = 86.2%**、seed12000 **67/80 = 83.8%**、seed13000 **73/80 = 91.2%** ⇒ **H1 = min 67/80 = 83.8% ✅**（门 40/80，余量 **33.8 pp**；min-of-3 是**向下偏**统计量 ⇒ 门是保守的）；**H2 ✅**（正向未见 13/13/15，掉幅 −0.67/−0.67/−10.67 pp，三个都 ≤ 15 pp ⇒ **没拆东墙**）；**H3 只读**：极差 **7.5 pp**（sd 3.8）vs 标准配方 **38.8 pp**，但 n=3、2 自由度 ⇒ **无功效、永不作门**；**H4 只读**：三个新 seed 的 11 格 val 曲线与 F4 逐格配对符号检验 = 3胜5负3平/5胜3负3平/6胜4负1平，双侧 **p=0.7266/0.7266/0.7539** ⇒ 轨迹形态不可区分。**决策（预注册 §3.4 决策树照抄）**：H1✅∧H2✅ ⇒ 「等 epoch 下换 batch/lr」这条杠杆**前瞻成立** ⇒ seed 稳健性缺口有**第二条独立**关闭路线（第一条 = 档 8 纠正数据 D4）。**诚实标注（预注册 §4 写死）**：仍**不能说**「便宜配方比 bs8/22000 更稳健」——标准配方的 3 seed（1000/2000/3000）与 7H 的 3 seed（11000/12000/13000）**不是同一批** ⇒ 不构成配对（坑 57）；且与档 8 **跨数据集** ⇒ 只比形状不比高低（坑 33）。② **9C 接卡开训**：7H 让卡后 **37 s**（**18:22:43**）过闸 0–6（GPU free 81153 MiB、配对臂 11 格、合并集 219 集/53638 帧），seed21000 起跑 ⇒ ETA ~**10-08 23:00**；哨兵心跳正常。③ **档 10 立项 + 预注册先落盘 + 排队发车**：问题 = 阶梯第 4 步「**标准 chunk 执行 K=50 = chunk_size**」**从来没在关门配方上测过**（档 4/4r/4x 量 K=50 用的全是档 8 之前的弱配方）⇒ 唯一问题「**D4 的 65/65/64 换成 K=50 还过不过同一条门**」；设计 = 三臂 `s8c_seed2000`/`s8d_seed4000`/`s8d_seed5000` 的 `checkpoints/022000`（**数字格**），**唯一变量 K（10→50）**，3 臂×4×20 = **240 反向** + 3×20 正向，K=10 参照**从盘上并入不重跑**并与 `S8_VERDICT.md:16` 逐臂对账（对不上 ⇒ 🚫 rc=3 不采信）；判据 **E1** min ≥ **40/80**（同一条使命门）／**E2** 逐臂 Δ 最坏档（≤−20 CRASH、−20~−10 GREY、>−10 NONINF，沿用档 4r 事前规则）／**E3** 侧躺率 Fisher **只读不设门**／**E4** 墙钟 **ms/步 ≤ 50**／**E5** 正向护栏只读；**18:04 `setsid` 发车排队**（PID=SID=PGID=**74668**、哨兵 **74704**；等 `runs/s9c.*` + 进程消失，上限 48 h）⇒ 预算 ≈**1.1 h GPU**、ETA ~**10-09 00:15**。⚠️ **绝不与 9C 并发**：E4 是**墙钟门**，抢卡会把 ms/step 抬高几倍 ⇒ 判的是排班不是模型（每格评测前还要 free ≥ 44000 MiB）。④ **工具与钉子**：新增 `code/mg_verdict_s10.py`（**自测 77/77**：常数与目录命名 13 / `band_e2` 边界 9（−20.0 归 CRASH、−10.0 归 GREY）/ `gate_e1`·`gate_e2`·`delta_pp` 14 / `e3_pooled`·`ms_per_step`·`xcheck`·`fmt_kn` 14 / **端到端 5 场景 27**，把退出码 **0/2/3** 三条路各走一遍；夹具只写 tempdir + 只 patch `mg_verdict_s2f.RUNS` ⇒ 不碰真 `runs/`、不断言盘上进度，坑 77）、`code/chain_s10.sh`、`code/chain_s10_sentinel.sh`（10 min 心跳、有界 60 h、MISSING ⇒ `logs/ALERTS.log`；**不进看门狗清单**，坑 78）；复用而非重写（坑 54）：`collect/ci/pct/load` ← `mg_verdict_s2f`、`prov/rev_dirs/fwd_dirs` ← `mg_verdict_s7f`、`fisher_two_sided` ← `mg_verdict_s2`；`mg_verdict_s7h` 自测 **43/43** 复核（7H 收尾那一步不会卡）；`ms_per_step` 加了 `loader=` 注入点才测得到。⑤ **干跑验闸**（预注册 §7.6）：`DRY_RUN=1` + 上游标记换成已存在的 + 终态标记指 `/tmp` ⇒ 闸 0–6 全过、15 条命令的 K/seed/npz/ckpt 尾串/目录名逐项核对（目录名与判定工具要读的 15 个**集合完全相同**、mode↔npz 配对错 **0**、正向 npz 与盘上 8C/8D 的 K=10 参照**同名同 seed**）、`runs/` **零污染**；闸 0b 还钉了「任何 `s10_*` 产物必须**晚于**预注册落盘时间」（防「看完数才写门」）。⑥ **文档回填 + 新坑 86/87**：`runs/MISSION_VERDICT.md` §一 加「第二条独立路线」、§二 便宜配方 interim→**final**、§三 补 **7H** 行、§五 极限 7 的数字更正、§八 行 1/2/3 翻 ✅ + interim 表→**final 表** + 新增行 9（档 10）；`STAGE_PLAN.md` 新增**档 10** 章节 + 9C 节里「7H min 67/80（2/3 seed）」改 3/3；坑 **86**（打印路径里 `n=0` 有两种意思，`{k}/{n or EPS}` 兜底会把「缺读」印成「真 0/20」，而 E5 的结论恰恰依赖这个区分）、坑 **87**（判定工具 f-string 同引号嵌套会 `SyntaxError`，用 `chr()` 拼 key「绕过」= 把语法错换成**只有跑到那一行才暴露**的静默错，本轮同一个错犯了两次）。备份：`README.md.bak_pre_pit86`、`README.md.bak_pre_ms51`、`runs/MISSION_VERDICT.md.bak_pre_s7hfinal`、`STAGE_PLAN.md.bak_pre_s10`、`code/mg_verdict_s10.py.bak_pre_syntaxfix`。|
| 52 | **档 11「语言泛化」判定工具补齐并全绿 + 20 读链与哨兵发车排队（零训练；真机前置里本轮唯一可做的一级）**（10-07 20:15~20:45） | 🔄 **三链在飞**：9C seed21000 训练中（哨兵 tick=28、`sweep_cells=0/33`、`test_evals=0/15`）→ 档 10 排队（PID=SID=PGID=**74668**）→ **档 11 排队**（20:39 `setsid`，**PID=SID=PGID=123056**；哨兵 **123400**，tick=1 `s11=RUN reads=0/20`）；ETA 依预注册 §6 ≈ 9C ~10-08 23:00 → 档 10 ~10-09 00:15 → **档 11 ~10-09 02:00**。✅ 五件：① **`code/mg_verdict_s11.py` 补齐（自测 138/138）**：纯函数边界（`gate_l1` 30/60 压线过、29/60 不过、缺读 UNKNOWN 且**点名**；`gate_l1b` 10/20 压线；`band_l2` ±15.0 归带内；`paired_l2` 的 b/c/Δ/npair 与缺臂单列；`gate_l3` 20.0%→COND_OK、25%→UNCERTAIN、50.0%→FAKE_COND；`decide` 九支决策树逐支）+ **端到端 12 场景**把退出码 **0/2/3** 三条路都走一遍（A 全过 / B 只 F2 掉门 / C 假条件化矛盾 / D 产物全缺 / E sidecar 自伤 `orig==patched` / F 老产物缺放宽字段 / G 参照对不上（反向 65、正向 12 各一例）/ H `summary.task` 不是预注册那句 / I 不变量被破坏 / J 无 sidecar / K sidecar 坏 JSON / L 出身字段 9 连击）；夹具只写 tempdir，且**同时** patch `mg_verdict_s2f.RUNS` 与本模块 `RUNS`（`load_sidecar`/缺产物检查用后者，只 patch 一个会去读真盘）。② **修掉一枚恒真绿灯（新坑 88）**：`broken`/`nofield` 两行原本拿 `collect([], "", "")` 当兜底 ⇒ 键本来就存在、永远返回空 ⇒「不变量违例 **0** 条 ✅」「缺字段 **0** 条 ✅」两枚灯**没接电**，而它们正是 `trust` 的输入（违例>0 ⇒ 退出码 3）；改成 `.get(arm, {}).get("broken", [])`，并**各补一个能把它变红的场景**（I 造 `relaxed 17 < strict 20`、F 造缺 `n_success_relaxed`）。③ **真盘空跑（输出到 `/tmp`、不写 `runs/`）**：`rc=3`、出身问题 20 条全是「产物不在」、`S11_L1=UNKNOWN`、机器行全 `NA`、全文无假 `0/60`；**参照对账 0 条不符** ⇒ 盘上 K=10 原话读数确实池化成反向 **65/65/64**、正向 **16/12/16**（rep1 池化反向 54/60、正向 44/60，L2 的配对分母对得上）；`runs/` 条目数 **315** 未变、`s11_*` 目录 **0** 个。④ **`code/chain_s11.sh`（175 行）+ `code/chain_s11_sentinel.sh`（48 h 有界、10 min 心跳、MISSING ⇒ `logs/ALERTS.log`）**：清单唯一真源 = `mg_eval_lang.py --print-plan` 的 TSV（20 读 × 11 列；闸 2 把**列数**也钉死，防 `read` 错位 = 拿 A 句的指令跑 B 臂的权重）；闸 0–8 **干跑全过**（预注册时间序 / `S8_D4=PASS` 出处 / 三臂 `022000` 数字格 / 15 读原话参照齐 / 双 npz / `mg_eval_lang` 47-47 与 `mg_verdict_s11` 138-138 两个自测绿 / GPU free 硬闸 44000 MiB），`runs/` 零污染；每读完**当场**要 `lang_sidecar.json` 与日志里的 `[lang] patch` 行，缺一条就 `die`（本档最大的静默失败 = patch 没生效 ⇒ 跑的还是原话 ⇒ L1 假过、L3 假阴；不能等烧完 20 读才发现）；发车循环用 `done < <(...)` 而不是管道（新坑 90①：管道里的循环体在子壳，`die` 只退子壳、链会照写 `done`）。⑤ **文档回填 + 新坑 88/89/90**：`STAGE_PLAN.md` 新增**档 11** 章节（含阶梯 7 = `NOT_OPENED_THIS_ROUND`、阶梯 8 = 无硬件的收口状态）；坑 **88**（空收集器兜底 ⇒ 检查空转，比崩溃更难发现）、坑 **89**（自测断言用裸子串会撞上阈值文案 `30/60` ⇒ 假警报把人引去改实现）、坑 **90**（管道 `while` 子壳吞 `die`；`cd A && cmd > rel.log &` 的重定向在 `cd` 之前求值 ⇒ 哨兵起不来却看着像发成功了）。⚠️ 本档**不进任何既有门**：使命门（40/80）、D1–D4、H1–H4、C1–C4、E1–E5 一字未动；L1 是**筛查**（n=60/句 ⇒ 1σ ≈ 6.5 pp），「过门」≠「与原话等价」（那需 ≥400 局/句）。备份：`README.md.bak_pre_pit88`、`README.md.bak_pre_ms52`、`STAGE_PLAN.md.bak_pre_s11`、`code/mg_verdict_s11.py.bak_pre_selftest`。|

## 结果（第 3 轮 · 档 2 / 档 3 / 档 4 关门，2026-10-01 21:00）

**结论：π₀.₅ 的单臂抓取「一个方向行、反方向不行」，而且我们已经把不行的原因排除到只剩两个候选。**

| 档 | 问题 | 结果 | 门 | 判定 |
| --- | --- | --- | --- | --- |
| 档 2 门1 | 正向（托盘→bin）未见初姿 | **63.7%**（51/80，四读 45/75/60/75%） | ≥50% | ✅ |
| 档 2 门2 | **反向**（bin→托盘）未见初姿 | **37.5%**（30/80，四读 30/35/55/30%） | ≥50% | ❌ |
| 档 2 门3 | 加了反向后正向退了多少 | 63.7% vs 档 1 的 70% ⇒ **−6.2 pp** | ≤15 pp | ✅ |
| 档 2 上界 | 脚本专家同批 seed | 正 **100%** / 反 **70%**（6 局失败全是 can 侧躺） | — | 反向只打到上界的 54% |
| 档 3 | 三个训练 seed（各 **60 局**） | **70.0% / 63.3% / 70.0%**，最差 63.3% | 最差 ≥50% | ✅ |
| 档 4 | K 曲线 | K=1 85% ≈ **K=10 80%** ≫ K=25 25% ≈ K=50 30% | — | ✅ K=10 是唯一「又准又实时」的点 |

**⇒ 档 2 判 ❌，档 3 / 档 4 判 ✅。** 「π₀.₅ 能做单臂抓取」这个最小闭环在**正向**上已经证明
（未见初姿 64~70%、三个 seed 都过门、K=10 可部署）；**反向**没证明，差 12.5 pp。

### 反向为什么不行：五条已排除的（每条都花掉了 GPU，别再重跑）

| # | 排除掉的可能 | 证据 |
| --- | --- | --- |
| 1 | 检查点选得不好 | 按 val 选到峰值 011000 重读 TEST：正向 57.5%、反向 **26.7%**（更低）。两规则合并反向 **29/100** ⇒ 这就是真实水平 |
| 2 | val 能选出点 | val rev 5/10=50% 的检查点 TEST 只有 26.7%，val 2/10=20% 的 `last` TEST 有 37.5% ⇒ **反序**（坑 27） |
| 3 | 记忆 / seed 泄漏 | 训练 seed vs 未见 seed（n=80）：反向 Fisher **p=0.50**、正向 **p=1.00** ⇒ 无记忆证据 |
| 4 | 成功判据太严 | 放宽到「can 曾进过 ±9 cm 方框就算成功」的**天花板 = 38%**，仍不过门 ⇒ 判据不是瓶颈 |
| 5 | 管路（action/state/normalizer/夹爪语义） | 同一模型同一套代码正向能到 64%；档 0/档 1 已逐条自证 |

### 反向失败的机理（100 局分类账 `runs/_diag/tax_rev_test.md`）

**A 没抓起 44% / B 抓起了没送到 39% / C 送到了没落定 17%** —— 三个相位都有，不是单一 bug。
最清晰的一条可改机理是 **C 类的「举太高」**：成功局 max_lift 均值 **11.7 cm**，
而「进过方框却没成」的 9 局**全部**是 15.4~21.8 cm（均值 18.4）、全部跑满 400 步超时。
举高 6~10 cm ⇒ 落下冲击 ⇒ can 侧躺 ⇒ 落定判据挂掉。**专家那 6 局失败也是同一条**
（位置对到 0.3~0.5 cm，但 `final_tilt≈90°`）⇒ 反向 70% 上界的缺口全是侧躺。
逐 seed：20 个 TEST seed 里只有 5 个从未成功，其中 4 个专家能成（真差距）、1 个专家也成不了
⇒ 主要矛盾仍是**执行抖动**，不是位姿覆盖不到（与档 1 的 8c 同一条）。

### 机理已定位：**两种不同的病**（21:50 · `runs/_diag/lift_profile.md`）

`code/mg_lift_profile.py`（**61 项自测**，纯 CPU、不占训练 GPU）把上面那条「举太高」的**推断**
做成了测量。高度一律以**抓取点**为基准，松手事件按「闭合段」切分、用段内**中位宽度**
判是否真夹住（坑 31）。

**先验尺再量人**：专家反向示范松手高度中位 **1.9 cm**、60 局全域 **[1.3,2.7]**；
策略**成功局**中位 **2.1 cm** ⇒ 阳性对照通过（差 +0.2 cm，容差 ±1.5），
这把尺子才允许拿去量失败局。

| 失败类 | 占失败 | 病灶 | 关键读数 |
| --- | --- | --- | --- |
| **A** 物体从没离地 | **44%** | **空合**：can 根本没进过手指 | **21/31 局一次都没夹住**；空合 **49** 次 vs 真夹持 17 次（空合率 **74%**）。专家 60 局**空合 0 次** |
| **B** 抓起没送到 | 39% | 松手太高 | 松手高度中位 **11.8 cm**，**22/28** 越过专家全域上界 2.7 cm |
| **C** 送到了没落定 | 17% | 松手太高 | 松手高度中位 3.1 cm，**4/7** 越过专家全域（最高 12.0）；rule-of-three 保守 p₀=3/60=0.05 下二项尾 **p=1.9e-04** |

* **A 与 B/C 是两种病，处方不同**（本轮最重要的修正）：
  * A = **接近段/合爪时机**：合爪瞬间横向偏差太大 —— 与档 1 已量过的坑 17 是同一条
    （can 半径 2.5 cm + 夹爪半开口 4.0 cm ⇒ 合爪时横向偏差必须 ≲1.5 cm）。
  * B/C = **下降段/松手时机**：峰值抬升 C 类中位 **17.7 cm** vs 专家 **11.5 cm**（举过头 +6.2 cm），
    同样的下压速率自然停不到 2 cm。
  * ⇒ 「修一处、三类同时下降」这个预测**作废**。A 占失败 44%、盘子最大，**该先修 A**。
* **normalizer 假设排掉**（本来是最省事的解释）：策略 dz 值域 `[-0.93,+0.84]` vs 示范
  `[-1.00,+0.86]`、std `0.247` vs `0.250`（比值 **0.99**）、松手前 20 步 mean dz 中位
  C 类 `-0.109` 比专家 `-0.084` **还更负** ⇒ 下压指令在、幅度没被压扁。
  问题在**时机**不在**幅度**；夹爪是 bang-bang（grip std≈0.95、值域顶到 ±1），
  开合是离散决策，早开一步就从高处掉。
* **一条被自己撤回的结论**（记下来别再犯）：本工具第二版报过「成功局 0/29 多段夹持、
  失败局 50/71，Fisher **p=1.1e-11** ⇒ A/B/C 同一病因」。那是**分段 bug 造出来的假信号**：
  把「合拢途中宽度瞬时经过 0.05、最终压到 0.001」的**空合**也算成一次夹持，
  每局失败凭空多出几段。改成按闭合段切分 + 中位宽度判据后，A 类只剩 **2/31** 真多段，
  Fisher **p=0.056 不显著** ⇒ 整条撤回（坑 31(d)）。
  ⚠️ 注意这个 bug **只**污染了「多段夹持」这一条；第四节的松手高度结论**不受影响**，
  因为它有阳性对照背书（成功局的宽度中位 0.0497 ≈ 专家 0.0499）。
* **对档 2c 的意义**：无论判 R1（干扰）还是 R2（任务本身难），
  「松手高度只有 ~2 cm、抓取从不空合」这两条信息**本来就在现有 60 条示范里**
  ⇒ 是策略没学准，不是数据里没有。所以**「先加数据到 120 条」不该排第一**；
  「复核判据口径」也**第二次**被关掉（专家就是在 1.9 cm 松手并被判成功的）。

### 只剩两个候选，档 2c 正在分辨（ETA ≈ 02:30）

* **H-A 干扰**：反向被正向挤掉了。旁证 = 同一模型里正向 val 到 14000 步还有 5~8/10，
  反向 val 从 11000 的 5/10 掉到 13000 的 **0/10**。处方 = 改数据配比/采样。
* **H-B 任务本身难**：反向要伸进**有墙的** bin2 象限抓（运动学极限）、专家平均用掉 **312 步**
  （正向 240，horizon 只有 400）、还要求 can 立着保持 10 步。处方 = 加反向数据 / 改示范 / 修 C 类举高。

档 2c = 同一份数据集只喂反向 60 集（`--dataset.episodes=[60..119]`，normalizer 逐比特不变、
等 epoch 7600 步），**唯一变量是批次里有没有正向帧**。判定规则 R1/R2/R3 + 护栏 G1/G2
**跑前预注册**在 `code/chain_s2c.sh`，执行在 `code/mg_verdict_s2c.py`（7 项自测，含「G1 产物没到 ⇒ 悬空而非作废」三态），
产物 `runs/S2C_VERDICT.md`。全文见 `STAGE_PLAN.md`「档 2c」。

### 本轮顺手修掉的四个工具缺陷（都会**安静地**给出错结论，比崩掉更危险）

1. `chain_watchdog.sh` 的清单写了 `step_14400_rev`，而扫描循环最后一格是 `step_14000`
   ⇒ 从 08:13 起每 10 min 误报一次「MISSING 档2双向检查点扫描」，把真报警淹掉。
2. `mg_verdict_s2.py` 用 `c > t + 0.10` 判「训练 seed 更好 ⇒ 有记忆」⇒ 把 Fisher p=0.46 的
   纯噪声报成需要查 seed 泄漏，白追一条不存在的线索。已换成 Fisher 精确检验（对着 scipy 校验过）。
3. `mg_probe_crossinstr.py` 用 `ckpt.parent/"train_config.json"` 找数据出处，而 lerobot 把它写在
   检查点目录**里面** ⇒ `conclusion_valid` 恒 False，一次跑对的探针被静默降级（坑 30）。
   已修 + 加 `--rescore`（不重跑、只重算标志位）。
4. 同一文件的 `follow_string = behavior_counts['no_transport']` 把「can 纹丝不动（策略停摆）」
   算成「照指令字符串走（不搬运）」⇒ 40 局里 39 局是冻结，差点被读成「π₀.₅ 真在做语言条件化」
   （坑 28）。已按 `max_lift_cm < 1.0` 拆出 `frozen` 类，`probe_conclusive=False`。

## 结果（第 2 轮 · 档 1 关门，2026-10-01 01:50）

**结论：π₀.₅ 不只会背一条示范——它在 20 个从未见过的初始位姿上把 can 抓起并落袋，成功率 ~70%。**
（01:50 关门时报的是单次读数 80%；02:51 的两次复跑都是 65%，所以头条数字下修为
**70%（三次读数 80/65/65，单读 1σ ≈ 10 pp）**。门是 ≥50%，三次读数**每次都过门**，关门结论不变。）

| 组 | 口径 | 结果 |
| --- | --- | --- |
| **主指标** | 未见 seed 2000..2019，20 局，K=10 | **16/20 = 80%**（门 ≥50%）；复跑 ×2 = 13/20、13/20 ⇒ **均值 70%** |
| 同一检查点 | 同上，K=50（标准 chunk 执行） | 6/20 = 30% |
| 零样本对照 | 档 0 模型（固定初态 85%）跑未见 seed | 0/20 = 0% |
| 训练 seed 对照 | 1000..1009，10 局，K=50 | 2/10 = 20%（**不比未见 seed 好** ⇒ 没有记忆） |
| 固定初态回归 | seed 0，20 局，K=50 | 9/20 = 45%（档 0 同口径 85%，权衡见 STAGE_PLAN） |

训练：`rand60`（60 条随机初姿示范，专家噪声 0.05）/ 7200 步 = 4.0 epoch / bs 8 / lr 1e-4 / A800 单卡 ≈3 h。
K=10 的 val 曲线（seed 3000..3009，10 局）：step2000 0/10 → 3000 5/10 → 4000 3/10 → 5000 6/10 → 6000 6/10。
证据：`runs/s1_gate_test_rand20_k10/`、`runs/s1_gate_test_rand20/`、`runs/s1_kcurve/`、
`runs/diag_r2last_zeroshot_k10/`；判定与机理全文见 `STAGE_PLAN.md` 档 1。

**为什么 K=10 与 K=50 差这么多（本轮最大的发现，README 坑 17）**：K=50 时策略在离 can 横向
**5.41 cm**、高 **+2.5 cm** 处就把夹爪合上 ⇒ 10/10 局空合（width→0.001）⇒ 随后 9/10 局把臂
竖直甩到 eef_z 1.28~1.74。脚本专家同一口径下的横向偏差是 **0.31 cm**；can 半径 2.5 cm、
夹爪半开口 4.0 cm ⇒ 合爪瞬间横向偏差必须 ≲1.5 cm。K=10（0.5 s 重规划一次）的成功局
min_dxy 全在 1.3 cm 内。⇒ **部署工作点取 K≈10；K=50 的读数如实并列上报，不隐藏。**

## 结果（第 1 轮，2026-09-30）

**结论：π₀.₅ 能从固定示范初态出发，把 can 抓起来并放进目标篮格——最小闭环已打通。**

**定版成绩（20 局，固定示范初态，K=50 标准 chunk 执行）**：

| 策略 | 数据 / 训练量 | pc_success | 备注 |
| --- | --- | --- | --- |
| **π₀.₅**（全参数微调） | fixed30n / 4000 步 = 4.7 epoch ≈ 100 min | **17/20 = 85%** | 平均第 240 步落袋（示范 229 步）；视频 `runs/final_pi05_r2_last_k50/ep0_succ.mp4` |
| π₀.₅（同 run 早检查点） | fixed30n / 2500 步 = 2.95 epoch | 10/20 = 50% | 曲线仍在爬升 |
| π₀.₅（第 1 轮，单轨迹数据） | fixed10 / 1500 步 = 2.6 epoch ≈ 25 min | 首条成功局 | 证明「能」的最早证据 |
| **ACT**（简单 BC，从零） | fixed10 / 20000 步 = 70 epoch | **10/10 = 100%** | K=100；K=1 则 0%（chunk 策略评测口径，见下） |

π₀.₅ 基座（`weights/pi05_base_lr044`，14.47 GB，未动一个字节）在 10 条固定初态示范上全参数微调，
batch 4 / lr 1e-4 / bf16 / gradient checkpointing，A800 单卡 **1.05 step/s**，
**1500 步（≈25 分钟、2.6 个 epoch）就出现了第一条闭环成功局**：

| 检查点 | 训练 loss | pc_success（K=50，5 局） | 备注 |
| --- | --- | --- | --- |
| 500 | 0.056 | 0/5 = 0% | can 没被碰到（离目标最近 60.7 cm） |
| 1000 | 0.037 | 0/5 = 0% | 已能抬起 can 7.1 cm 并搬运 22 cm |
| 1500 | 0.022 | **1/5 = 20%** | 首条成功局，第 316 步落袋 |
| 2000 | 0.015 | **1/5 = 20%** | 成功局第 **231** 步完成，示范是 229 步；can 离目标 0.8 cm |
| 2500 | 0.013 | **2/5 = 40%** | 本轮最好 |
| 3000 | 0.011 | 1/5 = 20% | loss 已收敛，成功率不再涨 |

原始证据：`runs/pi05_fixed10_r1/sweep/step_*/eval_summary.json`。

### 为什么成功率卡在 20~40%（不是链路 bug，是数据）

`data/fixed10` 的 10 条示范**逐比特相同**（跨 episode 动作标准差 = 0.000）——
固定初态 + 确定性专家 ⇒ 实际上只有**一条**训练样本。策略把它背下来了（loss 0.011），
但对自己的微小偏差没有任何恢复能力，典型的 BC 协变量漂移。
两个旁证：

* 把执行口径从 K=50 改成 K=10（重规划频率 ×5），成功率同样是 20%（`runs/eval_pi05_2000_k10`）
  ⇒ 残差不是 chunk 开环误差累积，是策略本身；
* 失败局的形态高度一致：can 被抬起 7~10 cm，但搬运到离目标 27~44 cm 处就偏掉。

→ 对策已落地：`data/fixed30n`（30 条，初态仍固定，专家动作加 σ=0.05 噪声，只加在 dx/dy/dz 上，
夹爪保持干净），跨 episode 动作标准差 dx 0.065 / dy 0.079 / dz 0.107，30/30 严格成功。
第 2 轮 `runs/pi05_fixed30n_r2`（batch 8 / 4000 步 / 1.4 s 每步）曲线：

| 检查点 | epoch | pc_success（K=50，8 局） |
| --- | --- | --- |
| 500 | 0.59 | 0/8 |
| 1000 | 1.18 | 2/8 = 25% |
| 1500 | 1.77 | 0/8 |
| 2000 | 2.36 | 0/8 |
| 2500 | 2.95 | **5/8 = 62.5%** |
| 3000 | 3.54 | 2/8 = 25% |
| 3500 | 4.13 | **6/8 = 75%** |
| 3500 复评 | 4.13 | 5/8 = 62.5% |

8 局的二项噪声约 ±15%，单点不可信（1500/2000 的 0/8 与 2500 的 5/8 可以是同一个真值）；
但**2500~3500 三个检查点合计 13/24 = 54%**（3500 两次评测合并 11/16 = 69%；
r1 同口径合计只有 5/20 = 25%），
说明**多样性 + 轮数**才是杠杆。第 3 轮 `runs/pi05_fixed30n_r3`（8000 步 = 9.4 epoch）接着往上推。

> 扫描脚本的一个坑：最后一个检查点用 `checkpoints/last` 定位，而 `last` 是指向最新编号目录的
> 软链——训练没跑完时它会指到上一个检查点，于是「step 4000」那行其实是 3500 的复评。
> 定版评测一律等训练进程退出后再取 `last`（`code/chain_r3.sh` 就是这么做的）。
两个排除项：

* flow-matching 去噪步数 10 → 20（r1@2500，10 局）= 2/10 = 20%，与 10 步的 4/15 无差异
  ⇒ 采样精度不是瓶颈（`runs/eval_pi05_2500_k50_inf20`）；
* r1@2500 那个「40%」本身就是 5 局的假象，10 局复测只有 20% ⇒ **评测局数太少会把噪声当信号**。

### 顺带确认「对齐没问题」的三条硬证据

1. **姿态三维**：策略输出 `droll/dpitch/dyaw` 恒为 0.000，与示范完全一致（示范也是恒 0）；
2. **夹爪语义**：策略 gripper 均值 +0.49 / 标准差 0.838，示范 +0.54 / 0.844——**符号与量级都对**
   （+1 = 闭合）；要是语义反了，这里会是负相关；
3. **动作量程收敛**：`dx` 标准差 0.08→0.16（示范 0.20）、`dy` 均值 −0.02→+0.11（示范 +0.17）、
   `dz` 标准差 0.17→0.32（示范 0.27），随训练逐项逼近示范分布。

### ACT 对照臂：100%，但**只在标准 chunk 执行口径下**

`runs/act_fixed10_r1`（从零训练 20000 步 = 70 个 epoch，loss 0.73@2K → 0.033@19K）：

| 执行口径 | pc_success | 现象 |
| --- | --- | --- |
| **K=100**（= chunk_size，标准 chunk 执行） | **10/10 = 100%** | 每局第 225~227 步落袋（示范 229 步），can 离目标中心 0.4~0.5 cm，抬升 9.5 cm |
| K=1（逐步重规划） | 0/10 = 0% | 只抬起 1.2~2.3 cm，can 最近也只到离目标 46 cm |

**这不是 bug，是 chunk 策略的评测口径问题**：ACT 每调一次 `predict_action_chunk` 就从 CVAE 先验重采一个
隐变量 `z`；K=1 意味着**每一步都换一条随机轨迹的第一帧**，动作序列自相矛盾，机械臂只会小幅抖动。
ACT 的正确用法是「执行整个 chunk」或「K=1 + temporal ensembling」（本轮按最小化原则不做 ensembling）。
π₀.₅ 的 flow-matching 对噪声采样没那么敏感，K=50 与 K=10 分别是 20% / 20%（`runs/eval_pi05_2000_k10`）。

> 训练口径必须和评测口径一致：`policy.n_action_steps` 训练时设多少，评测时就按多少执行。
> 视频证据：`runs/eval_act20000_k100/ep0_succ.mp4`、`ep1_succ.mp4`；K=1 的失败对照在 `runs/eval_act20000_k1/`。

ACT 在 step 2000 时（loss 0.73）也是 0/5 且几乎不动（抬升 0.3 cm），但 `droll/dpitch/dyaw` 同样恒 0、
gripper 符号同样正确 ⇒ 当时就能判定是欠拟合而非对齐错误。

## 命令

```bash
cd min_grasp_pi05
source code/env.sh

# 契约探针（不训练不联网，13 s）
$MG_PY code/mg_probe.py --all --episodes 3

# 采示范（阶段 1 固定初姿；阶段 2 加 --seed-mode random）
$MG_PY code/mg_collect.py --episodes 10 --name fixed10 --video

# 重放对齐验证
$MG_PY code/mg_probe.py --replay data/fixed10_raw.npz

# 训练：ACT（从零）/ π₀.₅（微调基座）
$MG_PY code/mg_train.py --policy act  --dataset fixed10 --steps 20000 --batch-size 8 --save-freq 2000
$MG_PY code/mg_train.py --policy pi05 --dataset fixed10 --steps 4000  --batch-size 2 --save-freq 500

# 闭环评测（K=1 全闭环；K=chunk_size 标准 chunk 执行，两者都是同步的）
$MG_PY code/mg_eval.py --ckpt runs/act_fixed10_r1/checkpoints/last/pretrained_model \
    --episodes 10 --video --demo-npz data/fixed10_raw.npz --n-action-steps 1

# π₀.₅ 两轮微调（r1 = 10 条同轨迹；r2 = 30 条带专家噪声）
bash code/run_pi05_r1.sh
DATASET=fixed30n STEPS=4000 BS=8 SAVE_FREQ=500 bash code/run_pi05_r2.sh

# 检查点扫描：每出一个检查点就评一次，把过拟合曲线画出来（不用等训练跑完才开奖）
RUN=runs/pi05_fixed30n_r2 EPISODES=8 K=50 STEPS_TOTAL=4000 SAVE_FREQ=500 \
    DEMO_NPZ=data/fixed30n_raw.npz bash code/mg_sweep.sh runs/pi05_fixed30n_r2

# 采集带专家噪声的示范（初态仍固定；只保留严格成功局）
$MG_PY code/mg_collect.py --episodes 30 --name fixed30n --expert-noise 0.05 --overwrite
```

## 已经踩到的坑（都已在代码里钉死，别再踩）

1. **物体摆放不走 `env.rng`**：robosuite 1.5.2 的每个 placement sampler 在构造时自己
   `np.random.default_rng()`（无 seed → 取 OS 熵）。只设 `env.rng` 的话机械臂初姿可复现、
   物体位置每次都变（实测同 seed 两次 reset，can 差 4 cm）→ `_seed_randomness()` 三个源都钉。
2. **动作增益别按 `output_max` 推断**：`output_max=0.05` 但 `ramp_ratio=0.2` + 阻抗控制，
   饱和动作一个控制步只走 11 mm。凭 5 cm 设计专家/归一化会差 4~5 倍。
3. **成功判定会假阳性**：can 在搬运途中滑脱、自由落体穿过篮子上方的 z 窗口
   （`bin_z < z < bin_z+0.1`）就被 `_check_success()` 判成功（实测第 145 步中招）。
   → 加「物理落定 + 连续保持」，且两个口径都进指标，不隐藏。
4. **夹爪语义与老文档相反**：1.5.2 的 `SimpleGripController` 是 `+1` 闭合。照抄文档注释会把
   整套数据的夹爪反过来（BC 学出来就是「碰到物体就松手」）。
5. **`LeRobotDataset` 必须 `finalize()`**：episode 元数据有 buffer（默认 10 条才落盘），
   不调用就没有 `meta/episodes/*.parquet`，数据集读不回来（还会掉进联网兜底路径）。
6. **torchcodec 在这台机器上是坏的**（`undefined symbol`，共享 venv 同样坏）→ 数据集一律
   `use_videos=False`（PNG），不用视频编码。
7. **`pip install robosuite` 会把 numpy 降级到 1.26.4**（依赖解析所致），会破坏 torch/lerobot 的 ABI
   → 用 `--no-deps` 装 robosuite，缺的依赖从已装好的 venv 拷贝（numba/llvmlite/mink/qpsolvers/daqp/h5py）。
8. **HF 直连与 xet CDN 被墙**：`lerobot/pi05_base` 的 14.5 GB blob 走 hf-mirror 只有 58 KB/s；
   paligemma tokenizer 在 HF 上是 gated（403）。→ 基座与 tokenizer 从本机
   `.codex-persist/hf-cache/modelscope` 硬链接进 `weights/`，tokenizer 再按 HF 缓存布局摆好
   （`refs/main` + `snapshots/<sha>/`），全程 `HF_HUB_OFFLINE=1`。
9. **`PreTrainedPolicy` 是抽象类**，`PreTrainedPolicy.from_pretrained(ckpt)` 直接
   `TypeError: Can't instantiate abstract class`。必须先
   `PreTrainedConfig.from_pretrained(ckpt)` 拿到 `type`，再 `get_policy_class(type)`。
10. **`n_action_steps` 挂在 `policy.config` 上**，不是 policy 实例上。ACT/PI05 的 `select_action()`
    读 `self.config.n_action_steps`，`reset()` 用它建动作队列；改错地方 = 改了个没人看的属性，
    评测口径静默变成默认值。另外它不能超过 `chunk_size`（`PI05Config.__post_init__` 会报错）。
11. **`make_pre_post_processors(...)` 只认 TypedDict 里那几个 kwargs**：传 `device=` / `use_amp=`
    会被**静默丢弃**（它内部只 `kwargs.get(...)`）。设备必须通过
    `preprocessor_overrides={"device_processor": {"device": "cuda"}}` 打进去，
    否则 batch 落在检查点 JSON 里保存的设备上（π₀.₅ 基座那份写的是 `cpu`）。
12. **π₀.₅ 加载时的 `Missing key(s): ...paligemma.model.language_model.embed_tokens.weight` 是良性的**，
    别去"修"它。`model.safetensors` 的 `__metadata__` 明写了
    `{'...language_model.embed_tokens.weight': '...paligemma.lm_head.weight'}`——
    两者是同一个张量（HF `_tied_weights_keys = ["lm_head.weight"]`），文件里只存一份，
    所以 `load_state_dict` 报缺键但权重是对的。**用 `__metadata__` 自证，不要靠猜。**
13. **「固定初态 + 确定性专家」= 只有一条训练样本**：`data/fixed10` 的 10 条示范逐比特相同
    （跨 episode 动作 std = 0.000）。BC 能把它背到 loss 0.011，但闭环只有 20~40%。
    要过拟合曲线往上走，必须给专家加噪声（`mg_collect.py --expert-noise`）制造轨迹多样性，
    而不是加训练步数。这是本轮最贵的一课。
14. **chunk 策略不能用 K=1 评测**：见上「ACT 对照臂」。K=1 逐步重规划会让 ACT 每步重采 CVAE 隐变量，
    100% → 0%。别把这个当成「policy 学坏了」去查归一化/夹爪语义，会白忙一整晚。
    先用 K=chunk_size 确认策略本身学到了，再谈闭环重规划频率。
    * **⚠️ 适用边界：本条只对 ACT 成立，对 π₀.₅ 恰好相反（2026-10-01 02:36 实测，标题里的
      「chunk 策略」是过度概括，别再照抄）**。同一个档 1 检查点、同一批**未见** seed 2000..2019、
      各 20 局，只改 K：**K=1 → 17/20 = 85%**（全曲线最高），K=10 → 80%，K=25 → 25%，K=50 → 30%。
      机理差别在解码器：ACT 每步重采 **CVAE 隐变量**，K=1 等于每步换一个人格，动作序列不连贯；
      π₀.₅ 的 flow-matching 去噪是**条件在同一个观测+指令**上的，逐步重规划反而拿到最多纠偏机会。
      ⇒ 判「K=1 崩了是不是链路 bug」之前，**先确认策略家族**。ACT 崩、π₀.₅ 不崩，两者都是正常的。
      ⇒ 但**别因此就把部署工作点改成 K=1**：K=1 每次控制步都要一次 3.6 B 模型推理，
      实测摊到每控制步 ≈323 ms，而 20 fps 的预算是 50 ms ⇒ **超预算 6.5 倍，跑不了实时**。
      K=10 摊薄到 32 ms/控制步（预算的 0.65 倍）且成功率 80% ⇒ **K=10 才是唯一「又准又实时」的工作点**。
      完整推导与告警见 STAGE_PLAN 档 4。
15. **epoch 数决定闭环成功率，训练 loss 不决定**：ACT 70 epoch → 100%；π₀.₅ r1 5.2 epoch → 20~40%。
    r1 的 loss 已经从 0.157 降到 0.011（几乎背下来了），成功率却纹丝不动——
    因为 10 条示范是同一条轨迹，loss 低只代表「记住了」，不代表「抗自己的误差」。
16. **重放对齐验证必须回到该局自己的 seed**：`mg_probe.py --replay` 原先写死
    `reset(seed=FIXED_SEED)`，档 1 的随机初姿示范（rand60）拿 seed=1000 的动作从 seed=0 重放，
    必然 0/2 假 FAIL。已改为读 npz 的 `seeds` 字段逐局 reset（无该字段才退回固定 seed）。
    随机位姿档的所有「对齐失败」结论都要先排除这一条。

17. **执行节奏 K 是「泛化」的一等变量，不是档 4 的细节（2026-09-30 实测，本条修正陷阱 14 的适用边界）**：
    同一个 step-3000 检查点、同一批未见 seed 3000..3009、同一套判据，只改 K：
    **K=50 -> 0/10 = 0%，K=10 -> 5/10 = 50%**。K=50 时一局 400 步只咨询策略 **8 次**，
    10 局里 8 局 can 抬起 <0.7 cm；K=10 时咨询 40 次，8/10 局能把 can 抬起 5.4~10.4 cm，5 局落袋。

    **机理已定位到「接近段几何精度」，不是夹爪语义 / 归一化 / 动作尺度**（2026-10-01，
    `code/mg_diag_miss.py` + `code/mg_diag_trace.py`，证据 `runs/_diag/miss_step3000_k50_vs_k10.json`）。
    做法：can 没被抓住 ⇒ 它整局停在**初始位置**，而初始位置由 seed 完全决定，于是把 rollout 的
    eef 轨迹和 can 真值放进同一坐标系，直接量「差多少、差在哪个轴」：

    | 量（同一批 seed 3000..3009） | 脚本专家（60 局示范） | 策略 K=50（0/10） | 策略 K=10（5/10） |
    | --- | --- | --- | --- |
    | 合爪时刻 t | 38（25~50） | 49（40~75） | 成功局与示范同量级 |
    | 合爪时 eef_z | **0.8796**（±0.004） | 平均**高 +2.5 cm** | 0.868~0.881（对齐） |
    | 合爪时横向偏差 dxy | **0.31 cm**（max 0.76） | **5.41 cm** | 成功局 min_dxy 0.03~1.25 cm |
    | 夹爪最小开口 | 0.0417（夹着 can） | **0.0010（空合，10/10 局）** | 成功局 0.0411~0.0417 |
    | 之后 | 抬升搬运落袋 | 9/10 局把臂竖直甩到 eef_z 1.28~1.74 | — |

    所以链条是：**K=50 时第一个 chunk 把臂送到「离 can 还差 3~5 cm、高 2.5 cm」的地方就合爪
    ⇒ 两指合到 0.001（中间什么都没有）⇒ can 原地不动 ⇒ 策略接着执行背下来的「抬升+搬运」，
    一路把臂积分到竖直极限**。K=10 时同样这批 seed 有 5 局把横向偏差收到 1 cm 内、开口停在
    0.0417（= 真夹住了），成功率随之从 0 变 50%。
    推论：**成功与否近乎由「min_dxy 是否 < 1.3 cm」二分决定**（K=10 的 5 局成功全在此内，
    5 局失败的 min_dxy 是 4.2~12.6 cm）。夹爪语义、归一化、动作尺度都是对的——
    否则不会有 0.0417 这个「夹住 can」的读数和专家级轨迹。
    与陷阱 14 并不矛盾，要分档看：
    * 档 0（固定初态过拟合）：轨迹本来就是背下来的，K=chunk_size 能跑出 85%/100%，
      而 K=1 会把 ACT 打到 0%（每步重采隐变量）——**这一档用 K=chunk_size 是对的**；
    * 档 1 起（未见位姿泛化）：需要闭环纠偏，K=chunk_size 会把一个**其实会做**的策略
      测成 0%。此时把 0% 当成「没学会」去查归一化/夹爪语义/数据，方向就全错了。
    ⇒ 新口径：**多初始位姿档的主指标必须带 K 扫描（{1,10,25,50}），单点 K 的结论一律不成立**。
    ⇒ 且 K 不是只能靠扫：训练量上去后 K=50 自己也在涨（step5000：K=50 3/10、K=10 6/10），
      说明「开环也能做」是能力问题不是口径问题，两条曲线要一起报。
    证据：`runs/s1_diag_step3000_k10/eval_summary.json` vs `runs/pi05_rand60_s1/sweep/step_3000/`。

18. **`gripper_width` 在 reset 时就是 0.0417（半合），不是张开**：用 `width < 0.055` 判「已合爪」
    会在 t=0 就命中，算出来「示范合爪时刻恒为 0」。正确判据是**先张开再合上的跃变**
    （`width > 0.070` 之后再 `< 0.055`），已封在 `mg_diag_miss.close_transition()`。
    三态口径：空合 <0.020 / 夹住 can 0.030~0.065 / 张开 >0.070（示范实测：张开 0.0795、夹 can 0.0417）。

19. **`eef_z` 冲到 1.7 不是仿真炸了**：机器人基座实测在 `[-0.5, -0.1, 0.912]`（`get_body_xpos("robot0_base")`），
    竖直可达上限 ≈ 0.912 + 0.855 ≈ **1.77**。示范里 eef_z ∈ [0.874, 1.046]；rollout 里出现 1.3~1.75
    = 抓空后把「抬升」积分到关节极限（陷阱 17 的尾迹），判据是 `z_max > 1.30`。
    顺带：`state_units` 契约写的 `wxyz quaternion` 是**错的**，实测是 xyzw（陷阱见 STAGE_PLAN 档 2），
    档 8 接真机前必须改字符串。

20. **评测端没钉 RNG 种子（已实证，不是推测）**：`mg_eval.py` / `mg_probe_crossinstr.py` 只把 seed
    传给 `env.reset(seed=...)`，没有 `torch.manual_seed` / `np.random.seed`。π₀.₅ 的 flow-matching
    每局从噪声采样 ⇒ **同一检查点、同一 seed、同一 K，重跑逐局结果会变**：
    实测 `pi05_rand60_s1/checkpoints/005000` @K=10 seed=2000，两次跑分别是
    「no_transport / lift 0.6 cm / 失败」和「fwd_like / 严格成功」
    （`runs/_smoke/crossinstr_s1/`，两次间隔 11 分钟，代码与参数完全相同）。
    ⇒ 三条纪律：
    * 结论一律按「≥20 局的成功率」下，**绝不**拿单局当证据；
    * 20 局的成功率**本身也带重跑噪声**（不只是二项噪声），落在门上（如 10/20 = 50%）时必须
      **重跑一次**再判，别用一次读数定档；
    * 需要严格复现时再给 mg_eval 钉种子 —— 档 1 关门前不动它，避免同一条验证曲线的前后段
      跑在不同代码上（这是本项目的隔离纪律，见 STAGE_PLAN 档 2「实现方式」）。

21. **`checkpoints/last` 是符号链接，训练途中会被反复改写**：实测
    `runs/pi05_rand60_s1/checkpoints/last -> 006000`（00:54 更新）。任何「扫检查点曲线」的脚本
    都**必须用显式步数目录** `checkpoints/007200/pretrained_model`；`last` 只有在训练进程退出后
    才等价于最后一步。已经吃过一次：`chain_s1_kcurve.sh` 的 step7200 格用了 `last`，00:59 实际评的
    是 step6000，那条「7200 = 6/10」是 6000 的重复读数（目录已改名
    `runs/s1_kcurve/step_6000_dup_mislabeled`），真 6500/7000/7200 由
    `code/chain_s1_kcurve_tail.sh` 在定版门之后补。定版门（`chain_s1_eval` / `chain_s1_k`）
    用的是训练退出后的 `last`，不受影响。

22. **进程守卫（`pgrep -f`）的五个自伤模式**——今晚五个全部踩到，每个都能让整条流水线静默停摆：
    * **(a) 子串误匹配**：`pgrep -f "mg_sweep"` 同样匹配 `mg_sweep_bidir.sh`。档 1 的定版门
      `chain_s1_k.sh` 因此被一个**不相干的 8 小时任务**永久堵死（01:41 实测）。
      ⇒ 守卫一律写**完整脚本名**并转义点：`pgrep -f "code/mg_sweep\.sh"`。
    * **(b) 匹配到自己**：把 `while pgrep -f "job_name=pi05_rand60_s1"; do sleep; done` 直接写在
      `bash -c "..."` 的监控命令里，pgrep 会匹配**这条监控命令自己**（它的 cmdline 含该串），
      于是所有等待方永远等不到——实测一次把 4 条链同时卡住（01:29）。
      ⇒ 监控时用括号技巧（`job_name=pi05_rand60[_]s1`）或改看 GPU/日志，别把 pattern 原样写进命令行。
      **`pkill` 更狠，它会直接杀掉执行它的那个 shell**：02:23 实测
      `pkill -f "code/chain_watchdog\.sh"` 命中自己的 `bash -lc '...'` 整串命令行，
      当前 shell 收到 SIGTERM（exit 143），**同一行后面的 `apply_patch` 根本没执行**，
      而屏幕上没有任何报错提示——只看到一个莫名的 143。
      ⇒ 杀进程前先 `ps -eo pid,cmd | grep -F '<pattern>'` 把命中集**打印出来核对**再动手；
      或者把 kill 单独一条命令跑，别和后续有副作用的操作串在 `&&` 链上。
    * **(c) 「等退出」在进程从未出现时会立刻通过**：`while pgrep ...; do sleep; done` 在 pgrep
      无匹配时**立即**继续往下走。`chain_s2_eval.sh` 因此在训练发车前 1 秒醒来、找不到检查点
      直接 FATAL 自杀（01:30 实测）。⇒ 先等「出现」再等「消失」，两个条件都要有。
    * **(d) 运行中的 bash 脚本不能改**：bash 按**字节偏移**续读脚本，改文件会让后续执行跳到错误
      位置产生乱码命令。⇒ 要改先 `kill` 再重启（今晚改 `chain_s1_k.sh` 就是这么做的，
      它当时还没产出任何读数，零损失）。
    * **(e) 「先等出现、再等消失」仍会被同名残留进程骗过 —— (c) 的补救本身不够（01:36 实测第二次）**：
      按 (c) 改完之后，`chain_s2_eval.sh` 的守卫是「等 pgrep 出现 → 等它消失 → 收检查点」。
      但坑 24 那次**断行事故**先起了一个同 `job_name` 的短命训练进程，几秒后自己退出：
      出现 ✓ → 消失 ✓ → 本链据此判定「训练已完成」→ 找不到 `last` 检查点 → **FATAL 自杀**。
      而真正的训练 01:39 才发车。净结果：**训练老老实实跑 6.6 小时，档 2 的关门评测根本没人收**，
      失败发生在无人盯的凌晨，日志里只留一行 FATAL，02:05 复查进程表才发现。
      ⇒ 判「上游完成」的唯一证据是**磁盘上的产物**，不是进程状态的翻转。现在三者同时成立才继续：
      `last/model.safetensors 已落盘` ∧ `训练进程静默` ∧ `扫描进程静默`；否则回去重等
      （`MAX_WAIT_TRIES` 轮，默认 8 h 上限），进程在不在只是辅助条件。
      ⇒ 推广成房规：**任何自动化链发车后，都要立刻复查它是否还活着**
      （`pgrep -af code/chain_`），别假设「起过就一定还在等」。为此加了
      `code/chain_watchdog.sh` —— 按「链 → 完成产物」清单每 10 分钟记一次心跳，
      链既不在跑、产物又没出现，就判 `MISSING` 并 loud 报警（正是本条这种死法）。

23. **`lerobot-train` 拒绝已存在的 `output_dir`（`FileExistsError`），而扫描脚本会先把目录建出来**：
    `mg_sweep_bidir.sh` 一上来就 `mkdir -p "$RUN/sweep_bidir"`，所以**一次被杀掉的运行会留下一个空
    `$RUN`，把下一次发车堵死**（01:36 实测：档 2 训练启动即 exit 1）。
    ⇒ `chain_s2_train.sh` 现在发车前把已存在的 `$RUN` / `$RUN_meta` 改名让路（`*.stale_<ts>`），
    绝不静默复用（复用会让 `.done` 记录的步数与实际检查点对不上）。
    顺带记两个量级：单个 π₀.₅ 检查点 **20 GB**，档 1 的 13 个 = 254 GB；`save_freq=1000 × 14400 步`
    的档 2 会再加 ~280 GB。盘够（可用 50 T），但要算。
    * **附带坑（同一事故）**：杀掉失败分支时，只杀了训练进程和 `chain_*` 父进程，
      **漏了它 60 秒后才 fork 出来的 `mg_sweep_bidir.sh`**。那个孤儿扫描按**路径字符串**
      等检查点，于是会和新分支抢同一个 `$RUN/sweep_bidir/`、对同一批检查点做**重复评测**
      （01:36 实测，已 kill 526196/527078/527083）。
      ⇒ 重启一条自动化链之前，必须 `ps -eo pid,ppid,lstart,cmd` 把**整棵进程树**核对一遍，
      确认旧分支死透；「父进程没了」不等于「子进程没了」。

24. **改 shell 脚本里的续行反斜杠 = 静默改变训练超参**：给 `run_pi05_s2.sh` 插一行
    `--seed "${SEED:-1000}"` 时漏了行尾 `\`，而下一行之前是 `exec` ⇒ 命令在那里**截断**，
    训练用默认 `save_freq=2000`、默认 job_name、时间戳 output_dir，并且**丢掉了
    `--extra policy.optimizer_lr=1e-4`**（退回配置默认 2.5e-5）。
    `bash -n` 查不出来（语法完全合法），进程照常跑，日志照常出——只有对比「实际命令行 vs 期望」
    才能发现（01:29 实测，跑了 7 分钟才发现，已杀掉重来）。
    ⇒ 两条防线：① 可变参数放在参数表**最末尾**（漏反斜杠只会丢它自己）；
    ② 发车前用 `DRY_RUN=1` 打印真实 `[cmd]` 并逐项断言关键 flag（`chain_s2_train.sh` 的预检，
    缺一项就 `exit 4` 拒绝发车）。**任何自动化发车的脚本都该有这道预检。**

25. **`lerobot-train` 把 ≥1000 的 step 缩写成 `1K`/`7K`，任何 `step:[0-9]+` 的正则都会在 900 处静默截断**：
    指标行形如 `ot_train.py:435 step:7K smpl:58K ep:240 epch:4.00 loss:0.041 ...`——
    `step:` 和 `smpl:` 两个字段都被 humanize 过。03:05 实测：档 2 训练明明跑到 step 2688，
    用 `grep -oE "step:[0-9]+ .*loss:[0-9.]+"` 抽曲线只抽出 9 个点、最大 step 900，
    看起来像「训练在 step 900 之后就不再记日志了」。
    **已结束的档 1 日志同样是 72 行齐全**（`grep -c 'loss:'` = 72 = 7200/log_freq 100），
    证明不是丢日志，是正则没匹配上缩写形式。
    ⇒ 抽 loss 曲线用 `epch:` / `loss:` 这两个**不会被缩写**的字段，别用 `step:`；
    要步数就从 tqdm 行取（`tr '\r' '\n' | grep -oE "[0-9]+/14400 \["`，看门狗就是这么读的）。
    ⇒ 顺带记一条同源的：**`logs/train_pi05_s2.log` 在训练结束前一直是 0 字节**（包装脚本 stdout 被块缓冲），
    真正的日志在 `runs/<job>_meta/train.log`。别把这两件事当成「训练卡死」。

26. **`checkpoints/last` 不能当关门检查点**：小数据 BC 的成功率**先升后降**，用 `last` 关门
    等于把「选点」这件事偷偷交给「训练什么时候停」。档 2 实测：正向 val 6/10(9000) → **8/10(11000)**
    → 5/10(14000)，反向 val 3/10(10000) → **5/10(11000)** → **0/10(13000)** → 2/10(14000=last)。
    ⇒ 关门检查点必须**只用 val 选**（`code/mg_select_ckpt.py`：规则写死、曲线落盘、可审计），
    选定后 TEST **只准读一次**；读完再回来换规则重选 = 在 test 上挑点，test 就退化成第二个 val。
    ⇒ 但别指望选点能救一个真不行的模型：档 2 换到 val 峰值 011000 后，反向 TEST 反而从
    32.5% 掉到 26.7%（见坑 27）。选点是**卫生**，不是**杠杆**。

27. **val 只有 10 局时，「挑 val 最大值」= 在纯噪声里挑峰**：p≈0.3 时 n=10 的 1σ≈15 pp，
    14 个扫描点里必然有一个看起来像 50%。档 2 就是这么选中 011000 的（val rev 5/10=50%），
    TEST 三读实测 **26.7%**；而 val 只有 2/10=20% 的 `last`，TEST 却有 32.5% —— **val 与 TEST 反序**。
    ⇒ val 至少 20 局（1σ≈10 pp）才谈得上选点；更稳的做法是**主读数用等 epoch 的 `last`**
    （规则与基线一致、可直接对账），val 曲线只当「学习趋势」看，选点读数只作并列参考。
    `code/mg_sweep_rev.sh` 已按这条改（档 2c 起 val = 20 局）。

28. **交叉指令探针会把「行为冻结」读成「照指令走」**：行为指纹只看 can 末态落在
    bin1 托盘 / bin2 象限哪个中心附近，而「策略停摆、can 纹丝不动」与「听懂了所以不搬」
    **指纹完全相同**。原实现 `follow_string = behavior_counts['no_transport']`，
    于是一次停摆就能被读成「π₀.₅ 真的在做语言条件化」。实测两个交叉格 40 局里
    **39 局 max_lift < 0.3 cm**（根本没碰 can）。
    ⇒ 已修：`code/mg_probe_crossinstr.py` 按 `max_lift_cm < 1.0` 把 `no_transport` 拆成
    `follow_string`（碰过没搬）与 `frozen`（纹丝不动），冻结占比 ≥80% ⇒ `probe_conclusive=False`，
    该探针**不出结论**。要真判语言条件化，得加一个能区分两者的观测量
    （例如 eef 是否到过本场景目标上方），或改成「同一场景、两条指令」的对照设计。

29. **闭环评测读数不可复现：同检查点、同 seed、同 K，三读 30% / 35% / 55%**。
    根因：`mg_env._seed_randomness` 只钉了 `env.rng` / `sampler.rng` / `np.random`，**没钉 torch**；
    π₀.₅ 的 flow-matching 动作采样从 **torch 全局 RNG** 抽噪声，而它在进程启动时是随机播种的
    ⇒ 初态逐比特相同、动作序列每次不同。
    ⇒ 后果一：单读 20 局的 1σ≈**11 pp**，比二项公式给的还大（因为策略内部也随机）。
      判 50% 的门至少要 **60~80 局**；A/B 比较两边必须同局数，否则显著性检验的功效是假的。
      （档 2 的门当初用 40 局判反向 32.5% FAIL；补读到 60 局是 40%，80 局见 `runs/S2_VERDICT.md`。
      结论方向没变，但**幅度被高估过**。）
    ⇒ 后果二：修法很简单（每局开头 `torch.manual_seed(seed)`，rep 索引进 seed 就能既复现又独立），
      但**中途改会让已收的 100+ 局全部不可比**，所以留到档 5（Harness）一次性换口径并记录。
      在那之前：任何单读数字都不许单独当结论用。

30. **「降级/作废」类护栏字段自己也会坏，而且坏得很安静**：`code/mg_probe_crossinstr.py`
    用 `ckpt.parent / "train_config.json"` 找检查点的数据出处，而 lerobot 把这个文件写在
    检查点目录**里面**（`pretrained_model/train_config.json`）⇒ `dataset_of_ckpt` 恒为空串
    ⇒ `conclusion_valid=False`，一次**跑对了**的探针（40 局行为数据全在）被静默判成不可用。
    护栏算错比数据算错更难发现：它不报错，只是把好结果降级扔掉。
    ⇒ 已修（先按里面找、再退回父目录），并加 `--rescore <dir>`：**不重跑**、只重算
    `dataset_of_ckpt` / `conclusion_valid` / `probe_conclusive` 并重写 summary
    （`cells`/`per_episode` 原样保留）。⇒ 房规：护栏字段必须把它**实际读到的路径**打印出来，
    否则没人知道它是判对了还是根本没找到文件。

31. **量「举多高」有四个坑，每一个都会安静地给出错数字**（`code/mg_lift_profile.py` 前两版全踩了）：
    (a) **基准选错**：以开局 `eef_z` 为基准，量出来专家示范的抬升是 **0.0 cm**、松手时比起始**低** 11 cm
        —— 因为机械臂是先降到桌面抓 can 再抬到篮口，而篮底与桌面齐平（`BIN_FLOOR_OFFSET=0`）。
        ⇒ 高度必须以**抓取瞬间**的 `eef_z` 为基准；这样「松手高度」就直接等于 can 的**跌落高度**。
    (b) **松手检测不能用单一宽度阈值**：reset 后空手开口 `0.0417`、夹住 can `≈0.05`，只差 **0.008**
        ⇒ 任何「宽度落在夹持带里」的判据会把**每一局开局**误判成「已经夹住了」。
        必须走状态机：只有「先张开(`w>0.070`) 再收拢」才算一次抓取尝试，收拢后 `w>0.012` 才是真夹住
        （空合只有 `0.001`）。数值取自 `mg_env.py:66-69` 的实测常量。
    (c) **两个口径偷偷错开**：`carry` 算在**最后一段**夹持、`release` 算在**第一段**。
        成功局只有一段所以看不出来（r=0.992 是真的），失败局是多段，一读就串。
        （这里原先写过「100 局里 50 局 ≥2 段」，那个数是 (d) 的分段 bug 造出来的；修好后是 **9/71**。）
        ⇒ 逐段记录后派生：`carry_cm` 取各段最大（与 eval 的物体 `max_lift` 同义）、
        `release_above_grasp_cm` 取第一次松手，并**同时**报 first/last/max 三个口径证明结论不依赖选法。
    (d) **判「夹住了没有」要看段内宽度的中位数，不能看单个样本，也不能看最小值**：
        闭合是个**过程**，手指合拢途中宽度会短暂经过 0.05 附近；用「第一个 w>0.012 的样本」判夹持，
        会把**空合**（最终压到 0.001）也算成一次成功夹持。实测这样量出来 A 类（物体从没离地）的
        「夹持段」宽度中位是 **0.0010** —— 和空合值一模一样，而专家是 0.0499。
        反过来用 `w_min` 也不行：成功局有 2/29 的段最小宽度瞬时掉到 0.0015（松手抖动），
        会把真成功判成空合。**中位数**在两个阳性对照上都是 100%（DEMO 60/60、OK 29/29）。
        ⇒ 这个 bug 曾经造出一条 Fisher **p=1.1e-11** 的假结论（见上面「一条被自己撤回的结论」）。
    另外两条方法论：**代理校验只在成功局上做**（r=0.992；全局只有 0.07，因为 A 类 31 局物体根本没离地
    而 eef 在动 —— 用全局相关性会把一把好尺子判废）；**有效性门用阳性对照**（策略成功局必须复现
    专家的松手高度），而不是用全局相关性 —— 松手高度是直接测量，不经代理。

32. **训练 seed 不是连续的，「记忆对照」必须先核对 seed 真在训练集里**：
    反向采集带重试，60 条示范的 seed 散在 **[5000,5092]**（中间 33 个值根本没用上）。
    而 `mg_eval` 只能给**连续**窗口（`seed = args.seed + ep`），所以档 2c 主链的护栏 G2
    用 `--seed 5000`（= 5000..5009）时，里面 **5002 不是训练 seed** ⇒ 那道「训练 seed 对照」
    实际只有 **9/10** 是真训练局。偏差方向是**更保守**（更不容易报出记忆），不改变判定，但要记下来。
    正向 seed 1000..1059 是**连续**的，所以正向对照没这个问题 ——
    **别把「正向没踩到」推广成「反向也没踩到」**，两边的采集脚本不是同一次跑的。
    ⇒ 逐 seed 核对后，唯一一段完全落在反向训练集里的连续 10-seed 窗口是 **5062..5071**。
    `code/mg_g2_supp.sh` 已把这个核对做成**发车闸**（窗口里缺一个 seed 就 `exit 4`，
    实测拿 5000 去跑确实被拦下并打印 `[5002]`）。
    **更要紧的是 n=10 的护栏几乎没有功效**：对 TEST 30/80 做 Fisher，训练 seed 要 **≥8/10**
    才触发 p<0.05（实测 5/10→p=0.50、6/10→p=0.19、7/10→p=0.085）。
    ⇒ 所以第 3 轮那条排除#3「无记忆」的**正确读法**是「**没有碾压式记忆的证据**」，
    不是「排除了记忆」。顺带核过：把 5002 那局按最坏情况算成成功（6/10），Fisher 仍 p=0.190
    ⇒ 档 2 那条排除**不受这个 seed 缺口影响**，不用重跑。要真判得 4 读 40 局（`code/mg_g2_supp.sh`）。

33. **跨 run 比曲线必须先换算成 epoch，否则会拿「训练量多一倍」冒充「没有干扰」**：
    档 2c 的对照双方帧数不同（单任务 16032 帧 / 联合 30447 帧，batch 都是 8）
    ⇒ 每 epoch 分别是 **2004 步** 和 **3806 步**。**同号 step 的 epoch 差整整一倍**：
    step 4000 对单任务是 2.00 ep，对联合只有 1.05 ep。按步号并排画曲线，单任务在每个点上都「赢」，
    而这个赢跟干扰毫无关系，纯粹是它多训了一倍 epoch。
    ⇒ `code/mg_epoch_curve.py`（**43 项自测**）把 steps/epoch **从 meta.json 反查出来并打印出处**
    （优先 `episodes_subset.n_frames`，回落到数据集 `meta/info.json` 的 `total_frames`；
    查不到就报错、**绝不用默认值**），再按预注册规则对齐：对基准 run 的每个 epoch 网格点，
    取对方 |Δepoch| 最小的点，并列取更早的 step。实测对齐后 2.00 ep 处 30% vs 20%、Fisher p=0.649。
    **它只报趋势、不出判定**（val n=20 且坑 27 记录过 val/TEST 反序）；判定仍只认 TEST 4 读 80 局。
    顺带量到一条形状事实：联合模型的反向 val 在 **2.89 ep 见顶 50%（5/10）→ 3.42 ep 掉到 0%**，
    而两边的 `last` 都在 **3.79 ep** ⇒ **主读数落在双方的下降尾巴上**。这不破坏档 2c 的公平性
    （同 epoch、同规则，比的正是「去掉正向帧有没有用」），但它说明「早停/选点」是
    **独立于**干扰假设的另一条杠杆 —— 别把两者塞进同一次改动里，否则又归因不了。

34. **每个检查点 20 GB，其中 13 GB 是从没用过的 `training_state`；`runs/` 已经 1.6 TB**：
    `checkpoints/0NNNNN/` = `pretrained_model/`（**7.0 GB**，评测只需要这个）
    + `training_state/`（**13 GB**，只有断点续训才读）。四个已关门的 run 各 15 个检查点
    ⇒ 约 **780 GB 纯死重**，而共享盘当时 **97% 满**（余 38 TB）。
    ⇒ 房规：① 新 run 的 `--save-freq` 按「真要几个 val 点」给，别照抄 1000；
    ② 清理只动**已出判定**的 run 的 `training_state/`，且要先跟人确认（删除不可逆，
    删到正在跑的 run 会直接毁掉那一发）；③ 任何链发车前先 `df` 一次
    （`code/chain_s2e_data.sh` 里做成了门槛 `NEED_DISK_GB=40`）。
    本轮**没有**执行任何删除：档 2c 还在飞，动刀的时机是判定落盘之后。

35. **`fisher_two_sided` 的签名是 (成功数A, 试验数A, 成功数B, 试验数B)，传「失败数」不报错、只给错 p**：
    本轮新写的两个工具（`mg_epoch_curve.py`、`mg_verdict_s2e.py`）**都**在第一版把第二/第四个参数
    传成了 `n - k`（失败数）。函数照样返回一个 0~1 之间的浮点数，看起来完全正常 ——
    这是最危险的一类 bug：静默给出错的显著性，而判定全靠它。
    实测差多少：6/20 vs 2/20 正确 p=**0.2351**，传失败数得到 **0.682**（差 2.9 倍）；
    本来「不显著」的结论量级都被改写了。
    ⇒ 房规：① 任何调用 Fisher 的新工具，selftest 里必须用一个**独立写法**（直接枚举超几何）
    钉死参数语义，不能只测「返回了个数」；② 断言里写死的参考值必须是**算出来的**
    （本轮对着 `scipy.stats.fisher_exact` 逐位核过：0.23511623511623514 / 7.2615872e-06 / 1.0 全同），
    不能凭记忆写 —— 第一版硬写的 0.1948 就是错的，被自测抓出来；
    ③ 报告文本里凡是「护栏没到」的行会带「不作废」三个字，**别用子串「作废」去断言**（会假失败），
    作废的唯一标记是 🚫。

36. **「换个工作点会不会更好」要先算实时预算，别先跑实验**：
    A 类抓空（占失败 44%）看着很像「重规划不够频繁」，直觉上想扫 K∈{1,5}。
    但档 4 已经把账算死了：单次推理 ≈0.323 s、控制频率 20 fps ⇒ 每控制步预算 **50 ms**；
    K=5 摊到每步是 **65 ms（已超预算 30%）**，K=1 是 323 ms（超 6.5 倍）。
    ⇒ **K<10 全部不可部署**，扫了也不能用；而「异步 chunk 调度」在第 1 轮就明确排除在外。
    所以这一发**没有跑**，A 类只能从数据/示范侧修（这正是档 2e 与档 2d 的 H1/H2/H3 归因要回答的）。
    教训：动手前先翻已算死的账（档 4 的墙钟拆解），能省下一小时 GPU 和一个无法落地的结论。

37. **`setsid nohup ... &` 外面那层 wrapper shell 会**长期活着**，把看门狗的静默死亡检测废掉**：
    用 `bash -c '... setsid nohup bash code/chain_X.sh ... &'` 发车时，那个 `bash -c` 本身
    会留在进程表里（PPID=1，SID 是它自己的），而**它的整条命令行里就含有 `code/chain_X.sh`**。
    看门狗判 RUNNING 用的是 `pgrep -f 'code/chain_X\.sh'` ⇒ 哪怕真的链已经死了，
    这个 wrapper 仍然命中，心跳永远显示 RUN，**报警永远不会响**。
    这比坑 22(a)（`pgrep -f` 匹配到你自己的命令行，一次性误报）更危险：那个是假报警，
    这个是**假健康**，而且会持续几小时。2026-10-01 23:40 实测抓到两个（s2e_train / watchdog 各一）。
    ⇒ 房规：① 发车后必须 `pgrep -af '<pattern>'` 数一下命中数，**只能有 1 条**，多出来的按 PID 杀掉；
    ② 杀之前先确认目标链的 `SID == 自己的 PID`（`ps -o pid,ppid,sid,stat`，STAT 带 `s`）——
    是 session leader 才说明 setsid 生效、杀 wrapper 不会连带杀掉它；
    ③ 一次 `bash -c` 里只发一条链，别把 kill/python/relaunch 揉在同一行（这次的 wrapper 就是这么来的）。

38. **扫描的终点格用 `checkpoints/last` = 拿上一个检查点冒充终点**（`mg_sweep_rev.sh` / `mg_sweep_bidir.sh`）：
    lerobot 的 `checkpoints/last` 是**每次 save 都重指的软链**，不是「训练结束才出现」。
    原 `wait_ckpt()` 在 `s == STEPS_TOTAL` 时把 `ck` 指到 `last/pretrained_model`，然后只检查
    `model.safetensors` 是否存在 ⇒ 训练还在半路时 `last -> 020000` 早就存在，函数**立刻返回**，
    于是 `step_22000_rev` 读的是 020000 的权重，还把 `22000` 写进 `.done` 让它永远不被重测。
    2026-10-02 09:36 档 2e 实测吃到：`step_20000_rev` 6/20 与 `step_22000_rev` 10/20 是**同一份权重**
    （inode 37381291785 相同，`readlink last` = 020000）。
    ⇒ 修法：终点格必须核对 `readlink checkpoints/last == %06d(STEPS_TOTAL)` 才认（已改成 `wait_last_ckpt`），
    并把「这一格读的是哪个 ckpt 目录」打进日志（坑 30）。
    ⇒ **波及面已核清**：档 2（STEPS_TOTAL=14400）与档 2c（7600）都**不是** SAVE_FREQ=1000 的整数倍，
    循环 `s<=STEPS_TOTAL` 根本走不到终点格 ⇒ 那两档的历史曲线**没有**终点格，是「没测」不是「测错」，
    所有已落盘判定不受影响。主门读数用的是训练结束后才解析的 `last`，也是对的。
39. **评测本身不可复现，所以「重跑一次结果一样」不能当回归测试**：
    `mg_eval.py` 只钉了 numpy/仿真随机源（`env.reset(seed=…)`），**没有钉 torch 种子**；
    而 π₀.₅ 的 flow-matching 去噪从 `torch.randn` 起步 ⇒ 每次进程启动的动作噪声都不同。
    同一份权重、同一批 seed、同一个 K，两次读 6/20 与 10/20（档 2e，见坑 38）。
    ⚠️ 别把这读成「环境不稳」：n=20、p≈0.4 时两读之差的 1σ = √(2·20·0.24) ≈ 3.1 局，
    差 4 局只是 1.3σ —— **完全在二项噪声内**。真正的教训是：
    ① 单次 n=20 的读数 1σ ≈ 11 pp，任何「val 选点」「一格曲线」都别当结论（坑 27 的 val/TEST 反序就是这么来的）；
    ② 同一检查点重读 = **独立抽样**，不是复现，不能用来证明「代码没改坏」；
    ③ 要回归测试就用**钉死随机源的那条路**：`mg_ceiling.py` 把噪声流写成 `default_rng(12345)`，
       同参数重跑 = 逐比特相同轨迹 ⇒ 2026-10-02 改判据就是靠它逐局回归的（20/20 局 success、
       success_step、steps、final_tilt、min_dist 全部一致）。策略侧的 torch 种子留到档 5 再钉。
40. **事后放宽判据有四条纪律，少一条就变成 p-hacking**（2026-10-02 用户授权放宽反向口径时立的）：
    背景：档 2c 严格口径 46.2% 差 3.8 pp 没过门，分类账显示多出的都是「送到了却侧躺」（C 类）。
    用户拍板「送到目标位置为首要条件，侧躺也算送到，但要追加标记」。这是**看到结果之后**改口径，所以：
    ① **历史数值不追改**，两口径并排报（`pc_success` 语义一个字不动，放宽另开 `pc_success_relaxed`）；
    ② **上界必须同口径重测**：严格上界 14/20=70%，放宽后 **20/20=100%**（6 局专家失败全是侧躺而
       min_dist ≤0.52 cm，早在 ±9 cm 框内）。分子放宽、分母不放宽，比值就没意义；
       顺带一个反直觉后果：「这 6 个 seed 专家也做不到、不该算策略的账」这个借口**消失了**；
    ③ **缺字段 ≠ 0**：改判据前跑的 `eval_summary.json` 没有 `pc_success_relaxed`，必须显式剔除并报出来，
       当 0 计入会把结论系统性压向失败；
    ④ **显著性重算**，不许沿用严格口径的 p；且要写清「两组是同一策略的独立 rollout」，
       所以口径效应的 p 里混着重采样噪声（坑 39），不是配对检验。
    实现上把判据抽成**纯函数** `mg_env_reverse.reverse_settled(..., upright_required=)`，
    两口径在同一条轨迹上并行判定 ⇒ 放宽读数**不额外花 GPU**（档 2e 的 160 局关门读数是白捡的），
    并由 `code/mg_criterion_selftest.py`（66066 项）钉住「严格 == 历史实现」与「严格 ⊆ 放宽」。
41. **`cd X && cmd &` 会把整条 `&&` 链都丢到后台**，前台 shell 的 cwd 根本没变：
    2026-10-02 10:12 发车档 2f 时写成 `cd $MG && setsid nohup bash code/chain_s2f_relax.sh > logs/x.log & sleep 8; cat logs/x.log`
    ⇒ `cat` 报 No such file（它在**原** cwd 找 `logs/x.log`），一度以为链没起来。
    链其实好得很（PPID=1、日志在 `$MG/logs/`）。⇒ 房规：后台发车后的自查一律用**绝对路径**，
    或者写成 `( cd $MG && setsid nohup … ) &` 把子 shell 括起来。
    🔁 **2026-10-02 20:38 复发一次（换了个形状，更阴）**：档 5 第一次发车时链在旧 G0a 判据上 `die`，
    修完判据重新发车时沿用了**同一个日志名** `logs/chain_s5_harness.log`；重定向是发车那一刻才截断的，
    在这之前 `tail` 到的全是上一轮的 `[G0a] FAIL`，读起来就像「修了还是不过」。
    ⇒ 加强版房规：① 后台发车后的第一条自查命令自带绝对路径（`MG=…; tail -n 20 "$MG/logs/x.log"`）；
    ② **发车前先把同名旧日志 `cp` 成 `.pre_<原因>.log` 留档**（本次留的是 `logs/chain_s5_harness.pre_g0afix.log`），
    让「盘上那行 FAIL 属于哪一轮」永远可判；③ 判链是否真在跑只看 `pgrep` 的 PID 与日志 mtime，不看内容。

42. **选点脚本只看目录名、不看产物里的 `policy_ckpt`** ⇒ 坑 38 的坏格能一路骗到 `ckpt_selection.json`：
    2026-10-02 档 2e 的 `sweep_rev/step_22000_rev/` 装的是 020000 的权重（`last` 当时指着它），
    读出的 val 10/20 被旧版 `read_sweep()` 当成 22000 的分，argmax 就这么选中了 22000。
    上游 `wait_last_ckpt()` 修的是「别再产生坏格」，**下游没人核出身**。已修：
    ① `mg_select_ckpt.py` 逐格核 `policy_ckpt` 的格号 == 目录名 step（记 `last` 就现场 `readlink` 核对），
       对不上 ⇒ `mismatch` 剔除**并打印原因**，绝不参与 argmax（**第二道闸**）；
    ② 顺带修掉同源的第二个 bug：`--direction both` 时某格只有 fwd 没有 rev，旧版按 `fwd + 0` 记分
       ⇒ 系统性压低它；现在**取消资格**进 `ineligible`（与坑 40③「缺字段 ≠ 0」同一条原则）；
    ③ 新增 `--out`，更正写到 `ckpt_selection_corrected.json`，**误标版原样留档**，
       且 `--selftest`（51 项）里有一条反向断言钉住「历史文件必须仍是 22000/10 分」，谁覆盖了自测就红；
    ④ 回归证明没改坏历史：新版重算 档 2 = **11000/13 分**、档 2c = **5000/8 分**，与两份历史
       `ckpt_selection.json` 逐个数字相同，两条 sweep 剔除格都是 0。
    ⇒ 房规：**任何按目录名索引产物的汇编脚本，都必须回头核对产物内部自报的出身**（ckpt 格号 / seed 窗口 / task 串）。

43. **`date +"…%s…" 参数` 不是 `printf`**，多出来的参数会让 `date` 报 `extra operand` 并写出**空标记**：
    2026-10-02 档 2f 与档 4r 两条链的收尾都写成
    `date +"%Y-%m-%d %H:%M:%S …完成 K=%s ckpt=%s" "$KS" "$WANT" > "$MARK"`
    ⇒ `runs/s2f_relax.done` 与 `runs/s4r.done` 都是 **0 字节**（日志里那行 `date: extra operand` 就是它）。
    **为什么危险**：下游闸门一律按 `[ -f "$MARK" ]` 判存在，空文件照样「存在」⇒ 链其实没写清
    「什么时候、用什么参数收的工」，而这正是房规要求的 provenance。要是哪天有人把闸门改成
    `[ -s "$MARK" ]` 或去 `cat` 它取参数，就会**静默**拿到空值。
    ⇒ 修法：改用 `printf '%s …\n' "$(date +'%Y-%m-%d %H:%M:%S')" …`，并且**写完立刻断言非空**
    `[ -s "$MARK" ] || die "标记写空了"`。已修 `chain_s2f_relax.sh` / `chain_s4r_kcurve.sh`
    （各留 `.bak_pre_datefix`），两个空标记按日志里的真实收工时间**回填**并注明是回填。
    ⚠️ `chain_s3r_seed.sh` 同一个 bug（第 140 行），但**正在跑**、房规不许改运行中的脚本
    ⇒ 它的 `runs/s3r.done` 也会是空的，等链收工后回填（`logs/chain_s3r_seed.log` 的收工行是时间出处）。

44. **π₀.₅ 的 GPU 前向本身不可逐比特复现，钉死 torch 种子也没用** ⇒ 「同权重 + 同种子 ⇒ 动作流逐比特相同」
    这类等价性护栏在 GPU 上**根本写不成**（2026-10-02 档 5 的 G0a 上撞的）。
    实测：`--torch-seed 12345` + 同 3 个 env seed（7002..7004），**三次「检测器关掉」的对照跑之间**就两两不同 ——
    首个分歧步 = **1**、`max|Δaction|` ≈ **2.04**、局长度 `[400,400,282] / [400,400,283] / [400,400,257]`；
    而**逐局放宽结果三对全一致**（成功局落在 283 / 282 / 257 步）。也就是分叉从第一次前向就开始，
    量级和「换了一颗种子」一样大，但**统计口径没被破坏**。
    根因：cuDNN / 矩阵规约的非确定性，被 flow-matching 的多步去噪迭代放大。
    ⚠️ 这条比坑 39 更硬：坑 39 只观测到「成功率不可复现（6/20 vs 10/20）」，本条证明**连动作流都从第 1 步分叉**，
    所以「重跑一遍结果一样」既不能当回归测试，也不能当等价性证明。
    ⇒ 修法（`code/mg_g0a_equiv.py`，两层判据；旧的 `mg_g0a_bitcmp.py` 已改名 `.superseded` 留档）：
    ① **G0a-1 CPU 确定性**（7 项）：桩策略下 observe-only 与 detector-off 的动作流**逐比特相同**，
       且 harness 前后 torch 的 CPU/CUDA RNG 状态**未被触碰** ⇒ 证明「外壳代码」自己不消耗随机数；
    ② **G0a-2 GPU 噪声地板对照**：先跑 **3 次 detector-off** 当地板，再判被检对
       「首个分歧步**不早于**地板 ∧ 逐局放宽结果一致 ∧ 局长度落在地板的取值范围内」，
       外加结构化断言（每步恰好一次策略调用、observe 模式下专家步数 = 0）。
    ⇒ 房规：**GPU 上的等价性只能用「噪声地板对照 + 结构化断言」，不能用逐比特**；
    真要逐比特就搬到 CPU，或者走 `mg_ceiling.py` 那条钉死 `default_rng(12345)` 的专家路（坑 39③）。
    ⇒ 连带后果（已写进 `runs/S5_PREREG.md`）：档 5 的 G0b「观察模式 == 基线」也只能按**二项噪声**判，
    不能按「逐局相同」判；实时性门（≤50 ms/step）只在 `timing_isolated=true` 的产物上判。
45. **可行性预检的「接管前状态」必须采样自被测策略，不能来自专家自己** —— 否则预检证明的是
    「专家能不能接**自己**的班」，天花板会系统性虚高（2026-10-02 档 5 实测吃到）。
    `code/mg_resume_probe.py` 的构造是 `expert_cls(env).reset()` → 专家跑 t 步 → `resume()`，
    所以它量到的 T1 4/5、T3 7/8、carry 5/5 全是**干净前态**（can 立着、腕姿态是专家自己的、末端在专家轨迹上）。
    预注册据此算出可行性天花板 (55+13.0)/80 = **85.0%**，正式读数只有 **76.7%**；
    而差距**不在检测器**（失败召回 25/25 = 100%、在线触发率 36.7% ≈ 离线标定 36.2%），
    在「专家接**策略**的烂摊子」：23 次接管里只有 **12 次**能走进 `grasp`。
    ⇒ 房规：任何「续跑 / 接管 / 恢复」类能力的预检，前置状态必须来自被测策略的真实 rollout
    （最省事：直接回放正式读数落盘的接管片段）；否则门会被设计在虚高天花板的刀刃上（本轮 H1 门就正好卡在 85%）。
46. **反应式状态机的相位退出逻辑不对称 = 静默死循环**，而且它在指标上长得像「正常运行」：
    `code/mg_expert.py` 的 `grasp` 相位有 `MAX_GRASP_TRIES=3` 的「再降 4 mm 重夹」阶梯，
    而 `descend → grasp` 的判据（`xy_ok` ±8 mm ∧ `|eef_z − can_z − 15 mm| < 10 mm`）**没有任何超时/退路**
    ⇒ 判据长期不成立时，专家以 0.7 倍速在 can 上方**原地打转到 horizon**（档 5 实测 162~305 步、
    爪子全程 0.0798 完全张开、11/23 次接管如此）。
    **为什么危险**：失败得很安静 —— 成功率只掉一点、相位序列看着「在干活」、每步动作都合法、
    ms/step 还更快（专家 0.03 ms/step vs 策略 50.8）⇒ 光看门指标看不出有一半接管在空转。
    ⇒ 房规：① 每个相位都要有**超时 / 重试上限**，超了显式记 `unrecoverable`（让失败可观测）；
    ② 诊断看**相位游程长度**（`itertools.groupby`）而不是相位集合 —— 集合会去重，
    `['approach','descend']` 这种「正常」序列可能就是 300 步死循环；
    ③ 判「卡住」的硬证据是**命令 vs 实际**：`dz_cmd`（从 action 反解）与 `dz_act`（eef 实测位移）之比 <20%
    ⇒ 接触阻挡；can 每步还在动 ⇒ 目标被推着跑（`code/mg_diag_resume.py` 就是为分辨这两者写的）。
47. **干预类实验（harness / 接管 / 纠正）的主判据必须是「配对净收益」，不是总成功率**：
    档 5 总成功率 46/60 = **76.7%** 比同 3 rep 基线 39/60 = 65.0% 高 **+11.7 pp**，看着像有效；
    按 (rep, seed) 配对拆账却是：**救回 6 局 / 把「基线会成功」做成失败 6 局 ⇒ 净 0 局**，
    而且 Fisher **p = 0.2280** 本来就不显著。根因是坑 39：同初态两次 rollout 是**独立抽样**，
    n=20 单读 1σ ≈ 11 pp，三读之间的漂移足以造出 ±10 pp 的「效果」。
    ⇒ 房规：① 干预类读数必须报**四类拆账**（救回 / 毁掉 / 两边都失败 / 两边都成功），
    只报总成功率 = 把噪声当效果；② 下一轮预注册把「配对净收益 > 0」写成主判据；
    ③ ⚠️ 配对仍**不是反事实**（基线是另一次采样），净收益也只是估计 ——
    要更接近反事实就用 observe-only 那一读：`would_have_fired` ∧ 本局最终成功 = **真误触发**
    （档 5 实测 3/22 = 13.6%，其中 2 次是「已松手、落定保持还没走完时爪子空合」的判据结构性尾巴）。

48. **单位藏在字段名里 ⇒ 阈值静默放大 1000 倍，把「can 静止」读成「can 被推着走」**（`code/mg_diag_resume.py`）：
    `med_dcan_xy_mm` 在算的时候已经 `* 1000` 变成 mm，`stuck_verdict` 里却又写成
    `med_dcan_xy_mm * 1000 >= CAN_MOVING_M * 1000` ⇒ 两边约掉后实际阈值是 **0.0005 mm**（应为 0.5 mm）。
    seed 7014 的 can 每步中位位移 **0.005 mm**（= 静止）被判成「XY 追不上：can 在被推着走」，
    重算后改判「XY 对不上：can 静止但末端进不了 ±8 mm（中位误差 9.6 mm）」——
    两种结论指向**完全不同**的修法（前者要改夹持/推挤，后者要改对准容差），而指标上一个字都看不出来。
    ⇒ 房规：① 带单位后缀的字段在比较处必须与阈值同单位，阈值一侧也写全（`CAN_MOVING_M * 1000`）；
    ② 自测必须钉**阈值上下各一点点**的两例（`CAN_MOVING_M` 与 `CAN_MOVING_M * 0.999`），只钉典型值的自测抓不到单位错误；
    ③ 统计口径改了就在**同一份 trace** 上 `--reanalyze` 离线重算（不重跑仿真、不占 GPU），
    原版自动留档 `.pre_reanalyze_*`、旧逐局判定留在 `per_episode_pre_reanalyze`（坑 40：不静默覆盖）。

49. **「有产物就跳过」的回归脚本 + 改了被测代码不换输出目录 = 拿到旧代码的 PASS**：
    `code/mg_g1_expert_regression.sh` 可续跑（`[ -f ceiling_summary.json ] && 跳过重跑`）。
    给 `mg_expert.py` 加完 descend 停滞阶梯后若沿用旧目录，脚本会把**改之前**那份产物拿来对账并打印 `[G1] PASS` ——
    护栏看着过了，实际测的是旧代码，档 5.1 的整条读数都建在假锚上。
    ⇒ 房规：① 改完专家必须换 `G1_NEW=runs/s5_1_g1_*` 重跑（本次新锚 `runs/s5_1_g1_ceiling_rev_test20_n05`，
    专家 sha16 `317c2b29…`，20 局逐比特、严格 14/20 ∧ 放宽 20/20）；
    ② 发车闸**不能只 grep 日志里的 PASS**，还要核产物里记的 `code_sha256_16` 与当前文件哈希逐个相同
    （`code/chain_s5_1.sh` 闸 3：env/expert 四个文件全对齐才放行）；
    ③ 通用形式：任何「跳过已有产物」的脚本，其产物必须自带被测代码的哈希，闸门比的是**哈希**而不是存在性。

50. **「松手后守卫窗」被标定否决：只用夹爪宽度分不开「放进目标区的正常松手」与「中途滑脱」**：
    动机是修坑 47③ 那 2 次「已松手、落定保持还没走完时爪子空合」的结构性误触发。
    守卫判据 `held ∧ 最近 guard_w 步内出现过 width ≥ 0.07 ⇒ 抑制本次触发`，在**档 5 开工前就存在**的
    档 2 反向 TEST 240 局上扫 `guard_w ∈ {0,5,10,15,20,25,30,40,60,90}`（`runs/_diag/guard_calib.md`）：
    `s2e` 臂失败召回恒 **25/25**、误触发恒 **4/55** ⇒ 副门「4 → ≤1」**一个窗长都没满足**；
    窗长拉到 90 还开始吃真失败（ALL 臂 105/108 → 103/108、`s2c` 36/36 → 35/36）。
    机理：那 4 次误触发发生时「距上次张开 **140~205 步**」，根本不是松手尾巴 ⇒ **时间窗这个自变量选错了**。
    要真分开只能用目标框真值（can 是否已在 bin1 ±0.09 m 内），那会破掉「只用本体感觉、真机可迁移」的前提 ⇒ 第一轮不引入。
    ⇒ 房规：① 加抑制逻辑前先在旧语料上标窗长（语料早于被影响的读数 ⇒ 不构成事后调参，坑 40）；
    ② 标定工具只加**默认关闭**的参数，加完必须重跑对账、产物除时间戳外与锚逐字节相同；
    ③ **「否决」也是结论，必须落盘留档**，否则下一个人会把同一个守卫再实现一遍。

51. **统计/格式化辅助函数不做类型门 ⇒ 少写一个 `len()` 就在真产物上崩，而自测全绿**：
    `code/mg_verdict_s5_1.py` 的 `kk(k, n)` 里有一处写成 `kk(len(p4_s5["rescued_of_fired"]), p4_s5["fired_on_fail"])`
    （漏了第二个 `len()`）⇒ `rate()` 拿到 list，`k / n` 抛 `TypeError`。**32 项自测全绿**却在 4 个 rep 跑完、
    判定该落盘的那一刻崩掉（`logs/chain_s5_1.log` 尾部）——因为自测只覆盖纯函数的正常路径，
    而 `kk` 当时是 `main()` 里的闭包，根本没法被自测摸到。
    更危险的变体：如果 `n` 恰好是 numpy 标量或 bool，`k / n` **不报错、只给错数字**。
    ⇒ 房规：① 这类辅助函数提到模块级并**第一行就做类型门**（`isinstance(x, int)` 且显式排除 `bool`，
    因为 `True` 是 `int` 的子类）；② 自测必须包含**传错类型**的用例（现在 `frac_str` 有 8 项，40 项全绿）；
    ③ 判定脚本在真产物上跑一次「预演」比自测更能抓这类 bug——但预演的 `--out` 必须指到 `runs/` 外面
    （本次用 `/tmp/`，缺料时脚本干净 FATAL 且不写文件，已验）。

52. **机理门的常数不许来自桩件（stub）时间线**：
    `runs/S5_1_PREREG.md` 的 M4 门写「认输局片段中位 ≤110（阶梯理论值 96 步）」，那个 96 来自
    `mg_expert_resume_selftest.py` 的 `BlockedDescendEnv` 桩：`restage1@26 / restage2@61 / give_up@96`。
    桩件里 restage 之后的 `approach` 是**瞬时**的；真环境每次 restage 都要走完「升回 `PRE_HEIGHT` →
    重新对准 xy → 再下降」一整轮 ⇒ 实测认输延迟 **191 / 208 / 271 步**（中位 208），M4 必挂。
    桩件能证「逻辑阶梯按顺序发生」，**不能证「多少步」**。
    ⇒ 房规：以步数/时长为单位的门，常数只能来自 ① 真环境的确定性跑（G1/`mg_ceiling.py` 那种钉死噪声流的配置）
    或 ② 已落盘的实测分布；桩件只用于自测逻辑分支。写预注册时要问一句「这个数是桩件给的还是真环境给的」。

53. **发车前先算「干预的因果足迹」，足迹太小的读数在数学上不可能显著**：
    档 5.1 的预注册估「阶梯可及的收益面 ≈ 12 格死循环」，**默认阶梯能覆盖全部死循环**；
    但同一批标定产物里 trace 侧已经写着只触发 **2/6** 段（`runs/s5_1_stall_calib_trace`）。
    实测下来足迹是 **3/80 格**（其中只有 1 格结局被改变）⇒ 净收益 −2 里能归因给改动的最多 −1 格，
    其余全是坑 39 的采样噪声（逐 rep 净收益 +2/−4/+3/−3，σ ≈ 3.5 格）。
    而功效表（预注册第六节）要求 **净 ≥ +8** 才可能 p<0.05 ⇒ 这 30 min GPU + 一次判定**在发车前就能算出不可能出结论**。
    ⇒ 房规：干预类读数发车前必须落一张「足迹表」：
    `覆盖率的实测值（不是假设值）× 可及格数 × 历史救回率 = 期望净收益`，
    与功效表的检出下限比一比；**小于下限就不跑**，先修覆盖率或换杠杆。
    本次的足迹表事后补在 `runs/s5_2_handback_ceiling/handback_ceiling.md`（可救 0/31、原则上上界 14/31、
    期望净 ≈ +4 < 检出下限 +8）。

54. **同一个工具对「示范」和「策略」用了两套事件定义 ⇒ 造出假结论**（`code/mg_diag_miss.py`，档 6 实测）：
    它给示范定「合爪时刻」用 `close_transition()`（先张开 width>0.070 再合上 width<0.055），
    给策略却用「首次 `width < W_EMPTY=0.020`」。可**策略夹住 can 时 width=0.0417~0.050，永远到不了 0.020**
    ⇒ 那个时刻只能是**后来某次空合**（实测 t=114~213，臂早已离开 can），于是 `dxy_at_close` 被打成 **5~40 cm**，
    看起来「策略横向比专家差一个数量级」。换回同口径后真值是：专家 0.60 cm、策略成功局 0.4 cm、
    策略失败局 1.7~4.4 cm —— 差 3~7 倍，不是 10~60 倍，**处方完全不同**。
    ⇒ 房规：跨对象（示范 / 策略 / 专家）比较的量，**事件定义必须是同一个函数**，且要 import 而不是各写一份。
    新工具 `code/mg_geom_taxonomy.py`（自测 **65** 项）就是为此而生：合爪口径 import 自 `mg_diag_miss`，
    A/B/C 口径 import 自 `mg_tax_fail`，一个都不重写。

55. **注释里的机理常数会传抄走样，而且传抄错的那份被当成了实验依据**（档 6 实测，差点白烧 10 h GPU）：
    `code/mg_expert.py:59` 写「单侧指隙 ≈ (0.0805−0.066)/2 ≈ 7 mm」，并由它推出「指隙 7 mm < `XY_TOL` 8 mm
    = 几何矛盾」；档 5.1 的 descend 停滞机理、以及上一会话已获用户接受的下一步
    （「收紧专家对准判据 → 重采 180 条示范 → 重训 ~10 h」）都建立在这个 7 mm 上。
    真环境实测（`code/mg_probe_grasp_geom.py`，自测 **11** 项 → `runs/s6_grasp_geom/geometry.md`）：
    can 直径 **50.17 mm**（geom AABB 2×0.02509）、全开 **79.36 mm** ⇒ 单侧指隙 **14.59 mm = 1.82× 容差**，
    **矛盾根本不成立**；而那个 0.066 的真身是**手掌碰撞盒 x 向全宽 63.11 mm**
    （`gripper0_right_hand_collision` size[0]=0.031554）—— 把「手掌宽」当成了「can 粗」。
    同一份实测还钉掉第二个传抄错：`mg_diag_miss.CAN_TOP_Z=0.9206` 用的是 `mg_env.CAN_HALF_HEIGHT=0.0603`，
    但实测支撑面 z=**0.8196**、can 半高 **0.0407** ⇒ 真顶面 **0.9010**（偏高 19.6 mm）。
    两个参数化都给出静置中心 0.8603（0.82+0.0403 = 0.80+0.0603）⇒ **只有「顶面」会露馅**，
    这就是它能长期潜伏的原因。
    ⇒ 房规（坑 52 的延伸）：机理常数不许来自桩件，**也不许来自注释**；必须有一份
    「从真环境测出来、带出处、可重跑」的落盘产物（本次 = `runs/s6_grasp_geom/geometry.{md,json}`）。
    ⚠️ 两处代码**都没改**：`CAN_TOP_Z` 一改历史 `_diag/miss_*.json` 就不可比（口径不能中途变），
    `mg_expert.py` 被 G1 回归锚引用（连注释都不动最安全）。真值以探针产物为准。

56. **`增益 = 1 + 斜率` 只有在 x/y 同长度单位时才成立**（`code/mg_geom_taxonomy.py`，档 6 实测）：
    回归 `dx_at_close = a + b·can_x` 时 `can_x` 是**米**（0.14~0.20）、`dx_at_close_cm` 是**厘米**
    ⇒ b 的单位是 cm/m，数值比无量纲值大 **100 倍**，`G = 1 + b` 直接算出 **−28.5** 这种荒谬值
    （真值 **0.705**）。荒谬到反而容易发现；但如果 x/y 只差 1000 倍里的一个 10 倍，就会**安静地**给出
    一个看起来合理的错数（坑 48 是同一类病）。
    ⇒ 房规：任何「1 + 斜率」「比值」「相减」式的派生量，先问一句两边的单位；工具里把换算写在
    **进入回归之前**的一行上，并配一条自测钉子（本次：混单位必须复现 −30 cm/m、同单位必须给 0.7）。

57. **单 run 的配方比较，在 ±20 pp 的 run 间方差下数学上不可能检出小效应**（档 6 结论推导）：
    档 3r 三个 seed 用**同一份数据、同一套超参、等 epoch**，反向放宽口径 = 41.2% / 68.8% / **80.0%**
    ⇒ 极差 **38.8 pp**、sd ≈ 20 pp。而「数据量」这条杠杆的历史证据只有 +15 pp
    （档 2 联合 1:1 的 30/80 → 档 2e 2:1 的 42/80，**Fisher p=0.0801 不显著**，且配比同时变了）。
    换句话说：**换一个配方重训一次 = 换一次随机数**，seed 标签并不能控制任何东西（数据一变，优化轨迹全变）。
    要在 ±20 pp 的方差里检出 +10 pp 的效应，需要每臂 **4~6 个 run**（≈60~90 h GPU），
    「加一倍数据、训一个 seed、比一次」这种设计**在发车前就能算出不会出结论**（同坑 53 的足迹表逻辑）。
    ⇒ 房规：配方类实验（加数据 / 改超参 / 改配比）发车前必须先报「run 间方差」与「每臂 run 数」，
    n=1 的配方比较只能当**探索**、不能当判定；要判定就先把方差本身压下去（更大 batch / 早筛 seed / 多 seed 集成）。

58. **`loss`/`grdn`/`updt_s` 都是 AverageMeter，窗长 = `log_freq` ⇒ 历史训练日志根本测不出「逐步」量**：
    出处 `lerobot/scripts/lerobot_train.py:376-381`。历史 run 是 `log_freq=100`、`batch=8`
    ⇒ 日志里每个 `grdn` 已经是 **800 样本的平均**，逐步噪声被抹平了。想测梯度噪声必须
    `--log_freq=1`（档 7A-2 就是这么做的，测出 η₈ = **54.19%**）。
    ⇒ 房规：**换 batch 时必须按 `log_freq = 800/batch` 重设**，否则两条 run 的 CV 窗长不同、
    数字不可比（bs32 ⇒ log_freq=25，档 7B 已这么发）。任何「从日志算方差/CV」的分析，
    先把窗长（样本数）写在报告里，再写数字。

59. **崩掉那个 seed 的训练 loss 反而最低最平滑 ⇒ BC loss 在最优附近是简并的，日志里没有早筛信号**：
    档 3r 三个 seed 同数据同超参等 epoch，末点 loss = 0.0290 / **0.0280（崩掉的 seed2000，最低）** / 0.0270，
    相差只有 7%；grdn 残差 sd（扣掉共同收敛趋势后）= 0.0711 / **0.0578（seed2000，最小）** / 0.0842
    ⇒ **最平滑的那条曲线对应最差的闭环成功率（41.2% vs 80.0%）**。
    两条后果：① 不存在零 GPU 的坏 seed 早筛，筛必须花 GPU 跑 val rollout；
    ② 「loss 收敛了」≠「行为对了」——loss ≈ 0.028 对应一族行为差别极大的策略，
    这也解释了为什么「加数据（降 loss）」这条杠杆的效应那么弱（+15 pp、p=0.0801）。
    ⇒ 房规：任何「用训练曲线预测闭环成功率」的想法，先做这个对照（好/坏 run 的 loss 画像有没有分开），
    分不开就别把它写进方案当省钱的办法。

60. **换 batch 会连带换掉 `--steps`（等 epoch）与 LR 调度；调度形状其实守恒，但 lr 必须自己改**：
    ① `lerobot/optim/schedulers.py:99-104` 在 `steps < scheduler_decay_steps(30000)` 时**自动缩放**：
    `actual_warmup = int(warmup × steps/30000)`、`actual_decay = steps`。真日志锚
    （`runs/pi05_mix60f120r_s3r_seed3000/train.log`）：`Scaling warmup: 200 → 146, decay: 30000 → 22000`。
    实测 steps = 2750/5500/11000/22000 时 warmup 占全程都是 **0.654~0.664%**（= 200/30000），
    余弦也都在最后一步落到 `decay_lr` ⇒ **按训练进度分数看，LR 调度形状守恒，不是混淆项**
    （这条推翻了「抬 steps 会 LR 重启」的顾虑，但只对**新起 run** 成立；`--resume` 改 steps 仍会换调度总长）。
    ② 但 **Adam 的每步位移量级 ≈ lr，与梯度尺度无关** ⇒ 等 epoch 下步数少 4× 而 lr 不变，
    总位移就少 ~4×，会**系统性欠拟合**。所以换 batch 必须同时改 lr（档 7B 用 sqrt 缩放：8→32 ⇒ 1e-4→**2e-4**；
    线性缩放 4e-4 对 3B 基座太激进）。
    ⇒ 房规：等 epoch 换 batch 时，`steps / save_freq / log_freq / lr` 四个量**一起算、一起写进启动器**，
    并留一个欠拟合哨兵（档 7 的 M3：末点 loss ≤ 1.5× 基线）；不许只改 batch。

61. **同一个仓里两个 Fisher 精确检验的签名不同（2×2 表 vs `(k1,n1,k2,n2)`），混用会得到一个看起来合理的错 p**：
    `code/mg_seedcurve.fisher2(a,b,c,d)` 收 2×2 表（行=组、列=成功/失败）；
    `code/mg_verdict_s2.fisher_two_sided(a,n1,b,n2)` 收「成功数, 局数, 成功数, 局数」。
    把 `(11,9,3,17)` 喂给后者 = 在算「11/9 局 vs 3/17 局」，p 值完全错但量级看着正常。
    本次是在自测里被钉子抓到的（`mg_verdict_s7.py --selftest` 有一条「两套实现必须给出同一个 p」）。
    ⇒ 房规：跨模块复用统计函数时，**先写一条自测把两套实现在同一个输入上对齐**（同坑 54/56 的家族）；
    签名不同的同义函数，注释里把参数含义写在 def 的紧邻上一行。

62. **看门狗的「完成产物」必须把「合法地决定不做」也算成终态，否则一次预注册分支能把报警文件淹掉**：
    `code/chain_watchdog.sh` 的三态是 RUNNING / DONE(产物在) / MISSING(进程没了且产物也没有 ⇒ 报警)。
    档 7C 是**条件发车**链（`runs/S7_PREREG.md` §3：7B 的 M1∧M2∧M3 全过才发）：闸不过时它写
    `runs/s7c.SKIPPED` 再 exit 0 —— 这是预注册写好的分支，**不是静默死亡**。
    但原实现只认 `runs/s7c.done`，于是一次合法的「不发车」会换来每 10 min 一条 MISSING **假警**、
    一直刷到上限；报警文件一旦混进假警，「响就必须有人看」这条价值就没了（真警被淹掉）。
    ⇒ 修法：产物判定加兜底 `[ -f "${art%.done}.SKIPPED" ]` 也算 DONE；同时把 `MAX_TICKS` 从 288 抬到 400
    （48 h → 66.7 h）。⚠️ 更正：7C 的正确 ETA 是 **2026-10-04 ~16:40**（= 看门狗重启后 25.8 h），
    48 h 本来就够；抬上限的真实理由是**给一次重跑留余量**，不是「否则会在收尾前瞎掉」——
    原来那句话是把 17.4 h 从 10-03 23:00 加成了 10-05（坑 55 的形状：常数/日期传抄走样），在此更正留痕。
    ⇒ 房规：**条件发车链必须写一个终态产物（done 或 SKIPPED），看门狗两个都认**；
    但 SKIPPED 只能由链自己写、看门狗不许猜（否则就退化成坑 22(e) 那个「起过不等于还在等」的反面）。

63. **关门评测传给 `mg_eval.py` 的 ckpt 路径必须写「数字格」，写 `last` 会让判定工具的出身核对判「不采信」**：
    `code/mg_eval.py:113` 是 `ckpt = Path(args.ckpt)`（**不 resolve**），`:229` 原样写进
    `eval_summary.json` 的 `policy_ckpt` ⇒ 传 `checkpoints/last/pretrained_model` 就记成 `…/last/…`。
    档 7F 起 `code/mg_verdict_s7f.py` 的 `prov()` 按**尾串**断言（F1/F2 要 `checkpoints/018000/pretrained_model`、
    F3/F4 要 `…/005500/…`、7G 要 `…/018000/…`），尾串不对 ⇒ 报告标 🚫、**退出码 3**、发车链 `die`
    ⇒ 22 h 的读数被判「不采信」，而权重其实是对的（`last` 就是终点格）。
    档 3r/7B 的历史 TEST 都是用 `last` 评的（`mg_verdict_s7.py` 的核对不比尾串，所以当时没暴露）。
    ⇒ 修法（已钉进 `chain_s7f.sh` / `chain_s7g.sh`）：**先按坑 38 核对 `readlink checkpoints/last == %06d(STEPS)`，
    再用数字格路径评测** —— 两道守卫都留着，且判定工具读得到正确出身。
    ⇒ 房规：**「判定工具断言什么」与「链传什么」是同一个契约的两侧**，改任一侧都要同步改另一侧并跑 `--selftest`；
    新档的评测路径一律写数字格（`last` 只用于人工临时看一眼）。

64. **预注册里的资源门槛（显存/磁盘/墙钟）必须从探针的实测表里复制，凭记忆写会写出一个「放行即 OOM」的守卫**：
    `runs/S7F_PREREG.md` §7 第 7 条写「GPU free ≥ 20000 MiB（F3、7G 的 bs8 训练）」，
    但**同一句**引用的实测峰值是 **33799 MiB**（bs8+grad-ckpt，出处 `runs/s7_probe/timing.md`）
    ⇒ 20000 的守卫会放行一个必然 OOM 的显存状态，而它长得像「已经检查过了」。
    ⇒ 修法：`chain_s7f.sh` / `chain_s7g.sh` 按实测峰值取 **bs8 ≥36000 / bs32 ≥45000 / 评测 ≥9000 MiB**，
    并在脚本头注明与预注册正文的差异（资源守卫不是科学判据 ⇒ 不回改预注册正文，坑 40）。
    ⇒ 房规：预注册里的**每一个数字**都要带出处；资源类数字直接从探针表**复制粘贴**，不重新敲（坑 55 家族：常数传抄走样）。

65. **自测的期望值必须由被测函数的定义独立算出来，并且专门测边界；这次是「期望写错、代码是对的」，而发车闸调 `--selftest` ⇒ 一条错期望能把 12 h 的链堵死**：
    `mg_verdict_s7f.py` 的无差别带是 `|Δ| ≤ 11.0 pp`（预注册的 2σ），而自测里两条都写成
    `diff_branch(22, 80, 13, 80, …) == "SAME"` —— 22/80−13/80 = **11.25 pp > 11.0** ⇒ 代码正确返回 `HIGHER`，
    自测报 34 passed / **2 failed**。第二条的名字甚至还写着「11.25 pp 仍算 SAME（… ⇒ 边界外）」，自相矛盾。
    因为 `chain_s7f.sh` 的闸 6 是 `--selftest` 全绿，这两条错期望会直接 `die` ⇒ 整档不发车（**假警堵真活**，坑 62 的镜像）。
    ⇒ 修法：一条改成带内值（21/80 ⇒ 10.0 pp ⇒ `SAME`）、一条改成带外值（22/80 ⇒ 11.25 pp ⇒ `HIGHER`），
    期望旁边把**算式**写进用例名，重跑 **36/36**。
    ⇒ 房规：写阈值类自测时，**至少各一条落在带的内侧、外侧、和（若可构造）正好压线**，
    用例名里带上算式（`10.0 pp ≤ 11 ⇒ SAME`），这样错的是哪一侧一眼可见。

66. **n=20 的 val 曲线「形态」不能用来选 epoch 预算（坑 27/42 的第三次复现，这次是在一个新用途上）**：
    档 7F 的起点是「三条 batch8 的 11 格 val 曲线里两条在 epoch 3.102 见峰后回落」（里程碑 41 的 ④），
    据此差点把训练预算改成 3.102 ep 并花 **22.4 h** 做 7G 前瞻验证。F1/F2 把同一批检查点放到
    **n=80 的 TEST seed** 上复核：三个 seed 在 `018000` vs 末点 `022000` 的差 = **−2.5 / +2.5 / −1.3 pp**、
    Fisher p = **0.87 / 0.87 / 1.00** ⇒ **那个「峰后回落」的形态根本不存在**（val 每格 n=20 ⇒ 1σ≈11 pp，
    「回落 −10/−20 pp」正好落在 1~2σ 里）。若照着 val 改预算，会得到一个与末点**统计上不可分**的检查点，
    还会把「早停」误当成一条真杠杆写进后续所有处方。
    坑 27（val n=10 选不出点）与坑 42（val 选点在 TEST 上反序）当时只写成「不许在 val 上**挑检查点**」，
    **没覆盖「不许用 val 曲线的形态推训练长度」** ⇒ 同一条统计事实以第三种形态又咬了一次。
    ⇒ 修法：`code/chain_s7g.sh` 的触发闸**不读 val 曲线**，只 grep `runs/_diag/s7f_trigger_interim.md`
    里那行机器可读的 `7G_TRIGGER=`（由 `code/mg_verdict_s7f.py --mode f` 在 n=80 TEST 上算）；本轮实测 `NO`。
    ⇒ 房规：**val 曲线只当趋势图**（看有没有崩、有没有学起来）；任何要写进处方的数字
    （训练预算 / 选点 / 早停）都必须先在 **n≥80 的 TEST** 上复核，且复核**先落盘预注册再跑**（坑 40）。

67. **夹爪语义是反的，而契约函数里那句自然语言描述是错的**：
    实测 **+1 = 闭合、−1 = 张开**（`code/mg_expert.py:75` 的 `GRIP_CLOSE = +1.0`，动作第 7 维直接透传给
    robosuite 的 gripper 命令）；但 `code/mg_env.py` 的 `contract()` 返回的字典里写着
    `"gripper_semantics": "-1 = close"` —— **这句是错的**（`mg_env.py` 是冻结文件 ⇒ 按房规**只记不改**，出处钉在这条坑里）。
    档 8 采集器的 stub 预演第一版照 contract 写了 `−1` ⇒ 爪子全程张开 ⇒
    `code/mg_calib_detector.py` 的 T1（`W_EMPTY=0.02` / `N_EMPTY=3`：夹爪宽度连续 3 帧低于空爪阈值 = 「已合爪」）
    **永不触发** ⇒ 两局各白烧 800 步，报告上呈现为「接管率 0% / 产出率 0」这种
    **长得像真读数的假读数**（差一步就被当成「脚本专家接不上手 ⇒ 档 8 不可行」写进判定）。
    ⇒ 修法：`code/mg_collect_corr.py` 里**引用常数、不写字面量**（`from mg_expert import GRIP_CLOSE`、
    `from mg_calib_detector import W_EMPTY, N_EMPTY, HOLD_LO, HOLD_HI, N_HOLD`），并且发车前必须跑一次
    **能逼出触发的 stub 预演**（`--stub-policy gripper_close`，零 GPU、3 s/局）：
    如果在「必然该触发」的桩下检测器都不触发，那一定是语义/常数错，**不是**策略或专家的问题。
    ⇒ 房规：**契约文件里的自然语言不是真理源，代码里的常数才是**；新链路引用动作/状态常数一律 `import`
    （坑 55 家族：常数传抄走样），且任何依赖「检测器会触发」的链路，预演要用一个**必然触发**的桩去证伪。

68. **lerobot v3.0 的读写口径不对称 + 空数据集会去连 HF，两者都会把真读数埋进堆栈**：
    (a) **图像口径不对称**：`LeRobotDataset` 回读给的是 `(3,H,W) float32 ∈[0,1]`，而 `add_frame()` 只收
    `(H,W,3) uint8` ⇒ 把回读的帧直接透传进新数据集会 `ValueError`（写「复制 + 追加」建集时必踩）。
    修法 = 加 `to_hwc_uint8()` 逆变换；且**不能只看不报错就算过**：0..255 全值域可逆性写了自测，
    合并后再用「合并集第 `fr0+i` 帧 == 纠正集第 `i` 帧」的**逐比特抽查**兜底（预演抽查 61 帧 × 5 字段全等）。
    (b) **零收下时回读会去连 hub**：一帧都没收下 ⇒ 数据集没有 `meta/tasks.parquet` ⇒
    `LeRobotDataset(...)` 转头去 HF 拉元数据，而本仓是 `HF_HUB_OFFLINE=1` ⇒
    抛出来的是一堆网络/hub 堆栈，把「产出率 = 0」这个**唯一有价值的读数**盖住；
    且留下的空目录会让下次 `--append` 撞上半个数据集。
    修法 = 回读自证**先判有没有帧**；零收下就不走回读、并 `shutil.rmtree` 掉新建的空目录
    （沙箱拒绝 `rm -f` ⇒ 删除一律走 python）。
    ⇒ 房规：**跨库读写必须写「回读自证」**（写进去什么、读出来逐比特是什么），且回读路径要先处理
    「写了 0 条」这个边界；离线环境里每一处 `LeRobotDataset(...)` 都要先问「元数据齐不齐、不齐它会不会去连网」。

69. **门的分辨率必须匹配它的样本量：A2 在 ~35 个接管上判「≥40%」，1σ≈8 pp ⇒ 一次「不过」分不开 32% 与 40%**：
    档 8 的格 8A 用 **80 局**标定产出率，其中接管局约 **35** 个（好 seed 语料实测接管率 43.8%；坏 seed 会更高 ⇒ n≈35~50），
    而 A2 的门是「接管局放宽成功率 **≥40%**」。n=35 的二项 **1σ ≈ 8.1 pp** ⇒
    真值 40% 时约**一半**概率测到 <40%（假 HELD）、真值 32% 时约**一成**概率测到 ≥40%（假放行）。
    与坑 27/42/66 同族，但**形状更隐蔽**：那几条是「用小样本挑最大值」（有选择偏差），
    这条是「用小样本判一个固定阈值」（**没有**选择偏差，但功效不足 ⇒ 闸变成随机器）。
    这次是在 8A 真跑之前用**事前预测**发现的（`code/mg_forecast_s8a.py` ⇒ `runs/_diag/s8a_yield_forecast.md`、
    `runs/S8_PREREG.md` §9 增补 6）：A2 的三个点估计（35.7% / 15.2% / 17.0%）全部低于门 ⇒ 大概率 HELD。
    ⇒ 处置：**门不改**（改门必须人显式批准并留档，坑 40），而是把功效警告与
    「一次 HELD 只能读成『n=80 局的标定分不开 32% 与 40%』」写进预注册，并**事前**写好 HELD 的三条处置路线，
    免得半夜把一次噪声当定论、或反过来把一次真信号当噪声放过去。
    ⇒ 房规：**每道门在预注册时就要算它自己的 1σ**（`阈值 ± 1σ` 能不能把处方关心的两个值分开）；
    分不开 ⇒ 要么把样本抬到能分辨的量级，要么把这道门**降级成「只透明、不拦路」的诊断量**，
    不要留一道分辨率不够的拦路闸 —— 它会以「看起来客观」的方式**随机**决定整条链走不走。

70. **坑 44 的房规原来只覆盖「策略前向」，其实「渲染」也要它：本仓的 offscreen 渲染跨进程不确定
    （~71% 的帧差 1~2 灰阶），而这条路径上一个神经网络都没有 ⇒ 不能归因给 cuDNN**：
    给采集器加 `descend_diag()` 后验「对数据集零影响」，图像 parquet 的 sha256 对不上 ⇒ 差点判成回归。
    真相是**同一版代码连跑两遍也对不上**：old↔old2 有 **702/986** 张解码后像素不等（最大差 **2** 灰阶、
    PNG 字节 ~55% 不等），old↔new 是 **698/986**（最大差 **2**）⇒ 量级与分布同阶，不是改动引入的。
    判别「渲染噪声 vs 物理发散」的关键读数：像素差**不随帧号增长**（帧 0/40/…/480 的最大差恒为 0~1），
    而 `observation.state` / `action` / 5 个索引列**逐比特相等**，`meta/stats.json` 只有两个图像键的
    `mean/std` 差 **~5e-9（相对）**、`min/max/q01/q10` 完全相同 ⇒ 渲染器级浮点非确定性，物理与轨迹是确定的。
    ⚠️ 与坑 44 的关系：**同族、同修法，但不同机理**。坑 44 是 π₀.₅ 的 bf16 GPU 前向（cuDNN/cuBLAS 按当时时序挑算法）；
    本次三跑全是 `--stub-policy gripper_close`（**不加载任何策略、不做任何推理**）⇒ 坑 44 的解释在这里不成立。
    环境是 `MUJOCO_GL=egl`（`code/env.sh`）⇒ 图像在 GPU 上离屏渲染；**机理未定位**（候选：EGL/NVIDIA 驱动的浮点归约顺序、
    或并发占卡时的设备/上下文选择 —— 三跑都在 F3 评测 / F4 训练占卡时进行，故不能排除并发相关）。
    量级上无害：±2/255 ≈ **0.8%** 灰阶，且**原始 180 条示范也带同样的噪声**（同一渲染路径）⇒ 不改变数据的语义尺度。
    ⇒ 正确口径 = **结构量全等 + `state`/`action` 逐比特 + 图像差落在「同版本两遍」的噪声地板内**。
    ⇒ 房规（把坑 44 的那条**推广**到所有产物，不只 GPU 推理）：**任何「改动前后对比」都必须配一次「改动前 vs 改动前」的地板**，
    否则分不清信号与噪声；方法学出处就是 `code/mg_g0a_equiv.py` 的 G0a-2「噪声地板对照」。
    拿「图像 sha256 相等」当门会把**零影响**的改动误判成回归（本次差点就误判 ⇒ 会白白回滚一个有用的诊断）。
    ⚠️ 既有判定一条不受影响：merge 的 B2 / 逐比特门比的是**同一次运行内**的复制保真
    （合并集第 `fr0+i` 帧 == 纠正集第 `i` 帧）与「原有负载 sha256 不变」（建集走复制、不重编码）⇒ 都在进程内，确定性成立。
    （出处 `runs/_diag/diagchk/VERDICT.md`、`runs/S8_PREREG.md` §9 增补 7；同族：坑 44（GPU 前向）、坑 39（成功率不可复现）、
    坑 52（机理门的常数不许来自桩件时间线））
71. **离线重建真值之前必须先证明「你当成常量的那个量真的没变」，而且要用**逻辑对撞**、不是数值核对**：
    为了给档 8 事前定病因，用盘上的 `rollout_actions.npz` 离线重算专家的 `xy_err/z_err`：
    `state[:,0:3]` 是专家当时看到的 eef（`mg_eval_harness.py:183` 存的是 `env.step()` **之前**的 obs），
    can 初态由 seed 决定 ⇒ 20 次 `env.reset(seed)` 就能重建。数值核对**漂亮地过了**：
    重建的 `can_z0` 与每局记录里的 `can_z0` 差 **1.11e-16**（机器精度）。
    于是第一版结论很自信：「**75% 的失败接管是卡在 `approach`、xy 从未对准**」—— 而这条是**错的**。
    抓住它的是**逻辑对撞**：记录的相位串里有 `descend`，而进入 descend 的**前提**是对**当时的真 can** 满足过
    `xy_ok`（`code/mg_expert.py:186,221`）⇒「相位串含 descend」与「按初态重建出 xy 从未对准」**不能同时为真**
    ⇒ 唯一解释是 **can 在接管之前就被策略撞走/夹起又掉了**（15/20 局中招，个别 `xy_err` 达 **667 mm**；
    独立佐证 `max_lift_cm` 12~20 cm）。而 `can_z0` 的数值核对**查不出这件事**：它只核对**reset 那一刻**，
    物体在那之后动没动，它一个字都不说。
    ⇒ 房规：**任何「把某个量当常量」的离线重建，都要配一条跨两个独立记录的蕴含式核对**
    （A 记录 ⇒ B 必须成立；B 不成立 ⇒ A 的前提被破坏）。只核对初值 = 只证明了「起点找对了」，
    没证明「过程中没变」。查不出来就必须**把效度门写进工具、把不合格的样本剔出统计**，
    而不是把结论照发（`code/mg_diag_nograsp.py` 的 `RX_can_moved` 就是这道门）。
    ⇒ 连带后果：盘上的 npz **没有逐步 can 位姿** ⇒ 这条离线路线到此为止，只能**检测**不能**修正**；
    能修正的只有采集器（每步读**当时**的 `env.object_pos`，见坑 72 / §9 增补 7）。
    （出处 `runs/_diag/nograsp_corpus.md`、`runs/S8_PREREG.md` §9 增补 8；同族：坑 45「可行性预检的接管前状态
    必须采样自被测策略」—— 都是「拿错了参照物」，只是一个错在采样来源、一个错在时点）

72. **检测器只看本体感觉 ⇒ 它会在一个「已经赢下」的局上触发接管**（有界，但要记）：
    接管检测器故意只用 `state[:,7] = gripper_width`（`runs/_diag/harness_calib.md`，不碰 can 位姿真值），
    所以「can 已经送进框、正在等那 10 步落定」的窗口里爪子是空的 ⇒ 检测器照样触发。
    语料实证：`s5_1_handback_rev_test20_k10_rep3/7010`（接管@240、放宽成功@257、专家只走 18 步、
    `min_dist_to_target_xy` = 19.7 mm）⇒ 这种局会**同时**进 A2 的分子、又只贡献十几帧垃圾。
    ⇒ **量级算过了**：语料 1/35 接管 ≈ 2.9%；A2 的门是 40%、在 ~35 个接管上 **1σ≈8.1 pp**（坑 69）
    ⇒ 影响 ≈ **1 pp，比门的分辨率小一个量级** ⇒ **不改任何门、也不再动采集器**（距链发车 8 h，
    再改一次就要再走一遍坑 70 那套零影响验证，风险 > 收益）。留档 + 让 8A 的 `seg_len` 分布自然暴露它。
    （`code/mg_harness.py:88` 的 `latch_success()` 已保证放宽成功**之后**不再触发 ⇒ 窗口只有落定那 10 步，**有界**。）
    ⇒ **10-04 17:25 复测（重放台 drive2；两个总体 × 三种口径，出处 `runs/_diag/s9_rescue/FINDINGS.md` §六 / §9 增补 10）**：
    「xy 已在框内」这个**宽口径**混了两种局 —— 真·「已赢、只差落定」（段长 **18/19** 步）与「已进框但被撞倒/斜」
    （段长 **105~187** 步、其中 2 局倾角 **90.0°**、专家还得走一百多步）。按 **段长 ≤30** 分开后：
    真·已赢 = 好 seed **1/35 = 2.9%**（与上面那个数**一致**）、坏 seed 池化 **8/175 = 4.6%**、`022000` **1/16 = 6.2%**；
    宽口径 = 2/35、12/175 = 6.9%、2/16 = **12.5%**。A2 三口径（原 → 剔真·已赢 → 剔宽口径）：
    `022000` **68.8% → 66.7% → 64.3%**、主组 **62.3% → 60.5% → 59.5%** ⇒ **门 A2 不是坑 72 的假象**；
    真·已赢贡献的可用帧只占 **0.8%（主组）/ 1.6%（`022000`）** ⇒ 对 A1 可忽略。
    ⚠️ 但上面那句「只贡献十几帧」在 `022000` 上要按**宽口径**读成 **205 帧 = 18.2%**，其中 187 帧来自侧躺在框内的那一局
    ⇒ 那是**合法的难状态**、不是污染。**结论不变：不改任何门、不动采集器**（量级现在被夹住了）。

73. **「更差的政策 ⇒ 更难的纠正数据」是直觉、不是测量；而且盘上已有录像时，先问「能不能重放」再建模**：
    增补 6 用**好 seed 1000** 的接管语料（`runs/s5_1_handback_*`）预测 8A 的 A2，给了 L 22.9% / M 35.7% /
    U 42.9% + 靶子校正 17.0%，结论「三个点估计全低于门 40% ⇒ 大概率写 `s8a.HELD`」，并自己标注了一条偏差：
    「8A 跑的是坏 seed 2000、状态可能更难 ⇒ 本预测对 A2 **偏乐观**」。用 CPU-only 重放台直接实测后，
    **这条偏差的方向判反了**：
    * 同一份好 seed 语料、horizon 抬到采集口径 800、换成采集器的 `hand_back=False` ⇒ A2 = **12/35 = 34.3%**
      [20.8, 50.8] ⇒ 与模型 **M 的 35.7% 几乎重合** ⇒ **模型的算术没错**。
    * 坏 seed 2000（8A 的真靶子）在 val 窗口 11 格 / 220 局 / **175 个接管**上 ⇒ A2 = **109/175 = 62.3%**
      [54.9, 69.1]；单看 8A 用的 `022000` ⇒ **11/16 = 68.8%** [44.4, 85.8]（**Wilson 下界就已过门**）
      ⇒ 预测**偏悲观 28 pp**，三门全过。
    * 机理（接管瞬间的 can **真值**，逐步取自重放 ⇒ 不需要增补 8 那道效度门）：两组初态倾角都是 **0.00°**
      ⇒ `TILT`（>10°）都是**局内被撞倒的**。构成：坏 seed **CLEAN 53.7% / MOVED 20.6% / TILT 25.7%**，
      好 seed **CLEAN 8.6% / MOVED 25.7% / TILT 65.7%**；分类 A2：CLEAN **72.3%** / MOVED 63.9% / TILT **40.0%**
      （好 seed 的 TILT 只有 **21.7%**）。⇒ **策略越强，留下的接管状态越难**：好策略真去抓、抓起来又掉 ⇒ can 倒地；
      差策略在 can 上方空挥、根本没碰着它 ⇒ can 还立着。而专家的抓取几何假定 can 立着。
    ⇒ 房规两条：
    ① **跨策略外推产出率时，偏差方向必须测、不许推**。「参照物更难/更容易」这类判断，得先有参照物自己的读数
       才许写进预测的偏差项（同族：坑 45「接管前状态必须采样自被测策略」、坑 71「把某量当常量」——
       三条都是**拿错了参照物**，只是错的维度不同：采样来源 / 时点 / 策略强弱）。
    ② **盘上已有 `(state, action)` 录像时，先问「能不能重放」再建模**：`env.reset(seed)` 钉住全部随机源、
       物理与渲染尺寸无关 ⇒ 重放**逐比特**复现（**300 局 `max|Δ| = 0.0e+00`**），于是「零 GPU、当晚、在真物理上」
       就能量到本来要排队等 GPU 的读数。重放台还过了三条外部对账（接管步 **18/18**、接管局数 **35 vs 35**、
       纯重放放宽成功 **14/20 = 70.0%** 与 `eval_summary.json` 逐字相同）⇒ 它量的是**同一条 harness 语义的实测**，不是模型。
       ⚠️ 但重放台只能吃**评测窗口**的录像 ⇒ 必须避开 D1 的 TEST 窗口 **7000..7019**（拿它定专家的修法 = 用 TEST 调参）；
       `code/mg_s9_rescue.py` 对此有**硬闸**：`--runs` 指到 TEST 窗口直接拒绝执行，除非显式 `--allow-test-window`
       （给了就在产物里打 🚨`TEST_WINDOW_CONTAMINATION`，且只许用于验证工具本身）。
    ⚠️ 本坑**不改任何门**：A2 仍是 40%、8A 仍按预注册跑；改的只是「事前预测」这一份文档的结论。
    （出处 `runs/_diag/s9_rescue/FINDINGS.md`、`runs/S8_PREREG.md` §9 增补 9；里程碑 46）

74. **「相对初态的位移阈值」在「物体本来就要走远路」的任务里 ≠「被扰动」；而且诊断读数的总体必须与下游真正要用的那一个一致**：
    重放台给接管状态分的三类里，`MOVED` 的判据是「can 相对**初态**水平位移 > 10 mm」（`code/mg_s9_rescue.py:67`）。
    可反向任务里 can 本来就要走 **≈700 mm** 进目标框 ⇒ 这个类**同时**装进了「刚被碰了一下」
    （`022000` ep1：`dxy` = **0.011** m、接管@77）和「已经送到框里、只差落定」（ep0：`dxy` = **0.698** m、接管@264、18 步完成）
    ⇒ 它**不是**难度标签，别拿它当「策略把物体弄乱了」的证据。
    同一份文档里还有一处更承重的**总体错误**：`frames_by_state_class` 的**池化 11 格**读数
    （CLEAN 70.9% / MOVED 18.4% / TILT 10.8%）被当成了「8B 那份数据教的是什么」，而 8A/8B **只从 `022000` 采集**
    ⇒ 正确总体是 `022000`：**CLEAN 0 帧 / MOVED 726（64.5%）/ TILT 399（35.5%）**。两者差到会把结论讲反：
    池化说「TILT 只占一成」，真靶子上 TILT 占**三成半**、CLEAN **一帧都没有**；档 9 的第 1 优先级（侧躺几何）
    在正确总体上更强 —— `022000` 的 TILT 占接管 **8/16 = 50%**（不是 25.7%）、且 **6/8** 段被过滤 3（>300 步）砍掉
    ⇒ 修它同时抬 **A2 与 A1 的产出率**（做得快 ⇒ 段长落进 ≤300 ⇒ 帧也收得下）。
    ⇒ 房规两条：① 阈值要**按任务的行程尺度**归一，或改用「相对目标 / 相对当前相位」的量 ——
    「相对初态 > ε」只在物体本该待在原位的任务里才等于「被扰动」；② **诊断读数的总体必须与下游动作的总体一致**
    （采集用哪条检查点，构成就按那条算）。同族：坑 57（n=1 不做高低比较）、坑 71（把某量当常量）、
    坑 73（拿错参照物外推）—— 这是「拿错总体/参照物」的又一种形状。
    ⚠️ 本坑**不改任何门**（A1/A2/A3 都不用 `state_class`），只改诊断文档的口径；渲染器已加 **assert**
    （重算的 A2 分子 / A1 帧数必须与工具自己存的字段相等，不等就崩，不许印错数）。
    （出处 `runs/_diag/s9_rescue/FINDINGS.md` §五/§六/§八、`runs/S8_PREREG.md` §9 增补 10；里程碑 47）

75. **清理循环里的 `pgrep -f '<pattern>'` 会匹配到**自己这条命令**⇒ 把自己的 wrapper 杀掉（坑 22(a) 的自伤版）**：
    2026-10-05 20:47 发车 8D 后按坑 37 的房规「`pgrep -af` 数命中、多出来的按 PID 杀掉」写了一个 for 循环，
    循环体里的判据是 `case "$cmd" in "bash code/chain_s8d.sh") 保留;; *) kill -9 $p;; esac`；
    而**这个循环自己的命令行里就含有 `code/chain_s8d\.sh`** ⇒ `pgrep` 把它也捞出来、`case` 判成「不是真链」⇒
    `kill -9` 打在自己身上，整条命令 **exit 137**、后半段（复查、日志核对）**一行都没跑**。
    幸运的是真链已经是 session leader（`SID==PID`、`STAT=Ss`），没被连带杀掉；但如果顺序反过来
    （先杀父再判子），或者真链还没 `setsid` 成功，这一下就是一条 20 h 的链。
    ⇒ 房规三条：① **模式里用字符类打断自匹配**（`pgrep -af 'chain_s8[d]\.sh'`）—— 这条命令自己的 cmdline
    含的是 `chain_s8[d]\.sh`，**匹配不上**这个正则；② 杀之前**必须**先 `ps -o pid,ppid,sid,stat` 核目标
    `SID==PID`（是 session leader 才说明 `setsid` 生效、杀 wrapper 不连带），并且**只杀 cmdline 与真链逐字不同的**；
    ③ 清理循环**不要**和发车写在同一条命令里（坑 37 ③ 的同一家族：一次只干一件事）。
    同族：坑 22(a)（`pgrep -f` 匹配到自己造成一次性误报）、坑 37（wrapper 造成**假健康**）——
    本坑是第三种形状：**自伤**。（出处 `logs/chain_s8d.log`、里程碑 48）

76. **把一条共用链脚本「参数化」时，`bash -n` 抓不到语义错；必须做「默认值逐字复现归档产物」的冒烟对账**：
    为了用同一条 `code/chain_s8mech.sh` 跑 8D 的两个新臂，给它加了 `TAG/TITLE/CTL_DESC/...` 等 8 个可覆盖变量。
    改末尾那行 `printf` 时把续行拆断了（`"$TAG"` 单独一行、后面 `"$(date ...)" ... > "$MARK"` 变成**另一条命令**）——
    **`bash -n` 照样通过**（语法合法），跑起来只会写一个空的/错的 done 标记，正是坑 43 的形状。
    靠的是「改完把尾部 8 行打出来看一眼」才发现。
    ⇒ 房规：① 改共用脚本后，除了 `bash -n`，必须**用默认参数重出一次已归档的产物**并 `diff`
    （本次：`RESCUE=0 FID=0` + 复制一份 `runs/_diag/s8_mech/{rescue,fid}` 到临时目录 ⇒ 重出的 `COMPARE.md`
    与归档版**只差有意新增的那一行**，其余逐字相同；临时目录用 python `shutil.rmtree` 清掉）；
    ② 复制既有产物目录做冒烟时**别把 `*.done` 一起复制**——链开头「认产物就退出」，会直接早退、什么都没测到
    （本次第一遍就吃到了：只复制 `rescue/`+`fid/` 才跑通）；
    ③ 参数化之后，脚本里**写死的旧文案**（如等待行的 `echo "等 8C 的 11 格 ..."`）会变成误导，
    而实例一旦发车就**不许再编辑**（坑 22(d)）⇒ 要么在参数化时一并把这些文案也参数化，
    要么就地更正留痕（本次选了后者，见 `runs/S8_PREREG.md` §9 增补 12 §4）。
    同族：坑 43（done 标记写空）、坑 22(d)（不编辑运行中的 .sh）、坑 55（引用走样要就地更正留痕）。
    （出处 `code/chain_s8mech.sh.bak_pre_s8d`、里程碑 48）

77. **自测里断言「盘上进度」= 定时炸弹：主链一收工，旁链的发车闸就自杀**：
    `code/mg_prov_s8d.py` 的旧版自测里有一条断言「8D 的 TEST 产物**还没**落盘」（当时是真的），
    等 8D 干净收工、产物齐了 ⇒ 自测反而 **2 条失败**；而按房规每条链的发车闸都要先跑 `--selftest`
    ⇒ 旁链**按纪律自杀**、D4 的出身核对根本没跑成（`runs/s8d_prov.FAILED`）。
    形状与坑 65（期望值写错）不同：这次**期望和代码都没错，错的是把「环境状态」当成了不变量**。
    ⇒ 房规：① 自测的输入一律用**合成夹具**（`tempfile` + 现造 json），或只断言**与盘上进度无关**的不变量
    （如「`missing + 已核 == 应有读数`」「缺产物的目录不许再出现在出身问题里」）；
    ② 需要真盘对照的核对**不进自测**，另开 `--mode check` 之类的显式入口；
    ③ 新工具落盘时就问一句「这条断言在**主链收工之后**还成立吗」。
    本档遵守情况：`mg_eval_zlim` / `mg_zlim_replay` / `mg_s9a_lift` / `mg_s9b_gain` / `mg_verdict_s9b` / `mg_verdict_s9c`
    的自测**全部**是合成夹具（`mg_verdict_s9b` 的 z1–z7 现造 Z0b json、r6–r9 现造 sidecar）。
    同族：坑 65（期望值必须由定义独立算出）、坑 40③（缺字段≠0）。
    （出处 `code/mg_prov_s8d.py:186-196`、`runs/s8d_prov.FAILED`、里程碑 49）

78. **在飞的看门狗不许编辑 ⇒ 新链天然落在监控盲区里，这个缺口必须显式记账、由链自己的终态标记兜住**：
    `code/chain_watchdog.sh` 的清单是**写死在脚本里**的，而它一旦发车就属于「在飞的 .sh」（坑 22(d)：不编辑），
    改清单只能 `kill` 再重启（还会把 tick 编号搞乱）。于是档 9 的两条新链（`chain_s9b.sh`、`chain_s9c.sh`）
    **都不在清单里** ⇒ 静默死亡不会被自动报警（正是坑 22(e) 那次事故的形状）。
    ⇒ 房规：① 新链**必须**自带三态终态标记（`<档>.done` / `.FAILED` / `.SKIPPED`，`printf` 写 + `[ -s ]` 自检，坑 43），
    让「有没有收工」随时可从盘上判定，不依赖进程表；② 预注册里**显式写明**「本链不进看门狗清单，由人工巡检覆盖」
    （`runs/S9_PREREG.md` §6 第 4 条、增补 4 ③）；③ 巡检的最小动作 = `ls -la runs/s9*.??*` + `tail logs/chain_s9*.log`；
    ④ 只有当**看门狗本身已收工**（tick 到上限、进程消失）时才允许改清单重启，别为了加一条而打断在飞的监控。
    同族：坑 22(d)（不编辑在飞的 .sh）、坑 22(e)（认产物不认进程表）、坑 37（setsid + 核 SID==PID）。
    （出处 `runs/S9_PREREG.md:187`、`code/chain_s9c.sh` 头注、里程碑 49）

79. **`OSC_POSE` 的 `dz` 是速度级/阻抗级指令，不是位置级 ⇒「把 `dz` 置 0」≠「保持高度」，末端会滑行 4~6 cm**：
    档 9B 的原设计（can 抬升超 cap 就把 `dz` 夹到 0）在冒烟局里**看着生效了**（sidecar `n_clamped_total=24`、`max|Δdz|=0.065`），
    但那一局 `max_lift_cm` 仍冲到 **18.52 cm**（cap 12.87）、末倾角 89.95°（侧躺）。纯 CPU 重放定位（保真 `max|Δeef_z|=5.96e-08`）：
    在「已超 cap 却仍在上升」的 **25 步**里，`dz>0` **0 步**、`dz==0`（被夹）3 步、**`dz<0`（在命令下降）22 步**，
    而这 25 步的 `Δeef_z` **全部 > 0** ⇒ **不是 can 在夹爪里滑移，是末端自己在滑行**。
    量化（400 局 TEST 的 npz，零 GPU，`runs/_diag/s9_tax/coast_400.json`）：「最后一次 `dz>0.3` 之后末端还多升了」
    中位 **3.77 cm**、p75 4.82、**p90 5.87**、最大 13.31 ⇒ 要靠提前量补就得把触发线压到 `cap − 5.87 ≈ 5.9 cm`，
    而搬运本身需要 ~11.5 cm 升程（示范中位）⇒ **被动限位与完成任务在几何上不相容**，原设计当场判死。
    ⇒ 房规：任何「夹住/置零某一维动作」的干预，**发车前必须先量该维的制动距离**（用盘上 npz 重放，零 GPU、2 分钟），
    并把它与任务本身需要的行程比一比；控制器增益 `KP` 要有事前依据（本档 `KP=0.5 /cm` 来自实测「`dz=−0.4` ⇒ 每步消除 ~0.5 cm/步 的上升速度」），
    而且**只许用本体感觉**（`eef_z`、夹爪宽度都在 state 里），不许读仿真特权真值（`env.object_pos`）——否则不可部署。
    同族：坑 81（本坑的定量版）、坑 14（K 与执行口径）、`code/mg_env.py` 的动作有效增益 11.1 mm/控制步。
    （出处 `runs/S9_PREREG.md` 增补 1 ①、`runs/_diag/s9_tax/{coast_400,pop_probe24}.json`、里程碑 49）

80. **`$?` 会被同一条命令里的 `$(...)` 命令替换覆盖 ⇒ 写出一个假的 `RC=0`**：
    档 9B 的 v1 可行性台这样记退出码：`printf '%s %s\n' "$(date '+%F %T')" "$?" > logs/z0b_v1.rc`。
    shell 先展开**所有**命令替换再执行 `printf` ⇒ `$(date)` 成功 ⇒ `$?` 已经是 **date 的 0**，不是被记的那条命令的退出码。
    于是 `Z0B_RC=0` 是**假的**（真值 RC=1）。这次没造成错结论，因为门槛的真理源是 json 里的 `gate.pass=false`，
    但同一条写法若用在链脚本的 `die` 判据上，就是一次**静默放行**（比坑 43 的「写空标记」更难发现：标记内容看起来完全正常）。
    ⇒ 房规：① **先 `rc=$?` 存变量，再做任何 `$(...)`**（`code/chain_s9c.sh` 的 `verdict_out`/`train_arm` 已照此写）；
    ② 判定用的退出码**不许**与时间戳/日志前缀写在同一条命令里；③ 真值优先取**产物内的结构化字段**（`gate.pass`），
    退出码只作交叉核对。同族：坑 43（done 标记写空）、坑 22(e)（认产物不认进程表）、坑 30（出处打进日志）。
    （出处 `runs/S9_PREREG.md` 增补 3 ⑤3、`logs/z0b_v1.rc` vs `runs/_diag/s9_tax/z0b_v1_ceilhold.json`、里程碑 49）

81. **动作过滤器/安全外壳发车前必须先量「单步最大位移 + 制动距离」：peak-hold 类设计对**弹射局**物理不可达**：
    坑 79 量的是「被动置零」的滑行；档 9B 的 v2 换成了**主动**终点预测式节流（`dz = clip(min(dz_policy, (cap − rise − safety·inflight)/(safety·k)), −1, 1)`，
    常数由公式定：脉冲响应 `b=[0.4093,0.6105,0.1768,0.1015]`、`k=1.2981`、上升保真比 1.138、**制动保真比 0.680**
    ⇒ `safety = max(1.138, 1/0.680) = 1.4702`、`k_eff = Σb × safety = 1.9085`；76230 搬运步、R²=0.739，**零 GPU**）。
    结果仍然 **0/12**（加限位后 13.50~14.83 cm vs 门线 13.15），val 确认台 3/12。逐步 trace 给出了死因：
    `t=159` 策略 `dz=+0.70` ⇒ 末端**单步 +3.65 cm**（K=10 的一个执行步里积分出来的位移）；
    `t=171–175` 策略 dz 已 ≤−0.02、限位器输出**饱和**在 −0.81~−0.91（最大刹车），末端**仍在 4 步里涨 +3.45 cm**
    ⇒ 越界不是「策略想抬高」，而是**接触/动量把末端弹上去**；任何只改 `dz` 的外壳都只能在弹射**之后**刹车 ⇒ 必然过冲。
    ⇒ 房规：① 任何「按住某个量」的外壳，**立项时**就要算清「单步最大位移」与「饱和制动距离」，
    并把它们与门的容差（本档 cap+1.0 cm）比一比——**容差 < 单步位移 ⇒ 这个设计不用跑就已判死**；
    ② 门的可行性要有**前置闸**（本档的 Z0b：纯 CPU 重放台，≥11/12 局按得住才许上 GPU），
    并把「最多几次重设计」**事前写死**（增补 3 ④：2 次），用尽就停、不许为过闸而改 cap/tol/need/N/样本；
    ③ 前置闸要有一个**独立确认台**（本档 Z0b′ 换 val 窗口），因为动力学常数是在 TEST 上量的（坑 27/42）；
    ④ 若成因是接触/动量，处方不在动作层，而在**教材几何 / 释放时机 / 接受并打标**（本项目的现行放宽判据已把侧躺送达算成功并打 `delivered_tipped`）。
    收益：这条纪律让 9B 的**总 GPU 消耗 ≈ 0 h**（预注册原估 3.1 h），并把一个「看起来很便宜的部署侧补丁」干净地判死。
    同族：坑 79（dz 滑行）、坑 40（预注册先落盘、看完数不许改门）、坑 27/42（选点/调参不许用门数据）。
    （出处 `runs/_diag/s9_tax/{dz_gain_400,z0b_v1_ceilhold,z0b_feasibility,z0b_feasibility_val}.json`、`runs/S9_PREREG.md` 增补 3/4、`runs/S9B_VERDICT.md`、里程碑 49）

82. **夹爪指令的符号不许引注释，必须从数据实测——`code/mg_env.py` 自己的注释就自相矛盾**：
    同一个文件里，第 11 行写「`[6]` 夹爪 −1 = 闭合，+1 = 张开（robosuite 约定）」、第 305 行的元数据写
    `"gripper_semantics": "-1 = close, +1 = open"`；而第 66/68 行的**实测标注**是
    `GRIP_OPEN_WIDTH = 0.0788 # action=-1 张开到底`、`GRIP_EMPTY_CLOSE = 0.0010 # action=+1 空合到底` ⇒ **两处相反**。
    一手实测（`code/mg_bclass_grip.py::grip_sign_probe`，专家 120 集）：在「宽度真的动了」（|Δwidth|>2e-4）的 **3729** 步里，
    `sign(act) == sign(Δwidth)` 只占 **3.27%** ⇒ **+1 = 闭合、−1 = 张开**（第 66/68 行对，第 11/305 行错）。
    分箱佐证：张开段（width>0.07）act 中位 **−1.000**、夹住段 act 中位 **+1.000**／均值 **+0.858**。
    这次差点写错方向：诊断初稿据此声称「B 组的闭合指令**更强**」，而实际 B 的 `act_mean` 中位 **+0.7785 低于** OK 的 **+0.8875**，
    整条因果话术是反的（已在 `grip_mech_400.md` §六② 就地推翻）。
    ⇒ 房规：① 任何用到 `action[:,6]` 的分析，**开工第一件事**是实测符号（`sign(act)` vs `sign(Δ宽度)` 的一致率），
    并把统计量**写进产物**（本工具写进报告头 + json 的 `sign` 字段）；② 与注释冲突时**以数据为准**，
    冻结文件的注释**不改**（`mg_env*.py` 只 import/调用），冲突登记到本坑；③ 工具里加**符号守卫**：实测结果 ≠ 假定值时
    往 stderr 吼一条 WARN，提醒人工复核方向性措辞，不许静默出错。
    同族：坑 6（gripper 语义）、坑 54（同一个量不重写第二遍）、坑 40③（缺值不猜）。
    （出处 `code/mg_env.py:11,66-68,305`、`code/mg_bclass_grip.py::grip_sign_probe`、`runs/_diag/s9_tax/grip_mech_400.json` 的 `sign`、里程碑 50）

83. **`max_lift_cm`（can 抬升）不能当「已抓住」的判据；0/1 双峰混合要用「发生率 + 比例检验」，中位数差会把 p 打歪**：
    档 9A 的分类尺子（`code/mg_tax_fail.py`）拿 `max_lift_cm ≥ 5 cm` 判「抓起了」，于是有了「B = 抓起了却没送到」这个桶，
    并在 `runs/_diag/s9_tax/SUMMARY.md` 里被写成「真失败的最大单一桶（52%/62%）」。一手复核（TEST 窗 400 局）：
    B 组 69 局里 **31 局（44.9%）搬运期最小开口 < `GRIP_HOLD_WIDTH=0.012`**（`w_min` 中位 **0.00316 m** ≈ 空合到底 0.001）
    ⇒ **指间从头到尾没有罐**，而它们的 can 抬升中位仍有 **12.9 cm** —— 罐是被**接触弹射**顶起来的（与 9B 同一机理）。
    直接量化那个代理：B 组里 `max_lift_cm ≥ 8 cm` 的 54 局，**23 局（42.6%）是空合**。
    ⇒ 「B」里 **~45% 实属 A 族（没夹住）**、**~55% 才是真放置失败**（占全体 **9.5%**，38/400）。
    **统计量的坑（同一批数据上暴露的）**：`w_min` 是**双峰混合**（≈0.049 夹住 / ≈0.003 空合），中位数落在哪一峰完全由混合比例决定 ⇒
    val 窗 `w_min` 的中位数差 **p=0.0531（不显著）**，而同一批数据的**空合发生率**差 B 27.6% vs OK 11.3%（+16.3 pp）方向一致；
    test 窗上两者都显著但幅度差一个量级（中位差 −0.0218 vs 发生率差 +39.6 pp）。用错统计量 ⇒ 结论随窗口翻转。
    ⇒ 房规：① 「夹住没有」用 **`w_min ≥ GRIP_HOLD_WIDTH`**（`mg_env` 的物理常数、**专家假阳 0/120**），不用 can 抬升；
    ② 分组变量是 0/1 时，统计量用**发生率差 + 比例置换检验**（`rate_perm_test`），不许用中位数差；
    ③ **统计型**阈值（如 `W_LOSS` = 专家自己的 p05）**自带假阳地板**（实测逐集 **16.7%**），报告必须把地板印出来、读者要**减地板**再读
    （B 84.1% / OK 40.6% 减掉 16.7% 才是 +67.4 pp / +23.9 pp；「OK 组 40% 中途丢罐」这种说法是错的）；
    ④ 归因标签 ≠ 成功判据：OK 组也有 14/261（5.4%）空合却照样送达 ⇒ 空合的阳性预测值只有 **66%**，必须配合成败一起读；
    ⑤ 已归档的逐臂计数**不追改**，只改解释 + 给可复算的替代判据（`SUMMARY.md` §⓪ 就地更正留痕）。
    同族：坑 33（跨数据集/窗口只比方向不比高低）、坑 40③（缺值不当 0）、坑 81④（成因是接触 ⇒ 处方不在动作层）。
    （出处 `runs/_diag/s9_tax/grip_mech_400.{md,json}`、`grip_mech_val.{md,json}`、`runs/_diag/s9_tax/SUMMARY.md` §⓪、里程碑 50）

84. **分类口径里「蕴含关系」的判定顺序错了，会造出一张**结构性恒空**的表——而且它长得像正常输出、不报错**：
    `delivered_tipped`（侧躺送达）**蕴含**放宽成功。诊断初稿这样分组：
    `cls = "OK" if (grasped and relax) else ("A" if not grasped else ("TIP" if tipped else "B"))`
    ⇒ 侧躺局一律先被 `grasped and relax` 吞进 **OK**，**TIP 组恒为 0**，于是「TIP vs OK」那张表整张全是 `—`，
    看上去像「样本太小不判」（工具还专门有 `n<5 ⇒ 不判` 的合法分支），**没有任何报错**。
    而它同时破坏了与已公布口径的一致性：修好后 TEST 窗 400 局 = **OK 261 / TIP 69 / B 69 / A 1**，
    与档 9A 独立工具（`mg_s9a_lift.py`）公布的「立着送达 261、侧躺送达 69、放宽也失败 70」**逐位吻合**（B 69 + A 1 = 70）。
    ⇒ 房规：① 分类逻辑**抽成纯函数**（`classify(grasped, relax, tipped)`）并用合成夹具自测四条分支，别埋在 I/O 循环里；
    ② 加**分组一致性不变量**（`invariant_cls`：夹住的侧躺局必须全在 TIP）并纳入**非零退出码**，让恒空表当场炸出来；
    ③ 新工具的分组**必须与已公布口径逐位对账**——两条独立实现给出同一组计数，是比自测更强的正确性证据；
    ④ 「整张表都是 —」不是可接受的终态，要么补样本、要么改口径，不许当作「没结论」轻轻放过。
    同族：坑 77（自测用合成夹具）、坑 40③（缺字段≠0）、坑 43（标记非空自检）。
    （出处 `code/mg_bclass_grip.py::classify` + 自测 k1–k3 + `invariant_cls`、`runs/_diag/s9_tax/grip_mech_400.md` §一、里程碑 50）

85. **「按事件切窗」的跨组比较必带删失偏差：整窗上「显著」的差，在等长前缀窗上会全部消失**：
    搬运段窗口 = [首次合到 `GRASP_THR` 以下, 其后首次张过 `RELEASE_THR`]。**罐一丢，释放阈值就再也达不到** ⇒
    窗口一路截到 `len(width)-1`。实测搬运步数中位：**专家 174 / OK 189 / B 107** ⇒ B 的窗口天然短 43%，
    且多出来的部分是**丢罐之后**的行为。于是整窗读数给出「B 组加速度显著更大（+0.00194，p=0.0001）、闭合指令显著不同（−0.1088，p=0.0001）」，
    而换成**等长同相位前缀窗**（搬运段前 `K_MATCH=40` 步，两组都取得到；不够长的局整条记 nan 并排除，不当 0）后：
    `m_act_mean` **p=0.4965**、`m_spd_p95` **p=0.9721**、`m_acc_p95` **p=0.8652** ⇒ **三项全部不显著**，
    即 B 与 OK 在夹爪指令与运动学上**不可区分**。原来那些「显著」全是窗口长度差与后果。
    **事件时刻也要用绝对步数**：`loss_after_frac = (t_loss − tg)/(tr − tg)` 的分母 `tr` 本身被截断 ⇒ 会骗人；
    改用 `loss_after_steps = t_loss − tg` 才看到真相：**B 的中位丢罐时刻 = 夹住后第 1 步**（p25=1、p75=2、≤10 步占 91%；
    对照专家假阳局的中位 = 第 164 步、OK = 第 78 步）⇒ 不是「搬运途中掉了」，是「闭合那一刻就没夹上」。
    ⇒ 房规：① 任何按事件切的窗，**必须同时报窗口长度差**与**等长前缀窗**的对照，只有后者能定量；
    ② 事件时刻一律用**绝对步数**，分母含被截断量的比值不许进结论；
    ③ 若等长窗**仍跨过事件时刻**（本例 40 步窗 ≫ 第 1 步丢罐），则窗内该事件的量只能读作**后果**、不是前兆；
    ④ 「整窗显著 / 匹配窗不显著」这个组合本身就是结论：**事前不可预测** ⇒ 任何「事前过滤/限速/限力」类干预都按不住它（与坑 79/81 同源）。
    同族：坑 79（dz 滑行）、坑 81（制动距离）、坑 33（只比方向）、坑 40③（缺值不当 0）。
    （出处 `runs/_diag/s9_tax/grip_mech_400.md` §二·补/§一·补、`code/mg_bclass_grip.py::ep_metrics` 的 `m_*`/`loss_after_steps`、里程碑 50）

86. **判定工具的打印路径里 `n=0` 有两种意思；`{k}/{n or EPS}` 这种兜底会把「缺读」印成「真 0/20」**：
    档 10 的 E5 行（正向护栏，只读）初稿写的是 `f"{fwd50[sd]['k']}/{fwd50[sd]['n'] or EPS}"`，
    目的是防 `n=0` 时打印难看。但 `n=0` 有两个**完全不同**的来源：**跑了 20 局、0 成功**（真读数，必须如实印 `0/20`）
    与**产物根本不在**（缺读，必须印 `—`）。兜底把两者印成同一个 `0/20` ⇒ 空跑（还没有任何 K=50 产物）时，
    报告看起来像「三臂正向全 0/20」，而 E5 的结论恰恰是「三臂全 0 ⇒ K=50 只在反向可用」——
    一个**只读护栏行**会在数据缺席时自动「得出结论」。同一次空跑里，`K=50 缺产物` 的计数也只统计了反向 12 个、
    漏了正向 3 个（写死 `15` 的自测断言才把它抓出来）。
    ⇒ 房规：① 计数一律走**一个**函数 `fmt_kn(c)`（`n<=0` ⇒ `—`，否则 `k/n`），不许在 f-string 里就地兜底；
    ② 「缺产物/缺字段」的清单必须覆盖**本档所有**目录（反向 + 正向），不许只列主口径那半边；
    ③ 自测里必须有一个场景是**产物全缺**，并断言全文**不出现** `0/20`（`code/mg_verdict_s10.py::selftest` 场景 C）。
    同族：坑 40③（缺值不当 0）、坑 84（结构性恒空表长得像正常输出）。
    （出处 `code/mg_verdict_s10.py::fmt_kn`/`report`、自测场景 C，2026-10-07 空跑）
87. **判定工具的 f-string 嵌套：同引号嵌同引号会 `SyntaxError`，而用 `chr()` 拼 key「绕过」它 = 把语法错换成静默错**：
    `f"...{e1['min_k']}..."`（单引号外壳）里再嵌 `f"{e1['min_k']}"` ⇒ `ast.parse` 报 `f-string: unmatched '['`。
    本轮**同一个错犯了两次**，第二次的「修法」是 `e1[chr(109)+chr(105)+chr(110)+chr(95)+chr(107)]`——
    它能过 parser，但把一句人话变成了没人能复核的表达式，且**只有跑到那一行才会暴露**（判定工具是夜里跑的）。
    ⇒ 房规：① 判定工具里的 f-string 一律**双引号外壳 + 单引号字典访问**（`f"...{e1['min_k']}..."`）；
    ② 需要「先判空再格式化」的，**先算局部变量**再插值（`e1_txt = "—" if ... else f"..."`），不许三层嵌套；
    ③ **禁止** `chr()`/字符串拼接绕语法错——绕得过 parser 绕不过复核；
    ④ 任何判定工具落盘后立刻 `python -c "import ast;ast.parse(open(f).read())"` + `--selftest`，
    两步都绿才算写完（`chain_s10.sh` 闸 5 把 `--selftest` 做成了**发车前硬闸**）。
    同族：坑 65（判据代码里不留没被测过的表达式）、坑 80（`rc=$?` 先存再用）。
    （出处 `code/mg_verdict_s10.py` E1 行、`logs/verdict_s10_selftest.log`，2026-10-07）
88. **拿「空收集器」当 `.get()` 的兜底默认值，会让不变量检查**恒为空转**——它不报错，还长得像通过**：
    档 11 判定初稿写的是 `by_code.get(code, {}).get(arm, collect([], ""))["broken"]`，本意是「这一格没读到就给个空结果」。
    但 `collect([])` 返回的字典**本来就带** `broken`/`nofield` 键（全空）⇒ 既不会 `KeyError`，也永远取不到真数据 ⇒
    报告里「不变量『放宽 ⊇ 严格』违例：**0** 条 ✅」「缺字段：**0** 条 ✅」变成**两枚恒真的绿灯**，
    而这两项恰恰是 L4 采信与否的依据（违例 > 0 ⇒ `trust=False` ⇒ 退出码 3）。交接摘要还把它误诊成 `KeyError`——
    误诊的形状值得记：**空转比崩溃更难发现**，因为崩溃会逼你去读代码，空转只会让你相信门是好的。
    ⇒ 房规：① 兜底默认值只许是**中性容器**（`{}` + `.get("broken", [])`），不许是「调用一次真函数拿到的空结果」；
    ② 每条绿灯都必须有一个自测场景能把它**变红**（本档场景 I 用 `strict_override` 造 `relaxed 17 < strict 20`、
    场景 F 用 `legacy=True` 造缺放宽字段，断言计数分别读到 **1**），否则那条灯等于没接电；
    ③ 复核别人的判定工具时，先问「这行如果数据全缺会打印什么」——打印 `0 条 ✅` 的就是嫌疑犯。
    同族：坑 84（结构性恒空表长得像正常输出）、坑 86（`n=0` 的两种意思）、坑 65（不留没被测过的表达式）。
    （出处 `code/mg_verdict_s11.py::report` 的 `broken`/`nofield` 两行 + 自测场景 I/F，2026-10-07）
89. **自测断言用**裸子串**去钉「缺读不许当 0」，会撞上报告自己的阈值文案 ⇒ 假警报，且会把人去改实现**：
    场景 D（产物全缺）里写了 `chk("不许出现 0/60", "0/60" not in out)`，结果**红了**——
    不是实现把缺读印成了 `0/60`，而是 §三 的门文案本身写着「每句 3 臂池化 20×3 = 60 局放宽 ≥ **30/60** = 50%」，
    `30/60` 里含子串 `0/60`。危险不在断言失败本身，而在**它指向的方向是反的**：红灯看着像「实现把缺读当 0 计」，
    很容易去改 `fmt_kn`/`report` 的打印逻辑（把真门改坏），而真正该改的是断言的**锚点**。
    ⇒ 房规：断言「某个读数格不许出现假 0」时，锚到**格的形状**而不是裸数字：
    `"| 0/60 |" not in out`（表格单元两侧有空格与竖线）、`"=0/60" not in out`（机器行 `S11_R1=NA`）、
    再配一条正向锚 `"S11_R1=NA" in out`。阈值文案里的数字与读数格里的数字，**必须能被断言区分开**。
    同族：坑 86（同一个 `0/20` 的两种意思）、坑 40③（缺值不当 0）。
    （出处 `code/mg_verdict_s11.py::selftest` 场景 D，2026-10-07）
90. **bash 两处「起得来但不对」：管道里的 `while` 循环体在子壳（`die` 只退子壳），`cd A && cmd > rel.log &` 的重定向在 `cd` 之前求值**：
    ① 按 TSV 清单发车的循环若写成 `tail -n +2 plan.tsv | while read ...; do one_read ...; done`，
    循环体在**子壳**里 ⇒ `one_read` 里的 `die`（`exit 4`）只结束子壳，父链**继续往下跑**并写出 `done` 标记
    （形状 = 「评测炸了但链报收工」，比不发车坏得多）。⇒ 一律 `done < <(tail -n +2 "$PLAN_TSV")`（进程替换，循环在当前 shell）。
    ② `cd "$MG" && setsid bash code/x.sh > logs/x.log 2>&1 &` 里，重定向由**当前** shell 在 `cd` 生效前展开 ⇒
    相对路径落到别处或直接 `No such file or directory`（本轮哨兵就这么没起来一次，而链起来了 ⇒ 看着像「都发成功了」）。
    ⇒ 发车一律用**绝对路径**重定向；发完立刻 `ps -o pid,ppid,sid,pgid,cmd -p <PID>` 核 `SID==PID==PGID` 且 `PPID=1`（坑 37），
    并 `cat` 一眼它自己的心跳日志（哨兵第一行 tick=1 就是「真的活着」的证据）。
    同族：坑 37（setsid 核身份）、坑 41（路径全绝对）、坑 75（`pgrep` 用字符类防自匹配）、坑 80（`rc=$?` 先存）。
    （出处 `code/chain_s11.sh` 的 `< <(...)` 循环、`code/chain_s11_sentinel.sh` 发车，2026-10-07 20:39）

## 下一阶段（第 1 步跑通后才动）

1. 多初始位置（`--seed-mode random`，同一套契约与评测口径）；2. 正反向；3. 三个训练 seed；
4. 标准 chunk 执行（`--n-action-steps = chunk_size`）；5. Harness 接管；6. 纠正数据；7. RL 微调；8. 真机。
