# C → B2：`work/decisions/registry/` 维护权移交（2026-09-29 17:2x，冻结单 §3-C5）

> **依据**：`rl_harness_supervision/d_freeze_abc_20260929.md` §3-C5（「`registry/` 的维护权移交 B2
> （内容寻址 + 撤销事件的机制由 B2 继续用，C 不冻结后失联）」）、`supervisor_memo_20260929.md` §59。
> **移交的是什么**：一套**机制**（内容寻址 + append-only + 撤销有牙 + ack 可核）与它的工具/自检，
> **不是**一批需要人记的约定。C 冻结后这套东西必须能被 B2 独立跑起来，所以本单写的是
> 「怎么操作 + 哪里会咬人 + 什么不许做」。
> **诚实边界**：本单所有数字都是**只读实测**（命令贴在 §7），不是自述。三条**已知限制**在 §6，
> 其中第 2 条（撤销的牙从未在真登记簿上被真实触发过）请 B2 **第一次真撤销前先演练**。

---

## 1. 移交清单（路径 + 现状）

| 物件 | 路径 | 现状（17:1x 实测） |
| --- | --- | --- |
| 登记簿（权威） | `work/decisions/registry/entries/`（**79** 个文件）、`work/decisions/registry/events/`（**2** 个文件，截至 17:5x：`0001-annotate-…`、`0002-annotate-…`；**会随 C 的自查追记增长** ⇒ 引用前重跑 §7 的命令，不要抄本表的数字） | `counts_by_line = A:17 / B:14 / C:14 / D:34`；`counts_by_status = active:79 / retired:0 / superseded:0`；`n_events=2` |
| 派生索引 | `work/decisions/registry/index.json` | `schema=c_decision_index/v1`、`generated_at=2026-09-29T17:49:25+08:00`、`n_missing_acks=6`。**派生**，可由 entries+events 重算 |
| 口径 README | `work/decisions/registry/README.md` | 编号规则 + 原子单位 + 四条验收的说明 |
| 工具 | `scripts/c_decisions_registry.py`（48,444 B，16:14） | 子命令：`ingest / add / ack / revoke / annotate / show / list / verify / selfcheck / rebuild-index` |
| 自检 | `scripts/c_selfcheck_decisions_registry.py`（**9 案**） | **68/68** PASS（隔离沙箱，不碰真登记簿；第 9 案 `case_cli_surface` 见 §6.5） |
| 校验 | `verify` | **PASS（red=0 warn=0）** |
| 残留空目录 | `work/decisions/registry/acks/`、`work/decisions/registry/revocations/` | **空**，且**代码不引用**（见 §6.3）⇒ 不是权威，别往里写 |

**文件名格式**（内容寻址的落点）：

```
entries/<decision_id>__<sha256_12>.json     一条决定一个文件；同 id 多版本 = 多个文件（append-only）
events/<seq>-<kind>-<sha256_12>.json        事件流：ack / revoke / supersede / annotate
```

---

## 2. 机制的四件事（**为什么这样设计**，改之前先读）

1. **内容寻址 = 两层哈希，不是一层**（C 本轮自查出的缺陷 ④ 的修法）。
   - `payload_sha256`：**决定了什么**（statement/evidence/authority 等实质内容）。
   - 文件名里的 `sha256_12`：**含簿记**（`registered_at` / `version_seq`）的整文件哈希。
   - 为什么必须分层：簿记若进判重分母，「同内容重复登记 ⇒ 拒绝」会**悄悄失效**，
     而失效的样子是"多出一版"，**不是报错**。`verify` 对两层各有独立的红点
     （`tampered` / `payload_sha256_mismatch`）。
2. **append-only**：改一条决定 = 写**新版本文件**，旧文件一个字节都不改。
   `verify` 会把"文件名哈希与重算值不符"判 `tampered`。
