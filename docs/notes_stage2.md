# 阶段 2 实测记录：正反向交替 / reset-free，到底省了什么、代价是什么

> 2026-09-22 · 本机（Ubuntu 22.04 / 1×A800 / 共享节点）实测
> 概念解释在 [`notes_stage0.md`](notes_stage0.md)，阶段 1 的结果在 [`notes_stage1.md`](notes_stage1.md)。
> 这一页只写**真跑出来的东西**和**怎么读它**，所有数字都能用文末的命令复现。

---

## 0. 这一阶段要回答的三个问题

ROADMAP 阶段 2 的验收标准是「能回答」下面三句话，所以本页就按它们组织：

| 问题 | 一句话答案（先给结论，证据在后面） |
| --- | --- |
| **Q1 交替是否更快/更省？** | 省。省下的复位数 = **成功完成的任务数**（每个成功任务省掉一次人工复位）。策略越可靠，省得越多：可靠策略下 0 次复位 vs 2727 次，含复位成本的吞吐 181 vs 27 任务/千步（6.8×）。 |
| **Q2 代价是什么？** | 起始状态多样性可能塌缩，但**塌缩不是交替本身造成的**，而是「策略不可靠」+「救场时把物体摆回固定点」两个条件叠加的结果。策略处处可靠时，交替的起始覆盖是满格 36/36、熵 0.994，与人工复位无差别。 |
| **Q3 两者都失败时谁复位？** | 规则式救场：连续 `stall_limit=120` 步没有任何任务完成 → 把物体按当前方向摆回源区域，并记账 `manual_resets += 1`。随机策略下这一条每 20000 步触发 ~140 次，是系统唯一还在往前跑的原因。 |

**最该记住的一条**：在 reset-free 系统里，「复位策略」（谁复位、复位到哪）不是实现细节，
而是**决定学习分布的设计变量**。同一个交替机制，救场时均匀重采样 → 起始熵 0.937；
救场时摆回固定 home 点 → 起始熵 0.609。差的这一截，就是学习数据多样性的差距。

---

## 1. 环境：`envs/bidirectional_pickplace.py`

和阶段 1 的 Reach 同一个哲学：**先用抽象环境把机制和度量搞清楚，再搬去 robosuite / 真机**。
一个点代表末端，在 30cm×30cm 的桌面上把一个物体在 A 区（左）和 B 区（右）之间来回搬。

| 要素 | 内容 |
| --- | --- |
| **observation** | 7 维 `[末端xy(2), 物体xy(2), 目标xy(2), 是否抓着(±1)]`，全部除以 `half=0.15` 归一化到 [-1,1] |
| **action** | 2 维**末端位移增量**，[-1,1]²，实际位移 = `action × action_scale(0.04)` 米 |
| **一个 task** | 两相：`seek`（空手走到物体 2cm 内 → 抓起）→ `carry`（抓着走到目标 2cm 内 → 放下） |
| **一局（episode）** | 400 步，里面**连续做很多个 task**；一个 task 成功后立刻切方向、采样新目标 |
| **reward** | 每步 `-当前子目标距离`；抓起 `+2`；放下（= 完成一个 task）`+8` |
| **terminated** | 永远 False（这不是「一局一个任务」的环境，靠 truncated 结束） |
| **truncated** | `step_idx >= max_steps(400)` |
| **成功判定** | 环境代码自己判：`carry` 相末端与目标距离 ≤ `place_radius(0.02)` → `success[direction] += 1`。**没有让任何模型来打分**，这是阶段 1 就定下的纪律 |

### 1.1 两种复位模式（本阶段的主角）

```
alternate（reset-free）   task 成功 -> 物体留在放置点 -> 下一个 task 的抓取点就是它
                          零复位成本，但下一轮的起始状态由策略自己上一轮的行为决定（内生）
fixed（人工复位）         task 成功 -> 物体重新均匀采样回源区域 -> 每个 task 付一次复位
                          起始状态由环境决定（外生、均匀），成本 = 任务数
```

代码在 `_advance_task()`：`alternate` 分支什么都不做（物体自然留在原地），
`fixed` 分支 `self.obj = self._sample_in(src)` 并 `fixed_resets += 1`。

### 1.2 规则式救场（Q3 的答案所在）

`step()` 里每步累加 `steps_since_task`，一旦 `>= stall_limit(120)` 就调 `_rule_reset()`：
把物体摆回当前方向应有的源区域、重新采样目标、`manual_resets += 1`。
「摆回哪里」由 `recovery_mode` 决定，这是本阶段新加的对照维度：

| recovery_mode | 救场时把物体放到哪 | 类比真机 |
| --- | --- | --- |
| `resample` | 在源区域里**均匀重采样** | 人手随便把物体丢回桌上某个位置 |
| `home` | 放回该区域的**固定 home 点**（区域中心） | 恢复动作「把物体摆回标定好的固定位」 |

### 1.3 覆盖率：三类分布必须分开记

这是本阶段最重要的一件事，也是最容易搞混的地方。环境用 `grid_n=6` 把桌面切成 36 个 5cm 格子，
分别记录三种分布（`coverage_report()` 一次全给出）：

| 名字 | 记的是什么 | 由谁决定 |
| --- | --- | --- |
| `goal_cell_counts` | 环境**请求**的目标格子 | 环境均匀采样（外生） |
| `start_cell_counts` | 策略**实际经历**的起始格子（每个 task 开始时物体在哪） | `alternate` 下由上一轮放置点决定（**内生**）；`fixed` 下由重采样决定 |
| `pick/place_cell_counts` | 策略**真正做到**的抓取 / 放置格子 | 策略能力 |

配套的还有 `start_sources`：每个起始状态**是谁给的**——
`prev_place`（上一轮放置点）/ `fixed_reset`（人工复位）/ `recovery`（救场）/ `episode_init`（开局）。
有了它，「起始状态多样性从哪来」就不用猜了。

**为什么必须分开记？** 因为只看「请求的目标很均匀」会得出「覆盖没问题」的错误结论。
真正的风险是：目标很均匀，但策略只在一小块地方成功，于是 `alternate` 下
下一轮的出发点全挤在那一小块 —— 学习分布自我收窄，而请求分布完全看不出这件事。

---

## 2. 实验一：对照实验（不需要训练，85 秒出结论）

```bash
python scripts/compare_reset_modes.py --recovery-modes resample,home
# 产出：runs/20260922_205020_stage2_compare/{compare.json,config.json,figures/}
```

**预算严格对齐**：每个 (策略, 模式, 救场, seed) 格子都烧 20000 步、跑 3 个 seed，
一次复位按 `reset_cost_steps=30` 步折算成本。总环境步数 216 万，纯 numpy，85 秒跑完。

### 2.1 为什么先用「写死的脚本策略」而不是先训练

因为这轮要回答的是**机制**问题，不是**算法**问题。脚本策略的可靠度可以精确设定，
于是能把「覆盖塌缩」归因清楚。三种策略构成一条谱（`--policies perfect,biased,random`）：

