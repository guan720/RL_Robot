#!/usr/bin/env python3
"""A 线：48 臂权威表**迁移闸**（ADR-A-006 裁定 2）的代码化前置检查 —— 全程只读。

为什么需要它：裁定 2 写的是「B 补齐 裁定 16.4 条目 + D 会签后，A 重跑
`a_regate_gate_current.py` + `summarize_lerobot_act_arms.py` 迁移；**迁移前必须核**新表
`NOT_CITABLE_measurement_invalid == 1` 且三分类 `== 25 / 22 / 1`，否则不迁并报回 D」，
并注明「**A 不自免**」。判据只写在日报/移交单里就等于没有闸 —— 本脚本把它变成**可执行断言**，
CLOSED 时 exit 1，可以直接串在迁移命令前面，闸不开就跑不到迁移那两条。

两个模式：
  --mode preflight（默认）：读 B 的 `reclassification.json` + `configs/b_probe_exonerations.json`，
      判「**现在能不能迁**」。任一 blocking 条不满足 → `MIGRATION_GATE=CLOSED` + exit 1。
  --mode postcheck：迁移**之后**读 A 自己的 `arms_summary.json`，判「迁完的表是否达标」。
      不达标 → exit 1，按裁定 2 **不迁**（留档 `arms_summary.json` 一字节未动，无需回滚）并报回 D。
      注意 postcheck **同时复核 B 侧 B1–B5**：迁移合法的前提是两张表都站在免罪后口径上，
      只核 A 侧会放过「A 迁了、B 的册子还是空的」这种半迁移状态。
  --selftest：变异自检，证明这道闸**有牙**（合规 fixture 必须 OPEN、缺任一条必须 CLOSED），
      而不是恒假判据。本仓有过「恒真判据」事故（`work/decisions/decisions_20260928_B.md`
      DR-003 验收判据 3），所以判据类工具一律自带反证。自检**不写任何文件**（fixture 全在内存里，
      探针产物指向仓库内已存在的真实文件），因此无需回收站清理。

**G1 / G2 / G3 / L9 四条「门禁代码级」判据的来历与 09-29 的重构（裁定 27）**：
移交单 `docs/a_handoff_to_b_probe_exoneration_gap_20260928.md` §4 原先把免罪册缺条目归因为
「册子 `_doc` 的『带外不受理』文案挡住了 裁定 10 通道」。09-29 复核 B 的门禁源码
（`scripts/b_gate_controlled_success.py`，v1.4 / `b9379fdb1089`）后**该归因不完整**：
`probe_kind` 在门禁里**从不参与分支**（只被回显），真正挡住目标臂的是三条**代码级**前置——
  G1 `ic_status → probe_exonerated` 的转移白名单只有 `("verified_ok","not_applicable_verified")`，
     **不含 `violated`**；而目标臂 blown 0.212 > 0.05 ⇒ ic_status 恒为 `violated`
     ⇒ 即便条目命中、证据 sha 全对，也**永远不会**转成 `probe_exonerated`（最根本的一条）；
  G2 争议带 `DISPUTED_BLOWN_BAND=(0.03,0.08)` 的「带外一律不受理」是**硬编码、不看 `probe_kind`**，
     目标臂 0.212 必判 `out_of_band_refused`，而该状态**明确不改 ic_status**；
  L9 `scope=="arm"` 要求产物 `blown_metric_impl` 在 `KNOWN_BLOWN_IMPLS` 内；目标臂权威 plain 产物
     `blown_metric_impl=null`（`missing_legacy_grandfathered`）⇒ 判 `scope_requires_known_impl` 当场拒绝。
     这一条**已被 D 于 09-29 独立重判实测复现**（`tmp/agentD_review_20260929/regate48.json` 里
     stdfloor 臂的**留档**产物正是这个拒绝路径；B 表用的是带指纹的 reblown 产物才命中的）。
⇒ **只改册子（`configs/b_probe_exonerations.json`）无法让 48 臂表达到 25/22/1**，必须改门禁代码；
  改代码 ⇒ `GATE_BUILD` 变 ⇒ 新版本 + 全量重判 + 改判 7 的登记义务，D 会签的范围也随之从
  「一条册子条目」变成「一次门禁语义变更」。三条判据都把这一点变成**可执行断言**，
  免得 B 白跑一轮「改册子 → 重判 → 还是 24/22/2」。
**09-29 下午的重构（裁定 27，D 认定 A 的 2 项 blocking 全是假红）**：上面三条锚点判据在 B 落地
v1.5（DR-008）之后**当场失效** —— v1.5 把带检查改成 `band_checked = kind not in BAND_EXEMPT_PROBE_KINDS`、
把晋级闸改成 `EXONERATION_PROMOTION_SOURCES[probe_kind]` 查表，两个文本锚点都认不出来，于是 A 的闸
对着一个**已经修好**的门禁报 `CLOSED / blocking_fail=2`。裁定 27 的定性是「**恒假的闸等于没有闸**」
（本仓第三条同源教训：DR-003 判据 3 恒真、D「裁定无代码承载」、本条恒假）。据此改为：
  G2 = **调门禁本尊实测**（blocking）：import `scripts/b_gate_controlled_success.py` 跑 `judge_file`
       判目标臂的 plain 产物（真册子、不写任何文件），要求 `input_contract.status == probe_exonerated`
       且 `measurement_valid is True`。不读源码、不认锚点 ⇒ **唯一不会被重构骗到的判据**（裁定 27④）。
  G1 / G3 = 原来的两条文本锚点，**降级为非 blocking 诊断**，并把锚点更新到认得 v1.5 的两种新形状；
       读不出结构就 WARN。与 G2 冲突时**一律以 G2 为准**（裁定 27：D 的实证结论优先）。
  L5 = 按门禁读的**精确键名**取（裁定 27②／裁定 21：门禁是 裁定 10 判据的唯一来源）。旧判据用
       「递归遍历 + `condN` 前缀匹配 + 值必须 is True」，被真条目里 `ruling10_conditions_evidence`
       的 5 条**证据散文 str** 打成假红。
  L6 = 照抄门禁读法（`cosign.by` 非空 + `cosign.fact_basis is True`），不再认 A 自造的 legacy 键名。
  L6b（新增，**非 blocking**）= 会签锚在哪个 build 上是**可核事实**，必须回显。DR-008 决定 7 明文
       build 不一致**不拒判**（否则死锁：条目只能在代码改完后写，写的那一刻会签必然锚在旧 build 上），
       所以本条只回显 + 变成引用纪律的一部分（裁定 27：会签 build 必须随数字一起走）。
  B7（新增，**非 blocking**）= 裁定 25 护栏①（DR-D22）：`cosign_build_matches=false` 期间该臂必须计入
       `summary.pending_cosign_reverify` 独立桶，不得直接算「已免罪」。执行人 B，A 只回显不代改。
  B8（新增，blocking）= 裁定 24④⑤（DR-D16）：两条豁免通道在 B 表上必须**可区分**（臂级回显 kind +
       summary 按 kind 分桶）。这是 A 侧「按 `probe_kind` 分组对账、不得直接比 `probe_exonerated` 计数」
       的前提；缺了它 A 的 P7 无从计算。
  P7（新增，postcheck blocking）= 裁定 24⑤：A 的 `VALID_probe_exonerated` **只**对应
       `clip_at_train_absmax`；stdfloor 在 A 表里维持 `valid` 但**另列一列**回显
       `probe_kind=reblown_single_source`。两表「被豁免臂数」必然差 1，是**设计差异不是缺陷**。

纪律：只读；默认不写任何文件（要留档才给 `--json-out`）；不改门禁（ADR-A-003）；
不碰 B/C/D 的文件；不执行 git 写命令（DR-003 决定 8 单写者纪律）；禁 `rm`（工作区 AGENTS.md）。

用法：
    # 判「现在能不能迁」（闸关着会 exit 1 并列出缺哪几条）：
    python3 scripts/a_migration_gate_preflight.py

    # 变异自检（证明闸有牙，不写任何文件）：
    python3 scripts/a_migration_gate_preflight.py --selftest

    # 迁移一条龙（闸不开就跑不到后面两条）：
    python3 scripts/a_migration_gate_preflight.py \\
      && python3 scripts/summarize_lerobot_act_arms.py --allow-build-change \\
      && python3 scripts/a_migration_gate_preflight.py --mode postcheck
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# 裁定 16.4 点名要登记的目标臂（blown 0.212，裁定 10 clip-at-train-absmax 通道免罪）
TARGET_ARM = "trimdone0_minmax_k2_lr1e-5_s20k_seed0"
TARGET_ARM_C = 12.469445          # = train-absmax，裁定 10 条件① 要求钉死在这个值
STDFLOOR_ARM = "trimdone0_stdfloor_minmax_k2_lr1e-5_s20k_seed0"   # blown 0.04 ≤ 0.05，本不需要豁免
REPLAN1_ARM = "trimdone0_minmax_k2_lr1e-5_s20k_seed0_replan1"     # 唯一 INVALID（免罪后）

DEFAULT_B_TABLE = "runs/infra/b_official_arms/reclassification.json"
DEFAULT_LEDGER = "configs/b_probe_exonerations.json"
DEFAULT_A_TABLE = "runs/infra/lerobot_act_env_20260928/arms_summary.json"
# B6（产物归属对账）读的 A 表。**09-29 迁移到 v1.5 后指回 DEFAULT_A_TABLE**：
# summarizer 已把 schema_version 3（归属回显 + `probe_kind` 列 + `exoneration_reconciliation` +
# `cosign_provenance`）直接写进 `arms_summary.json`，不再需要旁挂一份 v3 副本。
# 迁移前的两份留档一字节未动，仍可核：
#   attribution/arms_summary_v3.json                     = v1.2.1 / e4f5ec887788，schema 3（回归基线）
#   arms_summary.json 的 v1.2.1 内容                      = 已由上面那份留档承接
#   regate_v121_pinned/                                  = v1.2.1 的逐臂门禁裁定（含 PINNED_WHY.md）
DEFAULT_A_ATTRIBUTION_TABLE = DEFAULT_A_TABLE
# G1/G2/L9 判读的门禁源码（A 只读、不 import、不改）
DEFAULT_B_GATE = "scripts/b_gate_controlled_success.py"
# 目标臂的权威 plain 产物：裁定 10 规定免罪后引用的数字取自 plain 产物（探针产物是 composite policy）
TARGET_PLAIN_ARTIFACT = ("runs/infra/lerobot_act_env_20260928/"
                         "official_act_truth20_trimdone0_minmax_k2_lr1e-5_s20k_seed0.json")
TARGET_ARM_BLOWN = 0.212        # 增补五 §3 / 移交单 §2.2；B 表与 A 表同值
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
# 门禁的 DISPUTED_BLOWN_BAND（v1.4 / b9379fdb1089 实测值）；裁定 18.3 的 B5 判据要用它
DISPUTED_BAND = (0.03, 0.08)
# 裁定 29 / DR-D28：**引用锚只在 build 轴**（`GATE_BUILD` = 门禁脚本自身内容哈希、运行时现算
# ⇒ 判据不可能在 build 不变时改变）；spec 轴哈希的是散文规格文档，可在判据一字未动时被编辑
# （D 实测 35 分钟内移动 4 次：132fceb89f68 → 154b3636056f → a1a8f38e7893 → c7fadabe8e3c）
# ⇒ **spec 是观测日志、不是钉子**。权威口径的固定写法 = `v1.5 / f19f61341cbe`（不带 spec 值）。
# 本脚本的任何判据都**不得**比对 spec；自检 fixture 里也不写真实 spec 值，用下面这个自述占位符。
SELFTEST_SPEC_NOT_A_NAIL = "selftest_spec_not_a_nail（裁定 29：spec 轴不是钉子，勿比对）"

# 增补五 §3 / §7 的免罪后权威三分类（48 臂产物级）
REQUIRED_POST = {"citable": 25, "valid_zero_success": 22, "invalid": 1}
REQUIRED_PRE = {"citable": 24, "valid_zero_success": 22, "invalid": 2}
# 计数层是构建不变的（A 已实测 v1.2.1 / v1.3 / v1.4 同值）；迁移前后都必须还是这几个数
BUILD_INVARIANT_TOTALS = {"arms": 48, "episodes": 960, "raw_success": 377, "controlled_success": 135,
                          "insufficient_lift": 235, "flick": 7, "over_lift": 0, "provisional_pass": 0}
COND_PREFIXES = ("cond1", "cond2", "cond3", "cond4", "cond5")   # 裁定 10 的五条准入
COUNTERSIGN_KEYS = ("countersigned_by", "countersigned", "countersign", "countersign_ref",
                    "d_countersign", "approved_by_d", "cosign", "cosign_by", "cosigned_by")

# ---- 09-29 追加（裁定 21 / 裁定 24⑤ / 裁定 25 / 裁定 27）-------------------------------
# 裁定 21：裁定 10 的五条准入判据由**门禁独家执行**，A 侧不得自造键名。L5 只认门禁常量
# `RULING10_CONDITION_KEYS` 里的那五个精确键（裁定 27②）；读不到门禁源码时用下面这份**冻结副本**，
# 并在判据里显式声明「用了副本」。副本 = v1.5 / f19f61341cbe 的逐字抄录。
RULING10_KEYS_FALLBACK = ("cond1_C_equals_train_absmax",
                          "cond2_verdicts_and_counts_identical",
                          "cond3_diffs_enumerated_and_verdict_same",
                          "cond4_probe_path_C_build_recorded",
                          "cond5_scope_measurement_valid_only")
# 裁定 24⑤：A 的 `VALID_probe_exonerated` **只**对应 clip_at_train_absmax；reblown_single_source
# 在 A 表里维持 `valid`，但另列一列回显 kind。两表「被豁免臂数」必然差 1，是设计差异不是缺陷，
# 任何对账工具必须**按 probe_kind 分组比**，不得直接比 `probe_exonerated` 计数。
PROBE_KIND_CLIP = "clip_at_train_absmax"
PROBE_KIND_REBLOWN = "reblown_single_source"
# 裁定 25 护栏①（DR-D22）：`cosign_build_matches=false` 期间该臂必须进这个独立桶，不得直接算「已免罪」；
# B 换上 D 复签的块并重出表后该桶应清零（「会签—重判」是两轮）。
PENDING_COSIGN_BUCKET = "pending_cosign_reverify"
# 门禁里 kind 常量的**变量名**（G1/G3 的文本诊断锚点认它，避免硬编码字面量随 B 改名而失效）
KIND_CONST_CLIP = "PROBE_KIND_CLIP_AT_TRAIN_ABSMAX"


def _load(path: Path):
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:                                     # noqa: BLE001 - 读不到就是一条 FAIL
        return {"__load_error__": f"{type(exc).__name__}: {exc}"}


def _norm_artifact(val) -> str | None:
    """把产物路径归一成仓库相对形式再比对（B 表的 `supersedes` 里出现过绝对路径）。"""
    if not isinstance(val, str) or not val.strip():
        return None
    s = val.strip().replace("\\", "/")
    marker = "RL_Robot/"
    if marker in s:
        s = s.split(marker, 1)[1]
    while s.startswith("./"):
        s = s[2:]
    return s or None


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _walk(node, trail="$"):
    """递归产出 (json_path, key, value)，用于在不假设 B 的 schema 的前提下找到实质内容。"""
    if isinstance(node, dict):
        for key, val in node.items():
            yield f"{trail}.{key}", key, val
            yield from _walk(val, f"{trail}.{key}")
    elif isinstance(node, list):
        for idx, val in enumerate(node):
            yield from _walk(val, f"{trail}[{idx}]")


def _find_value(node, want: float, tol: float = 1e-6) -> list[str]:
    hits = []
    for path, _key, val in _walk(node):
        if isinstance(val, (int, float)) and not isinstance(val, bool) and abs(val - want) <= tol:
            hits.append(path)
    return hits


def _find_keys(node, needles: tuple[str, ...]) -> dict[str, str]:
    out: dict[str, str] = {}
    for path, key, val in _walk(node):
        low = str(key).lower()
        for nd in needles:
            if nd in low and isinstance(val, (str, int, float)) and str(val).strip():
                out.setdefault(nd, f"{path}={val}")
    return out


# --------------------------------------------------------------------------------------
# 门禁源码的文本级判读（G1 / G2 / L9）。只读 B 的文件；锚点找不到就降级为 WARN，不 FAIL。
# --------------------------------------------------------------------------------------

def read_gate_source(root: Path, rel: str = DEFAULT_B_GATE) -> tuple[str, str | None]:
    path = root / rel
    if not path.is_file():
        return "", None
    try:
        return path.read_text(encoding="utf-8", errors="replace"), _sha256(path)
    except Exception:                                             # noqa: BLE001
        return "", None


def _tuple_of_str(src: str, const: str) -> tuple[str, ...] | None:
    m = re.search(rf"^{const}\s*=\s*\(([^)]*)\)", src, re.MULTILINE)
    return tuple(re.findall(r"[\"']([^\"']+)[\"']", m.group(1))) if m else None


def _tuple_of_float(src: str, const: str) -> tuple[float, ...] | None:
    m = re.search(rf"^{const}\s*=\s*\(([^)]*)\)", src, re.MULTILINE)
    if not m:
        return None
    nums = re.findall(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", m.group(1))
    return tuple(float(n) for n in nums) if len(nums) >= 2 else None


def ruling10_condition_keys(gate_src: str) -> tuple[tuple[str, ...], bool]:
    """L5 的判据键名**只从门禁取**（裁定 21 / 裁定 27②）。返回 (五个键名, 是否来自门禁源码)。"""
    keys = _tuple_of_str(gate_src, "RULING10_CONDITION_KEYS") if gate_src else None
    if keys and len(keys) == 5:
        return tuple(keys), True
    return RULING10_KEYS_FALLBACK, False


def live_gate_build(root: Path, gate_rel: str = DEFAULT_B_GATE) -> str | None:
    """复刻门禁自己的 `GATE_BUILD = _sha12(Path(__file__).resolve())`（= sha256 前 12 位）。

    L6b / B7 用它判「会签锚的 build 与 live build 是否一致」。A 不 import 门禁来取这个值，
    因为 import 有副作用；sha256[:12] 是纯函数，复刻比 import 更安全。
    """
    digest = _sha256(root / gate_rel)
    return digest[:12] if digest else None


def gate_row_ic_status(row: dict) -> str | None:
    """`judge_file` 返回的行里**没有**顶层 `ic_status`，它在 `input_contract.status`（v1.5 实测）。"""
    blk = row.get("input_contract")
    return blk.get("status") if isinstance(blk, dict) else None


def promotion_allows_violated(src: str) -> bool | None:
    """G1 诊断锚点：晋级闸是否允许 `violated → probe_exonerated`（认 v1.4 / v1.5 两种形状）。

    v1.4 形状：`... and ic_status in ("verified_ok", "not_applicable_verified")`（不含 violated）；
    v1.5 形状（DR-008 决定 5）：`EXONERATION_PROMOTION_SOURCES = {PROBE_KIND_*: (...), ...}` 查表，
    只有 `clip_at_train_absmax` 那一行含 `("violated",)`。旧锚点只认前者 ⇒ v1.5 下假红（裁定 27）。
    """
    m = re.search(r"^EXONERATION_PROMOTION_SOURCES\s*=\s*\{(.*?)^\}", src,
                  re.MULTILINE | re.DOTALL)
    if m:
        for line in m.group(1).splitlines():
            if KIND_CONST_CLIP in line or PROBE_KIND_CLIP in line:
                return "violated" in re.findall(r"[\"\']([^\"\']+)[\"\']", line)
        return False
    wl = exoneration_transition_whitelist(src)
    return ("violated" in wl) if wl is not None else None


def band_check_is_kind_gated(src: str) -> bool | None:
    """G3 诊断锚点：争议带检查是否按 `probe_kind` 分通道（认 v1.4 / v1.5 两种形状）。

    v1.5（DR-008 决定 1）用**白名单**：`BAND_EXEMPT_PROBE_KINDS = (PROBE_KIND_CLIP_AT_TRAIN_ABSMAX,)`
    + `band_checked = kind not in BAND_EXEMPT_PROBE_KINDS`。旧的「回看 8 行找 if 条件里有没有
    `probe_kind`」认不出这种写法 ⇒ v1.5 下假红（裁定 27）。
    """
    m = re.search(r"^BAND_EXEMPT_PROBE_KINDS\s*=\s*\(([^)]*)\)", src, re.MULTILINE)
    if m:
        body = m.group(1)
        return bool(KIND_CONST_CLIP in body or PROBE_KIND_CLIP in body)
    return band_refusal_is_probe_kind_gated(src)


def arm_probe_kind(row: dict) -> str | None:
    """臂级 `probe_kind` 回显（裁定 19 / DR-D16）。B 表 v1.5 用 `probe_exoneration_kind`；
    也接受对象形式的 `probe_exoneration.probe_kind`（裁定 19 允许两种写法）。"""
    kind = row.get("probe_exoneration_kind")
    if isinstance(kind, str) and kind.strip():
        return kind.strip()
    exo = row.get("probe_exoneration")
    if isinstance(exo, dict):
        kind = exo.get("probe_kind")
        if isinstance(kind, str) and kind.strip():
            return kind.strip()
    found = {str(v) for _p, _k, v in _walk(row)
             if v in (PROBE_KIND_CLIP, PROBE_KIND_REBLOWN)}
    return sorted(found)[0] if len(found) == 1 else None


def cosign_build_facts(root: Path, ledger_doc, ledger_path: Path,
                       gate_rel: str = DEFAULT_B_GATE) -> dict:
    """会签 build 的可核事实（L6b / B7 共用一次计算，避免两处各算一遍算出不同结果）。"""
    ledger = ledger_doc if ledger_doc is not None else _load(ledger_path)
    _key, entry = find_entry(ledger if isinstance(ledger, dict) else {})
    cs = entry.get("cosign") if isinstance(entry, dict) else None
    cs = cs if isinstance(cs, dict) else {}
    cur = live_gate_build(root, gate_rel)
    at = str(cs.get("gate_build_at_cosign") or cs.get("gate_build") or "") or None
    return {"live_gate_build": cur, "cosign_gate_build": at,
            "cosign_build_matches": (at == cur) if (at and cur) else None,
            "cosign_gate_version": cs.get("gate_version_at_cosign")}


def exoneration_transition_whitelist(src: str) -> list[str] | None:
    """G1 锚点：`ic_status -> probe_exonerated` 的转移白名单。找不到锚点返回 None。"""
    m = re.search(r'"exonerated"\s+and\s+ic_status\s+in\s*\(([^)]*)\)', src)
    if not m:
        return None
    return re.findall(r"[\"']([^\"']+)[\"']", m.group(1))


def band_refusal_is_probe_kind_gated(src: str) -> bool | None:
    """G2 锚点：`out_of_band_refused` 的赋值是否已被 `probe_kind` 分支管住。

    判法（文本级）：找到给 status 赋 `out_of_band_refused` 的行，往上回看到它所属的
    `if` / `elif` 条件行为止（最多 8 行），条件文本里出现 `probe_kind` 即为已分通道。
    锚点行都找不到 ⇒ None（结构变了，交给人工复核）。
    """
    lines = src.splitlines()
    hits = [i for i, ln in enumerate(lines)
            if "out_of_band_refused" in ln and "status" in ln and "=" in ln]
    if not hits:
        return None
    for i in hits:
        cond: list[str] = []
        j = i - 1
        while j >= 0 and len(cond) < 8:
            cond.append(lines[j])
            stripped = lines[j].lstrip()
            if stripped.startswith("if ") or stripped.startswith("elif "):
                break
            j -= 1
        if "probe_kind" in "\n".join(cond):
            return True
    return False


def target_arm_impl(root: Path, b_doc: dict) -> tuple[str | None, str, dict]:
    """目标臂**权威 plain 产物**的 `input_contract.blown_metric_impl`（L9 用）。

    产物路径优先取 B 表里该臂的 `file`（B 表就是门禁看到的输入），取不到回落到常量路径。
    """
    row = next((a for a in (b_doc.get("arms") or []) if a.get("arm") == TARGET_ARM), {})
    rel = row.get("file") or TARGET_PLAIN_ARTIFACT
    doc = _load(root / rel) if isinstance(rel, str) else {}
    blk = (doc.get("input_contract") or {}) if isinstance(doc, dict) else {}
    impl = blk.get("blown_metric_impl") if isinstance(blk, dict) else None
    return (impl if isinstance(impl, str) and impl.strip() else None), str(rel), row


def run_gate_on_target(root: Path, artifact_rel: str = TARGET_PLAIN_ARTIFACT,
                       gate_rel: str = DEFAULT_B_GATE) -> tuple[dict | None, str | None]:
    """G3：用 B 的门禁**本尊**端到端判目标臂的 plain 产物（真册子、不写任何文件）。

    为什么要实测而不是继续读源码：G1/G2 是文本锚点判读，B 一重构就失真 —— v1.5（DR-008）把
    带检查改成 `band_checked = kind not in BAND_EXEMPT_PROBE_KINDS`、把晋级闸改成
    `EXONERATION_PROMOTION_SOURCES[probe_kind]` 查表，两条锚点当场失效（G2 假 FAIL）。
    端到端跑一次 `judge_file` 不依赖任何锚点，是**唯一**不会被重构骗到的判据。
    """
    gate_path = root / gate_rel
    artifact = root / artifact_rel
    if not gate_path.is_file():
        return None, f"门禁源码不存在：{gate_rel}"
    if not artifact.is_file():
        return None, f"目标臂 plain 产物不存在：{artifact_rel}"
    try:
        import contextlib
        import importlib.util
        import io
        spec = importlib.util.spec_from_file_location("a_preflight_b_gate", gate_path)
        if spec is None or spec.loader is None:
            return None, "无法加载门禁模块"
        mod = importlib.util.module_from_spec(spec)
        sys.modules["a_preflight_b_gate"] = mod
        with contextlib.redirect_stdout(io.StringIO()):
            spec.loader.exec_module(mod)
        ns = argparse.Namespace(paths=[str(artifact)], rise_cap=mod.RISE_CAP,
                                final_rise=mod.FINAL_RISE_MIN, hold_phases=None,
                                no_strict_final_rise=False, assist_off=False,
                                json_out=None, quiet=True)
        with contextlib.redirect_stdout(io.StringIO()):
            row = mod.judge_file(str(artifact), ns)
        return (row if isinstance(row, dict) else None), None
    except Exception as exc:                                    # noqa: BLE001 - 实测不可用就降级为诊断
        return None, f"{type(exc).__name__}: {exc}"
class Checks:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, cid: str, name: str, ok: bool, observed, required, *,
            blocking: bool = True, note: str = "") -> bool:
        self.rows.append({"id": cid, "name": name, "pass": bool(ok), "blocking": blocking,
                          "observed": observed, "required": required, "note": note})
        return bool(ok)

    @property
    def open(self) -> bool:
        return all(r["pass"] for r in self.rows if r["blocking"])

    def n_fail_blocking(self) -> int:
        return sum(1 for r in self.rows if r["blocking"] and not r["pass"])

    def n_warn(self) -> int:
        return sum(1 for r in self.rows if not r["blocking"] and not r["pass"])


def find_entry(ledger: dict) -> tuple[str | None, dict]:
    entries = ledger.get("entries") or {}
    if not isinstance(entries, dict):
        return None, {}
    if TARGET_ARM in entries and isinstance(entries[TARGET_ARM], dict):
        return TARGET_ARM, entries[TARGET_ARM]
    for key, val in entries.items():                             # 也接受按 sha256 建键、内部写臂名
        if isinstance(val, dict) and val.get("arm") == TARGET_ARM:
            return key, val
    return None, {}


def check_ledger(checks: Checks, ledger_path: Path, repo_root: Path, ledger_doc=None,
                 b_doc: dict | None = None, gate_src: str = "",
                 cosign_facts: dict | None = None) -> dict:
    ledger = _load(ledger_path) if ledger_doc is None else ledger_doc
    if "__load_error__" in ledger:
        checks.add("L0", f"免罪册可读（{ledger_path}）", False, ledger["__load_error__"], "可解析的 JSON")
        return {}
    checks.add("L0", f"免罪册可读（{ledger_path}）", True, f"entries={len(ledger.get('entries') or {})}",
               "可解析的 JSON")
    key, entry = find_entry(ledger)
    if not checks.add("L1", f"免罪册含 裁定 16.4 要求的 `{TARGET_ARM}` 条目", bool(entry),
                      f"命中的键={key}" if entry else f"现有键={sorted((ledger.get('entries') or {}))}",
                      "必须有一条命中目标臂",
                      note="条目内容 A 已备齐可直接抄：`docs/a_handoff_to_b_probe_exoneration_gap_"
                           "20260928.md` §5（含探针路径 / C / build / 五条准入逐条 / C=5.0 判别力反证）"):
        return {}

    probe_rel = None
    for cand in ("artifact", "probe_artifact", "probe_file", "probe"):
        val = entry.get(cand)
        if isinstance(val, str) and val.strip():
            probe_rel = val.strip()
            break
    probe_path = repo_root / probe_rel if probe_rel else None
    checks.add("L2", "条目声明探针产物路径且文件真实存在", bool(probe_path and probe_path.is_file()),
               probe_rel or "（未声明）", "仓库相对路径 + 文件存在")

    c_hits = _find_value(entry, TARGET_ARM_C)
    checks.add("L3", f"条目登记 C={TARGET_ARM_C}（train-absmax，裁定 10 条件①）", bool(c_hits),
               c_hits or "（未找到该数值）", f"条目内任处出现 {TARGET_ARM_C}")

    prov = _find_keys(entry, ("build", "gate_version"))
    checks.add("L4", "条目登记 gate build / version（裁定 16.4）", len(prov) >= 2,
               prov or "（未找到）", "同时出现 build 与 gate_version")

    # ---- L5（裁定 27② 收窄）：只认**门禁自己读的那五个精确键**，不做前缀递归遍历 ----
    # 旧判据 = 「递归遍历整条目 + 键名前缀匹配 cond1..cond5 + 命中值必须 is True」。真条目里有
    # **10 个**键命中前缀：`ruling10_conditions.condN_*` 5 个 bool True +
    # `ruling10_conditions_evidence.condN` 5 个**证据散文 str** ⇒ 字符串让它判 FAIL（裁定 27 认定假红）。
    # 门禁本身不受影响：它只按 `RULING10_CONDITION_KEYS` 的精确键名读 `ruling10_conditions` 这一个 dict。
    # 裁定 21：门禁是 裁定 10 判据的**唯一来源** ⇒ A 侧照抄门禁的键名与读法，不自造、不放宽。
    cond_keys, from_gate = ruling10_condition_keys(gate_src)
    conds = entry.get("ruling10_conditions")
    conds = conds if isinstance(conds, dict) else {}
    missing = [k for k in cond_keys if k not in conds]
    not_true = [k for k in cond_keys if conds.get(k) is not True]
    evidence = entry.get("ruling10_conditions_evidence")
    n_evidence = len(evidence) if isinstance(evidence, dict) else 0
    l5_note = ("键名取自门禁常量 `RULING10_CONDITION_KEYS`（裁定 21：门禁是 裁定 10 判据唯一来源）"
               if from_gate else
               "门禁源码里读不到 `RULING10_CONDITION_KEYS` ⇒ 用 A 侧冻结副本（v1.5 逐字抄录）；"
               "B 若改键名，请同步 a_migration_gate_preflight.py 的 RULING10_KEYS_FALLBACK")
    if n_evidence:
        l5_note += ("；条目另有 `ruling10_conditions_evidence` %d 条**证据散文**，本判据**不读**它"
                    "（裁定 27⑤ 建议 B 让布尔断言键与证据键不共用 `condN` 前缀；A 收窄后共用也无害）"
                    % n_evidence)
    checks.add("L5", "裁定 10 五条准入逐条核对（门禁读的五个精确键全为 true）",
               not missing and not not_true,
               {"ruling10_conditions": {k: conds.get(k) for k in cond_keys},
                "missing": missing, "not_true": not_true,
                "keys_from_gate_source": from_gate, "n_evidence_prose_keys": n_evidence},
               {k: True for k in cond_keys},
               note=l5_note)

    # ---- L6（裁定 27② 同源收窄）：照抄门禁的读法 —— `cosign.by` 非空 + `cosign.fact_basis is True` ----
    # 旧判据认 A 自造的一串 legacy 键名（countersigned_by / approved_by_d / ...），门禁一个都不读。
    # 那会造成「A 说会签齐了、门禁判 cosign_missing」的两张皮。裁定 16.4 原文「由 B 写、D 会签」，
    # 门禁在会签缺失/不成立时**显式拒受理**（不是静默忽略），A 侧照抄同一读法。
    cs = entry.get("cosign")
    cs = cs if isinstance(cs, dict) else {}
    cs_by = str(cs.get("by") or "").strip()
    legacy = sorted(k for k in COUNTERSIGN_KEYS if k != "cosign" and entry.get(k))
    checks.add("L6", "D 会签成立（门禁读法：`cosign.by` 非空 + `cosign.fact_basis is True`）",
               bool(cs_by) and cs.get("fact_basis") is True,
               {"cosign.by": cs_by or None, "cosign.fact_basis": cs.get("fact_basis"),
                "cosign.verifier": cs.get("verifier"),
                "legacy_countersign_keys_门禁不读": legacy or None},
               {"cosign.by": "非空（且不得是 B 自己）", "cosign.fact_basis": True},
               note="裁定 16.4：条目「由 B 写、**D 会签**」，B 不能自签。门禁在 `cosign` 缺失或不成立时判 "
                    "`cosign_missing`（ic_status 保持原判）⇒ A 侧必须用同一读法，否则会放过真缺口"
                    + (f"；条目里还有 legacy 会签字段 {legacy}，门禁**不读**它们，只作历史留痕" if legacy else ""))

    # ---- L6b（09-29 追加，裁定 25 / DR-008 决定 7，**非 blocking**）----
    # 决定 7 明文：会签的 gate_build 与当前 GATE_BUILD 不一致时**不拒判**（否则死锁：条目只能在代码
    # 改完之后写，写的那一刻 D 的会签必然还锚在旧 build 上）。裁定 25 更正了 D 自己 裁定 17.5 的严格读法：
    # 意图是「不得拿旧 build 的会签当新 build 的通行证」，不是「build 字面必须相等」。
    # ⇒ 本条只把**可核事实**回显出来，并让它成为引用纪律的一部分（裁定 27：会签锚在哪个 build 上
    #   是可核事实，必须随数字一起走）。A 早前计划把它做成 blocking，经复核裁定 25 后**撤销**该计划。
    facts = cosign_facts or {}
    matches = facts.get("cosign_build_matches")
    checks.add("L6b", "会签 build vs live 门禁 build（只回显，按决定 7 **不拒判**）",
               matches is not False,
               {"cosign.gate_build_at_cosign": facts.get("cosign_gate_build"),
                "cosign.gate_version_at_cosign": facts.get("cosign_gate_version"),
                "live_gate_build": facts.get("live_gate_build"),
                "cosign_build_matches": matches},
               {"语义": "matches=False 时门禁照样受理，但必须回显 + 标记「D 须重跑 verifier 复签」"},
               blocking=False,
               note=("" if matches is not False else
                     "会签仍锚在旧 build ⇒ 门禁裁定里 `cosign_build_matches=false`。按 裁定 25 护栏①②："
                     "① 该臂须计入 `summary.pending_cosign_reverify`（见 B7），不得直接算「已免罪」；"
                     "② B 换上 D 备好的复签块（tmp/agentD_review_20260929/"
                     "D_cosign_block_for_registry.json，锚 f19f61341cbe）后必须**重出一次**表把桶清零"
                     "（「会签—重判」是两轮）。引用 25/22/1 时必须同时注明本事实（裁定 27）。"))

    declared = entry.get("sha256")
    actual = _sha256(probe_path) if (probe_path and probe_path.is_file()) else None
    if declared and actual:
        checks.add("L7", "探针产物 sha256 与登记一致", declared == actual, actual, declared)
    else:
        checks.add("L7", "探针产物 sha256 与登记一致", True,
                   f"declared={'有' if declared else '无'} / actual={'有' if actual else '无'}",
                   "（未声明或文件缺失，不作阻断，见 L2）", blocking=False)

    kind = str(entry.get("probe_kind") or "")
    blown = entry.get("disputed_value")
    ok_kind = bool(kind) and kind != "reblown_single_source"
    checks.add("L8", "`probe_kind` 走 裁定 10 通道（不是争议带重测通道）", ok_kind,
               {"probe_kind": kind or "（未写）", "disputed_value": blown},
               "非 reblown_single_source；目标臂 blown=0.212 必然在 (0.03,0.08) 带外",
               blocking=False,
               note="现册 `_doc` 的「带外 >0.08 一律不受理」只对 reblown_single_source 成立，"
                    "照抄会把 裁定 16.4 的条目永久挡住（移交单 §4）")

    # ---- L9（09-29 追加）：条目声明的 scope 能不能在门禁里**真正命中** ----
    key_is_sha = bool(key and SHA256_RE.match(str(key)))
    scope = str(entry.get("scope") or ("artifact" if key_is_sha else "arm"))
    impl, art_rel, _row = target_arm_impl(repo_root, b_doc or {})
    known = _tuple_of_str(gate_src, "KNOWN_BLOWN_IMPLS") if gate_src else None
    obs = {"scope": scope, "key_is_sha256": key_is_sha, "target_plain_artifact": art_rel,
           "blown_metric_impl": impl,
           "KNOWN_BLOWN_IMPLS": (list(known) if known is not None else "（门禁源码不可读）")}
    if scope == "arm":
        checks.add(
            "L9", "条目 `scope` 能在门禁里真正命中（不判 `scope_requires_known_impl`）",
            bool(impl) and (known is None or impl in known), obs,
            {"规则": "scope=arm ⇒ 被裁定产物必须自带 KNOWN_BLOWN_IMPLS 里的指纹",
             "否则": "改用 scope=artifact，或走祖父册 + 显式写明豁免判据是 裁定 10 五条准入而非指纹"},
            note="门禁的臂级豁免前置是 `scope==\"arm\" and impl_status != \"known\"` 当场拒绝；目标臂的权威 "
                 "plain 产物 blown_metric_impl=null（missing_legacy_grandfathered）⇒ 照抄现册 stdfloor 那条的 "
                 "scope=arm **必然不生效**。这条拒绝路径已被 D 于 09-29 独立重判实测复现（stdfloor 的**留档**"
                 "产物：tmp/agentD_review_20260929/regate48.json；B 表命中的是带指纹的 reblown 产物）。")
    else:
        checks.add(
            "L9", "条目 `scope` 能在门禁里真正命中（不判 `scope_requires_known_impl`）", True, obs,
            "scope != arm；或 scope == arm 且产物自带已知指纹",
            note=("" if key_is_sha else
                  "能命中，但 `scope=artifact` + **臂名键**绕过了臂级豁免的指纹前置（同臂任何产物、含无指纹的"
                  "旧留档都会被一并豁免），与门禁防「一次重测连带洗白历史」的设计意图冲突 ⇒ 请 D 会签时明确"
                  "是否接受（移交单 §5 的建议是走祖父册 + 显式 scope）。"))
    return entry


def check_b_table(checks: Checks, b_path: Path, b_doc_in=None,
                  cosign_facts: dict | None = None) -> dict:
    doc = _load(b_path) if b_doc_in is None else b_doc_in
    if "__load_error__" in doc:
        checks.add("B0", f"B 权威表可读（{b_path}）", False, doc["__load_error__"], "可解析的 JSON")
        return {}
    ident = (doc.get("gate_version"), doc.get("gate_build"), doc.get("gate_spec_sha256"))
    checks.add("B0", f"B 权威表可读（{b_path}）", True,
               f"{ident[0]}/{ident[1]}/spec {ident[2]}", "可解析的 JSON")

    cit = (doc.get("summary") or {}).get("citable") or {}
    checks.add("B1", "B 表 `NOT_CITABLE_measurement_invalid == 1`（裁定 2 的硬闸）",
               cit.get("NOT_CITABLE_measurement_invalid") == 1,
               cit.get("NOT_CITABLE_measurement_invalid"), 1)

    obs = {"citable": cit.get("citable_with_sensitivity_band"),
           "valid_zero_success": cit.get("no_controlled_success_to_cite"),
           "invalid": cit.get("NOT_CITABLE_measurement_invalid")}
    checks.add("B2", "B 表三分类 == 25 / 22 / 1（免罪后，增补五 §3 / §7）", obs == REQUIRED_POST,
               obs, REQUIRED_POST)

    arms = doc.get("arms") or []
    tgt = next((a for a in arms if a.get("arm") == TARGET_ARM), {})
    tgt_exo = tgt.get("probe_exoneration")
    # 裁定 19 之后 B 可能把 probe_exoneration 从裸字符串改成对象；两种写法都要认
    tgt_exonerated = (tgt_exo == "exonerated"
                      or (isinstance(tgt_exo, dict) and tgt_exo.get("status") == "exonerated"))
    checks.add("B3", f"`{TARGET_ARM}` 已被免罪（不再是 NOT_CITABLE）",
               bool(tgt) and tgt_exonerated
               and tgt.get("citable") != "NOT_CITABLE_measurement_invalid",
               {"ic_status": tgt.get("ic_status"), "probe_exoneration": tgt.get("probe_exoneration"),
                "citable": tgt.get("citable"), "mean_blown_frames_frac": tgt.get("mean_blown_frames_frac")},
               {"probe_exoneration": "exonerated", "citable": "!= NOT_CITABLE_measurement_invalid"})

    sums = {"arms": len(arms), "episodes": 0, "raw_success": 0, "controlled_success": 0,
            "insufficient_lift": 0, "flick": 0, "over_lift": 0, "provisional_pass": 0}
    for a in arms:
        sums["episodes"] += a.get("episodes") or 0
        for k in ("raw_success", "controlled_success", "insufficient_lift", "flick",
                  "over_lift", "provisional_pass"):
            v = a.get(k)
            sums[k] += v if isinstance(v, int) else 0
    checks.add("B4", "计数层保持构建不变（受控 135 / insuff 235 / flick 7 / raw 377）",
               sums == BUILD_INVARIANT_TOTALS, sums, BUILD_INVARIANT_TOTALS)

    # ---- B5（裁定 18.3 重写 + 18.4 升为 blocking）------------------------------------
    # 原判据 `required="verified_ok"` 被 D **驳回**：照它「修」等于撤销 裁定 13 对该臂的保留解除，
    # 属会导致退步的建议。D 实测两份产物各自都对（reblown 带指纹 ⇒ probe_exonerated；
    # 主目录旧产物无指纹 ⇒ scope=arm 按设计拒受理 ⇒ verified_ok），根因是标签粒度不够（裁定 19）
    # + 产物归属不唯一（裁定 18.2，由 B6 对账）。
    std = next((a for a in arms if a.get("arm") == STDFLOOR_ARM), {})
    std_file = _norm_artifact(std.get("file"))
    std_kind = arm_probe_kind(std)
    std_blown = std.get("mean_blown_frames_frac")
    band = DISPUTED_BAND
    in_band = isinstance(std_blown, (int, float)) and not isinstance(std_blown, bool) \
        and band[0] <= float(std_blown) <= band[1]
    chain_end = bool(std_file) and not any(
        _norm_artifact(a.get("supersedes")) == std_file
        for a in arms if isinstance(a, dict) and a.get("arm") != STDFLOOR_ARM)
    b5_terms = {
        "ic_status==probe_exonerated": std.get("ic_status") == "probe_exonerated",
        f"回显 probe_kind=={PROBE_KIND_REBLOWN}（裁定 19）": std_kind == PROBE_KIND_REBLOWN,
        "被裁定产物是 supersedes 链末端（裁定 18.2）": chain_end,
        f"blown ∈ 争议带 {list(band)}": in_band,
    }
    checks.add("B5", f"`{STDFLOOR_ARM}` 的 `probe_exonerated` 四个前提同时成立（裁定 18.3）",
               all(b5_terms.values()),
               {"terms": b5_terms, "ic_status": std.get("ic_status"),
                "mean_blown_frames_frac": std_blown, "file": std.get("file"),
                "supersedes": std.get("supersedes")},
               {"全部为真": list(b5_terms)},
               note="裁定 18.1：B 判的是 reblown/ 链末端产物（带指纹、blown 0.04 **在争议带内**）"
                    "⇒ `probe_exonerated` 是**对的**，A 移交单 §2.3 的诊断已被更正、不得再引。"
                    "本条现在验的是「这个标签的四个前提都还在」，其中 probe_kind 回显要等 v1.5（裁定 19）。")

    summary = doc.get("summary") or {}

    # ---- B7 / B7b（09-29 追加，裁定 25 护栏① / DR-D22，**均非 blocking**）--------------
    # `cosign_build_matches=false` 期间，该臂必须计入 summary 的**独立桶**，不得直接算「已免罪」；
    # B 换上 D 的复签块并重出表后，该桶应清零（护栏②：「会签—重判」是两轮）。执行人 **B**，
    # A 只回显不代改。B7 按**臂**判（不是按「桶空不空」判）：桶里出现别的臂是 B 的口径选择，
    # A 无权据此挡 B；A 只核「目标臂在不在桶里」与它自己的会签状态是否一致。
    facts = cosign_facts or {}
    matches = facts.get("cosign_build_matches")
    bucket = summary.get(PENDING_COSIGN_BUCKET)
    bucket_arms = (bucket.get("arms") if isinstance(bucket, dict)
                   else (list(bucket) if isinstance(bucket, list) else [])) or []
    tgt_in_bucket = TARGET_ARM in bucket_arms
    row_matches = tgt.get("probe_exoneration_cosign_build_matches") if isinstance(tgt, dict) else None
    if matches is False:
        b7_ok = tgt_in_bucket
        b7_req = (f"会签 build != live build ⇒ `{TARGET_ARM}` **必须在** summary.{PENDING_COSIGN_BUCKET} 里")
    else:
        b7_ok = not tgt_in_bucket
        b7_req = (f"会签已锚在 live build ⇒ `{TARGET_ARM}` **必须不在** summary.{PENDING_COSIGN_BUCKET} 里")
    checks.add("B7", f"目标臂的 `{PENDING_COSIGN_BUCKET}` 归属与其会签状态一致（裁定 25 护栏①）",
               b7_ok,
               {"cosign_build_matches（A 从册子算）": matches,
                "B 表回显 probe_exoneration_cosign_build_matches": row_matches,
                "target_arm_in_bucket": tgt_in_bucket,
                "bucket": bucket, "live_gate_build": facts.get("live_gate_build"),
                "cosign_gate_build": facts.get("cosign_gate_build")}, b7_req, blocking=False,
               note="**非 blocking**：DR-008 决定 7 明文 build 不一致**不拒判**，桶归属是「报表口径」，"
                    "不是「免罪成不成立」。执行人 B；A 已把这条可核事实随数字一起带出（L6b + 表 meta 的 "
                    "`cosign_*` 回显），引用纪律见 裁定 27。")

    # B7b：桶的判据必须是**三值感知**的。门禁只在 裁定 10（clip）通道里产出
    # `cosign_build_matches`；reblown 通道**从不要求 D 会签**（`cosign_missing` 这条拒绝路径只存在于
    # `_clip_channel_precheck` 里），所以那些臂的字段值恒为 null。若桶的判据写成 `is not True`
    # 而不是 `is False`，这些臂会被**永久**关在桶里 —— `zero_condition`（换上复签块）对它们
    # 根本不可满足，因为它们本来就没有、也不需要有会签块。
    tri_state_offenders = [a.get("arm") for a in arms
                           if isinstance(a, dict) and a.get("arm") in bucket_arms
                           and a.get("probe_exoneration_cosign_build_matches") is None]
    checks.add("B7b", f"`{PENDING_COSIGN_BUCKET}` 的判据是三值感知（`is False`，不是 `is not True`）",
               not tri_state_offenders,
               {"bucket_arms": bucket_arms,
                "arms_with_matches_null（该通道本就不要求会签）": tri_state_offenders,
                "bucket_criterion": (bucket.get("criterion") if isinstance(bucket, dict) else None),
                "bucket_zero_condition": (bucket.get("zero_condition") if isinstance(bucket, dict) else None)},
               {"桶里不得有": "probe_exoneration_cosign_build_matches is None 的臂",
                "理由": "null = 「该通道不要求会签」，False 才是「待复签」；两者混为一谈会让桶永远清不空"},
               blocking=False,
               note="来历：B 表 **11:45** 版的判据写成 `is not True`，把 stdfloor 关进了桶里 —— 它走 "
                    "reblown_single_source 通道，门禁**从不**为该通道产出会签字段（`cosign_build=null`、"
                    "`matches=null`），按那版判据它**永远**出不了桶，与 裁定 24①（降级 stdfloor = 撤销 "
                    "裁定 13，属退步）冲突。A 提请后 **B 已于 11:48 收成 `is False`** 并单列 "
                    "`cosign_not_required_arms`，修法与建议一致（D 在 裁定 29 §3 复核改判 CLOSED）。"
                    "本条现在的作用是**回归护栏**：防止将来又把 null 读成「待复签」。"
                    "详见 docs/a_handoff_to_b_pending_bucket_tristate_20260929.md。**A 不改 B 的文件。**")

    # ---- B8（09-29 追加，裁定 24④⑤ / DR-D16，blocking）---------------------------------
    # 两条豁免通道的**引用条件不同**（reblown_single_source 带 ±0.005 敏感带；clip_at_train_absmax 带
    # 「C=train-absmax、逐局裁定不变」），共用裸标签会让引用条件无从判断。裁定 24⑤ 进一步要求：
    # 任何对账工具必须**按 probe_kind 分组比**，不得直接比 `probe_exonerated` 计数 ⇒ B 表必须可分组，
    # 否则 A 侧的 P7 无从计算（这是 A 能履行 裁定 24⑤ 的前提，所以 blocking）。
    by_kind = summary.get("probe_exoneration_by_kind")
    exo_rows = [a for a in arms if isinstance(a, dict) and a.get("ic_status") == "probe_exonerated"]
    per_kind: dict[str, int] = {}
    no_kind_arms = []
    for a in exo_rows:
        k = arm_probe_kind(a)
        if not k:
            no_kind_arms.append(a.get("arm"))
        else:
            per_kind[k] = per_kind.get(k, 0) + 1
    tgt_kind = arm_probe_kind(tgt) if isinstance(tgt, dict) else None
    b8_terms = {
        "每条 probe_exonerated 臂都回显 kind（裁定 19 / DR-D16）": not no_kind_arms,
        f"summary.probe_exoneration_by_kind 与逐臂 kind 计数一致":
            isinstance(by_kind, dict) and {k: v for k, v in by_kind.items() if v} == per_kind,
        f"目标臂若被免罪 ⇒ kind 必须是 {PROBE_KIND_CLIP}（裁定 24⑤）":
            (tgt_kind == PROBE_KIND_CLIP) if (tgt.get("ic_status") == "probe_exonerated") else True,
        f"stdfloor 若被免罪 ⇒ kind 必须是 {PROBE_KIND_REBLOWN}（裁定 24⑤）":
            (std_kind == PROBE_KIND_REBLOWN) if (std.get("ic_status") == "probe_exonerated") else True,
    }
    checks.add("B8", "两条豁免通道在 B 表上**可区分**（臂级回显 kind + summary 按 kind 分桶）",
               all(b8_terms.values()),
               {"terms": b8_terms, "probe_exoneration_by_kind": by_kind,
                "per_arm_kind_counts": per_kind, "arms_missing_kind": no_kind_arms,
                "target_arm_kind": tgt_kind, "stdfloor_kind": std_kind,
                "n_probe_exonerated": len(exo_rows)},
               {"全部为真": list(b8_terms)},
               note="裁定 24⑤ 的「1 对 2」问题：A 的 `VALID_probe_exonerated` **只**对应 "
                    f"`{PROBE_KIND_CLIP}`，B 的 `probe_exonerated` 含两条通道 ⇒ 两表「被豁免臂数」"
                    "**必然差 1，属设计差异不是缺陷**。前提是本条成立（能按 kind 分组），A 侧对账在 P7。")
    return doc


def check_attribution(checks: Checks, root: Path, a_path: Path, b_doc: dict, a_doc_in=None) -> None:
    """B6（裁定 18.2 的对账面）：A 与 B 是不是在比**同一份产物**。

    D 指出的真缺陷：同一臂名，B 的表指向 `supersedes` 链末端、A 的表固定指主目录旧产物 ⇒
    「计数层逐格相同」成立只是因为重测恰好复现了同组计数（运气不是机制）。换一个「重测后计数变了」的臂，
    两表会在**计数层**分叉，而逐臂比数值的对账抓不到。所以归属对账必须是 blocking（裁定 18.4 同理）。
    """
    a_doc = _load(a_path) if a_doc_in is None else a_doc_in
    if not isinstance(a_doc, dict) or "__load_error__" in a_doc:
        checks.add("B6", "A 表可读（产物归属对账需要它）", False,
                   a_doc.get("__load_error__") if isinstance(a_doc, dict) else "非 JSON 对象",
                   f"可读的 arms_summary（{a_path}）")
        return
    a_meta = a_doc.get("meta") or {}
    arm_paths = ((a_meta.get("artifact_attribution") or {}).get("arm_paths") or {})
    if not arm_paths:
        checks.add("B6", "A 表回显每臂被裁定产物路径 + sha256（裁定 18.2）", False,
                   {"schema_version": a_meta.get("schema_version"),
                    "meta.artifact_attribution.arm_paths": "缺失"},
                   "arm_paths 覆盖全部臂，每项带 adjudicated_artifact + sha256",
                   note="A 的表由 scripts/summarize_lerobot_act_arms.py 生产（schema_version 3 起回显归属）；"
                        "现值表 = runs/infra/lerobot_act_env_20260928/attribution/arms_summary_v3.json")
        return
    b_rows = {a.get("arm"): a for a in (b_doc.get("arms") or []) if isinstance(a, dict)}
    mismatch, missing_sha, n_compared = [], [], 0
    for arm, info in arm_paths.items():
        b_row = b_rows.get(arm)
        if not isinstance(b_row, dict) or not isinstance(info, dict):
            continue
        n_compared += 1
        a_file = _norm_artifact(info.get("adjudicated_artifact"))
        b_file = _norm_artifact(b_row.get("file"))
        if not info.get("sha256"):
            missing_sha.append(arm)
        if a_file != b_file:
            mismatch.append({"arm": arm, "a_adjudicated_artifact": a_file, "b_file": b_file,
                             "a_attribution_kind": info.get("attribution_kind"),
                             "b_supersedes": _norm_artifact(b_row.get("supersedes"))})
    checks.add("B6", "A / B 两表逐臂指向**同一份**被裁定产物（裁定 18.2 的对账）",
               not mismatch and not missing_sha and n_compared > 0,
               {"n_compared": n_compared, "n_mismatch": len(mismatch),
                "mismatch": mismatch[:12], "n_missing_sha256": len(missing_sha),
                "missing_sha256_arms": missing_sha[:12]},
               {"n_mismatch": 0, "n_missing_sha256": 0, "n_compared": "= A 表臂数"},
               note="归属不一致会让**计数层**对账失效（比数值对得上、比的却不是同一份东西），"
                    "这比分类层差 1 臂严重 ⇒ 裁定 18.4 要求 blocking")
def check_gate_code(checks: Checks, root: Path, gate_src: str, b_doc: dict,
                    gate_row: dict | None = None, gate_row_err: str | None = None) -> None:
    """G1 / G2 / G3：裁定 10 的免罪通道在**门禁**里是否真的可达。

    09-29 的重构（裁定 27）：G1/G2 原本**都是文本锚点判读**。B 落地 v1.5（DR-008）后两条锚点
    当场失效（带检查改成 `band_checked = kind not in BAND_EXEMPT_PROBE_KINDS`、晋级闸改成
    `EXONERATION_PROMOTION_SOURCES[probe_kind]` 查表），A 的闸于是对着一个**已经修好**的门禁报
    blocking FAIL —— 裁定 27 定性为「**恒假的闸等于没有闸**」。现在的分工：
      G2 = **调门禁本尊实测**（blocking，裁定 27④）。不读源码、不认锚点，是唯一不会被重构骗到的判据。
      G1 / G3 = 原来的两条文本锚点，**降级为非 blocking 诊断**（锚点已更新到认得 v1.5 的两种新形状）。
    冲突时一律以 G2 为准。A 只读 B 的源码、只在内存里 import 跑 `judge_file`，**不写任何文件**、不改门禁。
    """
    _impl, _art_rel, row = target_arm_impl(root, b_doc or {})
    raw_blown = row.get("mean_blown_frames_frac")
    blown = (float(raw_blown)
             if isinstance(raw_blown, (int, float)) and not isinstance(raw_blown, bool)
             else TARGET_ARM_BLOWN)

    # ---- G2（blocking）：端到端实测，门禁本尊判目标臂的 plain 产物 ----
    g2_name = ("端到端实测：门禁本尊判目标臂 plain 产物 → 裁定 10 免罪**真的生效**（裁定 27④）")
    if gate_row is None and gate_row_err is None:
        gate_row, gate_row_err = run_gate_on_target(root)
    if gate_row is None:
        checks.add("G2", g2_name, False,
                   {"run_gate_on_target_error": gate_row_err or "（无返回）"},
                   "能端到端跑通门禁并拿到目标臂的裁定行",
                   note="实测不可用（门禁/产物缺失、加载异常）⇒ **没有证据**证明通道可达。本条 blocking："
                        "裁定 27④ 要求以实测为准，实测跑不起来就等于闸失去唯一可信判据，不能默认放行。")
    else:
        ic = gate_row_ic_status(gate_row)
        exo = gate_row.get("probe_exoneration")
        exo = exo if isinstance(exo, dict) else {}
        terms = {
            "input_contract.status == probe_exonerated": ic == "probe_exonerated",
            "measurement_valid is True": gate_row.get("measurement_valid") is True,
            "probe_exoneration.status == exonerated": exo.get("status") == "exonerated",
            f"probe_kind == {PROBE_KIND_CLIP}（裁定 10 通道，不是争议带通道）":
                exo.get("probe_kind") == PROBE_KIND_CLIP,
            "band_checked is False（免争议带检查 ⇒ 没被判 out_of_band_refused）":
                exo.get("band_checked") is False,
        }
        checks.add("G2", g2_name, all(terms.values()),
                   {"terms": terms, "ic_status": ic,
                    "measurement_valid": gate_row.get("measurement_valid"),
                    "gate_pass": gate_row.get("gate_pass"),
                    "exo_status": exo.get("status"), "probe_kind": exo.get("probe_kind"),
                    "band_checked": exo.get("band_checked"),
                    "mean_blown_frames_frac": blown,
                    "registered_clip_C": exo.get("registered_clip_C"),
                    "artifact_train_absmax": exo.get("artifact_train_absmax"),
                    "ruling10_conditions": exo.get("ruling10_conditions"),
                    "cosign_build_current": exo.get("cosign_build_current"),
                    "cosign_build_matches": exo.get("cosign_build_matches"),
                    "gate_version": gate_row.get("gate_version"),
                    "gate_build": gate_row.get("gate_build")},
                   {"全部为真": list(terms)},
                   note="做法：`importlib` 加载 scripts/b_gate_controlled_success.py，对目标臂的**权威 plain "
                        "产物**调 `judge_file`（真册子、`json_out=None` ⇒ 不写文件）。这条是 G1/G3 文本诊断的"
                        "**上位判据**，冲突时以本条为准（裁定 27：D 的实证结论优先，A 更新判据请以实测为准，"
                        "不要照文本扫描改）。注意 v1.5 下 `judge_file` **已就地晋级**，所以这里读的是观察值；"
                        "「底层原本是 violated」由 D 的 verifier 用还原法另判，A 不重复实现。")

    # ---- G1（非 blocking 诊断）：晋级闸是否允许 violated → probe_exonerated ----
    if not gate_src:
        checks.add("G1", "门禁源码可读（G1/G3 文本诊断的锚点所在）", True,
                   f"{DEFAULT_B_GATE} 读不到", "可读", blocking=False,
                   note="读不到就不判 G1/G3；G2 是实测、B1–B3 看 B 表结果，都仍是硬闸")
        return
    allows = promotion_allows_violated(gate_src)
    g1_req = {"要求": f"晋级闸允许 `violated → probe_exonerated`（{PROBE_KIND_CLIP} 通道）",
              "理由": f"目标臂 blown={blown} > 0.05 ⇒ 底层 ic_status 恒为 violated"}
    g1_obs = {"promotion_allows_violated": allows, "target_arm_blown": blown,
              "anchor": ("EXONERATION_PROMOTION_SOURCES（v1.5 形状）" if allows is not None and
                         re.search(r"^EXONERATION_PROMOTION_SOURCES", gate_src, re.MULTILINE)
                         else "ic_status in (...) 转移白名单（v1.4 形状）")}
    checks.add("G1", "【诊断】晋级闸允许 `violated → probe_exonerated`（文本锚点，认 v1.4/v1.5 两种形状）",
               True if allows is None else allows, g1_obs, g1_req, blocking=False,
               note="**非 blocking**（裁定 27）：文本锚点会随 B 重构失真，v1.5 落地时它已经假红过一次。"
                    "锚点认不出结构（None）时同样只 WARN。真判据看 G2 实测。")

    # ---- G3（非 blocking 诊断）：争议带检查是否按 probe_kind 分通道 ----
    band = _tuple_of_float(gate_src, "DISPUTED_BLOWN_BAND")
    gated = band_check_is_kind_gated(gate_src)
    covers = bool(band and band[0] <= blown <= band[1])
    g3_obs = {"DISPUTED_BLOWN_BAND": (list(band) if band else None), "target_arm_blown": blown,
              "band_check_is_kind_gated": gated, "band_covers_target": covers}
    g3_req = {"二选一": "带检查按 probe_kind 分通道（v1.5：BAND_EXEMPT_PROBE_KINDS 白名单），"
                        "或带上限已覆盖目标臂 blown"}
    checks.add("G3", "【诊断】带外受理通道对目标臂可达（文本锚点，认 v1.4/v1.5 两种形状）",
               True if (gated is None or covers) else (gated or covers),
               g3_obs, g3_req, blocking=False,
               note="**非 blocking**（裁定 27）：原 G2 的文本判据。v1.5 用白名单常量 "
                    "`BAND_EXEMPT_PROBE_KINDS` 而不是 `if probe_kind ...` 分支，旧锚点认不出 ⇒ 假红。"
                    "真判据看 G2 实测（`band_checked is False` 就是这条的直接证据）。")


def check_a_table(checks: Checks, a_path: Path, b_doc: dict, a_doc_in=None) -> None:
    doc = _load(a_path) if a_doc_in is None else a_doc_in
    if "__load_error__" in doc:
        checks.add("P0", f"A 权威表可读（{a_path}）", False, doc["__load_error__"], "可解析的 JSON")
        return
    meta = doc.get("meta") or {}
    checks.add("P0", f"A 权威表可读（{a_path}）", True,
               f"schema_version={meta.get('schema_version')}", "可解析的 JSON")

    want_build = (b_doc.get("gate_build") if b_doc else None)
    got_build = meta.get("gate_build")
    got_build = got_build[0] if isinstance(got_build, list) and got_build else got_build
    checks.add("P1", "A 表已迁到当前权威构建（迁移确实发生过）",
               bool(want_build) and got_build == want_build, got_build, want_build)

    den = meta.get("denominators") or {}
    post = {k: (den.get("post_probe_exoneration") or {}).get(k) for k in REQUIRED_POST}
    pre = {k: (den.get("pre_probe_exoneration") or {}).get(k) for k in REQUIRED_PRE}
    checks.add("P2", "免罪后三分类 == 25 / 22 / 1", post == REQUIRED_POST, post, REQUIRED_POST)
    checks.add("P3", "免罪前三分类 == 24 / 22 / 2（同一张表两套分母都要在）",
               pre == REQUIRED_PRE, pre, REQUIRED_PRE)

    row = next((a for a in (doc.get("arms") or []) if a.get("arm") == TARGET_ARM), {})
    checks.add("P4", f"`{TARGET_ARM}` 记 `VALID_probe_exonerated`（不得简写 valid）",
               row.get("validity_class") == "VALID_probe_exonerated",
               row.get("validity_class"), "VALID_probe_exonerated")

    inv = meta.get("invalid_arms") or []
    checks.add("P5", f"唯一 INVALID == `{REPLAN1_ARM}`",
               len(inv) == 1 and inv[0].get("arm") == REPLAN1_ARM,
               [i.get("arm") for i in inv], [REPLAN1_ARM])

    tot = (meta.get("totals") or {}).get("scope_all_48_products_supervisor_reconcile") or {}
    obs = {k: tot.get(k) for k in BUILD_INVARIANT_TOTALS}
    checks.add("P6", "48 臂合计仍是构建不变的那组数", obs == BUILD_INVARIANT_TOTALS,
               obs, BUILD_INVARIANT_TOTALS)

    # ---- P7（09-29 追加，裁定 24⑤ / DR-D21，postcheck blocking）-------------------------
    # 裁定 24⑤：A 的 `VALID_probe_exonerated` 与 B 的 `probe_exonerated` **不是同一概念**，v1.5 后
    # 长期是 1 对 2（A = 「原判 invalid 被救回」，只走 clip 通道；B = ic_status 标签，含两条通道）。
    # A 的义务：① stdfloor 在 A 表里维持 `valid`，但**另列一列**回显 `probe_kind=reblown_single_source`；
    # ② 任何对账必须**按 probe_kind 分组比**，不得直接比 `probe_exonerated` 计数。
    a_rows = [r for r in (doc.get("arms") or []) if isinstance(r, dict)]
    b_rows = {a.get("arm"): a for a in ((b_doc or {}).get("arms") or []) if isinstance(a, dict)}
    a_exo = [r for r in a_rows if r.get("validity_class") == "VALID_probe_exonerated"]
    kind_col_missing = [r.get("arm") for r in a_rows if "probe_kind" not in r]
    b_exo = {name: arm_probe_kind(row) for name, row in b_rows.items()
             if row.get("ic_status") == "probe_exonerated"}
    kind_mismatch = [{"arm": n, "a_probe_kind": next(
                          (r.get("probe_kind") for r in a_rows if r.get("arm") == n), "（A 表无此臂）"),
                      "b_kind": k}
                     for n, k in b_exo.items()
                     if next((r.get("probe_kind") for r in a_rows if r.get("arm") == n), None) != k]
    wrong_channel = [r.get("arm") for r in a_exo if r.get("probe_kind") != PROBE_KIND_CLIP]
    n_clip = sum(1 for k in b_exo.values() if k == PROBE_KIND_CLIP)
    recon = meta.get("exoneration_reconciliation")
    p7_terms = {
        "A 表每臂都有 `probe_kind` 列（无豁免的臂为 null）": not kind_col_missing,
        "B 判 probe_exonerated 的臂，A 表回显同一 kind（按 kind 分组比）": not kind_mismatch,
        f"`VALID_probe_exonerated` 只对应 {PROBE_KIND_CLIP}": not wrong_channel,
        "A 的免罪臂数 == B 的 clip 通道臂数（**不比裸 probe_exonerated 计数**）": len(a_exo) == n_clip,
        "meta 显式登记「两表被豁免臂数必然差 1 是设计差异」": isinstance(recon, dict) and bool(recon),
    }
    checks.add("P7", "A 表按 `probe_kind` 分组对账（裁定 24⑤：`VALID_probe_exonerated` 只对应 clip 通道）",
               all(p7_terms.values()),
               {"terms": p7_terms, "a_n_VALID_probe_exonerated": len(a_exo),
                "b_n_probe_exonerated": len(b_exo), "b_n_clip_channel": n_clip,
                "design_difference": len(b_exo) - len(a_exo),
                "arms_missing_kind_column": kind_col_missing[:12],
                "kind_mismatch": kind_mismatch[:12], "wrong_channel_arms": wrong_channel[:12],
                "meta.exoneration_reconciliation": recon},
               {"全部为真": list(p7_terms), "design_difference": "= reblown 通道臂数（现值 1）"},
               note="两表在「多少臂被豁免」上**必然差 1，属设计差异不是缺陷**（裁定 24⑤）。"
                    "本条把「按 kind 分组比」变成可执行断言：直接比裸计数会把这个设计差异读成缺陷，"
                    "或者反过来把真缺陷读成设计差异。")


def report(checks: Checks, mode: str, gate_open: bool, extra: dict) -> None:
    for r in checks.rows:
        tag = "PASS" if r["pass"] else ("FAIL" if r["blocking"] else "WARN")
        line = f"[{tag}] {r['id']:<3} {r['name']}"
        print(line)
        if not r["pass"] or mode == "postcheck":
            print(f"          observed = {json.dumps(r['observed'], ensure_ascii=False)}")
            print(f"          required = {json.dumps(r['required'], ensure_ascii=False)}")
        if r["note"]:
            print(f"          note     = {r['note']}")
    label = "MIGRATION_GATE" if mode == "preflight" else "POST_MIGRATION_CHECK"
    print()
    print(f"{label}={'OPEN' if gate_open else 'CLOSED'}  "
          f"blocking_fail={checks.n_fail_blocking()}  warn={checks.n_warn()}  "
          f"total_checks={len(checks.rows)}")
    for line in extra.get("disposition", []):
        print(line)
    if not gate_open and mode == "preflight":
        print("处置：按 ADR-A-006 裁定 2 **不迁**；A 的 48 臂表维持**留档口径**不动，"
              "引用时带留档表的 `gate_version / gate_build`（见 --json-out 里的 "
              "`a_table_identity`），三分类写「免罪后 25/22/1」时必须同时标注 PENDING 状态。")
    if not gate_open and mode == "postcheck":
        print("处置：按裁定 2 **不迁并报回 D**；留档 arms_summary.json 未被本脚本改动。")
    for line in extra.get("lines", []):
        print(line)


# --------------------------------------------------------------------------------------
# 变异自检：证明这道闸有牙（合规 fixture 必须 OPEN，缺任一条必须 CLOSED）
# 全部 fixture 在内存里构造，**不写任何文件**；探针产物指向仓库内已存在的真实文件（只读）。
# --------------------------------------------------------------------------------------

SELFTEST_PROBE = ("runs/infra/lerobot_act_env_20260928/clipprobe/"
                  "official_act_truth20_trimdone0_minmax_k2_lr1e-5_s20k_seed0_clipC12p469445.json")

# G1/G2 的门禁源码 fixture（**冻结**的形状，不读 B 的实时文件 —— 否则 B 一修好，自检就跟着变，
# 回归套件失去意义）。`_V14_SHAPE` 复刻 v1.4 / b9379fdb1089 的三处锚点结构；实时状态看 preflight 本身。
_FIXTURE_GATE_V14_SHAPE = '''
KNOWN_BLOWN_IMPLS = ("52eae25ee2d7",)
DISPUTED_BLOWN_BAND = (0.03, 0.08)
    if exo and exo["status"] == "exonerated" and ic_status in ("verified_ok", "not_applicable_verified"):
        ic_status = "probe_exonerated"
    elif exo and exo["status"] in ("evidence_missing", "evidence_sha_mismatch"):
        ic_status = "probe_exoneration_invalid"
    if mean_blown is None or not (lo <= float(mean_blown) <= hi):
        out["status"] = "out_of_band_refused"
'''

# G1/G2 都已修好（转移白名单含 violated + 带外判据按 probe_kind 分通道）⇒ 自检的正例
_FIXTURE_GATE_FIXED = '''
KNOWN_BLOWN_IMPLS = ("52eae25ee2d7",)
DISPUTED_BLOWN_BAND = (0.03, 0.08)
    if exo and exo["status"] == "exonerated" and ic_status in ("verified_ok", "not_applicable_verified", "violated"):
        ic_status = "probe_exonerated"
    if mean_blown is None or (probe_kind == "reblown_single_source" and not (lo <= float(mean_blown) <= hi)):
        out["status"] = "out_of_band_refused"
'''

# 另一条解锁路径：不分通道，直接把带上限扩到覆盖 0.212（G2 应走 covers 分支通过）
_FIXTURE_GATE_BAND_WIDE = '''
KNOWN_BLOWN_IMPLS = ("52eae25ee2d7",)
DISPUTED_BLOWN_BAND = (0.03, 0.30)
    if exo and exo["status"] == "exonerated" and ic_status in ("verified_ok", "not_applicable_verified", "violated"):
        ic_status = "probe_exonerated"
    if mean_blown is None or not (lo <= float(mean_blown) <= hi):
        out["status"] = "out_of_band_refused"
'''

# 门禁正当重构、两个锚点都消失 ⇒ G1/G2 必须降级为 WARN 而不是 FAIL（不得误挡 B）
_FIXTURE_GATE_NOANCHOR = '''
KNOWN_BLOWN_IMPLS = ("52eae25ee2d7",)
DISPUTED_BLOWN_BAND = (0.03, 0.08)
    ic_status = _resolve_input_contract_status(exo, mean_blown)
'''

# B 实际落地的 v1.5 形状（DR-008）：白名单常量 + 查表晋级。旧锚点认不出它（裁定 27 的假红根因），
# 新锚点必须认得 ⇒ 这份 fixture 就是「锚点更新对了」的正例。
_FIXTURE_GATE_V15_SHAPE = '''
KNOWN_BLOWN_IMPLS = ("52eae25ee2d7",)
DISPUTED_BLOWN_BAND = (0.03, 0.08)
PROBE_KIND_REBLOWN = "reblown_single_source"
PROBE_KIND_CLIP_AT_TRAIN_ABSMAX = "clip_at_train_absmax"
BAND_EXEMPT_PROBE_KINDS = (PROBE_KIND_CLIP_AT_TRAIN_ABSMAX,)
RULING10_CONDITION_KEYS = ("cond1_C_equals_train_absmax",
                           "cond2_verdicts_and_counts_identical",
                           "cond3_diffs_enumerated_and_verdict_same",
                           "cond4_probe_path_C_build_recorded",
                           "cond5_scope_measurement_valid_only")
EXONERATION_PROMOTION_SOURCES = {
    PROBE_KIND_REBLOWN: ("verified_ok", "not_applicable_verified"),
    PROBE_KIND_CLIP_AT_TRAIN_ABSMAX: ("violated",),
}
    band_checked = kind not in BAND_EXEMPT_PROBE_KINDS
    allowed = EXONERATION_PROMOTION_SOURCES.get(exo.get("probe_kind"), DEFAULT_PROMOTION_SOURCES)
'''

# G2 是**实测**判据，自检里用注入的伪造 `judge_file` 返回行来证明它有牙（真跑时不注入）。
# 形状照 v1.5 实测行抄：`ic_status` 在 `input_contract.status`，豁免细节在 `probe_exoneration` 对象里。
_FIXTURE_GATE_ROW_EXONERATED = {
    "gate_version": "v1.5", "gate_build": "f19f61341cbe",
    "measurement_valid": True, "gate_pass": True, "field_class": "strict",
    "labels_reportable": True,
    "input_contract": {"status": "probe_exonerated", "mean_blown_frames_frac": TARGET_ARM_BLOWN,
                       "train_time_norm_absmax": TARGET_ARM_C, "in_disputed_band": False,
                       "violated": False, "probe_exonerated": True},
    "probe_exoneration": {"status": "exonerated", "probe_kind": PROBE_KIND_CLIP,
                          "band_checked": False, "scope": "artifact",
                          "registered_clip_C": TARGET_ARM_C,
                          "artifact_train_absmax": TARGET_ARM_C,
                          "cosign_build_current": "f19f61341cbe",
                          "cosign_build_matches": True,
                          "ruling10_conditions": {k: True for k in RULING10_KEYS_FALLBACK}},
}
# 反证：门禁还是 v1.4 行为（带检查硬编码 ⇒ out_of_band_refused、晋级闸不放 violated）。
# 文本锚点认不出 v1.5 时 A 曾经**看不见**这种状态；改成实测后它必须把闸关死。
_FIXTURE_GATE_ROW_V14_BEHAVIOUR = {
    "gate_version": "v1.4", "gate_build": "b9379fdb1089",
    "measurement_valid": False, "gate_pass": False, "field_class": "strict",
    "labels_reportable": True,
    "input_contract": {"status": "violated", "mean_blown_frames_frac": TARGET_ARM_BLOWN,
                       "violated": True, "probe_exonerated": False},
    "probe_exoneration": {"status": "out_of_band_refused", "probe_kind": PROBE_KIND_CLIP,
                          "band_checked": True, "scope": "artifact"},
}
# run() 的默认哨兵：用上面的合规伪造行（自检要可重复，不能依赖 live 门禁的状态）
_STUB = "stub"


def _fixture_arm_names() -> list[str]:
    """48 个臂名（1 号 = 目标臂、2 号 = stdfloor 臂），B 表与 A 表 fixture 共用，保证 B6 能对上。"""
    names = [f"_selftest_arm{i:02d}" for i in range(BUILD_INVARIANT_TOTALS["arms"])]
    names[1] = TARGET_ARM
    names[2] = STDFLOOR_ARM
    return names


def _fixture_path(arm: str, sub: str = "") -> str:
    return f"runs/_selftest/{sub}official_act_truth20_{arm}.json"


def _fixture_b_table(*, exonerate_target: bool, three_class: dict, stdfloor_status: str,
                     stdfloor_probe_kind: bool = True, stdfloor_chain_end: bool = True,
                     stdfloor_blown: float = 0.04, by_kind_summary: bool = True,
                     pending_bucket: list | None = None,
                     pending_matches: bool | None = False) -> dict:
    """合成一份 B 权威表：48 臂 × 20 局，计数层故意凑成 BUILD_INVARIANT_TOTALS（只为验判据，非真实分布）。

    每臂带 `file` / `supersedes`（裁定 18.2 的归属对账 B6 要用）；stdfloor 臂的 B5 三个前提
    （`probe_kind` 回显 / 链末端 / 争议带内）各留一个开关，供变异自检用。
    """
    names = _fixture_arm_names()
    arms = []
    for name in names:
        arms.append({"arm": name, "file": _fixture_path(name), "supersedes": None,
                     "episodes": 20, "raw_success": 0, "controlled_success": 0,
                     "insufficient_lift": 0, "flick": 0, "over_lift": 0, "provisional_pass": 0,
                     "ic_status": "verified_ok", "probe_exoneration": None,
                     "citable": "no_controlled_success_to_cite", "mean_blown_frames_frac": 0.0})
    lump = arms[0]
    for k in ("raw_success", "controlled_success", "insufficient_lift", "flick",
              "over_lift", "provisional_pass"):
        lump[k] = BUILD_INVARIANT_TOTALS[k]
    tgt = arms[1]
    tgt.update({"mean_blown_frames_frac": 0.212,
                "ic_status": "probe_exonerated" if exonerate_target else "violated",
                # 裁定 19 之后 B 可能把 probe_exoneration 对象化；fixture 直接用对象形式验 B3 的兼容性
                "probe_exoneration": ({"status": "exonerated", "probe_kind": "clip_at_train_absmax"}
                                      if exonerate_target else None),
                "citable": "citable_with_sensitivity_band" if exonerate_target
                else "NOT_CITABLE_measurement_invalid"})
    std = arms[2]
    std_main = _fixture_path(STDFLOOR_ARM)
    std_file = _fixture_path(STDFLOOR_ARM, "reblown/") if stdfloor_chain_end else std_main
    std.update({"file": std_file,
                "supersedes": std_main if stdfloor_chain_end else None,
                "mean_blown_frames_frac": stdfloor_blown,
                "ic_status": stdfloor_status,
                "probe_exoneration": (
                    ({"status": "exonerated", "probe_kind": "reblown_single_source"}
                     if stdfloor_probe_kind else "exonerated")
                    if stdfloor_status == "probe_exonerated" else None)})
    if not stdfloor_chain_end:
        arms[3]["supersedes"] = std_file          # 有别的产物取代它 ⇒ 它不是链末端
    # 臂级 kind 回显（v1.5 的真实字段名是 probe_exoneration_kind）——B8 / P7 都按它分组
    for a in arms:
        exo = a.get("probe_exoneration")
        a["probe_exoneration_kind"] = (exo.get("probe_kind") if isinstance(exo, dict)
                                       else None) or None
    by_kind: dict[str, int] = {}
    for a in arms:
        if a.get("ic_status") == "probe_exonerated" and a.get("probe_exoneration_kind"):
            by_kind[a["probe_exoneration_kind"]] = by_kind.get(a["probe_exoneration_kind"], 0) + 1
    summary = {"citable": {"citable_with_sensitivity_band": three_class["citable"],
                           "no_controlled_success_to_cite": three_class["valid_zero_success"],
                           "NOT_CITABLE_measurement_invalid": three_class["invalid"]},
               "ic_status": {"verified_ok": 45, "violated": 2, "probe_exonerated": 1}}
    if by_kind_summary:
        summary["probe_exoneration_by_kind"] = by_kind      # 裁定 24④ / DR-D16
    if pending_bucket is not None:
        summary[PENDING_COSIGN_BUCKET] = {"n": len(pending_bucket), "arms": list(pending_bucket),
                                          "criterion": "probe_exoneration == 'exonerated' 且 "
                                                       "probe_exoneration_cosign_build_matches is False"
                                                       "（三值：True=已复签 / False=待复签 / "
                                                       "None=通道不要求会签）"}   # 裁定 25 护栏①
        # B 的真实表就是这么做的：进桶的臂同时把**三值**字段回显出来，B7b 才判得出「不是 null 误进桶」
        for a in arms:
            if a.get("arm") in pending_bucket:
                # `pending_matches=None` 复刻 B 表 11:45 那一版的缺陷：把 matches 为 **null**
                # （= 该通道本就不要求会签）的臂也塞进桶里 —— B7b 就是为抓这个而设（S22b）
                a["probe_exoneration_cosign_build_matches"] = pending_matches
                a["probe_exoneration_cosign_build"] = ("b9379fdb1089" if pending_matches is False
                                                       else None)
    # `gate_spec_sha256` **故意不写真实指纹**（裁定 29 / DR-D28）：spec 轴哈希的是散文规格文档，
    # 可以在判据一字未动时被编辑（D 实测 35 分钟内移动 4 次）⇒ 它是**观测日志，不是钉子**。
    # 写死一个真实值 = 一颗过期地雷：哪天有人把「spec 必须匹配」当规则，自检就会假红。
    return {"gate_version": "v1.5", "gate_build": "f19f61341cbe",
            "gate_spec_sha256": SELFTEST_SPEC_NOT_A_NAIL,
            "git_commit": "selftest", "arms": arms, "summary": summary}


def _fixture_ledger(root: Path, *, countersign: bool, conds_true: bool, c_value: float,
                    probe_kind: str, scope: str = "artifact", cosign_build: str | None = None,
                    evidence_prose: bool = False, conds_bool_true_but_evidence_only: bool = False,
                    legacy_countersign_only: bool = False) -> dict:
    """合成一条免罪册条目。

    **形状取自真条目**（裁定 27③：判据类工具的反例必须取自真实产物形状）：
      - 布尔断言在 `ruling10_conditions`，键名 = 门禁常量 `RULING10_CONDITION_KEYS` 的五个精确键；
      - `evidence_prose=True` 时再加 `ruling10_conditions_evidence`，键名同样以 `condN` 打头但值是
        **证据散文 str** —— 这正是把 A 旧 L5 打成假红的东西，必须有自检档位覆盖它；
      - 会签用门禁读的 `cosign` 对象（`by` + `fact_basis`），legacy 键名单独留一档反证。
    """
    probe = root / SELFTEST_PROBE
    conds = {k: (True if conds_true else (i != 2))
             for i, k in enumerate(RULING10_KEYS_FALLBACK, start=1)}
    if conds_bool_true_but_evidence_only:
        # 布尔键全 false，但证据散文写得满满当当 ⇒ 散文**不能**替代布尔断言（L5 必须红）
        conds = {k: False for k in conds}
    entry = {
        # 默认 artifact：目标臂的 plain 产物没有 blown_metric_impl 指纹，scope=arm 会被门禁当场拒绝
        # （L9 就是为此而设，S11 是它的反证）。
        "scope": scope,
        "probe_kind": probe_kind,
        "arm": TARGET_ARM,
        "artifact": SELFTEST_PROBE,
        "sha256": _sha256(probe) if probe.is_file() else None,
        "ruling_ref": "增补五 裁定 16.4 + 裁定 10（selftest fixture）",
        "disputed_value": TARGET_ARM_BLOWN,
        "clip_C": c_value,
        "C": c_value,
        "target_artifact": TARGET_PLAIN_ARTIFACT,
        "gate_build": "e4f5ec887788",
        "gate_version": "v1.2.1",
        "reason": "selftest fixture",
        "ruling10_conditions": conds,
    }
    if evidence_prose:
        entry["ruling10_conditions_evidence"] = {
            "cond1": "train_time_norm_absmax=%s == probe clip C=%s；反证 C=5.0 见 supporting_artifacts[1]"
                     % (TARGET_ARM_C, TARGET_ARM_C),
            "cond2": "verdict_diff_seeds=[]、count_diff={}；受控 9 / flick 1 / insuff 1 / raw 11 两路径全同",
            "cond3": "residual_row_diffs 4 条（seed 5012/5014/5016/5018 的 final_rise），all_verdict_same=true",
            "cond4": "探针路径 / C / build 已登记在本条目的 artifact、clip_C、gate_build_at_cosign 三处",
            "cond5": "plain composite_policy=false、探针 composite_policy=true ⇒ 探针产物不得当官方臂数字引用",
        }
    if countersign and not legacy_countersign_only:
        entry["cosign"] = {
            "by": "D", "fact_basis": True, "date": "2026-09-29T11:14:37+08:00",
            "gate_build_at_cosign": cosign_build if cosign_build is not None else "f19f61341cbe",
            "gate_version_at_cosign": "v1.5",
            "verifier": "scripts/d_verify_exoneration_cosign.py",
            "note": "selftest fixture（形状照 D 的复签块抄）",
        }
    if legacy_countersign_only:
        # 只有 A 旧判据认的 legacy 键、没有门禁读的 cosign 块 ⇒ 门禁判 cosign_missing，L6 必须红
        entry["countersigned_by"] = "D"
        entry["countersign_ref"] = "增补四 §3（事实基础已核可）"
    return {"_doc": "selftest fixture", "entries": {TARGET_ARM: entry}}


def _fixture_arm_paths(stdfloor_chain_end: bool = True) -> dict:
    """A 表的归属回显（schema_version 3 起有），与 _fixture_b_table 的 `file` 对齐。"""
    out = {}
    for name in _fixture_arm_names():
        out[name] = {"adjudicated_artifact": _fixture_path(name), "sha256": "0" * 64,
                     "attribution_kind": "main_dir_only"}
    sub = "reblown/" if stdfloor_chain_end else ""
    out[STDFLOOR_ARM] = {"adjudicated_artifact": _fixture_path(STDFLOOR_ARM, sub),
                         "sha256": "0" * 64,
                         "attribution_kind": ("reblown_remeasure" if stdfloor_chain_end
                                              else "main_dir_only")}
    return out


def _fixture_a_table(*, gate_build: str, post: dict, with_attribution: bool = True,
                     arm_paths: dict | None = None, with_probe_kind: bool = True,
                     exo_channel_wrong: bool = False, with_recon_meta: bool = True,
                     gate_version: str = "v1.5",
                     target_class: str = "VALID_probe_exonerated") -> dict:
    """合成一份 A 权威表（postcheck 的 P1–P7 用）。

    48 臂全都带 `probe_kind` **这一列**（无豁免的臂为 null）—— 裁定 24⑤ 要求 stdfloor 在 A 表里
    维持 `valid` 但**另列一列**回显 `probe_kind=reblown_single_source`；P7 按 kind 分组对账。
    `post`（三分类分母）与 `target_class`（目标臂的 validity_class）**各自独立**：S9 要单独验
    「分母退回 24/22/2」而不牵连 P4/P7，耦合在一起会让反例指不到真正被测的那条判据。
    """
    arms = []
    for name in _fixture_arm_names():
        if name == TARGET_ARM:
            cls = target_class
            kind = ((PROBE_KIND_REBLOWN if exo_channel_wrong else PROBE_KIND_CLIP)
                    if cls == "VALID_probe_exonerated" else None)
        elif name == STDFLOOR_ARM:
            cls, kind = "valid", PROBE_KIND_REBLOWN
        else:
            cls, kind = "valid", None
        arms.append({"arm": name, "validity_class": cls,
                     **({"probe_kind": kind} if with_probe_kind else {})})
    n_exo = sum(1 for a in arms if a["validity_class"] == "VALID_probe_exonerated")
    meta = {
        "schema_version": 3 if with_attribution else 2,
        "gate_version": [gate_version], "gate_build": [gate_build],
        "gate_spec_sha256": [SELFTEST_SPEC_NOT_A_NAIL],
        "denominators": {"pre_probe_exoneration": dict(REQUIRED_PRE), "post_probe_exoneration": dict(post)},
        "invalid_arms": [{"arm": REPLAN1_ARM, "reason": "measurement_invalid:no_probe_product"}],
        "totals": {"scope_all_48_products_supervisor_reconcile": dict(BUILD_INVARIANT_TOTALS)}}
    if with_attribution:
        meta["artifact_attribution"] = {
            "arm_paths": _fixture_arm_paths() if arm_paths is None else arm_paths}
    if with_recon_meta:
        meta["exoneration_reconciliation"] = {
            "rule": "按 probe_kind 分组比，**不得**直接比 probe_exonerated 计数（裁定 24⑤）",
            "a_VALID_probe_exonerated": n_exo,
            "b_probe_exonerated_by_kind": {PROBE_KIND_CLIP: n_exo, PROBE_KIND_REBLOWN: 1},
            "design_difference": 1,
            "note": "A 的 VALID_probe_exonerated 只对应 clip_at_train_absmax；stdfloor 走 reblown 通道，"
                    "在 A 表里维持 valid ⇒ 两表被豁免臂数必然差 1，属设计差异不是缺陷",
        }
    return {"meta": meta, "arms": arms}


def selftest(root: Path) -> int:
    """变异自检：证明这道闸**有牙**（合规 fixture 必须 OPEN、缺任一条必须 CLOSED）。

    裁定 27③ 追加的纪律：**判据类工具的反例必须取自真实产物形状**。09-29 的 L5 假红就是因为
    S1–S17 全用 A 自己想象的条目形状（`cond1_selftest` 这种自造键），而真条目是
    「5 个精确布尔键 + 5~7 条 `condN` 打头的**证据散文**」⇒ 自检 17/17 全绿、真跑却假红。
    现在 S18 / S24 直接用真形状，S19 用注入的伪造 `judge_file` 行证明 G2 实测有牙。
    """
    live_build = live_gate_build(root) or "f19f61341cbe"

    b_ok = _fixture_b_table(exonerate_target=True, three_class=REQUIRED_POST,
                            stdfloor_status="probe_exonerated")
    b_bad = _fixture_b_table(exonerate_target=False, three_class=REQUIRED_PRE,
                             stdfloor_status="probe_exonerated")
    b_no_kind = _fixture_b_table(exonerate_target=True, three_class=REQUIRED_POST,
                                 stdfloor_status="probe_exonerated", stdfloor_probe_kind=False)
    b_not_chain_end = _fixture_b_table(exonerate_target=True, three_class=REQUIRED_POST,
                                       stdfloor_status="probe_exonerated", stdfloor_chain_end=False)
    b_out_of_band = _fixture_b_table(exonerate_target=True, three_class=REQUIRED_POST,
                                     stdfloor_status="probe_exonerated", stdfloor_blown=0.12)
    b_no_by_kind = _fixture_b_table(exonerate_target=True, three_class=REQUIRED_POST,
                                    stdfloor_status="probe_exonerated", by_kind_summary=False)

    ledger_ok = _fixture_ledger(root, countersign=True, conds_true=True, c_value=TARGET_ARM_C,
                                probe_kind=PROBE_KIND_CLIP, cosign_build=live_build)
    # 裁定 27③ 要求补的那一档：**真条目形状**（布尔键 + condN 打头的证据散文并存）⇒ 必须 OPEN
    ledger_real_shape = _fixture_ledger(root, countersign=True, conds_true=True,
                                        c_value=TARGET_ARM_C, probe_kind=PROBE_KIND_CLIP,
                                        cosign_build=live_build, evidence_prose=True)
    # 布尔键全 false、只有散文 ⇒ L5 必须红（散文不能替代布尔断言）
    ledger_prose_only = _fixture_ledger(root, countersign=True, conds_true=True,
                                        c_value=TARGET_ARM_C, probe_kind=PROBE_KIND_CLIP,
                                        cosign_build=live_build, evidence_prose=True,
                                        conds_bool_true_but_evidence_only=True)
    led_arm_scope = _fixture_ledger(root, countersign=True, conds_true=True,
                                    c_value=TARGET_ARM_C, probe_kind=PROBE_KIND_CLIP,
                                    cosign_build=live_build, scope="arm")
    probe_missing = not (root / SELFTEST_PROBE).is_file()
    if probe_missing:
        print(f"  ✗ selftest 前置缺失：探针产物不存在 {SELFTEST_PROBE}")
        print("    （自检不写文件，需要仓库内这份真实产物做 L2/L7 的正例）")
        return 1

    import copy
    led_no_cs = copy.deepcopy(ledger_ok)
    led_no_cs["entries"][TARGET_ARM].pop("cosign")
    led_legacy_cs = _fixture_ledger(root, countersign=True, conds_true=True,
                                    c_value=TARGET_ARM_C, probe_kind=PROBE_KIND_CLIP,
                                    legacy_countersign_only=True)
    led_cond_false = _fixture_ledger(root, countersign=True, conds_true=False,
                                     c_value=TARGET_ARM_C, probe_kind=PROBE_KIND_CLIP,
                                     cosign_build=live_build)
    led_c5 = _fixture_ledger(root, countersign=True, conds_true=True, c_value=5.0,
                             probe_kind=PROBE_KIND_CLIP, cosign_build=live_build)
    led_reblown = _fixture_ledger(root, countersign=True, conds_true=True,
                                  c_value=TARGET_ARM_C, probe_kind=PROBE_KIND_REBLOWN,
                                  cosign_build=live_build)
    # 裁定 25 / DR-008 决定 7：会签锚在**旧 build** ⇒ 不拒判，只回显（L6b/B7 各一条 WARN）
    led_stale_cosign = _fixture_ledger(root, countersign=True, conds_true=True,
                                       c_value=TARGET_ARM_C, probe_kind=PROBE_KIND_CLIP,
                                       cosign_build="b9379fdb1089", evidence_prose=True)
    b_pending_bucket = _fixture_b_table(exonerate_target=True, three_class=REQUIRED_POST,
                                        stdfloor_status="probe_exonerated",
                                        pending_bucket=[TARGET_ARM])

    a_attr_ok = _fixture_a_table(gate_build=live_build, post=REQUIRED_POST)
    a_no_attr = _fixture_a_table(gate_build=live_build, post=REQUIRED_POST, with_attribution=False)
    a_migrated = _fixture_a_table(gate_build=live_build, post=REQUIRED_POST)
    a_stale_build = _fixture_a_table(gate_build="e4f5ec887788", post=REQUIRED_POST,
                                     gate_version="v1.2.1")
    a_bad_class = _fixture_a_table(gate_build=live_build, post=REQUIRED_PRE,
                                   target_class="VALID_probe_exonerated")
    a_no_kind_col = _fixture_a_table(gate_build=live_build, post=REQUIRED_POST,
                                     with_probe_kind=False)
    a_kind_wrong = _fixture_a_table(gate_build=live_build, post=REQUIRED_POST,
                                    exo_channel_wrong=True)
    a_no_recon = _fixture_a_table(gate_build=live_build, post=REQUIRED_POST,
                                  with_recon_meta=False)

    b_path = root / DEFAULT_B_TABLE
    ledger_path = root / DEFAULT_LEDGER
    a_path = root / DEFAULT_A_TABLE

    cases: list[tuple[str, bool, str]] = []

    def run(name: str, mode: str, expect_open: bool, expect_ids: tuple[str, ...],
            b_doc=None, ledger_doc=None, a_doc=None, gate_src=None, gate_row=_STUB,
            gate_row_err: str | None = None, expect_warn_min: int = 0) -> None:
        row = _FIXTURE_GATE_ROW_EXONERATED if gate_row == _STUB else gate_row
        checks, gate_open, _ = evaluate(mode, root, b_path, ledger_path, a_path,
                                       b_doc_in=b_doc, ledger_doc=ledger_doc, a_doc_in=a_doc,
                                       gate_src_in=gate_src, gate_row_in=row,
                                       gate_row_err_in=gate_row_err)
        failed = tuple(r["id"] for r in checks.rows if not r["pass"] and r["blocking"])
        n_warn = checks.n_warn()
        ok = (gate_open == expect_open) and (failed == expect_ids) and (n_warn >= expect_warn_min)
        cases.append((name, ok, f"gate={'OPEN' if gate_open else 'CLOSED'} "
                                f"blocking_fail={failed or '()'} warn={n_warn}"))
        print("    %-62s -> %s   gate=%-6s blocking_fail=%-14s warn=%d"
              % (name, "pass" if ok else "FAIL", "OPEN" if gate_open else "CLOSED",
                 failed or "()", n_warn))

    print("  迁移闸变异自检（fixture 全在内存，不写文件；G2 默认注入伪造行以保证可重复）：")
    run("S1  合规（B 免罪后 + 册子齐 + 会签 + 实测生效）-> OPEN", "preflight", True, (),
        b_doc=b_ok, ledger_doc=ledger_ok, a_doc=a_attr_ok, gate_src=_FIXTURE_GATE_FIXED)
    run("S2  缺 cosign 块 -> CLOSED(L6)", "preflight", False, ("L6",),
        b_doc=b_ok, ledger_doc=led_no_cs, a_doc=a_attr_ok, gate_src=_FIXTURE_GATE_FIXED)
    run("S3  五条准入有一条 false -> CLOSED(L5)", "preflight", False, ("L5",),
        b_doc=b_ok, ledger_doc=led_cond_false, a_doc=a_attr_ok, gate_src=_FIXTURE_GATE_FIXED)
    run("S4  C=5.0 而非 train-absmax -> CLOSED(L3)", "preflight", False, ("L3",),
        b_doc=b_ok, ledger_doc=led_c5, a_doc=a_attr_ok, gate_src=_FIXTURE_GATE_FIXED)
    run("S5  probe_kind 用争议带通道 -> 仅 WARN，仍 OPEN", "preflight", True, (),
        b_doc=b_ok, ledger_doc=led_reblown, a_doc=a_attr_ok, gate_src=_FIXTURE_GATE_FIXED,
        expect_warn_min=1)
    run("S6  B 表停在免罪前 24/22/2 -> CLOSED(B1,B2,B3)", "preflight", False, ("B1", "B2", "B3"),
        b_doc=b_bad, ledger_doc=ledger_ok, a_doc=a_attr_ok, gate_src=_FIXTURE_GATE_FIXED)
    run("S7  迁移后 A 表达标 -> OPEN", "postcheck", True, (),
        b_doc=b_ok, a_doc=a_migrated)
    run("S8  A 表数字对但构建没迁 -> CLOSED(P1)", "postcheck", False, ("P1",),
        b_doc=b_ok, a_doc=a_stale_build)
    run("S9  A 表迁了但三分类退回 24/22/2 -> CLOSED(P2)", "postcheck", False, ("P2",),
        b_doc=b_ok, a_doc=a_bad_class)
    run("S10 门禁源码是 v1.4 形状、但**实测**已生效 -> 仅 WARN，仍 OPEN（裁定 27：锚点降级）",
        "preflight", True, (),
        b_doc=b_ok, ledger_doc=ledger_ok, a_doc=a_attr_ok, gate_src=_FIXTURE_GATE_V14_SHAPE,
        expect_warn_min=2)
    run("S11 册子照抄 scope=arm -> CLOSED(L9)", "preflight", False, ("L9",),
        b_doc=b_ok, ledger_doc=led_arm_scope, a_doc=a_attr_ok, gate_src=_FIXTURE_GATE_FIXED)
    run("S12 门禁正当重构、锚点消失 -> 仅 WARN，仍 OPEN", "preflight", True, (),
        b_doc=b_ok, ledger_doc=ledger_ok, a_doc=a_attr_ok, gate_src=_FIXTURE_GATE_NOANCHOR)
    run("S13 带上限扩到 0.30（另一条解锁路径）-> OPEN", "preflight", True, (),
        b_doc=b_ok, ledger_doc=ledger_ok, a_doc=a_attr_ok, gate_src=_FIXTURE_GATE_BAND_WIDE)
    run("S14 stdfloor 缺 probe_kind 回显（裁定 19 未落地）-> CLOSED(B5,B8)",
        "preflight", False, ("B5", "B8"),
        b_doc=b_no_kind, ledger_doc=ledger_ok, a_doc=a_attr_ok, gate_src=_FIXTURE_GATE_FIXED)
    run("S15 stdfloor 不是链末端（归属错）-> CLOSED(B5,B6)", "preflight", False, ("B5", "B6"),
        b_doc=b_not_chain_end, ledger_doc=ledger_ok, a_doc=a_attr_ok, gate_src=_FIXTURE_GATE_FIXED)
    run("S16 A 表没回显归属（schema v2）-> CLOSED(B6)", "preflight", False, ("B6",),
        b_doc=b_ok, ledger_doc=ledger_ok, a_doc=a_no_attr, gate_src=_FIXTURE_GATE_FIXED)
    run("S17 stdfloor blown 落在争议带外 -> CLOSED(B5)", "preflight", False, ("B5",),
        b_doc=b_out_of_band, ledger_doc=ledger_ok, a_doc=a_attr_ok, gate_src=_FIXTURE_GATE_FIXED)
    # ---- 裁定 27③ 要求补的档位：反例取自**真实产物形状** ----
    run("S18 真条目形状（布尔键 + condN 证据散文并存）-> OPEN【裁定 27③ 补缺口】",
        "preflight", True, (),
        b_doc=b_ok, ledger_doc=ledger_real_shape, a_doc=a_attr_ok,
        gate_src=_FIXTURE_GATE_V15_SHAPE)
    run("S19 实测说免罪没生效（注入 v1.4 行为行）-> CLOSED(G2)【G2 的牙】",
        "preflight", False, ("G2",),
        b_doc=b_ok, ledger_doc=ledger_real_shape, a_doc=a_attr_ok,
        gate_src=_FIXTURE_GATE_V15_SHAPE, gate_row=_FIXTURE_GATE_ROW_V14_BEHAVIOUR)
    run("S20 只有 legacy 会签键、没有门禁读的 cosign -> CLOSED(L6)",
        "preflight", False, ("L6",),
        b_doc=b_ok, ledger_doc=led_legacy_cs, a_doc=a_attr_ok, gate_src=_FIXTURE_GATE_FIXED)
    run("S21 会签锚在旧 build（决定 7 不拒判）-> 仅 WARN(L6b,B7)，仍 OPEN",
        "preflight", True, (),
        b_doc=b_ok, ledger_doc=led_stale_cosign, a_doc=a_attr_ok,
        gate_src=_FIXTURE_GATE_V15_SHAPE, expect_warn_min=2)
    run("S22 同上但 B 已补桶 + 回显三值 -> 只剩 L6b 一条 WARN，仍 OPEN",
        "preflight", True, (),
        b_doc=b_pending_bucket, ledger_doc=led_stale_cosign, a_doc=a_attr_ok,
        gate_src=_FIXTURE_GATE_V15_SHAPE, expect_warn_min=1)
    run("S22b 桶里塞了 matches=null 的臂（判据写成 is not True）-> 仅 WARN(B7b)，仍 OPEN",
        "preflight", True, (),
        b_doc=_fixture_b_table(exonerate_target=True, three_class=REQUIRED_POST,
                               stdfloor_status="probe_exonerated",
                               pending_bucket=[STDFLOOR_ARM], pending_matches=None),
        ledger_doc=ledger_real_shape, a_doc=a_attr_ok,
        gate_src=_FIXTURE_GATE_V15_SHAPE, expect_warn_min=1)
    run("S23 门禁是 v1.5 形状（白名单 + 查表晋级）-> G1/G3 诊断都认得，OPEN",
        "preflight", True, (),
        b_doc=b_ok, ledger_doc=ledger_real_shape, a_doc=a_attr_ok,
        gate_src=_FIXTURE_GATE_V15_SHAPE)
    run("S24 布尔键全 false 但证据散文写满 -> CLOSED(L5)【散文不能替代布尔断言】",
        "preflight", False, ("L5",),
        b_doc=b_ok, ledger_doc=ledger_prose_only, a_doc=a_attr_ok,
        gate_src=_FIXTURE_GATE_V15_SHAPE)
    run("S25 B 表没有 probe_exoneration_by_kind 分桶 -> CLOSED(B8)【裁定 24④】",
        "preflight", False, ("B8",),
        b_doc=b_no_by_kind, ledger_doc=ledger_ok, a_doc=a_attr_ok, gate_src=_FIXTURE_GATE_FIXED)
    run("S26 A 表缺 probe_kind 列 -> CLOSED(P7)【裁定 24⑤】", "postcheck", False, ("P7",),
        b_doc=b_ok, a_doc=a_no_kind_col)
    run("S27 A 把 reblown 通道也记成 VALID_probe_exonerated -> CLOSED(P7)",
        "postcheck", False, ("P7",), b_doc=b_ok, a_doc=a_kind_wrong)
    run("S28 A 表 meta 没登记「差 1 是设计差异」-> CLOSED(P7)", "postcheck", False, ("P7",),
        b_doc=b_ok, a_doc=a_no_recon)
    run("S29 G2 实测跑不起来（门禁/产物缺失）-> CLOSED(G2)【无证据不放行】",
        "preflight", False, ("G2",),
        b_doc=b_ok, ledger_doc=ledger_ok, a_doc=a_attr_ok, gate_src=_FIXTURE_GATE_V15_SHAPE,
        gate_row=None, gate_row_err="FileNotFoundError: 门禁源码不存在（selftest 注入）")
    # ---- live 端到端：不注入伪造行，真调 B 的门禁本尊（唯一会跟着 live 状态变的一档）----
    run("S30 live 门禁端到端实测（真册子、真产物、不写文件）-> OPEN",
        "preflight", True, (),
        b_doc=b_ok, ledger_doc=ledger_real_shape, a_doc=a_attr_ok, gate_src=None,
        gate_row=None)

    bad = [n for n, ok, _d in cases if not ok]
    print("  迁移闸自检：%d/%d 通过%s" % (len(cases) - len(bad), len(cases),
                                      "" if not bad else " -> FAIL: " + str(bad)))
    return 0 if not bad else 1


def evaluate(mode: str, root: Path, b_path: Path, ledger_path: Path, a_path: Path,
             b_doc_in=None, ledger_doc=None, a_doc_in=None,
             gate_src_in: str | None = None, gate_row_in: dict | None = None,
             gate_row_err_in: str | None = None, gate_rel: str = DEFAULT_B_GATE,
             ) -> tuple[Checks, bool, dict]:
    """跑一遍判据。

    `gate_row_in` / `gate_row_err_in` 只为 `--selftest` 存在：注入一份伪造的 `judge_file` 返回行，
    用来证明 G2 有牙（真跑时两者都是 None ⇒ G2 走 `run_gate_on_target()` 端到端实测）。
    """
    checks = Checks()
    facts = cosign_build_facts(root, ledger_doc, ledger_path, gate_rel)
    b_doc = check_b_table(checks, b_path, b_doc_in, cosign_facts=facts)
    if mode == "preflight":
        gate_src = read_gate_source(root, gate_rel)[0] if gate_src_in is None else gate_src_in
        check_ledger(checks, ledger_path, root, ledger_doc, b_doc=b_doc, gate_src=gate_src,
                     cosign_facts=facts)
        check_gate_code(checks, root, gate_src, b_doc, gate_row=gate_row_in,
                        gate_row_err=gate_row_err_in)
        check_attribution(checks, root, a_path, b_doc, a_doc_in)
    else:
        check_a_table(checks, a_path, b_doc, a_doc_in)
    return checks, checks.open, b_doc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=("preflight", "postcheck"), default="preflight")
    ap.add_argument("--repo-root", default=".", help="仓库根（默认当前目录）")
    ap.add_argument("--b-table", default=DEFAULT_B_TABLE)
    ap.add_argument("--ledger", default=DEFAULT_LEDGER)
    ap.add_argument("--a-table", default=DEFAULT_A_TABLE)
    ap.add_argument("--attribution-table", default=None,
                    help="B6 产物归属对账读的 A 表（默认 = 归属回显版 arms_summary_v3.json）")
    ap.add_argument("--b-gate", default=DEFAULT_B_GATE,
                    help="门禁源码路径（A 只读、**不改**）。G1/G3/L9 读它的文本锚点，"
                         "G2 会 importlib 加载它跑 judge_file（json_out=None ⇒ 不写任何文件）")
    ap.add_argument("--json-out", default=None, help="留档路径；不给就只打印、不写任何文件")
    ap.add_argument("--selftest", action="store_true", help="变异自检：证明闸有牙（不写任何文件）")
    args = ap.parse_args()

    if args.selftest:
        return selftest(Path(args.repo_root).resolve())

    root = Path(args.repo_root).resolve()
    b_path = (root / args.b_table) if not Path(args.b_table).is_absolute() else Path(args.b_table)
    ledger_path = (root / args.ledger) if not Path(args.ledger).is_absolute() else Path(args.ledger)
    a_path = (root / args.a_table) if not Path(args.a_table).is_absolute() else Path(args.a_table)
    attr_rel = args.attribution_table or (DEFAULT_A_ATTRIBUTION_TABLE
                                          if args.mode == "preflight" else args.a_table)
    attr_path = (root / attr_rel) if not Path(attr_rel).is_absolute() else Path(attr_rel)

    checks, gate_open, b_doc = evaluate(args.mode, root, b_path, ledger_path,
                                        a_path if args.mode == "postcheck" else attr_path,
                                        gate_rel=args.b_gate)
    gate_src, gate_src_sha = read_gate_source(root, args.b_gate)
    facts = cosign_build_facts(root, None, ledger_path, args.b_gate)
    a_ident = {}
    a_doc_now = _load(a_path if args.mode == "postcheck" else attr_path)
    if isinstance(a_doc_now, dict) and "__load_error__" not in a_doc_now:
        a_meta = a_doc_now.get("meta") or {}
        a_ident = {"schema_version": a_meta.get("schema_version"),
                   "gate_version": a_meta.get("gate_version"),
                   "gate_build": a_meta.get("gate_build"),
                   "denominators": a_meta.get("denominators")}
    doc = {
        "check": f"arms_table_migration_gate_{args.mode}",
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "script": "scripts/a_migration_gate_preflight.py",
        "read_only": True,
        "mode": args.mode,
        "ruling_ref": "work/decisions/decisions_20260928_A.md ADR-A-006 裁定 2（迁移闸，A 不自免）；"
                      "监管备忘 增补五 裁定 16.4 / §3 / §7",
        "gate_open": gate_open,
        "b_table": {"path": str(b_path), "gate_version": b_doc.get("gate_version"),
                    "gate_build": b_doc.get("gate_build"), "git_commit": b_doc.get("git_commit")},
        "b_gate_source": {"path": args.b_gate, "sha256_12": (gate_src_sha or "")[:12] or None,
                          "readable": bool(gate_src),
                          "note": "G1/G3/L9 的文本诊断锚点所在的门禁构建；G2 直接 import 这个文件跑 "
                                  "judge_file（裁定 27④：实测是上位判据，锚点只是诊断）"},
        "cosign_build_facts": dict(facts, **{
            "ruling_ref": "裁定 25 / DR-008 决定 7（build 不一致不拒判，但必须回显）+ 裁定 27"
                          "（会签锚在哪个 build 上是可核事实，必须随数字一起走）"}),
        "ledger_path": str(ledger_path) if args.mode == "preflight" else None,
        "a_table_path": str(a_path) if args.mode == "postcheck" else str(attr_path),
        "a_table_role": ("post_migration_table" if args.mode == "postcheck"
                         else "artifact_attribution_source（B6）"),
        "a_table_identity": a_ident,
        "checks": checks.rows,
        "n_blocking_fail": checks.n_fail_blocking(),
        "n_warn": checks.n_warn(),
    }
    g2 = next((r for r in checks.rows if r["id"] == "G2"), None)
    disposition = []
    if facts.get("cosign_build_matches") is False:
        disposition.append(
            "引用纪律（裁定 27）：可引「25/22/1 @ v1.5 / %s（D 独立复算验收通过）」，但引用该臂必须"
            "**同时**注明「会签块尚锚在 %s、cosign_build_matches=false、按 DR-008 决定 7 不拒判但待复签换块」。"
            % (facts.get("live_gate_build"), facts.get("cosign_gate_build")))
    report(checks, args.mode, gate_open, {"disposition": disposition})
    if g2 is not None and isinstance(g2.get("observed"), dict):
        doc["g2_live_measurement"] = g2["observed"]
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print(f"\n写出: {out}")
    return 0 if gate_open else 1


if __name__ == "__main__":
    sys.exit(main())
