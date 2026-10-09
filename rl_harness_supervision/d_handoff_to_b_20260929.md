# D → B 执行单（2026-09-29 14:5x）：环境迁移后的**门禁不变性证明** + 4 条 P0 收口 + v1.6/双阈值排期

交出方：智能体 D（监管/口径裁定线）。接收人：智能体 B（门禁 / 可复现性 / pin 与登记线）。抄送：A、C。
依据：用户指令「持久环境的问题直接修复」+「其它验证项交给其它智能体」；
`rl_harness_supervision/supervisor_memo_20260929.md` **增补十 §30–§35（裁定 33）** 与
**增补十一 §36–§39（裁定 34）**；`work/decisions/decisions_20260929.md` **DR-D32 / DR-D33**。

**先说三件已经发生的事（B 的文档需要追认，不是纠错，是时序）**：
1. **`/root/venvs/rlrobot` 已在 14:35 切成符号链接** → `.codex-persist/envs/rlrobot`
   （自足 clean venv，14:24 由 D 按用户直接指令建成）。C 重建的那份 overlay venv 已 `mv` 到
   `recycle_bin/rlrobot_overlay_20260929_143331`（**回滚 = mv 回来 + 重指软链**）。
   ⇒ B 的 pin 文档 **§7.5 第 2 条**（14:38 写「当前在用的仍是真实目录…切换属 A/infra 的决定，B 不代做」）
   **在写下时已过期 3 分钟**；按 append-only **原文不改，挂更正指针到 memo 增补十一 §37**。
   **B 的判断本身没错**（不代做 infra 决定是对的），只是那件事被用户直接指派给了 D。
2. **裁定 32.3 前提 1 的 (甲)/(乙) 抉择已裁**：选 **(甲) 自足**，且**已建成**。
   B 在 §7.3 里写的「(甲) 已建成并由 B 验收通过」**与 D 的裁定一致**，本节予以确认。
3. **A 报的 3 处 lock 差异已裁（裁定 34.1）**：**放行**，但豁免是**按包按链路**授的；
   根因（installer 未钉 `imageio` 本体与 `uv`）**归 B 修**，见本单 §4。

**D 对 B 本轮产出的验收（先给结论，再派活）**：
`scripts/b_env_provenance_guard.py` 的 **G1–G5 + `--selftest` 10/10** ⇒ **D 验收通过**。
两点特别认可：① **M8 是反向变异**（freeze 用发行名原样 `ImageIO`/`Jinja2`/`typing_extensions`、
且不含 `pip`/`setuptools` ⇒ **不得**误报缺失）——D 在增补十 §32.2 独立撞到同一处假红，**B 先一步做成了牙**；
② **G2 对「差异 0 处」会 WARN**（防空比对被读成通过），与裁定 27.1「恒假的闸等于没有闸」同型。
D 用 B 的闸在**切换后的软链**上复跑：`PASS 5 / WARN 0 / RED 0，exit 0`
（产物 `runs/infra/d_persistent_env_20260929/guard_after_symlink_switch.json`，**未覆写 B 的 `guard.json`**）。

---

## 0. 现状（D 只读实测，14:2x–14:5x）

- **解释器**：`/root/venvs/rlrobot` → `.codex-persist/envs/rlrobot`（软链，14:35）；
  `include-system-site-packages = false`、`home = /opt/conda/bin`、`version = 3.11.9`；**6.4 GB / 82 pin**。
  `/root/venvs/lerobot_act`、`/root/venvs/lerobot_eval` 同样是软链（A 14:15 建）。
  三条都已登记 `.codex-persist/envs/symlinks.json` ⇒ **下个容器 `bootstrap` 自动重放**（仓里 73 处硬编码路径不用改）。
- **门禁**：`GATE_BUILD` 仍是 **`v1.5 / f19f61341cbe`**（D 用 C 的 manifest 与 B 的闸各测一次，一致）；
  权威表仍是 12:21 那份（`25/22/1`）。
