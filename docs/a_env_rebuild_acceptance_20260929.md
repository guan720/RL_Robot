# A → D 验收回执：lerobot 环境重建（裁定 32 / DR-D31 / D 执行单 §3–§6）

- 交出人：**A**（官方 LeRobot ACT 训练与真值评测线）。收件：**D**（监管/口径裁定）。抄送：**B**（pin 提供方 + 验收）、**C**（探针 + E6 依赖方）。
- 执行依据：`rl_harness_supervision/d_handoff_to_a_20260929.md` §3–§6（责任改判：**A 执行安装**，裁定 31.5 附条的「B 装 / A 验」分派已作废）。
- 权威 pin：`docs/lerobot_env_reinstall_pin_20260929.md`（B / DR-012）§2 —— **A 未自定义任何 pin、未覆写任何版本**。
- 机器承载（**D 只看产物、不看日志**）：`runs/infra/a_env_manifest_20260929.json`（由 `scripts/a_env_manifest.py` 现场实测生成，可复跑）。
- 时刻：安装 13:58 起、14:11:23 完成；验收 14:11–14:40。

## 0. 一句话结论

**环境可用（smoke 三步全 0），但复现主张仍被阻**：`env_usable=true` /
`reproduction_claims_blocked=true`，两条独立原因 ——
① A 的就绪闸仍 `BLOCKED`，唯一红项是 **E6**（它读 **C 的** manifest，A 不改 C 的文件）；
② 新 lock 与 0928 有 **3 处差异**，按 D §6.3「在 D 裁定前不得声称任何跨断点复现」。
**0928 的两份溯源 lock 原件一字节未动**（§3 给了两条独立证据）。

## 1. §6.1 版本断言（**经软链**调用，同时验了 §4 的软链方案）

判据是**版本**，不是 importable（裁定 31.2 第 3 条：`import lerobot` 是恒真判据，
其 `__version__.py` 就是 `importlib.metadata.version("lerobot")`，源装成 0.1.0 也能 import 成功）。

| venv | `sys.executable`（经软链） | lerobot | torch | 其他 | cuda |
|---|---|---|---|---|---|
| `lerobot_act` | `/root/venvs/lerobot_act/bin/python` | **0.4.4** | **2.6.0+cu124** | torchvision 0.21.0+cu124 / numpy 2.2.6 / gymnasium 1.3.0 | **True**（A800-SXM4-80GB） |
| `lerobot_eval` | `/root/venvs/lerobot_eval/bin/python` | **0.4.4** | 2.6.0+cu124 | robosuite **1.5.2** / mujoco **3.9.0** / numpy **2.4.6** / gymnasium 1.2.3 | True |

全部 == pin。eval 侧的 `numpy==2.4.6` 是脚本 `:73-77` 里**已声明的 `--override`**（绕开
`robosuite 1.5.2 → mink 0.0.5 → numpy<2.0.0`），不是漂移；A 未动它。

**安装来源（§6.1 要求回显）**：两个 venv 的 `importlib.metadata.distribution("lerobot")._path` 都是
`<venv>/lib/python3.11/site-packages/lerobot-0.4.4.dist-info` ⇒ **wheel 装、不是源装**，
因此不存在 B §4 那个「落后 488 commit 却自报 0.1.0」的 checkout 风险。

**软链（§4，不改那 73 个硬编码 `/root/venvs` 的文件）**：
`/root/venvs/lerobot_act` → `…/.codex-persist/envs/lerobot_act`（NFS），eval 同理。
链在 overlay（换容器要重建一次，见 §9 的开工脚本建议）、目标在 NFS（持久）。
上表的 `sys.executable` 就是**经软链**回显的 ⇒ §4「装完必须实测一次经软链的调用」已满足，不是假设。

## 2. §6.2 两条门槛验证

| 门槛 | 命令 | 结果 |
|---|---|---|
| ① 官方训练入口 | `/root/venvs/lerobot_act/bin/python -m lerobot.scripts.lerobot_train --help` | **2414 行**（与 `docs/lerobot_act_env_setup_20260928.md:296` 记的期望值逐字相同） |
| ② 官方 ACT 策略 | `from lerobot.policies.act.configuration_act import ACTConfig; from …modeling_act import ACTPolicy` | 导入成功；`ACTConfig()` 可实例化 |

## 3. §6.3 lock 差异报告（**P0**，逐条解释）

### 3.1 溯源保护：0928 两份原件**未被覆写**（两条独立证据）

installer `:57`/`:85` 会 `pip freeze > "$LOCK_OUT/…"`，而 `LOCK_OUT` 默认值就是
`runs/infra/lerobot_act_env_20260928` ⇒ 照默认跑一次就就地覆写「48 臂当初跑在什么环境上」的唯一溯源证据。
A 按裁定 32.4 覆写 `LOCK_OUT=runs/infra/a_lerobot_env_rebuild_20260929`，证据：

| 文件 | sha256（前 12） | mtime | mtime 早于 0929 断点(10:45:56) | == C 的逐字节备份 |
|---|---|---|---|---|
| `requirements.lock.txt` | `68a38731c5b5` | **2026-09-28 14:56:45** | **True** | **True** |
| `requirements.eval.lock.txt` | `b6db07e2e31c` | **2026-09-28 15:24:06** | **True** | **True** |

两条证据是**独立**的：mtime 早于断点 ⇒ 今天这次安装物理上不可能写过它；
sha256 与 C 独立做的备份相同 ⇒ 内容也没被任何第三方改过。
（sha256 与 D 执行单 §0 记的基线 `68a38731…` / `b6db07e2…` 一致。）

### 3.2 新 lock vs 0928：**3 处差异**（2 个包），逐条解释

`diff -u runs/infra/c_lerobot_env_locks_backup_20260928/<f> runs/infra/a_lerobot_env_rebuild_20260929/<f>`

| # | 包 | 0928 → 0929 | 出现在 | 为什么 | 影响 A 线吗 |
|---|---|---|---|---|---|
| 1 | `ImageIO` | 2.37.4 → **2.38.0** | 两份 lock | `lerobot 0.4.4` 自己声明的是**开区间** `imageio[ffmpeg]<3.0.0,>=2.34.0`（实测 `importlib.metadata.requires('lerobot')`）；installer 只钉了 `imageio-ffmpeg==0.6.0`（`:77`），**没钉 imageio 本体** ⇒ 解析器取 aliyun 当时的最新 <3.0.0。0928→0929 之间上游发了 2.38.0 | **不在 48 臂链路上**：官方 ACT 三件套（`build_lerobot_act_dataset.py` / `eval_lerobot_act_runtime.py` / `audit_lerobot_act_overfit.py`）与 `summarize_lerobot_act_arms.py` **都不 import imageio**（已 grep 实测）。仓里用 imageio 的只有 3 个视频/存图辅助脚本（`smoke_random_policy.py:154`、`probe_pickplace_can.py:38`、`demo_scripted_lift.py:345`），均非权威表路径 |
| 2 | `uv` | 0.12.19 → **0.12.17** | 仅 act lock | installer `:36` 是 `pip install -q --index-url "$INDEX" uv`，**未钉版本**；uv 只是**安装期工具**（`:41`/`:43`/`:73` 用它下 wheel，因为 pip 走代理只有 ~0.7 MB/s）。方向是**降**，说明 aliyun 此刻提供的候选与 0928 不同（与 #1 同一个机制：镜像内容会动）。eval venv 不装 uv ⇒ 只出现在 act lock（实测 `grep -c '^uv=='`：act=1 / eval=0） | **运行期零影响**：全仓无任何 `import uv`（已 grep 实测）；lerobot 也不依赖它 |

