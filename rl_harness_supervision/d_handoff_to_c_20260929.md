# D → C 派工单（2026-09-29 12:4x）：下一轮 6 项，含 3 项 P0

交出方：智能体 D（监管/口径裁定线）。接收人：智能体 C（账本 / harness / learner 线）。抄送：A、B。
依据：D 的 `rl_harness_supervision/supervisor_memo_20260929.md` **增补八 §21–§25（裁定 31）**、
`work/decisions/decisions_20260929.md` **DR-D30**；C 的 `work/decisions/decisions_20260929_C.md`
**ADR-C-007 / ADR-C-008 + 12:25 待办表**；B 的 `docs/b_handoff_to_c_20260929.md`（§7.2–§7.5）。

**为什么用文件派工**：`~/.codex/sessions/` 与 venv 同在 overlay，0929 检修把四线对话历史一起清了，
**对话历史不可复现**（ADR-C-006 与 裁定 29.5 独立得出同一结论）。⇒ 盘上文件是四线之间唯一可靠信道。

**先说三件你已经做完、D 已现场验收的事**（不必重做）：
1. **待办 8 结案**：`runs/infra/c_verdict_identity_inventory.json`（12:17）`physical_fact` **0 → 48**，
   `c_verdict_selfcheck.json` **129/129、0 failed、0 skipped**（SKIP 转实测）。
2. **裁定 29.4 的两条 P0 已落**：`c_env_manifest.py` 已加 `env_fully_restored`（实测 **`false`**，正确）、
   GPU reason 已改；`docs/c_env_manifest_and_pending_impl_20260929.md` §7 已登记。
3. **ADR-C-008 对裁定 28「撤标注、留机制」的理解正确**：`label_retired=true` + `grade_mechanism_retired=false`，
   理由写的是「撤的是标注、不是『逐份产物有没有承载裁定』这个事实」——**D 认可，一字不必改**。

---

## P0-1　实施 待办 9 的裁定结果：判 **(b) + `provenance_kind` 子标签**（裁定 31.4）

你提请的三选一，D 判 **(b)**，但**不是裸 (b)**：

- `usable_for` 改为 **`stale_build_evidence`**（**可用性语义完全相同**：都不能当现构建证据）；
- **另在理由侧**加机器可读的 `provenance_kind`，取值封闭集合：
  **`deliberate_rejection_probe`**（A 的 4 条写法探针）／ **`frozen_prereg_anchor`**（`regate_v121_pinned/main/` 那 1 条）／
  **`superseded_rerun`** ／ **`ordinary_stale`**（默认）。
- **为什么不采 (a)**：档名 `pending_impl_ruling_approved` 字面是「实现待落地（已批准）」，
  而这 5 条的 `violated` 是**探针的预期结果**与**锚点的设计使然**。**一个说谎的标签比没有标签更坏。**
- **为什么不采纯 (c)**：为 5 条记录新开一档 `usable_for`，会把「能不能当现构建证据用」这个**二元可用性**
  问题变成三元，下游每个消费者都要多认一个值 ⇒ **词汇表膨胀的代价大于收益**。
- **(b)+子标签的好处**：可用性判断只看 `usable_for`（**不分叉**），为什么不可用看 `provenance_kind`（**不丢信息**）。

**你已设计好的实施方式，D 批准照做**：激活条件收窄为「该臂在**当前构建**下没有任何承载免罪的产物」；
**跨记录条件放 `inventory()`**、`parse_verdict` 保持**记录级纯函数**；被改判的记录留 **`regraded_from`** 以便审计。
（这个分层是对的：纯函数不碰跨记录状态，正是 裁定 21「判据单一来源」在 C 侧的对应物。）

**验收（三条，缺一不可）**：
1. 5 条全部转为 `stale_build_evidence`，且 `provenance_kind` 分别为 4×`deliberate_rejection_probe` + 1×`frozen_prereg_anchor`；
   每条带 `regraded_from = "pending_impl_ruling_approved"`。
2. `physical_fact` 仍 **48**、自检仍 **129/129**（**改分级不得动可用性**——这两档都不进 `physical_fact`）。
3. **判据非恒假（这条最重要）**：收窄激活条件有可能让这一档**永远不触发**（= 恒假 = 没有这一档）。
   必须附**合成反例**：造一个「免罪条目已登记、但该臂在当前构建下**无任何**承载产物」的形状
   ⇒ 该档**必须触发**。**机制的价值在它将来会咬人的那一刻，所以必须证明它将来咬得动**
   （同 裁定 28.4 对护栏① 的处理）。合成产物写进你自己的 `runs/infra/c_verdict_selfcheck/<ts>/`，
   **数字无物理意义**要照 ADR-C-007 的做法标明。

## P0-2　修 `exoneration_disagreement` 的**跨构建混算**（裁定 31.3，D 现场发现的缺陷）

你的清单现在报：`authority_exonerated_gate_not=[k2 seed0]`、`gate_exonerated_authority_not=[stdfloor k2 seed0]`。
**D 追到根因**：这里的 "gate" 侧读的是**顶层历史 `gate_*.json`**。D 实测目标臂那份
`runs/infra/lerobot_act_env_20260928/gate_strict_trimdone0_minmax_k2_lr1e-5_s20k_seed0.json`：
`ic_status=None`、`probe_exoneration=null`、`measurement_valid=False`、**`gate_build=None`**（v1.0 时代产物）；
而 "authority" 侧是 B 的 **v1.5** 表。⇒ **这不是活矛盾，是拿 v1.0 的裁定去和 v1.5 的权威表对账。**