- **D 已做的基础验证（到此为止，其余归 B）**：`venvcheck` **35 PASS / 0 FAIL**、`env_check.py` **rc=0**
  （渲染平均像素 **108.5** 与阶段 0 同值、robosuite **19 envs**、cuda True A800）、
  `b_selfcheck_reproducibility.py --repeats 2` **rc=0 / 12 项全过**、
  `pip freeze --local` 与 82 pin lock 规范化后 **80/80 相同**（只差 `pip`/`setuptools`，freeze 默认不列自身）、
  经软链的 `smoke_random_policy.py --task Lift --episodes 1` 跑通并出视频。
  **全部命令与日志**：`runs/infra/d_persistent_env_20260929/verification.json`。
- **D 没做的（就是本单要 B 做的）**：门禁/回归那半边、`setup_env.sh` 的事前护栏、persistent lock 的身份登记、
  installer 的两处钉版本、A 报的锚点移位、git 代提交。

## 1. P0-1 门禁**不受环境迁移影响**的证明（B 的本职：可复现性线）

**为什么要这条**：环境是门禁产物的输入之一（解释器、numpy、torch 的实际生效值）。
D 已经证明「pin 逐格相同 + `env_check` 同值 + 可复现性 12/12」，但**门禁判据本身在新解释器上重跑过没有**，
只有 B 能答。**主张「环境换了但结论没变」必须给可核断言，不得只写「我验过了」**（增补十 §34 全员条）。

```bash
cd /workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot
V=/root/venvs/rlrobot/bin/python          # 现在是软链 → NFS 自足 venv
OUT=$PWD/runs/infra/b_env_migration_invariance_20260929
mkdir -p "$OUT"
$V -c "import sys,os;print('realpath=',os.path.realpath(sys.executable),'prefix=',sys.prefix)" | tee "$OUT/interpreter.txt"

# 1) B 的全套自检（json-out 一律指到本次目录，**不要覆盖 12:2x 的留档**）
MUJOCO_GL=egl OMP_NUM_THREADS=1 $V scripts/b_selfcheck_reproducibility.py   --repeats 2 --json-out "$OUT/reproducibility.json"
$V scripts/b_selfcheck_gate_regression.py  --json-out "$OUT/gate_regression.json"
$V scripts/b_selfcheck_gate_mutation.py    --json-out "$OUT/gate_mutation.json"
$V scripts/b_selfcheck_golden_values.py    --json     "$OUT/golden_values.json"
$V scripts/b_selfcheck_t17_mutation.py     --json-out "$OUT/t17_mutation.json"

# 2) 重判留档：期望「裁定变化 0 处」（退出码约定：有臂未过门禁就非零，别用 && 串接）
$V scripts/b_regate_all.py --allow-failing-arms --json-out "$OUT/regate.json"

# 3) 权威表重出到**新文件**，与 12:21 那份逐格 diff（构建必须仍是 f19f61341cbe）
$V scripts/b_official_arms_reclassification.py --json-out "$OUT/reclassification.json"
$V - "$OUT/reclassification.json" <<'PY'
import json,sys
old=json.load(open("runs/infra/b_official_arms/reclassification.json"))
new=json.load(open(sys.argv[1]))
keys=("gate_version","gate_build","summary")
for k in keys:
    same = old.get(k)==new.get(k)
    print(("SAME  " if same else "DIFF  ")+k, ("" if same else (old.get(k), new.get(k))))
sys.exit(0 if all(old.get(k)==new.get(k) for k in keys) else 2)
PY
```

**判定（D 会逐条独立复核）**：
- 五套自检的**通过数必须与 12:2x 那次逐项相同**（回归 157 断言 / 39 用例、变异 15/15、黄金值 47/47、
  T17 变异 6/6、可复现性 12/12）；少一项就是**环境迁移影响了判据**，必须查到底。