| 策略 | 实现 | 扮演什么角色 |
| --- | --- | --- |
| `perfect` | 比例控制器 `action = clip((子目标 - 末端)/action_scale, -1, 1)` | 处处可靠的**性能上界参照**，不需要学习 |
| `biased` | 同上，但「请求目标离目标区域中心 > `easy_radius`」时不干活（`--bias-behavior freeze` 停住 / `wander` 随机走） | 只在训练分布中心可靠的**真实策略替身** |
| `random` | 每步均匀随机 | 完全不可靠，逼出「谁兜底复位」 |
| `ckpt` | `--ckpt <model.zip>`，加载训练好的 SAC | 把真策略放进**同一张表**对照 |

`biased` 的舒适区半径 `easy_radius=0.06` m 对应**单区面积的 29%**（脚本用蒙特卡洛算出来并打印）。
默认 `freeze` 而不是 `wander`：随机游走偶尔会蒙对目标，把「策略不会做」的信号冲淡；
`freeze` 是干净的实验仪器，`wander` 更像真机，两个都留了开关。

### 2.2 表 A · 成本与吞吐（回答 Q1）

| policy | mode | recovery | tasks | succ% | fixed_rst | stall_rst | total_rst | steps/task | thr/1k(eff) | tasks/1k(raw) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| perfect | alternate | resample | **3627.3±19.9** | 98.6% | 0 | 0 | **0** | 5.5 | **181.37** | 181.37 |
| perfect | fixed | resample | 2726.7±7.0 | 98.2% | 2727 | 0 | 2727 | 7.3 | 26.78 | 136.33 |
| biased | alternate | resample | 74.7±14.2 | 27.0% | 0 | 150 | **150** | 279.3 | 3.05 | 3.73 |
| biased | fixed | resample | 83.0±15.3 | 29.2% | 83 | 149 | 232 | 250.0 | 3.07 | 4.15 |
| random | alternate | resample | 13.3±2.5 | 6.6% | 0 | 140 | 140 | 1559.5 | 0.55 | 0.67 |
| random | fixed | resample | 13.0±1.4 | 6.4% | 13 | 139 | 152 | 1558.4 | 0.53 | 0.65 |

（`recovery=home` 的行数字几乎一样，完整表在 `compare.json` / 日志里。）

三件该看出来的事：

1. **省下的复位数正好等于成功任务数**。`perfect` 成功 3627 个任务 → `fixed` 就付了 2727 次复位，
   `alternate` 付了 0 次。这不是巧合，是机制：交替用「反向任务」当了复位。
2. **策略不可靠时，交替省不了多少**。`biased`/`random` 两种模式的复位数几乎相同（150 vs 232、140 vs 152），
   因为复位的主力已经从「人工复位」变成了「救场复位」——失败太多，省下的那点人工复位不值钱。
3. **交替还顺带缩短了空行程**：`steps/task` 5.5 vs 7.3。因为交替时物体就停在末端刚放下的位置，
   下一次抓取几乎不用移动；人工复位则把物体扔到随机位置，得重新走过去。
   这是 `tasks/1k(raw)` 181 vs 136 的来源，和复位成本无关，是纯赚的。

> `thr/1k(eff)` = 每千个**含复位成本**的等效步能完成多少任务，`raw` 则不算复位成本。
> 两个都要看：`raw` 反映环境内的执行效率，`eff` 反映真机上的实际产能。
> 本机 `reset_cost_steps=30` 是很**保守**的取值——真机上人工复位要几秒到几十秒，
> 而一个控制周期只有几十毫秒，比值是几百到上千。按真机比值算，交替的优势只会更大。

### 2.3 表 B · 覆盖与分布（回答 Q2）

| policy | mode | recovery | goal_cells | goal_ent | start_cells | start_ent | endo_start% | place_cells |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| perfect | alternate | resample | 36 | 0.992 | **36.0 (100%)** | **0.994** | 99% | 36.0 |
| perfect | fixed | resample | 36 | 0.992 | 36.0 (100%) | 0.991 | 0% | 36.0 |
| biased | alternate | resample | 36 | 0.962 | 35.3 (98%) | 0.937 | 27% | 15.7 |
| biased | fixed | resample | 36 | 0.957 | 36.0 (100%) | 0.964 | 0% | 15.3 |
| biased | alternate | **home** | 36 | 0.963 | **25.0 (69%)** | **0.609** | 27% | 15.3 |
| biased | fixed | **home** | 36 | 0.961 | 33.3 (93%) | 0.690 | 0% | 14.7 |
| random | alternate | home | 30 | 0.872 | 26.3 (73%) | 0.473 | 8% | 11.7 |

`start_ent` = 起始状态分布的归一化熵（1.0 = 完全均匀走遍 36 格，0 = 全挤在一格）。
分母用 `log(36)` 而不是 `log(去过的格子数)`，否则「只去过 2 格但很均匀」也会得 1.0，塌缩就被掩盖了。

四条结论：

1. **请求的目标永远均匀**（`goal_cells` 36、`goal_ent` ≈0.96，两种模式一样）。
   所以只看「任务采样是不是随机的」根本发现不了问题。
2. **策略处处可靠时，交替没有覆盖代价**：`perfect` 的起始覆盖 36/36、熵 0.994，
   而且 99% 的起始状态是自己上一轮造出来的（`endo_start%`）。
   内生 ≠ 塌缩；内生 + 不可靠才塌缩。
3. **策略不可靠 + 救场摆回固定点，才会真塌**：`biased/alternate/home` 起始格子从 33.3 掉到 25.0，
   熵从 0.690 掉到 0.609。机制很直白：策略只在舒适区成功 → 放置点只在舒适区 →
   下一轮的出发点只在舒适区 → 救场又把它摆回固定的 home 点 → 整条链再也走不出去。
4. **`place_cells` 由策略能力决定，与复位模式无关**（`biased` 两种模式都是 ~15 格）。
   复位模式影响的是「它从哪儿出发」，不是「它能做到哪儿」。这两件事要分开说。

### 2.4 表 C · 可靠度扫描（Q2 的因果版）

`--scan-easy-radius` 把 `biased` 的舒适区从 8% 面积扫到 83%，看两条模式怎么分岔
（`recovery=resample`，3 seed × 20000 步）：

| 舒适区面积 | 成功率 | 起始熵 alternate | 起始熵 fixed | 复位 alternate | 复位 fixed | thr/1k alternate | thr/1k fixed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 8% | 5.3% / 6.0% | 0.857 | 0.864 | 150 | 163 | 0.46 | 0.52 |
| 20% | 18.0% / 18.6% | 0.920 | 0.943 | 150 | 196 | 1.80 | 1.77 |
| 39% | 38.7% / 39.5% | 0.947 | 0.978 | 150 | 277 | 5.17 | 4.56 |
| 54% | 52.8% / 52.3% | 0.951 | 0.978 | 145 | 354 | 8.99 | 6.90 |
| 70% | 66.5% / 67.4% | 0.951 | 0.984 | 131 | 494 | 15.04 | 10.52 |
| 83% | 81.3% / 81.2% | 0.976 | 0.988 | **111** | **781** | **30.17** | 15.53 |