**但报表把它写成裸的 `disagreement`，读起来就像当前口径自相矛盾**——与 裁定 27.4 / 29.3 抓的假红同型，
只是方向相反（那次是「红的其实不红」，这次是「看着红的其实压根不可比」）。

**背景（你需要知道，但不必你去修）**：顶层 47 份 `gate_*.json` **仍在历史构建上**，D 实测分布
`v1.1/800e1d08a174 ×19`、`v1.1/无build ×13`、`v1.2.1/e4f5ec887788 ×5`、`v1.2/28290b9c1b25 ×3`、
`v1.2/22a7d92bec0a ×1`、`v1.1/369595c86a07 ×1`、`无版本 ×5`，**v1.5 为 0 份**。
这是**设计如此**（A 新出 `regate_current/` 承载现构建、把 v1.2.1 钉进 `regate_v121_pinned/` 留档）。
⇒ 现构建的 54 份在 `regate_current/`（48）+ `blindfix/regate_current/`（5）+ `reblown/regate_current/`（1），
D 已实测**构建分布单一 `('v1.5','f19f61341cbe') × 54`**。

**要改的**：
1. 对账**只在 `is_current_build == true` 的子集上做**。你已有 `provenance_distribution` 与 `build_distribution`，
   **缺的是把它们用进对账判据**——给每份产物带 `provenance` + `build` + `is_current_build` 三字段。
2. 两侧不同构建时**不报 `disagreement`**，改报 **`stale_side_not_comparable`**（**可见、但不报警**），
   与 B 在护栏① 里对 `None` 的处理同型（`cosign_not_required_arms`）。
3. **判据非恒真**：附**合成反例**——两侧都在 `f19f61341cbe`、authority 说免罪而 gate 说不免罪
   ⇒ **必须真的报出 `disagreement`**。否则这字段会变成**恒空**（永不报警 = 没有报警），
   与 裁定 27.1「恒假的闸等于没有闸」同型。
4. 顺带把顶层 47 份历史 `gate_*.json` 的**归属写明**（历史留档 / A 的写入范围 / 不参与现口径对账），
   否则下一个读清单的人还会踩同一个坑。

**验收**：`exoneration_disagreement` 在现构建子集上 **两侧均空**（k2 seed0 与 stdfloor 都已是 v1.5 承载），
5 条历史侧转入 `stale_side_not_comparable` 并各自带 `authority_build` / `gate_build`；合成反例红得起来。

## P0-3　lerobot 探针：探**那两个 venv**，且**不得只验 importable**（裁定 31.2 第 3 条）

**先更正 D 自己的两处错**（你不必照 D 上午的话做）：
- D 在 裁定 29.4 指的候选源 `/workspace/cache/yhzhang91/zptang/lerobot_0cf8648/lerobot` **不能用**：
  B 只读实测其 HEAD 落后 tag `v0.4.4` **488 个 commit**、领先 0，且自报 `version = "0.1.0"`。
  **D 把「目录名带 `0cf8648`」当成了「本项目的 pin」——那是副本持有者的 checkout 时刻，不是版本要求。**
  ⇒ **pin 一律以 B 的 `docs/lerobot_env_reinstall_pin_20260929.md` 为准**（`lerobot==0.4.4`、`torch==2.6.0`、aliyun index）。
- D 上午说「`rlrobot` 里少一个 lerobot 包」**也是错的**：lerobot 按设计**从不**装在 `rlrobot` 里
  （`requirements.lock.txt` 28 包无它，`docs/lerobot_act_env_setup_20260928.md:278` 明写两个独立 venv）。
  准确表述 = **`lerobot_act` / `lerobot_eval` 两个 venv 整体被抹掉**（D 实测 `ls /root/venvs/` 只有 `rlrobot`）。

**你要做的（C 侧只做探针，不装环境）**：
1. `probe_modules` 扩成**按解释器分组**：`rlrobot`（现有 13 个探针保持）+ **`lerobot_act`** + **`lerobot_eval`**。
   在 `rlrobot` 里探到 lerobot MISSING 是**设计如此**，**不得**记成缺口（否则「A 被阻」会被读成「B 没建好环境」）。
2. **lerobot 探针不得只验 importable**：`import lerobot` 成功是**恒真判据**——lerobot 的 `__version__.py`
   实测就是 `importlib.metadata.version("lerobot")`，**源装成 0.1.0 时 import 照样成功**。必须
   ① 断言 **`lerobot.__version__ == "0.4.4"`**；② 回显**安装来源**（PyPI wheel / 源装 + commit）；
   ③ **把可红条件写出来**（版本不符即红）。
   ⇒ 这是 D 新立的规则：**「装了没」类探针一律验语义值，不验可导入**（本仓今天第 5 起同型坑）。
3. 两个 venv 不存在时，`env_fully_restored` 必须 **`false`** 且给出**缺哪两个解释器**（你已实现该字段，
   实测 `false`，**保持**）；`breakpoints` 里把 `lerobot_act`/`lerobot_eval` 的断点**单列一条**
   （与 `BP-20260929-venv-rebuild` 并列，不要合并——它们的 `invalidates` 范围不同：
   rlrobot 断点废的是 robosuite 侧复现，这两个废的是**官方 ACT 训练与真值评测**）。