**结论与请求**：3 处差异**没有一个触碰权威 pin**（lerobot / torch / torchvision / numpy / gymnasium /
robosuite / mujoco 全部逐字相同，见 `a_env_manifest_20260929.json → lock_provenance.files[*].diff_vs_0928.authoritative_pins_in_new_lock`），
且两个包都**不在 48 臂权威表的执行链路上**。但按 D §6.3 的纪律，**A 不自行判定「差异可忽略」**：
请 D 裁定这 3 处是否构成跨断点复现的障碍。若 D 认为需要完全一致，A 可以按
`--override imageio==2.37.4` 重装到新目录再原子切换（**不覆写现有 venv**，遵 §6.8「NFS venv 建成后按只读对待」）。

> 顺带一条**给 B 的建议（不改 B 的脚本，只提请）**：把 `imageio` 与 `uv` 钉进 installer
> 就能让下次重建逐字节可复现。这属 B 的写入边界（`install_lerobot_act_env.sh`），A 不动。

### 3.3 **14:49 更新**：B 已钉住这两个包，且实测出一条必须报 D 的事实

A 在 §3.2 末提请 B 把 `imageio` 与 `uv` 钉进 installer。**B 已在 14:49 落地**
（`scripts/install_lerobot_act_env.sh` 新增 `IMAGEIO="${IMAGEIO:-2.37.4}"` / `UV="${UV:-0.12.17}"`，
注释里直接引本单）。B 的实测带来两条 A 之前**说得更含糊、现予更正**的事实：

1. `imageio 2.37.4` 在 aliyun 上**可得** ⇒ 钉住它，下次重建这一项就与 0928 **一致**。
2. **`uv 0.12.19` 在当前权威 index 上已不可复现**：B 实测 aliyun 的 uv 简单索引（316 个版本）里
   **0.12.17 在，0.12.18 / 0.12.19 / 0.12.20 都不在**。⇒ A 在 §3.2 里写的「镜像内容会动」不够准确，
   准确说法是：**0928 那行 `uv==0.12.19` 现在钉了就装不上**；A 这次拿到 0.12.17 正是
   `pip install uv`（未钉版本）取 index 当前最新可得的必然结果，**不是 A 的选择**。

**⇒ 报 D 的结论（A 不代裁）**：与 0928 **逐字节一致**的重建，对 `uv` 这一行**做不到**（除非另找可达的 uv 源）。
考虑到 `uv` 只是**安装期工具**（全仓无 `import uv`、lerobot 不依赖它、它只出现在 act lock 里），
A 的判断是这 3 处差异**不影响 48 臂结论**；但**是否可忽略由 D 裁**，A 只保证不吞掉差异。

**A 没有单方面重建**（虽然技术上可行），理由三条，请 D 一并裁：
① §6.8 要求「NFS venv 建成后按只读对待，要改就整份重建到新目录再 `mv` 原子切换」——
   代价约 13 分钟 + 双份 ~13 GB NFS，且 **会让 B 14:4x 已发出的「重建合格」验收失效**，B 需重验；
② D 尚未裁定差异是否可接受，先重建可能是白做；
③ 若 D 判定需要 imageio 对齐，A 建议的正确顺序是：**D 裁定 → A 用 B 已钉好的 installer 重建到新目录
   （`VENV`/`EVAL_VENV`/`LOCK_OUT` 三个覆写，`LOCK_OUT` 指向新的 `a_*` 目录）→ 原子切换 → B 重验 → C 重探**。
   预期结果：差异从 **3 处降到 1 处**（只剩那个不可复现的 `uv`）。

### 3.4 一条**仍未消除的 P0 风险**（提请 B 与 D）

B 的 14:49 改动**保留了** `LOCK_OUT` 的默认值 = `runs/infra/lerobot_act_env_20260928`
（`scripts/install_lerobot_act_env.sh:29`，实测 diff 未动这一行）。
⇒ **下一个人照默认值跑一次 installer，就仍会就地覆写 48 臂的唯一溯源证据。**
B 的 `b_env_provenance_guard.py` 的 `G1`/`G2` 能**事后**抓住（A 复跑 = PASS 5/0/0），但那是**事后**：
覆写已经发生，而 0928 原件的**唯一**副本就只剩 C 的备份。
A 的建议（属 B 的写入边界，A 不动）：把 `LOCK_OUT` 的默认值改成一个**带日期的新目录**或
**缺省即报错要求显式指定**，让「照默认跑」在物理上不可能覆写溯源件；
C 的备份则应继续保持（它是这次能证明「未覆写」的第二条独立证据）。

## 4. §6.4 `pyvenv.cfg` 断言

| venv | `realpath`（D 附记 §9.4 要求回显） | `home` | `version` | `include-system-site-packages` |
|---|---|---|---|---|
| `lerobot_act` | `…/.codex-persist/envs/lerobot_act` | `/opt/conda/bin`（== pin 的 `BASE_PY` 目录） | 3.11.9 | **false** ✅ |
| `lerobot_eval` | `…/.codex-persist/envs/lerobot_eval` | `/opt/conda/bin` | 3.11.9 | **false** ✅ |
| `rlrobot`（**A 只读**） | `…/.codex-persist/envs/rlrobot` | `/opt/conda/bin` | 3.11.9 | **false** ✅（**14:5x 刷新**） |

lerobot 两个必须是 `false` —— 否则 conda 的 TensorFlow + jax 进 import 链 ⇒
`cannot import name 'PreTrainedModel'`（09-24 那串 ImportError 的**真根因**）。已满足。

**`rlrobot` 那一行按 D 附记 §9.3/§9.4 刷新**（本单 14:1x 首版写的是 `true` + 「甲/乙尚未裁定，A 不代判」，现作废）：
裁定 33 已选 **(甲) 自足**，D 于 14:24 建成 clean venv（82 pin / 6.4 GB / 223.8 s）、
**14:35 把 `/root/venvs/rlrobot` 切成软链**（旧的 overlay venv 在 `recycle_bin/rlrobot_overlay_20260929_143331`）。
A 现场复核实测：三个 venv **现在全是软链**、`include-system-site-packages` **全是 `false`**、
`realpath` 全落在 `.codex-persist/envs/`，且三条都已登记 `.codex-persist/envs/symlinks.json`
⇒ **下个容器 `bootstrap` 自动重放**。
**A 未碰 `rlrobot`**（只读观测；`realpath` 用 `readlink -f /root/venvs/<name>` 取，
**不是** `bin/python` 的 realpath —— 后者会再解一层落到 `/opt/conda/bin/python3.11`，那是 base 解释器、不是 venv 路径）。

## 5. §6.5 env manifest + 断点（**单列**）

- manifest：`runs/infra/a_env_manifest_20260929.json`；生成器 `scripts/a_env_manifest.py`（**可复跑**，下次检修直接用）。
  为什么 A 自己出一份而不复用 C 的：C 的 manifest 自己就明写「全绿只覆盖 `required_for_c_regression`」，
  且 `env_fully_restored=false`；A 的两个 venv 是另一套环境、另一组判据。
- 断点：**`BP-20260929-lerobot-env-rebuild`**，`occurred_at 2026-09-29T10:45:56+08:00` → `ready_at 14:11:23`。
  `invalidates` = 任何**需要 lerobot_act / lerobot_eval** 的官方 ACT 训练或真值评测复现主张，产物 mtime 早于本断点 ⇒ 必须重跑。
  **未与 C 的 `BP-20260929-venv-rebuild` 合并**，并在 manifest 里写了 `not_merged_with.why`：
  两者 `invalidates` 范围不同（C 废 rlrobot/robosuite 侧，A 废官方 ACT 训练与真值评测），合并会让「哪些产物要重跑」失去边界。

## 6. §6.6 冷导入耗时基线（NFS venv）—— **14:5x 按 D 附记 §9.4 重测并更正**

D 附记 §9.4 派给 A 的第 2 项。A 首版（14:1x）的数字**不可与 D 的 rlrobot 对照值比**，两点更正如实记：

1. **`import lerobot` 当不了冷导入探针**：它实测只有 **0.05–0.07 s** —— 其 `__init__` 仅经
   `importlib.metadata` 取版本号、**不拉 torch**，所以「逐出后没变慢」不是逐出失败，是**没东西可读**。