（每格是 `alternate / fixed`。`recovery=home` 的同一张表在 `compare.json` 的 `scan` 段里，差距更大。）

这张表把 Q1 和 Q2 合成了一句话：

> **策略越可靠，交替省的复位越多（163→781 次的差距越拉越大）、吞吐优势越大（0.9×→1.9×），
> 而起始熵的差距始终很小（0.007→0.012）。**

也就是说，在 `resample` 救场下，**交替的代价随可靠度上升而消失，收益随可靠度上升而放大**。
反过来，如果救场是 `home`（真机上更常见的「摆回固定位」），低可靠度区间的代价会明显变大
（起始熵 0.554 vs 0.621、起始格子 23.0 vs 32.3）。

**给真机系统的直接推论**：如果打算用 reset-free 交替省人力，就要同时设计救场动作
——让它带一点随机性（或按覆盖统计主动选择复位位置），否则省下的复位费会用「学习分布收窄」还回去。

### 2.5 图

```bash
python scripts/plot_stage2.py --compare runs/20260922_205020_stage2_compare --open
```

| 图 | 看什么 |
| --- | --- |
| `figures/fig_coverage_heatmaps_resample.png` / `_home.png` | 每行一个 (策略, 模式)，三列 = 请求的目标 / 经历的起始 / 做到的放置。`biased`+`home` 那两行中间一列的空白格就是塌缩本身 |
| `figures/fig_reliability_scan.png` | 左：起始熵 vs 成功率（蓝线低于橙线 = 交替的代价）；右：复位数 vs 成功率（蓝线远低于橙线 = 交替的收益） |
| `figures/fig_cost_bars_resample.png` / `_home.png` | 三联条形图：完成任务数 / 付出的复位 / 含成本吞吐 |

---

## 3. 实验二：SAC 训练，两条课程各训一个

```bash
# 交替（reset-free）课程：起始状态由策略自己上一轮的放置点决定
OMP_NUM_THREADS=1 setsid nohup python -u scripts/train_transport.py --mode alternate \
    > /tmp/train_alt.log 2>&1 < /dev/null & disown
# 人工复位课程：每个 task 都重采样起始状态（对照组）
OMP_NUM_THREADS=1 setsid nohup python -u scripts/train_transport.py --mode fixed \
    > /tmp/train_fix.log 2>&1 < /dev/null & disown
```

产出：`runs/20260922_205625_sac_transport_alternate/` 与 `runs/20260922_205625_sac_transport_fixed/`，
每个目录里有 `model_final.zip` / `best_model.zip` / `result.json` / `stage2_eval.jsonl` /
`evaluations_transport.npz` / `figures/`。

**耗时**：60000 步 / 13.5 分钟 / 74 步每秒（本机共享节点当时的 load 比阶段 1 低，
阶段 1 只有 15 步/秒；这类数字随邻居任务波动，别当成代码性能）。
策略网络 `[128,128]`，**89736 个参数**（比阶段 1 Reach 的 24459 大，因为要同时表达
seek/carry 两相 + 目标条件 + 方向切换）。

### 3.1 三段式对比（和阶段 1 同一套纪律：随机 / 未训练网络 / 训练后）

冻结评测：3 个 seed × 20000 步 = 60000 步交互，确定性推理。

| 策略 | 完成任务 | 每任务成功率 | 正/反 | 规则式救场 | 起始格子 | 起始熵 | 吞吐(任务/千等效步) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 随机策略 | 13.3 | 6.6% | 11.3 / 2.0 | 140 | 29.0 | 0.857 | 0.55 |
| 未训练的网络 | 0.0 | 0.0% | 0 / 0 | 150 | 18.0 | 0.788 | 0.00 |
| **训练后（alternate 课程）** | **3637.0** | **98.6%** | **1830 / 1807** | **0** | **36.0 (满格)** | **0.994** | **181.85** |

变的只有 `model_final.zip` 里的 89736 个数字。环境、奖励函数、评测 seed 一个字都没动。

**注意「未训练的网络」比随机策略还差（0 个任务 vs 13.3 个）**：这不是 bug。
随机策略的动作是均匀的，偶尔能撞上；而刚初始化的网络输出的是一个**固定的偏置方向**，
末端会一直往同一个方向顶到边界，比乱走更难碰巧完成任务。阶段 1 也见过同样的现象。

### 3.2 学习曲线：相变发生在 7500–10000 步

训练途中每 2500 步做一次冻结评测（`TransportEvalCallback`，指标与对照实验完全同源）：

| 训练步数 | 完成任务(每 4000 步预算) | 成功率 | 正/反 | 救场 | 起始格子 | 起始熵 |
| --- | --- | --- | --- | --- | --- | --- |
| 2500 | 2.0 | 4.8% | 2 / 0 | 30 | 22.0 | 0.808 |
| 5000 | 8.0 | 16.7% | 8 / 0 | 30 | 24.0 | 0.860 |
| 7500 | 117.0 | 79.6% | 62 / 55 | 20 | 33.0 | 0.927 |
| 10000 | 556.0 | 97.7% | 280 / 276 | 3 | 36.0 | 0.983 |
| 12500 | 712.0 | 98.6% | 359 / 353 | 0 | 36.0 | 0.987 |
| 60000 | 741.0 | 98.7% | 373 / 368 | 0 | 36.0 | 0.989 |

三件值得盯的事：

1. **相变很陡**：5000 步还是 16.7%，7500 步就 79.6%，10000 步 97.7%。和阶段 1 的 Reach 一样，
   这类稀疏 bonuses + 短 horizon 的任务是「突然学会」的，不是线性爬升。
   所以**别用 5000 步的结果判断这个任务学不学得会**。
2. **学会之前只有正向**（2500/5000 步：正 8 / 反 0）。原因是机制性的：
   每局第一个 task 必然是正向，只有正向成功了才会切到反向。
   策略弱的时候根本走不到反向任务，于是**反向数据完全缺失**。
   这是 reset-free 交替的一个真实风险：偏科会自我强化。7500 步之后正向通了，
   反向立刻跟上（62/55），说明这个环境里两个方向共享同一个「走到子目标」的能力。
3. **救场次数是策略强度的敏感指标**：30 → 20 → 3 → 0。策略一强，规则式兜底就完全不触发了。
   真机上这条曲线就是「人类干预率」的替代品，值得一直记着。

### 3.3 训练出来的策略 ≈ 脚本上界

| | 完成任务(3 seed × 20000 步) | 每任务成功率 | 吞吐(任务/千等效步) |
| --- | --- | --- | --- |
| `perfect` 脚本比例控制器（表 A） | 3627.3 | 98.6% | 181.37 |
| **SAC 训练后（alternate）** | **3637.0** | **98.6%** | **181.85** |