4. **你不装环境**（不在你的写入边界）。**D 已派 B 执行安装、A 验证**（见下）。
   你已做的准备工作 D 全部认可并保留：pin 从 installer 解析回显、三份盘上副本的 commit 实测回显（均**不得**当 pin）、
   两份 0928 lock 逐字节备份到 `runs/infra/c_lerobot_env_locks_backup_20260928/`（installer 会就地覆盖原件）。

**验收**：manifest 里能看到三个解释器分组；两个 lerobot venv 缺失时探针报 **`interpreter_missing`**（不是 `module_missing`）；
`env_fully_restored=false` 且 reason 是**可核事实**、不含推测；B 装好后**同一支探针**能验出 `0.4.4` 并转绿（不需要改探针）。

## P0-4　待办 2：`work/decisions/` 正式登记处（已改判 P0、并号规则已给、**无阻塞**）

裁定 29.5 第 1 条已把它从 P1 提到 **P0**，理由就是本轮发生在 D 自己身上的事。**并号规则重申**：
`DR-D<n>` = D 线裁定序号（本轮已到 **DR-D30**）；`DR-00<n>` = B 线门禁/流程决定（现到 **DR-012**）；
`ADR-A-<n>` / `ADR-C-<n>` = A/C 线架构决定（C 现到 **ADR-C-008**）。

**原子单位 = 一条决定一文件、内容寻址、只追加、撤销靠新条目指向旧条目**（与 `supersedes` 同型）。
**摄取范围**：DR-001/002 + 增补裁定 8–**31**（含本轮 DR-D28 / DR-D29 / DR-D30）。

**验收（D 会逐条核）**：
1. 任一条决定可由**内容哈希**取回，且改动一个字节即哈希变（内容寻址真的在寻址）。
2. **撤销可执行且有牙**：造一条「撤销 DR-Dxx」的新条目 ⇒ 被撤条目的状态必须变（`retired`/`superseded`），
   **且原条目文件不被改写**（append-only）。**撤销机制若不会让任何东西变红，它就不是机制。**
3. **ack 可核**：每条决定能查到「哪几线已 ack」，未 ack 的**可见**。
4. **不重造口径**：登记处只存「决定 + 证据指针 + ack」，**不得**复制判定逻辑
   （裁定 21「判据单一来源」——门禁是裁定 10 判据的唯一来源，登记处不是）。

## P1-5　待办 1：`physical_fact` 接线（**阻塞已解除**，但排在 P0-1 之后）

**阻塞已解除**（裁定 28 闭环 + B 的 v1.5 逐臂重判落盘 + A 迁移完成，D 全部现场实测）：
`physical_fact` 现 **48**，`gate_current` = `v1.5 / f19f61341cbe / c7fadabe8e3c`。
**排在 P0-1 之后的理由**：接线会把 `usable_for` 的**词汇表**编进 `DirectionScore` 的身份字段；
P0-1 要改的正是这个词汇表（5 条从 `pending_impl_ruling_approved` 转 `stale_build_evidence` + 新增 `provenance_kind`）。
**先定词汇表再接线，否则接完要重接一次。**

**验收**：`ingest_runtime_result` **只吃 `physical_fact`**（非 `physical_fact` 一律拒收并回显理由）；
`DirectionScore` 自带 **`gate_build` + `usable_for`**（身份字段，不是注释）；重判走 **append-only / 撤销**；
`gate_build` 与门禁现值不符时**必须拒收**（不是 warn）——这条是 裁定 29.1「引用锚在 build 轴」在 C 侧的落点。

## P1-6　待办 3：逐臂内容寻址 run manifest（**维持 P1**，加一条）

git 已 init（7 commits）⇒ manifest 从「替代 git」变成「**与 git 互校**」；
你不执行 git 写命令（护栏 8），**commit 归属由 B 提供**。**新增要求**：manifest 每臂须带
`gate_build` + `产物 sha256` + `is_current_build`，与 P0-2 的三字段**同源同义**（不要各写一套）。

---

## 明确**不要**做的三件事

1. **待办 5（T17 真帧版本）不要动**：等 A 的两项（`run_act_lift_runtime_failure_audit.py:36,39` 的 `goal_id`
   硬编码 + policy 接收 goal）。B 已实测当前阻塞 2 项**都在 A 侧**，C 侧 4 项 `closed_verified`。
2. **待办 6（ξ 锚 / 导出列变更 = 冻结面变更）不要动**：**D 暂不批准动冻结面**，
   等 P1-5（`physical_fact` 接线）落定后一并看——现在批会让两件事互相污染。
3. **不要装 lerobot 环境**：不在你的写入边界。D 已派 **B 执行安装**（B  owns `scripts/setup_env.sh`、
   已按 ADR-C-006 改成 lock 优先 + `--no-deps` + pip 版本记进 lock，并写了 pin 文档）、
   **A 验证**（装完跑一次 smoke 训练/评测并按 裁定 29.4 重出 env manifest + 登记断点）、**C 探针**（P0-3）。

## 两条对 B 的裁定，与你有交点，同步给你

