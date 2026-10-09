# lerobot 环境重装：权威 pin、安装方式与一个**必须避开的错源**（2026-09-29）

负责线：B（环境文档责任线，D 的 裁定 29.4 §19-B④ 指派）。接收人：C（P0：`probe_modules` 加 `lerobot`）、
A（**lerobot 装好前不得声称任何新训练/评测复现**，裁定 29.4）。抄送：D。
来源：从 `docs/lerobot_act_env_setup_20260928.md` §环境规格（`:276-301`）与
`scripts/install_lerobot_act_env.sh` 摘出，**并补 0929 检修后的实测**。登记：DR-012。

---

## 1. 现状（0929 实测，不是推测）

| 事实 | 实测 |
|---|---|
| `/root/venvs/` 下只剩什么 | **只有 `rlrobot`**（`ls /root/venvs/`）⇒ `lerobot_act` 与 `lerobot_eval` **两个 venv 都被检修抹掉了** |
| 所以缺口的准确表述 | **不是**「`rlrobot` 里少一个 `lerobot` 包」——lerobot 按设计**从不**装在 `rlrobot` 里（`requirements.lock.txt` 28 包无 lerobot，`docs/lerobot_act_env_setup_20260928.md:278` 明写两个独立 venv）。准确表述是「**A 的训练/评测环境整体需要按 installer 重建**」 |
| 这对 C 的探针意味着什么 | `probe_modules` 加 `lerobot` 时，**不要在 `rlrobot` 解释器里探**（那里本来就不该有）；要探 `lerobot_act` / `lerobot_eval` 两个 venv 是否存在，且在**各自的解释器**里验版本 |
| `rlrobot` 侧 | 已由 C 重建并合格：`robosuite 1.5.2 == pin == lock`、B 的可复现性自检 **12/12**（裁定 29.4 已解封 B/C 的只读后处理与 robosuite/mujoco 依赖项） |

## 2. 权威 pin（照抄即可，不要"顺手升级"）

| 项 | 值 | 出处 |
|---|---|---|
| **lerobot** | **`0.4.4`（PyPI 包，不是 git 源装）** | `scripts/install_lerobot_act_env.sh` 的 `LEROBOT="${LEROBOT:-0.4.4}"`；lock 实测 `lerobot==0.4.4` |
| 索引 | `https://mirrors.aliyun.com/pypi/simple`（`INDEX`） | 同上；**pypi.org 直连不通**，且 pip.conf 的 ustc 源会 302 到 tuna 并对本机 403 |
| 安装器 | **uv**（不是 pip） | pip 走代理下大 wheel 只有 ~0.7 MB/s，同 URL 用 uv 是 ~40 MB/s；**uv 不读 pip.conf**，正好绕开上面两条 |
| torch / torchvision | `2.6.0` / `0.21.0` | lerobot 0.4.4 声明 `torchvision>=0.21.0,<0.26.0`；系统自带的 0.19.1 属"不被官方支持的运行时" |
| base 解释器 | `/opt/conda/bin/python3.11`（3.11.9），venv **不带** `--system-site-packages` | 带 system-site-packages 会把 conda 的 TensorFlow + jax 拖进 import 链，jax/numpy 版本对不上时报成 `cannot import name 'PreTrainedModel'`（09-24 那串 ImportError 的真根因，**不是** transformers 装坏） |
| 训练 venv | `/root/venvs/lerobot_act`：lerobot 0.4.4 / torch 2.6.0 / torchvision 0.21.0 / **numpy 2.2.6** / **gymnasium 1.3.0** | lock `runs/infra/lerobot_act_env_20260928/requirements.lock.txt`（0928 14:56，2009 B） |
| 评测 venv | `/root/venvs/lerobot_eval`：同上 + **numpy 2.4.6 / gymnasium 1.2.3 / mujoco 3.9.0 / robosuite 1.5.2 / numba 0.67.0 / opencv-python 4.10.0.84 / py_trees 2.6.0 / imageio-ffmpeg 0.6.0** | lock `runs/infra/lerobot_act_env_20260928/requirements.eval.lock.txt`；C 另有备份 `runs/infra/c_lerobot_env_locks_backup_20260928/` |
| 为什么评测 venv 要 `--override numpy==2.4.6` | `robosuite 1.5.2 → mink 0.0.5 → numpy<2.0.0` 与本项目 numpy 2.4.6 冲突，正常解析直接判 unsatisfiable；mink 的 pin 是陈旧的，**实测能跑** ⇒ 用 override 强制。**只有评测环境需要**（训练环境不装 robosuite，保持干净） | installer `:60-77` 注释 + 0928 实测 |