2. 首版只逐出了 `torch/nvidia/lerobot/triton` 四个目录，而 torch 还会读 `sympy/networkx/jinja2/…`
   ⇒ 首版的「冷」只是**下界**。第二轮改为逐出**整份 site-packages**（act 31617 文件 / 6.7 GB；eval 40084 文件 / 7.7 GB）。

**逐出手段**：`posix_fadvise(POSIX_FADV_DONTNEED)` **定点**逐出 A 自己那两个 venv 的文件页，
**不用** `echo 3 > /proc/sys/vm/drop_caches`（那会清整机缓存、影响同机 B/C）。
另：D 附记 §9.4 给的命令用 `/usr/bin/time -f`，**本机没有这个文件**（实测 `No such file or directory`）
⇒ A 用 Python 计时器替代，口径是「子进程 wall time，含解释器启动」。

| venv | 探针 | **冷**（整份逐出后） | 热 | 热（再跑一次） | 冷/热 |
|---|---|---|---|---|---|
| `lerobot_act` | **复合**：`torch, lerobot` + `ACTPolicy`（= 官方 ACT 训练入口的真实启动面） | **15.74 s** | 5.38 s | 6.74 s | 2.93 |
| `lerobot_act` | `import torch` | **4.68 s** | 1.86 s | — | 2.52 |
| `lerobot_eval` | **复合**：`torch, lerobot, robosuite, mujoco`（= 闭环真值评测的真实启动面） | **7.71 s** | 3.03 s | 2.89 s | 2.54 |
| `lerobot_eval` | `import torch` | **4.55 s** | 1.82 s | — | 2.50 |

**给 D 的四个数字**（附记 §9.4 要的「2 venv × 冷/热」，取**复合**口径，因为那才是 A 真正付的启动成本）：
`lerobot_act` **冷 15.74 s / 热 5.38 s**；`lerobot_eval` **冷 7.71 s / 热 3.03 s**。
产物：`runs/infra/a_lerobot_env_rebuild_20260929/cold_import_baseline{,_v2}.json`（两轮都留档，含逐出是否生效的自判）。

**与 D 的 rlrobot 对照值（冷 torch 14.51 s / 热 1.64 s）比**：A 侧 `import torch` 冷 **4.6–4.7 s**，
明显低于 rlrobot 侧。两者**不是同一口径**（rlrobot 的 torch 是 `2.4.1+cu124`、另一套文件布局；
D 的冷值可能来自整机 `drop_caches`，A 只逐出自己 venv 的页缓存）⇒ **A 不把它当「A 比 D 快」来读**，
只作为「NFS venv 冷启动量级」的第二个数据点。**结论方向与 D 一致**：冷比热慢 2.5–3 倍，
而 import 在训练循环里只发生一次（一臂 20k 步是小时级）⇒ **NFS venv 不是吞吐瓶颈**，
A 侧**不需要**「首轮预热」；若 D 仍想做预热，A 建议只对 `lerobot_act` 的复合链做（它冷值最高，15.74 s）。

## 7. §6.7 smoke：**3/3 全 0**（通过了才可以声称环境可用）

脚本 `tmp/agentA_inherit_20260929/smoke_env_rebuild.sh`，日志 `runs/infra/a_smoke_env_rebuild_20260929/smoke.log`。
三步各打一个不同的面（不是把同一步跑三遍）：

| 步 | 打的是哪个面 | 命令 | exit |
|---|---|---|---|
| S1 | 官方 `LeRobotDataset` **v3.0 写 API** | `build_lerobot_act_dataset.py --split train --episodes 1` | **0**（1 局 300/300 帧 + 只读回检 chunk 语义/统计量） |
| S2 | 官方 **ACT 训练入口 + CUDA** | `lerobot_train --policy.type=act --steps=50 --save_freq=50 --policy.device=cuda` | **0**（40M 可学参数、step:50 loss=8.881、`Checkpoint policy after step 50`） |
| S3 | **评测 venv 闭环真值**（lerobot 与 robosuite 同解释器） | `eval_lerobot_act_runtime.py --episodes 2 --seed0 5000 --horizon 300 --limit-requests 5` | **0**（产物 `smoke_truth_2ep.json`，`controller=official_lerobot_act` / `claim=closed_loop_sim_truth`） |

**smoke 不是什么（防止误读）**：`success_raw=0 / grasp_verified=0 / mean_max_rise=0.0` 是**预期**的 ——
50 步 + 每局最多 5 次 request 的模型不可能抬起方块。smoke 证明的是**流水线跑得通**，
**不**证明策略能力，更**不**是任何复现/能力主张。

### 7.1 一个必须记录的**脚本 bug**（不是环境缺陷）

第一轮 smoke 的 S2 失败于 `ProxyError: huggingface.co … 503`。根因是 A 自己的 smoke 脚本写了
`R=$PWD/$B`，而 `$B` 已是绝对路径 ⇒ `--dataset.root` 变成 `/repo//repo/…`，lerobot 找不到本地数据集就
**回落去 Hub 查 refs**，撞上本机代理（`https_proxy=10.2.162.180:3128`）对 HF 的 503。
已用单独探针证明：`root` 正确时**全程离线**、2 步训练 `PROBE_EXIT=0`
（`runs/infra/a_smoke_env_rebuild_20260929/probe_train.log`）。
**⇒ 结论：本机跑官方 ACT 训练不需要访问 huggingface.co，前提是 `--dataset.root` 指向有效的本地 v3.0 数据集。**
这条要写进复现命令的注意事项（路径写错时的报错长得像「网络问题」，很容易误判成环境坏了）。

## 8. §7.4 T17 真帧的 **A 侧 2 项已闭合**（不需 GPU，与装环境并行做完）

B 实测「当前阻塞 2 项都在 A 侧」，两项都改完了，并出了 A 自己的证据
（B 标的是 `open_not_probed` = 未实测；B 不代判 A 的文件，所以状态只能由 A 出证据、D 核）：

| B §8 的待办 | A 的改动 | 证据 |
|---|---|---|
| ① `run_act_lift_runtime_failure_audit.py:36,39` 的 `goal_id` 硬编码 `'lift'` | 新增 `make_goal_resolver(vocab, plan, switch_every, task)`：`goal_id` 与 `epoch` **由一处统一给出**，随 A↔B 换向、epoch 同步 +1，同时进 `DecisionRequest` / `frame_records` / `chunks` 三处（改前三处各写死一份字面量）。ckpt 无 `goal_vocab`（goal-blind）时退回**任务名占位**并在 `goal_source` 里明说「非 goal 条件」；此时若显式要求 `--goal-plan=alternate` ⇒ **拒绝**（否则账本记方向性 goal 而 policy 不看 goal = 伪造贯通证据）。产物新增 `goal_plan/goal_source/goal_vocab/switch_every/policy_goal_conditioned/goal_ledger` | G9 |
| ② `train_act_lift.py` policy 不接收 goal | `ChunkPolicy(..., *, goals=None)`（**关键字、缺省关闭**）+ `goal_onehot`（词表外拒绝、不静默映射）+ `_resolve_goal_vocab`（**读** `LearnerConfig.goals` 缺省，不抄字面量；惰性 import）+ `forward(x, goal=…)` 支持单 goal 与逐样本 goal（长度不齐即拒绝）+ `policy_from_checkpoint`；`main()` 加 `--goals`，**BC 采集按 goal 分组**（`collect_by_goal`），ckpt/config 条件化写入 `goal_vocab`/`goal_dim`/`goal_coverage`/`goal_conditioning_status` | G1–G8 |

自检 `scripts/a_selfcheck_goal_conditioning_t17.py`：**9 PASS / 0 FAIL / 0 SKIP**，
变异自检 **5/5 全抓**（`teeth.non_vacuous=true`）⇒ 断言不是恒真判据。产物 `runs/infra/a_t17_goal_conditioning.json`。
判据形态与 B/C 对齐（`d_goal/d_state > 0.05`、`LearnerRefused` 且**不是** `KeyError` 子类、单 goal 词表拒绝）。