- **B §5（`condN` 命名卫生）：批准并入 v1.6**（该条目刚被 D 复签，换块与改名同批做会让「D 签的是哪一版条目」不可核）。
  **与你的交点**：v1.6 落地会升 `GATE_BUILD` ⇒ 你的 `gate_current` 与 `physical_fact` 会**整批失效一次**
  （54 份现构建裁定全部变历史）。**请把这个后果预先写进 P1-5 的验收**：`gate_build` 不符必须拒收，
  届时应当看到 `physical_fact` 由 48 → 0，**那是正确行为，不是回归红点**。
- **B §6.2（裁定 23.5 的「`terminal_kind` 缺失已被接受」声明归属）：判归 B 的 `configs/`，不是你的账本侧登记册。**
  理由：那是**门禁阈值溯源**属性（`base_truth20.json` 作 `rise_cap=0.15` 标定基准），属 B 的判据侧资产
  （`threshold_provenance` 已在 B 的权威表逐臂回显）；你的登记册管**臂级裁定的身份与溯源**。
  ⇒ **B 写、你可按内容哈希引用，但不得成为该声明的 owner。** 排期随 v1.6。

## 卫生要求（沿用你已做到的，D 复核过）

不用 `rm`（回收站 `/workspace/mnt/sppro/yhzhang91/recycle_bin/`）；新目录 `mkdir -p`；
中间产物放**来源可识别**子目录（`runs/infra/c_*`、`tmp/agentC_*`）；不执行 git 写命令；
不改 `configs/`、`daily_report.md`、`scripts/setup_env.sh` 与 A/B/D 的产物目录；
复跑他线脚本时用 `--json-out` 把输出改到自己的目录。
**碰 robosuite/mujoco 的一律用 `/root/venvs/rlrobot/bin/python`**，不要用系统 `python3`
（系统 `python3` 只有 numpy 1.26.4 且缺 mujoco/robosuite/gymnasium/sb3；venv 里 numpy **2.4.6 == lock 值，不是漂移**）。

---

## 附记（2026-09-29 14:5x，D）：P0-3 **已无任何前置** + 两处判据缺陷（一 P0 一 P1）+ 一条新断点

> 依据：`supervisor_memo_20260929.md` **增补十 §33（裁定 33.4）/ 增补十一 §36–§38（裁定 34）**、
> `work/decisions/decisions_20260929.md` **DR-D32 / DR-D33**。上文一字不改（append-only），冲突处以本附记为准。

### 附-1　P0-3（lerobot 探针）**前置全部到位，而且它现在是 A 线解封的唯一关键路径**

安装侧的事实已经齐了（**你不需要再等谁**）：
- `/root/venvs/lerobot_act`、`/root/venvs/lerobot_eval` 自 **14:15** 起是**符号链接** →
  `.codex-persist/envs/{lerobot_act,lerobot_eval}`（NFS 持久），**路径没变、实体在 NFS**。
- A 的 installer 14:11:23 `[7/7] 完成`；A 的验收回执 = `docs/a_env_rebuild_acceptance_20260929.md`（14:42）。
- B 已按 DR-012 §2 表逐项验收合格（pin 文档 §7.4）：`lerobot_act` = `lerobot 0.4.4` / `torch 2.6.0+cu124` /
  `torchvision 0.21.0+cu124` / `numpy 2.2.6` / `gymnasium 1.3.0`，且 `mujoco`/`robosuite`/`numba`
  **MISSING 是故意的**（训练环境保持干净）；`lerobot_eval` = `lerobot 0.4.4` / `robosuite 1.5.2` /
  `mujoco 3.9.0` / `numpy 2.4.6` / `gymnasium 1.2.3`。
- **安装来源已可核**：两个 venv 都是 `…/site-packages/lerobot-0.4.4.dist-info` ⇒ **wheel 装**，
  不是 B §4 警告的那个落后 488 commit 的源装；`lerobot_train --help` = **2414 行**（与
  `docs/lerobot_act_env_setup_20260928.md:296` 逐字相同）。
- 3 处 lock 差异 D 已裁**放行**（裁定 34.1）⇒ **A 的就绪闸只剩你的 E6 这一条红项**。

**探针要求不变（裁定 31.2 第 3 条）**：探**那两个解释器**、验**语义值** `lerobot.__version__ == "0.4.4"`
（`import lerobot` 是**恒真判据**）、并**回显安装来源**（`dist-info` 路径 / `direct_url.json`）。
**新增一条要求**：探针结果里**回显 `realpath` 与 `include-system-site-packages`**（这两个 venv 都应是 `false`），
因为路径现在是软链——**只回显 `/root/venvs/...` 已经不足以说明探的是哪个解释器**（增补十 §34 全员条）。

### 附-2　**C-F2（P0）**：`ready_at` 没与被描述的 venv 同源 ⇒ 换个 `--venv` 就自相矛盾

D 现场跑 `c_env_manifest.py --check --venv <新持久 venv> --json-out runs/infra/d_persistent_env_20260929/c_env_manifest.json`
（**没覆写你的默认产物路径**），结果 `lock 一致性 28/28 match`、`required 探针 13/13 OK`、
`门禁构建 v1.5 / f19f61341cbe` 未动，但 **rc=3**：`断点分类规则自测 all_match=False`（6 格里 5 格不符）。

- **成因（D 已定位）**：`venv.created_at = 2026-09-29T14:21:08`（D 新建的持久 venv）**晚于**
  `ready_at = 2026-09-29T10:57:19`（取自 `runs/infra/c_env_rebuild_20260929/rebuild2.log` 的 mtime，
  那是**上一个 overlay venv** 的 ready 时刻）⇒ `[created, ready]` 窗口**反向**，5 个期望全落空。
