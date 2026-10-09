# 本机环境笔记（2026-09-22 实测）

只记实测过的东西，避免以后重复踩坑。

## 1. 硬件与系统

- Ubuntu 22.04.4，112 core，~2 TB RAM，磁盘：NFS `/workspace/mnt/sppro`（1.1 P，已用 93%），容器 overlay `/`（7.0 T，可用 6.1 T）。
- **⚠️ 2026-09-29 更正：`112 core` 是宿主可见数，不是能用的量。** 容器 cgroup 配额只有 **12 核**
  （`/sys/fs/cgroup/cpu/cpu.cfs_quota_us=1200000` / `cfs_period_us=100000`；`cpuset.cpus=0-111` 不绑核但配额卡死；
  内存上限 225 GiB；`cpu.stat` 里 `nr_throttled=746`、`throttled_time≈2950 s` ⇒ **已经被限流过了**）。
  `nproc` / `os.cpu_count()` / `sched_getaffinity` 全都返回 112，**都不能当可用并行度用**。
  实测：robosuite Lift state-only 8 进程内近线性、**12 进程撞顶**、16 进程效率掉到 70%
  （`runs/infra/robosuite_throughput_probe_20260929/`；结论同步进 `docs/infra-gpu-render.md` §6.3）。
  这与下面 §7 记的 `loadavg` 是宿主机口径属**同一类错误**：容器里看得见的资源数字 ≠ 自己能拿到的量。
- GPU：1 × A800-SXM4-80GB，driver 590.48.01，CUDA 13.1；base env 里 torch 2.4.1+cu124，`cuda.is_available()=True`。
- **没有 docker，没有 nvidia-container-toolkit，没有 ROS**（`/opt/ros` 不存在）。
  → Genie Sim（Isaac Sim 5.1 容器）、MoveIt、BehaviorTree.CPP、ROSA 在这台机上都跑不了。

## 2. 网络（重要）

| 目标 | 结果 |
| --- | --- |
| `pypi.org` | 直连失败 |
| `mirrors.aliyun.com` / `mirrors.ustc.edu.cn` | 可用（`/etc/pip.conf` 已配 USTC 为主、aliyun 为备） |
| `huggingface.co` | 直连失败 |
| `hf-mirror.com` | 200，可用 → `export HF_ENDPOINT=https://hf-mirror.com` |
| `github.com` | 200，可 clone |

所有出网都经过代理 `http(s)_proxy=http://10.2.162.180:3128`；**绕过代理直连镜像会挂死**，所以代理不能关。
代理对「首次拉取的大文件」限速明显：实测 pip 下载 ~164–240 KB/s；同一个文件被拉过一次后，curl 再取能到 11–34 MB/s（代理缓存生效）。
结论：**大 wheel 只需要忍一次**；重复安装会快很多。venv 放在 overlay（`/root/venvs/...`）而不是 NFS，也是为了避免小文件 IO 慢。

## 3. 依赖版本的坑

- **`stable-baselines3` 必须钉 `<2.8`**。SB3 2.8+ 要求 `torch>=2.8`；本机继承的是 torch 2.4.1+cu124，pip 会去下 `torch-2.14.0`（554 MB）+ 一串 `nvidia-*` CUDA 包（数 GB），并且**在 venv 里盖掉 GPU 版 torch**。实测装到 2.7.1 正常，不触发 torch 下载。
- `gymnasium` 钉 `<1.3` 以匹配 SB3 2.7.x。
- `opencv-python` 钉 `<5`。不钉的话 pip 先下 opencv 5.0.0.93（73.8 MB），再因约束回溯到 4.14.0.94（77.4 MB），在代理限速下白等十几分钟。
- robosuite 1.5.2 会连带 `numba` + `llvmlite`(59.9 MB) + `mink==0.0.5` + `qpsolvers` + `pynput` + `pygame`，第一次装比较久。
- `pyyaml`、`imageio`、`psutil`、`rich`、`numpy 1.26.4` 已在 base，venv 直接继承，不会重下。
- **RoboRSI 的 `[libero]` extra 与本项目互斥**：它钉 `robosuite==1.4.0` / `gym==0.25.2` / `mujoco==3.3.0`，且要求 Python ≥ 3.12。必须单独一个环境，详见 `notes_roborsi.md`。

## 4. 渲染