SAC 已经把这个环境的**已知上界打平了**（差别在噪声范围内）。
这件事的意义不是「RL 很厉害」，而是：**这个抽象环境已经不够难了**。
下一步要加难度（视觉观测 / 接触物理 / 更长的 horizon / 物体姿态），
否则再训也只是在天花板上磨。

### 3.4 跨模式冻结评测：两条课程学到的是同一个策略

这是本阶段最有意思的一个阴性结果（negative result）。把在一种课程下训出来的策略，
拿到另一种复位模式下评测（同样的 3 seed × 20000 步）：

| 训练课程 | 在自己的课程下 | 在另一种模式下 |
| --- | --- | --- |
| `alternate`（内生起始） | 3637 任务 / 98.6% / 起始熵 0.994 / 复位 0 | `fixed`：2622 任务 / 98.1% / 起始熵 0.991 / 复位 2622 |
| `fixed`（均匀起始） | 2639 任务 / 98.1% / 起始熵 0.991 / 复位 2639 | `alternate`：3550 任务 / 98.6% / 起始熵 0.990 / 复位 0 |

**两条课程收敛到的策略可以互换，掉点都在噪声内**（98.6% vs 98.1%）。
也就是说：在这个环境里，「起始状态分布内生 vs 外生」并没有让策略过拟合到自己的出发分布。
原因很清楚——策略收敛后**处处可靠**，于是内生链条照样走遍 36 格（起始熵 0.994），
和 §2.3 里 `perfect` 脚本策略的行为完全一致。

**但要小心这条结论的适用边界**：它能成立，是因为这个环境里的策略确实做到了处处可靠。
§2.4 的可靠度扫描已经说明，一旦策略只在部分工作空间可靠（真机 + 视觉观测几乎必然如此），
交替的起始分布就会收窄。所以：

> 覆盖率和起始熵必须**一直记着**，不能因为「这次训练没塌」就把指标删掉。
> 它是发现「学会了、但学窄了」的唯一手段，而这件事在成功率曲线上完全看不出来
> （98.6% 的成功率和 0.994 的起始熵可以同时存在，也可以和 0.6 的起始熵共存）。

### 3.5 图与视频

```bash
python scripts/plot_stage2.py --latest --open      # 一次把 compare + train 的图全画了
python scripts/render_transport_video.py --run runs/20260922_205625_sac_transport_alternate
# 看覆盖塌缩（不可靠策略 + 救场摆回固定点）
python scripts/render_transport_video.py --policy biased --easy-radius 0.09 --recovery-mode home \
    --steps 2000 --out runs/20260922_205020_stage2_compare/transport_biased_home.mp4
# 看救场兜底（完全不可靠）
python scripts/render_transport_video.py --policy random --steps 900 \
    --out runs/20260922_205020_stage2_compare/transport_random.mp4
```

| 文件 | 看什么 |
| --- | --- |
| `runs/..._transport_alternate/figures/fig_learning_curves.png` | 四联图：吞吐 / 成功率与内生起始占比 / 救场次数 / 起始覆盖与熵 |
| `runs/..._transport_alternate/figures/fig_learning_curves_both.png` | 两条课程的学习曲线叠在一起（几乎重合 = §3.4 的结论） |
| `runs/..._transport_alternate/figures/fig_forward_backward.png` | 偏科检查：正向和反向的成功数是否同步上涨（前 5000 步只有正向，见 §3.2） |
| `runs/..._transport_alternate/figures/fig_two_curricula.png` | 六联柱状图：两种课程训练的策略 × 两种测试模式（含跨模式） |
| `runs/..._transport_alternate/transport_ckpt.mp4` | 训练后的策略。上排 alternate：物体在 A/B 之间来回、`human resets` 恒为 0；下排 fixed：物体每完成一个 task 就瞬移回源区域（那就是一次人工复位） |
| `runs/..._stage2_compare/transport_biased_home.mp4` | **覆盖塌缩的可视化**：`biased`(舒适区 9cm) + `home` 救场。2000 步 / 6 局，alternate 起始格子 16/36、熵 0.644；fixed 24/36、熵 0.766。右侧蓝格只点亮区域中心那几格 |
| `runs/..._stage2_compare/transport_biased_resample.mp4` | 同一策略、同样 2000 步，只把救场改成均匀重采样：起始格子 **26/36、熵 0.884**（home 版是 16/36、0.644）—— 直观看出「救场怎么摆物体」决定了还剩多少多样性 |
| `runs/..._stage2_compare/transport_random.mp4` | 完全不可靠时：末端乱走，物体每 120 步被规则摆回源区域，`stall resets` 一直涨 —— 这就是 Q3 的兜底机制在跑 |

---

## 4. 闭环：把训练好的策略放回同一张对照表

```bash
python scripts/compare_reset_modes.py --policies perfect,biased,random,ckpt \
    --ckpt runs/20260922_205625_sac_transport_alternate/model_final.zip \
    --recovery-modes resample,home --out runs/20260922_205020_stage2_compare
```

| policy | mode | tasks | succ% | 正/反 | total_rst | steps/task | thr/1k(eff) | start_cells | start_ent | endo_start% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| perfect（脚本上界） | alternate | 3627.3±19.9 | 98.6% | 1825/1802 | **0** | 5.5 | 181.37 | 36.0 | 0.994 | 99% |
| **ckpt（SAC 60k 步）** | alternate | **3637.0±16.7** | **98.6%** | **1830/1807** | **0** | 5.5 | **181.85** | 36.0 | 0.994 | 99% |
| ckpt（同一个模型） | fixed | 2622.0±3.6 | 98.1% | 1324/1298 | 2622 | 7.6 | 26.58 | 36.0 | 0.991 | 0% |
| biased（只在 29% 区域可靠） | alternate | 74.7±14.2 | 27.0% | 48/26 | 150 | 279.3 | 3.05 | 35.3 | 0.937 | 27% |
| random | alternate | 13.3±2.5 | 6.6% | 11/2 | 140 | 1559.5 | 0.55 | 29.0 | 0.857 | 7% |

**同一把尺子量出来的结论**：训练后的 SAC 与手写比例控制器在每一列上都打平
（任务数、成功率、复位次数、每任务步数、覆盖格子、起始熵）。
这说明三件事：

1. 环境已经被「解决」了，天花板是几何决定的（每任务 5.5 步 ≈ 一次跨区移动的最少步数）。
2. `alternate` 模式下 **60000 步评测里一次复位都没付**，物体始终在策略自己手里流转。
3. 覆盖塌缩在这个组合下**没有发生**（36/36、熵 0.994）——但同一张表里的 `biased` 行
   和 §2.4 的扫描说明，只要策略不是处处可靠，塌缩就会出现。指标要留着。

---

## 5. 这一阶段踩到的坑（都是实际报错或实际得到错误数字的）

