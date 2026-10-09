# 阶段 0/1 笔记：从零看懂这套代码在干什么

写给完全没有 RL 背景的自己。读完这份再去看代码，每一行都能对上号。

## 1. 强化学习到底在做什么

一句话：**让一个网络（策略）在环境里反复试错，用奖励信号把网络里的数字慢慢改好。**

```
       action（动作）
  策略 ───────────────▶ 环境
  policy ◀─────────────── env
       observation（观测）+ reward（奖励）
```

循环里只有两个函数，这是整个 RL 生态的统一接口（Gymnasium API）：

```python
obs, info = env.reset(seed=0)                              # 开新的一局
obs, reward, terminated, truncated, info = env.step(action)  # 走一步
```

### 必须分清的五个要素

| 术语 | 在本项目 Reach 里的具体含义 | 在真机抓取里的对应 |
| --- | --- | --- |
| observation | 6 个数：末端位置(3) + 目标位置(3)，都归一化到 [-1,1] | 关节角、末端位姿、物体位姿、相机图像 |
| action | 3 个数：末端 xyz 位移增量，[-1,1]，乘 `action_scale` 得到米 | robosuite 是 7 维（位姿增量 6 + 夹爪 1）；真机可能是关节力矩 |
| reward | `-距离`；进入 3cm 成功圈额外 +10 | 谁给奖励，是你们研究的核心问题之一（仿真真值 / VLM 评分 / 人工） |
| terminated | 到达目标 → 这一局**成功**结束 | 物体放进目标区域 |
| truncated | 超过 100 步还没到 → **超时**结束 | 超时、碰撞、安全限位触发 |

`terminated` 和 `truncated` 必须分开：前者是任务完成，后者是时间用完。混在一起会让算法学到错误的东西。

### 一次「训练」改的是什么

只有策略网络里的权重（一堆浮点数）。环境、奖励函数、评测 seed 都不变。
所以证明「学会了」的唯一办法是：**同一批没参与训练的初始状态上，训练后的成功率高于训练前。**
`scripts/train_reach.py` 就是把这件事做成了一张三行对比表。

## 2. 为什么第一步是手写 Reach，而不是直接上 robosuite

| | 手写 Reach | robosuite Lift |
| --- | --- | --- |
| 代码量 | 约 100 行，全部能读懂 | 几万行，黑盒 |
| obs | 6 维，含义一眼看清 | 40+ 维 + 图像，需要查文档 |
| 一次训练 | 几分钟 | 几小时起 |
| 失败原因 | 只可能是 RL 概念没懂 | 可能是接触物理、夹爪时序、渲染、依赖 |

先在 Reach 上把概念打通，再进 robosuite，出问题时才知道该怀疑哪一层。

## 3. 三个脚本分别在验证什么

### `scripts/env_check.py`（阶段 0 验收）
- 打印依赖版本 + GPU，确认不是装到了错误的 Python 里；
- 用一个只有球和地面的最小 MuJoCo 模型测**离屏渲染**，并检查画面平均像素值不是 0（0 意味着黑屏，视频会全黑）；
- 在 Reach 里跑 100 步随机策略，打印 obs/action 形状；
- 结果写成 `runs/env_check/<时间戳>.json`，以后环境变了可以对比。

### `scripts/smoke_random_policy.py`（阶段 1a）
- 用**随机动作**跑 robosuite 任务，成功率接近 0 是正常的，它不是用来出成绩的；
- 真正目的是把 obs 字典逐项打印出来，让你知道策略网络的输入长什么样：
  - `robot0_eef_pos` / `robot0_eef_quat`：末端位置与姿态（世界系，米 / 四元数）
  - `cube_pos` / `cube_quat`：被操作物体的位置与姿态（键名随任务变，`Lift` 里物体叫 cube）
  - `gripper_to_cube_pos`：夹爪到物体的相对位置，做 RL 时最有用的一维特征
  - `robot0_joint_pos`：七个关节角（弧度）
  - `robot0_proprio-state`(50) / `object-state`(10)：上面各项已拼好的向量，低维 RL 直接用这两个
  - `frontview_image`：256×256×3 相机图像（`use_camera_obs=True` 时才有）
- 并录一段 mp4，让你看到「随机策略的机械臂在乱动」是什么样子。
- 动作语义（robosuite 默认 `OSC_POSE` 控制器）：
  `action[0:3]` 末端位移增量、`action[3:6]` 姿态增量（axis-angle）、`action[6]` 夹爪（-1 开 / +1 合）。
  **这一条极其重要**：以后某次抓取失败，你要能判断是「规划错了」还是「动作接口语义理解错了」。