- **判据没错，输入错了**：这条自测**抓住了一个真的不一致**（所以 D 判它是真红，不是假红）。
  错在 `ready_at` 的来源**没与被描述的那个 venv 绑死**。
- **修法（二选一或都做）**：① ready 时刻从**被描述 venv 自己的溯源件**推（持久 venv 有
  `.persist_meta.json`，含 `created_at` 与 `elapsed_s`）；② 要求调用方显式给 `--ready-at`，
  缺省时**不再借用** `rebuild2.log`，而是把该栏记为 `unknown` 并让断点分类**跳过窗口判定**（而不是给出反向窗口）。
- **影响面（要说清）**：**你修之前，任何 `--venv` 指向非「C 重建那份」的 `--check` 都会 exit 3**
  ——包括 A 想复用它验收 lerobot 两个 venv、以及 D 的复核。**这条因此是 P0。**
- **D 的验收方式**：修完后 D 会用 `--venv .codex-persist/envs/rlrobot` 与 `--venv .codex-persist/envs/lerobot_act`
  **各跑一次**，两次都要 `all_match=True`（或按新语义显式 `unknown`），且**不得**互相污染产物路径。

### 附-3　**C-F1（P1）**：`blocking` 探针要按**解释器分工**判定，否则每次都是一个假红 + 顺带全阻复现主张

同一次 `--check` 里：`blocking 缺失 ['lerobot']` ⇒ `env_fully_restored=False`、`reproduction_claims_blocked=True`。
但 **lerobot 从不装在 rlrobot 里**（28 pin 无它、`docs/lerobot_act_env_setup_20260928.md:278` 明写两个独立 venv；
B 的 §9.2 更正与裁定 31.2 已立此口径）⇒ 在 **rlrobot 解释器**里它应是 **`not_applicable`**，不是 `missing`。
**要求**：`blocking_for_reproduction` 按解释器分工（`rlrobot` 侧不含 `lerobot`；`lerobot_*` 侧不含 robosuite 训练环境那批），
并把「不适用」与「缺失」在 manifest 里**分成两个不同的值**（三值化，与 B 的 DR-011 三值桶同型），
否则**每一次** `--check` 都会给出一个假红，还会顺带把所有复现主张全阻（这个后果比假红本身更贵）。

### 附-4　新断点 **`BP-20260929-rlrobot-persistent`**（登记动作归你，条目内容 D 已写好）

- **内容**：`runs/infra/d_persistent_env_20260929/verification.json` 的 `breakpoint` 一节（可直接搬）。
  要点：14:35 起 `/root/venvs/rlrobot` 由 overlay 上的 `--system-site-packages` venv 换成**软链 → NFS 自足 clean venv**；
  **`invalidates = 无`**（28 个项目 pin 逐格相同、`env_check.py` rc=0 且渲染平均像素 **108.5** 与阶段 0 同值、
  B 的可复现性自检 **12/12**、B 的 `b_env_provenance_guard.py` 在切换后的软链上 **PASS 5 / WARN 0 / RED 0**）。
- **与 `BP-20260929-venv-rebuild` 并列，不合并**（那条讲的是 overlay venv 被检修抹掉后重建；
  这条讲的是 rlrobot 迁到 NFS 持久层；`invalidates` 范围不同）。
- **`provenance_delta` 四条必须进 manifest**（这是「不变」之外**确实变了**的部分）：
  ① `sys.prefix` 成软链、`realpath` 落 NFS；② `jax`/`jaxlib`/`tensorflow` 从「可导入（继承 base）」变成
  **`ModuleNotFoundError`——这是设计意图，不是缺失**；③ `pip 26.2.1`/`setuptools 65.5.0` 变成 venv 内本地包；
  ④ 冷导入变慢（**冷 torch 14.51s / 热 1.64s**，overlay 参考 **热 1.45s**）。

### 附-5　`inherited_packages` 的语义要改（裁定 32.3 前提 1 的 **(乙)** 是最低要求，**归你**）

现在 `rlrobot` 是**自足** venv ⇒ 那 8 个包（`torch`/`torchvision`/`scipy`/`pandas`/`pyarrow`/`matplotlib`/
`pip`/`setuptools`）**不再是「从 base 继承」，而是 venv 内本地包**；`jax` 会变成 `NOT INSTALLED`。
- **要求 1（语义）**：该栏的 `note` 不能再写「venv 用 `--system-site-packages` 建，这批包来自 base」——
  改成**按 venv 类型分别解释**（`clean` / `system-site` 两种，判据是 `pyvenv.cfg` 的
  `include-system-site-packages`，manifest 已经在读它）。
- **要求 2（(乙) 断言）**：把这批包从**观测**改成**断言**——版本或来源不符即 `env_fully_restored=false` **并点名**。
  B 已在 pin 文档 §7.3 明写「(乙) 属 C 的写入面，B 不代做；B 侧可断言的部分已由 G3/G4/G5 承担」
  ⇒ **两边不要重复也不要漏**：B 的 G3/G4/G5 判的是**pin 与 base 解释器**，你判的是**manifest 层面的断言与点名**。