> 注意这与 C 的 ADR-C-006 是**同一个冲突的两个现场**：`rlrobot` 侧表现为
> `ResolutionImpossible`（pip 26.2.1 解析器更严），`lerobot_eval` 侧表现为 uv 需要 `--override`。
> 口径一致（C 提出、D 采纳）：**解析器到不了某个组合，不代表那个组合不可用**；
> 以「实际装成并跑通全量回归」的 lock 为事实源，冲突报给 D，**不要就地放宽 pin**。

## 3. 重装命令（唯一路径）

```bash
bash scripts/install_lerobot_act_env.sh          # 建 lerobot_act + lerobot_eval，并跑门槛验证、写两份 lock
BUILD_EVAL_ENV=0 bash scripts/install_lerobot_act_env.sh   # 只要训练环境时
```

装完**必须**过的门槛（installer 已内置，手动复核也照这两条 + 一条版本回显）：

```bash
/root/venvs/lerobot_act/bin/python -c "from lerobot.policies.act.configuration_act import ACTConfig; \
from lerobot.policies.act.modeling_act import ACTPolicy; print('OK')"
/root/venvs/lerobot_act/bin/python -m lerobot.scripts.lerobot_train --help > /dev/null && echo OK
/root/venvs/lerobot_act/bin/python -c "import lerobot; print(lerobot.__version__)"   # 必须是 0.4.4
```

## 4. **必须避开的错源**：D 在 裁定 29.4 里提的候选 checkout 比 pin 落后 **488 个 commit**

D 找到的候选源 `/workspace/cache/yhzhang91/zptang/lerobot_0cf8648/lerobot`（目录名自带 commit）——
B 实测（只读，未改他人副本一个字）：

| 实测项 | 值 | 含义 |
|---|---|---|
| 该 checkout 的 HEAD | `0cf864870cf29f4738d3ade893e6fd13fbd7cdb5`（2025-05-28，"[Fix] Unpin torch beyond 2.6.0…"） | 目录名里的 `0cf8648` 就是它 |
| `git rev-list --left-right --count v0.4.4...HEAD` | **`488  0`** | HEAD 比 tag `v0.4.4` **落后 488 个 commit**、领先 0 |
| 该 HEAD 的 `pyproject.toml` | `version = "0.1.0"` | **从它装出来的包会自报 0.1.0**，`lerobot==0.4.4` 的 pin 直接对不上 |
| tag `v0.4.4` 在该 mirror 里 | 存在，= `8fff0fde7c79f23a93d845d1a50e985de01f8b8a`（2026-02-27），其 `pyproject.toml` 的 `version = "0.4.4"` | 所以离线源装**可行**，但**必须先 checkout 到 tag** |
| 远端 | `https://gitee.com/mirrors/lerobot.git` | mirror，不是上游 |

⇒ **裁定 29.4 里那句"候选源"要加一条限定**：`lerobot_0cf8648` 这个工作副本**停在 0cf8648**，
直接 `pip install .` 会得到 **0.1.0**，而 48 臂权威表依赖的官方 ACT 入口
（`lerobot.scripts.lerobot_train`、`normalize_processor.py` 的行为）**是 0.4.4 的**。
这不是"版本略旧"，是**差 488 个 commit 的另一个 API**。

**离线回退的正确写法**（仅当 aliyun/PyPI 都不通时）：

```bash
# 不要动他人的工作副本：在自己的目录里 clone 该 mirror 并 checkout tag
git clone https://gitee.com/mirrors/lerobot.git /workspace/mnt/sppro/yhzhang91/scripts/lomoon_claude/tmp/lerobot_v044
git -C /workspace/mnt/sppro/yhzhang91/scripts/lomoon_claude/tmp/lerobot_v044 checkout v0.4.4   # = 8fff0fde…
# 装完仍必须验 lerobot.__version__ == 0.4.4（源装可能自报 pyproject 里的静态值）
```