| 坑 | 现象 | 修法 |
| --- | --- | --- |
| **config 里的 `reset_mode` 和命令行维度重复传参** | `TypeError: got multiple values for keyword argument 'reset_mode'` | 构造环境前 `env_kwargs.pop("reset_mode", None)`（`recovery_mode` 同理）。复位模式是**实验维度**，不该由 config 单方面决定 |
| **环境计数器在 `reset()` 时清零** | 跨多局统计时只拿到最后一局的数据，任务数少一个数量级 | 每局结束都取一次 `coverage_report()`，用 `merge_episode_reports()` 累加。视频脚本里连事件检测的「上一帧快照」也要跟着 reset 重置 |
| **格子计数的键类型不一致** | `AttributeError: 'tuple' object has no attribute 'split'` | 环境内部用 `(i, j)` 元组键，`coverage_report()` 才转成 `"i,j"` 字符串（为了能写进 JSON）。跨模块统一走 `cell_key()` |
| **`json.dump` 不能写元组键** | `TypeError: keys must be str, int, float, bool or None` | 同上，所有要落盘的计数都先过 `cell_key()` |
| **熵的分母选错会掩盖塌缩** | 「只去过 2 格但很均匀」也算 1.0 | 归一化熵的分母用 `log(全部格子数)`，不是 `log(去过的格子数)` |
| **`model.logger.name_to_value` 在 callback 里是空的** | 训练回报一直是 `nan` | SB3 每次 `dump()` 后会清空它；改读 `model.ep_info_buffer`（Monitor 塞进去的最近 100 局） |
| **表格键名在「一个任务都没完成」时是 `None`** | `KeyError: 'resets_per_task'` | 求均值的键集合要扫**所有** seed，不能只看第一行；`None` 的键显式补上 |
| **三元组当字典键查** | 表 A / 表 B 一行都没打出来（静默失败，不报错） | `results` 的键是「策略-模式-救场」用竖线拼成的字符串，遍历 `combos`（三元组）时要先 `join` 成同样的字符串再查 |
| **视频只渲出一局** | `--steps 2000` 只出 401 帧 | 一局 `max_steps=400` 就 truncated，要跨局续跑 |
| **`A && B &` 的作用域** | 变量为空，文件写到了 `/` 根目录 | `VAR=x && cmd &` 会把**整条链**放进后台子 shell，父 shell 拿不到 VAR。要么分行，要么直接把路径写死 |

最后一条真的把文件写到了 `/transport_biased.mp4`。按工作区规矩没有 `rm`，
已经 `mv` 到 `/workspace/mnt/sppro/yhzhang91/recycle_bin/`。

---

## 6. 这些结果**不能**证明什么（边界）

1. **不能推广到真机 / 视觉观测**。这里是 2D 点质量 + 仿真真值状态观测，没有接触物理、
   没有夹爪、没有物体姿态、没有相机噪声。策略之所以能「处处可靠」，正是因为观测是白送的。
   `../RoboRSI/docs/capx-pickplace-lessons.md` 的结论正好相反：纯视觉抓取成败首先取决于定位可靠性。
2. **不能证明 RL 比脚本强**。恰恰相反：SAC 只是打平了 20 行的比例控制器。
   这个环境的价值是**机制验证**，不是算法验证。
3. **`reset_cost_steps=30` 是保守假设**。真机上人工复位是秒级、控制周期是几十毫秒级，
   比值是几百到上千。按真机比值重算，交替的吞吐优势会大得多——但我们没有真机数据，
   所以只报 30 这个保守值，并把它做成可调参数。
4. **覆盖率塌缩的结论依赖 `biased` 这个人为构造的策略**。它的作用是「可控地设定可靠度」，
   不是对任何真实策略的断言。真正需要验证的是：真机策略的可靠度分布落在扫描曲线的哪一段。
5. **一次 seed（训练 seed=0）**。两条课程各只训了一个 seed，相变点（7500–10000 步）
   的方差未知。对照实验有 3 个 seed，训练没有。
6. **没有验证「交替会不会让策略学得更慢」**。两条课程都到了天花板，所以这个问题在本环境里
   问不出答案；要加难度（视觉 / 接触 / 更长 horizon）才能重新问一次。

---

## 7. 一键复现

```bash
source /root/venvs/rlrobot/bin/activate

# 实验一：对照实验（不需要训练，~5 分钟；含 ckpt 行则要先有训练好的模型）
python scripts/compare_reset_modes.py --recovery-modes resample,home \
    --policies perfect,biased,random,ckpt \
    --ckpt runs/20260922_205625_sac_transport_alternate/model_final.zip \
    --out runs/20260922_205020_stage2_compare

# 实验二：两条课程各训一个（各 ~14 分钟，本机共享节点，长任务记得 setsid）
OMP_NUM_THREADS=1 setsid nohup python -u scripts/train_transport.py --mode alternate \
    > /tmp/train_alt.log 2>&1 < /dev/null & disown
OMP_NUM_THREADS=1 setsid nohup python -u scripts/train_transport.py --mode fixed \
    > /tmp/train_fix.log 2>&1 < /dev/null & disown

# 图 + 视频
python scripts/plot_stage2.py --latest --open
python scripts/render_transport_video.py --run runs/20260922_205625_sac_transport_alternate
python scripts/render_transport_video.py --policy biased --easy-radius 0.09 \
    --recovery-mode home --steps 2000 --out runs/20260922_205020_stage2_compare/transport_biased_home.mp4
```

**哪几个 run 目录是「正式版」**（其余是冒烟或被取代的，留着只是为了可追溯，别拿它们对数字）：

| 目录 | 内容 |
| --- | --- |
| `runs/20260922_205020_stage2_compare/` | 对照实验正式版（4 策略 × 2 模式 × 2 救场 × 3 seed + 可靠度扫描）、5 张图、3 段视频 |
| `runs/20260922_205625_sac_transport_alternate/` | 交替课程训练（60000 步）、4 张图、`transport_ckpt.mp4` |
| `runs/20260922_205625_sac_transport_fixed/` | 人工复位课程训练（60000 步）、2 张图 |
| `runs/20260922_204114_stage2_compare/` | 早期版本（3 策略，指标口径相同但缺 ckpt 行），已被上面取代 |
| `runs/20260922_205249_sac_smoke_transport_alternate/` | 3000 步冒烟，只用来验证流程通不通 |

| 文件 | 作用 |
| --- | --- |
| `envs/bidirectional_pickplace.py` | 阶段 2 环境：正反向交替 / 覆盖率网格 / 规则式救场 |
| `eval/transport_eval.py` | **唯一的指标定义处**，对照实验与训练评测共用 |
| `scripts/compare_reset_modes.py` | 对照实验（表 A/B/C）+ 可靠度扫描 |
| `scripts/train_transport.py` | SAC 训练 + `TransportEvalCallback`（训练中冻结评测）+ 跨模式评测 |
| `scripts/plot_stage2.py` | 覆盖热力图 / 可靠度扫描 / 学习曲线 / 两课程对比 |
| `scripts/render_transport_video.py` | 动作 + 覆盖率积累的视频 |
| `configs/transport_sac.yaml` | 全部超参（env / compare / train / eval 四段） |