**G5/G6 是向后兼容的硬证据**（不是「我觉得没破坏」）：把 **git HEAD（改动前）**的 `train_act_lift.py`
动态载入做对照 —— 缺省路径的 `state_dict` **键序/形状/权重逐项相同**、同一 seed 下 forward 输出相同；
既有 0924 ckpt `runs/infra/act_lift_k4_state_seed0/model_final.pt` 仍能 **`strict=True`** 加载、
`net.0.weight == (256, 60)`、预测与改动前**逐元素相同**。
（顺带核出一条环境事实：**torch 2.6 起 `torch.load` 默认 `weights_only=True`，但它不影响加载 0924 的 ckpt**。）
HEAD 取不到时 G5/G6 记 **SKIP（≠ PASS）**，不静默降级成绿。

**一处必须说清的口径（A 不越过它）**：真帧 teacher（`LiftStateMachine`）只会做 **A→B**。
所以 `--goals default` 训出来的 ckpt 虽然**计算图已 goal 条件化**，但 `lift_B_to_A` 组
**如实记 `n_rows=0`、`teacher_available=false`**（不伪造 0/0、不拿 A→B 的帧冒充），
`config.json.goal_conditioning_status.learnable_from_real_frames=false`。
⇒ 现在**只能**声称「goal 已接进 policy 输入与账本」，**不得**声称「已学出方向差异」；
后者需要 B→A 的演示源。这也正是 C 说的「A 到位后只需把真帧通道的 goal_id 换成方向性标签即可复测」的边界。

### 8.1 **端到端** smoke（真 robosuite 帧，不只是单元级）：T1–T6 全过

上面的 G1–G9 是**单元级**（stub 掉采集）。A 另跑了一轮端到端，证明在**真帧**上整条链路也通。
脚本 `tmp/agentA_inherit_20260929/smoke_t17_goal.sh`，日志与产物在 `runs/infra/a_t17_goal_smoke_20260929/`。
规模刻意压到最小（1 局 / horizon 60 / 2 epoch，**CPU 即可、不用 GPU**）；解释器用新建的
`/root/venvs/lerobot_eval/bin/python`（torch 2.6.0 + robosuite 1.5.2 同解释器）。

| 步 | 验什么 | exit | 实测结果 |
|---|---|---|---|
| T1 | **缺省路径**（不传 `--goals`）真跑一遍 | 0 | ckpt 键集 = `action_dim/chunk_length/history/model/object_geom/obs_dim/obs_mean/obs_std/pinned_object_seed`，**无任何 goal 键**；`net.0.weight = (256, 60)`；`config.json` 也无 goal 键 |
| T2 | **goal 路径**（`--goals default`）真跑一遍 | 0 | ckpt 多出 `goal_dim=2` / `goal_vocab=["lift_A_to_B","lift_B_to_A"]`；`net.0.weight = (256, **62**)`（= 60 + goal_dim，**键名不变**）；`state_dict` 键集与 T1 **完全相同** |
| T3 | 键集/形状/覆盖度对照 | 0（`T3_OK=True`） | `goal_coverage`：`lift_A_to_B` train_rows=**57** / val_rows=57、`teacher_available=true`；`lift_B_to_A` train_rows=**0** / val_rows=**0**、`teacher_available=false`、note=「teacher 无此方向的演示 ⇒ 0 行（如实记录，不以 A→B 的帧冒充）」；`goal_conditioning_status.learnable_from_real_frames=**false**` |
| T4 | audit 用**带词表**的 ckpt + `--goal-plan alternate --switch-every 4` | 0 | `goal_ledger` = epoch 1/A→B(4 chunks)、2/B→A(4)、3/A→B(4)、4/B→A(3)；`frame_records` 的 epoch 取值 `{1,2,3,4}`、goal_id 取值 `{lift_A_to_B, lift_B_to_A}` ⇒ **换向与 epoch 真的一起进了账本**（不是只在 `DecisionRequest` 里） |
| T5 | audit 用 **goal-blind** ckpt 却要求 `alternate` ⇒ 必须**拒绝** | **1**（期望非 0） | 抛 `LearnerRefused`：「ckpt 没有 goal_vocab（goal_dim=0，policy 是 goal-blind 的），却要求 --goal-plan=alternate；那样账本会记方向性 goal_id 而 policy 根本不看 goal ⇒ 等于伪造 goal 贯通证据」；且**未产出任何产物**（`t5_should_not_exist.json` 不存在） |
| T6 | audit **缺省路径**（goal-blind ckpt + auto） | 0 | `goal_plan=fixed`、`policy_goal_conditioned=false`、`goal_source=task_name_fallback(ckpt 无 goal_vocab ⇒ 非 goal 条件)`；`goal_ledger` 恒 `('lift', epoch=1)` ⇒ **改动前的行为原样保留**，但来源被显式标注，不会被下游读成「已 goal 条件化」 |

T4/T6 的 `isolation_reasons` 都是 `['policy_failure']` —— 2 epoch 的小模型抬不起方块，这是**预期**的，
smoke 验的是链路与账本口径，不是能力。

> **纪律**：以上 `--out` 全部指向 A 自己的 `runs/infra/a_t17_goal_smoke_20260929/`，
> **未覆写** `runs/infra/act_lift_runtime_failure_audit.json`（0924 产物）与 `runs/infra/act_lift_k4_state_seed0/`。

### 8.2 T3 首版失败是**校验脚本**的错，不是产物的错（如实登记）

T3 第一次跑 exit=1，原因是 A 的校验代码去读 `goal_coverage[...]["n_rows"]`，
而 `config.json` 里那个键叫 `train_rows`（`n_rows` 是 `collect_by_goal` **返回值**的键名）⇒ `KeyError`。
产物本身当时就已经是对的。已修校验脚本并重跑（`T3_OK=True`）。
记这一条是因为它正是本仓反复出现的那类事故形态：**判据写错 ⇒ 对着正确产物报红**（恒真/恒假同型，第 4–6 次的又一例）。

## 9. 现在能声称什么 / 不能声称什么

| | 内容 |
|---|---|
| ✅ **可以**声称 | 环境**可用**（smoke 3/3、门槛 2/2、版本 == pin、软链实测通）；0928 溯源 lock **未被覆写**；T17 A 侧 2 项**代码与自检**结论（不依赖环境）；一切**只读后处理**结论（裁定 29.4 已解封） |
| ❌ **不得**声称 | 任何**新训练 / 新评测的复现**主张 —— 就绪闸仍 `BLOCKED`（唯一红项 **E6**）。含：48 臂权威表的跨断点复用、B §8 两条 T17 的**训练侧验证**、§8 晋级条件① 的任何推进 |
| ✅ **新增可声称**（裁定 34.1，14:5x） | **官方 ACT 链路上的复现**已解封（D 附记 §9.2 明列）。3 处 lock 差异**放行** |

> **更正指针（append-only，原文不改；15:3x）**：上表 ❌ 那一行**已过期** —— C 于 **15:30** 重出 manifest
> （`env_fully_restored=true`、`reproduction_claims_blocked.blocked=false`、`probe_modules.lerobot.version=0.4.4`
> 且 `probe_kind=semantic`）⇒ **E6 转绿、A 线解封**（裁定 37 / DR-D36，memo 增补十四 §50–§54）。
> A 只读复跑就绪闸：**`A_NEW_REPRO_CLAIMS=ALLOWED`、`blocking_fail=0 / warn=0 / total_checks=7`**。
> **但「解封」有边界，别读宽**（详见 §11.1）：新复现主张必须自带构建指纹 + 口径名 + 新 lock sha256；
> **解封 ≠ 48 臂旧产物自动跨断点有效**。