D 已裁定的另外两条照旧：`sqzhang26/gaoyuxuan/lerobot` 与 `clzhang25/LIBERO/lerobot` 是**他人副本**，
**不得**当本项目 pin。

## 5. 给 C 的探针要求（P0，裁定 29.4）——**只验 importable 抓不到上面这类错**

1. 探针目标必须是 **`lerobot_act` / `lerobot_eval` 两个 venv 各自的解释器**，不是 `rlrobot`。
2. 判据不能只是 `import lerobot` 成功，必须验 **`lerobot.__version__ == "0.4.4"`**；
   源装场景下 `__version__` 来自 `importlib.metadata.version("lerobot")`
   （实测该文件就是这么写的），装成 0.1.0 时 import 照样成功 ⇒ **只验 importable 是恒真判据**。
3. 回显**安装来源**：PyPI wheel（`direct_url.json` / `INSTALLER`）还是源装（`-e` / 本地路径），
   源装必须回显 **commit**（`v0.4.4` = `8fff0fde7c79f23a93d845d1a50e985de01f8b8a`）。
4. 两份 lock（train / eval）都要进 `lock_conformance` 比对；评测环境那条 `numpy==2.4.6` 的
   `--override` 属**已声明的例外**，要在 manifest 里写明理由，不能被读成"pin 漂移"。

## 6. 与门禁/权威表的关系（别误读）

- 本文档**不改任何判据、不改任何产物数字**。48 臂权威表现值 = **`v1.5 / f19f61341cbe`**
  （引用锚只在 **build 轴**，裁定 29.1；**不带 spec 值**）。
- lerobot 缺失**不影响**已落盘的 48 臂裁定与免罪结论（那些是**只读后处理**，裁定 29.4 已解封），
  它影响的是**新的训练/评测**：在两个 venv 按 §2 的 pin 重建并通过 §3 的门槛之前，
  **A 不得声称任何新的复现**（裁定 29.4）。

---

## 7. 裁定 32（DR-D31）落地 + B 的验收实测（2026-09-29 14:0x–14:4x 追加）

> **本节为追加，§1–§6 原文一字未改**；与 §1/§2/§3 冲突之处以本节为准，并按 append-only
> 给出更正指针（§7.5）。本节所有数字都是 B 现场实测，不是转述。

### 7.1 裁定 32.1 责任改判 + 「9 个变量全部可覆写」B 实测成立

裁定 31.5 附条原写「**B 执行安装** → A 验证 → C 探针」，裁定 32.1 按用户指令**改判为 A 执行安装**，
B 的角色是「**给出权威 pin 并验收**」。B 认这个改判（理由与 D 相同：谁用这个环境跑训练，谁负责它装对了），
并已按新分工执行：**B 全程没有跑任何安装命令**，只做了只读验收（§7.4）与判据落地（§7.3）。

D 在 裁定 32.1 断言「installer 已把 9 个变量全部写成可覆写，A 不需要改脚本」——这是**对 B 的文件**做的断言，
B 逐个实测（`scripts/install_lerobot_act_env.sh`，只读）：

| 变量 | 行 | 写法 | 可覆写 |
|---|---|---|---|
| `VENV` | `:23` | `${VENV:-/root/venvs/lerobot_act}` | ✓ |
| `BASE_PY` | `:24` | `${BASE_PY:-/opt/conda/bin/python3.11}` | ✓ |
| `INDEX` | `:25` | `${INDEX:-https://mirrors.aliyun.com/pypi/simple}` | ✓ |
| `TORCH` | `:26` | `${TORCH:-2.6.0}` | ✓ |
| `TORCHVISION` | `:27` | `${TORCHVISION:-0.21.0}` | ✓ |
| `LEROBOT` | `:28` | `${LEROBOT:-0.4.4}` | ✓ |
| `LOCK_OUT` | `:29` | `${LOCK_OUT:-<repo>/runs/infra/lerobot_act_env_20260928}` | ✓（**默认值就是 裁定 32.4 的雷**，见 §7.3） |
| `EVAL_VENV` | `:68` | `${EVAL_VENV:-/root/venvs/lerobot_eval}` | ✓ |
| `BUILD_EVAL_ENV` | `:69` | `${BUILD_EVAL_ENV:-1}` | ✓ |

⇒ **9/9 成立，D 的断言正确**，A 确实不需要改 B 的脚本。

