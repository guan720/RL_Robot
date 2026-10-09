# D → A 执行单（2026-09-29 13:0x）：环境重装（**责任改判给 A**）+ 持久化 + 溯源保护

交出方：智能体 D（监管/口径裁定线）。接收人：智能体 A（官方 LeRobot ACT 训练与真值评测线）。抄送：B、C。
依据：用户指令「让 A 自己安装环境」；`rl_harness_supervision/supervisor_memo_20260929.md`
**增补九 §26–§29（裁定 32）**；`work/decisions/decisions_20260929.md` **DR-D31**。
**权威 pin 来源（照抄，不要"顺手升级"）**：B 的 `docs/lerobot_env_reinstall_pin_20260929.md`（DR-012）。

**责任改判**：裁定 31.5 附条原写「B 执行安装 → A 验证 → C 探针」，**该分派作废**。
现为 **A 执行安装 + 门槛验证 + smoke + 重出 manifest + 登记断点**；B **只**提供权威 pin 并验收
（`install_lerobot_act_env.sh` / `setup_env.sh` 仍在 B 的写入边界，**A 只用环境变量覆写、不改脚本**）；
C **只**出探针。**理由**：安装是执行动作不是判据动作，谁用这个环境跑训练谁负责它装对了。

---

## 0. 现状（D 只读实测，不是推测）

- `ls /root/venvs/` **只有 `rlrobot`** ⇒ `lerobot_act` / `lerobot_eval` **两个 venv 都被 0929 检修抹掉**。
- GPU **全空**：`nvidia_smi` 实测 `memory_used=0 MiB` / `utilization_gpu=0 %`（A800-SXM4-80GB）
  ⇒ **A 此刻没有能跑训练的解释器**，这是 A 线**唯一的硬阻塞**。
- base 解释器：`python3` = `/opt/conda/bin/python3`、**3.11.9**（与 installer 的 `BASE_PY` 默认值一致）。
- `/etc/pip.conf`：`index-url = mirrors.ustc.edu.cn`（B 实测该源 302 到 tuna 并对本机 **403**）、
  `extra-index-url = mirrors.aliyun.com`。**pypi.org 直连不通。**
- **仓里有 73 个文件硬编码 `/root/venvs`** ⇒ **不要改路径**，用第 4 步的软链方案。

## 1. 先跑 bootstrap（用户已建持久容器；每个新容器都要跑一次）

```bash
python3 /workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist/bin/codex-persist bootstrap
python3 /workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist/bin/codex-persist status
```
`bootstrap` = restore（恢复 `~/.codex/sessions` 等，**永不覆盖本地已有数据**）+ 写 `~/.bashrc` hook + 起后台 watch。
**这治的是「对话历史不可复现」**（本轮 D 的上下文就是这么丢的）；环境持久化治另一半，见下。
**建议顺手开 link 模式**（零丢失窗口，但**多容器共用同一份 sessions 时不要开**）：
`codex-persist link` —— 它会检测 codex 进程，有进程在跑时拒绝执行。

## 2. **不要用 `mkvenv <name> <lock>`**（D 实测它这条路径会失败）

D 只读实测 `.codex-persist/bin/codex-persist:500-525`，两处缺陷：
- **缺陷①**：`cmd_mkvenv` 的安装行是 `pip install -r REQ`，**没有 `--no-deps`**。
  而 D 用 `importlib.metadata` 实测 **`robosuite 1.5.2` requires `mink==0.0.5`**，lock 钉的是 **`mink==1.2.0`**
  ⇒ 解析器判 unsatisfiable，**必撞 `ResolutionImpossible`**。这就是 C 的 ADR-C-006
  （`known_conflicts[mink-numpy-resolution]`）与 B pin 文档 §2 末行说的「同一个冲突的两个现场」。
  **已确立口径**：解析器到不了某个组合 ≠ 该组合不可用；从 lock 安装**必须 `--no-deps`**。
- **缺陷②**：`mkvenv` 硬编码 `--system-site-packages`（`:510`）且**不覆写 index**。
  但 B 的 pin 文档与 installer `:31` 明写 **lerobot 的 venv 必须不带 `--system-site-packages`**，
  否则 conda 的 TensorFlow + jax 进 import 链 ⇒ `cannot import name 'PreTrainedModel'`
  （**09-24 那串 ImportError 的真根因，不是 transformers 装坏**）；
  不覆写 index 则会走 ustc 源（403）。
⇒ **`lerobot_act` / `lerobot_eval` 一律走 installer；`rlrobot` 用 `mkvenv` 时不带 REQ 参数**（见第 5 步）。
`.codex-persist` 在**项目仓外**、是共享基础设施，**D 不改它**；建议的最小修法（加 `--no-deps` / `--index-url` /
`--clean` 三个开关）已写进 memo §27 裁定 3，由用户决定。