`libEGL.so.1`、`libEGL_mesa.so.0`、`libOSMesa.so.8`、`libGL.so.1` 都在 `/usr/lib/x86_64-linux-gnu`。
所以 `MUJOCO_GL=egl`（GPU，首选）和 `MUJOCO_GL=osmesa`（CPU，退路）都可用。
无显示器环境下如果忘了设这个变量，录视频会直接报错或得到全黑画面。

## 5. 复现方式

```bash
bash scripts/setup_env.sh
```

脚本会建 venv（`/root/venvs/rlrobot`，可用 `VENV=` 覆盖）、按上面的版本约束装依赖、写出 `requirements.txt`，最后自动跑 `scripts/env_check.py` 自检。
注意 venv 在容器 overlay 上，**容器重启会丢**；`requirements.txt` 在仓库里，重建只要重跑一次脚本。

## 6. robosuite 1.5.2 的 API 差异（2026-09-22 实测）

网上大部分教程/代码是给 robosuite 1.4 写的，直接抄会报错。本机实测差异：

| 你在教程里看到的 | 1.5.2 实际 | 处理方式 |
| --- | --- | --- |
| `env.action_space.low/high` | **没有** `action_space` / `observation_space` 属性 | 用 `env.action_spec` → `(low, high)` 两个 numpy 数组；维度用 `env.action_dim` |
| `obs = env.reset()` | 返回 `OrderedDict`，**不是** `(obs, info)` | `scripts/smoke_random_policy.py` 里 `unpack_reset()` 两种都兼容 |
| `obs, r, done, info = env.step(a)` | 返回 **4 元组**，不是 gymnasium 的 5 元组 | `unpack_step()` 兼容 4/5 元组，4 元组时 `truncated=False` |
| `env.render(offscreen=True, camera_name=...)` | `render()` **不接受任何参数**，只往屏幕窗口画（本机无显示器 → 必炸） | 离屏取帧走两条路：① `obs["<camera>_image"]`（需 `use_camera_obs=True`）② `env.sim.render(camera_name=..., height=..., width=...)` |

其它实测事实：

- `Lift` + `Panda` 默认 `horizon=1000`、`control_freq=20` → 一局 50 秒仿真时间，随机策略跑满 1000 步约 20 秒墙钟（含 256×256 录帧）。
- `use_camera_obs=True, camera_names='frontview'` 时 obs 里有 `frontview_image`，shape `(256,256,3)`、dtype `uint8`、平均像素 ~150（不是黑屏，说明 EGL 真的渲染了）。
- `Lift` 的 obs 键名是 `cube_pos` / `cube_quat` / `gripper_to_cube_pos`，不是通用的 `object_pos`。另有拼好的 `robot0_proprio-state`(50) 和 `object-state`(10)，做低维 RL 直接用这两个最省事。
- 启动时三条 WARNING（`No private macro file`、`robosuite_models` 未装、`mink-based whole-body IK`）都是无害的，只有用 GR1 人形机器人才需要处理。
- `numpy 2.4.6` + `robosuite 1.5.2` + `mujoco 3.9.0` 组合无 deprecation 报错。

## 7. 性能：这台机是共享的，CPU 争抢是主要瓶颈

> **⚠️ 2026-09-29 待复测的另一种解释（本节结论可能需要改）**：本节把"排队等 CPU"归给共享机上的邻居争抢，
> 但容器 cgroup 配额只有 **12 核**（见 §1 的更正）。下表那行 `CPU 1116%` = **11.16 核**，
> 恰好贴在 12 核配额上 ⇒ "torch 默认 56 线程跑不完 5000 步"更可能是**自己撞配额被限流**
> （56 线程抢 12 核 ⇒ 同步开销 + `nr_throttled` 增长），而不是邻居占满。
> 两种解释给出的**行动建议相同**（小网络一律单线程），所以历史结论没有被用错；
> 但"`loadavg` 600–1200 ⇒ 别人把 CPU 占满了"这个**归因**不成立（`loadavg` 是宿主机口径）。
> **要区分只需一次复测**：同一份 SAC 训练分别在 `OMP_NUM_THREADS=1` 与默认线程下跑，
> 同时采 `/sys/fs/cgroup/cpu/cpu.stat` 的 `nr_throttled` 增量 —— 若默认线程组的增量远大于单线程组，
> 就是自我限流。**本轮未做此复测，故只标注不改结论。**