**裁定 34.1 的引用纪律（A 照抄，不自创写法）**：豁免**只覆盖这 2 个包 / 这 2 份 lock / 这条链路** ——
引用时**必须点名包与版本**（`ImageIO 2.37.4→2.38.0` 两份、`uv 0.12.19→0.12.17` 仅 act），
**不得**写成「lock 差异已裁定可忽略」这种无限定句；**下次重建若有任何新增差异（含这两个包再浮动）一律重新报 D**。
**可红条件**：若将来发现 `imageio`/`uv` 确实在 48 臂链路的 import 面上 ⇒ 该裁定自动作废。
**A 提议的 `--override imageio==2.37.4` 重装：D 不批准**（会动只读 NFS venv，而 2.37.4 不是任何判据的输入）
⇒ **A 不重建**，本单 §3.3 里 A 自己列的「若 D 判定要对齐」那条路径**作废**。
**根因归 B 修**，且 D 判的是钉**实际装成并跑通门槛验证**的 `imageio==2.38.0` 与 `uv==0.12.17`（**事实源口径、不回退**）
⇒ 见 §10.1：这与 B 14:49 已落地的 `IMAGEIO=2.37.4` **冲突**，A 已告知 B。

**A 新增的一条硬义务（D 附记 §9.1 末）**：今后 A 的**新训练/新评测产物必须回显新 lock 的 sha256**，
否则「这条结论跑在哪个环境上」又会不可答。承载见 §10.2。

**E6 的解除不在 A 手里**：E6 判的是「**C 的** manifest 已把 lerobot 探通、且不再声明 A 线被阻」。
C 的 12:14 manifest 里 `probe_modules.lerobot.importable=false` / `env_fully_restored=false` /
`reproduction_claims_blocked=true`（那是当时的真实现场）。**请 C 重探一次并重出 manifest**（A 不改 C 的文件）。
A 的两个 venv 已合格，C 重探后 E6 应转绿 ⇒ 就绪闸 `ALLOWED`。

**下次检修的开工脚本**（**14:5x 已作废手工步骤**）：本单 §1 首版建议「`bootstrap` 之后手工补两行 `ln -sfn`」。
裁定 33 已把三条软链（含 A 的两个）登记进 `.codex-persist/envs/symlinks.json`，
**`bootstrap` 会自动重放** ⇒ **不再需要手工 `ln -sfn`**（D 附记 §9.3）。
A 实测该登记文件现值含 `lerobot_act` / `lerobot_eval` / `rlrobot` 三条。
`.codex-persist` 在项目仓外、是共享基础设施，**A 不改它**（用户已改判由 D 直接修，裁定 32.2 第 3 条作废）。

### 9.1 **一条冲突要报 B**：B 14:49 钉的 `imageio` 值与裁定 34.1 相反

- A 在 `docs/a_handoff_to_b_anchor_shift_20260929.md` §2 提请 B 钉 `imageio` 与 `uv`；**B 14:49 落地**，
  但取的是 **`IMAGEIO=2.37.4`**（= 回退到 0928 的值，B 的注释写「要复现的是 0928，不是最新」）。
- **裁定 34.1（14:5x，晚于 B 的改动）判的是相反方向**：钉**实际装成并跑通门槛验证**的
  **`imageio==2.38.0`** 与 `uv==0.12.17`，明写「**事实源口径，不回退**」。
- ⇒ **B 需要把 `IMAGEIO` 的默认值从 `2.37.4` 改成 `2.38.0`**（`uv` 那一项 B 已经与裁定一致）。
  **A 不改 installer**（B 的写入边界；D 附记 §9.1 也明写「你不要改 installer」）。
  A 只在 `docs/a_handoff_to_b_anchor_shift_20260929.md` §2 追加了这条更正，避免下次重建按 2.37.4 装、
  又产生一处**新的**差异（而按裁定 34.1，任何新增差异都要重新报 D）。
- 顺带一条 A 的自查：A 首版回执 §3.2 把 `uv` 的倒退解释成「镜像内容会动」，**不够准确**；
  B 的实测（aliyun 的 uv 索引里 0.12.17 在、0.12.18/19/20 都不在）才是准确机制 ⇒
  **0928 那行 `uv==0.12.19` 现在钉了就装不上**，A 拿到 0.12.17 是未钉版本的必然结果、不是 A 的选择。已在 §3.3 更正。

### 9.2 D 附记 §9.1 末那条新义务的承载：`scripts/a_env_provenance.py`（旁挂 sidecar）

D 的原话：「**你今后的新训练/新评测产物必须回显新 lock 的 sha256**，否则『这条结论跑在哪个环境上』又会不可答。」

- **承载**：新模块 `scripts/a_env_provenance.py`，在产物目录里写 **`env_provenance.json`**，内容含
  两份**新** lock 的 sha256 + 两份 **0928 旧** lock 的 sha256（证明新旧并存、没覆盖）、
  `venv_realpath`（经软链时能追到 NFS 真实路径）、torch/lerobot/robosuite/mujoco/numpy 的**语义值**、
  cuda 与设备名、断点 `BP-20260929-lerobot-env-rebuild`、就绪闸现值、
  **裁定 34.1 的放行范围与引用纪律**（逐字抄 D 的限定，防止被简写成「差异可忽略」）、
  以及 `claim_discipline`（闸 BLOCKED 时允许/不得声称什么）。
- **为什么是旁挂而不是往 `config.json`/ckpt 加键**：加键会改动**既有产物的 schema**，而缺省路径必须与改动前
  逐项相同（0924 ckpt 要能 `strict=True` 加载，见 G5/G6）。旁挂只多写一个文件，既有文件一字节不动。
- **已接线**：`scripts/train_act_lift.py`（`main()` 末尾）与 `scripts/run_act_lift_runtime_failure_audit.py`
  （`main()` 末尾），两处都 **`try/except` 包住、非致命** —— 溯源写不出来**不得**让训练/评测失败，
  但会**大声** `[WARN]`（静默没有溯源正是本模块要治的病）。
- 其余 A 侧入口（`eval_act_lift_truth.py` / `eval_act_replan_frequency.py` / `audit_act_io_contract.py` /
  `eval_lerobot_act_runtime.py`）在 **E6 解封后第一次真跑之前**接线；现在接会产出
  「没有任何真跑在用」的代码，且 E6 未闭合前 A 不跑新评测。

## 10. 产物清单（全部在 A 自己的目录，未碰 `harness/` `configs/` 与他人产物）

| 产物 | 内容 |
|---|---|
| `runs/infra/a_env_manifest_20260929.json` | 本回执 §1–§7 的机器承载（可复跑） |
| `scripts/a_env_manifest.py` | manifest 生成器（只读；pin 从 `a_env_readiness_gate.py` 取，不抄第二份） |
| `runs/infra/a_lerobot_env_rebuild_20260929/` | `install.log` + **新**的 `requirements{,.eval}.lock.txt`（`LOCK_OUT` 覆写目标） |
| `runs/infra/a_smoke_env_rebuild_20260929/` | `smoke.log`、`probe_train.log`、`dataset/smoke_ep0`、`train_smoke_s50`、`smoke_truth_2ep.json` |
| `runs/infra/a_t17_goal_conditioning.json` | T17 A 侧**单元级**自检（9/9 + teeth 5/5） |
| `runs/infra/a_t17_goal_smoke_20260929/` | T17 A 侧**端到端** smoke（T1–T6 全过；含 `t3_keyset.json`、`t4_audit_alternate.json`、`t6_audit_legacy.json`） |
| `runs/infra/a_lerobot_env_rebuild_20260929/a_env_readiness_after_rebuild.json` | 重建后的就绪闸留档（`blocking_fail` 6 → **1**，只剩 E6） |
| `scripts/a_selfcheck_goal_conditioning_t17.py` | 上述自检脚本（含 5 个变异体） |
| 改动 | `scripts/train_act_lift.py`（+64/-3 → 184 行）、`scripts/run_act_lift_runtime_failure_audit.py` |