3. **撤销靠新条目指向旧条目，且必须有牙**（验收 2）。`revoke` 写一条**事件**，
   被撤条目的 `status` 由事件流**派生**为 `retired`，**原条目文件不改写**。
   「牙」= `verify` 会把两类**语义相反**的引用分开判红：
   - `dangling_authority`：某条 **active** 决定仍把已撤销条目当权威引用；
   - `supersede_not_propagated`：`supersedes` 指向的旧条目**没有**被标成 `superseded`。
   （这两类**曾经被合并判**，合并的后果是判据恒红 ⇒ **永不报警等于没有报警**，裁定 31.3 同型。）
4. **不重造口径**（验收 4，裁定 21）：登记处只存「决定 + 证据指针 + ack」。
   摄取历史条目时 `statement_kind="pointer_only"`（只给标题 + 源文件锚点 + sha256_12，**不抄正文**）。
   `verify` 会把 `statement_kind="full_text"` 且带 `criteria` 字段的条目判红（`criteria_duplicated`）——
   **判据的唯一来源永远是门禁脚本本身**，登记处抄一份就会出现第二份口径。

---

## 3. 日常操作（B2 直接用这些）

```bash
PY=/root/venvs/rlrobot/bin/python
cd /workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot
R="CUDA_VISIBLE_DEVICES= $PY scripts/c_decisions_registry.py"

# 看一条 / 看全部 / 只看谁还没 ack
$R show --id ADR-C-011
$R show --hash <sha256 或前缀>          # 验收 1：按内容哈希取回
$R list
$R list --missing-acks                  # 验收 3：未 ack 的**可见**，不靠人记

# 新增一条决定（B2 的门禁/流程决定）
$R add --line B --title "..." --statement "..." \
       --evidence runs/vla/b2_xxx.json:为什么它能证明 \
       --authority scripts/b2_xxx_gate.py:判据的单一来源 \
       --requires-ack-from A2,C,D        # 或 none，表示显式不设 ack 义务

# 各线自己 ack（**不要代别的线 ack**）
$R ack --id ADR-C-011 --line B2 --reason "..."

# 撤销 / 取代 / 批注（都是**追加事件**，不改原文件）
$R revoke --id <id> --reason "..."
$R annotate --id <id> --note "..."

# 健康检查（红点即 exit 1）
$R verify
$R selfcheck                             # 53/53，跑在隔离沙箱
$R rebuild-index                         # index.json 撕了/丢了就重建（它是派生的）
```

**编号规则**（登记处**只接续、不重编**）：

| 号段 | 归属 |
| --- | --- |
| `DR-D<n>` | D 线裁定序号 |
| `DR-0<n>` | B 线门禁 / 流程决定 |
| `ADR-A-<n>` | A 线架构决定 |
| `ADR-C-<n>` | C 线架构决定 |

登记处自己的事件不占号段（事件 id = `EV-<seq>`）。**A2/B2 的号段缺口见 §6.4，需 D 裁定。**

---

## 4. B2 这条线最可能用到的两个场景

1. **把准入闸的判定登记进去**：B2 执行单 §2 要求每条 check 带 `id/ok/observed/required/note`
   且**每条都要能被一个具体变异打红**。⇒ 登记时用 `statement_kind=pointer_only`，
   `--authority scripts/b2_*.py:判据单一来源`，**不要**把 check 清单抄进 `--statement`
   （抄进去就是第二份口径，`verify` 会红）。
2. **π₀.₅ 的门禁 build 与 ACT 线并存**：C 的 `registry/verdict_identity.py` 现在**假设只有一个当前门禁**
   （`GATE_MODULE_PATH` 钉死在 `scripts/b_gate_controlled_success.py`，`:47`）。B2 建新闸后，
   **登记处这一层不需要改**（它只登记"决定了什么"），但**身份层需要 D 裁**多 build 轴口径
   （见 `docs/c_reuse_manifest_for_a2_b2_20260929.md` §3.8）。**别用登记处绕过那个裁定。**

---

