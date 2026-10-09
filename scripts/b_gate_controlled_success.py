#!/usr/bin/env python3
"""B 线门禁：《受控成功判据 v1.3》的可执行实现。

规格见 docs/b_controlled_success_v1_20260928.md。本脚本是**只读后处理**：
吃任意评测器写出的 audit/result JSON，产出裁定与三套账，不修改任何评测器、
checkpoint 或 A/C 的实现文件。

为什么需要它：监管 P0 要求 Lift 成功「不是 flick」，但
  - scripts/eval_act_lift_truth.py:38      只有 max_rise
  - scripts/eval_lerobot_act_runtime.py:187 有 phase_trace/max_rise/clip_events，无 final_rise
两者都无法自行区分「受控抬起」和「把方块弹射出去」。scripts/audit_lift_base_truth.py
字段最全，是本契约的参考实现。

三套账（分母互不相同，禁止混用）：
  policy_independent  仅 guard/recovery 全程未介入的局
  system_assisted     全部可判定局（含被救场的），救场成功不计入 policy 能力
  autonomous_learning 关闭动作辅助后重跑的局（由 --assist-off 标记的输入文件承担）

v4 不变量：unknown / preempted 既不是成功也不是失败，一律移出分母单独报告。
"""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
import numpy as np

# ---- 判据常量（v1.1，改动需在 docs/b_controlled_success_v1_20260928.md 登记版本）----
RISE_CAP = 0.15           # m。scripted base 实测 mean 0.0764 / max 0.078，取约 2 倍为上限
# C5 抬起高度门槛（m）。**原注释「与 robosuite Lift 的成功高度阈值同量级」是错的，已勘误**：
# 实测 robosuite `_check_success`（cube_height > table_offset[2] + 0.04，从桌面 body 原点起算）
# 换算成本项目的**相对初始高度**口径后，等效阈只有 0.0082~0.0087 m —— 本门槛比它严约 4.7 倍
# （860 行官方臂数据上 success_raw=True 的 max_rise 最小 0.0087、False 的最大 0.0082，
#   两侧被一条极窄的带完全分开）。这也是 success_raw 11/20 与受控成功 0~2/20 落差的真正来源。
# 保留 0.04 的正确锚：方块 z 向半尺寸 0.0217050 -> 全高 0.04341，0.04 = **0.92 × 物体全高**，
# 即「抬起约自身高度」，与环境实现无关。建议后续改成随 object_geom 缩放（见
# docs/b_gate_threshold_sensitivity_20260928.md §4.2）。**改这个值会放大所有历史臂的成功率，
# 属监管裁决范围，B 不自行改。** 阈值 ±0.005 敏感性：12 臂 0 robust / 5 sensitive，
# 敏感带 1→6，且全部边界局卡在 C5（无一卡 rise_cap）——报率必须附敏感带。
FINAL_RISE_MIN = 0.04

# 门禁**构建指纹**。仓库不是 git repo（见 docs/b_reproducibility_incident_20260928.md），
# 所以留档的 gate JSON 无法回答「这份裁定是哪一版门禁判的」。实测后果：
# runs/infra/b_normclip/gate_v11.json 里的 clip24 条目缺 measurement_valid/gate_reason
# （由加入输入契约检查**之前**的 v1.1 构建产出），用当前脚本重判会从 FAIL 翻成 INVALID。
# 因此每份裁定都必须带上脚本自身与规格文档的内容哈希。
GATE_SPEC_DOC = "docs/b_controlled_success_v1_20260928.md"
_ROOT = Path(__file__).resolve().parents[1]


def _sha12(p: Path) -> str | None:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()[:12]
    except Exception:                                   # noqa: BLE001
        return None


GATE_BUILD = _sha12(Path(__file__).resolve())
GATE_SPEC_SHA = _sha12(_ROOT / GATE_SPEC_DOC)


def _git_stamp():
    """DR-002/DR-003 之后，裁定 JSON 除 gate_build 外再带 git 提交号。

    为什么 gate_build 不够：它只是**门禁脚本自己**的内容哈希，覆盖不了产出被裁定
    产物的评测器（A 的 scripts/eval_lerobot_act_runtime.py）与 C 的实现文件。
    监管 P0 第一项要的是「这份裁定是哪一版代码判的」，git 之后才真的可答。
    非 git 环境返回 (None, None)，不抛异常。
    """
    import subprocess
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=_ROOT,
                              capture_output=True, text=True, timeout=20)
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=_ROOT,
                               capture_output=True, text=True, timeout=120)
        commit = (head.stdout.strip() or None) if head.returncode == 0 else None
        n_dirty = (len([ln for ln in dirty.stdout.splitlines() if ln.strip()])
                   if dirty.returncode == 0 else None)
        return commit, n_dirty
    except Exception:                                   # noqa: BLE001
        return None, None


GIT_COMMIT, GIT_DIRTY_FILES = _git_stamp()
# 版本号**单一来源**：JSON 里的 gate_version 与 CLI 页脚曾经各写一份，
# v1.2 改分类时页脚漏改，出现「JSON 说 v1.2、屏幕说 v1.1」的自相矛盾 —— 
# 这正是 gate_build 指纹要防的那类陈旧口径，所以统一到一个常量。
# v1.5（DR-008）：豁免册按 probe_kind 分通道 + 裁定 10（clip_at_train_absmax）通道落地
# + 晋级闸分路。阈值常量一格未动。**升版即触发全量重判**（裁定 16.3 改判 7）。
GATE_VERSION = "v1.5"
# v1.1 收紧：per-frame phase_of() 的词表只有 {hold, grasp, descend, approach}，
# 其中 "grasp" 的判据是 max|gripper_qpos| > 0.012 = **两指张开超过 1.2cm**，
# 它对「夹着 4.4cm 方块」和「空爪全开」给同一个标签，因此**不能单独**当作局末仍夹持的证据。
# v1 把它无条件放进 HOLD_PHASES，配合 C5 缺字段的偏松通道会产生假阳性 PASS
# （夹起后滑落回桌面、爪重新张开 -> success_raw=T, grasp_verified=T(held_ever),
#   max_rise<=0.15, end_phase="grasp" -> v1 判 controlled_success）。
# v1.1：HOLD_PHASES_STRICT 只认 hold；"grasp" 仅在 held_at_end 或 final_rise 至少有一个
# 可评时才被接受（见 judge_row）。
HOLD_PHASES_STRICT = {"hold"}
HOLD_PHASES_WITH_EVIDENCE = {"hold", "grasp"}

# v1.4（裁定 14 / DR-D09）：三个**失效模式标签**与它们实际读取的字段。
# 实测缺陷（A 的最小复现，docs/a_handoff_to_b_gate_vocabulary_20260928.md §2）：
# `held_at_end` 与 `final_rise` 双缺时，C4 落到 HOLD_PHASES_STRICT={"hold"} 分支拒绝 "grasp"
# -> c4=False -> 一路返回**最重的失效模式 flick**；同一局补测（strict）后其实是 insufficient_lift。
# 即「证据不足」被解析成「判成脱手弹射」，而不是弃权。影响面：5 臂 16 局假 flick，
# 使可引用 flick 只剩 2 局 / 920 局（DR-D09）。
# 收窄说明（DR-007，已升级给 D 复核）：DR-D09 的字面口径是 `field_class != "strict"` 即弃权，
# 但 `field_class` 也把 `terminal_kind` 算进关键字段，而三个标签**不读** `terminal_kind`
# （它走的是终局分支那条独立弃权路径）。按字面实现会把 base-only 标定产物
# （runs/infra/b_env_rebuild/base_truth20.json，缺 terminal_kind）判成 INVALID ——
# 那正是本文件 :741 注释警告过的「门禁把自己的标定基准作废」。故弃权只由本集合触发。
FAILURE_MODE_LABELS = ("flick", "insufficient_lift", "over_lift")
LABEL_CRITICAL_FIELDS = ("final_rise", "held_at_end", "phase_at_end")
# 状态机日志词表（audit_lift_base_truth.py / residual audit 写的是 6 元素 controller log，
# 不是逐帧 phase_of）。到达 "done" 意味着 hold 满 HOLD_STEPS=30 帧，是**更强**的夹持证据。
CONTROLLER_LOG_VOCAB = {"approach", "descend", "grasp", "lift", "hold", "done"}
CONTROLLER_LOG_HOLD = {"hold", "done"}
# 允许的「收到超训练分布输入」的帧占比。设成 5% 是因为实测健康臂（clip3）为 0，
# 而事故臂为 89~97%，中间没有灰区；留 5% 是给边界帧的容差。
INPUT_BLOWUP_TOL = 0.05
UNJUDGED_TERMINALS = {"unknown", "preempted", "takeover"}

# v1.2.1：输入侧约束键白名单。**只有这些键**算「执行侧介入」：
# `input_constraints` 里还混着 `train_time_norm_absmax` / `note` 这类元数据，
# 全量取非 None 会把元数据当成约束。两个名字都收是因为两条评测线的写法不同：
#   scripts/b_eval_act_lift_v1.py:224       -> input_constraints.clip_norm_input
#   scripts/eval_lerobot_act_runtime.py:516 -> execution_constraints.norm_input_clip
INPUT_CONSTRAINT_KEYS = ("clip_norm_input", "norm_input_clip")

# ==================== v1.3 新增（D 裁定 1/2/3 + 监管 §12 分派）====================
# 裁定 1：phase_at_end 与 phase_trace **词表互相矛盾**时判 INVALID，不再静默走 per-frame
# 兜底把 'done' 判成 flick。实测假阴性（daily_report.md §4「交接单 2」/§9-1）：residual 臂
#   runs/20260924_142702_sac_lift_residual_grasp_lift/audit_truth20_gatefields_pre_phase_trace.json
# 只写 phases（6 元素状态机日志）不写 phase_trace，20 局实质判据全过
# （held_at_end 20/20、final_rise 0.0563–0.1007、max_rise ≤0.111、success_raw 20/20），
# 却被判「20 局全 flick」；补 phase_trace 后同臂 20/20 受控。
PER_FRAME_VOCAB = {"hold", "grasp", "descend", "approach"}
CTRL_ONLY_VOCAB = CONTROLLER_LOG_VOCAB - PER_FRAME_VOCAB          # {"lift", "done"}

# 裁定 2：无归一化策略（如 SAC 直吃 raw 60 维 obs）的 not_applicable 必须**显式声明 +
# 带原始 obs 区间证据**。声明不等于豁免：缺训练期区间或缺闭环区间 -> 仍判 INVALID。
NA_KEY = "not_applicable"          # 写在产物 input_contract.not_applicable
RAW_OOB_TOL = 0.05                 # 闭环 raw obs absmax 相对训练期上界的容差

# 裁定 3：§12 争议带内的臂可由**已登记的探针证据**豁免为 probe_exonerated；
# 超出争议带一律不受理（§12 原文：两条路径都远超 0.05 的臂 INVALID 维持）。
DISPUTED_BLOWN_BAND = (0.03, 0.08)