## 3. 装 lerobot 两个 venv（**A 的主任务**，直接建在 NFS 上）

```bash
cd /workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot
P=/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist/envs
OUT=$PWD/runs/infra/a_lerobot_env_rebuild_20260929
mkdir -p "$OUT"

VENV="$P/lerobot_act" \
EVAL_VENV="$P/lerobot_eval" \
LOCK_OUT="$OUT" \
bash scripts/install_lerobot_act_env.sh 2>&1 | tee "$OUT/install.log"
```
**为什么这三个覆写是必须的**：
- `VENV` / `EVAL_VENV` → 建在 **NFS**（`.codex-persist/envs/`），换容器不用重装。
  脚本已把它们写成可覆写（`:23`、`:68`），**不需要改脚本**。
- **`LOCK_OUT` → 新目录，这条是 P0 溯源保护（裁定 32.4）**：脚本 `:57` 与 `:85` 会
  `pip freeze > "$LOCK_OUT/requirements.lock.txt"` / `requirements.eval.lock.txt`，
  而 `LOCK_OUT` **默认 = `runs/infra/lerobot_act_env_20260928`** ⇒ **照默认值跑一次就就地覆写 0928 的两份 lock**。
  那两份是「**48 臂权威表当初跑在什么环境上**」的**唯一溯源证据**（B 的 pin 文档引它们作权威出处）。
  **新装的环境是新事实，0928 的 lock 是旧事实，两者必须并存，不能新的盖掉旧的。**

**pin 一律用脚本默认值**（`TORCH=2.6.0`、`TORCHVISION=0.21.0`、`LEROBOT=0.4.4`、`INDEX=aliyun`、
`BASE_PY=/opt/conda/bin/python3.11`），**不要覆写、不要升级**。
评测 venv 的 `--override numpy==2.4.6` 已在脚本 `:73-77` 里，**不要动**（那是绕开
`robosuite 1.5.2 → mink 0.0.5 → numpy<2.0.0` 的既定解法）。

## 4. 软链回 `/root/venvs`（**不要改那 73 个文件**）

```bash
mkdir -p /root/venvs
ln -sfn "$P/lerobot_act"  /root/venvs/lerobot_act
ln -sfn "$P/lerobot_eval" /root/venvs/lerobot_eval
```
- 软链在 overlay（每容器重建一次，**这一行应进 `bootstrap` 或 A 的开工脚本**），**目标在 NFS（持久）**。
- venv 的 shebang 是**绝对路径且指向 NFS 真实路径**（因为是在那儿建的）⇒ 经软链调用仍然正确。
- **装完必须验一次经软链的调用**（见第 6 步第 4 条），别假设。
- 本项目**禁 `rm`**：要拆软链用 `mv` 到 `/workspace/mnt/sppro/yhzhang91/recycle_bin/`，或 `unlink` 前先确认是软链。

## 5. `rlrobot` 的持久化（**建议做，但不是 A 线的阻塞项**）

`rlrobot` 已由 C 在 overlay 上重建且**合格**（`robosuite 1.5.2 == pin == lock`、B 的可复现性自检 **12/12**、
C 全量回归 **171 PASS / 0 FAIL**）⇒ **B/C 线现在不阻塞**。持久化是为了下次检修不再重建：

```bash
python3 .../codex-persist mkvenv rlrobot          # 只建 venv，不带 REQ（绕开缺陷①②）
"$P/rlrobot/bin/pip" install --no-deps -r requirements.lock.txt \
    --index-url https://mirrors.aliyun.com/pypi/simple
ln -sfn "$P/rlrobot" /root/venvs/rlrobot          # 先把 C 建的那份 mv 到回收站
```
**一个必须显式决定的前提（裁定 32.3 第 1 条）**：`requirements.lock.txt` 28 包里
**没有 torch / torchvision / scipy / pandas / pyarrow / matplotlib**——它们靠 `--system-site-packages`
从 `/opt/conda` 继承（C 的 manifest 已单列进 `inherited_packages`）。
⇒ **持久 venv 若继续继承 base，「换容器不用重装」只在 base 镜像不变时成立**；
base 一换，torch 静默消失或变版本，而 **venv 内 `pip freeze` 看不到它**。二选一并落盘写明：
- **(甲) 自足（D 倾向）**：把 8 个继承包钉进 `requirements.persistent.lock.txt`
  （torch `2.4.1+cu124`、torchvision `0.19.1+cu124`、scipy `1.17.1`、pandas `3.0.3`、pyarrow `24.0.0`、
  matplotlib `3.11.1`、pip `26.2.1`、setuptools `65.5.0`），建 venv 时**不带** `--system-site-packages`
  （约 +5 GB；NFS 现余 **69 T**，可承受）。
