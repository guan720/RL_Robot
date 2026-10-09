"""把上游门禁裁定读成「带身份与有效性的裁定包」——C 线 ingest 的前置层（D 清单 P0-3）。

为什么必须有这一层
------------------
门禁在 2026-09-28 一天内连升 v1.1 → v1.2 → v1.2.1，约 40 份留档裁定被重判、有臂翻
`measurement_valid=False`、旧产物被归档，同一个目录里同时存在**多个 `gate_build`**。
而 C 侧现状是：

- `registry/release_bundle.py::DirectionScore` 只有 `flick_frac` / `controlled_success_rate`；
- `harness/ledger.py`、`harness/data_bridge.py`、`registry/release_bundle.py` 里
  grep 不到 `measurement_valid` / `gate_build` / `gate_spec_sha256` / `superseded`。

照现状 ingest，等于把**已作废的数字当物理事实**写进 append-only 账本 —— 账本一旦写下就不该
再改，作废数字进去就出不来了。这一层就是那道闸：先给每个数字绑定「谁判的、用哪一版判据判的、
这次测量本身可不可信」，再决定它能不能当事实用。

三条纪律
--------
1. **只读上游，不复制判据**。`controlled_success` / `flick` / `over_lift` 等一律取上游落盘的
   数值，本层绝不重算（重算就会出现第二套判据，正是 A 线 `a_regate_gate_current.py` docstring
   点名的产物漂移）。当前门禁构建通过 **import** `scripts/b_gate_controlled_success.py` 读取，
   不硬编码版本号 —— 版本号写死在 C 的文件里，B 一升级就过期。
2. **身份是内容寻址的**。每条记录带裁定文件自身的 `sha256` 与被判评测文件的 `sha256`；
   文件变一个字节，身份就变（仓库不是 git repo，这是唯一可靠的版本指纹）。
3. **分级而不是二值**。`usable_for` 有六档，`stale_build_evidence` 不是「错」，它是
   「旧判据口径的证据」——可以留档、可以比对，但**不能**当当前事实进账本或发布包。
4. **「裁定已核可、实现待落地」必须自成一档**（监管备忘 增补六 §8-C3 / 裁定 17.7）。
   存在这样一种状态：监管层已会签某臂的探针免罪（裁定 10 五条准入 D 独立复算全过），
   而门禁代码在当前构建上**产不出**那个结论（登记册的写法不被受理）。这种记录
   既不是 `physical_fact`（门禁产不出该数值），也不是 `stale_build_evidence`
   （事实基础已核可，与构建新旧无关），更不该被记成 `invalid_measurement`
   （那等于让**未被实现承载**的门禁结论单方面压倒已会签的裁定）。
   专用标签沿用 D 的 `PENDING_IMPL_probe_exonerated`：不得写「已免罪」（超出事实），
   也不得写「能力未知」（丢掉已核可的事实基础）。
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# T-B2-20（D→B2 执行单 2026-09-30 §二；裁定 93.4 的地基）：**多门禁并存**
# ---------------------------------------------------------------------------
# D 的裁定原文：「批准多门禁并存。`registry/verdict_identity.py:47` 的 `GATE_MODULE_PATH`
# 由**单值**改为**按 `gate_id` 索引的映射**：默认仍是 ACT 冻结基线（`0928` 两份 lock、
# `arms_summary_v3.json`、`requirements.lock.txt`、`clip*.json` **一个字节不动** ⇒ 冻结面不破）；
# 新增 `gate_id = "pi05_norm_contract"` → 指向 C2 的 `scripts/c2_gate_norm_contract.py`；
# **verdict_identity 必须带 `gate_id`；跨 gate 的身份串不得互认**（拿 ACT 门禁的身份去认
# π₀.₅ 闸的产物 ⇒ 必须红）。」
# 为什么现在做（不是"以后再说"）：裁定 93.4 要求 **A2 的 BC 入口自己复算闸产物 sha 并与 C2
# 声明值对账**，`registry/` 是这条对账的身份源；它此前只认 ACT 门禁 ⇒ A2 无处对账。
DEFAULT_GATE_ID = "act_controlled_success"
PI05_GATE_ID = "pi05_norm_contract"
GATE_MODULE_PATHS: dict[str, Path] = {
    DEFAULT_GATE_ID: ROOT / "scripts" / "b_gate_controlled_success.py",
    PI05_GATE_ID: ROOT / "scripts" / "c2_gate_norm_contract.py",
}
# 每个 gate 的**身份面**：哪些文件一起构成"这一版判据"。
# π₀.₅ 这一栏**必须**带 `harness/norm_contract.py` —— 判据本体在那个模块里，闸脚本只是驱动壳。
# 只认闸脚本的指纹，会在 C2 改判据而不动闸壳时**纹丝不动**（本轮实测就是这么回事：
# 11:4x 时 `harness/norm_contract.py` 已由 `43d19a876af1` 变到 `a030e951787e`，而
# `scripts/c2_gate_norm_contract.py` 仍是 `3f44225a5fa1`）⇒ 那就是"身份串认的是壳、不是判据"，
# 与本层存在的理由正相反（本层的由来就是"同一目录里同时存在多个 gate_build"）。
GATE_IDENTITY_FILES: dict[str, tuple[tuple[str, str], ...]] = {
    DEFAULT_GATE_ID: (("scripts/b_gate_controlled_success.py", "gate_module"),
                      ("docs/b_controlled_success_v1_20260928.md", "gate_spec_doc")),
    PI05_GATE_ID: (("scripts/c2_gate_norm_contract.py", "gate_module"),
                   ("harness/norm_contract.py", "criteria_module")),
}
# **登记但不进指纹**的相关件（连同"为什么不进"的理由一起写死，不留给读者猜）。
GATE_RELATED_FILES: dict[str, tuple[tuple[str, str, str], ...]] = {
    DEFAULT_GATE_ID: (),
    PI05_GATE_ID: (("scripts/c2_build_norm_stats.py", "stats_builder",
                    "它是 stats 档的**生成器**（产物侧身份），不是闸的判据面；stats 档自己的身份"
                    "由 C2 在 stats 件里声明（`representation_version` + sha），A2 按裁定 93.4 "
                    "对账时两边都要复算 ⇒ 不混进门禁指纹，否则一次生成器改动会被读成"
                    "「判据换了」"),),
}
# 产物侧的**门禁归属标记**：产物自己不写 `gate_id` 时用它推断（推断不出 ⇒ 如实记 None，**不猜**）。
# 语义 = `(键, 值前缀)`；值前缀为空串表示「该键存在即可（任意值）」。
# π₀.₅ 的实测标记 = `gate_verdict.json` 的 `artifact == "c2_norm_contract_gate"`
# （as_of 2026-09-30 07:40 那份：`runs/vla/c2_norm_contract_20260929/gate/run_20260930_073852/`）。
# ACT 一栏只收**门禁专属**键：`gate_spec_sha256` / `gate_spec_doc` 指向 ACT 的判据规格
# `docs/b_controlled_success_v1_20260928.md`；π₀.₅ 的判据本体在 `harness/norm_contract.py`，
# 它的产物里没有这两个键。实测覆盖率（2026-09-30，`runs/infra/lerobot_act_env_20260928/`
# 全量 234 条逐臂裁定行）：`gate_spec_sha256` 221/234、`gate_spec_doc` 221/234、`artifact` 0/234；
# C2 的 `gate_verdict.json` 顶层两个键都没有 ⇒ 两侧都不误认。那 13 条没有规格身份键的行
# 归属如实记 `None`（`not_measured`，不猜）；它们本来就按缺省门禁（ACT）对账 ⇒ 不构成回归。
GATE_ARTIFACT_MARKERS: dict[str, tuple[tuple[str, str], ...]] = {
    DEFAULT_GATE_ID: (("gate_spec_sha256", ""), ("gate_spec_doc", "")),
    PI05_GATE_ID: (("artifact", "c2_norm_contract"),),
}
# **通用裁定形状键 ≠ 门禁归属证据**（本轮改判的核心；自检件 MG5 抓到的洞正在这一行上）。
# 这些键说明「这是一条裁定行」，不说明「这是**哪个门禁**的裁定行」：π₀.₅ 要写逐臂裁定，
# 自然会带 `gate_build` / `measurement_valid` / `accounts`。把它们当 ACT 的归属标记，会让
# **每一份** π₀.₅ 逐臂产物同时命中两个门禁 ⇒ `infer_gate_id` 按「多命中不猜」回 `None`
# ⇒ 跨门禁检查静默落空 ⇒ 一份把构建号伪造成 ACT 现值的 π₀.₅ 产物被判成 `physical_fact`
# 并**准入**（MG5 的 b2 形态实测就是这么红的：构建号对得上、门禁对不上，而闸只比了构建号）。
# 所以它们不进标记表；「归属不可判」另有一条路（`artifact_gate_ambiguous` ⇒ 拒收），
# 与「归属未测」（0 命中 ⇒ `not_measured`）**分开记**，因为两者的后果不同。
GENERIC_VERDICT_SHAPE_KEYS: tuple[str, ...] = (
    "gate_build", "gate_version", "measurement_valid", "accounts", "terminal_semantics",
    "input_contract", "field_class", "per_episode", "gate_pass", "gate_reason")
# 兼容旧引用（`scripts/c_selfcheck_verdict_identity.py:79/95/98/121` 直接读这个名字）：
# **默认仍是 ACT 冻结基线**，指向的文件与改判前逐字节相同（冻结面不破；已由 B2 的多门禁自检件
# `runs/vla/b2_registry_multigate_20260930/` 逐件核过 sha）。
GATE_MODULE_PATH = GATE_MODULE_PATHS[DEFAULT_GATE_ID]

# 三套账与五档 bucket 的名字来自上游规格，C 侧只核对存在性，不重新定义语义。
ACCOUNTS = ("policy_independent", "system_assisted", "autonomous_learning")
BUCKETS = ("controlled_success", "provisional_pass", "over_lift", "flick", "insufficient_lift")

USABLE_PHYSICAL_FACT = "physical_fact"                 # 当前构建 + 测量有效 ⇒ 可当事实进账本
USABLE_STALE_BUILD = "stale_build_evidence"            # 旧构建：留档/比对可以，当事实不行
USABLE_INVALID_MEASUREMENT = "invalid_measurement"     # 测量本身被判不可信（INVALID / 截断当失败）
USABLE_UNIDENTIFIED = "unidentified_build"             # 判据身份或有效性声明缺失：连「旧」都说不清
USABLE_NOT_A_VERDICT = "not_a_verdict"                 # 聚合/敏感度报告：它**关于**裁定，本身不是裁定
# --- T-B2-20（D→B2 执行单 2026-09-30 §二）：**跨门禁**档 ---
# 「拿 ACT 门禁的身份去认 π₀.₅ 闸的产物 ⇒ 必须红」。这一档**不是** `unidentified_build`
# （身份很清楚，只是**属于另一个门禁**），也不是 `stale_build_evidence`（那个档的语义是
# 「同一个门禁的旧判据口径」，跨门禁套用它等于把两个判据体系说成一条时间线）。
# 词汇表扩项按裁定 31.4 的规矩「须先过 D」⇒ 本档的授权就是 D→B2 §二 那条裁定原文
# （要求"必须红"），不是 B2 自行加档；下游消费者（`registry/release_bundle.py` 只吃
# `physical_fact`、`harness/ledger.py` 走 `admit_as_physical_fact`）都按"非 physical_fact 即拒收"
# 处理 ⇒ 加档不会让任何既有消费者误放行。
USABLE_WRONG_GATE = "wrong_gate_identity"              # 跨门禁：身份串不得互认（必须红）
# 增补六 §8-C3：裁定已核可、门禁实现未承载。既不是事实（产不出），也不是旧证据（与构建无关），
# 更不是测量无效（那会让未实现的门禁结论压倒已会签的裁定）。
USABLE_PENDING_IMPL = "pending_impl_ruling_approved"
PENDING_IMPL_LABEL = "PENDING_IMPL_probe_exonerated"    # D 的过渡期专用标签（裁定 17.7）
# **裁定 28.1（增补七 §13，2026-09-29 11:5x）：该标注作废、全部撤下。**
# v1.5 / `f19f61341cbe` 上 D 的复签正式生效，目标臂的**现状态** =
# `probe_exonerated`（`probe_kind=clip_at_train_absmax`、`band_checked=false`）、
# `measurement_valid=True`、`gate_pass=True`；裁定 28.5 并规定「不得再写 `PENDING_IMPL`」。
#
# 但**本档的机制不作废**（与裁定 28.4 对护栏① 的处理同型：本轮成 moot，机制仍建议留）：
# 这一档描述的是「**某一份历史产物**的门禁输出没有承载当时已会签的裁定」，与臂的现状态无关。
# 旧产物不会因为裁定更新而改写（内容寻址 + 只读上游）。所以 C 的处置是：
#   ① 机制与档名保留；标签保留为**记录级标识符**；
#   ② 任何输出都不得让读者把它读成现状态 —— 命中记录的 `reasons` 里逐条带上作废声明，
#      清单摘要里单列 `pending_impl_ruling`（retired=true + 引用纪律）；
#   ③ 现状态一律**转引** D 的裁定并注明「C 未独立复核」，C 不重判、不另造口径。
LABEL_RETIRED = True
LABEL_RETIRED_BY = "裁定 28.1 / 28.5（增补七 §13，v1.5/f19f61341cbe 复签生效，2026-09-29 11:5x）"
LABEL_RETIREMENT_NOTE = (
    f"注意：{PENDING_IMPL_LABEL} 标注已按 {LABEL_RETIRED_BY} **作废**；它在此处只标识"
    "「这份历史产物的门禁输出未承载当时已会签的免罪」，**不是**该臂的现状态。"
    "该臂现状态见裁定 28.1（probe_exonerated @ v1.5/f19f61341cbe）。")
CITATION_RULE_28 = ("引用 25/22/1 必须带 v1.5 / f19f61341cbe；不得再写 PENDING_IMPL 当现状态；"
                    "引 v1.2.1 / e4f5ec887788 与 v1.4 / b9379fdb1089 的旧表必须标「历史口径」"
                    "（裁定 28.2 / 28.5）")
USABLE_LEVELS = (USABLE_PHYSICAL_FACT, USABLE_PENDING_IMPL, USABLE_STALE_BUILD,
                 USABLE_INVALID_MEASUREMENT, USABLE_UNIDENTIFIED, USABLE_NOT_A_VERDICT,
                 USABLE_WRONG_GATE)

# --- 裁定 31.4（增补八 §24，2026-09-29 12:4x）：待办 9 判 **(b) + `provenance_kind` 子标签** ---
# `usable_for` 回答「能不能当现构建证据用」（**二元可用性，不分叉**）；`provenance_kind` 回答
# 「为什么不能」（**不丢信息**）。所以子标签挂在理由侧，**不新增 `usable_for` 档位** ——
# 为 5 条记录新开一档会让下游每个消费者都要多认一个值，词汇表膨胀的代价大于收益（D 不采纯 (c)）。
# 取值是**封闭集合**，就地扩项 = 词汇表膨胀，须先过 D。
PROVENANCE_DELIBERATE_REJECTION_PROBE = "deliberate_rejection_probe"  # A 故意造出来**被拒**的写法探针
PROVENANCE_FROZEN_PREREG_ANCHOR = "frozen_prereg_anchor"              # 预登记钉死旧版本的冻结锚点
PROVENANCE_SUPERSEDED_RERUN = "superseded_rerun"                      # 同臂已有现构建重判取代它
PROVENANCE_ORDINARY_STALE = "ordinary_stale"                          # 默认：单纯旧构建留档
PROVENANCE_KINDS = (PROVENANCE_DELIBERATE_REJECTION_PROBE, PROVENANCE_FROZEN_PREREG_ANCHOR,
                    PROVENANCE_SUPERSEDED_RERUN, PROVENANCE_ORDINARY_STALE)
# 子标签按**产物的来源目录**（`provenance`，由 `inventory()` 按来源分层算出）判定，不按文件名猜。
DELIBERATE_REJECTION_PROBE_DIRS = ("migration_gate/exoneration_path_probe",)
FROZEN_PREREG_ANCHOR_DIRS = ("regate_v121_pinned",)
# 同一个探针目录里既有「故意被拒」的写法探针，也有**正向对照**（`gate_C1_control_stdfloor.json`：
# ic=probe_exonerated、gate_pass=true）。只按目录判会把正向对照也说成「故意被拒」——那是假话。
# ⇒ 必须同时看到「这份产物确实被拒了」才落这个子标签。
DELIBERATE_REJECTION_IC = "violated"
REGRADE_RULING_31_4 = (
    "裁定 31.4（增补八 §24，2026-09-29 12:4x）：待办 9 判 (b) —— 命中「裁定已核可、实现待落地」"
    f"形状、但该臂在**当前构建**下已有承载免罪产物的记录，转 {USABLE_STALE_BUILD}，"
    "另在理由侧加 provenance_kind 子标签、留 regraded_from 以便审计。(a) 不采（档名字面是"
    "「实现待落地」，而这批的 violated 是探针的预期结果 —— 说谎的标签比没标签更坏）；"
    "纯 (c) 不采（为 5 条记录把二元可用性变三元，词汇表膨胀代价大于收益）。")
# 裁定 31.3：对账只在两侧同为当前构建时做；不同构建改报这个（**可见、但不报警**，
# 与 B 在护栏① 里对 None 的处理同型 —— `cosign_not_required_arms`）。
STALE_SIDE_NOT_COMPARABLE = "stale_side_not_comparable"
# 待办 9 提请 D 裁定时 C 写的原话（裁定 31.4 判 (b)+子标签后**照原样留档**，不改写）：
TODO9_QUESTION_AS_FILED = (
    "裁定 28.2 把 v1.2.1/e4f5ec887788 与 v1.4/b9379fdb1089 降为「历史口径」，而本档命中的 5 条"
    "**全部**出自这两个构建；同时目标臂在**当前构建**下的那份（regate_current/）已是 "
    "ic=probe_exonerated、measurement_valid=true ⇒ physical_fact（B 的 v1.5 逐臂重判已落盘，"
    "实测 48 条 physical_fact）。逐条看这 5 条的性质：4 条出自 migration_gate/exoneration_path_probe/"
    "（gate_P0_baseline / P1_scope_arm / P2_scope_artifact / P3_band_widened）—— 那是 A "
    "**故意造出来被拒**的写法探针，violated 是探针的**预期结果**，不是实现缺口；1 条出自 "
    "regate_v121_pinned/main/ —— 那是预登记 §6 钉死 v1.2.1 的**冻结锚点**，violated 同样是设计使然。"
    "⇒ 本档的名字（「实现待落地」）对这 5 条已不成立。**C 未自行改分级**（不替 D 裁口径），"
    f"提请裁定三选一：(a) 留 {USABLE_PENDING_IMPL}（逐份产物的历史事实，靠 regraded/retired "
    f"标注防误读）；(b) 随裁定 28.2 转 {USABLE_STALE_BUILD}（C 倾向此项：这 5 条都是旧构建留档，"
    "且它们「未承载免罪」的事实可由 exoneration_disagreement 计数与 reasons 保留）；"
    "(c) 给「故意被拒的探针 / 冻结锚点」另立一档。若判 (b)，C 的实施是：把本档的激活条件收窄为"
    "「该臂在**当前构建**下没有任何承载免罪的产物」（跨记录条件，放在 inventory() 里做，"
    "parse_verdict 仍是记录级纯函数），并给被改判的记录留 regraded_from 以便审计 —— 机制保留，"
    "将来再出现「条目已登记、会签块未换到新 build」的窗口时它照常生效（同裁定 28.4 对护栏① 的处理）。")
RECONCILE_SCOPE_RULE = (
    "免罪对账只在 is_current_build==true 的子集上做：两侧都带 build，只有两侧同为当前构建"
    f"才报 disagreement；任一侧不在当前构建 ⇒ 报 {STALE_SIDE_NOT_COMPARABLE}（可见不报警）。")

# 监管备忘 增补五 §9-C②／增补六：裁定身份必须含 `field_class`（裁定 14 的前提量）、
# `validity_class`、`blowup_threshold_source` 三键。
ARM_SUMMARY_NAME = "arms_summary.json"
# `validity_class` 的取值由 A 的权威表定义（裁定 10）。C 只**核对**、不重定义、不自己推导：
# `scripts/summarize_lerobot_act_arms.py` 是 `arms_summary.json` 的唯一生产者，
# 免罪资格（`VALID_probe_exonerated`）由它的 `probe_exoneration()` 在代码里逐条断言 5 项准入。
# C 再实现一遍就是第二套判据 —— 那正是 A/B/C 三线一直在防的产物漂移。
VALIDITY_CLASSES = ("valid", "VALID_probe_exonerated", "invalid")
# 免罪在**权威层**与**门禁层**各自的取值。C 只核对两者是否一致，不重新推导任何一个：
# `validity_class` 由 A 的 `summarize_lerobot_act_arms.py::probe_exoneration()` 断言 5 项准入产出，
# `input_contract.status` 由 B 的门禁产出。两者不一致 = 裁定与实现脱节，不是 C 能裁的事。
AUTHORITY_EXONERATED = "VALID_probe_exonerated"
GATE_EXONERATED = "probe_exonerated"

# 本档的**激活条件**（裁定 31.4 批准的收窄）：跨记录条件，只在 `inventory()` 里判，
# `parse_verdict` / `classify` 仍是记录级纯函数（裁定 21「判据单一来源」在 C 侧的对应物）。
PENDING_IMPL_ACTIVATION_RULE = (
    f"该臂在**当前构建**下没有任何承载免罪的产物 ⇒ 才落 {USABLE_PENDING_IMPL}；"
    "已有承载产物 ⇒ 该记录只是旧构建留档，转 stale_build_evidence 并留 regraded_from。")
CARRYING_ARTIFACT_RULE = (
    f"「承载免罪的产物」= is_current_build==true 且 input_contract.status=={GATE_EXONERATED!r} 的"
    "逐臂裁定产物（同臂、同被判决的评测文件）。C 不重跑门禁去造这个观测。")


class VerdictIdentityError(RuntimeError):
    """裁定文件读不出来 / 结构不认识。不猜、不补默认值。"""


def content_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


_CURRENT_GATES: dict[str, dict[str, Any]] = {}
_CURRENT_GATE: dict[str, Any] | None = None      # 默认门禁（ACT）的缓存别名，旧调用方读得到同一份


def known_gate_ids() -> tuple[str, ...]:
    """已登记的门禁 id（`GATE_MODULE_PATHS` 的键）。表里没有的 id ⇒ 一律报错，不落到默认门禁。"""
    return tuple(GATE_MODULE_PATHS)


def _identity_file_rows(gate_id: str) -> list[dict[str, Any]]:
    """逐件算身份面的 sha（三值：文件不在 ⇒ `exists=false` + sha 记 `None`，**不写 0/false 顶替**）。"""
    rows: list[dict[str, Any]] = []
    for rel, role in GATE_IDENTITY_FILES.get(gate_id, ()):
        p = ROOT / rel
        exists = p.is_file()
        sha = content_sha256(p) if exists else None
        rows.append({"path": rel, "role": role, "exists": exists, "sha256": sha,
                     "sha256_12": (sha[:12] if sha else None),
                     "measurement_status": ("measured" if exists else "not_measured"),
                     "in_fingerprint": True})
    return rows


def _related_file_rows(gate_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rel, role, why_not in GATE_RELATED_FILES.get(gate_id, ()):
        p = ROOT / rel
        exists = p.is_file()
        sha = content_sha256(p) if exists else None
        rows.append({"path": rel, "role": role, "exists": exists, "sha256": sha,
                     "sha256_12": (sha[:12] if sha else None),
                     "measurement_status": ("measured" if exists else "not_measured"),
                     "in_fingerprint": False, "why_not_in_fingerprint": why_not})
    return rows


def gate_identity_fingerprint(ident: Mapping[str, Any]) -> str:
    """**门禁作用域内**的身份串：`<gate_id>@<身份面各件 sha256 串联后再 sha256 的前 12 位>`。

    为什么必须带 `gate_id` 前缀（D→B2 §二：「跨 gate 的身份串不得互认」）：裸构建指纹是
    一个 12 位十六进制串，两个门禁的指纹**在字符串空间里没有区别**，任何 `==` 比较都可能
    因为巧合或因为"调用方拿错了门禁的现值"而误认。前缀把比较限制在同一门禁内 ⇒
    拿 ACT 的串去比 π₀.₅ 的产物**永远不相等**（这不是概率问题，是构造问题）。
    为什么用"身份面各件 sha 串联"而不是只用闸脚本：见 `GATE_IDENTITY_FILES` 的注释
    （π₀.₅ 的判据本体在 `harness/norm_contract.py`，只认壳会在判据变动时纹丝不动）。
    """
    gate_id = ident.get("gate_id") or DEFAULT_GATE_ID
    parts = [str(gate_id)]
    for row in (ident.get("identity_files") or ()):
        if row.get("in_fingerprint"):
            parts.append(f"{row.get('path')}={row.get('sha256')}")
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"{gate_id}@{digest}"


def current_gate_identity(gate_id: str = DEFAULT_GATE_ID, *,
                          refresh: bool = False) -> dict[str, Any]:
    """**import** 上游门禁模块拿当前构建身份（不复制判据、不硬编码版本号），**按 `gate_id` 取**。

    `GATE_BUILD` 在 ACT 上游是「门禁脚本自身内容的 sha12」，所以 B 一改判据它就变；
    C 侧读它，等于自动跟随，不会出现「C 以为当前是 v1.2.1，其实已经 v1.3」。

    T-B2-20 之后本函数是**门禁作用域**的：
    - `gate_id` 缺省 = `DEFAULT_GATE_ID`（ACT 冻结基线）⇒ 既有调用方（含 C 的自检
      `current_gate_identity(refresh=True)`）行为逐字不变；
    - 表里没有的 `gate_id` ⇒ **报错**，不静默落到默认门禁（跨门禁认错身份比认错构建更贵）；
    - 返回值**必带 `gate_id` 与 `gate_identity_fingerprint`**（D→B2 §二：verdict_identity
      必须带 gate_id）；
    - 上游没公布 `GATE_BUILD` 的门禁（实测 π₀.₅ 的 `scripts/c2_gate_norm_contract.py` 只有
      `GATE_ROOT`，没有 `GATE_BUILD`/`GATE_VERSION`）⇒ 本层按 ACT 的**同一约定**自己算
      模块内容的 sha256[:12]，并把它标成 `gate_build_provenance="registry_computed_…"`。
      **两种 provenance 不得混读**：前者是上游公布的，后者是本层代算的（代算值与 C2 在
      `gate_verdict.json` 的 `evidence.gate_sha256_12` 里声明的值可互相对账，
      实测 as_of 11:5x 两者都是 `3f44225a5fa1`）；缺失的上游字段如实记 `None`
      并列进 `missing_upstream_identity_fields`，不猜、不补默认值。
    """
    global _CURRENT_GATE
    if gate_id not in GATE_MODULE_PATHS:
        raise VerdictIdentityError(
            f"未知 gate_id={gate_id!r}；已登记的是 {known_gate_ids()}。"
            "不猜、不落到默认门禁（D→B2 §二：跨 gate 的身份串不得互认）")
    cached = _CURRENT_GATES.get(gate_id)
    if cached is not None and not refresh:
        return cached
    mod_path = GATE_MODULE_PATHS[gate_id]
    if not mod_path.exists():
        raise VerdictIdentityError(f"[{gate_id}] 找不到上游门禁模块: {mod_path}")
    spec = importlib.util.spec_from_file_location(f"_gate_probe_{gate_id}", mod_path)
    if spec is None or spec.loader is None:
        raise VerdictIdentityError(f"[{gate_id}] 无法加载上游门禁模块: {mod_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    module_sha = content_sha256(mod_path)
    published_build = getattr(mod, "GATE_BUILD", None)
    ident: dict[str, Any] = {
        "gate_id": gate_id,
        "gate_version": getattr(mod, "GATE_VERSION", None),
        "gate_build": (published_build if published_build else module_sha[:12]),
        "gate_build_provenance": ("upstream_module_attr:GATE_BUILD" if published_build
                                  else "registry_computed_module_sha256_12"),
        "gate_spec_sha256": getattr(mod, "GATE_SPEC_SHA", None),
        "gate_spec_doc": getattr(mod, "GATE_SPEC_DOC", None),
        "module_path": str(mod_path.relative_to(ROOT)),
        "module_sha256": module_sha,
        "identity_files": _identity_file_rows(gate_id),
        "related_files": _related_file_rows(gate_id),
    }
    ident["missing_upstream_identity_fields"] = tuple(
        k for k in ("gate_version", "gate_spec_sha256", "gate_spec_doc") if ident.get(k) is None)
    ident["gate_identity_fingerprint"] = gate_identity_fingerprint(ident)
    if not ident["gate_build"]:
        raise VerdictIdentityError(
            f"[{gate_id}] 上游门禁模块没有 GATE_BUILD，本层也算不出模块指纹："
            "无法判定裁定是否出自当前构建")
    _CURRENT_GATES[gate_id] = ident
    if gate_id == DEFAULT_GATE_ID:
        _CURRENT_GATE = ident
    return ident


def infer_gate_id_candidates(payload: Any) -> tuple[str, ...]:
    """产物命中的**全部**门禁归属标记（`GATE_ARTIFACT_MARKERS`），排序去重。

    与 `infer_gate_id()` 分开暴露，是因为「命中 0 个」与「命中 ≥2 个」都必须回 `None`
    （两种都不猜），但**后果不同**：前者是归属未测（`not_measured`，按调用方声明的门禁
    继续走），后者是**归属不可判**（两个门禁都像 ⇒ 必须拒收）。把两者压成同一个 `None`
    就是 MG5 那个洞的形状：不可判被读成「没有不一致」，于是构建号一对上就准入。
    """
    if not isinstance(payload, Mapping):
        return ()
    hits: list[str] = []
    for gid, markers in GATE_ARTIFACT_MARKERS.items():
        for key, prefix in markers:
            if key not in payload:
                continue
            val = payload.get(key)
            if not prefix or (isinstance(val, str) and val.startswith(prefix)):
                hits.append(gid)
                break
    return tuple(sorted(set(hits)))


def infer_gate_id(payload: Any) -> str | None:
    """从产物自身推断它出自哪个门禁（`GATE_ARTIFACT_MARKERS`）。推断不出 ⇒ `None`（**不猜**）。

    命中**多于一个**门禁 ⇒ 也返回 `None`，本层不替上游裁它属于谁；调用方必须同时读
    `infer_gate_id_candidates()` 才能区分「未测」与「不可判」（后者要拒收）。
    """
    uniq = infer_gate_id_candidates(payload)
    return uniq[0] if len(uniq) == 1 else None


def gate_id_mismatch_reason(requested: str, current: Mapping[str, Any] | None,
                            artifact_declared: Any) -> str | None:
    """跨门禁对账：三种来源（调用方声明 / 现值身份 / 产物自述）必须指向同一个门禁。

    返回 `None` = 一致；返回字符串 = **红**的理由（D→B2 §二：拿 ACT 门禁的身份去认 π₀.₅ 闸的
    产物 ⇒ 必须红）。产物没自述门禁（`None`）不算不一致 —— 那是 `not_measured`，
    按三值纪律不得读成"不符"，也不得读成"符合"。
    """
    cur = (current or {}).get("gate_id")
    if cur is not None and str(cur) != str(requested):
        return (f"调用方声明 gate_id={requested!r}，但传进来的门禁现值身份是 "
                f"gate_id={cur!r}（fingerprint={ (current or {}).get('gate_identity_fingerprint') }）"
                "⇒ 跨门禁身份串不得互认（D→B2 §二）")
    if artifact_declared is not None and str(artifact_declared) != str(requested):
        return (f"产物自述出自 gate_id={artifact_declared!r}，而本次对账用的是 "
                f"gate_id={requested!r} ⇒ 跨门禁身份串不得互认（D→B2 §二）")
    return None


def load_arm_index(arms_dir: str | Path) -> dict[str, Any]:
    """读 A 的**唯一权威表** `arms_summary.json`，建「评测文件 → 行」的索引（只读）。

    索引同时按「相对 arms_dir 的路径」与「basename」两种键登记：留档臂的 `file` 是 basename，
    而 blindfix 重测臂的 `authoritative_eval_file` 带子目录（`blindfix/xxx.json`），
    两种都要能命中，否则重测臂会静默匹配不上、`validity_class` 变成「未声明」。
    """
    arms_dir = Path(arms_dir)
    path = arms_dir / ARM_SUMMARY_NAME
    if not path.exists():
        return {"available": False, "path": str(path), "sha256": None, "index": {}, "n_rows": 0}
    sha = content_sha256(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("arms") if isinstance(payload, dict) else payload
    index: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        for key in (row.get("file"), row.get("authoritative_eval_file")):
            if not isinstance(key, str) or not key:
                continue
            index.setdefault(key, row)
            index.setdefault(Path(key).name, row)
    meta = (payload.get("meta") or {}) if isinstance(payload, dict) else {}
    # `rows` / `meta` 是 裁定 31.3 的对账要的：权威侧必须**自己带构建**（`meta.gate_build`
    # 与逐行 `gate_build`），否则又会拿 v1.0 的 gate 产物去和 v1.5 的表对账（跨构建混算）。
    return {"available": True, "path": str(path), "sha256": sha,
            "sha12": sha[:12], "index": index, "n_rows": len(rows or []),
            "rows": [r for r in (rows or []) if isinstance(r, dict)],
            "meta": {k: meta.get(k) for k in ("schema_version", "generated_at", "producer",
                                              "gate_version", "gate_build", "gate_spec_sha256")},
            "meta_denominators": meta.get("denominators")}


def read_arm_timing(eval_path: str | Path) -> dict[str, Any]:
    """读一条臂评测产物里的**时间尺度**字段（`n_action_steps` 等）。

    为什么单独一个函数、不在全量扫描里做：评测 JSON 每份 2–3 MB，127 条全读一遍要几十秒，
    而 `n_action_steps` 只在「用账本语义去解读某条真实臂」时才需要。
    """
    eval_path = Path(eval_path)
    if not eval_path.exists():
        raise VerdictIdentityError(f"评测产物不存在，无法取 n_action_steps: {eval_path}")
    doc = json.loads(eval_path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise VerdictIdentityError(f"{eval_path}: 顶层不是 dict，结构不认识")
    keys = ("chunk_size", "n_action_steps", "replan_every", "temporal_ensemble_coeff")
    out = {k: doc.get(k) for k in keys}
    out["source"] = str(eval_path)
    if out["n_action_steps"] is None:
        raise VerdictIdentityError(f"{eval_path}: 没有 n_action_steps 字段，无法确定这条臂的槽长")
    return out


def assert_n_matches_arm(n: int, arm_timing: dict[str, Any], *, arm: str = "") -> int:
    """监管备忘 增补五 §9-C④ 的硬裁定：真实帧路径的 `n` **必须等于**该臂的 `n_action_steps`。

    背景：规格算例用 n=6（γ=0.9、H=20），而真实臂是 `n_action_steps ∈ {2, 4}`
    （K=2 族为 2）。拿 n=6 的账本语义去解读 K=2 的臂，等于让 C 的槽与 A 的臂
    **不在同一个时间尺度上对话** —— harness 因此接不上主线。不一致就抛，不静默换算。
    """
    want = arm_timing.get("n_action_steps")
    if want is None:
        raise VerdictIdentityError(f"{arm or arm_timing.get('source')}: 缺 n_action_steps，无法核对 n")
    if int(n) != int(want):
        raise ValueError(
            f"n 与该臂的 n_action_steps 不一致：n={n} 而 {arm or arm_timing.get('source')} 的 "
            f"n_action_steps={want}（监管备忘 增补五 §9-C④）。真实帧路径不得沿用规格算例的 n，"
            f"也不得静默换算：要么按该臂的 n 重建视图，要么显式声明这是另一条臂。")
    return int(n)


def _unwrap(payload: Any, source: str) -> list[dict[str, Any]]:
    """上游裁定有两种落盘形态：单臂 `list`（长度 1）或裸 `dict`；多臂汇总也可能是 list。"""
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list):
        rows = [r for r in payload if isinstance(r, dict)]
        if len(rows) != len(payload):
            raise VerdictIdentityError(f"{source}: list 里有非 dict 元素，结构不认识")
        return rows
    raise VerdictIdentityError(f"{source}: 顶层既不是 dict 也不是 list（{type(payload).__name__}）")


@dataclass(frozen=True)
class VerdictIdentity:
    """一条裁定的完整身份 + 有效性裁定。`usable_for` 决定它能不能当物理事实用。"""

    source_path: str
    source_sha256: str
    arm: str
    eval_file: str | None
    eval_sha256: str | None
    gate_version: Any
    gate_build: Any
    gate_spec_sha256: Any
    gate_spec_doc: Any
    measurement_valid: Any
    measurement_validity_declared: bool
    field_class: Any
    missing_fields: tuple
    gate_pass: Any
    gate_reason: Any
    accounts: dict[str, Any]
    buckets: dict[str, Any]
    input_contract_status: Any
    suspect_truncation_as_failure: Any
    validity_class: Any
    validity_reason: Any
    arm_field_class: Any
    validity_source: str
    blowup_threshold_source: Any
    labels_reportable: Any
    upstream_superseded_by: Any
    arm_summary_sha256: str | None
    arm_verdict: bool
    # 规范名是 `is_current_build`（裁定 31.3 要求「每份产物带 provenance + build +
    # is_current_build 三字段」，P1-6 的 run manifest 必须与此**同源同义**，不得各写一套）。
    # 旧名 `matches_current_build` 已改；语义一字未变（str(gate_build) == str(当前构建)）。
    is_current_build: bool
    superseded: bool
    superseded_by: str | None
    provenance: str
    usable_for: str
    reasons: tuple[str, ...]
    gate_current: dict[str, Any] = field(default_factory=dict)
    # 命中「裁定已核可、实现待落地」时带上 D 的专用标签；其余档为 None。
    pending_impl_label: str | None = None
    # 裁定 31.4：`stale_build_evidence` 的**理由侧**子标签（封闭集合 PROVENANCE_KINDS）；
    # 其余档为 None（可用性只看 usable_for，子标签只解释「为什么不可用」）。
    provenance_kind: str | None = None
    # 被 inventory() 跨记录改判过的记录留原档名，以便审计（append-only：不改写原判断的依据）。
    regraded_from: str | None = None
    # --- T-B2-20（D→B2 执行单 2026-09-30 §二）：**门禁作用域**的身份，五件 ---
    # `gate_id` = 本次对账**用的**门禁（调用方声明；缺省 = `DEFAULT_GATE_ID` = ACT 冻结基线）；
    # `artifact_gate_id` = 产物**自述或可推断**的门禁（推断不出 = `None`：三值纪律，不猜）；
    # `gate_id_mismatch` = 两者（或门禁现值身份）不一致的**理由串**；`None` = 一致或无从判定；
    # `gate_identity_fingerprint` = 门禁作用域的身份串（`<gate_id>@<身份面指纹>`），
    #   跨门禁**构造上不可能相等**（见 `gate_identity_fingerprint()` 的注释）。
    gate_id: str = DEFAULT_GATE_ID
    gate_id_source: str = "default_not_declared_by_caller"
    artifact_gate_id: str | None = None
    artifact_gate_id_source: str | None = None
    gate_id_mismatch: str | None = None
    gate_identity_fingerprint: str | None = None
    # `artifact_gate_candidates` = 归属标记命中的**全部门禁**（实测形态，不是结论）；
    # `artifact_gate_ambiguous` = 命中 ≥2 个 ⇒ 归属不可判（与「0 命中 = 未测」分开记，
    # 因为后果不同：不可判必须拒收）。产物自己写了 `gate_id` 字段时以它为准 ⇒ 不算不可判。
    artifact_gate_candidates: tuple[str, ...] = ()
    artifact_gate_ambiguous: bool = False

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["missing_fields"] = list(self.missing_fields)
        out["reasons"] = list(self.reasons)
        out["artifact_gate_candidates"] = list(self.artifact_gate_candidates)
        return out


def is_arm_verdict(row: dict[str, Any]) -> bool:
    """这一行是**逐臂裁定**，还是关于裁定的聚合报告？

    判据：聚合报告（阈值敏感度、多臂汇总）带 `arms` / `thresholds` 而**没有** `accounts`；
    逐臂裁定一定带 `accounts`（三套账）。旧版判据的逐臂裁定可能没有 `measurement_valid`
    字段，所以不能拿「有没有该字段」当判别式 —— 那会把旧裁定误判成聚合报告。
    """
    if "accounts" in row:
        return True
    return not ("arms" in row or "thresholds" in row)


def classify(gate_build: Any, measurement_valid: Any, suspect_truncation: Any,
             current_build: Any, *, validity_declared: bool = True,
             arm_verdict: bool = True, validity_class: Any = None,
             input_contract_status: Any = None,
             gate_id_mismatch: str | None = None,
             gate_id_ambiguous: bool = False) -> tuple[str, tuple[str, ...]]:
    """有效性分级：**纯函数**，互斥优先级，便于单测与变异自检。

    优先级（从高到低）：**跨门禁** > **门禁归属不可判** > 不是裁定 > 身份/有效性声明缺失
    > **裁定已核可但实现待落地**
    > 测量不可信 > 构建过期 > 可当事实。

    顺序不是随意的：
    - `跨门禁`（T-B2-20 / D→B2 §二）排在**最高**：一旦对账用的门禁现值与产物所属门禁不是
    - 同一个，后面每一档的判断都失去参照系 ——「是不是逐臂裁定」「构建新旧」「测量有没有效」
    - 全是**相对某个判据体系**说的。让它掉进 `not_a_verdict` 或 `stale_build_evidence`
    - 都会说谎：前者把"我用错了门禁"说成"这不是裁定"，后者把两个判据体系说成一条时间线。
    - 聚合报告根本不是「一次测量」，把它当裁定会凭空造出一个不存在的臂；
    - 连判据身份都说不清（或有效性从未声明）的裁定，讨论「测量有没有效」没有意义，
      也**不能**反过来说它 INVALID —— 那是替上游下一个它没下过的结论；
    - 「裁定已核可、实现待落地」排在「测量不可信」之前：这一档要处理的正是
      *门禁判 `measurement_valid=False`、而监管层已会签免罪* 的冲突。若让它掉进
      `invalid_measurement`，等于让**未被实现承载**的门禁结论单方面压倒已会签的裁定
      （增补六 裁定 17.7 明写两种表述都不得采用）。它排在「身份缺失」之后：
      连判据身份都说不清时，无从判断「实现待落地」是相对哪一版实现说的；
    - 测量被上游判为不可信的裁定，即使出自当前构建也不能当事实。
    """
    if gate_id_mismatch:
        return USABLE_WRONG_GATE, (f"跨门禁身份不得互认：{gate_id_mismatch}",)
    if gate_id_ambiguous:
        # 归属不可判**不是**跨门禁（跨门禁要说得出它属于谁），也不是「身份缺失」
        # （身份键在，只是两个门禁的专属标记同时命中）⇒ 落 `unidentified_build`：
        # 这一档的语义正是「连『出自哪一版判据体系』都说不清」。不新造档位（裁定 31.4：
        # 词汇表扩项须先过 D），但**必须拒收**：若让它按调用方声明的门禁走下去，
        # 就等于给「伪造构建号 + 混形状」开一条准入路径（MG5 的 b2）。
        return (USABLE_UNIDENTIFIED,
                ("门禁归属不可判：产物同时命中 ≥2 个门禁的**专属**归属标记"
                 "（candidates 见记录字段 `artifact_gate_candidates`）⇒ 三值纪律下记 "
                 "not_measured、不猜它属于谁；但**不得**因此按调用方声明的门禁当物理事实 "
                 "⇒ 拒收。要消除这一档，得由上游在产物里写明 `gate_id` 字段（已作为知会记进日报）",))
    if not arm_verdict:
        return USABLE_NOT_A_VERDICT, ("聚合/敏感度报告：带 arms/thresholds、无 accounts，不是逐臂裁定",)
    if gate_build in (None, "", "<unknown>"):
        return USABLE_UNIDENTIFIED, ("gate_build 缺失：无法判定出自哪一版判据",)
    if not validity_declared:
        return USABLE_UNIDENTIFIED, ("measurement_valid 字段缺失：有效性未声明（旧判据口径），不得当事实",)
    # 截断当失败是**终局语义**问题；裁定 10 的探针免罪针对的是输入契约 / blown 那一维，
    # 覆盖不到终局语义 ⇒ suspect 优先。否则这一档会变成「免罪万能牌」：
    # 任何被权威表记过免罪的臂，连终局语义造假的裁定都能被抬出 invalid_measurement。
    if suspect_truncation is True:
        return (USABLE_INVALID_MEASUREMENT,
                ("terminal_semantics 怀疑把截断标成了失败（裁定 10 的探针免罪只针对"
                 "输入契约 / blown，覆盖不到终局语义，故不落入 pending_impl）",))
    if is_pending_impl_exoneration(validity_class, input_contract_status):
        return (USABLE_PENDING_IMPL,
                (f"权威表 validity_class={AUTHORITY_EXONERATED}（裁定 10 五条准入已会签），"
                 f"但门禁 input_contract.status={input_contract_status!r} 未承载免罪 "
                 f"（!= {GATE_EXONERATED}）⇒ 裁定已核可、实现待落地。"
                 f"过渡期标签 {PENDING_IMPL_LABEL}：不得写「已免罪」，也不得写「能力未知」",
                 LABEL_RETIREMENT_NOTE))
    reasons: list[str] = []
    if measurement_valid is not True:
        reasons.append(f"measurement_valid={measurement_valid!r}（不是 True）")
    if suspect_truncation is True:
        reasons.append("terminal_semantics 怀疑把截断标成了失败")
    if reasons:
        return USABLE_INVALID_MEASUREMENT, tuple(reasons)
    if str(gate_build) != str(current_build):
        return (USABLE_STALE_BUILD,
                (f"gate_build={gate_build} 不是当前构建 {current_build}（旧判据口径）",))
    return USABLE_PHYSICAL_FACT, ()


def is_pending_impl_exoneration(validity_class: Any, input_contract_status: Any) -> bool:
    """权威层已记免罪、门禁层没产出免罪 ⇒ 「裁定已核可、实现待落地」。

    **只认这一个方向**（增补六 §8-C3 点名的那一个）。反方向（门禁 `probe_exonerated`
    而权威表不是 `VALID_probe_exonerated`）**不在本函数职责内**：裁定 18 已判
    stdfloor 臂的门禁免罪是**对的**、是权威表滞后，那不是实现缺口。反方向只计数上报
    （`inventory()` 的 `exoneration_disagreement`），不改分级 —— C 不替 A/B 裁定谁对。
    """
    return (str(validity_class) == AUTHORITY_EXONERATED
            and str(input_contract_status) != GATE_EXONERATED)


def parse_verdict(path: str | Path, *, current: dict[str, Any] | None = None,
                  arm_index: dict[str, Any] | None = None,
                  gate_id: str | None = None) -> list[VerdictIdentity]:
    """解析一份裁定文件（可能含多臂），返回逐臂的身份记录。

    给了 `arm_index`（`load_arm_index()` 的产物）就把 A 权威表里的 `validity_class` /
    `blowup_threshold_source` / `labels_reportable` / `superseded_by` 一并绑定；
    匹配不上就如实记 `absent_from_arms_summary`，**不自己推导** validity。

    T-B2-20（D→B2 §二）：`gate_id` 声明"这份产物该拿哪个门禁的现值来对账"，缺省 =
    `DEFAULT_GATE_ID`（ACT 冻结基线）⇒ 既有调用方行为逐字不变。产物自述/可推断的门禁
    与它不一致 ⇒ 记录降级为 `wrong_gate_identity`（**必须红**，跨门禁身份串不得互认）。
    """
    path = Path(path)
    if not path.exists():
        raise VerdictIdentityError(f"裁定文件不存在: {path}")
    requested_gate = gate_id or DEFAULT_GATE_ID
    if requested_gate not in GATE_MODULE_PATHS:
        raise VerdictIdentityError(
            f"未知 gate_id={requested_gate!r}；已登记的是 {known_gate_ids()}"
            "（不猜、不落到默认门禁）")
    current = current or current_gate_identity(requested_gate)
    gate_id_source = "caller_declared" if gate_id else "default_not_declared_by_caller"
    sha = content_sha256(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise VerdictIdentityError(f"{path}: JSON 解析失败（{type(exc).__name__}: {exc}）") from exc
    rel = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
    # 顶层推断（单件产物，如 C2 的 `gate_verdict.json`）；逐行推断在下面（ACT 的多臂裁定）。
    payload_candidates = infer_gate_id_candidates(payload)
    payload_gate = payload_candidates[0] if len(payload_candidates) == 1 else None

    out: list[VerdictIdentity] = []
    for row in _unwrap(payload, rel):
        declared_gate = row.get("gate_id") if isinstance(row.get("gate_id"), str) else None
        row_candidates = infer_gate_id_candidates(row)
        # 逐行优先（ACT 的多臂裁定每行自带归属键），行上没有标记才回落到顶层（C2 的单件聚合产物）。
        candidates = row_candidates or payload_candidates
        inferred_gate = candidates[0] if len(candidates) == 1 else None
        artifact_gate = declared_gate or inferred_gate
        artifact_gate_source = ("artifact_field:gate_id" if declared_gate
                                else ("artifact_marker" if inferred_gate else None))
        # **归属不可判**（≥2 个门禁的专属标记同时命中）与**归属未测**（0 命中）必须分开：
        # 前者不得报「一致」（那正是 MG5 的洞），后者按三值纪律不得报「不一致」。
        # 产物自己写了 `gate_id` 字段 ⇒ 上游已声明归属，本层不推断、也不算不可判。
        ambiguous = bool(not declared_gate and len(candidates) > 1)
        mismatch = (None if ambiguous
                    else gate_id_mismatch_reason(requested_gate, current, artifact_gate))
        eval_file = row.get("file")
        eval_path = ROOT / eval_file if isinstance(eval_file, str) and eval_file else None
        accounts = row.get("accounts") if isinstance(row.get("accounts"), dict) else {}
        indep = accounts.get("policy_independent") if isinstance(accounts.get("policy_independent"),
                                                                 dict) else {}
        terminal = row.get("terminal_semantics") if isinstance(row.get("terminal_semantics"),
                                                              dict) else {}
        contract = row.get("input_contract") if isinstance(row.get("input_contract"), dict) else {}
        gate_build = row.get("gate_build")
        arm_verdict = is_arm_verdict(row)
        validity_declared = "measurement_valid" in row
        arm = Path(eval_file).stem if isinstance(eval_file, str) and eval_file else path.stem
        # 三键之二/三（validity_class、blowup_threshold_source）来自 A 的权威表，不是 C 算的。
        row_arm = _lookup_arm(arm_index, eval_file, arm)
        summary_sha = (arm_index or {}).get("sha256")
        if row_arm is None:
            (validity_class, validity_reason, blowup_src, labels_rep, upstream_sup,
             arm_field_class) = (None,) * 6
            validity_source = ("absent_from_arms_summary" if (arm_index or {}).get("available")
                               else "arms_summary_not_loaded")
        else:
            validity_class = row_arm.get("validity_class")
            validity_reason = row_arm.get("validity_reason")
            blowup_src = row_arm.get("blowup_threshold_source")
            labels_rep = row_arm.get("labels_reportable")
            upstream_sup = row_arm.get("superseded_by")
            # A 的 field_class 是**权威裁定那一份**的（可能来自 blindfix 重测），
            # 与本文件自己的 field_class 不是一回事：留档的 partial 裁定 join 到重测行时，
            # 两个值会不同。分列两键，谁也别冒充谁。
            arm_field_class = row_arm.get("field_class")
            validity_source = f"arms_summary.json@{str(summary_sha)[:12]}"
        # 分级必须在 join 之后：`pending_impl_ruling_approved` 这一档要同时看
        # 权威层的 validity_class 与门禁层的 input_contract.status（增补六 §8-C3）。
        ic_status = contract.get("status")
        usable, reasons = classify(gate_build, row.get("measurement_valid"),
                                   terminal.get("suspect_truncation_labeled_as_failure"),
                                   current.get("gate_build"),
                                   validity_declared=validity_declared,
                                   arm_verdict=arm_verdict,
                                   validity_class=validity_class,
                                   input_contract_status=ic_status,
                                   gate_id_mismatch=mismatch,
                                   gate_id_ambiguous=ambiguous)
        out.append(VerdictIdentity(
            source_path=rel, source_sha256=sha, arm=arm,
            eval_file=eval_file,
            eval_sha256=(content_sha256(eval_path)
                         if eval_path is not None and eval_path.exists() else None),
            gate_version=row.get("gate_version"), gate_build=gate_build,
            gate_spec_sha256=row.get("gate_spec_sha256"), gate_spec_doc=row.get("gate_spec_doc"),
            measurement_valid=row.get("measurement_valid"),
            measurement_validity_declared="measurement_valid" in row,
            field_class=row.get("field_class"),
            missing_fields=tuple(row.get("missing_fields") or ()),
            gate_pass=row.get("gate_pass"), gate_reason=row.get("gate_reason"),
            accounts={name: accounts.get(name) for name in ACCOUNTS},
            buckets={name: indep.get(name) for name in BUCKETS},
            input_contract_status=contract.get("status"),
            suspect_truncation_as_failure=terminal.get("suspect_truncation_labeled_as_failure"),
            validity_class=validity_class, validity_reason=validity_reason,
            arm_field_class=arm_field_class,
            validity_source=validity_source, blowup_threshold_source=blowup_src,
            labels_reportable=labels_rep, upstream_superseded_by=upstream_sup,
            arm_summary_sha256=summary_sha,
            arm_verdict=arm_verdict,
            is_current_build=str(gate_build) == str(current.get("gate_build")),
            superseded=False, superseded_by=None, provenance="",
            usable_for=usable, reasons=reasons, gate_current=dict(current),
            pending_impl_label=(PENDING_IMPL_LABEL if usable == USABLE_PENDING_IMPL else None),
            gate_id=requested_gate, gate_id_source=gate_id_source,
            artifact_gate_id=artifact_gate, artifact_gate_id_source=artifact_gate_source,
            gate_id_mismatch=mismatch,
            gate_identity_fingerprint=current.get("gate_identity_fingerprint"),
            artifact_gate_candidates=candidates, artifact_gate_ambiguous=ambiguous))
    return out


def _lookup_arm(arm_index: dict[str, Any] | None, eval_file: Any, arm: str) -> dict[str, Any] | None:
    """在 A 的权威表索引里找这条臂：先按评测文件路径，再按 basename，最后按臂名。"""
    if not arm_index or not arm_index.get("index"):
        return None
    index = arm_index["index"]
    for key in (eval_file, Path(eval_file).name if isinstance(eval_file, str) else None,
                arm, arm.replace("official_act_truth20_", "", 1)):
        if isinstance(key, str) and key in index:
            return index[key]
    return None


def _distribution(values: Iterable[Any]) -> dict[str, int]:
    dist: dict[str, int] = {}
    for v in values:
        dist[str(v)] = dist.get(str(v), 0) + 1
    return dict(sorted(dist.items(), key=lambda kv: (-kv[1], kv[0])))


def classify_provenance_kind(*, usable_for: str, provenance: str = "", source_path: str = "",
                             superseded: bool = False, gate_pass: Any = None,
                             input_contract_status: Any = None) -> str | None:
    """`stale_build_evidence` 的**理由侧**子标签（裁定 31.4）。记录级**纯函数**、封闭集合。

    只给 stale 这一档打子标签：其余档的「为什么」已经由 `usable_for` 自己说清了
    （`invalid_measurement` = 测量不可信、`unidentified_build` = 连构建都说不清），
    再挂子标签就是 D 不采纯 (c) 时点名的那种词汇表膨胀。

    优先级不是口味，是**信息量**排序：

    1. `frozen_prereg_anchor` —— 出自预登记钉死旧版本的目录（`regate_v121_pinned/`）。
       它「旧」是**设计使然**；不看这条就会把冻结锚点读成「忘了重判」。
    2. `deliberate_rejection_probe` —— 出自探针目录**且这份产物确实被拒**
       （`gate_pass` 非 True，或 `input_contract.status == violated`）。**必须同时看到被拒**：
       同一个目录里还有正向对照（`gate_C1_control_stdfloor.json`：ic=probe_exonerated、
       gate_pass=true），只按目录判会把「故意被接受」写成「故意被拒」——
       一个说谎的标签比没标签更坏（裁定 31.4 不采 (a) 的同一个理由）。
    3. `superseded_rerun` —— 同臂已有现构建重判取代它。
    4. `ordinary_stale` —— 默认：单纯旧构建留档。
    """
    if usable_for != USABLE_STALE_BUILD:
        return None
    where = f"{provenance or ''}|{source_path or ''}"
    if any(marker in where for marker in FROZEN_PREREG_ANCHOR_DIRS):
        return PROVENANCE_FROZEN_PREREG_ANCHOR
    if any(marker in where for marker in DELIBERATE_REJECTION_PROBE_DIRS):
        refused = gate_pass is not True or str(input_contract_status) == DELIBERATE_REJECTION_IC
        if refused:
            return PROVENANCE_DELIBERATE_REJECTION_PROBE
    if superseded:
        return PROVENANCE_SUPERSEDED_RERUN
    return PROVENANCE_ORDINARY_STALE


def artifact_identity(record: "VerdictIdentity") -> dict[str, Any]:
    """裁定 31.3 要求每份产物带的字段（provenance + build + is_current_build）+ 内容身份。

    **单一来源**：免罪对账、清单摘要、P1-6 的逐臂 run manifest 一律从这里取，
    不得各写一套（D 派工单 P1-6：三字段要与 P0-2「同源同义」）。
    """
    return {"source_path": record.source_path,
            "provenance": record.provenance or "<unknown>",
            "gate_build": record.gate_build,
            "gate_version": record.gate_version,
            "is_current_build": bool(record.is_current_build),
            "source_sha256": record.source_sha256,
            "arm": record.arm,
            "eval_file": record.eval_file,
            "input_contract_status": record.input_contract_status,
            "measurement_valid": record.measurement_valid,
            "usable_for": record.usable_for,
            # T-B2-20（D→B2 §二）：门禁作用域的身份。**单一来源**原则不变：下游要认门禁，
            # 一律从这里取，不得自己再拼一个 gate_id（拼第二份就是第二套判据）。
            "gate_id": record.gate_id,
            "artifact_gate_id": record.artifact_gate_id,
            "gate_id_mismatch": record.gate_id_mismatch,
            "gate_identity_fingerprint": record.gate_identity_fingerprint,
            "artifact_gate_candidates": list(record.artifact_gate_candidates),
            "artifact_gate_ambiguous": bool(record.artifact_gate_ambiguous)}


# --- P1-5：裁定 → 账本/发布包的准入闸（裁定 29.1「引用锚在 build 轴」在 C 侧的落点）---

DIRECTION_IDENTITY_FIELDS = ("gate_version", "gate_build", "gate_spec_sha256", "verdict_sha256",
                             "measurement_valid", "usable_for", "provenance_kind",
                             "is_current_build", "superseded_by", "regraded_from",
                             "gate_id", "gate_identity_fingerprint")

ADMISSION_RULE = (
    "准入闸：**只有 `usable_for == physical_fact` 且 `gate_build` 等于门禁现值**的裁定，"
    "才准被当成物理事实写进账本 / 进发布包。其余各档一律**拒收并回显理由**（不是 warn、"
    "不是静默降级）；要留档就写成**带身份的事件**，不进事实表。"
    "**T-B2-20（D→B2 执行单 2026-09-30 §二）追加两条**：① 对账必须**门禁作用域**内进行 —— "
    "记录的 `gate_id` 与门禁现值的 `gate_id` 不是同一个 ⇒ 拒收（`wrong_gate_identity`，"
    "跨门禁身份串不得互认）；② 现值默认按**记录自己的** `gate_id` 取（各自查各自），"
    "且 `gate_build` 对上之后还要比 `gate_identity_fingerprint`（π₀.₅ 的判据本体在 "
    "`harness/norm_contract.py`，只比闸脚本的构建号会在判据变动而闸壳不动时放过）。"
    "**MG5 复判后追加第三条**：③ 产物同时命中 ≥2 个门禁的**专属**归属标记 ⇒ 归属不可判 "
    "⇒ 拒收（`unidentified_build`）。这一条堵的是「构建号伪造成现值 + 形状混着写」的准入路径："
    "归属推断按三值纪律回 `None`（不猜），但 `None` **不得**被读成「没有不一致」——"
    "「未测」与「不可判」分开记，后者拒收。通用裁定形状键（`GENERIC_VERDICT_SHAPE_KEYS`）"
    "不是归属证据、不进标记表，否则每一份 π₀.₅ 逐臂产物都会变成不可判（系统性假红）。"
    "**预先写明的后果**（D 派工单「与 B §5 的交点」）：B 的 v1.6 落地会升 `GATE_BUILD`，"
    "届时现存的 48 条 `physical_fact` 会**整批**变成「与门禁现值不符」⇒ 本闸全部拒收、"
    "清单里 `physical_fact` 由 48 → 0。**那是正确行为，不是回归红点**；"
    "要在 v1.6 上重新出裁定，而不是把闸放宽。")


def _field(obj: Any, name: str, default: Any = None) -> Any:
    """`VerdictIdentity` 与等价 dict 都能读（账本侧不该被迫 import 裁定层的类型）。"""
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def direction_identity(record: Any) -> dict[str, Any]:
    """把一条裁定翻成 `DirectionScore` / 账本事件要带的**身份字段**。

    `gate_build` / `is_current_build` / `usable_for` / `verdict_sha256` 全部取自
    `artifact_identity()` —— **同源同义，不另写一套**（D 派工单 P1-6 的硬要求）。
    身份字段是**字段**，不是注释：缺了它，下游就无从判断这个数字出自哪一版判据。
    """
    ident = artifact_identity(record) if not isinstance(record, Mapping) else dict(record)
    return {"gate_version": ident.get("gate_version", _field(record, "gate_version")),
            "gate_build": ident.get("gate_build", _field(record, "gate_build")),
            "gate_spec_sha256": _field(record, "gate_spec_sha256"),
            "verdict_sha256": ident.get("source_sha256", _field(record, "source_sha256")),
            "measurement_valid": ident.get("measurement_valid",
                                           _field(record, "measurement_valid")),
            "usable_for": ident.get("usable_for", _field(record, "usable_for")),
            "provenance_kind": _field(record, "provenance_kind"),
            "is_current_build": bool(ident.get("is_current_build",
                                               _field(record, "is_current_build"))),
            "superseded_by": _field(record, "superseded_by"),
            "regraded_from": _field(record, "regraded_from"),
            "gate_id": ident.get("gate_id", _field(record, "gate_id", DEFAULT_GATE_ID)),
            "artifact_gate_id": _field(record, "artifact_gate_id"),
            "gate_id_mismatch": _field(record, "gate_id_mismatch"),
            "artifact_gate_ambiguous": bool(_field(record, "artifact_gate_ambiguous", False)),
            "gate_identity_fingerprint": ident.get(
                "gate_identity_fingerprint", _field(record, "gate_identity_fingerprint"))}


def admit_as_physical_fact(record: Any, *, current: dict[str, Any] | None = None,
                           require_current_build: bool = True,
                           refresh: bool = False) -> dict[str, Any]:
    """跑准入闸，**返回判定**（不抛错）：`admitted` + `refusal_reasons` + 完整身份。

    返回而不是抛错，是为了让「拒收」这件事本身**可留档**：账本侧可以把 refusal 连同身份
    写成一条事件（留档、可查、不进事实表），而不是只留一个栈。要严格拒收的调用方
    （`harness/ledger.ingest_runtime_result`、`registry/release_bundle.build_bundle`）
    自己按 `admitted` 抛错。

    `require_current_build=True`（默认）⇒ `gate_build` 与门禁现值不符就是**拒收**，不是 warn。
    注意这里比的是**调用时的门禁现值**（`current_gate_identity()`），不是记录被解析时
    存下的那份 `gate_current` —— 判据在脚下移动过就必须重新对表，这正是 v1.6 那一刀要能落下来的原因。
    """
    identity = direction_identity(record)
    # T-B2-20（D→B2 §二）：**各自查各自** —— 调用方没给现值时，按记录自己的 `gate_id` 去取
    # 那个门禁的现值（不是默认门禁的）。调用方给了别的门禁的现值 ⇒ 下面的跨门禁检查会拒收。
    rec_gate_id = identity.get("gate_id") or _field(record, "gate_id") or DEFAULT_GATE_ID
    gate_now = (current if current is not None
                else current_gate_identity(rec_gate_id, refresh=refresh))
    expect_build = gate_now.get("gate_build")
    reasons: list[str] = []
    gate_now_id = gate_now.get("gate_id") or DEFAULT_GATE_ID
    if str(rec_gate_id) != str(gate_now_id):
        reasons.append(f"跨门禁：记录的 gate_id={rec_gate_id!r}，而用于对账的门禁现值是 "
                       f"gate_id={gate_now_id!r}（fingerprint={gate_now.get('gate_identity_fingerprint')}）"
                       "⇒ 身份串不得互认（D→B2 §二 / T-B2-20）")
    mm = identity.get("gate_id_mismatch") or _field(record, "gate_id_mismatch")
    if mm:
        reasons.append(f"gate_id_mismatch：{mm}")
    # 归属不可判 ⇒ **本闸自己再判一次**，不只依赖分级结果（纵深防御：`classify` 已把它落成
    # `unidentified_build`，但准入闸是最后一道，不能假设分级永远带着这一档走过来 ——
    # 记录可能是从盘上反序列化的 dict，也可能出自别的分级路径）。
    if identity.get("artifact_gate_ambiguous") or _field(record, "artifact_gate_ambiguous", False):
        cands = list(_field(record, "artifact_gate_candidates") or ())
        reasons.append("门禁归属不可判：产物同时命中 ≥2 个门禁的专属归属标记 "
                       f"candidates={cands} ⇒ 不猜它属于谁，也不准入"
                       "（要准入就得让上游在产物里写明 `gate_id` 字段）")

    usable = identity.get("usable_for")
    if usable != USABLE_PHYSICAL_FACT:
        detail = f"usable_for={usable!r}（本闸只吃 {USABLE_PHYSICAL_FACT!r}）"
        if identity.get("provenance_kind"):
            detail += f"；provenance_kind={identity['provenance_kind']}"
        if identity.get("regraded_from"):
            detail += f"；regraded_from={identity['regraded_from']}"
        reasons.append(detail)
    if not identity.get("gate_build"):
        reasons.append("gate_build 缺失 ⇒ 连「出自哪一版判据」都说不清（unidentified）")
    if identity.get("superseded_by"):
        reasons.append(f"已被取代：superseded_by={identity['superseded_by']}")
    if require_current_build and identity.get("gate_build") and expect_build is not None:
        if str(identity["gate_build"]) != str(expect_build):
            reasons.append(f"gate_build={identity['gate_build']} ≠ 门禁现值 {expect_build}"
                           f"（gate_version={identity.get('gate_version')} vs "
                           f"{gate_now.get('gate_version')}）⇒ 拒收，不是 warn")
        elif identity.get("is_current_build") is False:
            reasons.append("记录自带 is_current_build=False，与「gate_build 等于现值」自相矛盾"
                           "（身份字段不自洽 ⇒ 拒收，交回裁定层重解析）")
    # 身份面指纹（`gate_identity_fingerprint`）比 `gate_build` **覆盖面更宽**：π₀.₅ 的判据本体在
    # `harness/norm_contract.py`，只比闸脚本的 `gate_build` 会在判据变动而闸壳不动时**放过**。
    # 只在"构建号已对上"的前提下追加这一条，避免与上面的 stale 理由重复报同一件事。
    fp_rec = identity.get("gate_identity_fingerprint") or _field(record, "gate_identity_fingerprint")
    fp_now = gate_now.get("gate_identity_fingerprint")
    build_matched = bool(identity.get("gate_build")) and expect_build is not None \
        and str(identity["gate_build"]) == str(expect_build)
    if require_current_build and fp_rec and fp_now and build_matched and str(fp_rec) != str(fp_now):
        reasons.append(f"身份面指纹不符：记录 {fp_rec} ≠ 门禁现值 {fp_now}"
                       f"（gate_id={gate_now_id}）⇒ 判据面里除了闸脚本还有别的件变了"
                       "（π₀.₅ 的判据本体在 harness/norm_contract.py）⇒ 拒收，不是 warn")
    record_reasons = [str(x) for x in (_field(record, "reasons") or ())]
    return {"admitted": not reasons,
            "refusal_reasons": reasons,
            "refusal_reason": "；".join(reasons) or None,
            "identity": identity,
            "gate_current": {"gate_version": gate_now.get("gate_version"),
                             "gate_build": gate_now.get("gate_build"),
                             "gate_spec_sha256": gate_now.get("gate_spec_sha256"),
                             "gate_id": gate_now.get("gate_id"),
                             "gate_identity_fingerprint": gate_now.get("gate_identity_fingerprint")},
            "gate_id": rec_gate_id,
            "gate_id_matches_current": (str(rec_gate_id) == str(gate_now_id)),
            "require_current_build": require_current_build,
            "verdict_reasons": record_reasons,
            "arm": _field(record, "arm"),
            "source_path": _field(record, "source_path"),
            "rule": ADMISSION_RULE}


def authority_exoneration(row: dict[str, Any]) -> dict[str, Any]:
    """A 的权威表里这一臂的**免罪声明**（字段全是 A 落的，C 不推导、不另造判据）。

    两个字段说的是两件事，**任一成立**就算权威侧记了免罪：

    - `validity_class == VALID_probe_exonerated`：这臂的有效性**靠**探针免罪才成立；
    - `ic_status == probe_exonerated`：输入契约那一维被免罪（有效性可能本来就成立）。

    只看前者会把 裁定 18 的 stdfloor 臂报成「门禁免罪、权威没免」的活矛盾 ——
    而它两侧其实一致（权威表 ic_status=probe_exonerated）。裁定 31.3 抓的正是这类假红。
    """
    validity_class = row.get("validity_class")
    ic_status = row.get("ic_status")
    return {"arm": row.get("arm"),
            "validity_class": validity_class,
            "ic_status": ic_status,
            "exonerated": (str(validity_class) == AUTHORITY_EXONERATED
                           or str(ic_status) == GATE_EXONERATED),
            "exonerated_by": sorted(filter(None, [
                ("validity_class" if str(validity_class) == AUTHORITY_EXONERATED else None),
                ("ic_status" if str(ic_status) == GATE_EXONERATED else None)])),
            "gate_build": row.get("gate_build"),
            "gate_version": row.get("gate_version"),
            "gate_file": row.get("gate_file"),
            "adjudicated_artifact": row.get("adjudicated_artifact"),
            "superseded_by": row.get("superseded_by")}


def _row_arm_keys(row: dict[str, Any]) -> tuple[str, ...]:
    """权威表一行可能对应到记录里的哪些 `arm` 键（记录侧 arm = 被判决评测文件的 stem）。"""
    keys: list[str] = []
    for field_name in ("file", "authoritative_eval_file"):
        value = row.get(field_name)
        if isinstance(value, str) and value:
            keys.append(Path(value).stem)
    arm = row.get("arm")
    if isinstance(arm, str) and arm:
        keys.append(arm)
    out: list[str] = []
    for k in keys:
        if k not in out:
            out.append(k)
    return tuple(out)


def _match_counterpart(row: dict[str, Any], candidates: Sequence["VerdictIdentity"]
                       ) -> tuple["VerdictIdentity | None", str]:
    """在候选产物里认出**权威表正在对账的那一份**（认不出就如实说认不出，不静默挑一份）。

    优先级：① 权威表自己指的 `gate_file`（A 落的指针，最强证据）；
    ② `adjudicated_artifact`（被判决的评测产物）；③ 该臂只有唯一候选时按臂名认。
    同一臂在现构建下可能有**多份**产物（stdfloor 臂就有 `regate_current/` 与
    `reblown/regate_current/` 两份，判的是 reblow 前后两个不同的评测文件）——
    这时只有权威表的指针能说明它认哪一份；C 自己挑就等于替 A 决定了口径。
    """
    def _hits(predicate) -> list["VerdictIdentity"]:
        return [r for r in candidates if predicate(r)]

    gate_file = row.get("gate_file")
    if isinstance(gate_file, str) and gate_file:
        hits = _hits(lambda r: r.source_path == gate_file
                     or r.source_path.endswith("/" + gate_file))
        if len(hits) == 1:
            return hits[0], "authority_gate_file"
        if len(hits) > 1:
            return None, f"ambiguous_authority_gate_file({len(hits)})"
    adjudicated = row.get("adjudicated_artifact")
    if isinstance(adjudicated, str) and adjudicated:
        hits = _hits(lambda r: r.eval_file == adjudicated
                     or (r.eval_file or "").endswith("/" + adjudicated))
        if len(hits) == 1:
            return hits[0], "authority_adjudicated_artifact"
        if len(hits) > 1:
            return None, f"ambiguous_adjudicated_artifact({len(hits)})"
    if len(candidates) == 1:
        return candidates[0], "arm_name_unique_candidate"
    if not candidates:
        return None, "no_gate_artifact_found"
    return None, f"ambiguous_arm_artifacts({len(candidates)})"


def reconcile_exonerations(records: Sequence["VerdictIdentity"], arm_rows: Sequence[dict[str, Any]],
                           current: dict[str, Any]) -> dict[str, Any]:
    """免罪对账（裁定 31.3）：**只在两侧同为当前构建时**才报 `disagreement`。

    为什么必须按构建收窄：被扫目录里的 gate 侧产物横跨十几个构建（顶层 47 份历史
    `gate_*.json` 最老的是 v1.0 时代、`gate_build` 干脆是 None），而权威表是 v1.5 的表。
    拿 v1.0 的裁定去和 v1.5 的权威表对账，报出来的 "disagreement" 不是活矛盾，
    是**跨构建混算**。收窄之后两个结果都要看得见：

    - 两侧都在当前构建 ⇒ 真可比 ⇒ 不一致就报进 `authority_exonerated_gate_not` /
      `gate_exonerated_authority_not`（**会红**，非恒真见自检的合成反例）；
    - 任一侧不在当前构建 ⇒ 报 `stale_side_not_comparable`（可见、不报警，
      与 B 护栏① 的 `cosign_not_required_arms` 同型），并各自带 authority_build / gate_build。
    """
    current_build = str(current.get("gate_build"))
    by_arm: dict[str, list["VerdictIdentity"]] = {}
    for r in records:
        by_arm.setdefault(r.arm, []).append(r)

    live_compared: list[dict[str, Any]] = []
    stale_side: list[dict[str, Any]] = []
    non_adjudicated: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    fwd: list[str] = []
    rev: list[str] = []

    for row in arm_rows:
        auth = authority_exoneration(row)
        auth_current = str(auth["gate_build"]) == current_build
        cands: list["VerdictIdentity"] = []
        for key in _row_arm_keys(row):
            for r in by_arm.get(key, ()):
                if r not in cands:
                    cands.append(r)
        counterpart, matched_by = _match_counterpart(row, cands)
        if counterpart is None:
            unmatched.append({"arm": auth["arm"], "matched_by": matched_by,
                              "authority": auth, "n_candidates": len(cands),
                              "candidates": [artifact_identity(r) for r in cands]})
        else:
            gate_exo = str(counterpart.input_contract_status) == GATE_EXONERATED
            entry = {"arm": auth["arm"], "matched_by": matched_by,
                     "authority": auth, "gate": artifact_identity(counterpart),
                     "authority_exonerated": bool(auth["exonerated"]),
                     "gate_exonerated": gate_exo}
            if counterpart.is_current_build and auth_current:
                entry["comparable"] = True
                entry["agree"] = bool(auth["exonerated"]) == gate_exo
                if not entry["agree"]:
                    entry["direction"] = ("authority_exonerated_gate_not" if auth["exonerated"]
                                          else "gate_exonerated_authority_not")
                    (fwd if auth["exonerated"] else rev).append(str(auth["arm"]))
                live_compared.append(entry)
            else:
                stale_side.append({**entry, "comparable": False,
                                   "kind": STALE_SIDE_NOT_COMPARABLE,
                                   "authority_build": auth["gate_build"],
                                   "gate_build": counterpart.gate_build,
                                   "why_not_comparable": _not_comparable_reason(
                                       auth_current, counterpart.is_current_build,
                                       auth["gate_build"], counterpart.gate_build, current_build)})
        # 其余候选：不是权威表在认的那一份 ⇒ 不参与对账，但一律可见（不静默丢）。
        for r in cands:
            if counterpart is not None and r.source_path == counterpart.source_path:
                continue
            gate_exo = str(r.input_contract_status) == GATE_EXONERATED
            differs = bool(auth["exonerated"]) != gate_exo
            ident = artifact_identity(r)
            if r.is_current_build:
                if differs:
                    non_adjudicated.append({
                        "arm": auth["arm"], "authority": auth, "gate": ident,
                        "gate_exonerated": gate_exo,
                        "why_excluded": ("现构建产物，但**不是**权威表指定对账的那一份"
                                         f"（gate_file={auth['gate_file']!r}）：它判的是同臂另一个"
                                         "评测产物（如 reblow 前后两份）。权威表没对它下过结论，"
                                         "所以不算「权威 vs 门禁」的矛盾；列在这里只为可见。")})
            elif differs:
                stale_side.append({"arm": auth["arm"], "matched_by": "same_arm_historical_artifact",
                                   "authority": auth, "gate": ident, "comparable": False,
                                   "kind": STALE_SIDE_NOT_COMPARABLE,
                                   "authority_exonerated": bool(auth["exonerated"]),
                                   "gate_exonerated": gate_exo,
                                   "direction": ("authority_exonerated_gate_not"
                                                 if auth["exonerated"]
                                                 else "gate_exonerated_authority_not"),
                                   "authority_build": auth["gate_build"],
                                   "gate_build": r.gate_build,
                                   "why_not_comparable": _not_comparable_reason(
                                       auth_current, False, auth["gate_build"], r.gate_build,
                                       current_build)})

    top_level = [r for r in records if (r.provenance or "<unknown>") == "<top-level>"]
    return {
        "scope": RECONCILE_SCOPE_RULE,
        "current_build": current_build,
        "authority_side_rule": ("权威侧的免罪取 A 表自己的两个字段（validity_class / ic_status），"
                                "任一成立即算已记免罪；C 不推导、不加第三个判据。"),
        "authority_exonerated_gate_not": sorted(set(fwd)),
        "gate_exonerated_authority_not": sorted(set(rev)),
        "n_live_compared": len(live_compared),
        "live_compared": live_compared,
        "live_all_agree": all(e["agree"] for e in live_compared) if live_compared else None,
        STALE_SIDE_NOT_COMPARABLE: stale_side,
        "n_stale_side_not_comparable": len(stale_side),
        "current_build_non_adjudicated": non_adjudicated,
        "authority_row_without_counterpart": unmatched,
        "red_condition": ("两个方向列表非空 = 真的活矛盾（两侧同为当前构建而免罪不一致）。"
                          "本轮真清单两侧为空**不是**因为判据恒空：合成反例"
                          "（scripts/c_selfcheck_verdict_identity.py::case_reconciliation_*）"
                          "证明它红得起来。"),
        "historical_gate_artifact_ownership": {
            "what": "被扫目录**顶层**（provenance=`<top-level>`）的历史 gate_*.json",
            "n_records": len(top_level),
            "n_files": len({r.source_path for r in top_level}),
            "build_distribution": _distribution(r.gate_build for r in top_level),
            "gate_version_distribution": _distribution(r.gate_version for r in top_level),
            "n_at_current_build": sum(1 for r in top_level if r.is_current_build),
            "owner": ("A 线的产物目录（`runs/infra/lerobot_act_env_20260928/` 由 A 写）。"
                      "C 只读：不新建、不改写、不删（护栏 8 / 裁定 21）。"),
            "status": ("**历史留档，设计如此**：现构建的逐臂重判由 A 落在 `regate_current/`"
                       "（+ `blindfix/`、`reblown/` 两个子树），v1.2.1 锚点钉在 "
                       "`regate_v121_pinned/`。顶层这批不随之改写（内容寻址 + 只读上游）。"),
            "participates_in_current_reconciliation": False,
            "reading_rule": ("看到顶层产物的 ic_status / measurement_valid 与权威表不一致，"
                             "**先查 gate_build**：不是当前构建 ⇒ 属 "
                             f"{STALE_SIDE_NOT_COMPARABLE}，不是活矛盾（裁定 31.3）。"),
        },
    }


def _not_comparable_reason(authority_current: bool, gate_current: bool, authority_build: Any,
                           gate_build: Any, current_build: str) -> str:
    if not authority_current and not gate_current:
        sides = "两侧都不在当前构建"
    elif not authority_current:
        sides = "权威侧不在当前构建"
    else:
        sides = "门禁侧不在当前构建"
    return (f"{sides}（authority_build={authority_build}、gate_build={gate_build}、"
            f"当前构建={current_build}）⇒ 不可比，按 {STALE_SIDE_NOT_COMPARABLE} 上报，"
            "不当活矛盾（裁定 31.3）。")


def regrade_pending_impl(records: Sequence["VerdictIdentity"], current: dict[str, Any]
                         ) -> tuple[list["VerdictIdentity"], dict[str, Any]]:
    """裁定 31.4 的**跨记录**改判：本档的激活条件收窄。

    收窄后的激活条件：**该臂在当前构建下没有任何承载免罪的产物**。已有承载产物 ⇒
    这份记录只是旧构建留档（它的 `violated` 是探针的预期结果 / 锚点的设计使然），
    转 `stale_build_evidence` + `provenance_kind` 子标签 + `regraded_from` 审计字段。

    这一段**只能**放在 `inventory()` 这一侧（本函数由它调）：`parse_verdict` / `classify`
    是记录级纯函数，碰不到「同臂还有别的产物」这个事实 —— D 批准的分层正是这个意思
    （纯函数不碰跨记录状态，裁定 21「判据单一来源」在 C 侧的对应物）。

    改判**不动可用性语义**：两档都不能当现构建证据，所以 `physical_fact` 一条不变。
    """
    current_build = str(current.get("gate_build"))
    carrying_arms = {r.arm for r in records
                     if str(r.gate_build) == current_build
                     and str(r.input_contract_status) == GATE_EXONERATED}
    out: list["VerdictIdentity"] = []
    regraded: list[dict[str, Any]] = []
    for r in records:
        if r.usable_for == USABLE_PENDING_IMPL and r.arm in carrying_arms:
            kind = classify_provenance_kind(
                usable_for=USABLE_STALE_BUILD, provenance=r.provenance,
                source_path=r.source_path, superseded=r.superseded,
                gate_pass=r.gate_pass, input_contract_status=r.input_contract_status)
            reasons = list(r.reasons) + [
                f"{REGRADE_RULING_31_4}",
                (f"改判依据（跨记录）：该臂在**当前构建** {current_build} 下已有承载免罪的产物"
                 f"（input_contract.status={GATE_EXONERATED}）⇒ {PENDING_IMPL_ACTIVATION_RULE}"),
                (f"本条来源性质 provenance_kind={kind}（封闭集合 {list(PROVENANCE_KINDS)}）："
                 "可用性只看 usable_for，为什么不可用看这个子标签。"),
                ("注意：按 classify 的记录级优先级，这条本会落 invalid_measurement"
                 "（measurement_valid 非 True）；裁定 31.4 判的是 stale_build_evidence —— "
                 "它的 violated 是探针/锚点的**设计结果**，不是测量事故。原判断留在 regraded_from。"),
            ]
            out.append(_rebuild(r, usable_for=USABLE_STALE_BUILD, provenance_kind=kind,
                                regraded_from=USABLE_PENDING_IMPL, pending_impl_label=None,
                                reasons=reasons))
            regraded.append({"source_path": r.source_path, "arm": r.arm,
                             "provenance": r.provenance or "<unknown>",
                             "gate_build": r.gate_build, "gate_version": r.gate_version,
                             "is_current_build": bool(r.is_current_build),
                             "source_sha256": r.source_sha256,
                             "regraded_from": USABLE_PENDING_IMPL,
                             "regraded_to": USABLE_STALE_BUILD,
                             "provenance_kind": kind})
        else:
            out.append(r)
    return out, {"regraded": regraded, "n_regraded": len(regraded),
                 "carrying_arms_at_current_build": sorted(carrying_arms),
                 "carrying_artifact_rule": CARRYING_ARTIFACT_RULE,
                 "activation_rule": PENDING_IMPL_ACTIVATION_RULE}


def _rebuild(record: "VerdictIdentity", **changes: Any) -> "VerdictIdentity":
    """frozen dataclass 的「改几个字段重造一份」（原记录不改写，append-only 的同一精神）。"""
    payload = asdict(record)
    payload["missing_fields"] = list(record.missing_fields)
    payload["reasons"] = list(record.reasons)
    payload.update(changes)
    return VerdictIdentity(**payload)


def inventory(paths: Sequence[str | Path], *, current: dict[str, Any] | None = None,
              root_label: str = "", root: str | Path | None = None,
              arm_index: dict[str, Any] | None = None,
              collect: list["VerdictIdentity"] | None = None,
              gate_id: str | None = None) -> dict[str, Any]:
    """扫一批裁定文件，产出「身份 + 有效性 + 取代关系」的清单。

    取代关系（`superseded_by`）不是猜的：**同一被判决的评测文件**（`eval_file`）如果同时存在
    旧构建与当前构建的裁定，当前构建那份就取代旧的那份；没有当前构建版本的，旧裁定只标
    `stale_build_evidence`，`superseded_by` 保持 `None`（意思是「还没有新判据重判过它」，
    而不是「它仍然有效」）。

    给了 `root` 就按**来源分层**（`provenance`）统计：同一目录树下既有原始留档裁定，也有
    A 线重判产物（`regate_current/`）与归档（`superseded_gate_v1.0/`），把它们混在一个分布里
    会看不出「裸 ingest 顶层 `gate_strict_*.json` 到底有多少条能当事实」。
    """
    current = current or current_gate_identity(gate_id or DEFAULT_GATE_ID)
    records: list[VerdictIdentity] = []
    errors: list[dict[str, str]] = []
    for p in paths:
        try:
            records.extend(parse_verdict(p, current=current, arm_index=arm_index,
                                         gate_id=(gate_id or current.get("gate_id"))))
        except VerdictIdentityError as exc:
            errors.append({"path": str(p), "error": str(exc)})

    by_arm: dict[str, list[VerdictIdentity]] = {}
    for r in records:
        by_arm.setdefault(r.arm, []).append(r)

    superseded: list[dict[str, Any]] = []
    replaced: dict[int, str] = {}
    for arm, rows in by_arm.items():
        current_rows = [r for r in rows if r.is_current_build]
        if not current_rows:
            continue
        winner = sorted(current_rows, key=lambda r: r.source_sha256)[0]
        for r in rows:
            if r is winner or r.is_current_build:
                continue
            replaced[id(r)] = winner.source_path
            superseded.append({"arm": arm, "superseded_path": r.source_path,
                               "superseded_build": r.gate_build,
                               "superseded_by": winner.source_path,
                               "superseded_by_build": winner.gate_build})

    final: list[VerdictIdentity] = []
    for r in records:
        if id(r) in replaced:
            r = VerdictIdentity(**{**asdict(r), "superseded": True,
                                   "superseded_by": replaced[id(r)],
                                   "missing_fields": list(r.missing_fields),
                                   "reasons": list(r.reasons)})
        final.append(r)

    root_rel = None
    if root is not None:
        rp = Path(root)
        root_rel = str(rp.relative_to(ROOT)) if rp.is_relative_to(ROOT) else str(rp)
    if root_rel:
        with_prov = []
        for r in final:
            rel_dir = str(Path(r.source_path).parent)
            if rel_dir == root_rel:
                prov = "<top-level>"
            elif rel_dir.startswith(root_rel + "/"):
                prov = rel_dir[len(root_rel) + 1:]
            else:
                prov = rel_dir
            with_prov.append(VerdictIdentity(**{**asdict(r), "provenance": prov,
                                                "missing_fields": list(r.missing_fields),
                                                "reasons": list(r.reasons)}))
        final = with_prov

    # --- 裁定 31.4：跨记录改判（本档激活条件收窄）+ 理由侧 provenance_kind 子标签 ---
    # 顺序要紧：改判必须在 provenance 之后（子标签按来源目录判）、在分布统计之前
    # （否则 usable_for_distribution 报的是改判前的旧口径）。
    final, regrade_evidence = regrade_pending_impl(final, current)
    final = [_rebuild(r, provenance_kind=classify_provenance_kind(
                 usable_for=r.usable_for, provenance=r.provenance, source_path=r.source_path,
                 superseded=r.superseded, gate_pass=r.gate_pass,
                 input_contract_status=r.input_contract_status))
             if r.provenance_kind is None else r
             for r in final]

    conflicting = sorted(arm for arm, rows in by_arm.items()
                         if len({str(r.gate_build) for r in rows}) > 1)
    by_prov: dict[str, dict[str, int]] = {}
    for r in final:
        by_prov.setdefault(r.provenance or "<unknown>", {})
        key = r.usable_for
        by_prov[r.provenance or "<unknown>"][key] = by_prov[r.provenance or "<unknown>"].get(key, 0) + 1

    # 本档的**实测**证据（不是叙述）：记录级形状命中几条、其中几条因收窄被改判、
    # 改判后还剩几条。C 只统计已解析出的字段，不重跑门禁。
    current_build_str = str(current.get("gate_build"))
    record_level_shape = [r for r in final
                          if is_pending_impl_exoneration(r.validity_class, r.input_contract_status)
                          and r.arm_verdict and r.gate_build not in (None, "")
                          and r.measurement_validity_declared
                          and r.suspect_truncation_as_failure is not True]
    pending_records = [r for r in final if r.usable_for == USABLE_PENDING_IMPL]
    carried_at_current = [r for r in final
                          if r.is_current_build
                          and str(r.input_contract_status) == GATE_EXONERATED]
    pending_evidence = {
        "activation_rule": PENDING_IMPL_ACTIVATION_RULE,
        "carrying_artifact_rule": CARRYING_ARTIFACT_RULE,
        # 记录级形状（parse_verdict/classify 那一层看到的）：改判前命中多少条
        "n_record_level_shape": len(record_level_shape),
        "record_level_shape_all_at_historical_builds": bool(record_level_shape) and all(
            not r.is_current_build for r in record_level_shape),
        "record_level_shape_builds": sorted({str(r.gate_build) for r in record_level_shape}),
        "record_level_shape_provenance": sorted({r.provenance or "<unknown>"
                                                 for r in record_level_shape}),
        # 收窄之后仍留在本档的（= 该臂在当前构建下**没有**任何承载免罪的产物）
        "n_pending_impl": len(pending_records),
        "pending_impl_arms": sorted({r.arm for r in pending_records}),
        "pending_impl_provenance": sorted({r.provenance or "<unknown>" for r in pending_records}),
        # 被改判的（裁定 31.4 判 (b)）：逐条留审计字段
        "n_regraded_to_stale": regrade_evidence["n_regraded"],
        "regraded_records": regrade_evidence["regraded"],
        "regraded_provenance_kinds": _distribution(
            r["provenance_kind"] for r in regrade_evidence["regraded"]),
        "carrying_arms_at_current_build": regrade_evidence["carrying_arms_at_current_build"],
        "current_build_carrying_records": [
            {"arm": r.arm, "source_path": r.source_path, "provenance": r.provenance or "<unknown>",
             "gate_build": r.gate_build, "is_current_build": bool(r.is_current_build),
             "input_contract_status": r.input_contract_status,
             "measurement_valid": r.measurement_valid, "usable_for": r.usable_for}
            for r in carried_at_current],
    }
    arm_rows = list((arm_index or {}).get("rows") or [])
    reconciliation = reconcile_exonerations(final, arm_rows, current)
    record_level_forward_arms = sorted(
        {r.arm for r in final
         if str(r.validity_class) == AUTHORITY_EXONERATED
         and str(r.input_contract_status) != GATE_EXONERATED})
    exoneration_block = {
        **reconciliation,
        "authority_side": {
            "available": bool(arm_rows),
            "n_rows": len(arm_rows),
            "source": (arm_index or {}).get("path"),
            "sha256": (arm_index or {}).get("sha256"),
            "meta": (arm_index or {}).get("meta") or {},
            "rule": reconciliation["authority_side_rule"],
            **({} if arm_rows else {"why_unavailable":
                                    "没有加载到 arms_summary.json（arm_index 为空）⇒ 权威侧无从对账，"
                                    "两个方向列表为空**不是**「没有矛盾」，是「没得比」。"}),
        },
        "pending_impl_label": PENDING_IMPL_LABEL,
        "pending_impl_ruling": {
            "label_retired": LABEL_RETIRED,
            "retired_by": LABEL_RETIRED_BY,
            "grade_mechanism_retired": False,
            "why_grade_survives": ("裁定 28 撤下的是**标注**（对臂现状态的表述），不是「逐份产物"
                                   "有没有承载裁定」这个事实。旧产物不因裁定更新而改写；"
                                   "机制保留同裁定 28.4 对护栏① 的处理（本轮 moot，机制仍留）。"),
            "arm_current_status_per_ruling": ("probe_exonerated（probe_kind=clip_at_train_absmax、"
                                              "band_checked=false）@ v1.5 / f19f61341cbe，"
                                              "measurement_valid=True、gate_pass=True"),
            "arm_current_status_source": "转引 裁定 28.1，**C 未独立复核**（C 不重判、不另造口径）",
            "citation_rule": CITATION_RULE_28,
            "todo9_question_as_filed": TODO9_QUESTION_AS_FILED,
            "ruling": REGRADE_RULING_31_4,
            "ruling_rationale": {
                "not_a": ("档名 pending_impl_ruling_approved 字面是「实现待落地（已批准）」，"
                          "而这 5 条的 violated 是探针的**预期结果**与锚点的**设计使然** —— "
                          "一个说谎的标签比没有标签更坏。"),
                "not_pure_c": ("为 5 条记录新开一档 usable_for，会把「能不能当现构建证据用」这个"
                               "**二元可用性**问题变成三元，下游每个消费者都要多认一个值 ⇒ "
                               "词汇表膨胀的代价大于收益。"),
                "adopted_b_plus_sublabel": ("可用性判断只看 usable_for（不分叉），为什么不可用看 "
                                            "provenance_kind（不丢信息）。"),
            },
            "implementation": {
                "activation_condition": PENDING_IMPL_ACTIVATION_RULE,
                "carrying_artifact_definition": CARRYING_ARTIFACT_RULE,
                "layering": ("跨记录条件只在 inventory() 里做（regrade_pending_impl）；"
                             "parse_verdict / classify 仍是记录级纯函数，一字节未改其判据。"),
                "regraded_to": USABLE_STALE_BUILD,
                "audit_field": "regraded_from（原档名留在记录上，append-only：不改写原判断）",
                "provenance_kind_vocabulary": list(PROVENANCE_KINDS),
                "availability_unchanged": ("改判只换「为什么不可用」的说法，不换可用性："
                                           f"{USABLE_PENDING_IMPL} 与 {USABLE_STALE_BUILD} "
                                           "都不能当现构建证据 ⇒ physical_fact 一条不动。"),
            },
            "evidence": pending_evidence,
            "not_always_false": ("收窄有可能让本档**永远不触发**（恒假 = 没有这一档）。反例已附："
                                 "scripts/c_selfcheck_verdict_identity.py::"
                                 "case_pending_impl_not_always_false 造「免罪条目已登记、但该臂在"
                                 "当前构建下无任何承载产物」的形状 ⇒ 本档必须触发；"
                                 "同一目录再补一份现构建承载产物 ⇒ 必须改判。合成产物在 "
                                 "runs/infra/c_verdict_selfcheck/<ts>/，数字无物理意义（ADR-C-007）。"),
        },
        "scope_note": ("逐份裁定口径：本档说的是「**这份产物**的门禁输出没有承载免罪」，"
                       "不是「当前构建仍不能承载」。实现落地后新产出的裁定会带 "
                       f"{GATE_EXONERATED}、本档自动清空；旧产物仍如实留档（不改写）。"),
        # 对每条**记录级**正向脱节的臂，列出它在当前构建下的产物观测：
        # 空列表 = 当前构建下还没有该臂的裁定产物 ⇒ 从产物侧无法判断实现是否已承载
        # （C 不重跑门禁去造这个观测 —— 那就是第二套判据）。
        "per_arm_current_build": {
            arm: [artifact_identity(r) for r in final
                  if r.arm == arm and r.is_current_build]
            for arm in record_level_forward_arms},
        "note": ("正向（权威已记免罪、门禁某份产物未承载）由 usable_for 与 per_arm_current_build "
                 "承载；反向（门禁免罪、权威表未记）只上报不改分级（裁定 18：stdfloor 的门禁免罪"
                 "是对的）。**两个方向列表现在只在两侧同为当前构建时才非空**（裁定 31.3）。"),
    }
    if collect is not None:
        # P1-6：把**改判之后**的记录对象交给调用方（run manifest 要用 `artifact_identity()`
        # 读属性；喂序列化 dict 就等于另开一条取值路径，「同源同义」会变成一句空话）。
        # 用出参而不是塞进返回值：本函数的返回值要能被 `json.dumps`
        # （`runs/infra/c_verdict_identity_inventory.json` 就是它），活对象塞进去会写不出来。
        collect.extend(final)
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H%M%S%z"),
        "root_label": root_label,
        "gate_current": current,
        "gate_id": current.get("gate_id"),
        "gate_identity_fingerprint": current.get("gate_identity_fingerprint"),
        "gate_id_distribution": _distribution(r.gate_id for r in final),
        "artifact_gate_id_distribution": _distribution(
            r.artifact_gate_id or "<not_declared_by_artifact>" for r in final),
        "n_wrong_gate": sum(1 for r in final if r.usable_for == USABLE_WRONG_GATE),
        "n_gate_ambiguous": sum(1 for r in final if r.artifact_gate_ambiguous),
        "n_files_scanned": len(paths),
        "n_verdicts": len(final),
        "build_distribution": _distribution(r.gate_build for r in final),
        "gate_version_distribution": _distribution(r.gate_version for r in final),
        "usable_for_distribution": _distribution(r.usable_for for r in final),
        "provenance_distribution": _distribution(r.provenance or "<unknown>" for r in final),
        "usable_for_by_provenance": {k: by_prov[k] for k in sorted(by_prov)},
        "provenance_kind_distribution": _distribution(
            r.provenance_kind for r in final if r.provenance_kind),
        "regraded_from_pending_impl": regrade_evidence,
        "measurement_valid_distribution": _distribution(r.measurement_valid for r in final),
        "arms_with_conflicting_builds": conflicting,
        "n_superseded": len(superseded),
        "validity_class_distribution": _distribution(r.validity_class for r in final),
        "validity_source_distribution": _distribution(r.validity_source for r in final),
        "labels_reportable_distribution": _distribution(r.labels_reportable for r in final),
        "field_class_mismatch_count": sum(
            1 for r in final if r.arm_field_class is not None and r.field_class is not None
            and r.arm_field_class != r.field_class),
        # 免罪在权威层与门禁层的脱节计数（两个方向分开报，只**上报**不改分级）。
        # 正向 = 增补六 §8-C3 的那一档（已会签、实现未承载）⇒ 已由 usable_for 承载；
        # 反向 = 门禁免罪而权威表不是 VALID_probe_exonerated ⇒ 裁定 18 判过 stdfloor
        # 那一条门禁是**对的**、属权威表滞后，C 不替 A/B 裁定谁对，只把数量摆出来。
        "exoneration_disagreement": exoneration_block,
        "arm_summary": ({k: arm_index.get(k) for k in ("available", "path", "sha256", "n_rows")}
                        if arm_index else {"available": False}),
        "superseded": superseded,
        "parse_errors": errors,
        "records": [r.to_dict() for r in final],
        "invariant": ("只读上游裁定、不重算任何判据数字；usable_for=physical_fact 仅当"
                      "「出自当前 gate_build」且「measurement_valid is True」且"
                      "「不怀疑截断当失败」；旧构建裁定一律降级为 stale_build_evidence，"
                      "不得当物理事实进账本或发布包。权威表已记免罪而门禁未承载的裁定"
                      "单独归 pending_impl_ruling_approved（过渡期标签 "
                      f"{PENDING_IMPL_LABEL}），既不当事实也不当旧证据、更不当测量无效；"
                      f"裁定 31.4 后本档激活条件收窄（{PENDING_IMPL_ACTIVATION_RULE}），"
                      f"被改判的记录转 {USABLE_STALE_BUILD} 并带 provenance_kind + regraded_from。"
                      "免罪对账只在两侧同为当前构建的子集上做（裁定 31.3），不同构建改报 "
                      f"{STALE_SIDE_NOT_COMPARABLE}（可见不报警）。"),
    }


def scan_dir(directory: str | Path, pattern: str = "gate_*.json",
             *, current: dict[str, Any] | None = None,
             collect: list["VerdictIdentity"] | None = None,
             gate_id: str | None = None) -> dict[str, Any]:
    """扫一个目录下的裁定文件（默认 `gate_*.json`），返回 `inventory()` 的结果。"""
    directory = Path(directory)
    if not directory.is_dir():
        raise VerdictIdentityError(f"目录不存在: {directory}")
    paths = sorted(p for p in directory.rglob(pattern) if p.is_file())
    label = (str(directory.relative_to(ROOT)) if directory.is_relative_to(ROOT)
             else str(directory))
    return inventory(paths, current=current, root_label=label, root=directory,
                     arm_index=load_arm_index(directory), collect=collect, gate_id=gate_id)
