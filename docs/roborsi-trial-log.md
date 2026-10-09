# RoboRSI 本机试跑记录：`libero configure` + `libero doctor` 已跑通

> 日期：2026-09-22 · 结论：**两条路径（osmesa 与官方默认 egl）都通过，doctor 退出码 0，
> 真实 LIBERO 任务完成一次 reset + 离屏渲染。全程不需要 LLM API key。**
> 一键复现：`bash scripts/install_roborsi_minimal.sh`（幂等，可续跑）

## 1. 最终状态

| 项目 | 值 |
| --- | --- |
| conda 环境 | `/opt/conda/envs/roborsi`（Python 3.12，327 个包，3.0 GB） |
| RoboRSI | `/root/roborsi_trial/RoboRSI`，commit `9b644d2`（2026-09-21），editable 安装 |
| LIBERO-PRO | `/root/roborsi_trial/LIBERO-PRO`，commit `eafdb80`，911 MB（自带 554 个 `.pruned_init` + 564 个 `.bddl`） |
| LIBERO-Pro 资产 | **工作区** `../roborsi_runtime/LIBERO-PRO-assets`，2029 个文件 / 15 MB（`bddl_files` 440 + `init_files` 230 + `metadata`） |
| 关键版本 | torch `2.6.0+cpu` · mujoco `3.3.0` · robosuite `1.4.0` · numpy `2.2.6` · gym `0.25.2` · bddl `1.0.1` · transformers `5.17.0` · litellm `1.102.0` |
| 有意跳过 | `lerobot`、`torchvision`、`flexivrdk`、`record3d`、各家 IM SDK（原因见 §3.1） |
| RoboRSI home | **工作区** `../roborsi_runtime/home/.roborsi`（`config.json` ✓ / `workspace` ✓ / `libero.json` ✓ / `trace.db`、`evals/` 也会落这里）；`roborsi onboard` 已执行，硬件扫描：0 串口、0 相机 |
| 模型 provider | 全部 `not set`，默认模型 `anthropic/claude-opus-4-5` → **`eval` 之前必须先配 key** |

## 2. 两次 doctor 实测结果

命令：

```bash
cd /workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/roborsi_runtime && source env.sh
# A. 官方默认路径（不设 MUJOCO_GL，代码里默认 egl）
MUJOCO_GL= time roborsi libero doctor --backend libero --task libero_object/0 --reset --json
# B. 显式 CPU 软渲染（env.sh 默认就是这个）
time roborsi-doctor libero_object/0 0
```

| | A：默认（egl） | B：osmesa |
| --- | --- | --- |
| 退出码 | 0 | 0 |
| 墙钟耗时 | **2 m 22 s**（user 31 s） | **2 m 52 s**（user 41 s） |
| `rendering` 字段 | `{"backend": "egl", "egl_vendor": "system"}` | `{"backend": "osmesa"}` |
| `importable` | true | true |
| `backend.available` | true | true |
| `task_count` | 40（4 个 suite × 10 任务） | 40 |
| `reset.ok` | true | true |
| stderr 里 error/traceback | 0 行 | 0 行 |

reset 冒烟返回的内容（两次一致）：

```json
{"ok": true, "task": "libero_object/0", "seed": 0,
 "instruction": "pick the alphabet soup and place it in the basket",
 "images": ["head_camera", "wrist"], "state_size": 39}
```

`visible_raw_keys`（暴露给 agent 的观测键）：
`agentview_image` / `agentview_depth` / `robot0_eye_in_hand_image` / `robot0_eye_in_hand_depth` /
`robot0_eef_pos` / `robot0_eef_quat` / `robot0_joint_pos` / `robot0_joint_pos_cos` /
`robot0_joint_pos_sin` / `robot0_joint_vel` / `robot0_gripper_qpos` / `robot0_gripper_qvel` /
`robot0_proprio-state`

**注意里面没有任何 `object*` 键** —— 这正好现场验证了 `docs/roborsi-callchain.md` §3 说的
"ground-truth 防火墙"：LIBERO-PRO 建模时需要 object observable（`use_object_obs=True`），
但 adapter 在边界上用 `_visible_raw_obs()` 把物体真值全部删掉了。

### 关于 `egl_vendor: "system"`