---

## 8. 下一步（阶段 3 的接口已经预留好了）

阶段 2 留下的三个插槽，正好是阶段 3 要填的：

1. **救场复位 = 恢复技能插槽**。现在是 `_rule_reset()` 一条规则；
   阶段 3 把它换成 `py_trees` 里的一个恢复子树（回 home → 重新定位 → 重试），
   `manual_resets` 这个记账口径不用改，将来换成 LLM 接管也不用改。
2. **覆盖率统计 = 采样策略插槽**。`start_cell_counts` 已经能告诉上层「哪些起始状态没见过」，
   阶段 3 可以让 harness 据此主动选择复位位置（把 `home` 换成「去最少访问的格子」），
   直接对治 §2.4 里 `recovery=home` 的塌缩。
3. **`eval/transport_eval.py` = 发布门槛**。阶段 3 的最小 CI（train → eval → 通过才写 registry）
   就应该调 `evaluate_transport()`，把「任务成功率 + 起始熵 + 救场次数」三个都设阈值，
   只看成功率会让「学窄了」的新版本蒙混过关。

同时把难度加上去（否则 RL 只是在天花板下磨）：接 robosuite `PickPlaceCan` 或
`../Agibot_path_IK/genie_sim`，观测换成相机图像，动作换成末端 6D 增量 + 夹爪，
然后把本阶段的三张表原样重跑一遍——**指标口径不变，才有可比性**。

---

## 9. 加难度重跑（2026-09-23）：让 RL 重新有东西可学

### 9.1 为什么必须加难度，以及加了什么

§3.3 的结论是坏消息：理想环境里 SAC 60000 步 = 3637 任务 / 98.6%，20 行手写比例控制器
= 3627 / 98.6%。**RL 只是打平了脚本上界**，于是本阶段真正想研究的风险
（reset-free 交替导致起始分布塌缩）在训练后的策略上根本没机会出现（36/36、熵 0.994）。
环境到天花板之后，所有「交替 vs 复位」的问题都退化成几何问题。

所以新增 `envs/transport_perturbed.py`：**继承** `bidirectional_pickplace.py`，只覆写预留的
五个钩子（`_transform_action` / `_effective_scale` / `_grasp_ok` / `_carry_slips` / `_obs`），
覆盖率统计、任务推进、正反向切换、规则式救场、成功判定一行都没复制——
**加难度前后的指标口径完全一致，两张表可以直接对比**。

最终难度（`configs/transport_perturbed.yaml`，候选 D）：

| 旋钮 | 值 | 对应的真机现象 | 它逼出来的行为 |
| --- | --- | --- | --- |
| `action_delay` | 1 | 通信 + 控制器周期 | 增益 1 的纯 P 等幅振荡，永远停不进圈 |
| `gain_noise` | 0.50 | 电机标定 / 负载变化（每局抽一次） | 不能背增益，只能闭环 |
| `drift` | 0.008 | 标定偏置 / 侧向力（每局随机方向） | 近处必须大增益硬顶稳态误差 |
| `payload_gain` | 0.70 | 有负载时更慢更钝 | seek 相和 carry 相是两个被控对象 |
| `approach_speed_limit` | 0.030 | 冲太快把小物体撞飞 | 进圈前必须减速（撞飞 = 这一抓落空） |
| `slip_prob` | 0.04 | 搬运途中掉物 | 抓起后必须尽快送走，掉了要重抓 |

`obs_noise` 刻意保持 0：**扰动只影响策略能看到什么、能做到什么，绝不影响环境怎么判成败**。

三股压力是互相拉扯的：限速要求「慢慢接近」，滑落要求「快快搬走」，漂移要求「近处大增益」，
而增益抽签 + 负载降速意味着同一局里两个相、局与局之间被控对象都不同。
**任何一组固定 (g) 或 (kp,kd) 都不可能同时满足**——这就是脚本上界被压到 85% 的机理；
策略网络可以做增益调度（远处小增益蹭、进圈大增益顶、抓到后加速），这是固定增益表达不出来的。

> **一个必须记录的 bug（本次已修，同款还在别处）**：延迟队列 `deque(maxlen=k)` 是错的，
> 必须是 `maxlen = action_delay + 1`（k 条在途 + 当前这条）。写成 k 时实际延迟只有 k-1，
> `action_delay=1` 会退化成**完全没有延迟**。标定时正是靠「只加延迟 1 与无扰动的数字逐位相同」
> 发现的（`envs/transport_perturbed.py:122-130`）。**`envs/reach_perturbed.py:60-66` 有同款 bug，
> 该文件归阶段 3 的并行会话所有，本次没动**——阶段 3 的「长延迟学不动」结论里，
> 实际延迟比名义值小 1，重跑前要先修。

### 9.2 难度是标定出来的，不是拍脑袋（`scripts/calibrate_transport.py`）

判据两条：随机策略 ≈ 0%，且**最强脚本基线**落在 55–88% 之间（RL 有明确的超越目标，又不至于硬到学不动）。
脚本基线同时扫两个族，取两族里最好的一档当天花板：P 族 `clip(g*(subgoal-ee)/scale)`、
PD 族 `clip((kp*(subgoal-ee) - kd*v)/scale)`（v = 相邻两帧真实位移差，本轮新增的基线）。

第一轮单因素扫描（`runs/infra/20260923_113232_transport_calib.json`）的关键教训：
**延迟、漂移、限速单独加，都压不垮带速度反馈的 PD**（98.4% / 98.6% / 98.7%）——
它们是稳态误差或相位滞后，反馈能吸收。只有「每局抽增益 + 负载降速」这类
**改变被控对象本身**的扰动才有效。第二轮（`runs/infra/round2_transport_calib.json`）：

| 候选 | 随机 | 最强脚本 | 阶段2满分模型 | 撞飞/任务 | 取舍 |
| --- | --- | --- | --- | --- | --- |
| C 限0.026 滑4% 噪45% | 0.0% | 82.7% (pd 1:0.5) | 81.9% | 4.23 | 撞飞偏多 |
| **D 限0.030 载0.70（选用）** | **0.0%** | **85.5% (p g0.7)** | 84.2% | **1.94** | 带内、撞飞少、吞吐 29.5/千步 |
| E = D 去掉滑落 | 0.0% | 85.9% | 77.9% | 2.46 | 少了「快搬」这股压力 |
| F 限0.026 滑3% 漂0.006 | 0.0% | 89.6% | 84.0% | 1.61 | 偏简单 |
| G = F 去掉漂移 | 0.4% | 97.0% (p g0.35) | 77.3% | — | 去掉漂移脚本又满分 |
| H 漂0.016 限0.026 | 0.0% | 84.4% | 78.7% | 10.80 | 「弹球」动力学，不适合当第一个基准 |

### 9.3 对照实验（扰动版）：交替不再免费