### 7.2 裁定 32.2：`codex-persist mkvenv` 的两处缺陷 —— 装 lerobot 那两个 venv **一律走 installer**

B 复述 D 的裁定（因为本文档是 裁定 32.1 认定的**唯一权威 pin 来源**，A 照抄这里）：

1. **`mkvenv` 不得用于 `lerobot_act` / `lerobot_eval`。** 两个原因：① `pip install -r` 没有
   `--no-deps` ⇒ 必撞 `ResolutionImpossible`（`robosuite 1.5.2` 要 `mink==0.0.5`，lock 钉 `mink==1.2.0`，
   与 §2 末行是同一个冲突的两个现场）；② `mkvenv` 硬编码 `--system-site-packages` 且不覆写 index ⇒
   正好踩中 §2 表里那条「不带 `--system-site-packages`」（09-24 那串 `cannot import name 'PreTrainedModel'`
   的真根因）与 ustc 源 403。**一律走 `scripts/install_lerobot_act_env.sh` + 环境变量覆写路径。**
2. **`mkvenv` 用于 `rlrobot` 时不要带 REQ 参数**：先 `mkvenv rlrobot` 只建 venv，再手工
   `pip install --no-deps -r requirements.lock.txt --index-url https://mirrors.aliyun.com/pypi/simple`。
3. `.codex-persist/bin/codex-persist` 在**项目仓外**、是用户的共享基础设施，**不在 B 的写入边界**
   （B 只写本仓 `scripts/b_*`、`docs/b_*`、`configs/b_*`、`runs/infra/b_*`、B 的 decisions 与日报追加）
   ⇒ **B 不改它**。D 也已声明不改。B 实测到 14:2x 该文件已带 `--clean` / `--find-links`
   / `venvcheck` 子命令（见 D 的 `requirements.persistent.lock.txt` 头部 `install=` / `verify=` 两行），
   即 裁定 32.2 建议 3 的最小修法**已有人落地**；README「依赖持久化」那节仍需补一行
   「从 lock 安装必须 `--no-deps`」的警告 —— **该义务属 infra 会话/用户，不属 A/B/C/D 任何一线**，
   B 已在 DR-013 与本节双处登记，避免它掉进「谁都不写」的缝里。

### 7.3 裁定 32.3 / 32.4：B 的判据落地 —— `scripts/b_env_provenance_guard.py`（5 判据 + 10/10 变异）

散文纪律拦不住手滑，所以两条裁定都做成会红的闸（新文件，**不改 installer**，A 跑安装时 B 不碰它）：

| 判据 | 锚 | **可红条件** |
|---|---|---|
| `G1_locks_0928_not_overwritten` | 裁定 32.4 / P0 | 0928 两份 lock 的 sha256 != 实测基线（`68a38731c5b5…` / `b6db07e2e31c…`）、或 mtime 落在 0929 及以后、或文件缺失、或 C 的逐字节备份与原件不一致 |
| `G2_rebuild_lockout_not_default` | 裁定 32.4 / P0 | `--rebuild-dir` 解析后 **== 0928 目录**（= 用了默认 `LOCK_OUT`，会就地覆写溯源件）；同时逐包枚举新旧差异，**空比对会 WARN**（防止「差异 0 处」被读成通过） |
| `G3_persistent_pin_conformance` | 裁定 32.3 前提 1 | 28 个项目 pin 与 `requirements.lock.txt` 不符；6 个原继承 pin / 2 个引导件 pin 缺失或版本不符；**`torch`/`torchvision` 的 pin 少了 `+cu124`**；给了 `--frozen` 时 freeze 产物与 pin 版本不符或真缺包 |
| `G4_base_python_assertion` | 裁定 32.3 前提 2 | `pyvenv.cfg` 的 `home` != `/opt/conda/bin` 或该目录不存在、`version` != `3.11.9`、`executable` 不存在、或解释器自报版本 != `3.11.9`（**验语义值**，裁定 31.2 第 3 条） |
| `G5_numpy_shadowing` | 裁定 32.3 前提 1 | venv 里**生效**的 numpy != `2.4.6`（退回 base 的 `1.26.4` = 遮蔽失效，属「半自足」静默漂移） |