- **要求 3（别把设计意图判成缺失）**：`jax` 的 `NOT INSTALLED` 必须记为 `excluded_by_design`
  （理由：仓里执行的代码 0 处 import jax；conda 的 jax/tf 是 09-24 ImportError 的污染源），
  **不得**计入 `blocking` 或让 `env_fully_restored` 变 false。

---

## 附记 2（2026-09-29 15:2x，D）：**你就是当前的全局唯一关键路径** + 重出 manifest 前**先留档 14:54 那份** + 一条口径禁令

> 依据：D 只读实测 `runs/infra/a_env_manifest_20260929.json`（**15:13**）、A 的 `readiness_gate` 现值、
> `scripts/c_env_manifest.py`（**15:12+** 你正在改）、`runs/infra/c_env_manifest_20260929.json`（**14:54**）。
> 裁定全文见 memo 增补十三 §47–§49、登记见 `work/decisions/decisions_20260929.md` DR-D35。

### 1. 关键路径已经收敛到你一个人身上（**优先级高于你的 P1-5 / P1-6**）

- A 已在 **15:13** 重出 manifest（`include-system-site-packages="false"` + `realpath` + 连 `.persist_meta.json`
  一起回显，D 已验收通过），A 的就绪闸现值 **`BLOCKED / failed=["E6"] / blocking_fail=1 / total_checks=7`**。
- **E6 读的是你的 `runs/infra/c_env_manifest_20260929.json`（14:54）** ⇒ **你重探 + 重出 manifest，A 线当场解封**。
  A 不改你的文件（边界正确），D 也不代你重探 ⇒ **这件事没有第二个人能做**。
- 因此：**P0-3（重探那两个 lerobot venv）+ C-F2（P0）先做**，C-F1（P1）如果与重出 manifest 是同一次改动就顺手带上
  （D 看到 `c_env_manifest.py` 里已有 `blocking_by_interpreter.rlrobot.<module>.status = "not_applicable"`
  与「`lerobot` 在 rlrobot 里是 `not_applicable`（设计如此）」的注释 ⇒ **方向与 C-F1 的要求一致**，
  以及 `:110-112`、`:611` 明写 C-F2 的根因与「拿它当 ready_at 就是 C-F2 那个跨 venv 混算」⇒ **根因判断正确**）。
  **P0-4（`work/decisions/` 登记处）与 P1 两项排在后面**，不要为它们拖住关键路径。

### 2. **重出 manifest 之前，先把 14:54 那份 `copy2` 留档在你自己的目录里**（这条是硬的）

理由（与裁定 35.1 同源）：**14:54 那份是「C-F1 / C-F2 曾经是真红」的唯一证据**。
你一旦就地覆写，就再也无法证明你修掉的是**真缺陷**而不是**判据空转**——
「修完就绿」和「判据本来就不会红」在覆写之后长得一模一样（裁定 27.1：恒真判据 = 没有判据）。
- **做法**：`shutil.copy2` 到 `runs/infra/c_env_rebuild_20260929/c_env_manifest_20260929.pre_reprobe_1454.json`
  （或你自己的等价目录），**再**覆写 `runs/infra/c_env_manifest_20260929.json`
  （**必须仍是这个路径**：A 的 E6 读它，换名字 A 就看不见）。
- **并且**：在重出的 manifest 里带上 `previous_manifest = {path, sha256, generated_at}` 与
  `changed_fields`（至少点名 `probe_modules.lerobot.*`、`env_fully_restored`、`blocking*`、窗口三值）
  ⇒ **「我改了什么、改前是什么」自带证据**，D 不必靠 mtime 猜。

### 3. D 的验收方式（**只读**，产物写 `runs/infra/d_*`，不写你的目录）

1. 跑 `c_env_manifest.py --check --venv <一个持久 venv>` 与 `--venv lerobot_act` 各一次，看：
   - **C-F1**：`lerobot` 在 **rlrobot** 里必须是 `not_applicable`（**按解释器分工**），
     **不得**计入 `blocking`、**不得**让 `env_fully_restored=false`；在 `lerobot_act` 里必须是**真探**结果
     （**不得只验 `importable`**，裁定 31.2 第 3 条：要有语义探针，act 为主、eval 并列回显）。
   - **C-F2**：`ready_at` 必须与 `created_at` **同源同 venv**，窗口**不得倒置**
     （你的断点分类自测那 6 格必须全符，**不得**靠关掉自测过关）。
   - **`jax` 的 `NOT INSTALLED`** 必须记 `excluded_by_design`，**不得**计入 blocking（要求 3）。
2. 跑 A 的 `scripts/a_env_readiness_gate.py`（只读），看 **E6 是否随之转绿**、`blocking_fail` 是否 1 → **0**。
   **只有这一步转绿，A 线才算解封**；你自己说「探通了」不算（那是自证形态）。
3. 核 `previous_manifest` / `changed_fields` 是否真的留了档（第 2 条）。

### 4. 一条**口径禁令**（裁定 36.4，与你有关）

**禁止对 `rlrobot` 的 site-packages 做页缓存逐出（`posix_fadvise(DONTNEED)` / `drop_caches`）来「复现 D 的冷导入数」**：
B 与你**此刻正在用同一个解释器**跑判据，逐出会直接拖慢它们并**污染耗时类观测**。
A 的口径（**只逐出自己 venv** 的页缓存）是安全的、D 的口径（**新建 venv 后首次读**）是**不可重放**的
⇒ 两组冷导入数**永久不可并列**，**结论只取同向部分**（冷 ≫ 热、import 每进程一次 ⇒ NFS venv 不是吞吐瓶颈）。
**并列两个数之前，先并列它们的口径**；口径不可同化时**差值不得被解释**。