# ==================== v1.5 新增（裁定 10 / 裁定 16.4 / DR-008）====================
# 豁免册从「一条通道」变成「按 probe_kind 分路的多条通道」。原因（D 的会签前独立核验
# scripts/d_verify_exoneration_cosign.py 实测，tmp/agentD_review_20260929/D_cosign_k2seed0.json）：
# 裁定 3 的争议带牙是为 `reblown_single_source`（增补三 §12：blown 口径两条代码路径给出
# 0.2120 / 0.1180 两个值，重测一次消除口径分歧）设计的，它的适用前提就是「值在带内、
# 只是尺子不确定」。而 裁定 10 是**另一条**通道：clip-at-train-absmax 因果探针，
# 目标臂 blown=0.212 **必然**在带外 —— 它要解除的不是「尺子不确定」，而是
# 「这次测量的输入越界是否改变了逐局裁定」。把两条通道写成一条，等于让 裁定 16.4
# 明文要求登记的条目永远无法受理（A 移交单 §4）。
PROBE_KIND_REBLOWN = "reblown_single_source"
PROBE_KIND_CLIP_AT_TRAIN_ABSMAX = "clip_at_train_absmax"
# **白名单**语义：只有列在这里的 kind 免争议带检查。未知 kind 一律按带内处理 ——
# 新增通道必须显式进白名单并配自己的牙，防止豁免册退化成「翻案万能钥匙」。
BAND_EXEMPT_PROBE_KINDS = (PROBE_KIND_CLIP_AT_TRAIN_ABSMAX,)
# 裁定 10 的五条准入（增补四 §3 核可、A 移交单 §5 逐条备齐、D 独立复算 ALL_FIVE_PASS）。
# 键名与 D 的核验产物一致，便于逐条对账；缺任一键或值为 false ⇒ 条目不受理。
RULING10_CONDITION_KEYS = ("cond1_C_equals_train_absmax",
                           "cond2_verdicts_and_counts_identical",
                           "cond3_diffs_enumerated_and_verdict_same",
                           "cond4_probe_path_C_build_recorded",
                           "cond5_scope_measurement_valid_only")
# 晋级闸按 kind 分路（DR-008 决定 5）。**精确**放开而不是宽口径：
#   带内重测通道行为逐字不变（既有的 verified_ok -> probe_exonerated）；
#   只有 裁定 10 通道能把 violated 升为 probe_exonerated —— 因为它证明的正是
#   「越界这次测量没改变任何逐局裁定」，即 violated 的**后果**被探针消除，
#   而 reblown 通道消除的是「尺子不确定」，从来不能推翻一个真的超阈。
EXONERATION_PROMOTION_SOURCES = {
    PROBE_KIND_REBLOWN: ("verified_ok", "not_applicable_verified"),
    PROBE_KIND_CLIP_AT_TRAIN_ABSMAX: ("violated",),
}
DEFAULT_PROMOTION_SOURCES = ("verified_ok", "not_applicable_verified")
CLIP_C_TOL = 1e-6      # 登记的 clip_C 与产物自报值的比对容差（同一浮点数的两种写法）
# 「登记了假证据」的状态集合：命中即判 probe_exoneration_invalid（measurement_valid=False），
# 而不是静默维持原判。理由：册子里写了一条指向不存在 / 已被改写 / 根本不支持登记的证据，
# 比「没登记」更糟 —— 它让读者以为这个臂被核过。v1.5 把 裁定 10 通道的两种证据侧失效
# （探针没记录截断值、探针记录的截断值 ≠ 登记的 clip_C）并进同一家族。
EXONERATION_EVIDENCE_FAILURES = ("evidence_missing", "evidence_sha_mismatch",
                                 "probe_clip_unstated", "probe_clip_mismatch")

# 监管 §12 分派：blown_metric_impl 指纹写进裁定 JSON；**新产物缺指纹则拒判**。
# 存量产物按 sha256 登记在受版控的豁免册里（DR-002 护栏 1 的登记模型：
# 「被引用的裁定产物改为在受版本管理的文本文件里登记 sha256 + gate_build + gate_spec_sha256」）。
# 豁免册带 cutoff，挡不住新产物 —— 这是它相对于「按 mtime 判新旧」的关键优势。
KNOWN_BLOWN_IMPLS = ("52eae25ee2d7",)   # A 线 blown_frame_stats()+normalized_input_vector() 源码指纹
GRANDFATHER_DOC = "configs/b_blown_impl_grandfathered.json"
EXONERATION_DOC = "configs/b_probe_exonerations.json"
IMPL_REJECT_STATUS = "missing_new_reject"
# measurement_valid 的白名单（单一来源，禁止在各处散写）
IC_VALID_STATUSES = ("verified_ok", "not_applicable", "not_applicable_verified", "probe_exonerated")


def _g(row, *names, default=None):
    for n in names:
        if n in row and row[n] is not None:
            return row[n]
    return default


def classify_phase_field(row):
    """分辨 phase_trace 到底是哪一种语义 —— 仓库里同名字段有两套不兼容的词表。

    实测（2026-09-28）：
      scripts/audit_lift_base_truth.py 与 residual audit 写的 phase_trace = **6 元素状态机日志**
        例 ['approach','descend','grasp','lift','hold','done']，词表含 lift/done；
      scripts/b_eval_act_lift_v1.py / eval_act_lift_truth.py / eval_lerobot_act_runtime.py
        写的 phase_trace = **逐帧 phase_of() 分类**（最多 horizon=300 元素），
        词表只有 {hold, grasp, descend, approach}，**永不产出 done/lift**。
    v1 的 `phase_at_end or phase_trace[-1]` 兜底把两者混用，等于用 A 的语义去满足 B 的判据。
    v1.1 显式分流，并在输出里报告用的是哪一种。
    """
    pt = row.get("phase_trace") or []
    if not isinstance(pt, list) or not pt:
        return ("absent", None, None)
    vocab = set(map(str, pt))
    if len(pt) <= 8 and vocab <= CONTROLLER_LOG_VOCAB and ("done" in vocab or "lift" in vocab):
        return ("controller_log", str(pt[-1]), pt)
    return ("per_frame", str(pt[-1]), pt)


_SHA_CACHE: dict = {}


def _sha256_file(p):
    """带缓存的整文件 sha256（豁免册与探针证据都按它对齐，DR-002 护栏 1）。"""
    key = str(p)
    if key in _SHA_CACHE:
        return _SHA_CACHE[key]
    val = None
    try:
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for blk in iter(lambda: f.read(1 << 20), b""):
                h.update(blk)
        val = h.hexdigest()
    except Exception:                                   # noqa: BLE001
        val = None
    _SHA_CACHE[key] = val
    return val


def _load_registry(rel):
    """读受版控的登记册。返回 (dict, err)。册子不可读时 err 非空 —— 调用方必须据此
    **拒绝豁免**，不能静默当成空册（否则一次 IO 失败就等于把所有防线关掉）。"""
    p = _ROOT / rel
    if not p.exists():
        return {"entries": {}}, "missing:%s" % rel
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(obj, dict) or not isinstance(obj.get("entries"), dict):
            return {"entries": {}}, "malformed:%s（缺 entries 字典）" % rel
        return obj, None
    except Exception as exc:                            # noqa: BLE001
        return {"entries": {}}, "unreadable:%s（%s）" % (rel, exc)


def phase_vocab_status(row, kind, end_phase):
    """裁定 1：phase_at_end 与 phase_trace 的词表是否**互相矛盾**。返回 (status, note)。

    只在矛盾时报 mismatch，不在「佐证较弱」时报，以控制爆炸半径：
      mismatch_no_trace    phase_at_end ∈ {lift,done}（状态机词表）却无 phase_trace 佐证
      mismatch_per_frame   phase_at_end ∈ {lift,done} 而 phase_trace 是逐帧分类（永不产出 lift/done）
      unknown_vocab        phase_at_end 不属任何已知词表
    `phase_at_end ∈ PER_FRAME_VOCAB` 且无 trace **不算**矛盾：PER_FRAME_VOCAB ⊂
    CONTROLLER_LOG_VOCAB，两套词表都认这些值，此时沿用 v1.1 的分级取证据逻辑
    （held_at_end / final_rise / strict hold）。实测 48 个官方臂 phase_at_end 取值只有
    {hold 135, grasp 651, descend 19, approach 55}、phase_trace 覆盖 48/48、词表矛盾 0 局，
    故裁定 1 对官方臂零影响，只咬 residual 那类「状态机日志但没写 trace」的产物。
    """
    p = row.get("phase_at_end")
    if p is None:
        return ("absent_field", "")
    p = str(p)
    if p in ("", "unknown", "None"):
        return ("unknown_value", "")
    if p not in (CONTROLLER_LOG_VOCAB | PER_FRAME_VOCAB):
        return ("unknown_vocab", "phase_at_end=%r 不属任何已知词表（%s）"
                % (p, sorted(CONTROLLER_LOG_VOCAB | PER_FRAME_VOCAB)))
    if p in CTRL_ONLY_VOCAB:
        if kind == "controller_log":
            return ("consistent", "")
        if kind == "absent":
            return ("mismatch_no_trace",
                    "phase_at_end=%r 属状态机词表，但产物没写 phase_trace —— "
                    "门禁无法核验这个词表来源（裁定 1：判 INVALID，不猜）" % p)
        return ("mismatch_per_frame",
                "phase_at_end=%r 属状态机词表，而 phase_trace 是逐帧 phase_of() 分类"
                "（词表只有 %s，永不产出 lift/done）—— 两字段互相矛盾（裁定 1）"
                % (p, sorted(PER_FRAME_VOCAB)))
    return ("consistent", "")


