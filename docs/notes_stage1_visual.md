# 怎么「看见」学习：结果图、视频、以及「成功」到底怎么判定

> 2026-09-22 · 配套 [`notes_stage1.md`](notes_stage1.md)（数字）和 [`notes_stage0.md`](notes_stage0.md)（概念）
> 想看 SAC 网络结构 / 损失函数 / 状态机到关节的链路，去 [`notes_stage1_internals.md`](notes_stage1_internals.md)。
> 这一页解决一个问题：**训练跑完了，但我什么都看不见，也不知道成功长什么样。**

---

## 0. 先说清楚：为什么你之前什么都看不见

`envs/reach_env.py` 是**纯 numpy 的抽象环境**：一个点（代表机械臂末端）在 30cm 的盒子里移动。
它的 `render()` 直接 `return None` —— **这个环境根本没有画面**，这是故意的：
第一阶段的目的就是把 RL 的五个要素（obs/action/reward/terminated/truncated）剥离到最小，
不掺入渲染、接触物理、相机这些干扰项。

所以「看不见」不是你的问题，也不是训练没跑，而是**这个环境没有可看的东西**。
要看见，得自己加可视化。现在加了三样：

| 想看见什么 | 用什么 | 产出 |
| --- | --- | --- |
| 学习是怎么发生的 | `scripts/plot_results.py` | 4 张 PNG |
| Reach 里策略在干什么 | `scripts/render_reach_video.py` | 1 个 mp4（随机 vs 训练后并排） |
| 真实物理仿真里的「成功」 | `scripts/demo_scripted_lift.py` | 1 个 mp4 + result.json |

---

## 1. 四张结果图：`scripts/plot_results.py`

```bash
source /root/venvs/rlrobot/bin/activate
python scripts/plot_results.py --run runs/20260922_170720_sac_reach --explain
```

产出在 `runs/20260922_170720_sac_reach/figures/`。每张图回答一个表格回答不了的问题：

### `fig_curve.png` —— 学习是突变的，不是渐变的

- 蓝线：每 5000 步用**独立环境**评 20 局的平均奖励；灰色虚线：平均 episode 长度。
- 关键现象：0→10000 步奖励一直是负的（-8.8、-10.2），**10000→15000 步直接跳到 +9**，之后平台期。
- 原因：SAC 前期在高熵探索，而评测用 `deterministic=True`（取分布均值）。
  一个还没成形的高熵分布，它的均值动作往往很差。
- **实操结论：训练中途看到评测是负的，不要停。** 要看 `ent_coef` 和训练时的 `ep_rew_mean` 趋势。
- 灰虚线同步从 86 步掉到 2.3 步 → 不只是「能到」，是「越来越快」。

### `fig_three_way.png` —— 提升到底体现在哪一列

同一批 50 个初始状态、同一个 seed，只有网络权重不同：

- 成功率 16% → 6% → 100%。注意**未训练的网络比纯随机还差**：
  这说明「加了个神经网络」本身不带来任何能力，能力全部来自数据。
- 平均步数 91.6 → 2.6。一步最大位移 8.7cm、目标平均距离 19cm，理论下限约 2.2 步，
  所以 2.6 步已经接近最优，不是勉强蹭进成功圈。
- 平均末距 211mm → 8mm（成功圈半径 30mm）。

### `fig_trajectories.png` —— 行为变成了什么样（最重要的一张）

- 上排随机策略：一团折线，在盒子里乱撞，3 局全部走满 100 步超时。
- 下排训练后：从起点一条直线扎进绿圈，2-3 步结束。
- 最下面 3D 图把所有局叠在一起：无论目标在哪个角落，都是直线过去。
- 图例：黑点=起点，绿星=目标，红方块=终点，绿圈=成功判定范围（30mm）。

**成功率是标量，行为是轨迹。** 这两排并排放，比任何数字都更能说明「学会了」。

### `fig_distance.png` —— 最早的学习信号

- 一局之内「离目标还有多远」随步数的平均变化。
- 为什么重要：成功率是阶跃量（0 或 1），距离是连续量。
  **学习早期成功率还没动的时候，距离曲线已经在降了** —— 这是你能最早看到的学习信号。
- 绿色虚线是成功圈半径，曲线穿过它就代表成功。

> 图里标签是英文：本机 matplotlib 只有 21 个西文字体，没有中文字体，
> 中文会画成方框。中文解释在终端输出（`--explain`）和本文档里。

---

## 2. Reach 动画：`scripts/render_reach_video.py`

```bash
python scripts/render_reach_video.py --run runs/20260922_170720_sac_reach --steps 45
```

产出 `runs/20260922_170720_sac_reach/reach_random_vs_trained.mp4`，左右并排：

| 画面元素 | 含义 |
| --- | --- |
| 灰色线框盒子 | 工作空间 [-15cm, 15cm]³ |
| 绿色半透明球 | **成功判定范围**：`dist <= goal_radius`（30mm）这一行代码的可视化 |
| 绿星 | 目标点 |
| 蓝/灰点 + 拖尾 | 末端当前位置和走过的路径 |
| 标题里的 `dist ... mm` | 当前离目标多远 |
| 标题里的 `SUCCESS / TIMEOUT / running` | 这一局的状态 |

你会看到：左边那个点乱走、dist 一直在 200mm 上下晃、最后 TIMEOUT；
右边那个点 2-3 步扎进绿球、dist 掉到 2mm、状态变 SUCCESS。