### `scripts/train_reach.py` + `scripts/eval_policy.py`（阶段 1b）
- 训练用一批 seed，评测用**另一批固定 seed**（默认 12345）；
- 输出三行对比表：随机策略 / 未训练的网络 / 训练后的网络；
- `eval_policy.py` 可以用 `--seed 999` 再换一批初始状态复评，排除「刚好背下了评测集」。

## 4. 会遇到的名词（SAC 相关）

| 名词 | 通俗解释 |
| --- | --- |
| policy（策略） | 输入 obs、输出 action 的网络。SAC 输出的是一个分布，训练时采样、评测时取均值 |
| on-policy / off-policy | off-policy（SAC）可以把旧经验存在 replay buffer 里反复用，样本效率高；on-policy（PPO）用完就扔 |
| replay buffer | 存 `(obs, action, reward, next_obs, done)` 的池子，`buffer_size=100000` 就是最多存 10 万条 |
| gamma（折扣因子） | 未来的奖励打多少折。0.99 表示 100 步后的奖励还值 37% |
| tau | 目标网络的软更新速度，越小越稳、越慢 |
| seed | 随机数种子。固定 seed 才能复现，比较实验必须固定 |
| deterministic | 评测时取分布均值而不是采样，减少评测噪声 |

## 5. 常见故障

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `ModuleNotFoundError: No module named 'py_trees'`（或 gymnasium / robosuite / stable_baselines3） | 你在 conda **base** 里，提示符是 `(base)` | `source /root/venvs/rlrobot/bin/activate`，提示符变 `(rlrobot)`；或直接用 `/root/venvs/rlrobot/bin/python`。脚本已内置这个检查 |
| `MUJOCO_GL` 相关报错 / 视频全黑 | 无显示器时默认后端不可用 | `MUJOCO_GL=egl`（GPU）或 `MUJOCO_GL=osmesa`（CPU），本机两者都装了 |
| robosuite 任务名不存在 | 版本差异 | `python -c "import robosuite as s; print(sorted(s.ALL_ENVIRONMENTS))"` |
| `step()` 返回值解包错误 | robosuite 实测返回 **4 元组**（`obs, r, done, info`），不是 gymnasium 的 5 元组 | 脚本里已做兼容（`unpack_step`） |
| `env.action_space` 不存在 | robosuite 1.5 没有 `action_space` / `observation_space` | 用 `env.action_spec` → `(low, high)`，维度用 `env.action_dim` |
| `env.render(offscreen=True, ...)` 报 unexpected keyword | 1.5 的 `render()` 不接受参数，只往屏幕窗口画 | 离屏取帧用 `obs["<camera>_image"]` 或 `env.sim.render(camera_name=..., height=..., width=...)` |
| 训练慢到离谱、CPU 占用 1000%+ | torch 在 112 核机上默认开 56 线程，小网络的线程同步开销 > 计算量 | `OMP_NUM_THREADS=1`（脚本已默认设好），或用 `--threads` 调 |
| `import stable_baselines3` 报 `AttributeError: StringDType` | venv 继承了 base 的 jax，它要 numpy>=2 | `pip install "numpy>=2"` |
| robosuite 建环境时 `assert get_joint_qpos_addr(...)` 失败 | mujoco 版本过新（3.13）与 robosuite 1.5.2 不兼容 | 钉 `mujoco>=3.3,<3.10`，本机用 3.9.0 |
| 下载 HF 资产超时 | huggingface.co 不通 | `export HF_ENDPOINT=https://hf-mirror.com` |
| `pip install` 卡住 | pypi.org 直连不通 | 走已配好的 USTC/aliyun 镜像 |
| torch 找不到 CUDA | 装进了错误的 env | `which python` 应是 `/root/venvs/rlrobot/bin/python` |

## 6. 阶段 1 的验收标准（做完才算过）

1. `env_check.py` 全绿，渲染平均像素值 > 0；
2. `smoke_random_policy.py` 跑出 mp4，并能口头说清 obs 里 4 个关键项和 action 的 7 维含义；
3. `train_reach.py` 的对比表里，训练后成功率明显高于未训练（目标 > 80%）；
4. `eval_policy.py --seed 999` 复评，成功率不明显下降；
5. `docs/` 里留下一页自己的话写的总结：obs/action/reward/终止条件/哪份参数变了。

做完这五条，再进阶段 2（正反向交替 + 覆盖率统计）。