- `b_regate_all.py` 的**裁定变化 = 0 处**；权威表 `25/22/1`、`45/2/1`、`47/1`、
  计数层 `135/235/7/0/0`（raw 377 / 分母 960）**逐格不变**；`gate_build` 仍是 `f19f61341cbe`。
- 第 3 步那段 diff 脚本 **exit 0**（`gate_version` / `gate_build` / `summary` 三键全同）。
- **产物 mtime ≥ 脚本 mtime**（B 自己立的规矩）。
- **一句话结论要写成可核形式**：不是「门禁在新环境上也没问题」，而是
  「在 `realpath=<NFS 路径>`、`include-system-site-packages=false`、`numpy 2.4.6` 生效的解释器上，
  N 项自检与 M 份裁定记录逐格不变，构建 `f19f61341cbe`」。

## 2. P0-2 `scripts/setup_env.sh` 的 **freeze 覆写护栏**（D 现场发现的新风险；G1 是事后检测，这条要事前拒绝）

**风险（可核）**：`scripts/setup_env.sh:107-108` 是
```bash
  "$VENV/bin/pip" freeze --local
} > "$LOCK"          # LOCK=$REPO/requirements.lock.txt
```
现在**存在一个自足 venv**（82 个本地包）。若有人
`VENV=/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist/envs/rlrobot bash scripts/setup_env.sh`，
那份 **28 pin 的门禁产物会被就地覆写成 82 pin**（含 `torch`/`nvidia-*`），**provenance 头四行也会被改写**。
后果：① C 的 `c_env_manifest.py::_parse_lock` 从 28 变 82（`n_pins` 与 `lock.sha256_12` 全变）；
② B 的 G3「28 个项目 pin」基线失配；③ **`requirements.lock.txt` 是 0928 那批产物的溯源件之一**，
覆写它与裁定 32.4 保护 0928 lock 的理由**同型**（把可核事实换成新事实、旧的永久不可答）。
**G1 只能在事后报 RED（sha 变了），拦不住手滑** ⇒ 需要**事前**护栏。

**要求（B 的写入边界；三选一，D 倾向 (a)+(c)）**：
- **(a) 断言后拒绝**：freeze 前读 `$VENV/pyvenv.cfg` 的 `include-system-site-packages`；
  若为 `false`（自足 venv）⇒ **不写 `requirements.lock.txt`**，改写 `requirements.persistent.lock.txt`
  （或直接 `exit 1` 并打印「这份 lock 只能由带 `--system-site-packages` 的 venv 生成」）。
- **(b) 数量闸**：freeze 行数 **!= 28** ⇒ 拒绝覆写并要求 `--allow-lock-rewrite` 显式开关。
- **(c) 事前备份**：真要写之前，把旧 lock `cp` 到 `runs/infra/b_lock_history/requirements.lock.<sha12>.txt`
  （**禁 `rm`**；与 C 对 0928 两份 lock 做逐字节备份同型）。
- **牙**：护栏必须能被证明会红——给一个 `--selftest`（或一段可复跑的命令）演示
  「指向自足 venv 时拒绝、指向继承 venv 时放行」两个方向。**没有牙的护栏按裁定 27.1 视为没有护栏。**
- **顺带（同一处）**：`requirements-inherited.json` 的写入块在自足 venv 下会把 `jax` 记成 `NOT INSTALLED`
  ——**这是设计意图**（增补十 §31 末条：新 venv 里 `import jax`/`import tensorflow` 都 `ModuleNotFoundError`）。
  该文件的语义要按 **venv 类型分别解释**，B 在脚本注释里写明，并知会 C（C 的 `inherited_packages` 同步改）。

## 3. P0-3 登记 `requirements.persistent.lock.txt` 的身份 + 给它挂一条牙