**有牙证明**：`--selftest` **10/10**（baseline 合成世界全绿 + M1 sha 篡改 / M2 备份分叉 / M3 mtime 改今天 /
M4 `LOCK_OUT` 用默认值 / M5 `torch` 改 cu121 / M6 base python 说成 3.10.14 / M7 numpy 遮蔽失效 /
M9 freeze 里 torch 漂移，**全部抓住**；另含 1 条**反向**变异 M8：freeze 用发行名原样
（`ImageIO`/`Jinja2`/`typing_extensions`/`PyYAML`/`Pygments`/`Werkzeug`）且不含 `pip`/`setuptools`
⇒ **不得**误报缺失。M8 存在的理由见 §7.6）。临时目录一律 `mv` 到回收站，脚本内无 `rm`/`rmtree`。

**现场判定（14:3x，两个 venv 各跑一次）**：`5 项判据 → PASS 5 / WARN 0 / RED 0`，exit 0。
产物：`runs/infra/b_env_provenance/guard.json`、`guard_persistent_venv.json`、
`persistent_rlrobot_frozen_20260929.txt`（82 行，`pip freeze --all`）。

**裁定 32.3 前提 1 的选项声明（D 要求「必须落盘写明选了哪个」）**：选 **(甲) 自足**，
且 **(甲) 已建成并由 B 验收通过** —— `.codex-persist/envs/rlrobot`（14:24，6.4 GB，
`include-system-site-packages = false`）实测 `torch==2.4.1+cu124`、`torchvision==0.19.1+cu124`、
`scipy==1.17.1`、`pandas==3.0.3`、`pyarrow==24.0.0`、`matplotlib==3.11.1`、`pip==26.2.1`、
`setuptools==65.5.0`、`numpy==2.4.6`，与 `requirements.persistent.lock.txt` 的 82 个 pin
**逐 pin 对账全过**（`--frozen`），`nvidia-*-cu12` 传递闭包 14 个轮子齐备。
**(乙) 仍是最低要求且尚未满足**：把 C manifest 的 `inherited_packages` 从**观测**改成**断言**属 C 的写入面，
B 不代做；B 侧可断言的部分已由 G3/G4/G5 承担。

**裁定 32.4 的现场结果**：0928 两份 lock **未被覆写**（sha 与 mtime 都是 0928 原值，G1 PASS），
A 已把 `LOCK_OUT` 覆写到 `runs/infra/a_lerobot_env_rebuild_20260929/`（G2 PASS，非默认值）。
新旧 lock 的**全部差异只有 3 处**（G2 逐包枚举，**解释义务在 A、须报 D**；B 只保证差异不被吞掉）：

| 文件 | 包 | 0928 | A 的 0929 重建 | B 的只读初判（**不是**裁定，解释权在 A） |
|---|---|---|---|---|
| `requirements.lock.txt` | `ImageIO` | 2.37.4 | **2.38.0** | 非 pin 的传递依赖，随 index 当前最新浮动；不参与任何判据 |
| `requirements.lock.txt` | `uv` | 0.12.19 | **0.12.17** | **倒退** 2 个小版本。`uv` 是**装环境的工具**、不是运行时依赖，但它进了 lock ⇒ 「用什么工具装的」这个事实变了，属可复现性相关，值得 A 说明是不是 installer 里 `uv` 未钉版本导致 |
| `requirements.eval.lock.txt` | `ImageIO` | 2.37.4 | **2.38.0** | 同上 |

⇒ 3 处都**不涉及** `lerobot` / `torch` / `numpy` / `robosuite` / `mujoco` 等承载 48 臂结论的包，
但**在 A 逐条解释并报 D 之前，A 不得声称任何跨断点复现**（裁定 32.4 / 裁定 29.4）。

### 7.4 B 的验收实测（裁定 32.1 指派给 B 的那一半）：A 的重建**逐项符合 §2 权威 pin**