def blown_impl_check(path, d, n_with):
    """监管 §12 分派：把 blown_metric_impl 写进裁定 JSON，**新产物缺指纹则拒判**。

    为什么必须拒判而不是 warn：§12 实测同一条轨迹、同一帧数口径下，两条代码路径算出
    0.2120 与 0.1180 两个 blown_frac（差 1.8 倍、逐局最大差 6.8 倍）。没有指纹就无法
    判断某份产物是哪把尺子量的，边缘臂（余量 0.010 那种）的裁定因此不可采信。
    """
    blk = d.get("input_contract")
    blk = blk if isinstance(blk, dict) else {}
    impl = blk.get("blown_metric_impl")
    out = {"impl": impl, "source": blk.get("blown_metric_source"),
           "blowup_threshold": blk.get("blowup_threshold"),
           "gate_tolerance": blk.get("gate_tolerance"),
           "known_impls": list(KNOWN_BLOWN_IMPLS), "grandfather_registry": GRANDFATHER_DOC,
           "artifact_sha256": None, "status": "no_blown_field", "reject": False, "note": ""}
    if n_with == 0:
        out["note"] = ("本产物 0 局记录 blown 字段，指纹检查不适用"
                       "（是否可裁定由 ic_status 的 unverified / not_applicable 分支决定）")
        return out
    sha = _sha256_file(Path(path))
    out["artifact_sha256"] = sha
    if impl in KNOWN_BLOWN_IMPLS:
        out["status"] = "known"
        return out
    if impl:
        out["status"] = "unknown_impl"
        out["note"] = ("产物声明 blown_metric_impl=%s，不在门禁已知实现清单 %s 内 —— "
                       "口径可能又漂了。裁定照常给出，但**不得**当作可引用数字，"
                       "须由 D 确认后加进 KNOWN_BLOWN_IMPLS。" % (impl, list(KNOWN_BLOWN_IMPLS)))
        return out
    reg, err = _load_registry(GRANDFATHER_DOC)
    ent = (reg.get("entries") or {}).get(sha or "")
    if err:
        out["status"] = IMPL_REJECT_STATUS
        out["reject"] = True
        out["note"] = ("缺 blown_metric_impl 指纹，且豁免册不可用（%s）—— "
                       "按新产物拒判（册子读不到时一律不豁免）" % err)
        return out
    if ent:
        out["status"] = "missing_legacy_grandfathered"
        out["grandfather_reason"] = ent.get("reason")
        out["grandfather_recorded"] = ent.get("recorded")
        out["grandfather_cutoff"] = reg.get("cutoff")
        out["note"] = ("存量产物：豁免册按 sha256 命中（记录时间 %s，cutoff %s）。它产出于 A 线 "
                       "blown 单一来源化（ADR-A-001，impl=52eae25ee2d7）之前，按 DR-002 护栏 1 "
                       "登记豁免；一旦重测，必须改用带指纹的新产物，豁免不随臂迁移。"
                       % (ent.get("recorded"), reg.get("cutoff")))
        return out
    out["status"] = IMPL_REJECT_STATUS
    out["reject"] = True
    out["note"] = ("**拒判**：产物记录了 blown 字段（%d 局）却没有 blown_metric_impl 指纹，"
                   "且不在豁免册 %s 内 —— 按监管 §12 分派视为新产物。修法：用带 ADR-A-001 "
                   "补丁的评测器重跑；确属存量则由 B 执行 scripts/b_blown_impl_registry.py --scan "
                   "登记（该工具带 cutoff，挡不住 cutoff 之后的新产物）。" % (n_with, GRANDFATHER_DOC))
    return out


def arm_key_candidates(path):
    """豁免册可用的键：整文件 sha256、文件名、去前缀的臂名、再去 _gatefields 后缀。"""
    name = Path(path).name
    stem = name[:-5] if name.endswith(".json") else name
    cands = [name, stem]
    for pre in ("official_act_truth20_", "audit_truth20_", "audit_truth20_gatefields_",
                "official_act_truth20_gatefields_"):
        if stem.startswith(pre):
            cands.append(stem[len(pre):])
    for suf in ("_gatefields", "_reblown", "_pre_phase_trace"):
        if cands[-1].endswith(suf):
            cands.append(cands[-1][:-len(suf)])
    return list(dict.fromkeys(cands))


def _artifact_train_absmax(d):
    """被裁定产物**自己**声明的训练期归一化输入 |x| 上界（裁定 15：两个键都读）。

    裁定 10 条件 ① 要求「C 必须钉死在该 ckpt 自己的训练期 absmax 上」，所以这个值
    必须从**被判产物**里取，不能信登记册里抄来的数 —— 否则豁免册写个 12.469445
    就能给任意臂免罪。
    """
    if not isinstance(d, dict):
        return None
    blocks = (d.get("input_constraints"), d.get("input_contract"))
    keys = ("train_time_norm_absmax", "blowup_threshold")
    for blk in blocks:
        if not isinstance(blk, dict):
            continue
        for k in keys:
            try:
                v = float(blk.get(k))
            except (TypeError, ValueError):
                continue
            if v > 0:
                return v
    return None


def _artifact_clip_c(d):
    """被裁定产物**自己**记录的截断值（执行侧约束），用于核验探针真截在登记的 C 上。"""
    if not isinstance(d, dict):
        return None
    for blk in (d.get("execution_constraints"), d.get("input_constraints")):
        if not isinstance(blk, dict):
            continue
        for k in INPUT_CONSTRAINT_KEYS:
            try:
                v = float(blk.get(k))
            except (TypeError, ValueError):
                continue
            if v > 0:
                return v
    return None