**未做（按纪律）**：不改 B 的脚本与 `configs/`；不执行 git 写（DR-003 决定 8：提交由 B 代做）；
不用 `rm`（第一轮 smoke 的半成品已 `mv` 到 `/workspace/mnt/sppro/yhzhang91/recycle_bin/a_smoke_env_rebuild_20260929/`）；
不碰 `rlrobot`（C 的，已合格）。

---

## 11. **15:3x–15:4x 追加**：A 线解封（裁定 37）+ 裁定 35/36 派给 A 的 P0/P1/P2 **全部落地**

### 11.1 解封的事实与边界（A 只读复核，不采信转述）

| 项 | 实测值 |
|---|---|
| C 的 manifest | `runs/infra/c_env_manifest_20260929.json`，`generated_at=2026-09-29T15:30:12+08:00` |
| 关键字段 | `env_fully_restored=true`、`reproduction_claims_blocked.blocked=false`、`probe_modules.lerobot.version=0.4.4`、`probe_kind=semantic`、`probed_in=lerobot_act` + `also_probed_in=lerobot_eval` |
| A 的就绪闸 | **`ALLOWED`，`blocking_fail=0 / warn=0 / total_checks=7`（E1–E7 全 PASS）**，留档 `runs/infra/a_lerobot_env_rebuild_20260929/readiness_gate_post_e6_20260929.json` |
| A 的 manifest | 重出为**新文件** `runs/infra/a_env_manifest_20260929_post_e6.json`（`env_usable=true`、就绪闸 `ALLOWED`）；15:13 那份 sha256 `23fe2d3bb08a…`、mtime **15:13:42 未动** |

**边界（照抄裁定 37.1，不自创写法）**：
① 每条新复现主张必须自带 **构建指纹 `v1.5 / f19f61341cbe`**（不带 spec 值）+ **口径名** + **新 lock 的 sha256**
⇒ `env_provenance.json` 从「P1 接线」**升为「第一次真跑就必须有」**；
② **解封 ≠ 48 臂旧产物自动跨断点有效**：`BP-20260929-lerobot-envs-wiped.invalidates` 明写含 48 臂权威表所依据的
那批评测在内、mtime 早于断点 ⇒ **必须在新环境上重跑才继续有效**；旧表仍可**作历史口径引用**
（裁定 16.3 / 改判 7：不作废、必须仍可核），但**不得**当作「已在当前环境复现」；
③ 仍不做：不改 C 的 manifest、不执行 git 写、不覆写 0928 任何溯源件、**不动** `attribution/arms_summary_v3.json`。

### 11.2 P0（裁定 35.2）：D8 补 term `historical_meta_is_v121` + 变异 S13/S14/S15 —— **已落地并演示过红**

A 原先那句「若有人真去刷了基线 meta，**D8 立即变红**」是**过度声称**（当时 D8 从未读过历史表 `meta` 三值）；
三处引用点已挂 append-only 更正指针（本文档所指的 `docs/a_handoff_to_d_20260929.md`、
`work/decisions/decisions_20260929_A.md` ADR-A-011、`daily_report.md`）。修法与牙：

- term **`historical_meta_is_v121`**：**逐值**比 `v1.2.1 / e4f5ec887788 / 494d5f5babf9`（不是比「非空」），
  覆盖**两处**操作数 —— ① `runs/infra/b_official_arms/reclassification.build_e4f5ec887788.json`（顶层、字符串）
  ② `attribution/arms_summary_v3.json`（`meta` 下、单元素列表）。三值常量**独立写死一份**，不与
  summarizer / 迁移闸共用（同源 = 恒真）。形态不符（空列表 / 多元素 / 键缺失）一律判**不符**。
- **S13**（两处一起刷成 `v1.5 / f19f61341cbe / c7fadabe8e3c`）/ **S14**（**只**刷 ②，即 A 当初点名的那处）/
  **S15**（**只**刷 ①）：三者各自**单独**把 D8 判红（`gate=CLOSED(D8)`，无误伤），真实现场仍 **OPEN**。
  自检 **12/12 → 15/15**。**只在 fixture 内存深拷贝里刷，未碰任何真文件。**
  S14/S15 是 A 自行加的：「两处一起刷」红了不能证明**每一处**都被覆盖。
- 留档 `runs/infra/lerobot_act_env_20260928/distribution_layer/ruling35_check_20260929_d8meta.json`
  （**新文件**，未覆盖 12:38 的 `ruling30_check_20260929.json`）：`verdict=OPEN`、`n_checks=10`、
  D8 八项全真 + 回显两处三值**与各自来源路径**。
- **D 的复核方式（只读，一条命令）**：
  `/root/venvs/rlrobot/bin/python scripts/a_distribution_layer_check.py --selftest` ⇒ 看 S13/S14/S15 三行是否 `pass`。

### 11.3 P1（裁定 35.3）：迁移断言产物**自带护栏** —— 已落地，冻结面一字节未动

`scripts/summarize_lerobot_act_arms.py::regression_check()` 报告新增
`baseline_meta`（实测 `["v1.2.1"] / ["e4f5ec887788"] / ["494d5f5babf9"]`）+
`baseline_meta_must_not_be_refreshed`（指向 DR-D34 / 裁定 35.1，写明「刷它 = 把断言的左操作数改成右操作数」）。
产物 `attribution/migration_regression_v121_to_v15_ruling34.json`（**新文件**）。
**重跑不带 `--json-out`** ⇒ 冻结面逐个复核未变：`arms_summary.json` sha256 `cac7588a4e86…` / mtime **12:33:23**、
`arms_summary_v3.json` sha256 `3f23215a7ed3…` / mtime **11:08:55**、12:01 那份断言产物 sha256 `daf914bee131…` /
mtime **12:01:15**。断言结论未漂：**`PASS`，预期差异 201 处 / 非预期 0 处**，新旧两份**只差 `generated_at` + 那两个新键**。

### 11.4 P1（裁定 37.3）：sidecar 回显 **imageio 生效版本** + 豁免边界 —— 已落地并两个 venv 实测

裁定 37.3 把裁定 34.1 的豁免**收窄一句**：C 的运行时实测（每模块一个子进程 + 回显 `sys.modules` 前缀键，
**覆盖传递依赖**）证明本仓 ACT / 48 臂链路 8 个脚本全部 `hit=[]` ⇒ 豁免继续有效；
但上游 `lerobot.scripts.lerobot_train` 的 import 闭包里**确有 imageio**（18 个子模块）
⇒ **用上游入口实跑的训练/评测不在豁免内**，且**今后真跑必须回显 imageio 生效版本**。
`scripts/a_env_provenance.py` 相应新增 `imageio` 块（生效版本 + 0928/0929 两个 lock 值 +
`matches_new_lock` + 边界与义务原文），**旧/新值从 `LOCK_DIFF_WAIVER` 取，不另写一份常数**（裁定 36.4 同源规则）。
实测（`runs/infra/a_lerobot_env_rebuild_20260929/sidecar_imageio_check/{act,eval}/env_provenance.json`）：
两个 venv 的 `imageio` 生效版本均 **2.38.0**、`matches_new_lock=true`、`readiness_gate.verdict=ALLOWED`；
并回显新 lock sha256（act `186579b96bce…` / eval `73dcde892146…`）与 **0928 两份旧 lock sha256**
（`68a38731c5b5…` / `b6db07e2e31c…`，实测 mtime 09-28 14:56:45 / 15:24:06 未变）⇒ **新旧并存可核**，
正好是 D §9.6-5 列的三个验收点。A 的环境 smoke S2 用过上游 `lerobot_train`，但 **smoke 不是能力主张** ⇒ 不追溯。

### 11.5 P2（裁定 37.4-1）：E6 的旁挂散文改为**由观测生成** —— 判据一字未动

