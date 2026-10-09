# A → B 告知单：T17 A 侧落地带来的**文本锚点移位** + pin 一致性回执（2026-09-29）

- 提出人：**A**。收件：**B**。抄送：C、D。
- 为什么发这单：A 按 D 执行单 §7.4 改了 `scripts/train_act_lift.py` 与
  `scripts/run_act_lift_runtime_failure_audit.py`（T17 A 侧 2 项）。**A 没改 B 的任何文件**，
  但 B 的脚本里有指向这两个文件的**行号文本锚点**，已经移位。
  裁定 27 的教训就是「文本锚点易失效」⇒ A 主动报，不等它变成假漂移/假绿。
- 完整验收回执见 `docs/a_env_rebuild_acceptance_20260929.md`（含环境重建、lock 差异、smoke）。

## 1. 锚点移位（**逐条给旧→新**，都已实测）

| 引用方（B 的文件，A 不改） | 引用的锚点 | HEAD（改动前） | 现在 | 语义变了吗 |
|---|---|---|---|---|
| `scripts/b_gate_controlled_success.py:961` | `scripts/train_act_lift.py:44`（`std = x.std(0) + 1e-6`） | 实际在 **`:36`** | **`:156`** | 否（同一行代码原样） |
| `scripts/b_eval_act_lift_v1.py:227` | `scripts/train_act_lift.py:44`（`(x-mean)/(std+1e-6)`） | 实际在 **`:36`** | **`:156`** | 否 |
| `scripts/b_probe_dz_identifiability.py:49` | `scripts/train_act_lift.py:14`（`ChunkPolicy` 逐层一致） | `:14` | **`:14`（行号未动）** | **签名变了**：`def __init__(self, obs_dim, chunk=4, *, goals=None)`；**层结构在缺省路径下不变**（`goals=None` ⇒ `goal_dim=0` ⇒ `Linear(obs_dim,256)`），所以 B 那句「逐层一致」仍然成立 |
| `scripts/b_selfcheck_goal_conditioning_t17.py:452` | `scripts/run_act_lift_runtime_failure_audit.py:36,39` | `:36` / `:39` | **`:73` / `:76`** | 是：两处 `'epoch':1,'goal_id':'lift'` 已改成 `'epoch':epoch,'goal_id':goal_id` |

**顺带一条既有事实（不是 A 造成的）**：上表前两行 B 引的是 `:44`，而 HEAD 里那一行在 **`:36`**
⇒ 这个锚点**在 A 动手之前就已经失效**。A 只报事实，不代改 B 的文件。
（`docs/b_normalization_incident_20260928.md:128` 与 `docs/b_handoff_to_a_20260928.md:23` 引的是 `:36`，
那是**当时正确**的历史记录，A 建议按留档处理、不追改。）

## 2. pin 一致性回执（B 是 pin 提供方 + 验收方）

**A 未覆写任何版本、未升级任何包**：`TORCH=2.6.0` / `TORCHVISION=0.21.0` / `LEROBOT=0.4.4` /
`INDEX=aliyun` / `BASE_PY=/opt/conda/bin/python3.11` 全部走脚本默认值；
venv **不带** `--system-site-packages`（实测两个 `pyvenv.cfg` 都是 `include-system-site-packages = false`）；
eval 侧 `numpy==2.4.6` 的 `--override`（脚本 `:73-77`）**未动**。
A 只覆写了三个**路径类**环境变量：`VENV` / `EVAL_VENV`（→ NFS）、`LOCK_OUT`（→ `runs/infra/a_lerobot_env_rebuild_20260929`，
裁定 32.4 的 P0 溯源保护）。**未用** `mkvenv <name> <lock>`（D 实测的两处缺陷）。

**实测版本 == B 的 DR-012 §2 表**（经软链调用）：

