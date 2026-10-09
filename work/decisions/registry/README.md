# `work/decisions/registry/` —— 决定登记处（口径与规则）

**这不是文档，是台账的权威存储。** 实现与判据都在
`scripts/c_decisions_registry.py`（写入/派生/`verify`）与
`scripts/c_selfcheck_decisions_registry.py`（双向变异自检，53 条）。
本文件只解释**口径**；要判据请读那两个脚本本身（裁定 21：判据单一来源）。

建立依据：待办 2 / 执行单 P0-4（裁定 29.5 第 1 条改判 P0）。
动机是本轮实测的损失：0929 检修把 `/root/venvs/` 与 `~/.codex/sessions/` 一起清掉，
环境靠 lock 复现了、**对话历史不可复现**；而「同一条裁定在三个地方有三种措辞、
没人能说出哪份是权威」这件事，D 自己在本轮撞上了。

---

## 1. 目录

| 路径 | 是什么 | 权威性 |
| --- | --- | --- |
| `entries/<decision_id>__<sha256_12>.json` | 一条决定一个文件；文件名尾 = 该文件内容的 sha256 前 12 位 | **权威** |
| `events/<seq>-<kind>-<sha256_12>.json` | append-only 事件流：`ack` / `revoke` / `supersede` / `annotate` | **权威** |
| `index.json` | 由 entries + events 重算的检索视图 | **派生**（`rebuild-index` 可随时重出，丢了不算丢数据） |
| `README.md` | 本文件 | 口径说明 |

`acks/` 与 `revocations/` 两个空目录是早期布局的残留；**ack 与撤销都是事件**，
一律落在 `events/`，不要往那两个目录写东西。

## 2. 原子单位与四个不变量

1. **内容寻址**：文件名里的哈希就是内容的哈希。改一个字节 ⇒ 重算值与文件名不符 ⇒
   `verify` 报 `tampered`，且**原哈希取不回任何条目**。哈希在寻址，不是装饰。
2. **append-only**：登记处**只新增文件**，从不改写既有文件。撤销、取代、ack 全部是
   **新事件**；条目的 `status` 由事件流**派生**，不是被改写出来的。
   （自检用 before/after 的 sha256 **与 mtime** 双重证明原文件没被碰。）
3. **不重造口径**：登记处只存「决定 + 证据指针 + ack」。摄取历史条目时
   `statement_kind="pointer_only"`（只给标题 + 源文件锚点 + sha256_12，**不抄正文**）；
   任何 `statement_kind="full_text"` 且带 `criteria` 字段的条目 ⇒ `verify` 报
   `criteria_duplicated`。判据的唯一来源仍是门禁/自检脚本本身。
4. **登记处不代发号**：号段与作者线不符 ⇒ `add()` 直接拒（见 §3）。

## 3. 编号规则（只接续、不重编）

| 号段 | 属线 | 例 |
| --- | --- | --- |
| `DR-D<n>` | D 线裁定序号 | `DR-D36` |
| `DR-0<n>` | B 线门禁 / 流程决定 | `DR-014` |
| `ADR-A-<n>` | A 线架构决定 | `ADR-A-017` |
| `ADR-C-<n>` | C 线架构决定 | `ADR-C-008` |

- `DR-D` 与 `DR-0` **共享 `DR-` 前缀但不共享号段**：`DR-013` 属 B，`DR-D13` 属 D，互不占号。
- 下一号 = **「源文档 ∪ 登记处」里该号段的最大序号 + 1**。
  源文档扫描面是 `work/decisions/` 下**全部** markdown（登记处自己除外），
  **不是**写死的一份清单 —— 别线随时会新开当日文档或在旧文档里补发新号
  （今天实测到 `decisions_20260928_B.md:822` 补发 `DR-014`），写死就扫不到 ⇒ 撞号。
  摄取范围与并号扫描面是两件事：前者要稳定可复现，后者要**尽量宽**（宁可多认一个号）。
- 事件不占上述号段（事件 id = `EV-<seq>`）。

## 4. 两层哈希：`sha256`（文件）与 `payload_sha256`（决定）

一个条目里有两类字段，必须分开哈希：

- **payload（决定了什么）**：`decision_id` / `line` / `title` / `statement` /
  `statement_kind` / `decided_at` / `affects` / `requires_ack_from` / `evidence_pointers` /
  `source` / `supersedes` / `authority_pointers` / `criteria_single_source` / `extra`。
  ⇒ `payload_sha256` = 这部分的哈希，**判重按它**。
- **簿记（谁何时记的第几版）**：`version_seq` / `registered_at` / `registered_by` /
  `payload_sha256` 自身。⇒ 会随每次登记而变，但不改「决定了什么」。

为什么必须分层（两处真踩过的坑，都在自检里钉住了）：

- `registered_at` 若算进判重分母，「同内容重复登记 ⇒ 拒绝」就只在两次调用**落在同一秒**时
  才成立，跨秒会静默多出一版 ⇒ 那是靠运气的判据。
- `version_seq` 若算进判重分母，重复登记会因为版本号 +1 而哈希不同 ⇒ 去重护栏被完全打穿。