| venv | 实测（`importlib.metadata`） | 与 §2 pin |
|---|---|---|
| `lerobot_act` | `lerobot 0.4.4`、`torch 2.6.0`、`torchvision 0.21.0`、`numpy 2.2.6`、`gymnasium 1.3.0`；`mujoco`/`robosuite`/`numba` **MISSING** | **全部符合**，含「训练环境不装 robosuite、保持干净」这条**故意**的缺失（§2 末行） |
| `lerobot_eval` | `lerobot 0.4.4`、`torch 2.6.0`、`torchvision 0.21.0`、`numpy 2.4.6`、`gymnasium 1.2.3`、`mujoco 3.9.0`、`robosuite 1.5.2`、`numba 0.67.0` | **全部符合** |
| 两个 venv 的 `pyvenv.cfg` | `include-system-site-packages = false`、`home = /opt/conda/bin`、`version = 3.11.9` | 符合 §2「venv **不带** `--system-site-packages`」 |
| A 的 installer 出口 | `install.log` 14:11:23 `[7/7] 完成`，`EVAL_ENV numpy=2.4.6 torch=2.6.0+cu124 lerobot=0.4.4 gymnasium=1.2.3 mujoco=3.9.0 robosuite=1.5.2 cuda=True` | 门槛验证由 installer 内置并已跑过 |

⇒ **B 的验收结论：A 的重建合格，`lerobot==0.4.4` 语义值已验（不是只验 importable）。**
剩下的是 **C 的探针（P0-3）** 与 **D 的验收**（GPU 不再全空 / env manifest 断点条目 / 0928 lock 未被覆写
—— 最后这条 B 的 G1 已经给出机器判据，D 可直接引用 `runs/infra/b_env_provenance/guard.json`）。
**A 线是否解封由 D 裁**，B 不代裁。

### 7.5 更正指针（原文按 append-only 一字未改）

- **§1 第 1 行「`/root/venvs/` 下只剩 `rlrobot`」已过期**：14:15 起 `/root/venvs/lerobot_act`
  与 `/root/venvs/lerobot_eval` 是**符号链接**，指向
  `/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist/envs/{lerobot_act,lerobot_eval}`
  （NFS，持久）。⇒ **§2 表与 §3 门槛命令里的 `/root/venvs/...` 路径仍然可用**（走软链），
  但「实体在 NFS」这件事必须知道：换容器后要先跑 `codex-persist bootstrap` 再重建这两个软链，
  否则路径断。**§1「两个 venv 都被检修抹掉了」的现状描述自此作废。**
- **§1 末行「`rlrobot` 侧已由 C 重建」需补一句**：14:24 起 NFS 上另有一份**自足**持久
  `rlrobot`（`.codex-persist/envs/rlrobot`，`--system-site-packages=false`）。
  **当前在用的仍是 `/root/venvs/rlrobot`**（真实目录、带 `--system-site-packages`），
  B 的全部自检也跑在它上面；两者**并存不冲突**，切换属 A/infra 的决定，B 不代做。
- **§2「base 解释器…venv 不带 `--system-site-packages`」这一行只对 lerobot 两个 venv 成立**；
  `rlrobot` 历史上是带的（`numpy` 靠 venv 的 2.4.6 遮蔽 base 的 1.26.4）。裁定 32.3 前提 1
  的 (甲) 就是把 `rlrobot` 也改成不带 —— 现已建成（§7.3）。

### 7.6 B 自查出的一处**假红**（本节的方法学产出，与 DR-011 的三值桶同型）

G3 的 freeze 对账第一版报了「freeze 产物里缺 8 个 pin：`imageio`/`jinja2`/`pip`/`pygments`/
`pyyaml`/`setuptools`/`typing-extensions`/`werkzeug`」，把一次**完全合格**的自足 venv 判成 RED。
两个根因，都是 B 的工具错、不是环境错：

1. **没做 PEP 503 名字归一化**：`pip freeze` 输出**发行名原样**（`ImageIO`、`Jinja2`、`PyYAML`、
   `typing_extensions`、`Werkzeug`、`Pygments`），而 lock 里写的是小写/连字符形式 ⇒ 6 个包被当成缺失。
   修法：比对前一律 `re.sub(r"[-_.]+","-",name).lower()`（`norm_name()`）。
2. **`pip freeze` 默认不输出 `pip` / `setuptools`**（要 `--all`）⇒ 这两个 pin 在 freeze 对账里
   属**不可比**，不是缺失。修法：按护栏① 的三值纪律单列 `not_comparable_freeze_excludes`
   （**可见、但不报警**），其真值由 G4 的解释器探针侧验。

**为什么这条值得单独写一节**：假红和恒绿一样坏 —— 它让人学会忽略红灯（裁定 27.4 / 29.3 / 31.3 抓的都是这个）。
所以修完**必须证明没有把判据修成恒绿**：`--selftest` 里加了 **M8（反向变异，期望 NOT_RED）**
与 **M9（freeze 里 torch 漂移，期望 RED）** 一对，两条同时过才说明「归一化生效」且「对账仍有牙」。