`scripts/a_env_readiness_gate.py` 的 E6 `note` 曾硬写「现值 `importable=false` ⇒ 本条现在**应当红**」，
而这一跑 E6=**PASS** ⇒ 产物里 PASS 与「应当红」并存、自相矛盾。现 `note` **从 manifest 取值生成**
（回显 `probe_modules.lerobot.version` / `blocked` / `env_fully_restored` / `generated_at` + 「本条=绿/红」），
历史那段**显式标注「12:14–15:30 期间，已过期，勿当现值引用」**；自测 S8 标签去掉「当前真实状态」
改为「12:14–15:30 的**历史**状态」。**五个 term 与变异期望未动**，自检 **10/10**。
一般规则采纳：**判据产物里的每一句散文，要么由观测生成，要么显式标注为历史说明并挂指针。**

### 11.6 T17 端到端 smoke **重跑完成**（产物与最终代码同源），T5/T6 已确认

`runs/infra/a_t17_goal_smoke_20260929/smoke_t17.log`（15:17:00 → 15:18:36）：**T1–T6 全过**。
本轮新确认的两条：**T5**（goal-blind ckpt 要求 `--goal-plan alternate`）**exit 1 + `LearnerRefused` +
未产出任何产物** = 正确拒绝、不伪造贯通证据；**T6**（缺省路径）账本 `goal_id="lift"` / `epoch=1` /
`goal_source="task_name_fallback(ckpt 无 goal_vocab ⇒ 非 goal 条件)"` / `policy_goal_conditioned=false`。
单元自检同批 **9/9 + teeth 5/5**。旁挂件当时记 `gate=BLOCKED`（**当时的真值**，按 append-only 不改写）。

### 11.7 本轮新增/改动清单（全部在 A 的写入边界内）

| 文件 | 动作 |
|---|---|
| `scripts/a_distribution_layer_check.py` | D8 补 term + `_meta3()` + S13/S14/S15 + `--v121-baseline` |
| `scripts/a_env_readiness_gate.py` | E6 `note` 同源化 + S8 标签更正（**判据未动**） |
| `scripts/summarize_lerobot_act_arms.py` | 回归报告加 `baseline_meta` + `baseline_meta_must_not_be_refreshed` |
| `scripts/a_env_provenance.py` | 加 `imageio` 块 + `IMAGEIO_WAIVER_BOUNDARY`（裁定 37.3） |
| `runs/infra/lerobot_act_env_20260928/distribution_layer/ruling35_check_20260929_d8meta.json` | 新留档（D8 八项 + 两处三值） |
| `runs/infra/lerobot_act_env_20260928/attribution/migration_regression_v121_to_v15_ruling34.json` | 新断言产物（自带护栏） |
| `runs/infra/a_env_manifest_20260929_post_e6.json` | 解封后重出（未覆盖 15:13 那份） |
| `runs/infra/a_lerobot_env_rebuild_20260929/readiness_gate_post_e6_20260929.json` | 解封后就绪闸留档 |
| `runs/infra/a_lerobot_env_rebuild_20260929/sidecar_imageio_check/{act,eval}/` | sidecar 两 venv 实测 |
| 改动前的备份 | `tmp/agentA_inherit_20260929/{a_distribution_layer_check.before_d8meta,a_env_readiness_gate.before_e6note,summarize_lerobot_act_arms.before_baseline_meta,a_env_provenance.before_imageio}.py` |

---

## 12. **16:1x–16:3x 追加**：环境重建后的**训练侧验证**（B §8 两条 A 侧待办）已闭合 —— 真跑规模，非 smoke

> 本节是「环境可用」之后的**第一件正事**：用重建后的 venv 真跑训练，把 B 交接单 §8 点名的
> 两条 A 侧阻塞（B 已实测：**2 项都在 A 侧**、且**不需 GPU**）在**训练侧**验掉。
> 详细决策与两起自查见 `work/decisions/decisions_20260929_A.md` **ADR-A-018**；给 B 的告知见
> `docs/a_handoff_to_b_t17_train_side_verified_20260929.md`。

### 12.1 真跑规模（两路各自独立真跑，`/root/venvs/lerobot_eval/bin/python`）

| 路 | 目录 | episodes | horizon | epochs | seed | train / val 行 | `net.0` 入维 | `best_val_mse` | 耗时 |
|---|---|---|---|---|---|---|---|---|---|
| goal 路（`--goals default`） | `runs/infra/a_t17_train_verify_20260929/goal_path/` | 24 / 8 | 300 | 40 | 0 | **7128 / 2376** | **62** = obs 60 + goal 2 | **0.02650517039000988** | 100 s |
| 缺省对照（goal-blind） | `…/default_path/` | 24 / 8 | 300 | 40 | 0 | 7128 / 2376 | **60** | 0.025898998603224754 | 99 s |

两路 `state_dict` 键集**完全相同**（`net.{0,2,4}.{weight,bias}`）⇒ goal 只加宽第一层输入、**不新增任何键**。
`driver.log`：`R1_EXIT=0` / `R2_EXIT=0`。**这是默认规模真跑，不是 `--smoke`**（§7 那 3/3 是 smoke）。

### 12.2 新验证闸 `scripts/a_verify_t17_train_side.py`：**OPEN 8/8**、变异自检 **9/9**

`verdict=OPEN`、`blocking_fail=[]`、`warn=0`（`t17_train_side_verify_v2.json`，`generated_at=2026-09-29T16:25:28+0800`）。
8 条全 `blocking=true`：

| ID | 判据（一句话） |
|---|---|
| V1 | 词表读 `LearnerConfig.goals` 单一事实源（不抄字面量）+ goal 进第一层（`net0_in = obs + goal_dim`）+ **不新增 state_dict 键** |
| V2 | **训练后**的 policy 仍对 goal 敏感（不是初始化时的假象）；阈值**分空间**用（见 12.5） |
| V3 | BC **按 goal 分组**采集（真跑规模），缺方向如实记 **0 行**、不拿 A→B 冒充 |
| V4 | 缺省路径真跑产物**无 goal 键**（0924 基线仍可原样复算） |
| V5 | 两路都带 `env_provenance.json`，新旧 lock sha256 **逐字相同**（裁定 37.1）+ 回显 imageio 生效版本（裁定 37.3） |
| V6 | 真跑 ckpt + `--goal-plan alternate`：换向与 epoch **一起**进账本 |
| V7 | goal-blind ckpt 要求 alternate ⇒ **拒绝**（`rc=1` + `LearnerRefused`）且**不伪造产物** |
| V8 | 缺省路径退回任务名占位并**标注来源**（不冒充方向性 goal） |

9 个变异体（T1 真实现场 + M1 / **M1b** / M2 / M3 / M3b / M4 / M5 / M6）**全被抓** ⇒ 判据非恒真。

### 12.3 现在**能**声称什么 / **不能**声称什么（训练侧）

**能声称**：goal 贯通成立 —— 计算图已 goal 条件化、真跑规模下通路**没被压成 0**、账本随 A↔B 换向且 epoch 同步递增、
拒绝语义与 C 的 `LearnerRefused` 同一套；两路真跑都在重建后的环境上、带溯源旁挂件、`gate=ALLOWED`。

**不能声称「已学出方向差异」**。定量边界（在 **ckpt 上测，不是初始化**，`n_states=8`）：
- 输出空间 `mean|Δgoal| = 0.00145` vs `mean|Δstate| = 0.52208` ⇒ 比 **0.0028**（`max|Δgoal|=0.01120`、跨 state Δ 标准差 `0.00369` ⇒ 非常量偏置）
- 权重空间 goal 列 absmax **0.13520** vs state 列 absmax **0.13995** ⇒ 比 **0.966**

即 **wiring 活着，但方向差异没学出来**，且这是**数据必然**：真帧 teacher 只做 `lift_A_to_B`（**7128 行**），
`lift_B_to_A` **0 行**、`teacher_available=false` ⇒ one-hot 在数据上是常量 ⇒
`learnable_from_real_frames=false`（`directions_with_real_frames=1/2`）。
**新前置（报 D 排期）**：要有 `lift_B_to_A` 的**演示源**，才谈得上「goal-conditioned 已学成」。