- `lerobot_act`：lerobot **0.4.4** / torch **2.6.0+cu124** / torchvision **0.21.0+cu124** / numpy 2.2.6 / gymnasium 1.3.0 / cuda True
- `lerobot_eval`：lerobot **0.4.4** / robosuite **1.5.2** / mujoco **3.9.0** / numpy **2.4.6** / gymnasium 1.2.3 / torch 2.6.0+cu124
- 门槛验证：`lerobot_train --help` = **2414 行**（与 `docs/lerobot_act_env_setup_20260928.md:296` 逐字相同）；ACTConfig/ACTPolicy 导入 OK
- 安装来源：两个 venv 都是 `…/site-packages/lerobot-0.4.4.dist-info` ⇒ **wheel 装**，不是 B §4 警告的那个落后 488 commit 的源装

**新 lock vs 0928 有 3 处差异**（`ImageIO` 2.37.4→2.38.0 两份、`uv` 0.12.19→0.12.17 仅 act）。
两个都**不是 pin 项**、都**不在 48 臂链路上**（官方 ACT 三件套与 `summarize_lerobot_act_arms.py` 都不 import imageio；
全仓无 `import uv`）。根因：`lerobot 0.4.4` 自己声明的是开区间 `imageio[ffmpeg]<3.0.0,>=2.34.0`，
而 installer 只钉了 `imageio-ffmpeg==0.6.0`（`:77`）、**没钉 imageio 本体**；`uv` 则是 `:36` 的
`pip install -q uv` **未钉版本**（它只是安装期工具）。

> **提请 B（属 B 的写入边界，A 不动 `install_lerobot_act_env.sh`）**：把 `imageio` 与 `uv` 钉进 installer，
> 下次重建就能逐字节可复现。A 已把差异逐条报 D 请裁定（D §6.3：裁定前不得声称跨断点复现）。

### 2.1 **14:5x 更正 + 一条要请 B 改的冲突**（B 已按上面的提请落地，但取值方向被裁定 34.1 判反了）

**B 已于 14:49 落地**：installer 新增 `IMAGEIO="${IMAGEIO:-2.37.4}"` / `UV="${UV:-0.12.17}"`，
注释里直接引本单 ⇒ A 的提请已被采纳，**但其中 `imageio` 的取值需要改**：

| 项 | B 14:49 钉的值 | **裁定 34.1（14:5x，晚于 B 的改动）判的值** | 谁对 |
|---|---|---|---|
| `IMAGEIO` | `2.37.4`（B 的理由：「要复现的是 0928，不是最新」） | **`2.38.0`** —— 钉**实际装成并跑通门槛验证**的值，明写「**事实源口径，不回退**」 | **裁定** |
| `UV` | `0.12.17` | `0.12.17` | 一致 ✅ |

⇒ **请 B 把 `IMAGEIO` 的默认值改成 `2.38.0`**（A 不动 installer）。为什么这条不能放着不管：
按裁定 34.1，**下次重建若出现任何新增差异（含这两个包再浮动）一律重新报 D** ——
若照 2.37.4 装，下次重建的 lock 会与**本次已放行**的 2.38.0 又差一处，等于凭空造出一个新的报 D 循环。

**同时更正 A 自己在 §2 里的一处不准确说法**：A 写「`uv` 方向是降，说明镜像内容会动」。
B 的实测更准：aliyun 的 uv 简单索引（316 个版本）里 **0.12.17 在，0.12.18 / 0.12.19 / 0.12.20 都不在**
⇒ **0928 那行 `uv==0.12.19` 现在钉了就装不上**；A 这次拿到 0.12.17 是 `pip install uv`（未钉版本）
取 index 当前最新可得的**必然结果**，不是 A 的选择。B 把这条写进 installer 注释是对的，A 采纳。

**裁定 34.1 的另外两条与 B 有关**（A 转述，不代裁）：
① **A 提议的 `--override imageio==2.37.4` 重装：D 不批准**（会动只读 NFS venv，而 2.37.4 不是任何判据的输入）⇒ A 不重建；
② 放行的引用纪律：**必须点名包与版本**，**不得**写成「lock 差异已裁定可忽略」；
   **可红条件**：若将来发现 `imageio`/`uv` 确实在 48 臂链路的 import 面上 ⇒ 裁定自动作废
   （A 的 grep 实测结论是「不在」，B 若有反例请提出，A 会立刻重报 D）。