- **身份（请写进 B 的登记册，建议 DR-013）**：
  | 项 | 值 |
  |---|---|
  | 文件 | `requirements.persistent.lock.txt`，**82 pin**，`sha256_12=69d61657f531` |
  | 生成器 | `scripts/d_build_persistent_lock.py`（依赖闭包 BFS；pin 漂移 ⇒ exit 3、闭包 GAP ⇒ exit 4） |
  | 生成报告 | `runs/infra/d_persistent_env_20260929/persistent_lock_report.json`（含 `required_by` / `known_conflicts` / `gaps`） |
  | **不是**什么 | **不是门禁产物**、不参与 `GATE_BUILD`、**不被** `c_env_manifest.py::_parse_lock` 读取 |
  | 与 28 pin lock 的关系 | 头部 `base_lock=requirements.lock.txt sha256_12=d1ea71b7b4e5`；前 28 行**逐行沿用**，后 54 行是闭包新增 |
  | 已知冲突 | `robosuite 1.5.2 -> mink==0.0.5`（实际装成 `1.2.0`，按裁定 32.2 口径**记录不改**） |
  | 排除项 | `jax` / `jaxlib`（仓里执行的代码 0 处 import；conda 的 jax/tf 是 09-24 ImportError 的污染源） |
  | 等价性补钉 | `h5py 3.14.0`（`robosuite/utils/camera_utils.py:12` 模块级 import，但不在 robosuite 的 `install_requires` 里） |
- **牙（建议挂在 L0 系列，与 L0-f/L0-g 并列）**：
  ① persistent lock 头部的 `base_lock sha256_12` == 仓里 `requirements.lock.txt` 的实测 sha256 前 12 位；
  ② persistent lock 的 pin **⊇** 28 pin lock，且交集部分**逐格相同**；
  ③ `torch`/`torchvision` 的 pin **必须带 `+cu124`**（与 G3 同型，防止有人重生成时解析成 CPU 版）。
  三条都要能红（改一位 sha、删一个 pin、去掉 `+cu124` 各演示一次）。

## 4. P0-4 installer 钉两个未钉版本（裁定 34.1 第 4 条；A 提请、B 的写入边界）

`scripts/install_lerobot_act_env.sh`：
- `:77` 只钉了 `imageio-ffmpeg==0.6.0`，**没钉 `imageio` 本体** ⇒ 解析器取镜像当时的最新（0928 是 2.37.4、0929 是 2.38.0）。
- `:36` 的 `pip install -q --index-url "$INDEX" uv` **未钉版本** ⇒ 0928 装到 0.12.19、0929 装到 **0.12.17**（方向是降）。

**要求**：钉 **`imageio==2.38.0`** 与 **`uv==0.12.17`**——即**「实际装成并跑通门槛验证」的那个值**
（与裁定 32.2「lock 是事实源、范围 pin 是意图」同型），**不要**回退到 0928 的 `2.37.4`
（回退等于按意图改事实，而且要重装只读 venv）。
并在脚本注释里写明根因：**镜像内容会动 ⇒ 未钉版本 = 每次重建都漂移**；
`uv` 虽是安装期工具，但它进了 lock ⇒「用什么工具装的」这个事实也属可复现性。
**改完的验证**：不需要重装（裁定 34.1 第 3 条已否决重装）；只需 `bash -n` + 把两处 pin 的**取值理由**写进注释，
并在下次重建时由 G2 的逐包枚举确认「差异 0 处」（**注意 G2 对空比对会 WARN**，那条 WARN 是防误读、不是失败）。

## 5. P0-5 A 报的 4 条锚点移位（`docs/a_handoff_to_b_anchor_shift_20260929.md` §1）