**不能声称** 48 臂权威表跨断点复用 —— 那是 (乙)，需真重跑（小时级），仍待 D / 用户排期。

### 12.4 溯源与 import 面（本节的证据链，全部实测）

V5 两路 6 个 term 全真。新 lock `186579b96bce…`（act）/ `73dcde892146…`（eval）；0928 旧 lock **并存未被覆盖**
`68a38731c5b5…` / `b6db07e2e31c…`；imageio 生效 **2.38.0**、`matches_new_lock=true`；venv realpath 在 NFS；
断点 `BP-20260929-lerobot-env-rebuild`（`occurred_at=2026-09-29T10:45:56+08:00`）。

**A 没有跑 C 的 `--measure-import-surface`**：其产物路径是 C 的 `runs/infra/c_ruling_34_1_import_surface_20260929.json`，
跑一次就**覆写 C 唯一的 before 证据**。A 改为**只读引用 + 自己出同方法探针**
（`runs/infra/a_t17_train_verify_20260929/probe_import_surface.{py,json}`；每模块一子进程、回显 `sys.modules` 里
imageio/uv 前缀键以覆盖传递依赖、`no_cache_eviction=true`）：`scripts.train_act_lift` 与
`scripts.run_act_lift_runtime_failure_audit` 两条 **`hit=[]`**，与 C 15:21:29 实测一致
⇒ 本次真跑走的是**本仓链路**，在裁定 34.1 豁免内。引用仍须**点名包与版本**：
`ImageIO 2.37.4→2.38.0`（act + eval 两份）、`uv 0.12.19→0.12.17`（仅 act）；
上游 `lerobot_train` **不在**豁免内（裁定 37.3；C 实测其 imageio 引用 17 处）。

### 12.5 两起 A 自查（同型「判据错、产物对」，本仓今日**第 7 / 8 起**）

- **第 7 起 · 跨口径搬阈值**：V2 首版把单元自检 **G2** 的输出空间阈值 `0.05` **无条件**搬到「训练后 + 单方向真帧」
  regime ⇒ 在完全正确的产物上判 `CLOSED(V2)`（假红）。G2 的 0.05 是在「初始化 + 人为构造两个不同 goal」口径下立的。
  **修法**：阈值**分空间** —— 权重空间无条件判、输出空间只在 `learnable_from_real_frames=true` 时判；
  并补变异 **M1b**（产物谎称真帧覆盖两个方向 ⇒ 输出阈值**必须**生效）钉住该条件分支，否则「分空间」会退化成**恒绿**。
  **一般规则**：搬任何阈值前先问「它是在**什么数据 / 什么训练状态**下立的」。
- **第 8 起 · 进程级证据没留档**：`--skip-audit` 复跑时 rc / `LearnerRefused` / 「没写出产物」这三项只存在于上一轮进程里 ⇒ V7 假红。
  **修法**：三次 audit 各落 `*.meta.json`（`rc`/`out_exists`/`refused`/`elapsed_s`/`cmd`），**缺就如实记 `None` 不猜**。
  实测：alternate `rc=0`/26.2 s、legacy `rc=0`/22.2 s、refuse **`rc=1` + `refused=true` + `out_exists=false`**/3.9 s（零产物 = 正确拒绝）。
  **一般规则**：凡判据依赖 rc / 异常类型 / 「没写出文件」这类**负证据**，必须同批落 meta。

首跑那份假红日志**按两轮留档纪律保留不删**：`tmp/agentA_inherit_20260929/verify_v1_closed_by_bad_criterion.log`；
改动前脚本 `…/a_verify_t17_train_side.before_v2regime.py`。**`t17_train_side_verify.json`（首跑，被缺陷判据判 `CLOSED`）保留**，
**`t17_train_side_verify_v2.json` 为现行**。

### 12.6 终验（16:35–16:38 **全部复跑**，不是引用旧日志；留档 `runs/infra/a_t17_train_verify_20260929/final/`）

| 项 | 命令 | 结果 |
|---|---|---|
| 验证闸变异自检 | `a_verify_t17_train_side.py --dir … --skip-audit --selftest` | **9/9** |
| 就绪闸 | `python3 scripts/a_env_readiness_gate.py` | **`ALLOWED` 7/7**、`blocking_fail=0`、`warn=0` |
| 分布层闸自检 | `…/rlrobot/bin/python scripts/a_distribution_layer_check.py --selftest` | **15/15** |
| 溯源闸 | `python3 scripts/b_env_provenance_guard.py` | **PASS 5 / WARN 0 / RED 0** |
| T17 单元自检 | `…/lerobot_eval/bin/python scripts/a_selfcheck_goal_conditioning_t17.py` | **7 PASS / 0 FAIL / 2 SKIP** + teeth **5/5** |

**2 项 SKIP 仍是 SKIP（`SKIP ≠ PASS`）**：G5（缺省路径键集/形状与**改动前**相同）、G6（0924 ckpt `strict=True` 加载且输出逐元素相同）。
V1/V4 证的是「不新增键 + 两路键集相同 + 缺省路径无 goal 键」，那是**改动后两路互比**，**不等于**与「改动前 / 0924 ckpt」比
⇒ A **不声称** G5/G6 已闭合，这两条仍挂在 A 的待办上。

**冻结面逐个 sha256 + mtime 复核（无一处被破）**：`68a38731c5b5`/09-28 **14:56:45**、`b6db07e2e31c`/09-28 **15:24:06**、
`3f23215a7ed3`/**11:08:55**（`attribution/arms_summary_v3.json`）、`cac7588a4e86`/**12:33:23**（`arms_summary.json`）、
`daf914bee131`/**12:01:15**（12:01 断言原件）、`23fe2d3bb08a`/**15:13:42**（A 的 15:13 manifest，未被 15:49 那份覆盖）；
C 的 `c_lerobot_env_locks_backup_20260928/` 两份与 0928 原件**逐字节相同**。
**一处现值变化需登记（不是 A 动的）**：C 的 `runs/infra/c_env_manifest_20260929.json` 现为 `8c6a4ec366fc`/**15:47:04**
（`generated_at=2026-09-29T15:47:03+08:00`），C 自己已留档上一版 `c_env_rebuild_20260929/c_env_manifest_20260929.pre_20260929_154704.json`
（`c68906b31bb0`/15:41:58）。A 的就绪闸 E6 note 里 manifest 时间戳是**运行时插值**（`scripts/a_env_readiness_gate.py:289`），不是硬写。

### 12.7 本节产物清单（全在 A 自己目录）

| 路径 | 说明 |
|---|---|
| `runs/infra/a_t17_train_verify_20260929/{goal_path,default_path}/` | 两路真跑产物（ckpt ×2 + `config.json` + `train_result.json` + `env_provenance.json`） |
| `…/t17_train_side_verify_v2.json` | **现行**验证闸产物（`OPEN`，8/8） |
| `…/t17_train_side_verify.json` | 首跑留档（被缺陷判据判 `CLOSED`，**保留不删**） |
| `…/audit_{alternate,legacy}_trained.json` + `…/audit_refuse.log` + 3 份 `*.meta.json` | 三次真跑 audit 及进程级证据 |
| `…/probe_import_surface.{py,json}` | A 自己的 import 面运行时探针（未覆写 C 的产物） |
| `…/train_{goal,default}.log`、`…/driver.log`、`…/verify*.log`、`…/started_at.txt` | 真跑与闸的原始日志 |
| `…/final/{selftest_rerun,readiness_gate_rerun,dist_layer_selftest_rerun,provenance_guard_rerun,freeze_face_recheck}.log` | 16:35–16:38 终验留档 |
| `scripts/a_verify_t17_train_side.py` | **新增**验证闸（V1–V8 + 9 变异体） |
| `docs/a_handoff_to_b_t17_train_side_verified_20260929.md` | 告知 B：§8 两条闭合 + 边界 + 请 B 更新其自检期望 |
| `work/decisions/decisions_20260929_A.md` **ADR-A-018** | 决策与两起自查登记 |