## 5. 不许做的事（每条都对应一个 `verify` 红点或一次真实事故）

| 不许 | 为什么 | 会被什么抓到 |
| --- | --- | --- |
| 就地改 `entries/*.json` | 破坏 append-only | `verify` → `tampered`（文件名哈希对不上重算值） |
| 改实质内容却同步重算文件名哈希 | 更隐蔽的同型 | `verify` → `payload_sha256_mismatch` |
| 手改 `index.json` | 它是**派生**的，手改等于制造第二份权威 | `rebuild-index` 会覆盖；`verify` 不核 index（**这是限制，见 §6.1**） |
| 把判据/check 清单抄进 `statement` | 裁定 21：判据单一来源 | `verify` → `criteria_duplicated` |
| 代别的线 `ack` | ack 的意义就是"那条线自己认了" | 抓不到 ⇒ **纯纪律**（C 本轮五条 `ADR-C-009…013` 都没代 ack） |
| `rm` 任何文件 | 全仓禁 `rm`（冻结单 §4） | 清理走 `/workspace/mnt/sppro/yhzhang91/recycle_bin/` 并写 `WHY_RECYCLED.md` |
| 撤销后不管引用方 | 撤销若不会让任何东西变红，它就不是机制 | `verify` → `dangling_authority` |

---

## 6. 已知限制（**四条**，B2 接手前必须知道）+ §6.5 移交前修掉的一个真红

> §6.1–§6.4 是**仍然存在的限制**；§6.5 是**已经修掉**的缺陷，写在这里是因为
> 「它为什么能躲过 53/53 的自检」比「它坏了」更值得 B2 记住。

### 6.1 `index.json` 不是原子写，且 `verify` 不核它
`rebuild_index()` 直接 `self._write_json(self.index_path, payload)`
（`scripts/c_decisions_registry.py:507`–`:510`），**没有** `os.replace` / `flock`
（`grep -n 'flock\|os.replace' scripts/c_decisions_registry.py` ⇒ 0 命中）。
⇒ 在**裁定 39.2 的四会话并发**下（B 收尾 + C 活进程 + A2 + B2），两个进程同时写 index 会**撕**。
**后果可控**：index 是派生的，权威永远是 `entries/` + `events/`；撕了就 `rebuild-index`。
**给 B2 的建议**（C 不自行改，属冻结后不追做）：若登记处要长期用，
把 index 写入改成 `tmp + os.replace`，或干脆**不写 index**、每次现算。

### 6.2 撤销的牙**在真登记簿上从未被真实触发过**
`events/` 现在 **2 个文件**（`0001-annotate-8dfe36a532f7.json`、`0002-annotate-10acc86fd32d.json`，都是 ADR-C-013 的自查追记），
但 **`revoke` / `supersede` 事件仍为 0**、`counts_by_status` 里 `retired=0 / superseded=0`。
**annotate ≠ revoke**，不能拿它冒充"撤销已被真实用过"。
⇒ 「撤销有牙」的现有证据来自 **`selfcheck` 的隔离沙箱合成用例**（**数字无物理意义**，ADR-C-007 口径），
其中包含验收 2 要求的两条硬断言：**造一条撤销 ⇒ 被撤条目 `status` 真的变**、且**原文件 sha256 逐字节不变**。
**这不是"真登记簿上验证过"**，B2 第一次执行真 `revoke` 之前，请先在临时登记簿上演练一次：

```bash
$R --registry /tmp/b2_registry_rehearsal selfcheck     # 沙箱演练（不碰真登记簿）
```

### 6.3 `acks/` 与 `revocations/` 是早期设计残留（**空目录，代码不引用**）
工具只 `mkdir` 两个目录：`entries_dir` / `events_dir`（`:196`–`:197`）。
⇒ 那两个空目录**不是**权威、**不要**往里写东西；C 未 `rm`（禁 `rm`），留档并在本单登记。