A 主动报而**不代改 B 的文件**，做法正确，D 认可。B 侧处理：
| B 的文件 | 旧锚 | 新锚 | 语义变了吗 |
|---|---|---|---|
| `scripts/b_gate_controlled_success.py:961` | `train_act_lift.py:44` | **`:156`** | 否 |
| `scripts/b_eval_act_lift_v1.py:227` | `train_act_lift.py:44` | **`:156`** | 否 |
| `scripts/b_probe_dz_identifiability.py:49` | `train_act_lift.py:14` | `:14`（行号未动） | **签名变了**（`goals=None` 缺省路径下层结构不变 ⇒ B 那句「逐层一致」仍成立，但**注记要补签名**） |
| `scripts/b_selfcheck_goal_conditioning_t17.py:452` | `run_act_lift_runtime_failure_audit.py:36,39` | **`:73` / `:76`** | **是**（两处硬编码已改成 `epoch`/`goal_id` 变量 ⇒ B 那条自检的**期望值要跟着改**，不是只改行号） |

**另记 A 顺带查出的一条既有事实**：前两行 B 引的是 `:44`，而 HEAD 里那一行**本来就在 `:36`**
⇒ **该锚点在 A 动手之前就已失效**。这与裁定 29.1 的 spec 轴问题同型（**引用锚只在 build 轴，
文本锚点易失效**）。**要求 B 借这次把这三处从「行号锚」改成「内容锚」**（例如按
`std = x.std(0) + 1e-6` 的**规范化文本**搜索并回显命中行号），否则下次 A 改文件又会移。
`docs/b_normalization_incident_20260928.md:128` 与 `docs/b_handoff_to_a_20260928.md:23` 引的 `:36`
是**当时正确**的历史记录 ⇒ 按 A 的建议**留档不追改**。

## 6. P0-6 git 代提交（DR-003 决定 8：git 写命令由 B 单写者执行）

本轮 **D 的仓内新增/改动**（`git status` 实测）：
- 新增：`scripts/d_build_persistent_lock.py`、`requirements.persistent.lock.txt`、
  `rl_harness_supervision/d_handoff_to_b_20260929.md`（本单）
- 改动：`rl_harness_supervision/supervisor_memo_20260929.md`（增补十 + 增补十一）、
  `rl_harness_supervision/d_handoff_to_a_20260929.md`（§9 附记）、
  `rl_harness_supervision/d_handoff_to_c_20260929.md`（附记）、
  `work/decisions/decisions_20260929.md`（DR-D32 / DR-D33）、`daily_report.md`（D 线小节）
- **仓外**（不在 git 里，B 不用管，但要知道它变了）：`.codex-persist/bin/codex-persist`、`.codex-persist/README.md`、
  `.codex-persist/envs/symlinks.json`、`.codex-persist/envs/rlrobot/`
- `runs/` 不纳管（`.gitignore`）⇒ D 的验证产物**只在盘上**，引用时给路径不给 diff

**提交前**：跑 `scripts/b_git_size_guard.py`（2 MB 闸）；`git add` **一律显式路径**，
**绝不 `git add tmp/`**（`tmp/` 未进 `.gitignore`）；A/C/D 的盘上快照按既有惯例代提交。

## 7. P1（排在 P0 之后；①②③ 互不阻塞）

1. **v1.6 一次做完**（B 自己在 §10.1 的排期，D 确认）：裁定 23 六项 + 裁定 31.5① 的 `condN` 改名 +
   裁定 31.5② 的「`terminal_kind` 缺失已被接受 + 理由」声明落 **B 的 `configs/`**。
   **落地即升 build ⇒ 主动通知 D 跑第三轮复签**（B② 已登记为义务，不要等 D 发现）。
   **附加要求（裁定 31.5①）**：改名后 D 的 `scripts/d_verify_exoneration_cosign.py` 会**同时验新旧 `condN` 键名不并存**
   （两套都读得到是更坏的形状）⇒ B 改完先自己 grep 一遍旧键名。
2. **`C5=0.04` 的双阈值并行重判：现在解锁了。** 裁定 29.5 第 3 条把它排在「等 A 迁表完成之后」，
   而迁表**已结案**（增补八 §21：54 份裁定记录、构建单一 `('v1.5','f19f61341cbe') × 54`、postcheck 17/17）。
   **纪律不变**：**不得原地改常数**；先写**预登记**（两套阈值定义 = `0.04` 与 `0.92 × 2 × size_z`、臂集、
   构建指纹、判定规则、**可红条件**、差集产物路径），再并行重判 48 臂、**报差集**，
   交 D 裁定后才进门禁。**这项是 B 的（判据线），不是 A 的。**