**「成功」在 Reach 里就是：末端点进入绿球，这一局立刻结束并拿 +10 奖励。**
没有别的玄机。

---

## 3. 真实物理仿真里的成功：`scripts/demo_scripted_lift.py`

Reach 的成功太抽象（一个点进一个球）。这个脚本用 **robosuite + MuJoCo 物理引擎**
（有重力、接触、摩擦、夹爪力学），跑一个**完全不学习**的手写状态机，把方块真的拎起来。

```bash
MUJOCO_GL=egl python scripts/demo_scripted_lift.py --episodes 2 --verbose
```

产出 `runs/scripted_lift/<时间戳>/lift_scripted.mp4` 和 `result.json`。
本次实测：2/2 成功，方块 z 从 0.82 升到 0.88-0.89 m（判定线 0.84 m）。

### 控制器是 5 阶段状态机（纯规则，零学习）

```
approach  末端水平移到方块正上方 12cm
descend   垂直下降到夹爪中心比方块中心高 1.5cm
grasp     夹爪闭合 20 步（约 1 秒）
lift      保持闭合、末端全速上升，直到方块离桌面 > 6cm
hold      悬停 40 步，让你看清楚
```

动作就是 robosuite 默认的 `OSC_POSE`：`action[0:3]` 末端位移增量（每步最多 5cm）、
`action[3:6]` 姿态增量（恒 0，保持朝下）、`action[6]` 夹爪（-1 开 / +1 合）。
控制器只做一件事：把「目标点 − 当前位置」除以 5cm 再 clip 到 [-1,1]，即比例控制。

### 「成功」的四重证据链（这是本页最该记住的部分）

| # | 证据 | 在哪看 | 谁说了算 |
| --- | --- | --- | --- |
| 1 | **物理事实**：方块中心 z 从 ~0.82 升到 >0.84 | `result.json` 的 `final_cube_z` | 物理引擎 |
| 2 | **仿真器判定**：`Lift._check_success()` = `cube_z > table_z + 0.04` 返回 True | `info["success"]` | 环境代码，一行 |
| 3 | **奖励**：方块离桌后每一步 `reward` 从 0 变 1（稀疏奖励） | 终端打印 / result.json | 环境代码 |
| 4 | **画面**：mp4 里能看到方块悬在空中 | `lift_scripted.mp4` | 你的眼睛 |

四条互相印证，缺一条都可能是假的。**判定权永远在环境手里，不在模型嘴里。**

这条纪律在后面会越来越重要：
- 换成 VLM/大模型打分时，必须先做校准实验（和仿真真值对比、统计误判率），否则一定 reward hacking；
- RoboRSI 的评测文档也是同一条纪律：「成功标签只认仿真器判定」，Reviewer 只负责解释失败原因，不负责宣布成功。

### 一个有意思的对比

- 随机策略跑 `Lift` 1000 步：成功率 **0%**（见 smoke 实验）。
- 手写状态机跑 `Lift` ~90 步：成功率 **100%**。
- 差别不在「判定」（判定是同一行代码），而在**能不能把动作序列做对**。

这就是 RL / 模仿学习 / 大模型要解决的问题本身：
Lift 的难点不是「什么叫成功」，而是「怎么在接触物理里把接近→对准→闭合→抬升的时序做对」。
手写规则能解决 Lift，但解决不了更复杂的任务（物体位姿任意、有遮挡、要避障）——
那些情况下规则写不出来，才需要让策略从数据里学。
**而学出来的策略，仍然用同一行 `cube_z > table_z + 0.04` 来验收。**

---

## 4. 一个差点骗过我们的坑：视频上下颠倒

MuJoCo 离屏渲染的像素是 **bottom-up** 的。robosuite 的 `sim.render(...)` 和
`use_camera_obs=True` 拿到的 `<camera>_image` 都**没有**帮你翻转。
第一版录出来的视频是倒的：桌面在画面上方、机械臂吊在下面，看起来像「相机装反了」。

修法就一行：`frame[::-1]`。
robosuite 官方自己的 `robosuite/scripts/make_reset_video.py:90` 和
`robosuite/utils/camera_utils.py:103` 也是这么干的。
详见 [`notes_env.md`](notes_env.md) §10。自己写录视频代码时记得加。

---

## 5. 命令清单

```bash
source /root/venvs/rlrobot/bin/activate
export MUJOCO_GL=egl HF_ENDPOINT=https://hf-mirror.com

# 结果图（4 张 PNG + 每张怎么读）
python scripts/plot_results.py --run runs/20260922_170720_sac_reach --explain

# Reach 动画：随机 vs 训练后并排
python scripts/render_reach_video.py --run runs/20260922_170720_sac_reach --steps 45

# 真实物理仿真里的抓取成功（不学习，纯规则）
python scripts/demo_scripted_lift.py --episodes 2 --verbose

# 随机策略在真实仿真里长什么样（对照用，成功率 0%）
python scripts/smoke_random_policy.py --task Lift --episodes 1
```

看完这四个产出，你应该能回答：
1. 学习曲线上的「相变」发生在第几步，为什么中途是负的？
2. 训练后的策略**行为**上和随机策略差在哪？
3. 「成功」由谁判定、依据是什么、有几重证据？
4. 为什么手写规则能 100% 而随机 0%，那 RL 学的到底是什么？

这四个问题答得上来，阶段 1 就算真的过了。