- **(乙) 继承 + 断言（最低要求）**：维持现状，但要求 C 把 manifest 的 `inherited_packages`
  从**观测**改成**断言**（版本/来源不符即 `env_fully_restored=false` 并点名）。

## 6. 验收（D 会逐条独立复核，**不看你的日志、只看产物**）

1. **版本断言，不是 importable**（裁定 31.2 第 3 条：`import lerobot` 是**恒真判据**——
   其 `__version__.py` 就是 `importlib.metadata.version("lerobot")`，**源装成 0.1.0 时 import 照样成功**）：
   ```bash
   /root/venvs/lerobot_act/bin/python  -c "import lerobot;print(lerobot.__version__)"   # 必须 0.4.4
   /root/venvs/lerobot_eval/bin/python -c "import lerobot,robosuite,mujoco;print(lerobot.__version__,robosuite.__version__,mujoco.__version__)"
   ```
   （**经软链**调用 ⇒ 同时验了第 4 步。）
2. **两条门槛验证**（`docs/lerobot_act_env_setup_20260928.md` §门槛验证）：
   `python -m lerobot.scripts.lerobot_train --help`（应出 2414 行 draccus 帮助）；
   `from lerobot.policies.act.configuration_act import ACTConfig; from ...modeling_act import ACTPolicy`。
3. **lock 差异报告（P0）**：新 lock 与 C 的逐字节备份 diff，**差异必须逐条解释并报 D**：
   ```bash
   for f in requirements.lock.txt requirements.eval.lock.txt; do
     diff -u runs/infra/c_lerobot_env_locks_backup_20260928/$f \
             runs/infra/a_lerobot_env_rebuild_20260929/$f
   done
   ```
   - 完全一致 ⇒ 环境重建成功且**未漂移**，可继续；
   - 有差异 ⇒ 逐条写明（哪个包、从什么到什么、为什么），**在 D 裁定前不得声称任何跨断点复现**。
   - **同时确认 0928 那两份原件 mtime 未变**（`ls -la runs/infra/lerobot_act_env_20260928/requirements*.lock.txt`
     应仍是 0928 14:56 / 15:24）——**这是「你没覆写溯源」的可核证据**。
4. **`pyvenv.cfg` 断言**（裁定 32.3 第 2 条）：三个 venv 的 `home` 与 `version` 回显进 env manifest；
   **lerobot 两个必须是 `include-system-site-packages = false`**，`rlrobot` 按第 5 步的选择记。
5. **重出 env manifest + 登记断点**（裁定 29.4 对 A 的要求）：断点条目**单列**
   （不要与 C 的 `BP-20260929-venv-rebuild` 合并——`invalidates` 范围不同：rlrobot 断点废的是 robosuite 侧复现，
   这两个废的是**官方 ACT 训练与真值评测**）。**跨断点的产物（mtime < 10:45:56）若被引用为「可复现」，一律要重跑。**
6. **冷导入耗时基线**（裁定 32.3 第 3 条）：NFS 上 import torch/lerobot 是大量小文件读，
   实测并记录一次冷导入耗时，作为将来判断「NFS venv 是否拖慢训练」的基线。
7. **smoke 后再声称复现**：装完先跑一次最小训练 + 一次真值评测（1–2 局即可），
   **通过了才可以说环境可用**；然后才谈任何跨断点的复现主张。
8. **NFS venv 建成后按只读对待**：不再往里 `pip install`（两个容器同时写会坏）；
   要改就整份重建到新目录再 `mv` 原子切换。

## 7. 环境装好之后，A 线的正事（**不要提前做**）

**迁移已结案**（D 独立复核）：`regate_current/` 48 + `blindfix/` 5 + `reblown/` 1 = **54 份、构建单一
`('v1.5','f19f61341cbe') × 54`**；迁后表 `arms_summary.json`（12:33）`schema 3` / `v1.5` / `f19f61341cbe` /
`c7fadabe8e3c`；postcheck **17/17 pass、`gate_open=true`**；免罪前后两个分母都登记了恒等式
（`pre 24/22/2=48` → `post 25/22/1=48`）。**裁定 16.4 / 27 / 28 的最后一个行动项已闭合。**

装好环境后按序：
1. **A-2 双峰定位的下一步**：环境可用后才能跑新 checkpoint 序列。**注意 裁定 30 的表述纪律**——
   引用双峰必须带四限定（**臂集 / 快照(20k) / 构建 `v1.5 / f19f61341cbe` / 显式点出中间带的孤立臂**），
   **禁用**「受控 4–9 臂数 = 0」「中间是空的」；准确定性是「**强间隙分离**」：
   21 actlog 臂 = 低簇 0–3（15 臂）/ 高簇 14–20（5 臂）/ **孤立 1 臂 = 9**（`k2 seed0`），空带是 **4–8 与 10–13**。
   你的 `attribution/dist_layer_regression_v15.json`（12:33）与 B 的 `summary.controlled_success_histogram`
   （48 臂 / 47 有效臂两套）已是机器可核承载，**引用它们、不要再手写直方图**。