`runs/20260923_115158_stage2_compare_perturbed/`（无 ckpt）与
`runs/20260923_124126_stage2_compare_perturbed_ckpt/`（加入训练后的策略），
每格 3 seed × 20000 步，口径与 §2 完全相同。摘录（resample 救场）：

| policy | mode | tasks | succ% | stall_rst | total_rst | thr/1k(eff) | start_cells | start_ent | endo% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| perfect（脚本上界） | alternate | 605.3±14.4 | 85.2% | 55 | 55 | 27.95 | 36.0 | 0.986 | 85% |
| perfect | fixed | 387.3±2.1 | 78.2% | 58 | 445 | 11.61 | 36.0 | 0.986 | 0% |
| pd（速度反馈基线） | alternate | 565.3±8.8 | 84.1% | 57 | 57 | 26.05 | 36.0 | 0.989 | 84% |
| biased（舒适区 6cm） | alternate | 48.3±4.6 | 20.5% | 137 | 137 | 2.00 | 34.7 | 0.925 | 20% |
| biased + home 救场 | alternate | 49.7±6.6 | 21.1% | 136 | 136 | 2.06 | **25.0** | **0.575** | 21% |
| random | alternate | 0.0 | 0.0% | 150 | 150 | 0.00 | 18.0 | 0.782 | 0% |
| **ckpt（SAC，示范预填 60k）** | alternate | 132.0±14.2 | 43.1% | 124 | 124 | 5.57 | 35.7 | 0.966 | 43% |
| ckpt（同一模型） | fixed | 103.3±4.5 | 37.1% | 125 | 229 | 3.85 | 36.0 | 0.964 | 0% |

三个新发现（理想环境里都看不到）：

1. **交替不再免费**。理想环境里 perfect/alternate 的救场是 0 次；扰动环境里即使处处可靠的
   控制器也要付 ~55 次 stall 救场——掉物和撞飞会制造「卡死 120 步」，reset-free 的
   「反向任务自动当复位」假设在有接触扰动的世界里只部分成立。
2. **两种模式的成功率不能直接互比**。同一策略在 alternate 下系统性更高
   （perfect 85.2 vs 78.2，pd 84.1 vs 79.2，ckpt 43.1 vs 37.1）：reset-free 模式下
   「抓起」这一相几乎免费（物体就在手边），fixed 模式每局都要从空手寻物开始。
   要比只能比含复位成本的吞吐（27.95 vs 11.61）或冻结评测的同口径曲线。
3. **塌缩机制与环境是否理想无关**。biased + home 在扰动环境里照样塌到 25/36、熵 0.575
   （resample 版 34.7 / 0.925）——开关仍然是「策略局部可靠 + 救场摆固定点」这两个条件，
   与 §2.4 的结论一致，只是这次发生在带扰动的动力学上。

### 9.4 训练：相变为什么从 7.5k 步推迟到 65k 步

理想环境里相变在 7500–10000 步（§3.2）；扰动环境里从零训练（150000 步，alternate）
直到 ~65k 步才离开 0%：`5k:0% … 65k:5% 70k:11% 90k:21% 115k:31% 130k:51% 150k:49%`，
冻结评测 40.7%（118.7 任务，正/反 71/48，救场 150→122，起始 36/36 熵 0.966）。
排查了三条假设：

| 假设 | 实验 | 结论 |
| --- | --- | --- |
| 部分可观测（延迟让观测缺信息） | 观测加真实速度分量（7→9 维，`include_velocity`），20k 步 | 0–5%，**否**（脚本控制器在该观测下数字逐位不变，口径安全） |
| 探索拿不到奖励 | 随机策略在扰动环境跑 20000 步 | 完成 0 个任务（理想环境 7.8%）→ SAC 早期拿不到 `place_bonus`，critic 无从起步；且采样动作 std 0.15–0.33 但均值饱和 → 冲进圈撞飞。**是根因** |
| 先给一点会做的数据 | pd 控制器跑 10000 步预填回放池（`--demo-steps`，SERL 式最小闭环），再训 60k | 60k 步冻结 43.2%（132.7 任务，正/反 78/54，救场 123，起始 35.7/36 熵 0.966，内生 43%）；同预算从零 ≈0–11% → **约 3× 样本效率，是** |

两条反例同样是发现：

- **示范不是越多越好**：预填 40000 步在同预算更差（20k 步时 5% vs 10k 预填的 12%）。
  池子里脚本转移占比过高时，on-policy 的修正被稀释——示范是点火器，不是燃料。
- **naive fine-tune 会先退化**：拿理想环境满分模型（冻结 83.3%）在扰动环境续训，
  2.5k 步掉到 44%、5k 步 33%、10k 步才回到 59%，始终没回到起点。动力学变了之后旧 critic
  是错的，策略先被错误的价值估计带偏。这正是阶段 3 发布门禁要拦的情形：
  「新版本在旧环境好」不等于「可以直接上线」。

**覆盖率这一轮的答案**：43.2% 的策略起始覆盖 35.7/36、熵 0.966、内生起始 43%，
与理想环境满分策略的 36/36、0.994 同量级——**策略只有四成可靠也没有塌缩**，
因为救场是 resample。把同一个策略的救场换成 home，起始熵立刻掉到 0.790（§9.3 表 ckpt 行）。
塌缩的开关从头到尾是「救场把物体摆哪」，不是「策略有多强」。

### 9.5 闭环：训练后的策略放回同一张表

ckpt 行 vs 脚本上界：43.1% vs 84.1%（pd）/ 85.2%（perfect），每任务步数 153 vs 35，
救场 124 vs 57。**RL 还没追上脚本上界——这正是加难度的目的**：理想环境里两者打平、
问题不可判定；现在差距是可测量的，下一轮改进（课程、示范质量、奖励塑形）有了靶子。
同时 ckpt 在 alternate 比 fixed 高 6 个点（43.1 vs 37.1），再次印证 §9.3 发现 2 的口径提醒。

**课程 × 预算的 2×2（都带 10k 步示范预填；冻结评测 3 seed × 20000 步）**：

| 课程 | 60k 步 | 150k 步 | 跨模式（换到另一种复位模式测） |
| --- | --- | --- | --- |
| alternate | **43.2%**（132.7 任务，熵 0.966） | **67.8%**（299.7 任务，熵 0.981，内生 68%） | 36.8%（60k）/ 62.9%（150k，fixed 下） |
| fixed | 38.4%（109.3 任务，熵 0.960） | **58.6%**（212.7 任务，熵 0.976） | 43.3% / 56.7%（alternate 下） |
| 无示范对照：alternate 从零 | — | 40.7%（118.7 任务） | 36.5%（fixed 下） |

三个读法：

1. **同预算 60k，alternate 仍赢**（+4.8 个点，吞吐 5.60 vs 4.04 任务/千步）：学习早期
   reset-free 省下的预算是实打实的。