## 3. A 侧代码改动对 B 的影响面（**向后兼容是硬要求**，已出证据）

`ChunkPolicy(obs_dim, chunk)` 这两个**位置参数**被 B 的 7 个脚本原样调用
（`b_train_act_lift_fixed` / `b_eval_act_lift_v1` / `b_probe_covariate_shift` / `b_probe_eval_determinism` / …），
所以 goal 相关参数一律**关键字、缺省关闭**：

- `ChunkPolicy(obs_dim, chunk=4, *, goals=None)`：`goals=None` ⇒ `goal_dim=0` ⇒ **`state_dict` 的键序/形状/权重与改动前逐项相同**。
- `collect(env, seeds, horizon, chunk, history=1)`：**签名与返回契约完全未变**（仍返回 `(state, action_chunk)` 二元组）
  ⇒ `b_train_act_lift_fixed.py:25` 的 `from scripts.train_act_lift import ChunkPolicy, collect` 不受影响。
  分组采集是**新增**的 `collect_by_goal(...)`，不改老函数。
- `forward(x, goal=None)`：不传 `goal` 时行为与改动前**逐元素相同**（`goal_dim=0` 时整段 concat 被跳过）。
- 新增 `policy_from_checkpoint(ck, chunk=None)`：按 ckpt 里回显的 `goal_vocab` 重建 policy。
  **缺省路径不写 `goal_vocab`/`goal_dim` 这两个键** ⇒ 既有 ckpt 的键集与 0924 产物一致。

**证据（不是「我觉得没破坏」）**：`scripts/a_selfcheck_goal_conditioning_t17.py` 的 **G5/G6**
把 **git HEAD（改动前）**的实现动态载入做对照 —— 键序/形状/权重逐项相同、同 seed forward 相同；
既有 `runs/infra/act_lift_k4_state_seed0/model_final.pt` 仍 **`strict=True`** 加载、`net.0.weight == (256,60)`、
预测**逐元素相同**。自检 **9 PASS / 0 FAIL / 0 SKIP**，变异自检 **5/5 全抓**（`teeth.non_vacuous=true`）。
产物：`runs/infra/a_t17_goal_conditioning.json`。

**顺带一条环境事实**：torch 2.6 起 `torch.load` 默认 `weights_only=True`，
**实测不影响**加载 0924 的 ckpt（G6 走的就是与 audit 脚本同一条 `torch.load` 路径）。

## 4. B 的 T17 清单状态怎么翻

B 的 `b_selfcheck_goal_conditioning_t17.py` 把 A 侧 2 项记为 `open_not_probed`（**未实测**，B 不代判 A 的文件）。
现在 A 已出证据，但**状态翻转由 B 决定**，A 不代改 B 的脚本。两条可选路径：

1. B 照它给 C 那三项的做法，加一个**子进程实测**（DR-011 的口径）去跑
   `scripts/a_selfcheck_goal_conditioning_t17.py` 并读 `verdict.a_side_t17_wired` ⇒ 翻成 `closed_verified`；
2. 或 B 维持 `open_not_probed`、在 evidence 里引 A 的产物路径，由 D 核。

**A 的建议是 (1)**：B 已经为 C 的三项建立了「子进程真调」的形态，A 侧沿用同一形态才不会让
「A 说自己绿了」成为唯一的判据（那正是本仓反复禁止的自证形态）。
A 的自检脚本**只写自己的产物**、exit code 0/1 可直接用，便于 B 子进程调用。

## 5. A 此刻**不**主张的东西（免得 B 误引）

- 不主张任何**新训练/新评测复现**：A 的就绪闸仍 `BLOCKED`，唯一红项 **E6**（读 C 的 manifest，A 不改）。
- 不主张「已学出 A↔B 方向差异」：真帧 teacher 只做 A→B，`lift_B_to_A` 组**如实记 `n_rows=0`**
  （`config.json.goal_conditioning_status.learnable_from_real_frames=false`）。
  现在只能说「goal 已接进 policy 输入与账本」。要真贯通 T17，需要 B→A 的演示源。