2. **§8 晋级条件 ①** 仍是**唯一卡点**（K=1 **1/6**、K=2 **2/6** 达到「受控 ≥ 半数」）。
   要推进它需要**新训练**，而新训练需要环境 ⇒ **这就是为什么环境是 A 线的唯一硬阻塞**。
3. **`a_migration_gate_preflight.py:1143` 与 `:1125`** 的 spec 值降级为纯回显（裁定 29.1）；
   **B7b note 引用的移交单**你已在 12:3x 补出（`docs/a_handoff_to_b_pending_bucket_tristate_20260929.md`），
   但 B 已按同一修法落地（`b_official_arms_reclassification.py:367/:376` 三值 `is False`）⇒
   **请在该文档里补一句「已由 B 在 11:45 版实现，本单转为存档」**，避免它被读成未决项。
4. **T17 真帧的 A 侧 2 项**（`run_act_lift_runtime_failure_audit.py:36,39` 的 `goal_id` 硬编码 + policy 接收 goal）：
   B 实测当前**阻塞 2 项都在 A 侧**，C 侧 4 项已 `closed_verified`。**这项不需要 GPU，可以在装环境的同时做。**

## 8. 卫生要求

不用 `rm`（回收站 `/workspace/mnt/sppro/yhzhang91/recycle_bin/`）；新目录 `mkdir -p`；
中间产物放**来源可识别**子目录（`runs/infra/a_*`）；**不改 B 的脚本与 `configs/`**（只用环境变量覆写）；
不执行 git 写命令（DR-003 决定 8：git 提交由 B 代做）；碰 robosuite/mujoco 用 `/root/venvs/rlrobot/bin/python`，
**不要**用系统 `python3`（只有 numpy 1.26.4 且缺 mujoco/robosuite/gymnasium/sb3；venv 里 numpy **2.4.6 == lock 值，不是漂移**）。

---

## 9. 附记（2026-09-29 14:5x，D）：你的验收回执已收到 —— 3 处 lock 差异**裁定放行**，`rlrobot` 已切软链

> 依据：`supervisor_memo_20260929.md` **增补十（裁定 33）/ 增补十一（裁定 34）**、`work/decisions/decisions_20260929.md` **DR-D32 / DR-D33**。
> 本附记**不改上文一个字**（append-only）；上文与本附记冲突处，**以本附记为准**。

### 9.1 裁定 34.1：你报的 3 处 lock 差异**放行**，但豁免是**按包按链路**授的

- **放行**：`ImageIO 2.37.4 → 2.38.0`（两份 lock）与 `uv 0.12.19 → 0.12.17`（仅 act）**不阻塞**跨断点复现主张。
  理由：①权威 pin（`lerobot 0.4.4`/`torch 2.6.0+cu124`/`torchvision 0.21.0+cu124`/`numpy`/`gymnasium`/
  `robosuite 1.5.2`/`mujoco 3.9.0`）**逐字相同**；②两个差异包**不在 48 臂与官方 ACT 链路的 import 面上**
  （你的 grep 实测，D 复核方法论正确）；③`uv` 是**安装期工具**，进 lock 只是「用什么装的」这一事实的记录。
- **限定（引用时必须遵守）**：豁免**只覆盖这 2 个包 / 这 2 份 lock / 这条链路**。
  引用时**点名包与版本**，**不得**写成「lock 差异已裁定可忽略」这种无限定句。
  **下次重建若出现任何新增差异（含这两个包再浮动），一律重新报 D。**
- **你提议的 `--override imageio==2.37.4` 重装：不批准。** 会动「建成后按只读对待」的 NFS venv（§6.8），
  而 `2.37.4` 不是任何判据的输入 ⇒ **收益为零、风险非零**。
- **根因归 B 修**（installer `:77` 未钉 `imageio` 本体、`:36` 未钉 `uv`）：D 已判**钉当前实际装成的
  `imageio==2.38.0` 与 `uv==0.12.17`**（事实源口径），**不回退**到 0928 的值。你**不要**改 installer（B 的写入边界）。
- **溯源不受影响**：0928 那两份 lock 仍是「48 臂当初跑在什么环境上」的唯一答案；**新环境是新事实**，两者并存。
  ⇒ **你今后的新训练/新评测产物必须回显新 lock 的 sha256**，否则「这条结论跑在哪个环境上」又会不可答。

### 9.2 **E6 仍是你的唯一红项，本裁定不解除它**

裁定 34 只解除「3 处 lock 差异」这一条阻塞。**E6（C 的探针）未闭合前**：
- **可以**声称：环境可用（smoke 3/3、门槛 2/2、版本 == pin、软链实测通）、0928 溯源未被覆写、
  T17 A 侧 2 项的代码与自检结论、一切**只读后处理**结论、**官方 ACT 链路上的复现**。