3. **动作侧饱和率是否进门禁 warn**：仍未裁。要推进就出一张**「饱和率 × 受控成功」的 48 臂实测表**
   （带构建指纹与臂集，按裁定 30 的表述纪律），D 才裁；**不出表就维持未裁**，不要写成「已同意进 warn」。

## 8. 验收（D 会逐条独立复核，**不看 B 的日志、只看产物**）

1. §1 的五套自检通过数与 12:2x **逐项相同**、`regate` 裁定变化 **0 处**、权威表三键全同、构建未动。
2. §2 的护栏**双向演示**（自足 venv 拒绝 / 继承 venv 放行），且 `requirements.lock.txt` 的
   `sha256_12` 仍是 **`d1ea71b7b4e5`**、28 pin 一行未动。
3. §3 的三条牙各红一次；登记条目里「不是什么」那一栏必须写明（防止它被当成门禁产物引用）。
4. §4 的两处 pin 与注释里的取值理由；`bash -n` 通过。
5. §5 的四处锚点已改，且**至少三处改成内容锚**；T17 那条自检的**期望值**跟着语义改（不是只改行号）。
6. §6 的提交里**不含** `tmp/`、不含 `runs/`；size guard 通过。
7. **表述纪律**：凡引用解释器，回显 `realpath` + venv 类型（clean / system-site）+ 是否经软链；
   凡引用分布层数字，带**构建指纹 + 臂集**（裁定 30）；凡引用 lock 差异豁免，**点名包与版本**（裁定 34.1 第 2 条）。

## 9. 卫生要求（与既有护栏一致）

不用 `rm`（回收站 `/workspace/mnt/sppro/yhzhang91/recycle_bin/`）；新目录 `mkdir -p`；
中间产物放**来源可识别**子目录（`runs/infra/b_*`）；**不覆写别人的产物**
（本轮 D 跑 B 的闸时把 `--json-out` 指到自己的目录，就是这个规矩）；
不执行 git 写命令之外的越界动作（git 由 B 单写者做）；
**NFS 上的 venv 建成后按只读对待**：不再往里 `pip install`（两个容器同时写会写坏它），
要改就整份重建到新目录再 `mv` 原子切换。

## 10. 附记（2026-09-29 15:1x，D）：**P0-1 验收通过** + 两处更正（一处是 D 的错）+ 剩余项台账

### 10.1 P0-1 **验收通过**（D 独立复核：只读你的 JSON 产物，不看日志、不看你的自述）

D 自己把六份产物重新解析了一遍（`runs/infra/b_env_migration_invariance_20260929/`），逐项与 12:4x 基线对齐：

| 项 | D 独立读到的值 | 基线（12:44–12:46） | 判 |
|---|---|---|---|
| `reproducibility.json` | `checks` 12 项、未过 0 | 12/12 | 同 |
| `gate_regression.json` | `ok=True` `n_asserts=157` `n_asserts_ok=157` `n_cases=39` | 157/157·39 | 同 |
| `gate_mutation.json` | `all_ok=True` `baseline_all_green=True` `n_mutations=15` `n_caught=15` | 15/15 | 同 |
| `golden_values.log` | 47/47、rc=0（**log-only**，见 10.2） | 47/47 | 同 |
| `t17_mutation.json` | `ok=True`、6 个 `status=pass`（含正对照 `M0`） | 6/6 | 同 |
| `regate.json` | `n_verdict_changes=0` `n_arms_matched_vs_old=16` `comparison_vacuous_sets=[]` `regression_ok=True` | 0 处 / 16 臂 / 非空洞 | 同 |
| `reclassification.json` | `n_artifacts=48` `citable 25/22/1` `ic_status 45/2/1` `measurement_valid 47/1` `pending_cosign_reverify.n=0` `git_commit=fe526d89…` | 25/22/1·47/1·pending 0 | 同 |
| 构建指纹 | 4 份产物全部 `gate_version=v1.5` / `gate_build=f19f61341cbe` / `gate_spec_sha256=c7fadabe8e3c…` | 冻结值 | 同 |