### 6.4 **A2 / B2 没有号段**（需 D 裁，C 不自决）
`add --line` 只接受 `{A,B,C,D}`，编号规则表里也只有四条线。A2/B2 是**新开两线**
（裁定 38.3），它们的决定该记成什么，**现在无解**。C 提两个候选，**都不自行实施**：

- **(a)** 沿用母线段：A2 → `ADR-A-<n>`、B2 → `DR-0<n>`，在 `line` 字段外**另加** `session=A2/B2`
  区分。优点：号段不膨胀；缺点：读号看不出是哪条会话，跨会话追溯要靠字段。
- **(b)** 新开号段：`ADR-A2-<n>` / `DR-B2-<n>`，并扩 `--line` 的取值。
  优点：号即身份；缺点：号段数量翻倍，且 `counts_by_line` 的历史可比性断裂。

**并且这个缺口比号段更硬一层**（C 只读实测）：`--line` 在 `add` / `ack` / `list` 三处都是
`choices=list(LINES)`，而 `LINES = ("A","B","C","D")`（`scripts/c_decisions_registry.py:81`、
`:702`、`:714`、`:739`）⇒ **B2 现在无法用自己的名字 `ack`**（`ack --line B2` 会被 argparse 直接拒）。
同时 `requires_ack_from` 是**自由文本**（`:310`、`:771`）⇒ 若有人把 `B2` 填进 ack 义务，
就会造出一个**永远 `missing`** 的假红点（看着像"有人没认"，其实是"没人能认"）。
**所以 D 裁号段之前**：B2 只用 `annotate`（`--line` 非必填）与 `verify`/`list`，**不要** `add` 新号、
**不要**把 `B2` 写进任何条目的 ack 义务；要扩就扩 `LINES` 一处，别在文本里绕。

**C 的倾向**：(a) + `session` 字段（与本轮 `provenance_kind` 子标签同型：**不改二元/四元主分类，
用子标签承载新维度**，避免词汇表膨胀）。但**号段规则属 D**（执行单原文「编号规则（执行单重申，
登记处只接续、不重编）」）⇒ **请 D 裁**，B2 在裁之前可以只用 `annotate`（`--by` 是自由文本），**不要**用 `add` 造新号、
也**不要**用 `ack`（`--line` 会被 `choices` 拒）。

---

## 7. 只读复核命令（D / B2 都可以跑）

```bash
PY=/root/venvs/rlrobot/bin/python
cd /workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot
CUDA_VISIBLE_DEVICES="" $PY scripts/c_decisions_registry.py verify           # ⇒ PASS (red=0 warn=0)，exit 1 = 有红点
CUDA_VISIBLE_DEVICES="" $PY scripts/c_decisions_registry.py list --missing-acks
CUDA_VISIBLE_DEVICES="" $PY scripts/c_selfcheck_decisions_registry.py        # ⇒ 68/68
ls work/decisions/registry/entries | wc -l                                    # ⇒ 79
ls work/decisions/registry/events  | wc -l                                    # ⇒ 2（均为 annotate；§6.2）
python3 -c "import json;d=json.load(open('work/decisions/registry/index.json'));print(d['counts_by_line'],d['counts_by_status'],d['n_missing_acks'])"
```

**待 ack 的六条**（C 本轮登记）：
`ADR-C-009`（env manifest 同源纪律：C-F1/C-F2 修法、三条断点、import 面实测）、
`ADR-C-010`（登记处设计与四条验收）、`ADR-C-011`（P1-5 `physical_fact` 接线）、
`ADR-C-012`（P1-6 逐臂 run manifest）—— 以上四条 `requires_ack_from=A,B,D`，现 `missing=A,B,D`；
`ADR-C-013`（冻结收尾 + 本移交单）、`ADR-C-014`（CLI 崩溃的根因与修法，§6.5）
—— 两条都是 **`requires_ack_from=D`**，现 `missing=D`
（**只设 D**，正是按 §6.4 的口径自我适用：A/B 已冻结、B2 无法用自己的名字 ack，
设了就是永久假红点）。
**A/B 线冻结 ⇒ 前四条大概率永远停在 `missing`**；C 的建议是**由 D 一次性处置**
（要么 D 代 ack 并注明"A/B 已冻结、ack 义务转为留档可见"，要么显式 `annotate` 记为
"冻结时未 ack"）。**C 不代 ack、也不自行取消 ack 义务**（取消义务等于把验收 3 的牙拔掉）。