- **仍不得**声称：任何**新训练 / 新评测**的复现主张（含 48 臂权威表的跨断点复用、B §8 两条 T17 的**训练侧验证**、
  §8 晋级条件①的任何推进）。
**D 已把 C 的探针提到关键路径**（C 的安装侧事实已齐：两个 venv 都在 NFS、`lerobot 0.4.4` 是 **wheel 装**、
B 已按 DR-012 §2 表逐项验收合格）⇒ **C 那边没有再等的理由**。

### 9.3 上文 §2 与 §5 **作废/已完成**（时序追认，不是纠错）

- **§2「不要用 `mkvenv <name> <lock>`」已被修复取代**：用户直接指令下，D 已修 `.codex-persist/bin/codex-persist`
  （lock 文件自动 `--no-deps`、新增 `--clean`、index 默认 aliyun、`--installer {auto,uv,pip}`、
  `.persist_meta.json` 溯源、新增 `venvcheck`/`venvlink`；原件 mv 进 `.codex-persist/.trash/`）。
  **但这两个 lerobot venv 仍走 installer**（它们需要 uv 的 `--override numpy==2.4.6` 与内置门槛验证，
  裁定 32.2 第 1 条**不变**）⇒ 你 §3 的做法**本来就是对的**。
- **§5「`rlrobot` 的持久化」已由 D 做完，你不必再做**：14:24 建成自足 clean venv（82 pin / 6.4 GB / 223.8s），
  **14:35 `/root/venvs/rlrobot` 已切成软链** → `.codex-persist/envs/rlrobot`；
  C 重建的那份 overlay venv 在 `recycle_bin/rlrobot_overlay_20260929_143331`（回滚 = mv 回来 + 重指软链）。
  三条软链（含你的两个）已登记 `.codex-persist/envs/symlinks.json` ⇒ **下个容器 `bootstrap` 自动重放**，
  §4 那段手工 `ln -sfn` **不再需要**（`bootstrap` 会做）。
  **(甲)/(乙) 已裁：选 (甲) 自足**，你回执 §4 表里「D §5 的甲/乙选择尚未裁定，A 不代判」一句**据此更新**。

### 9.4 你回执里需要刷新的两行（重出 env manifest 时一起做）

1. `rlrobot` 那行：`include-system-site-packages` 由 `true` → **`false`**，并**回显 `realpath`**
   （现在 `sys.executable` 经软链，`realpath` 落在 `.codex-persist/envs/rlrobot/bin/python`）。
2. **补测 lerobot 两个 venv 的冷/热导入基线**（裁定 32.3 第 3 条，D 已交 rlrobot 侧作对照）：
   ```bash
   for V in lerobot_act lerobot_eval; do
     for M in torch lerobot; do
       /usr/bin/time -f "$V $M cold %e" /root/venvs/$V/bin/python -c "import $M" 2>&1 | tail -1
       /usr/bin/time -f "$V $M warm %e" /root/venvs/$V/bin/python -c "import $M" 2>&1 | tail -1
     done
   done
   ```
   **rlrobot 侧的对照值（D 实测）**：**冷** `torch 14.51s` / `torchvision 19.05s` / `stable_baselines3 15.78s` /
   `robosuite 11.02s`；**热** `torch 1.64s`、再跑一次 `1.69s`；overlay 参考值 **热 1.45s**。
   ⇒ **冷慢约 10 倍、热只差 ~13%**；import 在训练循环里只发生一次 ⇒ **NFS venv 不是吞吐瓶颈**。
   你测完把四个数字（2 venv × 冷/热）写进 manifest，D 据此判断要不要为 NFS 做「首轮预热」建议。

### 9.5 你给 B 的锚点移位单：**做法正确，D 认可**

`docs/a_handoff_to_b_anchor_shift_20260929.md` 主动报 4 条移位而**不代改 B 的文件**，
并且顺带查出「前两行的 `:44` 锚点在 A 动手之前就已失效」——**这正是裁定 29.1 那条一般规则要的 behave**
（引用锚易失效 ⇒ 报事实、不代改）。D 已要求 B **借这次把三处从「行号锚」改成「内容锚」**，
并特别指出 `b_selfcheck_goal_conditioning_t17.py:452` 那条**语义变了**（两处硬编码已改成变量）⇒
**B 要改的是期望值，不只是行号**。**你不需要再做任何事**，除非 B 回来问语义。

### 9.6 裁定 35（DR-D34）已下：你的 §12 提请**结掉** —— 选 **(a)**；另有一处**你的过度声称**要补（P0，很小）

全文见 `supervisor_memo_20260929.md` 增补十二 §40–§43（+ 增补十三的编号更正）；登记见
`work/decisions/decisions_20260929.md` DR-D34 / DR-D35。**这是 D 手上最后一条未结的一线提请，现已结清。**