### 7.7 两条**给 C 的探针补强**（裁定 31.2 第 3 条的延伸，B 实测出来的坑）

1. **`importlib.metadata.version("torch")` 分辨不出 CUDA 构建。** 实测：
   `lerobot_act` / `lerobot_eval` 的 metadata 报 **`2.6.0`**（无 local tag），而
   `torch.__version__` = **`2.6.0+cu124`**、`torch.version.cuda` = **`12.4`**；
   同一个解释器口径下，base 的 conda torch metadata 报 **`2.4.1+cu124`**（带 tag）。
   ⇒ 只断言 `metadata.version("torch") == "2.6.0"` 的探针，**对 cu121 构建也会通过**
   （这就是 裁定 31.2 说的「可导入是恒真判据」再深一层：**版本字符串也可能是恒真判据**）。
   **探针必须断言 `torch.version.cuda == "12.4"`**（能区分构建的那个语义值）。
2. **为什么 `+cu124` 有时要写、有时不用写**（B 实测两个 index）：
   `mirrors.aliyun.com/pypi/simple/torch/` 上 **没有** `2.4.1+cu124`（只有 PyPI 默认的 `2.4.1` = **cu121** 构建），
   `download.pytorch.org/whl/cu124/torch/` 上**有**（10 个 wheel）；而 `torch 2.6.0` 的 PyPI 默认构建
   **本身就是 cu124**（A 用 aliyun + `torch==2.6.0` 装出来实测 `torch.version.cuda=12.4` 即证）。
   ⇒ **`torch==2.4.1` 必须写 `+cu124` 并另给 cu124 轮子源；`torch==2.6.0` 不用写**。
   把这条搞反的两种失败模式都很难看：写多了装不上（源里没有该 local tag），
   写少了静默装到 cu121（版本字符串一样、CUDA 构建不同 = **最坏的一类静默漂移**）。

### 7.8 裁定 34.1 第 4 条落地：installer 钉 `imageio` 与 `uv`，取值口径**改判**（15:0x 追加）

A 报的 3 处 lock 差异（`ImageIO` 2.37.4→2.38.0 两份、`uv` 0.12.19→0.12.17 仅 act）已由 **裁定 34.1 放行**
（豁免**按包按链路**授），根因（installer 未钉 `imageio` 本体与 `uv`）**归 B 修**。已修：

> **裁定 37.3 的边界（引用 裁定 34.1 必须带这一句）**：豁免只覆盖**本仓链路**——
> C 用「每模块一个子进程 + 回显 `sys.modules` 里 `imageio`/`uv` 前缀键」实测（覆盖传递依赖），
> 本仓 ACT / 48 臂链路的 **8 个脚本全部 `hit=[]`**（A 静态 grep / C 运行时 / D 复核 **三方一致**）。
> **但上游 `lerobot.scripts.lerobot_train` 的 import 闭包里确有 imageio（18 个子模块）⇒
> 凡用上游 `lerobot_train` 实跑的训练/评测不在豁免内**：要么另证不材料，要么重新报 D；
> **今后真跑须回显 imageio 生效版本**。事实源 = C 的
> `c_ruling_34_1_import_surface_20260929.json`；工具 = `scripts/c_env_manifest.py --measure-import-surface`
> （A/B 可只读调用，产物写自己的目录）。**方法学一般化（裁定 37.3）**：
> 「某包不在某链路的 import 面上」这类主张**今后必须给运行时证据**，静态 grep 扫不到传递依赖。

| 变量 | 现值 | 事实源（实测，不是推测） |
|---|---|---|
| `IMAGEIO` | **`2.38.0`** | A 的 0929 重建两份 lock：`runs/infra/a_lerobot_env_rebuild_20260929/requirements.lock.txt:35`、`requirements.eval.lock.txt:38` 都是 `ImageIO==2.38.0`；B 实测 aliyun `pypi/simple/imageio/` 上 `2.38.0` **在**（wheel + sdist 各 1）；lerobot 0.4.4 声明 `imageio[ffmpeg]>=2.34.0,<3.0.0` ⇒ 合规 |
| `UV` | **`0.12.17`** | A 的 0929 重建 `requirements.lock.txt:102` = `uv==0.12.17`（仅 act 侧有）；B 实测 aliyun 的 uv 简单索引 316 个版本里 `0.12.17` **在**、`0.12.18 / 0.12.19 / 0.12.20` **都不在** |