这一条是本次最有信息量的输出：RoboRSI 的 `configure_headless_rendering()`
（`roborsi/embodied/sim/libero/runtime.py:150`）只在 `find_library("EGL_nvidia")` 成功时才写
`~/egl-vendor/10_nvidia.json`。本机没有 `libEGL_nvidia.so.0`，所以它退回 system ICD = Mesa，
最终 `GL_RENDERER = llvmpipe`。**也就是说官方默认路径不会报错，而是静默用 CPU 渲染**，
渲染期间 `nvidia-smi` 是 0% 利用率。详见 `docs/infra-gpu-render.md` §2.3。

耗时解读：2m22s 里 user CPU 只有 31s，绝大部分是导入 + LIBERO 资产/模型构建的 I/O 与等待，
不是渲染。所以**这个数字不能用来估算 rollout 吞吐**，真正跑 episode 的成本要另测。

### 跨 suite 交叉验证（确认不是只有 `libero_object` 碰巧能跑）

```bash
MUJOCO_GL=osmesa roborsi libero doctor --backend libero --task libero_spatial/3 --reset --seed 1 --json
```

结果：退出码 0，`reset.ok = true`，耗时 **2 m 58 s**（user 40 s），
指令 `pick the akita black bowl on the cookies box and place it on the plate`，
`images` 与 `state_size` 与 `libero_object/0` 完全一致。
说明 `task_count = 40`（`libero_spatial|object|goal|10` × 10）都能用同一套配置驱动。

## 3. 安装过程踩的坑（按代价从大到小）

### 3.1 `pip install -e ".[libero]"` 会去下载 530 MB 的 CUDA torch（最大坑）

RoboRSI 的核心依赖里有 `lerobot[feetech,dynamixel,pi]`，而 lerobot 要求 `torch>=2.7,<2.12`。
解析器因此否掉先装的 `torch 2.6.0+cpu`，转去拉 `torch-2.11.0-cp312-manylinux_2_28_x86_64.whl`
（530 MB，还会连带 `nvidia-*` 一堆 CUDA 运行库）。本机镜像只有 ~300–600 KB/s，
实测 33 分钟仍没下完，而且这台机器根本没有 GPU 渲染栈，CUDA 版 torch 毫无收益。

解决：`pip install -e . --no-deps` 装本体，再手动装 pyproject 里 `libero` extra 的原始清单
+ CLI 导入链需要的那几个包（typer/rich/pydantic/litellm/openai/mcp/…），
跳过 `lerobot`、`flexivrdk`、`record3d` 和 IM SDK。代价是 `roborsi task`（π₀ 微调）
和真机相机相关命令不可用——本机本来也跑不了。

CLI 之所以要装这么多：入口是 `roborsi.cli.commands:app`，它在模块级 import 了全部子命令
（`dev/camera/skill/sim/task/farm/libero/skill_tiers/bench/bench_lh/selfevo`），
任何一个的顶层依赖缺失都会让 `roborsi libero doctor` 直接起不来。

### 3.2 hf-mirror 429 限流，且 `hf download` 限流时仍返回 0

第一次下载在 609 个文件后被 429 打断；重试时 `hf download` 打印
`Returning existing local_dir ... as remote repo cannot be accessed (429 ...)` 然后**退出码 0**。
按退出码判断会误以为下全了（实际 `init_files` 一个都没有）。

解决：`--max-workers 1` 降并发 + 循环重试，并且**用文件数判断完成**（`init_files` 下全 230 个才算完），
不看退出码。实测第 3–5 次尝试后限流解除，全部下完（总共才 15 MB，不是瓶颈）。

顺带一个好消息：LIBERO-PRO 仓库自带 554 个 `.pruned_init`，
`_load_init_states()`（`adapter.py:694`）在没有 `ROBORSI_LIBERO_INITDIR` 时会回退到
`<checkout>/libero/libero/init_files`，所以**只跑 `libero_object` 的话 HF 资产不是必需的**。

### 3.3 `/workspace/mnt/sppro` 是 NFS，不能当工作目录