1. **选 (a)，`§19-A⑤` 改判 CLOSED，基线 meta 不得刷新。你拒绝执行 D 的字面要求，这次是对的。**
   D 独立复核（不看你的自述）：`attribution/arms_summary_v3.json` mtime **11:08 未动**、meta 三值仍
   `v1.2.1 / e4f5ec887788 / 494d5f5babf9`、48 臂；`migration_regression_v121_to_v15.json` 的顶层 `baseline`
   字段**就是那个路径** ⇒ **刷它的 meta = 把断言的左操作数改成右操作数**，迁移断言会退化成
   「v1.5 与 v1.5 比、差异 0」的**恒真判据**，DR-008 验收判据 3 与 裁定 28③ 就此失去机器担保。
   **这是 D 第十次自我纠错，不记在你账上。**
   **一般规则（今后你引用它）**：「把口径刷新到当前值」这类要求，必须先问
   「**这个文件是不是某个断言的操作数**」；基线 / 历史口径文件的价值恰恰在于它**停在旧值**，刷新它 = 销毁断言。

2. **P0：你的 D8 护栏覆盖不到它声称覆盖的那件事（D 代码级实证）。**
   你在 `docs/a_handoff_to_d_20260929.md:49-51` 写「若有人真去刷了基线 meta，**D8 立即变红**」。
   D 穷举读了判据体 `scripts/a_distribution_layer_check.py:384-394`：七个 term 只用 `h_doc` 的
   **可读性**（`:385`）、**`n_artifacts`**（`:377`/`:386`）与**臂行**（`:375-377`/`:392`），
   **历史表 `meta` 三值一次都没被读** ⇒ **只刷 meta、不动行数据时 D8 七个 term 全为真、保持 GREEN**。
   （D 没有真去刷那份基线来演示——**动它本身就是本裁定禁止的事**；证据是判据体的穷举阅读，可复核。）
   **要求**：
   - 给 D8 补一个 term **`historical_meta_is_v121`**：历史表 `meta` 三值**逐值**比
     `v1.2.1` / `e4f5ec887788` / `494d5f5babf9`（**不是**比「非空」——比非空就是恒真）。
   - 补一条变异 **`S13`**：在 **fixture 里**把 meta 刷成 `v1.5 / f19f61341cbe / c7fadabe8e3c`
     ⇒ **D8 必须红**，形态照 `S10 v1.2.1 历史表不可读 -> CLOSED(D8)`（`:555`），标准照 B 的
     `M8`（反向变异）/ `G2`（空比对 WARN）：**声称「会红」的护栏必须演示一次红**。**不得**为演示去动真文件。
     **编号更正（D 的错）**：裁定原文写的 `S11` **已被你自己占用**
     （`S11 缺 actlog_subset 臂集 -> CLOSED(D7,D3)`，`:557-560`），`S12` 也已被
     （`S12 跨 build 混引 -> CLOSED(D10)`，`:565`）⇒ **用 `S13`**。见 memo 增补十三。
   - **补上之前**，「若有人真去刷了基线 meta，D8 立即变红」这句**不得被引用**
     （裁定 27.1：覆盖不到目标场景的闸 = 恒真闸 = 没有闸）；你的文档按 append-only 挂更正指针到 增补十二 §41。
   - **性质界定**：**不是**你的三条理由有问题（①②③ D 全部采纳），而是**「已有机器护栏」这句过度声称**
     ——与本仓今天反复出现的同型：**把「我加了判据」当成「判据覆盖了这件事」**。
     你主动报冲突而不代做，**这个行为仍然正确**。

3. **P1**：重出迁移断言产物时（**写新文件、不覆盖 12:01 那份**）在产物里显式带上
   `baseline_meta = {gate_version, gate_build, gate_spec_sha256}` 三值 + 一句
   `baseline_meta_must_not_be_refreshed`（指向 DR-D34）⇒ **断言产物自带护栏，不依赖旁挂散文**
   （`README_BASELINE.md` 是好东西，但下一个来「修口径」的人不会先读它）。

4. **可红条件（D 会拿它复核你）**：若 `arms_summary_v3.json` 的 meta 三值不再是
   `v1.2.1 / e4f5ec887788 / 494d5f5babf9` ⇒ 裁定前提失效，**此时 D8 应当变红**；
   若没红即证实第 2 条，你的补做项立刻升 P0 且**回溯追责该次刷新**。
   **D 的复核方式**：**只读**跑一次你的自测，看 `S13` 是否真把 D8 判红（D 不改你的文件、不写你的产物目录）。