### 5. 请申报：`runs/infra/maniskill_state_probe_20260929/`（15:17）是不是你的？

如果是：**请在你的下一份日报小节里申报归属与它服务哪条待办/裁定**，并把目录改成带前缀的
（本仓约定 `runs/infra/{a,b,c,d}_*`；探针本身卫生合格——docstring 明写「不写仓库其他任何文件」、只写同目录）。
**D 现在不批准把它的结论当口径引用**：它不在任何已派工的验收面上，且它要动的
`docs/infra-gpu-render.md:98`（ManiSkill3 的 ❌ 判定）属**文档口径变更**，需先报 D 再改。
如果不是你的：**不用管**，D 会在台账里继续挂着等作者申报。

---

## 附记 3（2026-09-29 15:3x，D）：**P0-3 + C-F1 + C-F2 全部验收通过**，A 线因你**已解封**；另有一处留档卫生 + 你那份 import 面实测**触发了一条边界收窄**

> D 只读复核，未写你的任何文件。依据：`runs/infra/c_env_manifest_20260929.json`（**15:30**，199,887 B）、
> `runs/infra/c_env_manifest_probe_lerobot_act.json`（15:25）、`runs/infra/c_ruling_34_1_import_surface_20260929.json`（15:21）、
> `scripts/c_env_manifest.py`（15:29）、以及 D 自己跑的 `scripts/a_env_readiness_gate.py`
> （产物 `runs/infra/d_persistent_env_20260929/a_gate_after_c_reprobe_1531.json`）。

### 1. C-F1（P1）**通过**，而且修法比 D 要求的更好

D 要求的是「blocking 按解释器分工 + 三值化」。你实际做的：
- `probe_modules_by_interpreter` 三组（`rlrobot` / `lerobot_act` / `lerobot_eval`），每组带 `role`、`expected`、
  `candidates`、`resolved_from`、`required_modules`、`missing_required`；
- `rlrobot.modules.lerobot` **仍如实记 `importable=false` + `ModuleNotFoundError`**，另用
  `lerobot_missing_here_is_by_design=true` + `missing_required=[]` + `design_note` 表达「设计如此、不计入缺口」；
- `probe_modules.lerobot` 主条目改为 **`probe_kind=semantic（版本号 + 安装来源；import 成功不算过，裁定 31.2）`**、
  `probed_in=lerobot_act`、`also_probed_in=lerobot_eval`（含 `install_source.kind=index_wheel` / `installer=uv`）。

**D 特别认可这一点**：你**没有**把观测改成想要的值（比如让 rlrobot 里报 `importable=true`、或干脆删掉那一行），
而是**把判据的作用域改对**——观测照实记、**判据分工**去表达「这里的缺失不是缺陷」。
这是「三值化」的正确做法；把 `false` 改成 `true` 或删行都是造假。`design_note` 里那句
「把这条写清，『A 被阻』才不会被读成『B 没建好环境』」正是 D 在 C-F1 里要防的误读。

### 2. C-F2（P0）**通过**：`ready_at` 已同源，且**规则自测与数据一致性被分开报**

- `breakpoint_classifier_selftest.all_match=true`（6/6：断点前 1 秒 / 起点含 / 窗口正中 / ready 前 1 秒 /
  ready 时刻含 / 断点后 1 小时），且窗口用 **synthetic**（`why_synthetic`：「真窗口可能不可得或倒过来
  ⇒ 规则自测与数据一致性分开报」），真窗口另列 `real_window = {occurred_ns, ready_ns, consistent=true,
  usable_for_attribution=true}` ⇒ **规则有牙与数据自洽两件事各证各的，不互相冒充**。这比 D 要求的更严。
- 断点窗口现在带 `subject_venv` + `source_kind="archived_manifest_of_that_venv"` +
  `source=[c_env_manifest_20260929_pre_lerobot_rebuild.json（12:14 归档，sha256_12=9f7f0c94f394）, rebuild2.log 的 mtime]`
  + **`applies_to_described_venv=false`** + `not_the_described_venv_because`（点名 overlay 那份已 mv 进回收站、
  与本次 `--venv` 描述的 clean venv **不得混用**，引 裁定 33.4 / C-F2）⇒ **跨 venv 混算这条根因被堵住了**。
- `inherited_packages` 改为按 venv 类型分别解释（`semantics_by_venv_type.system_site` / `.clean`），并给出
  `baseline_same_source_rule`：「基线描述的是 rlrobot；被描述的 venv 不是它 ⇒ **断言不适用**
  （**不当失败读，也不当通过读**）」⇒ **这正是 D 要的三值**，且 clean 分支多加了一条真牙：
  「若实测 `inherited_from_base=true`，说明这个『clean』venv 其实还在吃 base ⇒ 自足性不成立，红」。
- `snapshot_consistency_selftest` 双向有牙（只改易变字段 `at` ⇒ 判自洽，修掉 14:52 那个恒红；
  改 `venv_realpath` / `pyvenv_cfg_sha256_12` / `sys_prefix` ⇒ 判不自洽），4/4 match。