**特别认可两点**（都是「判据有牙」而不是「跑了一遍」）：
1. `invariance_verdict.json` 把 **`baseline_constants` 与 `red_conditions` 写进产物**
   ⇒ 结论**可核**、且**可红**（V6 明确把「空比对的 0 处」单列为红，V9 把「改脚本没重跑」单列为红）
   ——这正是 §1 与 §8.1 要的形式，**不是**「我看日志说通过了」。
2. `interpreter.txt` 回显 `realpath(prefix)=…/.codex-persist/envs/rlrobot` + `prefix_is_symlink=True` +
   `include-system-site-packages=false` + 生效 `numpy 2.4.6 / torch 2.4.1+cu124`
   ⇒ **「这份不变性是在迁移后的解释器上测的」这一前提本身被钉住了**（否则整份证明可以是旧环境跑的）。

**D 侧另行独立核到的冻结面（不采信你的「附带确认」，自己看 mtime/sha）**：
`runs/infra/lerobot_act_env_20260928/requirements.lock.txt` = **`68a38731c5b5…` / 09-28 14:56**、
`requirements.eval.lock.txt` = **`b6db07e2e31c…` / 09-28 15:24**（均未动）；
`attribution/arms_summary_v3.json` **11:08**（未动）；`runs/infra/lerobot_act_env_20260928/arms_summary.json` **12:33**
（**你的 15:05 重跑没有改写权威表**，这点很好）；`requirements.lock.txt`（门禁 28 pin）**12:13**（未动）；
被判的 `clip*.json` / `noclip.json` 仍是 09-28 16:4x–16:5x。⇒ **裁定 32.4 / 35.1 的冻结面无一处被破**。

### 10.2 更正一（**D 的错**）：`b_selfcheck_golden_values.py --json` 是**输入**不是输出

你查得对：`scripts/b_selfcheck_golden_values.py:35` 的 `--json` 默认值是
`docs/b_golden/async_td_golden_v1.json`、`:41` 立刻 `read_text()`，全脚本**不写任何 JSON 产物**。
D 在 §1 把它当输出路径用，照原命令跑必然 `FileNotFoundError` + `rc=1`——**那是 D 的命令错，不是环境迁移的红**。
你的处置（不带 `--json`、把 stdout 留成 `golden_values.log`、并在 `mtime_check` 里按 log-only 处理不算 STALE/MISSING）
**批准**，并已记为 D 第十一次自我纠错的第 ① 项（memo 增补十三）。
**衍生要求（P2，随 v1.6）**：这项**唯一**没有 JSON 产物的自检，请给它加一个 `--json-out`
（把 47 项逐条结果落盘），否则「D 只看产物」这条纪律对它就永远只能降级成看日志。

### 10.3 更正二：**P0-4 你已经做完了**，A 的提请就此闭合

D 读到 `scripts/install_lerobot_act_env.sh:52-53` 现为 `IMAGEIO="${IMAGEIO:-2.38.0}"` / `UV="${UV:-0.12.17}"`，
且 `:39-51` 写明了取值理由（**钉实际装成并跑通门槛验证的值、不回退**）与
「`uv 0.12.19` 在 aliyun 上已不可得」的实测 ⇒ **与 裁定 34.1 第 4 条逐字一致，P0-4 销账**。
A 在回执 §9.1 里提请「B 把 IMAGEIO 默认值从 2.37.4 改成 2.38.0」**已闭合**（D 已回给 A，见 A 附记 §9.6-6）。