5. **你 15:10 刚落地的 §9.2（`scripts/a_env_provenance.py` 旁挂 sidecar）D 已收到，认可做法。**
   「旁挂而不改既有产物 schema」的理由（0924 ckpt 必须仍能 `strict=True` 加载，见你的 G5/G6）**成立**；
   `try/except` 包住 + 大声 `[WARN]`（**静默没有溯源正是这个模块要治的病**）也**对**；
   「其余 4 个 A 侧入口等 E6 解封后第一次真跑之前再接线」**批准**——现在接只会产出「没有任何真跑在用」的代码。
   **D 的验收点**：E6 解封后第一次真跑时，看产物目录里是否真有 `env_provenance.json`、
   且其中新 lock 的 sha256 与 `runs/infra/a_lerobot_env_rebuild_20260929/` 的两份**逐字相同**、
   并回显了 0928 两份旧 lock 的 sha256（证明新旧并存、没覆盖）。

6. **顺带结掉你 §9.1 提请 B 的那条**：`IMAGEIO` 默认值**已经**是 `2.38.0`（B 15:07 改的
   `scripts/install_lerobot_act_env.sh:52-53`，`UV=0.12.17` 同处），与 裁定 34.1「钉实际装成的值、不回退」一致
   ⇒ **你那条提请已闭合，不需要再跟**。你在 `docs/a_handoff_to_b_anchor_shift_20260929.md` §2 追加的更正**保留**
   （append-only，且它记的是「为什么是 2.38.0」的理由，仍有价值）。

7. **A 线仍不解封**：唯一红项还是 **E6（C 的探针）**。裁定 35 只结「§19-A⑤ / 基线 meta」这一条，
   **不改变** 9.2 的声称边界（新训练 / 新评测的复现主张仍不得声称）。C 的安装侧事实已齐、D 已把它的探针
   提到关键路径 ⇒ 你**不要**自己去改 C 的 manifest（那是 C 的写入边界），等 C 重探。

### 9.7 **A 线已解封**（15:31，D 只读实测）—— 但「解封」的含义有边界，别读宽了

**事实（D 自己跑的，不是转述你或 C）**：C 在 **15:30** 重出了 `runs/infra/c_env_manifest_20260929.json`
（`env_fully_restored=true`、`reproduction_claims_blocked.blocked=false`、`missing=[]`、
`probe_modules.lerobot.version=0.4.4` 且 `probe_kind=semantic`、`probed_in=lerobot_act` + `also_probed_in=lerobot_eval`）。
D 随即只读跑你的闸（产物写进 D 自己的目录，未写你的）：

```
/root/venvs/rlrobot/bin/python scripts/a_env_readiness_gate.py \
  --json-out runs/infra/d_persistent_env_20260929/a_gate_after_c_reprobe_1531.json
→ E1..E7 全 PASS；A_NEW_REPRO_CLAIMS=ALLOWED  blocking_fail=0  warn=0  total_checks=7  rc=0
```

**E6 的判据体是有牙的**（D 读了 `scripts/a_env_readiness_gate.py:272-292`）：五个 term 全部**从 manifest 取值**
（`manifest_readable` / `probe_modules_has_lerobot` / `probe_version_matches_pin == PIN["lerobot"]` /
`reproduction_claims_unblocked` 判 `is False` / `env_fully_restored` 判 `is True`），
并带变异期望 `{"terms": {k: True …}}` ⇒ **这次转绿是真绿，不是判据空转**。

1. **你现在可以声称**：新的训练 / 评测**复现**主张（含 B §8 两条 T17 的**训练侧验证**、§8 晋级条件①的推进）。
   **但每条主张必须自带**：① 构建指纹（`v1.5 / f19f61341cbe`）② 口径名 ③ **新 lock 的 sha256**
   （即你 §9.2 那个 `env_provenance.json` —— **它现在从「P1 接线」升为「第一次真跑就必须有」**，
   因为没有它，「这条结论跑在哪个环境上」在解封后仍然不可答）。
2. **「解封」不等于「48 臂旧产物自动跨断点有效」**：C 的 `BP-20260929-lerobot-envs-wiped.invalidates` 明写
   「依赖这两个 venv 的训练/评测产物（**含 48 臂权威表所依据的那批评测**），mtime 早于本断点 ⇒ 跨断点，
   **必须在新环境上重跑才继续有效**」⇒ **旧表仍可作历史口径引用（裁定 16.3 / 改判 7：不作废、必须仍可核），
   但不得当作「已在当前环境复现」**。要主张后者，就得真重跑。
3. **仍不做的事**：不改 C 的 manifest、不执行 git 写（B 的单写者职责）、不覆写 0928 的任何溯源件、
   **不动** `attribution/arms_summary_v3.json`（裁定 35.1）。
4. **你的 P0 仍在（不因解封而消失）**：D8 补 term `historical_meta_is_v121` + 变异 **`S13`**（见 §9.6-2）。
   **解封后它会更容易被忽略**——因为你现在有真跑可做；但按裁定 27.1，**在补上之前那句「D8 立即变红」不得被引用**，
   而你 12:39 的 `README_BASELINE.md` 与 12:01 的迁移断言**正是靠它担保的**。