`cp -a` 60 MB 的源码树到 NFS 上跑了 2 分钟还没完（`du` 都会卡）。
挂载信息：`v4nassg02...:/mnt/Volume_01/... sppro nfs 1.1P 94%`。
RoboRSI/LIBERO-PRO 这类"几万个小文件 + 频繁 import"的东西必须放本地盘（这里用 `/root/roborsi_trial`），
只把笔记和脚本放回工作区仓库。

### 3.4 `--json` 的输出不是纯 JSON

`roborsi libero doctor --json` 的 stdout 前面会混进 LIBERO 自己的日志：
`[info] Applying task order index 0 (permutation: [...]) for benchmark 'libero_goal' (10 tasks).`
解析时要先定位第一个 `{`：

```python
raw = open("doctor.json").read(); d = json.loads(raw[raw.find("{"):])
```

### 3.5 litellm 每次启动都去拉远端价格表

`roborsi status` / `doctor` 启动时 litellm 会访问
`raw.githubusercontent.com/BerriAI/litellm/.../model_prices_and_context_window.json`，
本机访问不到，超时重试 3 次约 20 s 后才回落本地备份。
设 `export LITELLM_LOCAL_MODEL_COST_MAP=True` 直接跳过，CLI 明显变快。

### 3.6 无害但要认识的告警

- `Gym has been unmaintained since 2022 and does not support NumPy 2.0` —— 环境里是
  `gym 0.25.2` + `numpy 2.2.6`，实测 doctor 全绿，可以先不管；若后续 LIBERO 某处真的踩到
  numpy 2 的 API 变化，再把 numpy 降到 `<2`。
- `[robosuite WARNING] No private macro file found!` —— 首次运行的正常提示，
  想消掉就执行它给出的 `robosuite/scripts/setup_macros.py`。
- torch 首次导入会告警 `Failed to initialize NumPy`（装 torch 时 numpy 还没装），装完就没了。

## 4. 下一步：要跑 `eval` 还差什么

`configure` / `doctor` 不需要模型；`eval` 需要三个角色（Planner / Engineer / Reviewer）都要调 LLM。

1. **配 provider**：`roborsi provider login openai-codex`（OAuth）或在 `~/.roborsi/config.json`
   里填 `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` 等；`roborsi status` 确认 `Model` 与 provider 不再是 `not set`。
2. **先用最小预算跑一次**，别碰 `scripts/reproduce_libero_pro.sh`（那是完整 campaign）：

   ```bash
   cd /root/roborsi_trial/RoboRSI
   export LITELLM_LOCAL_MODEL_COST_MAP=True MUJOCO_GL=osmesa
   roborsi eval libero_pick_place --backend libero --sim-task libero_object/0 \
     --seeds 1 --tool-budget 10
   ```

   `--seeds 1 --tool-budget 10` 是为了先看清一轮调用链，而不是出成绩。
3. **看产物**：`~/.roborsi/evals/manifests/` 下的 campaign manifest、每次运行的
   `plan.md` / `summary.md` / `review.md`、以及 `trace.db` 里的工具调用与耗时；
   `roborsi eval-audit` 可以独立重算分数。
4. **成本预期**：渲染在 CPU 上（llvmpipe），256px + depth 每帧几十毫秒量级；
   一个 episode 数百步 + 每个工具调用可能触发 VLM 看图，所以**单 seed 的墙钟和 token 都要先实测再放量**。
   先测一次单 seed 的耗时与 token，再决定 seeds 数量。
5. PyRoKi IK/轨迹服务（官方 reproduce 脚本会用 ZMQ 起一个常驻服务）在 `configure`/`doctor`
   阶段用不到；等到跑需要 IK 的技能时再按 `docs/INSTALLATION.md` 单独建 `.venv-pyroki`。

## 5. 复现命令速查

```bash
# 全新一键（约 20-40 分钟，取决于镜像速度）；代码/环境装本地盘，资产与 home 装工作区
bash scripts/install_roborsi_minimal.sh

# 已有环境时的日常验证（全部走工作区入口）
cd /workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/roborsi_runtime && source env.sh
roborsi status
roborsi-configure                     # 写 home/.roborsi/libero.json
roborsi-doctor libero_object/0 0      # 换任务/换 seed: roborsi-doctor libero_spatial/3 1
roborsi-doctor libero_goal/2 3        # 4 个 suite 已验：object / spatial / goal
```

## 6. 目录布局：什么必须留本地盘，什么进工作区（2026-09-22 追加）