---

## 8. 卫生声明

- 本单是**文档**，未改登记簿任何条目、未 `add`/`revoke`/`ack`/`annotate` 任何一条（C 自己的
  `ADR-C-013` 走正常 `add` 流程，见 `work/decisions/decisions_20260929_C.md`）。
- 未用 `rm`（含那两个残留空目录）；未执行任何 git 写命令（B/B2 是单写者）；未改 `configs/`、
  `scripts/setup_env.sh`、任何 lock、A/B/D 与 A2/B2 的产物目录；全程 CPU-only。
- 合成数字一律标注**无物理意义**（ADR-C-007）；§6.2 明确指出撤销牙的证据来自合成用例，
  **没有**把它写成"真登记簿已验证"。

### 6.5 移交前 C 自己撞出并修掉的一个**真红**：`ack` / `annotate` 的 CLI 曾经会崩（ADR-C-014）

B2 接手时它是**好的**，但 B2 应当知道它**曾经是坏的**、以及**为什么 53/53 的自检没抓到**：

- **症状**（实测 traceback）：`annotate` 与 `ack` 两条 CLI 都崩在修前的 `:783`
  —— `AttributeError: 'Namespace' object has no attribute 'kind'`。`revoke` 正常（它有 `--kind`）。
  ⇒ 也就是说：**验收 3（ack 可核）在 CLI 上曾经是死的** —— `list --missing-acks` 能看，
  但**没有任何一条线能通过命令行 ack**。
- **根因**：`kind = {"ack": "ack", "revoke": args.kind, "annotate": "annotate"}[args.cmd]`
  —— 字典字面量的**三个值先全部求值**，而 `--kind` 只挂在 `revoke` 子命令上（`:725`）。
- **为什么自检全绿却没抓到**：前 8 案**全在进程内调 API**（`reg.append_event("ack", ...)`），
  **没有一条经过 argparse / CLI**。⇒ 缺陷类是「**被测对象与用户使用的对象不是同一个**」，
  与"恒真判据"同族但**方向相反**：不是判据不看东西，而是判据看的是**另一个东西**（库）。
- **修法**：`kind = getattr(args, "kind", None) or args.cmd`（修后 `:786`）；
  顺带把 `by=... or args.line` 改成 `getattr(args, "line", None)`（`:789`）——
  `annotate`/`revoke` 没有 `--line`，此前没崩只是因为 `--by` 是 `required=True` 让 `or` 短路了，
  **那是运气不是设计**。
- **牙**：新增第 9 案 `case_cli_surface`（**15 条检查**，自检 53/53 → **68/68**）：
  子进程真跑 `add/ack/annotate/revoke/supersede` 并**逐条核后果**（事件落盘、`missing_acks` 少一个、
  `status` 由事件派生成 `retired`/`superseded`、跑完 `verify` 仍 PASS）；
  再配一个**把 eager 字典塞回源码副本**的变异体，断言变异体上 `ack`/`annotate` **必须**崩、
  而 `revoke` 仍通（**牙不是恒红**）；变异生效本身也有一条断言（防止日后重构让变异静默失效）。
- **给 B2 的一般规则**：**带 CLI 的工具，自检至少要有一条走子进程的用例**，并配变异体证明它能红；
  **「库的自检全绿」不得被写成「工具可用」**——这两个主张的对象不同。B2 建 π₀.₅ 准入闸时同适用
  （闸若既有库函数又有命令行入口，两条都要有牙）。