def _load_json_best(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:                                   # noqa: BLE001
        return None


def _clip_channel_precheck(hit, path):
    """裁定 10 通道（`clip_at_train_absmax`）自己的牙。返回 (status, note, extra)。

    status=None 表示五条全过。争议带检查对这条通道**不适用**（目标臂 blown=0.212
    必然带外），但「不能当翻案万能钥匙」这个目的用更强的四条替代：
      ① 只受理 scope=artifact —— 免罪的对象是一次具体测量，重跑即失效、必须重新探针；
      ② 登记的 clip_C 必须等于**被判产物自己**声明的训练期 absmax（容差 1e-6）；
      ③ 条目必须带 裁定 10 五条准入的逐条核对结果，五键全 true；
      ④ 条目必须带 D 的会签（裁定 16.4：B 写、D 会签）。
    探针产物本体与 sha256 的校验沿用带内通道的公共代码；此外再加一条独立核验：
    探针产物**自己**记录的截断值必须等于登记的 clip_C（见 _clip_evidence_check）。
    """
    extra = {"channel": PROBE_KIND_CLIP_AT_TRAIN_ABSMAX}
    scope = str(hit.get("scope") or "artifact")
    if scope != "artifact":
        return ("clip_channel_requires_artifact_scope",
                ("裁定 10 通道**只受理 scope=artifact**（键 = 被判产物的 sha256），"
                 "本条登记为 scope=%s。理由：免罪的对象是「某 ckpt × 某 plain 产物」这**一次**"
                 "测量，不是整条臂；artifact scope 天然重跑即失效，必须重新探针。"
                 "ic_status 保持原判。" % scope), extra)
    try:
        clip_c = float(hit.get("clip_C"))
    except (TypeError, ValueError):
        clip_c = None
    extra["registered_clip_C"] = clip_c
    if clip_c is None or clip_c <= 0:
        return ("clip_c_undeclared",
                ("裁定 10 条目必须声明 clip_C（= 该 ckpt 训练期归一化 |x| 上界）；"
                 "实测登记值 %r。ic_status 保持原判。" % (hit.get("clip_C"),)), extra)
    own = _artifact_train_absmax(_load_json_best(path))
    extra["artifact_train_absmax"] = own
    if own is None:
        return ("artifact_train_absmax_unstated",
                ("无法核验 裁定 10 条件 ①：被判产物自己**没有**声明训练期 absmax"
                 "（input_constraints.train_time_norm_absmax / input_contract.blowup_threshold 都缺）。"
                 "不能拿登记册里的数替它主张。ic_status 保持原判。"), extra)
    if abs(own - clip_c) > CLIP_C_TOL:
        return ("clip_c_not_train_absmax",
                ("裁定 10 条件 ① **不成立**：登记 clip_C=%s，而被判产物自己声明的训练期 absmax=%s。"
                 "C 必须钉死在该 ckpt 自己的训练期上界上 —— A 的判别力反证已实测：C=5.0 时 "
                 "seed 5007 的 verdict 翻转、insufficient_lift 1→0，即「截得越紧越安全」是假的。"
                 "ic_status 保持原判。" % (clip_c, own)), extra)
    conds = hit.get("ruling10_conditions")
    conds = conds if isinstance(conds, dict) else {}
    missing = [k for k in RULING10_CONDITION_KEYS if k not in conds]
    false_ones = [k for k in RULING10_CONDITION_KEYS if conds.get(k) is not True]
    extra["ruling10_conditions"] = {k: conds.get(k) for k in RULING10_CONDITION_KEYS}
    if missing or false_ones:
        return ("entry_conditions_incomplete",
                ("裁定 16.4 要求条目含「裁定 10 五条准入的逐条核对」：缺 %s、非 true %s。"
                 "五条准入是 D 已核可的事实基础（增补四 §3），登记册必须把它抄成可核对的结构，"
                 "不能只留一句 reason。ic_status 保持原判。"
                 % (missing or "无", false_ones or "无")), extra)
    cosign = hit.get("cosign")
    cosign = cosign if isinstance(cosign, dict) else {}
    extra["cosign"] = dict(cosign)
    if not str(cosign.get("by") or "").strip() or cosign.get("fact_basis") is not True:
        return ("cosign_missing",
                ("裁定 16.4 原文：免罪册条目「由 B 写、**D 会签**」。本条会签缺失或不成立"
                 "（by=%r、fact_basis=%r）。B 不能自签。ic_status 保持原判。"
                 % (cosign.get("by"), cosign.get("fact_basis"))), extra)
    return (None, "", extra)


def _clip_evidence_check(hit, clip_c, evidence_path):
    """裁定 10 通道的最后一道牙：探针产物**自己**必须记录截在登记的 C 上。"""
    d = _load_json_best(evidence_path)
    got_c = _artifact_clip_c(d)
    if got_c is None:
        return ("probe_clip_unstated",
                ("探针产物 %s **没有**记录执行侧截断值（execution_constraints.norm_input_clip / "
                 "input_constraints.clip_norm_input 都缺）—— 无法核验它真截在 C=%s 上。"
                 "判 probe_exoneration_invalid。" % (hit.get("artifact"), clip_c)))
    if abs(got_c - float(clip_c)) > CLIP_C_TOL:
        return ("probe_clip_mismatch",
                ("探针产物自己记录的截断值 %s ≠ 登记的 clip_C=%s —— 登记的证据不是这次探针，"
                 "或探针跑错了 C。判 probe_exoneration_invalid。" % (got_c, clip_c)))
    return (None, "")


def probe_exoneration_check(path, mean_blown, impl_status=None, artifact=None):
    """裁定 3：VALID_probe_exonerated。只有**已登记且证据可校验**的探针才能解除 §12 保留。

    v1.5（DR-008）起分两条通道，各自带自己的牙；`artifact` 是被判产物已解析的 dict，
    传 None 时按需从磁盘读（保持三参调用方向后兼容）。

    通道一 `reblown_single_source`（裁定 3 / 增补三 §12 争议带重测）——带牙三条：
      1. mean_blown 必须落在争议带 [0.03, 0.08]；带外一律不受理（§12 原文 INVALID 维持），
         防止豁免册被当成「翻案万能钥匙」；
      2. 证据产物必须真实存在；
      3. 证据产物 sha256 必须与登记一致 —— 证据被改写/换过就判 probe_exoneration_invalid
         （measurement_valid=False），而不是静默忽略。

    通道二 `clip_at_train_absmax`（裁定 10 / 裁定 16.4，v1.5 新增）——免争议带检查，
    但换成**更强**的四条（见 _clip_channel_precheck）+ 一条证据侧核验
    （见 _clip_evidence_check）：只受理 scope=artifact、clip_C 必须等于被判产物自己
    声明的训练期 absmax、条目必须带五条准入的逐条核对、必须有 D 的会签。
    这条通道是 0.212 这种**带外**臂的唯一救济路径（裁定 12：blown 超阈 ⇒「这次测量
    不可信」，裁定 10 是唯一救济通道）。

    作用域（scope）——这一条是为了防止「豁免连带」：
      artifact（默认）只按被裁定产物的 sha256 命中，重跑即失效；
      arm       按臂名命中，但**要求**该产物自带已知 blown_metric_impl 指纹。
                没有这条要求，同名的**旧**产物（无指纹、非单一来源口径）会被一并豁免，
                等于用一次重测把整条历史洗白。实测本仓就有这一对：
                official_act_truth20_<arm>.json（旧，缺指纹）与 reblown/<arm>.json（新，带指纹）。
    """
    reg, err = _load_registry(EXONERATION_DOC)
    entries = reg.get("entries") or {}
    if err and not entries:
        return None
    sha = _sha256_file(Path(path))
    hit = key = None
    out_scope = None
    for cand in ([sha] if sha else []) + arm_key_candidates(path):
        if cand and cand in entries:
            ent = entries[cand] or {}
            scope = str(ent.get("scope") or ("artifact" if cand == sha else "arm"))
            if scope == "arm" and cand != sha and impl_status != "known":
                return {"registry": EXONERATION_DOC, "registry_error": err, "key": cand,
                        "scope": scope, "probe_kind": ent.get("probe_kind"),
                        "ruling_ref": ent.get("ruling_ref"), "evidence_artifact": ent.get("artifact"),
                        "evidence_sha256": None, "disputed_band": list(DISPUTED_BLOWN_BAND),
                        "mean_blown_frames_frac": mean_blown,
                        "status": "scope_requires_known_impl",
                        "note": ("臂级豁免**不受理**：本产物 blown_metric_impl=%s（状态 %s），"
                                 "而臂级豁免只对单一来源口径（已知指纹）的产物生效。"
                                 "否则同臂的旧产物会被一次重测连带洗白。ic_status 保持原判。"
                                 % (impl_status, impl_status))}
            hit, key = ent, cand
            out_scope = scope
            break
    if hit is None:
        return None
    lo, hi = DISPUTED_BLOWN_BAND
    # v1.5（DR-008）：通道由 probe_kind 决定。缺省按 reblown 处理（保守：未知 kind 带内）。
    kind = str(hit.get("probe_kind") or PROBE_KIND_REBLOWN)
    band_checked = kind not in BAND_EXEMPT_PROBE_KINDS
    out = {"registry": EXONERATION_DOC, "registry_error": err, "key": key,
           "scope": out_scope,
           "probe_kind": kind, "ruling_ref": hit.get("ruling_ref"),
           "evidence_artifact": hit.get("artifact"), "evidence_sha256": None,
           "disputed_band": [lo, hi], "mean_blown_frames_frac": mean_blown,
           "band_checked": band_checked,
           "status": None, "note": ""}
    clip_c = None
    if not band_checked:
        # 裁定 10 通道：免争议带检查，换成 _clip_channel_precheck 的四条更强的牙。
        st, note, extra = _clip_channel_precheck(hit, path)
        out.update(extra)
        clip_c = extra.get("registered_clip_C")
        # DR-008 决定 7：会签锚在旧 build 上**不拒判**（否则死锁：条目只能在代码改完之后写），
        # 但必须显式回显，让「D 该重跑一次核验」这件事在裁定里看得见。
        cs = extra.get("cosign") or {}
        cb = str(cs.get("gate_build_at_cosign") or cs.get("gate_build") or "")
        out["cosign_build_current"] = GATE_BUILD
        out["cosign_build_matches"] = (cb == GATE_BUILD) if cb else None
        if st:
            out["status"], out["note"] = st, note
            return out
    elif mean_blown is None or not (lo <= float(mean_blown) <= hi):
        out["status"] = "out_of_band_refused"
        out["note"] = ("豁免**不受理**：mean_blown_frames_frac=%s 不在争议带 [%.2f, %.2f] 内。"
                       "§12 明确「两条路径都远超 0.05 的臂，INVALID 维持」——"
                       "豁免册不能用来翻这个案。ic_status 保持原判。"
                       "（本条按 probe_kind=%s 走带内通道；若该臂另有 裁定 10 的 "
                       "clip-at-train-absmax 探针，须以 probe_kind=%s 另立条目走 DR-008 通道。）"
                       % (mean_blown, lo, hi, kind, PROBE_KIND_CLIP_AT_TRAIN_ABSMAX))
        return out
    art = _ROOT / str(hit.get("artifact") or "")
    if not str(hit.get("artifact") or "") or not art.exists():
        out["status"] = "evidence_missing"
        out["note"] = ("豁免登记的证据产物不存在（%s）—— 判 probe_exoneration_invalid，"
                       "measurement_valid=False。豁免必须有可校验的证据，不能只有一句话。"
                       % hit.get("artifact"))
        return out
    want, got = hit.get("sha256"), _sha256_file(art)
    if want and got != want:
        out["status"] = "evidence_sha_mismatch"
        out["note"] = ("豁免证据 sha256 不匹配：登记 %s，实测 %s —— 证据已被改写或换了文件，"
                       "判 probe_exoneration_invalid。" % (want, got))
        return out
    if not band_checked:
        # 证据侧最后一条独立核验：探针产物自己必须记录截在登记的 C 上。
        st, note = _clip_evidence_check(hit, clip_c, art)
        if st:
            out["status"], out["note"] = st, note
            return out
        out["probe_clip_C"] = clip_c
    out["status"] = "exonerated"
    out["evidence_sha256"] = got
    if band_checked:
        out["note"] = ("§12 争议带保留**已解除**：探针 %s（证据 %s，sha256 %s，裁定依据 %s）。"
                       "本臂 ic_status 由 verified_ok 升为 probe_exonerated；引用时仍须带 ±0.005 "
                       "敏感带与余量（余量 %.3f）。"
                       % (kind, hit.get("artifact"), (got or "")[:12],
                          hit.get("ruling_ref"), abs(float(mean_blown) - INPUT_BLOWUP_TOL)))
    else:
        out["note"] = ("裁定 10 免罪**成立**：clip-at-train-absmax 探针（C=%s = 本 ckpt 训练期 "
                       "absmax，证据 %s，sha256 %s，裁定依据 %s，D 会签 %s）。ic_status 由 violated "
                       "升为 probe_exonerated，measurement_valid=True。**引用纪律**：引用的数字取自 "
                       "plain 产物；探针产物 composite_policy=true，不得当官方臂数字引用。固定写法见 "
                       "docs/a_handoff_to_b_probe_exoneration_gap_20260928.md §5。"
                       % (clip_c, hit.get("artifact"), (got or "")[:12], hit.get("ruling_ref"),
                          ((hit.get("cosign") or {}).get("by") or "?")))
    return out


def insuff_diagnostic(judged, final_rise_min):
    """B-3：给 insufficient_lift 加「差多少」，而不只是计数。

    为什么值得单列：insufficient_lift 是当前主失效模式（A 线 21 臂合计 219 局），
    且 final_rise 密集分布在 0.035–0.045，正好横跨 C5=0.04 —— 只有计数无法回答
    「差一点点还是差很多」，也就无法判断该修策略还是该由 D 重定阈值（ADR-A-005 #3）。
    """
    vals = [b["final_rise"] for b in judged
            if b["verdict"] == "insufficient_lift" and b.get("final_rise") is not None]
    if not vals:
        return {"n": 0, "note": "本产物无 insufficient_lift 局"}
    a = np.asarray(vals, dtype=float)
    thr = float(final_rise_min)
    edges = [0.0, 0.01, 0.02, 0.03, thr - 0.005, thr]
    hist = {}
    for i in range(len(edges) - 1):
        hist["[%.3f,%.3f)" % (edges[i], edges[i + 1])] = int(((a >= edges[i]) & (a < edges[i + 1])).sum())
    hist[">=%.3f(不应出现)" % thr] = int((a >= thr).sum())
    return {
        "n": int(a.size), "threshold": thr,
        "final_rise_min": round(float(a.min()), 5), "final_rise_median": round(float(np.median(a)), 5),
        "final_rise_p10": round(float(np.percentile(a, 10)), 5),
        "final_rise_p90": round(float(np.percentile(a, 90)), 5),
        "final_rise_max": round(float(a.max()), 5),
        "gap_median": round(float(thr - np.median(a)), 5),
        "gap_p90_worst": round(float(thr - float(np.percentile(a, 10))), 5),
        "gap_min_best": round(float(thr - a.max()), 5),
        "n_within_0p005": int((a >= thr - 0.005).sum()),
        "n_within_0p010": int((a >= thr - 0.010).sum()),
        "frac_within_0p005": round(float((a >= thr - 0.005).mean()), 3),
        "histogram": hist,
        "note": ("差多少：中位差 %.4f m、最好的一局差 %.4f m；%.0f%% 的 insuff 局落在门槛下方 "
                 "0.005 m 内（即 ±0.005 敏感带一翻就变受控成功）。这个比例是「该修策略还是该重定 "
                 "C5」的判据：比例高说明主要卡在阈值上，须走 ADR-A-005 #3 由 D 裁定，"
                 "不能靠训练解决。" % (thr - float(np.median(a)), thr - float(a.max()),
                                    100 * float((a >= thr - 0.005).mean()))),
    }


def judge_row(row, rise_cap, final_rise_min):
    """返回 (verdict, checks, evidence)。

    verdict ∈ controlled_success / provisional_pass / over_lift / insufficient_lift
             / flick / failure / unjudged
      insufficient_lift = 局末仍夹持但 final_rise < 门槛（抬得不够高），v1.2 从 flick 里分出
      provisional_pass = C1-C4 全过，但「局末仍夹持」这一条**无字段可证**
                         （final_rise 与 held_at_end 都缺）。v1 会把它算成 controlled_success，
                         这是 v1.1 修掉的假阳性通道：它不得进 P1 晋级主张，只能列为待补测。
    """
    tk = str(_g(row, "terminal_kind", default="") or "")
    if tk in UNJUDGED_TERMINALS:
        return "unjudged", {"terminal_kind": tk}, {
            "terminal_kind": tk, "unjudged_reason": "terminal_%s" % tk,
            "phase_field_kind": None, "end_phase": None, "phase_vocab_status": None}

    raw = bool(_g(row, "success_raw", "success", "raw_success", default=False))
    grip = bool(_g(row, "grasp_verified", default=False))
    rise = float(_g(row, "max_rise", default=0.0) or 0.0)
    fin = _g(row, "final_rise", default=None)
    held_end = _g(row, "held_at_end", "held_end", "held", default=None)
    kind, pt_last, pt = classify_phase_field(row)
    end_phase = str(_g(row, "phase_at_end", default=None) or pt_last or "unknown")

    # ---- 裁定 1（v1.3）：phase 词表矛盾 -> 本局移出分母，不再静默判 flick ----
    # 旧行为：kind=="absent" 时 end_phase 取 phase_at_end（可能是状态机的 'done'），
    # 落到最后一个分支只认 HOLD_PHASES_STRICT={"hold"} -> c4=False -> 判 flick。
    # 于是「状态机跑完 hold 满 30 帧、方块全程在爪里」被报成「脱手弹射」，
    # 一个 20/20 的臂显示为 20 局全 flick（daily_report.md §4）。
    # 新行为：矛盾即 unjudged（v4 不变量：unknown 既不是成功也不是失败，一律移出分母），
    # 并在文件级判 measurement_invalid，让上游去补字段而不是接受一个假失效模式。
    vstat, vnote = phase_vocab_status(row, kind, end_phase)
    if vstat.startswith("mismatch") or vstat == "unknown_vocab":
        return "unjudged", {"phase_vocab": False}, {
            "phase_field_kind": kind, "end_phase": end_phase, "c4_basis": "not_evaluated_phase_vocab",
            "phase_vocab_status": vstat, "phase_vocab_note": vnote,
            "unjudged_reason": "phase_vocab_mismatch",
            "terminal_kind": (tk or None), "n_phase_trace": (len(pt) if pt else 0)}

    # C4：局末仍处夹持。按 phase 字段的语义分别取证据。
    if kind == "controller_log":
        # 状态机到达 hold/done 需要 hold 满 HOLD_STEPS=30 帧，是强证据。
        c4 = end_phase in CONTROLLER_LOG_HOLD
        c4_basis = "controller_log_reached_%s" % end_phase
    elif held_end is not None:
        c4 = bool(held_end) and end_phase in HOLD_PHASES_WITH_EVIDENCE
        c4_basis = "held_at_end=%s & end_phase=%s" % (held_end, end_phase)
    elif fin is not None:
        c4 = end_phase in HOLD_PHASES_WITH_EVIDENCE
        c4_basis = "end_phase=%s (held_at_end 缺，由 C5 final_rise 承担)" % end_phase
    else:
        # 既无 held_at_end 也无 final_rise：per-frame 的 "grasp" 只说明两指张开>1.2cm，
        # 空爪与夹着方块同标签，不足以证明局末仍夹持。
        c4 = end_phase in HOLD_PHASES_STRICT
        c4_basis = ("end_phase=%s（strict：仅认 hold）" % end_phase
                    if kind == "per_frame" else "end_phase=%s" % end_phase)

    checks = {
        "grasped": raw and grip,
        "rise_cap": rise <= rise_cap,
        "end_phase": c4,
        "final_rise": (None if fin is None else float(fin) >= final_rise_min),
        "held_at_end": (None if held_end is None else bool(held_end)),
    }
    evidence = {"phase_field_kind": kind, "end_phase": end_phase, "c4_basis": c4_basis,
                "terminal_kind": (tk or None),
                "n_phase_trace": (len(pt) if pt else 0),
                "phase_vocab_status": vstat,
                "phase_vocab_note": (vnote or None), "unjudged_reason": None}
    if not raw:
        return "failure", checks, evidence

    # over_lift 与 flick 必须分开命名：两者都过不了 rise_cap，但指向完全不同的旋钮。
    #   over_lift = 抓住了、局末仍夹持、方块没掉，只是上升停不下来
    #               -> 根因是 hold/done 帧上的 dz 正泄漏（执行侧 deadband 或训练侧可修）
    #   flick     = 方块脱离夹爪（held_at_end=False 或 final_rise<min）
    #               -> 根因是对齐前闭爪 / 夹到边角弹射（不是 deadband 能修的）
    # 实测依据：runs/infra/b_flick_sweep/mb_none.json 的 seed 5002/5015
    #   max_rise=0.376/0.634 但 final_rise=0.3592/0.6233、held_at_end=True、end_phase=hold
    #   —— 方块全程在爪里，v1 把它和真弹射一起叫 "flick" 是误命名。
    still_holding = (checks["held_at_end"] is True) or (
        checks["held_at_end"] is None and checks["final_rise"] is True)
    # v1.2（回应 A 线 2026-09-28 的口径问题，docs/lerobot_act_env_setup_20260928.md §6 要点 3）：
    # 原实现把 `raw_success ∧ ¬C5` 一律叫 flick，于是「把方块弹射出去」和「方块全程在爪里、
    # 只是没抬到 0.04 m」在汇总行里混为一谈，只有翻 failed_checks 才能分开。
    # 实测那 14 局 max_rise 全 ≤0.042（远低于 rise_cap 0.15）且 held_at_end=20/20，
    # 根本不是弹射。两者指向**相反**的修复方向（dz 幅度不足 vs 对齐/闭爪时机），必须分开。
    #   object_lost        局末已不夹持（或无 held_at_end 证据而 final_rise<min）-> flick
    #   insufficient_lift  局末仍夹持但 final_rise<min，且未超 rise_cap -> 抬得不够高
    object_lost = (checks["held_at_end"] is False) or (
        checks["held_at_end"] is None and checks["final_rise"] is False)
    insufficient_lift = checks["held_at_end"] is True and checks["final_rise"] is False

    if not checks["grasped"] or not checks["end_phase"] or object_lost:
        return "flick", checks, evidence
    if not checks["rise_cap"]:
        return ("over_lift" if still_holding else "flick"), checks, evidence
    if insufficient_lift:
        return "insufficient_lift", checks, evidence
    if checks["final_rise"] is None and checks["held_at_end"] is None:
        return "provisional_pass", checks, evidence
    return "controlled_success", checks, evidence


def not_applicable_check(d, rows, n_with, learned):
    """裁定 2（v1.3）：无归一化策略的 `not_applicable` 声明路径 —— **带牙**。

    背景：SAC 直接吃 raw 60 维 obs（`scripts/train_residual_lift.py` 未用 VecNormalize），
    不存在「归一化输入」，因此 `norm_input_blown_frames_frac` 没有对应量。按 v1.2 §2.6
    它会被判 unverified→INVALID，即使 raw 20/20、受控 20/20（daily_report.md §4/ADR-A-005 #2）。
    A 线明确**不自行绕过**（不删 ckpt 字段、不伪造 0.0），把选项交回 B/D；D 裁定走
    「显式 not_applicable 声明 + 原始 obs 区间检查」。

    牙在哪里：声明本身不放行。必须同时给出
      (a) 非空 reason；
      (b) 训练期原始 obs 区间 train_time_obs_absmax（标量或逐维列表）；
      (c) 闭环原始 obs 区间 closed_loop_obs_absmax 或逐局 raw_obs_absmax；
    并用 (b)×(1+RAW_OOB_TOL) 检查 (c)。超界比例 > INPUT_BLOWUP_TOL -> violated_out_of_range
    （与归一化炸穿同性质：策略在没见过的输入上跑）。任何一项缺失都判 INVALID。
    """
    blk = d.get("input_contract") if isinstance(d.get("input_contract"), dict) else {}
    decl = blk.get(NA_KEY)
    out = {"declared": bool(decl), "status": "absent", "note": "", "reason": None,
           "obs_space": None, "train_time_obs_absmax": None, "closed_loop_obs_absmax": None,
           "rows_with_raw_obs_absmax": 0, "limit_with_tol": None, "rows_out_of_range": None,
           "oob_frac": None, "tol": RAW_OOB_TOL}
    if not isinstance(decl, dict) or not decl:
        if learned and n_with == 0:
            out["note"] = ("学习策略产物既无 norm_input_blown_frames_frac，也无 input_contract.%s "
                           "声明 —— 按监管 增补二 §3 判 INVALID。若该策略确实不做归一化"
                           "（如 SAC 直吃 raw obs），走裁定 2 的声明路径：在产物里写 "
                           "input_contract.%s = {reason, obs_space, train_time_obs_absmax, "
                           "closed_loop_obs_absmax 或逐局 raw_obs_absmax}。" % (NA_KEY, NA_KEY))
        return out
    out["reason"] = decl.get("reason")
    out["obs_space"] = decl.get("obs_space")
    ta = decl.get("train_time_obs_absmax")
    rowvals = [r.get("raw_obs_absmax") for r in rows if r.get("raw_obs_absmax") is not None]
    out["rows_with_raw_obs_absmax"] = len(rowvals)
    cl = decl.get("closed_loop_obs_absmax")
    if cl is None and rowvals:
        cl = round(max(float(v) for v in rowvals), 4)
    out["train_time_obs_absmax"] = ta
    out["closed_loop_obs_absmax"] = cl
    if n_with > 0:
        out["status"] = "contradicted_by_blown_field"
        out["note"] = ("产物同时有 %d 局 norm_input_blown_frames_frac 又声明「无归一化」—— "
                       "两者矛盾，声明被忽略，按 blown 字段正常裁定。" % n_with)
        return out
    if not str(decl.get("reason") or "").strip():
        out["status"] = "declared_no_reason"
        out["note"] = "声明了 not_applicable 却没写 reason —— 声明不等于豁免，判 INVALID。"
        return out
    try:
        limit_base = float(ta if not isinstance(ta, (list, tuple)) else max(float(x) for x in ta))
    except Exception:                                   # noqa: BLE001
        limit_base = None
    if limit_base is None or limit_base <= 0:
        out["status"] = "declared_no_train_range"
        out["note"] = ("声明缺可信的 train_time_obs_absmax（实测 %r）—— 没有训练期区间就无从判"
                       "「越界」，判 INVALID。修法：训练时落盘 obs absmax（ADR-A-005 #2 选项 i）。" % (ta,))
        return out
    limit = limit_base * (1.0 + RAW_OOB_TOL)
    out["limit_with_tol"] = round(limit, 4)
    if cl is None:
        out["status"] = "declared_no_closed_loop_range"
        out["note"] = ("声明有训练期区间（%.4f）但**没有闭环 raw obs 区间**（既无 "
                       "closed_loop_obs_absmax 也无逐局 raw_obs_absmax，0/%d 局）—— 区间检查做不了，"
                       "判 INVALID。这就是裁定 2 的「带牙」：光声明不放行。" % (limit_base, len(rows)))
        return out
    if rowvals:
        n_oob = sum(1 for v in rowvals if float(v) > limit)
        denom = len(rowvals)
    else:
        n_oob = 1 if float(cl) > limit else 0
        denom = 1
    out["rows_out_of_range"] = n_oob
    out["oob_frac"] = round(n_oob / max(1, denom), 4)
    if out["oob_frac"] > INPUT_BLOWUP_TOL:
        out["status"] = "violated_out_of_range"
        out["note"] = ("原始 obs 区间检查**未过**：闭环 raw obs absmax 超出训练期上界 "
                       "%.4f×(1+%.2f)=%.4f 的局占 %.0f%% —— 与归一化炸穿同性质，判 INVALID。"
                       % (limit_base, RAW_OOB_TOL, limit, 100 * out["oob_frac"]))
        return out
    out["status"] = "verified_in_range"
    out["note"] = ("原始 obs 区间检查通过：闭环 raw obs absmax=%s ≤ 训练期上界 %.4f×(1+%.2f)=%.4f，"
                   "越界局 %d/%d。声明理由：%s"
                   % (cl, limit_base, RAW_OOB_TOL, limit, n_oob, denom, decl.get("reason")))
    return out


def judge_file(path, args):
    d = json.loads(Path(path).read_text())
    rows = d.get("rows") or d.get("per_episode") or []
    if not rows:
        return {"file": str(path), "error": "no rows/per_episode found", "keys": sorted(d)[:12]}
    buckets, per = [], []
    for r in rows:
        v, c, ev = judge_row(r, args.rise_cap, args.final_rise)
        fin_val = _g(r, "final_rise", default=None)
        interv = int(_g(r, "guard_interventions", default=0) or 0) + int(_g(r, "recovery_events", default=0) or 0)
        rec = {"seed": r.get("seed"), "verdict": v, "checks": c, "evidence": ev,
               "max_rise": round(float(_g(r, "max_rise", default=0.0) or 0.0), 4),
               "final_rise": (round(float(fin_val), 4) if isinstance(fin_val, (int, float)) else None),
               "end_phase": ev["end_phase"], "interventions": interv,
               "failed_checks": [k for k, val in c.items() if val is False],
               "not_evaluated": [k for k, val in c.items() if val is None],
               "steps": r.get("steps"), "terminal_kind": ev["terminal_kind"]}
        per.append(rec); buckets.append(rec)

    # ---- 字段完备性分级：决定这份产物能不能承载 P1 主张 ----
    present = lambda k: sum(1 for r in rows if r.get(k) is not None)
    have = {"final_rise": present("final_rise"), "held_at_end": (present("held_at_end")
            or present("held_end") or present("held")), "terminal_kind": present("terminal_kind"),
            "phase_at_end": present("phase_at_end"), "max_rise": present("max_rise"),
            "grasp_verified": present("grasp_verified")}
    missing = sorted(k for k, n in have.items() if n == 0)
    # v1.3：unjudged 行的 evidence 里 phase_field_kind 可能为 None（终局分支不评 phase），
    # 直接 sorted() 会因 None 与 str 混排抛 TypeError —— 这是加裁定 1 时顺带暴露的实现约束。
    kinds = {(b.get("evidence") or {}).get("phase_field_kind") for b in buckets}
    if not missing:
        field_class = "strict"
    elif set(missing) <= {"final_rise", "held_at_end", "terminal_kind", "phase_at_end"}:
        field_class = "partial"
    else:
        field_class = "blind"

    # ---- v1.4（裁定 14 / DR-D09）：证据不足 ⇒ 禁止输出失效模式标签 ----
    # 只禁**失效模式**标签；provisional_pass 是 v1.1 有意设计的「待补测」档，不动；
    # failure 是通用裁定，不动；controlled_success 由 C1..C5 全过得出，不在本条范围。
    missing_label_critical = sorted(set(missing) & set(LABEL_CRITICAL_FIELDS))
    labels_reportable = not missing_label_critical
    n_labels_abstained = 0
    if not labels_reportable:
        for b in buckets:
            if b["verdict"] in FAILURE_MODE_LABELS:
                ev_b = b.get("evidence")
                if isinstance(ev_b, dict):
                    # 保留证据不销毁（对齐 A 在 summarize_lerobot_act_arms.py 里的 *_raw 做法）：
                    # 改判之后仍要能回答「它本来被判成了什么」。
                    ev_b["label_before_abstain"] = b["verdict"]
                    ev_b["unjudged_reason"] = "evidence_missing_label_critical"
                b["verdict"] = "unjudged"
                n_labels_abstained += 1
    label_scope_note = (
        None if labels_reportable else
        "field_class=%s，标签关键字段缺 %s ⇒ %d 局失效模式标签改判 unjudged（裁定 14）。"
        "原标签保留在 per_episode[].evidence.label_before_abstain"
        % (field_class, ",".join(missing_label_critical), n_labels_abstained))

    judged = [b for b in buckets if b["verdict"] != "unjudged"]
    unjudged = [b for b in buckets if b["verdict"] == "unjudged"]
    indep = [b for b in judged if b["interventions"] == 0]
    cnt = lambda seq, v: sum(1 for b in seq if b["verdict"] == v)
    # v1.3（裁定 1）：unjudged 不再是一个笼统的桶 —— 「终局不可判」与「phase 词表矛盾」
    # 指向完全不同的修法（前者是 terminal_kind 语义，后者是评测器缺字段），必须分开计数，
    # 否则修好一个会掩盖另一个。
    unj_reason = {}
    for b in unjudged:
        k = (b.get("evidence") or {}).get("unjudged_reason") or "unspecified"
        unj_reason[k] = unj_reason.get(k, 0) + 1
    n_phase_mismatch = unj_reason.get("phase_vocab_mismatch", 0)
    # ---- 终局语义自检（v4：终局与外部截断不能合并）----
    hor = int(d.get("horizon", 0) or 0)
    n_full = sum(1 for r in rows if hor and int(r.get("steps") or 0) >= hor)
    n_termfail = sum(1 for r in rows if str(r.get("terminal_kind") or "").startswith("terminated_failure"))
    terminal_semantics = {
        "horizon": hor, "rows_at_full_horizon": n_full, "rows_labeled_terminated_failure": n_termfail,
        "suspect_truncation_labeled_as_failure": (n_termfail > 0 and n_full == n_termfail),
        "note": ("全部行都跑满 horizon 却被标成 terminated_failure："
                 "envs/robosuite_pickplace.py:135 的 step() 恒返回 terminated=False，"
                 "这些行其实是 truncated_horizon。裁定不变（任务确实没成功），"
                 "但该标签不得进训练视图——v4 要求终局与外部截断分开，bootstrap 语义不同。"
                 if (n_termfail > 0 and n_full == n_termfail) else ""),
    }

    ec = d.get("execution_constraints") or {}
    ic_raw = d.get("input_constraints") or {}
    exec_active = sorted(k for k, v in ec.items() if v is not None)
    # v1.2.1 修的真实缺陷：原实现只看 `execution_constraints`，于是**推理期对归一化输入
    # 做截断**这一介入不被计入复合 policy。实测后果（本仓自己的产物）：
    #   runs/infra/b_normclip*/ 里 9 个 clip 臂全部 --clip-norm-input 开启，
    #   但门禁给它们的裁定是 composite_policy=false / active_constraints=[]，
    #   连「裁定对象是 policy+约束，不是底模」这条 warn 都不会打印。
    # 而 scripts/b_eval_act_lift_v1.py:226 的注释早就写明
    #   「clip_norm_input 属于策略输入预处理，改变的是复合 policy」—— 意图有、实现漏了。
    # 危害是**不对称标注**：A 的评测器把同一介入写进 execution_constraints，会被正确标成
    # composite；B 的写进 input_constraints，就不会。跨线比较于是变成在比两类不同对象，
    # 而 clip1.5「受控口径最优 4/20」这类数字会被当成底模能力引用。
    input_active = sorted(k for k in INPUT_CONSTRAINT_KEYS if ic_raw.get(k) is not None)
    active_constraints = sorted(set(exec_active) | set(input_active))
    constraint_sides = {**{k: "exec" for k in exec_active},
                        **{k: "input" for k in input_active}}

    # ---- 策略输入契约（v1.1 新增，2026-09-28 归一化事故的直接产物）----
    # scripts/train_act_lift.py:44 用 std = x.std(0) + 1e-6 归一化，对**近常量维无下限保护**。
    # Lift 的 state obs 第 9/11 维是 cos(joint2)/cos(joint4)，teacher 里这两个关节几乎不动，
    # std 只有 9.7e-05 / 9.3e-04；第 28-34 维是 joint_acc，std 也偏小。
    # 训练时归一化 |x| 上界 = 23.7；闭环一旦偏离 teacher 轨迹，这几维被放大到 1e3~2e4
    # （实测 runs/infra/b_normclip/noclip.json：seed 5007 的 |x|max = 20403，
    #   20 局里 89~97% 的帧都超出训练输入范围）。第一层激活炸穿、tanh 饱和，
    # 策略输出 ±1 抖动 —— 此时「成功率」测的不是策略能力，而是数值事故。
    # 所以输入契约违例必须让 gate 直接判「测量无效」，而不是判「policy 失败」。
    blow = [r.get("norm_input_blown_frames_frac") for r in rows if r.get("norm_input_blown_frames_frac") is not None]
    absmax = [r.get("norm_input_absmax") for r in rows if r.get("norm_input_absmax") is not None]
    ic_blk = d.get("input_contract") if isinstance(d.get("input_contract"), dict) else {}
    # v1.3 修一处误导性输出：训练期上界过去只从 `input_constraints.train_time_norm_absmax` 取，
    # 而 A 线官方产物把它写在 `input_contract.blowup_threshold`（**按 ckpt 现算**）。
    # 这正是 ADR-A-005 #4：A 按 ckpt 现算、B 曾用常量 23.85，同族数值一致但规则不同，
    # 跨族引用时 0.05 容差不是同一把尺子。实测后果：48 个官方臂 `input_constraints` 全为空
    # -> train_max=None -> INVALID 的 note 一律打印「|x|>0.0」，看起来像阈值是 0。
    # 两个键都读，并把阈值**来源**与实测取值一起写进裁定，引用 blown 数字时必须一并引用。
    train_max = float(ic_raw.get("train_time_norm_absmax") or ic_blk.get("blowup_threshold") or 0) or None
    threshold_provenance = (
        "input_constraints.train_time_norm_absmax（B 线评测器写法）"
        if ic_raw.get("train_time_norm_absmax")
        else ("input_contract.blowup_threshold（A 线按 ckpt 现算，实测 %s）" % ic_blk.get("blowup_threshold")
              if ic_blk.get("blowup_threshold")
              else "unstated（产物未声明阈值来源 —— 跨族引用时 0.05 容差不是同一把尺子）"))
    # 监管 增补二 §3（rl_harness_supervision/supervisor_memo_20260928.md）：
    #   「任何闭环评测产物必须带 norm_input_blown_frames_frac；超阈判 INVALID。
    #     **缺字段同样判 INVALID**。」
    # 原实现只判「有字段且超阈」，于是缺字段的产物拿到 measurement_valid=true —— 
    # 等于「没测过输入契约」被记成「输入契约通过」，这正是 L1 能伪装成能力不足几天的原因。
    # 覆盖不全（只有部分局记录）等同未验证：无法主张整轮干净。
    n_with, n_tot = len(blow), len(rows)
    # 例外：**没有学习策略**的产物（scripted base-only）不存在归一化网络输入，
    # 输入契约对它不适用。若不加这一条，`runs/infra/b_env_rebuild/base_truth20.json`
    # （rise_cap=0.15 的标定基准、20/20 受控成功）会被判 INVALID —— 门禁把自己的
    # 标定基准作废了。判据从严：必须**同时**没有任何策略引用字段才算非学习产物。
    learned = bool(d.get("ckpt") or d.get("checkpoint") or d.get("policy_config"))
    mean_blown = (round(float(np.mean(blow)), 4) if blow else None)
    # v1.3（裁定 2）：先做 not_applicable 声明校验，再定 ic_status。
    na_check = not_applicable_check(d, rows, n_with, learned)
    if n_with == 0 and not learned:
        ic_status = "not_applicable"
    elif n_with == 0 and na_check["status"] == "verified_in_range":
        ic_status = "not_applicable_verified"
    elif n_with == 0 and na_check["declared"]:
        ic_status = "not_applicable_unverified"
    elif n_with == 0:
        ic_status = "unverified"
    elif n_with < n_tot:
        ic_status = "partial"
    elif mean_blown > INPUT_BLOWUP_TOL:
        ic_status = "violated"
    else:
        ic_status = "verified_ok"
    # 用 if/elif 而不是字典字面量：字典的**所有** value 都会被立即求值，
    # 未验证时 blow 为空，`np.mean([])` 会抛 "Mean of empty slice" 并得到 nan。
    # ---- v1.3（监管 §12 分派）：blown 实现指纹；缺指纹的新产物直接拒判 ----
    impl_chk = blown_impl_check(path, d, n_with)
    if impl_chk["reject"]:
        ic_status = IMPL_REJECT_STATUS
    # ---- v1.3（裁定 3）：争议带内的探针豁免（证据必须存在且 sha256 对得上）----
    exo = (probe_exoneration_check(path, mean_blown, impl_chk["status"], artifact=d)
           if mean_blown is not None else None)
    # v1.5（DR-008 决定 5）：晋级闸**按 probe_kind 分路**。原实现只认
    # verified_ok / not_applicable_verified，于是 裁定 10 的目标臂（ic_status=violated）
    # 即使豁免受理也升不上去、measurement_valid 仍 False —— 这是 D 实测的第三处阻塞
    # （promotion_possible_without_code_change=false）。分路而不是放宽：
    # 带内重测通道的可晋级来源逐字不变，只有 clip_at_train_absmax 能从 violated 晋级。
    if exo and exo["status"] == "exonerated":
        allowed = EXONERATION_PROMOTION_SOURCES.get(exo.get("probe_kind"),
                                                    DEFAULT_PROMOTION_SOURCES)
        if ic_status in allowed:
            ic_status = "probe_exonerated"
    elif exo and exo["status"] in EXONERATION_EVIDENCE_FAILURES:
        ic_status = "probe_exoneration_invalid"
    # out_of_band_refused **不改** ic_status（§12：带外 INVALID 维持），只把拒绝理由记进裁定。
    # v1.5 同理：clip 通道的四种拒绝（scope / clip_C / 五条准入 / 会签）也**不改** ic_status，
    # 只把拒绝理由记进裁定 —— 拒绝豁免不等于「测量有效」，维持原判才是保守方向。
    # 但证据侧的两种失效（探针文件不存在 / sha 不匹配）沿用既有口径判
    # probe_exoneration_invalid：登记了假证据比没登记更糟。

    if ic_status == "violated":
        ic_note = ("闭环有 %.0f%% 的帧收到超出训练分布的归一化输入（|x|>%.1f）——"
                   "本产物测的是数值事故不是策略能力，gate 判 measurement_invalid，"
                   "不得用于任何能力主张。根因见 docs/b_normalization_incident_20260928.md"
                   % (100 * float(np.mean(blow)), train_max or 0))
    elif ic_status == IMPL_REJECT_STATUS:
        ic_note = impl_chk["note"]
    elif ic_status == "unverified":
        ic_note = na_check["note"] or (
            "产物**未记录** norm_input_blown_frames_frac（0/%d 局）——输入契约未验证。"
            "按监管 增补二 §3 同样判 measurement_invalid：评测器需加 --record-input-blowup "
            "并重跑；在补齐前本产物成功率只能标「L1 暴露、候选」，不得作为率证据。" % n_tot)
    elif ic_status == "partial":
        ic_note = ("只有 %d/%d 局记录了 norm_input_blown_frames_frac——覆盖不全等同未验证，"
                   "无法主张整轮输入干净。请重跑缺失的局。" % (n_with, n_tot))
    elif ic_status == "not_applicable":
        ic_note = ("本产物没有学习策略（controller=%s，且无 ckpt/checkpoint/policy_config）"
                   "——不存在归一化网络输入，输入契约不适用，不按缺字段判 INVALID。"
                   % d.get("controller"))
    elif ic_status in ("not_applicable_verified", "not_applicable_unverified"):
        ic_note = na_check["note"]
    elif ic_status == "probe_exonerated":
        ic_note = exo["note"]
    elif ic_status == "probe_exoneration_invalid":
        ic_note = exo["note"]
    elif ic_status == "verified_ok" and exo and exo["status"] == "out_of_band_refused":
        ic_note = exo["note"]
    else:
        ic_note = ""
    input_contract = {
        "measured": bool(blow),
        "status": ic_status,
        "rows_with_field": n_with, "rows_total": n_tot,
        "train_time_norm_absmax": train_max,
        "threshold_provenance": threshold_provenance,
        "artifact_gate_tolerance": ic_blk.get("gate_tolerance"),
        "gate_tolerance_matches": (None if ic_blk.get("gate_tolerance") is None
                                   else abs(float(ic_blk.get("gate_tolerance")) - INPUT_BLOWUP_TOL) < 1e-9),
        "closed_loop_norm_absmax": (round(max(absmax), 1) if absmax else None),
        "mean_blown_frames_frac": mean_blown,
        "blown_metric_impl": impl_chk["impl"],
        "blown_metric_impl_status": impl_chk["status"],
        "in_disputed_band": (None if mean_blown is None
                             else bool(DISPUTED_BLOWN_BAND[0] <= mean_blown <= DISPUTED_BLOWN_BAND[1])),
        "violated": ic_status == "violated",
        "unverified": ic_status in ("unverified", "partial", "not_applicable_unverified"),
        "not_applicable": ic_status in ("not_applicable", "not_applicable_verified"),
        "probe_exonerated": ic_status == "probe_exonerated",
        "learned_policy": learned,
        "tolerance": INPUT_BLOWUP_TOL,
        "note": ic_note,
    }
    # ---- v1.3：measurement_valid 的单一判定点 + 全部失效理由（不再只报第一个）----
    ic_ok = ic_status in IC_VALID_STATUSES
    invalid_reasons = []
    if n_phase_mismatch:
        invalid_reasons.append("phase_vocab_mismatch: %d/%d 局 phase_at_end 与 phase_trace 词表矛盾"
                               "（裁定 1；这些局已移出分母，不再静默判 flick）" % (n_phase_mismatch, len(rows)))
    if ic_status == IMPL_REJECT_STATUS:
        invalid_reasons.append("blown_impl_missing: 新产物缺 blown_metric_impl 指纹（监管 §12 分派）")
    if ic_status == "violated":
        invalid_reasons.append("input_contract_violated: 闭环归一化输入超训练分布 %.4f > %.2f"
                               % (mean_blown or 0.0, INPUT_BLOWUP_TOL))
    if ic_status in ("unverified", "partial"):
        invalid_reasons.append("input_contract_unverified: %d/%d 局有 blown 字段" % (n_with, n_tot))
    if ic_status == "not_applicable_unverified":
        invalid_reasons.append("not_applicable_unevidenced: %s（裁定 2：声明不等于豁免）" % na_check["status"])
    if na_check["status"] == "violated_out_of_range":
        invalid_reasons.append("raw_obs_out_of_range: 闭环 raw obs 越界局占比 %.2f > %.2f（裁定 2）"
                               % (na_check["oob_frac"] or 0.0, INPUT_BLOWUP_TOL))
    if ic_status == "probe_exoneration_invalid":
        invalid_reasons.append("probe_exoneration_invalid: %s（裁定 3 的证据校验未过）"
                               % (exo or {}).get("status"))
    if not labels_reportable:
        invalid_reasons.append(
            "evidence_missing: field_class=%s，标签关键字段缺 %s（全部缺失字段 %s）；"
            "裁定 14 已把 %d 局失效模式标签改判 unjudged_evidence_missing"
            % (field_class, ",".join(missing_label_critical), ",".join(missing) or "-",
               n_labels_abstained))
    # v1.4：measurement_valid 增加 labels_reportable 一项。注意它**不**等价于
    # `field_class == "strict"` —— 只缺 terminal_kind 的产物（base-only 标定件）标签仍可报，
    # 不因本条作废（理由见 LABEL_CRITICAL_FIELDS 注释与 DR-007）。
    measurement_valid = bool(ic_ok and not n_phase_mismatch and labels_reportable)
    insuff_diag = insuff_diagnostic(judged, args.final_rise)
    n_prov = cnt(judged, "provisional_pass")
    return {
        "file": str(path), "controller": d.get("controller"), "gate_version": GATE_VERSION,
        "gate_build": GATE_BUILD, "gate_spec_sha256": GATE_SPEC_SHA,
        "gate_spec_doc": GATE_SPEC_DOC,
        "episodes_total": len(rows), "n_unjudged": len(unjudged),
        "unjudged_seeds": [b["seed"] for b in unjudged],
        "field_class": field_class, "missing_fields": missing, "field_presence": have,
        # v1.4（裁定 14）：标签可报性与弃权计数。字段名与 A 的
        # scripts/summarize_lerobot_act_arms.py（schema_version=2）的 labels_reportable 对齐，
        # 便于两条线在汇总层用同一个概念。
        "labels_reportable": bool(labels_reportable),
        "missing_label_critical": missing_label_critical,
        "n_labels_abstained": n_labels_abstained,
        "label_scope_note": label_scope_note,
        "phase_field_kinds": sorted(str(k) for k in kinds if k is not None),
        "unjudged_reasons": unj_reason,
        "n_phase_vocab_mismatch": n_phase_mismatch,
        "phase_mismatch_seeds": [b["seed"] for b in unjudged
                                 if (b.get("evidence") or {}).get("unjudged_reason") == "phase_vocab_mismatch"],
        "phase_vocab_notes": sorted({(b.get("evidence") or {}).get("phase_vocab_note")
                                     for b in unjudged
                                     if (b.get("evidence") or {}).get("phase_vocab_note")}),
        "composite_policy": bool(active_constraints),
        "execution_constraints": ec, "active_constraints": active_constraints,
        "input_constraints": ic_raw, "constraint_sides": constraint_sides,
        "terminal_semantics": terminal_semantics,
        "raw_success": sum(1 for r in rows if bool(_g(r, "success_raw", "success", "raw_success", default=False))),
        "n_provisional_pass": n_prov, "n_over_lift": cnt(judged, "over_lift"),
        "over_lift_seeds": [b["seed"] for b in judged if b["verdict"] == "over_lift"],
        "provisional_seeds": [b["seed"] for b in judged if b["verdict"] == "provisional_pass"],
        "accounts": {
            "policy_independent": {"denominator": len(indep), "controlled_success": cnt(indep, "controlled_success"),
                                   "provisional_pass": cnt(indep, "provisional_pass"),
                                   "over_lift": cnt(indep, "over_lift"), "flick": cnt(indep, "flick"),
                                   "insufficient_lift": cnt(indep, "insufficient_lift")},
            "system_assisted": {"denominator": len(judged), "controlled_success": cnt(judged, "controlled_success"),
                                "provisional_pass": cnt(judged, "provisional_pass"),
                                "over_lift": cnt(judged, "over_lift"), "flick": cnt(judged, "flick"),
                                "insufficient_lift": cnt(judged, "insufficient_lift")},
            "autonomous_learning": {"denominator": (len(judged) if args.assist_off else 0),
                                    "controlled_success": (cnt(judged, "controlled_success") if args.assist_off else None),
                                    "note": ("input marked --assist-off" if args.assist_off
                                             else "需另跑关闭动作辅助的评测并用 --assist-off 标记")},
        },
        # 这个键名是历史遗留：它算的其实是「raw 成功里**不受控**的比例」（含 over_lift，
        # v1.2 起也含 insufficient_lift），不是纯弹射比例。CLI 表头因此写 unctrl%。
        # 纯弹射比例用 flick_frac_strict。
        "flick_frac_of_raw_success": ((cnt(judged, "flick") + cnt(judged, "over_lift")
                                       + cnt(judged, "insufficient_lift")) / max(1,
                                       cnt(judged, "flick") + cnt(judged, "over_lift")
                                       + cnt(judged, "insufficient_lift")
                                       + cnt(judged, "controlled_success") + cnt(judged, "provisional_pass"))),
        "flick_frac_strict": (cnt(judged, "flick") / max(1, cnt(judged, "flick")
                               + cnt(judged, "over_lift") + cnt(judged, "insufficient_lift")
                               + cnt(judged, "controlled_success") + cnt(judged, "provisional_pass"))),
        "input_contract": input_contract,
        # v1.3 新增裁定字段（裁定 1/2/3 + §12 分派 + B-3 诊断）
        "not_applicable_declaration": na_check,
        "blown_metric": impl_chk,
        "probe_exoneration": exo,
        "insuff_diagnostic": insuff_diag,
        "measurement_valid": measurement_valid,
        "measurement_invalid_reasons": invalid_reasons,
        "gate_pass": bool(cnt(indep, "controlled_success") > 0 and measurement_valid),
        # v1.4 更正一条 v1.1 的设计注释：原文写「field_blind 不算 measurement_invalid，
        # CLI 会显示 FAIL 而不是 INVALID，所以它单独一支」。该分支已被裁定 14 推翻 ——
        # 关键字段缺失是「没测到」，不是「策略失败」，判 FAIL 会把测量缺口说成能力结论。
        # 现在 blind 也走 invalid_reasons，屏幕显示与文案一致，不再需要单独一支。
        "gate_reason": (("measurement_invalid: " + "; ".join(invalid_reasons)) if invalid_reasons
                        else ("pass" if cnt(indep, "controlled_success") > 0
                              else "no_controlled_success")),
        "git_commit": GIT_COMMIT, "git_dirty_files": GIT_DIRTY_FILES,
        "per_episode": per,
    }


def main():
    ap = argparse.ArgumentParser(description="受控成功判据 v1 门禁（只读后处理）")
    ap.add_argument("paths", nargs="+", help="audit_truth*.json / result.json")
    ap.add_argument("--rise-cap", type=float, default=RISE_CAP)
    ap.add_argument("--final-rise", type=float, default=FINAL_RISE_MIN)
    ap.add_argument("--hold-phases", default=None,
                    help="已废弃：v1.1 起 per-frame 只认 hold，controller_log 只认 hold/done（见 HOLD_PHASES_*）")
    ap.add_argument("--no-strict-final-rise", action="store_true",
                    help="缺 final_rise 字段时不因此判失败（默认：有字段就必须过）")
    ap.add_argument("--assist-off", action="store_true",
                    help="声明该输入是关闭动作辅助后跑的，用于填 autonomous_learning 账")
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    out = [judge_file(p, a) for p in a.paths]
    if not a.quiet:
        h = "%-40s %5s %5s %6s %6s %6s %6s %7s %8s %s"
        print(h % ("input", "eps", "unjd", "raw", "ctrl", "flick", "ovlift", "inslift", "unctrl%", "gate"))
        for r in out:
            if "error" in r:
                print("%-40s ERROR %s" % (Path(r["file"]).name[:40], r["error"])); continue
            pi, sa = r["accounts"]["policy_independent"], r["accounts"]["system_assisted"]
            print(h % (Path(r["file"]).parent.name[:40], r["episodes_total"], r["n_unjudged"],
                       r["raw_success"], f"{pi['controlled_success']}/{pi['denominator']}",
                       f"{sa['flick']}", f"{sa['over_lift']}", f"{sa['insufficient_lift']}",
                       f"{r['flick_frac_of_raw_success']*100:.0f}%",
                       ("PASS" if r["gate_pass"] else
                        ("INVALID" if not r["measurement_valid"] else "FAIL"))))
            flags = []
            if r["field_class"] != "strict":
                flags.append("字段等级=%s，缺 %s" % (r["field_class"], ",".join(r["missing_fields"]) or "-"))
            if r.get("n_labels_abstained"):
                flags.append("裁定14：%d 局失效模式标签已弃权（原标签见 evidence.label_before_abstain）"
                             % r["n_labels_abstained"])
            if r["n_provisional_pass"]:
                flags.append("%d 局 provisional_pass（C1-C4 过但局末夹持无字段可证，**不得**计入 P1 主张）"
                             % r["n_provisional_pass"])
            if not r["measurement_valid"]:
                ic = r["input_contract"]
                # v1.3：失效理由可能同时有多条（phase 词表矛盾 + 输入契约未验证 + 缺指纹），
                # 逐条打印。旧实现只报一条，会掩盖第二条 —— 修好一条以为过关。
                for why in (r["measurement_invalid_reasons"]
                            or ["input_contract.status=%s" % ic["status"]]):
                    flags.append("**测量无效** %s" % why)
                if ic["status"] == "violated":
                    flags.append("闭环归一化 |x|max=%s（训练上界 %s，来源 %s），平均 %.0f%% 的帧超出训练分布"
                                 " —— 本产物不得用于任何能力主张"
                                 % (ic["closed_loop_norm_absmax"], ic["train_time_norm_absmax"],
                                    ic["threshold_provenance"], 100 * (ic["mean_blown_frames_frac"] or 0)))
                else:
                    flags.append("输入契约 status=%s（%d/%d 局有字段）：%s"
                                 % (ic["status"], ic["rows_with_field"], ic["rows_total"], ic["note"]))
            bm, na, ex = r["blown_metric"], r["not_applicable_declaration"], r["probe_exoneration"]
            if bm["status"] == "unknown_impl":
                flags.append("blown_metric_impl=%s 不在已知清单 %s —— 口径可能又漂了，本裁定不得引用"
                             % (bm["impl"], bm["known_impls"]))
            elif bm["status"] == "missing_legacy_grandfathered":
                flags.append("存量产物豁免：缺 blown_metric_impl 指纹，但按 sha256 命中豁免册"
                             "（记录 %s，cutoff %s）—— 重测后必须换带指纹的新产物"
                             % (bm.get("grandfather_recorded"), bm.get("grandfather_cutoff")))
            if r["input_contract"]["in_disputed_band"]:
                flags.append("mean_blown_frames_frac=%s 落在 §12 争议带 [%.2f, %.2f] —— "
                             "引用前须确认豁免状态（当前 %s）"
                             % (r["input_contract"]["mean_blown_frames_frac"],
                                DISPUTED_BLOWN_BAND[0], DISPUTED_BLOWN_BAND[1],
                                (ex or {}).get("status", "无豁免登记")))
            if ex and ex["status"] == "out_of_band_refused":
                flags.append("探针豁免被拒：%s" % ex["note"])
            if na["status"] == "contradicted_by_blown_field":
                flags.append("not_applicable 声明与实测矛盾：%s" % na["note"])
            if r["input_contract"]["gate_tolerance_matches"] is False:
                flags.append("产物自带 gate_tolerance=%s 与门禁 INPUT_BLOWUP_TOL=%.2f 不一致 —— "
                             "以门禁为准，但须核对评测器版本"
                             % (r["input_contract"]["artifact_gate_tolerance"], INPUT_BLOWUP_TOL))
            if "unstated" in str(r["input_contract"]["threshold_provenance"]):
                flags.append("blowup 阈值来源未声明（ADR-A-005 #4）：%s"
                             % r["input_contract"]["threshold_provenance"])
            ins = r["insuff_diagnostic"]
            if ins.get("n"):
                flags.append("insufficient_lift %d 局：final_rise 中位 %.4f / p90 %.4f，"
                             "距 C5=%.3f 中位差 %.4f m，其中 %d 局（%.0f%%）在门槛下方 0.005 m 内"
                             % (ins["n"], ins["final_rise_median"], ins["final_rise_p90"],
                                ins["threshold"], ins["gap_median"], ins["n_within_0p005"],
                                100 * ins["frac_within_0p005"]))
            if r["composite_policy"]:
                flags.append("复合 policy：启用了 %s —— 裁定对象是 policy+约束，**不是底模**；"
                             "该臂的受控成功率不得当作 base policy 能力引用"
                             % ",".join("%s:%s" % (r["constraint_sides"].get(k, "?"), k)
                                        for k in r["active_constraints"]))
            if r["terminal_semantics"]["suspect_truncation_labeled_as_failure"]:
                flags.append("terminal_kind 语义可疑：%d 行跑满 horizon 却标 terminated_failure（实为截断）"
                             % r["terminal_semantics"]["rows_labeled_terminated_failure"])
            if len(r["phase_field_kinds"]) > 1:
                flags.append("phase_trace 语义混用：%s" % r["phase_field_kinds"])
            if r["n_phase_vocab_mismatch"]:
                flags.append("phase 词表矛盾 %d 局（裁定 1，已移出分母）：%s"
                             % (r["n_phase_vocab_mismatch"], "; ".join(r["phase_vocab_notes"]) or "-"))
            for f_ in flags:
                print("    [warn] %s" % f_)
            for e in r["per_episode"]:
                if e["verdict"] in ("controlled_success", "flick", "provisional_pass", "over_lift",
                                    "insufficient_lift"):
                    print("      %-17s seed=%-6s max_rise=%.3f final_rise=%s end=%-9s %s"
                          % (e["verdict"], e["seed"], e["max_rise"], e["final_rise"], e["end_phase"],
                             (("failed: " + ",".join(e["failed_checks"])) if e["failed_checks"] else
                              e["evidence"]["c4_basis"])))
        print("\n口径 %s：受控成功 = success_raw ∧ grasp_verified ∧ max_rise≤%.2f ∧ 局末仍夹持%s；"
              "unknown/preempted 移出分母。\n"
              "  「局末仍夹持」按 phase 字段语义取证据：controller_log→到达 hold/done；"
              "per-frame→held_at_end=True 或 final_rise≥%.2f，且 end_phase∈{hold,grasp}；"
              "两者都缺时 end_phase 只认 hold，否则降为 provisional_pass（不计入主张）。"
              % (GATE_VERSION, a.rise_cap,
                 "" if a.no_strict_final_rise else f" ∧ final_rise≥{a.final_rise}", a.final_rise))
        print("门禁构建：gate_version=%s gate_build=%s spec_sha256=%s（%s）"
              % (GATE_VERSION, GATE_BUILD, GATE_SPEC_SHA, GATE_SPEC_DOC))
        print("  留档裁定里的 gate_build 若与此不同，说明它出自旧构建，**必须重判**才能与新结果比较。")
        print("代码版本：git_commit=%s（工作区未提交改动 %s 个文件）"
              % (GIT_COMMIT or "非 git 环境", GIT_DIRTY_FILES if GIT_DIRTY_FILES is not None else "?"))
        print("  DR-002/DR-003 之后 git_commit 与 gate_build 一起构成裁定的代码版本；"
              "gate_build 只覆盖门禁脚本自己，覆盖不了产出被裁定产物的评测器。")
    if a.json_out:
        Path(a.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json_out).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
        print("写出:", a.json_out)
    return 0 if all(r.get("gate_pass") for r in out if "error" not in r) else 1


if __name__ == "__main__":
    sys.exit(main())