初版我把所有东西都放在 `/root/roborsi_trial`（工作区之外），这不合适。重排后的原则是：
**被 Python import 的东西留本地盘，配置/产物/资产/日志全部进工作区。**

| 内容 | 位置 | 文件数 / 体积 | 为什么 |
| --- | --- | --- | --- |
| conda 环境 | `/opt/conda/envs/roborsi`（本地） | 65618 / 3.0 GB | 放 NFS 光写入约 2 小时，且每次 CLI 启动都要 stat 成千上万个文件 |
| RoboRSI 源码（editable 安装目标） | `/root/roborsi_trial/RoboRSI`（本地） | 1533 / 61 MB | `roborsi` CLI 在模块级 import 全部子命令，NFS 上每次启动都会明显变慢 |
| LIBERO-PRO 检出 | `/root/roborsi_trial/LIBERO-PRO`（本地） | 2359 / 911 MB | 同上，`libero.libero` 是被 import 的 Python 包 |
| LIBERO-Pro 资产 | **工作区** `../roborsi_runtime/LIBERO-PRO-assets` | 2029 / 15 MB | 只在建环境时按任务读单个文件，实测无额外代价 |
| RoboRSI home（配置 / trace.db / evals / workspace） | **工作区** `../roborsi_runtime/home/.roborsi` | 小 | 这些是"我们的产物"，必须在自己目录里 |
| 运行日志 | **工作区** `../roborsi_runtime/logs` | 小 | 同上 |

入口有两个，等价：

```bash
source ../roborsi_runtime/env.sh      # 交互式：设好变量并把 bin/ 加进 PATH
../roborsi_runtime/bin/roborsi status # 脚本 / timeout 里：直接用可执行包装器
```

`bin/roborsi` 是**真正的可执行文件**（不是 shell 函数，所以 `timeout roborsi ...` 也能用），
它用 `env` 前缀在单条命令作用域内覆盖 `HOME` / `ROBORSI_HOME`，
于是 `config.json`、`trace.db`、`evals/` 全落到工作区，而同一个 shell 里的 `pip` / `git`
仍用原来的 `HOME`（缓存不会被写到 NFS）。另有 `bin/roborsi-configure`、
`bin/roborsi-doctor [task] [seed]` 两个快捷包装。

> 为什么要覆盖 `HOME` 而不是只用 `ROBORSI_HOME`：`roborsi/embodied/paths.py:21` 支持
> `ROBORSI_HOME`，但 `store/trace_db.py:131`、`agents/workspace.py:22`、`cli/commands.py:127`
> 等处硬编码了 `Path.home()/".roborsi"`，只有覆盖 `HOME` 才能把 `trace.db` 一起收进工作区。

### NFS 小文件实测（决策依据）

同一台机器，2000 个 1 KB 文件：

| 操作 | 本地盘 `/root` | 工作区 NFS | 倍数 |
| --- | --- | --- | --- |
| 写 | 0.48 s | 216.78 s | 453× |
| 读 | 0.12 s | 45.66 s | 387× |
| stat | 0.02 s | 35.04 s | **2083×** |

`/workspace/mnt/sppro` 是 NFS（1.1 P，已用 94%），`/` 是 overlay 本地盘（7 T，已用 14%），
`/dev/shm` 是 tmpfs（113 G，快但重启即失且吃内存），`/workspace/cache/yhzhang91` 是 fuse 对象存储。

### 混合布局的验证结果

资产与配置迁到工作区、代码与环境留本地盘之后重跑：

| 命令 | 结果 | 耗时 |
| --- | --- | --- |
| `roborsi-configure`（资产指向工作区） | `ok: true`，`libero.json` 写入工作区 | **3.5 s** |
| `roborsi libero doctor --task libero_object/0 --reset` | `importable/backend/reset` 全 true，`task_count=40` | **2 m 52 s** |
| `roborsi status`（走 `bin/roborsi` 包装器） | Config / Workspace 均指向工作区且为 ✓ | 数秒 |

与"全部在本地盘"时的 2 m 52 s / 2 m 22 s 没有可感知差异 —— 因为 doctor 只按需读
当前任务的那几个 bddl / init 文件，不会遍历 2029 个资产文件。