2. **两边都带示范时，alternate 在两个预算上都赢**（60k：43.2 vs 38.4；150k：67.8 vs 58.6）。
   早先「fixed 150k 反超」的读法是错的——那一臂 alternate 是从零训的（40.7%），混进了
   「有无示范」这个变量。真 2×2 补齐后结论干净了：**课程差距（+9.2 点）与示范差距
   （150k 上 40.7 → 67.8，+27.1 点）都真实存在，且可以叠加**。
   理想环境里两条课程可互换（§3.4），加难度之后不再成立；而 alternate 的内生分布
   也没有自毒：150k 臂内生起始 68%、覆盖仍满格 36/36（熵 0.981），说明只要救场是
   resample，「自己给自己出题」在扰动环境里长期是净收益。
3. 跨模式差距（3–5 个点）远小于课程差距，且随能力上升而缩小（58.6 vs 56.7）：
   §9.3 发现 2 的「alternate 成功率虚高」校准提醒主要作用于中低能力区间。

至此扰动环境的最好成绩是 **alternate + 示范 150k = 67.8%**（脚本上界 84.1%）：
差距从 60k 时的 41 个点收窄到 16 个点，RL 还在追但没追平——难度标定仍然有效。
（`runs/20260923_131025_sac_sac_transport_perturbed_demo_alternate150k_alternate`）

**视频（定性观察）**：`runs/20260923_124126_stage2_compare_perturbed_ckpt/transport_pd_perturbed.mp4`
（pd 基线：alternate 49 任务 / 79.0%，撞飞 160 次、掉物 28 次；fixed 34 任务 / 72.3%）与
`transport_ckpt_perturbed.mp4`（训练后策略：alternate 9 任务 / 32.1%，fixed 16 任务 / 47.1%）。
看点是 HUD 上的 `push`（撞飞）与 `slip`（掉物）计数怎么跳、以及 stall 救场把物体摆回哪里。
注意 ckpt 那段视频里 fixed 反而高于 alternate——**6 局窗口的噪声足以翻转方向**，
与 3 seed × 20000 步冻结评测（43.1% vs 37.1%）相反；视频只用来观察机制，不用来比数字。

### 9.6 这一轮踩到的坑

| 坑 | 现象 | 修法 |
| --- | --- | --- |
| 延迟队列 off-by-one | 「只加延迟 1」与「无扰动」数字逐位相同 | `maxlen = action_delay + 1`；`envs/reach_perturbed.py` 同款待修（见 §9.1 引文） |
| 重启对照臂漏传 `--steps` | fixed 臂按 config 的 150k 在跑，与 60k 的 alternate 臂不同预算 | 补跑 `--steps 60000` 的干净 A/B 臂；150k 臂保留作长 horizon 证据 |
| 学习曲线图例重名 | 两条 alternate 曲线图例都叫 `alternate` | `plot_stage2.py` 在同名时用 run 目录名片段做后缀（`[perturbed_demo_alternate]` vs `[perturbed_alternate]`） |
| 内联评测噪声 | 3 局内联评测相邻两点能差 10 个点（60k: 53.7% / 58.1%） | 曲线只看趋势，结论一律以 3 seed × 20000 步的冻结评测为准 |

### 9.7 这些结果**不能**证明什么

1. 43% 不是「可用」，只是「难度标定成功 + 示范预填有效 + 覆盖指标仍然敏感」三条证据。
2. 训练仍只有单 seed；「3× 样本效率」是两条曲线之比，不是显著性结论。
3. SB3 把 400 步截断当终止处理（既有问题，本轮未改），价值估计有偏，所有策略同偏、可比但不绝对。
4. push / slip 是风格化接触模型（进圈超速 → 物体平移 4.5cm），不对应真机接触物理；
   真机上的「难度」还要加上视觉与标定误差，那是阶段 4 的事。

### 9.8 一键复现（扰动版）

```bash
source /root/venvs/rlrobot/bin/activate

# 标定难度（~20 分钟/轮；改 configs/transport_perturbed.yaml 前先跑这个）
python scripts/calibrate_transport.py --filter D

# 对照实验（~5 分钟；带 ckpt 行 ~6 分钟）
python scripts/compare_reset_modes.py --config configs/transport_perturbed.yaml \
    --policies perfect,biased,random,pd,ckpt --p-gain 0.7 --pd-kp 1.0 --pd-kd 0.5 \
    --ckpt runs/20260923_121242_sac_transport_perturbed_demo_alternate/model_final.zip \
    --run-name stage2_compare_perturbed_ckpt

# 训练（从零 150k ~44 分钟；示范预填 60k ~17 分钟）
OMP_NUM_THREADS=1 setsid nohup python -u scripts/train_transport.py \
    --config configs/transport_perturbed.yaml --steps 150000 > /tmp/train_pert_alt.log 2>&1 &
OMP_NUM_THREADS=1 setsid nohup python -u scripts/train_transport.py \
    --config configs/transport_perturbed.yaml --steps 60000 --demo-steps 10000 \
    --demo-policy pd > /tmp/train_demo_alt.log 2>&1 &

# 图 + 视频（视频文件名自动带 _perturbed 后缀）
python scripts/plot_stage2.py --compare runs/20260923_124126_stage2_compare_perturbed_ckpt \
    --train runs/20260923_121242_sac_transport_perturbed_demo_alternate \
    --train runs/20260923_114747_sac_transport_perturbed_alternate
python scripts/render_transport_video.py --config configs/transport_perturbed.yaml \
    --policy pd --pd-kp 1.0 --pd-kd 0.5 --steps 2000 \
    --out runs/20260923_124126_stage2_compare_perturbed_ckpt/transport_pd_perturbed.mp4
```

**扰动版「正式版」run 目录**（其余为探针/被取代，只留作可追溯）：

| 目录 | 内容 |
| --- | --- |
| `runs/20260923_115158_stage2_compare_perturbed/` | 扰动对照实验（4 策略 × 2 模式 × 2 救场 × 3 seed + 扫描）、5 张图 |
| `runs/20260923_124126_stage2_compare_perturbed_ckpt/` | 同上 + 训练后策略行、5 张图、2 段视频（pd / ckpt） |
| `runs/20260923_114747_sac_transport_perturbed_alternate/` | 从零 150k 步（alternate）、冻结 40.7%、4 张图 |
| `runs/20260923_121242_sac_transport_perturbed_demo_alternate/` | **示范预填 10k + 60k 步（alternate）、冻结 43.2%——本轮主结果**、4 张图 |
| `runs/infra/round2_transport_calib.json` | 难度标定第二轮原始数据（候选 C–H） |
| `runs/20260923_125608_..._demo_fixed60k_fixed/` | 示范预填 + fixed 课程 60k（A/B 的 fixed 臂）、冻结 38.4% |
| `runs/20260923_123718_..._demo_fixed_fixed/` | 示范预填 + fixed 课程 150k、冻结 58.6%（当前扰动环境最好成绩） |
| `runs/20260923_131025_..._demo_alternate150k_alternate/` | 示范预填 + alternate 课程 150k（补 2×2，在跑） |