### 10.4 一条**新观察**（P2，**不是违规、不是本轮新问题**）：同 build 重跑会**就地覆写不留旧字节**

`scripts/b_regate_all.py:109-125` 的 `snapshot_if_stale()` 只在**旧产物的 `gate_build` 与当前构建不同**时才
`copy2` 留档；`builds == {cur_build}` 时**直接 return None** ⇒ 同 build 重跑就地覆写。
本轮实测被覆写的三份：`runs/infra/b_normclip/gate_v12.json`、`runs/infra/b_normclip2/gate_all.json`、
`runs/infra/b_gate_sensitivity/report.json`（均 **15:05**，且目录里**没有**新的 `*.build_f19f61341cbe.json`）。
**当前无害**：被判产物冻结、构建冻结、且 `judge_set()` 是**先读旧值再覆写**（`:138-146`）⇒
`n_verdict_changes=0` 是**真比对**不是空洞。
**但留白是**：同 build 下若内容真的漂了，**没有旧字节可对**（只有当次算出的 diff 计数）。
**建议（P2，随 v1.6 一起，别为它单独动冻结面）**：同 build 覆写前也留 `*.pre_<UTC>.json`，
或把重跑产物**只写进本次 run 目录**、就地覆写改成需要显式 `--in-place`。
**性质界定**：这是**既有纪律的留白**（快照按 build 命名，本来就是为「跨构建留档」设计的），
**不违反** 裁定 32.4；D 现在**不要求**你改，只要求你**知道**并在 v1.6 里顺手补。

### 10.5 剩余项台账（D 15:1x 只读实测，不是推测）

| 项 | 状态 | D 实测依据 |
|---|---|---|
| **P0-1** 门禁不变性 | **✅ 完成并验收通过** | `invariance_verdict.json` 10/10 + D 独立复核（10.1） |
| **P0-4** installer 钉 imageio/uv | **✅ 完成** | `install_lerobot_act_env.sh:52-53`（10.3） |
| **P0-2** `setup_env.sh` freeze 覆写护栏 | **⬜ 未动** | `scripts/setup_env.sh` mtime **12:13**；`:101-108` 仍是 `{ …freeze… } > "$LOCK"`，`LOCK=:56` 指向门禁 28 pin 的 `requirements.lock.txt` ⇒ **在 clean venv 里照默认跑一次就会把 28 pin 覆写成 82 pin**（G1 只能事后抓） |
| **P0-3** persistent lock 身份登记 + 三条牙 | **⬜ 未动** | `scripts/b_env_provenance_guard.py` mtime **14:34**（未含新牙）；无新增 `b_*` 承载文件 |
| **P0-5** A 的 4 条锚点移位（含 1 条**语义**变更） | **⬜ 未动** | `b_selfcheck_goal_conditioning_t17.py` **11:58**、`b_gate_controlled_success.py` **11:07**（均早于 A 14:44 的移位单） |
| **P0-6** git 代提交 | **⬜ 未做** | `git status`：16 改 + 11 未跟踪（含 D 的三份 handoff、`requirements.persistent.lock.txt`、`scripts/a_env_provenance.py`、你的 `scripts/b_env_migration_invariance_check.py`）；HEAD 仍 `fe526d8` |
| **P1** v1.6 / `C5=0.04` 双阈值预登记 / 饱和率实测表 | **⬜ 排在 P0 之后** | — |

**顺序建议**：P0-2 → P0-3 →（P0-5 + P0-6 一起收尾，提交里带上 P0-2/3 的改动）。
**P0-6 提醒**：显式路径 add、**不要** `git add tmp/`（现在 `?? tmp/` 是脏的）、提交前先跑 `b_git_size_guard.py`
（`configs/b_git_size_whitelist.json` 14:45 你自己动过，别忘了它要不要一起进提交）。
**D 不代做 git**（DR-003 决定 8：git 写是 B 的单写者职责），也**不会**去改上述任何 B 侧文件。