`version_seq` 同时是**版本顺序的权威键**：不靠文件名（尾部是内容哈希，字典序与写入时间
**无关**，「最新版」会随机落错 ⇒ 旧 ack 永远显示 `matches_current_content=true`，判据失去牙），
也不靠 mtime（文件系统状态，可被碰）。

## 5. 状态、撤销与「牙」

`status` ∈ `active` / `retired`（被 `revoke`）/ `superseded`（被 `supersede`），
由**最后一条**指向它的 `revoke`/`supersede` 事件派生。

**撤销若不会让任何东西变红，它就不是机制。** 两类引用的语义**相反**，必须分开判：

| 字段 | 语义 | 何时报红 |
| --- | --- | --- |
| `authority_pointers` | 「我拿它当权威」 | 引用的条目已 `retired`/`superseded` 而**引用方仍 `active`** ⇒ `dangling_authority`（撤销没传导下去） |
| `supersedes` | 「我取代它」 | 被取代者**仍 `active`** ⇒ `supersede_not_propagated`（取代只写了一半，缺一条 `supersede` 事件） |

把两者合并判会让「传导成功」也报红 ⇒ 判据恒红 ⇒ 等于没有判据。
每条牙在自检里都配了**反面用例**证明它非恒红。

## 6. ack

- `requires_ack_from` 三态：`None` = 未指定 ⇒ 由 `affects` 推；`()` = **显式**声明本条不设
  ack 义务（摄取历史条目用它：ack 纪律从登记处生效那天起算，**不追溯**给 73 条老裁定补 ack）；
  非空 = 指定哪几线必须 ack。
- **作者线不给自己 ack**：`missing_acks` 里排除 `owner_line(decision_id)`。
- ack 事件记下**当时条目的内容哈希**。条目换版本后，旧 ack 的
  `matches_current_content` 自动变 `false`（= stale：ack 的是旧内容，需要重新 ack）。
- 未 ack 的**可见**：`list --missing-acks`、`index.json` 的 `n_missing_acks`。不靠人记。

## 7. `verify` 的红/黄清单

**红**（`pass=false`，exit 1）：`tampered`、`payload_sha256_mismatch`、`entry_unreadable`、
`event_unreadable`、`event_tampered`、`event_target_missing`、`criteria_duplicated`、
`pointer_without_source`、`dangling_authority`、`supersede_not_propagated`。

**黄**（不影响 `pass`，但必须看得见）：`revoked_version_not_current`（撤的是旧版本，
新版本仍 active ⇒ 需要重新裁）、`version_bookkeeping_missing`（早期格式条目缺
`version_seq`/`payload_sha256` ⇒ 重新摄取即可补齐）。

## 8. 常用命令

```bash
PY=/root/venvs/rlrobot/bin/python
CUDA_VISIBLE_DEVICES="" $PY scripts/c_decisions_registry.py verify              # exit 1 = 有红点
CUDA_VISIBLE_DEVICES="" $PY scripts/c_decisions_registry.py list --missing-acks # 谁还没 ack
CUDA_VISIBLE_DEVICES="" $PY scripts/c_decisions_registry.py show --id ADR-C-009
CUDA_VISIBLE_DEVICES="" $PY scripts/c_decisions_registry.py show --hash <sha256 或前缀>
CUDA_VISIBLE_DEVICES="" $PY scripts/c_decisions_registry.py add --line C --title ... --statement ... \
    --affects A,B,D --requires-ack-from A,B,D --evidence path:why --authority path
CUDA_VISIBLE_DEVICES="" $PY scripts/c_decisions_registry.py ack --id ADR-C-009 --line B --reason ...
CUDA_VISIBLE_DEVICES="" $PY scripts/c_decisions_registry.py revoke --id DR-Dxx --by D --reason ...
CUDA_VISIBLE_DEVICES="" $PY scripts/c_decisions_registry.py ingest --dry-run    # 摄取历史 markdown
CUDA_VISIBLE_DEVICES="" $PY scripts/c_decisions_registry.py rebuild-index
CUDA_VISIBLE_DEVICES="" $PY scripts/c_selfcheck_decisions_registry.py           # 53 条双向自检
```

`show --hash` 接受 sha256 前缀；`ingest` 对已存在的号只跳过、不重写。

## 9. 写入纪律

- 登记处在 **C 线的写入边界**内；别的线要登记自己的决定，请走 CLI（`add`/`ack`/`revoke`），
  不要手写 `entries/`、`events/` 里的文件 —— 手写会绕过哈希命名与 `version_seq`。
- 任何「撤销」都不得改写被撤条目的文件；只准追加事件。
- 覆盖式重摄取（例如补齐 §4 的两个字段）前，先把旧 `entries/` 与 `index.json`
  **整目录归档**到 `/workspace/mnt/sppro/yhzhang91/recycle_bin/`（本仓禁用 `rm`），
  并写一份 `WHY_RECYCLED.md` 说明为什么可以安全重做。
  2026-09-29 16:1x 做过一次，归档在
  `recycle_bin/c_decisions_registry_pre_payload_sha_20260929_161643/`；
  当时真登记处 **0 条事件** ⇒ 没有任何 ack/revoke/supersede 引用条目哈希 ⇒ 重算无损。
  **有事件之后再重摄取就不是无损的**，必须先核对事件里的 `target_sha256`。