2026-09-22 17:00 前后实测：`load average` 长期在 **600–1200**（112 核），也就是说别人的任务把 CPU 占满了。
同一份 SAC 训练（两层 64 的 MLP，5000 步）：

| 配置 | 墙钟 | 有效速度 |
| --- | --- | --- |
| torch 默认 56 线程 | 5000 步跑不完（>5 分钟，CPU 1116%） | 线程同步开销 > 计算量 |
| `OMP_NUM_THREADS=1` 单线程 | 2000 步 116.6 s | ~17 步/秒 |
| `--device cuda`（GPU 空闲） | 2000 步 137.2 s | ~15 步/秒 |

结论：
- **小网络一律单线程**。`train_reach.py` / `eval_policy.py` 已在 import torch 之前设好 `OMP_NUM_THREADS=1`，
  并提供 `--threads` 开关。等接了图像策略（CNN/ViT）再调大。
- **GPU 对这个规模没用**（数据搬运开销 > 计算），别指望切 cuda 提速；GPU 留给以后的大模型/图像策略。
- 50000 步的 Reach 训练实测 **3274 秒（54.6 分钟，~15 步/秒）**，其中大部分时间是在排队等 CPU。
  这个量级正常，不是代码有问题。

## 8. 后台长任务怎么跑（修正之前的结论）

`nohup cmd &` 会在 `exec_command` 返回时被杀掉，但**加 `setsid` 就能活**：

```bash
setsid nohup /root/venvs/rlrobot/bin/python -u scripts/train_reach.py \
    --config configs/reach_sac.yaml > /tmp/train_full.log 2>&1 < /dev/null & disown
```

关键点：`setsid`（脱离控制终端/进程组）+ `</dev/null`（不占 stdin）+ `disown`。
之后用 `tail -f /tmp/train_full.log` 或 `ps -eo pid,etime,pcpu,cmd | grep train_reach` 查进度。
本机也装了 `tmux`（`/usr/bin/tmux`），交互式盯长任务更方便。

## 9. 本机有两套 Python，别搞混（新手最常踩）

| 解释器 | 提示符 | 里面有什么 | 能跑什么 |
| --- | --- | --- | --- |
| `/opt/conda/bin/python`（conda base，3.11.9） | `(base)` | torch 2.4.1+cu124、jax、TF、numpy、scipy、matplotlib | **跑不了本项目脚本**：没有 py_trees / gymnasium / robosuite / mujoco / SB3 |
| `/root/venvs/rlrobot/bin/python`（项目 venv，3.11.9） | `(rlrobot)` | base 的全部内容（`--system-site-packages` 继承）+ 上面那些缺的 | 本项目全部脚本 |
| `/opt/conda/envs/roborsi/bin/python3.12` | `(roborsi)` | RoboRSI + LIBERO 那一套（torch 2.6.0+cpu、robosuite 1.4.0） | 只跑 RoboRSI，**不要和本项目混用** |

```bash
source /root/venvs/rlrobot/bin/activate     # 提示符变 (rlrobot) 就对了
deactivate                                  # 退回 base
```

不想 activate 也可以直接用绝对路径：`/root/venvs/rlrobot/bin/python scripts/xxx.py`。

所有脚本入口都调了 `scripts/_venv.ensure_venv(...)`（用 `importlib.util.find_spec` 只探测不导入，
所以不会在设 `OMP_NUM_THREADS` 之前把 torch 拉起来）。环境不对时它打印的是修法，不是 traceback。

**venv 在容器 overlay（`/root/venvs`）上，容器重启会丢**；`requirements.txt` 和
`requirements-inherited.json` 在仓库里，重跑一次 `bash scripts/setup_env.sh` 就能重建。

## 10. 录视频必须上下翻转（极易踩）

MuJoCo 离屏渲染返回的像素是 **bottom-up** 的。robosuite 的 `sim.render(...)` 和
`use_camera_obs=True` 拿到的 `<camera>_image` 都**没有**帮你翻。
不翻的话视频是倒的：桌面在画面上方、机械臂吊在下方，看起来像「相机装反了」，
实际上只是少了一行 `[::-1]`。

robosuite 官方自己的 `robosuite/scripts/make_reset_video.py:90` 和
`robosuite/utils/camera_utils.py:103` 都是 `render(...)[::-1]`。

本项目 `smoke_random_policy.py` 的 `grab_frame()` 和 `demo_scripted_lift.py` 已内置翻转。
**自己写录视频代码时记得加。**