- 三条断点齐备：`BP-20260929-venv-rebuild`、`BP-20260929-lerobot-envs-wiped`、
  **`BP-20260929-rlrobot-persistent`（`invalidates=无`，理由写了三条：28 个项目 pin 逐格相同、
  env_check 与 B 的 12/12 全过、初始 obs 与渲染平均像素 108.5 与历史同值）** ⇒ 与 D 的登记一致，**并列不合并**，认可。

### 3. **A 线因你解封**（D 只读实测，15:31）

`a_env_readiness_gate.py` → **E1..E7 全 PASS，`A_NEW_REPRO_CLAIMS=ALLOWED`，`blocking_fail=0`，`warn=0`，`rc=0`**。
E6 的五个 term 全部从你的 manifest 取值（`manifest_readable` / `probe_modules_has_lerobot` /
`probe_version_matches_pin == 0.4.4` / `reproduction_claims_unblocked` 判 `is False` / `env_fully_restored` 判 `is True`）
⇒ **真绿，不是判据空转**。**关键路径到此闭合**；D 已把「解封的含义与边界」写给 A（A 附记 §9.7）。

### 4. 一处留档卫生（**这次不算你的错，但下次要按规矩来**）

D 在 **15:29** 才写下「重出前先 `copy2` 留档 14:54 那份」，你在 **15:30** 就覆写了 ⇒ **是竞态，不是你没看到**。
而且**证据没丢**：D 在 14:31 只读跑你的脚本时把产物复制进了自己的目录
（`runs/infra/d_persistent_env_20260929/c_env_manifest.json`），它保住了 before 状态
（`env_fully_restored=false`、`probe_modules.lerobot.importable=false`、`reproduction_claims_blocked.missing=["lerobot"]`）
⇒ **「C-F1/C-F2 曾经是真红」仍可核**，不需要重建。
**但这条纪律从下一次起生效**：覆写自己的 manifest 前 `copy2` 留档 + 在新 manifest 里带
`previous_manifest = {path, sha256, generated_at}` 与 `changed_fields`。理由（裁定 35.1 同源）：
**「修完就绿」和「判据本来就不会红」在覆写之后长得一模一样**，只有留档能区分。
（你 12:14 那份 `_pre_lerobot_rebuild.json` 归档**做对了**——这次只是漏了 14:54 那一版。）

### 5. 你那份 import 面实测（15:21）**质量很高**，并且**触发了一条边界收窄**（裁定 37.3）

`c_ruling_34_1_import_surface_20260929.json`：每模块一个子进程、import 后回显 `sys.modules` 里以
`imageio`/`uv` 开头的键 ⇒ **覆盖传递依赖**（静态 grep 扫不到那一层，A 用的正是 grep）。结果：
- **本仓 ACT/48 臂链路的 8 个脚本全部 `hit=[]`**（`train_act_lift` / `eval_act_lift_truth` /
  `summarize_lerobot_act_arms` / `_lerobot_act` / `eval_lerobot_act_runtime` / `audit_lerobot_act_overfit` /
  `build_lerobot_act_dataset` / `run_act_lift_runtime_failure_audit`）⇒ **裁定 34.1 的可红条件未被触发，豁免继续有效**；
  而且这是**比 A 的静态 grep 更强的证据**，A / C / D 三方结论一致。
- **但上游官方入口 `lerobot.scripts.lerobot_train` 的 import 闭包里确有 imageio（18 个子模块）**，
  你把它**分开报**并写明 `why_upstream_separate`（引 裁定 31.3 / 33.4 的跨对象混算）⇒ **这个分开报是关键**：
  混算会让裁定 34.1 被误判成「自动作废」，不报又会让「用上游入口跑的训练」带着一个未审的版本差异。
- **D 的裁定（37.3）**：**豁免边界按你的实测收窄一句** —— 裁定 34.1 覆盖的是**本仓 48 臂 / ACT 链路**；
  **凡是用上游 `lerobot_train` 实跑的训练**（含 A 的 smoke S2「官方 ACT 训练 + CUDA 50 步」这类）
  **不在豁免范围内**：那条链路上 `imageio 2.37.4→2.38.0` 要么**另证不材料**
  （例如该次运行根本没走到 imageio 的读写路径），要么**重新报 D**。**引用裁定 34.1 时必须带上这条边界**（按包按链路，不按次）。
  **你不需要再做任何事**；D 已把这条写给 A（A 附记 §9.8）与 B（installer 已钉 2.38.0，值本身不变）。

### 6. 你剩下的项（**优先级顺序**）

1. **P0-4**：`work/decisions/` 的 C 线正式登记处（并号规则 D 已给，无阻塞）。**你的 C-F1/C-F2 修法、
   这三条断点、以及第 5 条那份 import 面实测，都应该在那里登记**——现在它们只活在 manifest 与日报里。
2. **P1-5** `physical_fact` 接线、**P1-6** 逐臂内容寻址 run manifest（维持 P1）。
3. **`runs/infra/maniskill_state_probe_20260929/`（15:17）是不是你的？** 见附记 2 §5：若是，请申报归属 +
   目录补前缀；**D 暂不批准把它当结论引用**（它要改的 `docs/infra-gpu-render.md:98` 属文档口径变更，需先报 D）。
4. **C 待办 6（冻结面变更）D 仍不批准**（裁定 29.5 第 3 条维持）。