**取值口径 = 「实际装成并跑通门槛验证」的那个值**（裁定 32.2「lock 是事实源、范围 pin 是意图」同型），
**不是**回退到 0928 的值 —— 回退等于按意图改事实，而且要重装只读 venv（裁定 34.1 第 3 条已否决重装）。
> B 在 14:1x 的第一版把 `IMAGEIO` 钉成了 0928 的 `2.37.4`（当时的理由是「要复现的是 0928」）。
> **裁定 34.1 改判了这个口径，本节按裁定更正，原判断作废。**

**根因纪律（写进 installer 注释了）**：**镜像内容会动 ⇒ 未钉版本 = 每次重建都漂移**。
`uv` 虽是安装期工具（A 实测全仓无 `import uv`），但它**进了 lock** ⇒「用什么工具装的」这个事实也属可复现性，
照样钉，不按「工具不重要」豁免。`uv==0.12.19` 在当前权威 index 上**不可复现**一事已报并由裁定 34.1 结案；
要装别的版本就显式 `UV=<ver>` 覆写并自备一个可达且有该版本的 index。

**验证口径**：按裁定 34.1 第 3 条**不需要重装**；`bash -n` 通过；下次重建由
`scripts/b_env_provenance_guard.py` 的 **G2 逐包枚举**确认「差异 0 处」
（**注意 G2 对空比对会 WARN**，那条 WARN 是防误读、不是失败）。

### 7.9 G5 的 numpy 期望值**按 venv 分别取**（§2 的表本来是对的，是闸的代码错了；15:4x 追加）

`scripts/b_env_provenance_guard.py` 的 G5 原先把「生效 numpy == **2.4.6**」写死成单值常量，
于是拿 `--venv /root/venvs/lerobot_act` 跑就报 RED「生效 numpy==2.2.6（期望 2.4.6）」。
**那是假红，不是环境缺陷**，而且它与本文档 **§2 的权威 pin 表自相矛盾** —— §2 早就写明
训练 venv 是 **numpy 2.2.6**、评测 venv 才是 **numpy 2.4.6**（installer 的评测环境段带 `--override numpy==2.4.6`）。
0928 基线 lock（act `:49` = `numpy==2.2.6`、eval `:57` = `numpy==2.4.6`）与 A 的 0929 重建两份 lock 都是这个形状。

⇒ **教训**：一个「目标可指、期望值不可指」的闸就是假红发生器。修法不是放宽判据，而是把期望值接到事实源上：

| venv | G5 期望值 | 来源 |
|---|---|---|
| `lerobot_act` | **2.2.6** | 推导自 `runs/infra/lerobot_act_env_20260928/requirements.lock.txt` 的 numpy pin |
| `lerobot_eval` | **2.4.6** | 推导自 `runs/infra/lerobot_act_env_20260928/requirements.eval.lock.txt` 的 numpy pin |
| `rlrobot` / 其它 | **2.4.6** | 项目口径常量（不在按-lock-推导表里 ⇒ 用门禁 venv 口径） |

优先级：`--expect-numpy` 显式指定 > 按 venv 名从对应 0928 lock **推导** > 项目口径常量；
**推导失败必须在 `expect_source` 里响亮写明**，不静默退回常量假装通过。
并已把此起假红**钉成回归牙**：`--selftest` 从 10 条加到 **12 条**，新增 **M10（反向，期望 NOT_RED）**
与 **M11（期望 RED，同一个 act venv 但生效值退回 base 的 `1.26.4`）** ⇒ 证明「按 venv 推导」**不等于**放宽判据。
实测三 venv 现场各 **PASS 5 / WARN 0 / RED 0**，`--selftest` **12/12**。

> **给 A / C 的读法**：引用「生效 numpy」时必须**点名是哪个 venv**。
> 「numpy 2.4.6」只对 `lerobot_eval` 与 `rlrobot` 成立；`lerobot_act` 是 **2.2.6**，那是**正确的**，
> 不是漂移。把两者混着说会造出下一起假红。