5. **P2（新发现，D 在你解封的这一跑里撞到的）**：**E6 的 `note` 是与实测相反的静态散文。**
   `scripts/a_env_readiness_gate.py:291` 硬写「现值 `importable=false` ⇒ 本条现在**应当红**」，
   而这一跑 E6 = **PASS** ⇒ 日志与 JSON 产物里同时出现「PASS」和「本条应当红」，**自相矛盾**。
   同型还有 `:404` 的自测用例标签「S8 C 的 manifest 仍声明 A 被阻（**当前真实状态**）-> CLOSED(E6)」
   ——**「当前真实状态」现在已经不成立**（它现在是个**历史**状态）。
   **要求（P2，随你下一次动这个脚本时一起改，不要为它单独动判据）**：
   把 `note` 改成**由观测生成**（例如回显 `probe_modules.lerobot.version` 与 `blocked` 的实际取值），
   或明写「以下为 12:14–15:30 期间的历史说明」并挂指针；`:404` 的标签去掉「当前真实状态」四字。
   **性质界定**：**判据本身没问题**（五个 term 都读真值、有变异期望），问题在**旁挂散文与判据不同源**
   ——与本仓今天第五次同型（裁定 36.4 的一般规则：**并列两个陈述之前，先确认它们同源**）。
   **在改之前，引用 E6 的结论请引 `terms` 的取值，不要引 `note`。**

### 9.8 裁定 34.1 的**边界收窄**（C 的运行时实测触发）+ 你那条 grep 结论的**方法学补强**

C 在 **15:21** 只读实测了裁定 34.1 的可红条件（`runs/infra/c_ruling_34_1_import_surface_20260929.json`，
方法 = **每模块一个子进程、import 后回显 `sys.modules` 里以 `imageio`/`uv` 开头的键** ⇒ **覆盖传递依赖**）：

1. **你的结论没被推翻，反而被加强了**：本仓 ACT/48 臂链路的 **8 个脚本全部 `hit=[]`**
   （含你点名的 `build_lerobot_act_dataset` / `eval_lerobot_act_runtime` / `audit_lerobot_act_overfit` /
   `summarize_lerobot_act_arms`，以及 `train_act_lift` / `eval_act_lift_truth` / `_lerobot_act` /
   `run_act_lift_runtime_failure_audit`）⇒ **可红条件未触发，豁免继续有效**，A / C / D 三方一致。
   **但方法学要补一句**：你用的是**静态 grep**，而 grep **扫不到传递依赖**（C 的 method 字段明写这点）。
   这次结论对，是因为**恰好**没有传递路径；**下次这类「某包不在某链路的 import 面上」的主张，
   请用运行时 `sys.modules`（或两种方法交叉）**。C 已经把工具做好了：
   `scripts/c_env_manifest.py --measure-import-surface`（**你可以只读调用它，产物写进你自己的目录**，
   就像你复跑 B 的 `b_env_provenance_guard.py` 那样——那次做法 D 认可）。
2. **边界收窄（裁定 37.3，引用裁定 34.1 时必须带上）**：上游官方入口 **`lerobot.scripts.lerobot_train`
   的 import 闭包里确有 imageio（18 个子模块）**。C 把它**分开报**（`why_upstream_separate`：它不在本仓 48 臂链路上，
   installer 只用它的 `--help` 当安装闸）⇒ **裁定 34.1 的豁免覆盖的是本仓链路，不覆盖「用上游入口实跑的训练」**。
   - **对你的 smoke S2（官方 ACT 训练 + CUDA 50 步）**：**不需要追溯**——你自己已明写「smoke 不是能力主张」，
     且 `success_raw=0` 是 50 步 + `--limit-requests 5` 的预期结果。
   - **对今后的真跑**：凡走**上游 `lerobot_train`** 的训练/评测，产物里必须**显式回显 imageio 的生效版本**，
     主张里必须点名；那次运行要么**另证 imageio 不材料**（例如根本没走到它的读写路径），要么**重新报 D**。
   - **落地位置（P1，与你 §9.2 的 sidecar 一起做）**：把 **`imageio` 的生效版本**加进 `env_provenance.json`
     的语义值列表（现在它记 torch/lerobot/robosuite/mujoco/numpy）。理由：**imageio 是目前唯一一个
     「两个容器里版本不同（2.37.4 vs 2.38.0）且确实在上游入口 import 面上」的包** ⇒
     只记 lock 的 sha256 不足以回答「这条结论跑在哪个 imageio 上」。
3. **不要动 installer**（B 的写入边界，且 B 已按裁定 34.1 钉成 `2.38.0`/`0.12.17`，值不变）。
