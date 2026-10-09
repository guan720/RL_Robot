#!/usr/bin/env python3
"""A 线：**分布层**引用闸（裁定 30 / DR-D29 的代码承载）—— 全程只读。

为什么需要它
------------
裁定 30 立的一般规则是：**「计数层」与「按有效臂统计的分布层」对构建的敏感性不同。**

  - 计数层（逐局 verdict 计数）= **构建不变**：v1.4→v1.5 实测 135/235/7/0/0/377 一格未动（裁定 28 ③）。
  - 分布层（直方图 / 区间计数 / 极差 / 族均值的 n）= **构建相关**：它按 `measurement_valid` 的
    **臂集**统计，而臂集会被免罪 / 降级改变（实测无效臂 v1.2.1 = 7 → v1.5 = 1）。

A 的双峰预登记 `docs/a_bimodal_divergence_preregistration_20260928.md:17` 写的
「两族合并 21 个有 actlog 的臂里，受控成功落在 4–9 的臂数 = 0（中间是空的）」是一句**分布层**陈述，
写它的那一刻（09-28 21:15，v1.2.1 口径）成立 —— 那时 `k2 seed0` 是 `NOT_CITABLE_measurement_invalid`、
不在有效臂分布里。裁定 10 免罪在 v1.5 落地后它 `measurement_valid=True`、**重回分布**，计数 0→1，
而这一步**没有任何一线传播**（裁定 30 §20.2）。⇒ 该句在现口径下**为假**，必须禁用并挂更正指针。

判据只写在裁定散文里等于没有判据（本仓已四次同型事故：DR-003 判据 3 恒真、D「裁定无代码承载」、
A 的 L5/G2 恒假、B 的牙齿脚本误报）。本脚本把 裁定 30 的六条变成**可执行断言**，
CLOSED 时 exit 1。**A 不自免**：D6 扫的就是 A 自己的文档。

模式
----
  默认            读 A 表 / B 表 / v1.2.1 历史表 / actlog 名单 / live 门禁，跑 D1–D10。
  --selftest      变异自检，证明这道闸**有牙**（真实现场必须 OPEN、每个变异必须被对应判据抓住）。
                  fixture 全在内存里，**不写任何文件**。

判据非恒真（裁定 30.6 的双向自检）：可红条件 = 「21 臂 join 权威表后 4–9 计数 == 0」。
现场实测 == 1 ⇒ D2 绿；若该臂被重测（`scope=artifact` ⇒ 免罪随 sha256 失效）且新值落到 ≤3 或 ≥14，
D2 会因为「孤立臂消失」而要求改写定性 ⇒ 不是恒真，也不是恒假（见 M2 / M3 两个方向的变异）。

D8 的历史 meta 项（裁定 35.2 / DR-D34，memo 增补十二 §41）
----------------------------------------------------------
A 曾在 `docs/a_handoff_to_d_20260929.md:49-51` 写「若有人真去刷了基线 meta，**D8 立即变红**」，
而当时的判据体对 `h_doc` 只读了三样东西（可读性 / `n_artifacts` / 臂行），**meta 三值一次都没读过**
⇒ 只刷 meta、不动行数据时 D8 七个 term 全为真，那句话是**过度声称**（裁定 27.1：覆盖不到目标场景的闸
= 恒真闸 = 没有闸）。现补 term `historical_meta_is_v121`，**逐值比**两处操作数：
① v1.2.1 历史表（三值在**顶层且是字符串**）；② `attribution/arms_summary_v3.json`
（三值在 **`meta` 下且是单元素列表**，= 裁定 35.2 可红条件点名的那份基线）。
并用 S13（两处一起刷）/ S14（只刷 ②，即 A 当初点名的那处）/ S15（只刷 ①）演示它**真的会红**。
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

A_TABLE = "runs/infra/lerobot_act_env_20260928/arms_summary.json"
B_TABLE = "runs/infra/b_official_arms/reclassification.json"
B_TABLE_V121 = "runs/infra/b_official_arms/reclassification.build_e4f5ec887788.json"
ACTLOG_DIAG = "runs/infra/lerobot_act_env_20260928/closed_loop_dz_diag_A.json"
B_GATE = "scripts/b_gate_controlled_success.py"

# v1.2.1 基线的三值（裁定 35.2 / DR-D34）。**独立写死一份**，不与 summarizer / 迁移闸共用常量 ——
# 生产者与被检者同源会让「改一处两边一起绿」= 恒真（本文件 FORBIDDEN 那条注释立的同一规矩）。
# 两处操作数：① v1.2.1 历史表（顶层字符串）② 归属基线汇总表（meta 下单元素列表）。
V121_BASELINE = "runs/infra/lerobot_act_env_20260928/attribution/arms_summary_v3.json"
META3_KEYS = ("gate_version", "gate_build", "gate_spec_sha256")
V121_META3 = ("v1.2.1", "e4f5ec887788", "494d5f5babf9")
# S13/S14/S15 用的「被刷新后」三值 = 裁定 35.2 可红条件里那个 v1.5 口径
V15_META3 = ("v1.5", "f19f61341cbe", "c7fadabe8e3c")

# 裁定 10 / 裁定 28 的免罪臂本尊（裁定 30 §20.1：落在 4–9 的那一臂就是它）
TARGET_ARM = "trimdone0_minmax_k2_lr1e-5_s20k_seed0"
TARGET_KIND = "clip_at_train_absmax"

# 裁定 30.1 的定性（21 actlog 臂集，20k 快照，v1.5 / f19f61341cbe）
EXPECT_21 = {"low_0_3": 15, "empty_band_4_8": 0, "empty_band_10_13": 0,
             "high_14_20": 5, "forbidden_window_4_9": 1, "middle": 1}
# 裁定 30 §20.1 的 48 臂全集：4–9 区间 3 臂
EXPECT_48_IN_4_9 = 3

# 裁定 30.2 的**禁用写法**（与 summarizer 的 FORBIDDEN_DISTRIBUTION_PHRASINGS 同源，此处独立写死一份，
# 免得「生产者与被检者共用一个常量」导致改一处两边一起绿 = 恒真）
FORBIDDEN = ("受控成功落在 4–9 的臂数 = 0", "4–9 的臂数 = 0", "4–9 臂数 = 0",
             "中间是空的", "严格双峰、中间全空")
# 更正指针的可接受标记：出现禁用串的行，必须在 ±POINTER_WINDOW 行内带其中之一
POINTER_WINDOW = 8
POINTER_MARKERS = ("裁定 30", "裁定30", "DR-D29", "强间隙分离", "gap-separated", "gap_separated",
                   "更正指针", "已被证伪", "被证伪", "禁用", "4–8 与 10–13", "增补七 §20", "§20")
# 计数层（裁定 30.4：构建不变的那一层）
COUNT_KEYS = ("controlled_success", "insufficient_lift", "flick", "over_lift",
              "provisional_pass", "raw_success")
# A ↔ B 两表的计数层字段映射（**字段名不同、语义相同**，见 D4 的注释）
CROSS_TABLE_COUNT_FIELDS = (("controlled_success", "controlled_success"),
                            ("success_raw", "raw_success"),
                            ("episodes", "episodes"))
# D9：引历史口径必须同时报 n_artifacts（裁定 30.5）
V121_COUNT_SIGNATURE = re.compile(r"132\s*/\s*208\s*/\s*23|132.*208.*23.*364")
# A 线自己的文档（D6 / D9 的扫描范围）。daily_report.md 是四线共写，也扫，
# 但按 POINTER_MARKERS 放行「引用禁用串来说明它被禁用」的场合。
A_DOC_GLOBS = ("docs/a_*.md", "daily_report.md")


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


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _rows(doc) -> dict:
    if not isinstance(doc, dict):
        return {}
    out = {}
    for r in doc.get("arms") or []:
        if isinstance(r, dict) and r.get("arm"):
            out[r["arm"]] = r
    return out


def _meta3(doc):
    """读 `META3_KEYS` 三值。历史表把它们放在**顶层且是字符串**，归属基线汇总表放在 **`meta` 下且是
    单元素列表** ⇒ 两种形态都要能读；键缺失 / 形态不符（如空列表、多元素列表）一律算**不符**，
    不得退化成「非空即过」（裁定 35.2 要求逐值比）。"""
    if not isinstance(doc, dict):
        return (None, None, None)
    meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
    out = []
    for k in META3_KEYS:
        if k in meta:
            v = meta[k]
            if isinstance(v, list):
                v = v[0] if len(v) == 1 else tuple(v)
        else:
            v = doc.get(k)
        out.append(v)
    return tuple(out)


def _intervals(vals: list[int]) -> dict:
    def _in(a: int, b: int) -> int:
        return sum(1 for v in vals if a <= v <= b)
    return {"low_0_3": _in(0, 3), "empty_band_4_8": _in(4, 8), "empty_band_10_13": _in(10, 13),
            "high_14_20": _in(14, 20), "forbidden_window_4_9": _in(4, 9)}


def load_state(args) -> dict:
    a_path = ROOT / args.a_table
    b_path = ROOT / args.b_table
    h_path = ROOT / args.historical_table
    dz_path = ROOT / args.actlog_diag
    gate_path = ROOT / args.b_gate
    v121_path = ROOT / getattr(args, "v121_baseline", V121_BASELINE)
    a_doc = _load(a_path)
    b_doc = _load(b_path)
    h_doc = _load(h_path)
    dz = _load(dz_path)
    v121_doc = _load(v121_path)
    actlog: list[str] = []
    if isinstance(dz, dict) and isinstance(dz.get("arms"), list):
        actlog = [x if isinstance(x, str) else str(x.get("arm") or x.get("name"))
                  for x in dz["arms"]]
    live_build = None
    if gate_path.is_file():
        live_build = hashlib.sha256(gate_path.read_bytes()).hexdigest()[:12]
    docs: dict[str, list[str]] = {}
    for glob in A_DOC_GLOBS:
        for p in sorted(ROOT.glob(glob)):
            try:
                docs[str(p.relative_to(ROOT))] = p.read_text(encoding="utf-8").splitlines()
            except OSError:
                pass
    return {"a_doc": a_doc, "b_doc": b_doc, "h_doc": h_doc, "actlog": actlog,
            "live_build": live_build, "docs": docs, "v121_doc": v121_doc,
            "paths": {"a": str(a_path), "b": str(b_path), "historical": str(h_path),
                      "actlog": str(dz_path), "gate": str(gate_path),
                      "v121_baseline": str(v121_path)}}


def _dist(st: dict) -> dict:
    return ((st.get("a_doc") or {}).get("meta") or {}).get("distribution_layer") or {}


def _set(dist: dict, label: str) -> dict:
    return ((dist.get("arm_sets") or {}).get(label)) or {}


def _join21(st: dict) -> tuple[list[dict], list[str]]:
    a_rows = _rows(st.get("a_doc"))
    sub = [a_rows[n] for n in st["actlog"] if n in a_rows]
    missing = [n for n in st["actlog"] if n not in a_rows]
    return sub, missing


def run_checks(st: dict) -> Checks:
    ck = Checks()
    a_doc = st.get("a_doc") or {}
    b_doc = st.get("b_doc") or {}
    h_doc = st.get("h_doc") or {}
    a_meta = a_doc.get("meta") or {}
    dist = _dist(st)

    # ---- D1：分布层块存在，且引用锚只在 build 轴（裁定 30.4 + 裁定 29.1）----
    bf = dist.get("build_fingerprint") or {}
    spec_axis = str(bf.get("spec_axis", ""))
    d1_terms = {
        "distribution_layer_present": bool(dist),
        "gate_build_nonempty": bool(bf.get("gate_build")),
        "gate_version_nonempty": bool(bf.get("gate_version")),
        # 裁定 29.1 的正向要求：spec 轴必须**自称**只作观测，且**不得**出现任何 12 位十六进制指纹
        # （出现指纹 = 有人把 spec 值钉成生效条件，A 自己踩过：a_migration_gate_preflight 曾硬编码
        #  过期的 132fceb89f68。写成「不含 spec 字样」是错的判据 —— 换个措辞就绕过去了）。
        "spec_axis_self_declares_observation_only": "observation_only" in spec_axis,
        "spec_axis_carries_no_fingerprint": not re.search(r"\b[0-9a-f]{12}\b", spec_axis),
        "counting_layer_marked_invariant": (dist.get("counting_layer") or {}).get("build_invariant") is True,
        "distribution_layer_marked_dependent": (dist.get("distribution_layer") or {}).get("build_dependent") is True,
    }
    ck.add("D1", "A 表 meta 带 distribution_layer + 构建指纹（spec 只作观测）",
           all(d1_terms.values()), d1_terms,
           {"全部为真": list(d1_terms)},
           note="裁定 30.4「分布类陈述一律带构建指纹」的代码承载；spec 轴按 裁定 29.1 只回显 "
                "`observation_only`，**不得**当生效条件（A 自己踩过这颗地雷，已拔）。")

    # ---- D2：21 臂集 4–9 计数 == 1（**不是 0**），且那一臂就是免罪臂本尊 ----
    a_set = _set(dist, "actlog_subset")
    sub, missing = _join21(st)
    vals = sorted(int(r["controlled_success"]) for r in sub
                  if isinstance(r.get("controlled_success"), int))
    iv = _intervals(vals)
    middle = [r for r in sub if isinstance(r.get("controlled_success"), int)
              and 3 < r["controlled_success"] < 14]
    mid_info = [{"arm": r["arm"], "controlled_success": r["controlled_success"],
                 "validity_class": r.get("validity_class"), "probe_kind": r.get("probe_kind")}
                for r in middle]
    d2_terms = {
        "join_complete": not missing,
        "n_arms_21": len(sub) == len(st["actlog"]) == 21,
        "in_4_9_is_1_not_0": iv["forbidden_window_4_9"] == EXPECT_21["forbidden_window_4_9"],
        # 产物**回显**的区间计数必须等于 A 现场重算值：只核重算值会放过「表里写着 0、真值是 1」
        # 这种把禁用写法当事实写进产物的形态（自检 S3 抓出来的缺口，09-29 补牙）。
        "reported_equals_recomputed": ((a_set.get("intervals") or {}).get("forbidden_window_4_9")
                                       == iv["forbidden_window_4_9"]),
        "isolated_arm_is_target": [m["arm"] for m in mid_info] == [TARGET_ARM],
        "isolated_arm_is_probe_exonerated": all(
            m["validity_class"] == "VALID_probe_exonerated" for m in mid_info),
        "isolated_arm_kind_is_clip": all(m["probe_kind"] == TARGET_KIND for m in mid_info),
    }
    ck.add("D2", "「4–9 臂数 = 0」已为假：实测 1 臂，且是 裁定 10 的免罪臂本尊",
           all(d2_terms.values()),
           {"terms": d2_terms, "intervals": iv, "middle_band_arms": mid_info,
            "missing_arms": missing[:8]},
           {"in_4_9": EXPECT_21["forbidden_window_4_9"], "isolated_arm": TARGET_ARM,
            "validity_class": "VALID_probe_exonerated", "probe_kind": TARGET_KIND},
           note="裁定 30 §20.1 的**事实层**。A 独立复算，不采信 D 的转述（本仓纪律）。"
                "这一条就是 裁定 30.6 的可红条件：若该臂重测后落到 ≤3 或 ≥14，本条会红，"
                "届时定性要按新数据改写 —— 所以它非恒真亦非恒假。")

    # ---- D3：强间隙分离定性成立（裁定 30.1）----
    rep_iv = (a_set or {}).get("intervals") or {}
    d3_terms = {
        "low_0_3": rep_iv.get("low_0_3") == EXPECT_21["low_0_3"] == iv["low_0_3"],
        "high_14_20": rep_iv.get("high_14_20") == EXPECT_21["high_14_20"] == iv["high_14_20"],
        "empty_band_4_8": rep_iv.get("empty_band_4_8") == 0 == iv["empty_band_4_8"],
        "empty_band_10_13": rep_iv.get("empty_band_10_13") == 0 == iv["empty_band_10_13"],
        "characterization_gap_separated": (a_set or {}).get("characterization") == "gap_separated",
        "reported_matches_recomputed": rep_iv.get("forbidden_window_4_9") == iv["forbidden_window_4_9"],
    }
    ck.add("D3", "定性 = 强间隙分离（空带 4–8 与 10–13），不是「严格双峰、中间全空」",
           all(d3_terms.values()),
           {"terms": d3_terms, "reported_intervals": rep_iv, "recomputed_intervals": iv},
           {"low_0_3": EXPECT_21["low_0_3"], "high_14_20": EXPECT_21["high_14_20"],
            "empty_bands": ["4-8", "10-13"], "characterization": "gap_separated"},
           note="裁定 30.1：双峰结论**不倒**，但必须改述。表里回显的区间计数必须与 A 现场重算逐格相同，"
                "否则就是「文档声明已落地而产物没承载」（本仓同型事故第 4 次，裁定 29.3 立的规则）。")

    # ---- D4：A 表与 B 表在 21 臂上逐格相同 + 两表 build 一致 ----
    b_rows = _rows(b_doc)
    diff = []
    for r in sub:
        b = b_rows.get(r["arm"])
        if not isinstance(b, dict):
            diff.append({"arm": r["arm"], "problem": "B 表里没有这一臂"})
            continue
        # 两表的**字段名不同、语义相同**（A `success_raw` ↔ B `raw_success`）。
        # 必须显式映射：照字面比同名键会得到一片假红 —— 裁定 27 定过性「**恒假的闸等于没有闸**」，
        # A 的 L5/G2 就是这么栽的，不在这里重犯。缺字段（None）仍算红，不静默跳过。
        for a_key, b_key in CROSS_TABLE_COUNT_FIELDS:
            av, bv = r.get(a_key), b.get(b_key)
            if av is None or bv is None or av != bv:
                diff.append({"arm": r["arm"], "a_field": a_key, "b_field": b_key,
                             "a": av, "b": bv})
    a_build = (a_meta.get("gate_build") or [None])
    b_build = b_doc.get("gate_build")
    d4_terms = {
        "per_arm_counts_identical": not diff,
        "a_single_build": isinstance(a_build, list) and len(a_build) == 1,
        "a_build_equals_b_build": (a_build[0] if isinstance(a_build, list) and a_build else None) == b_build,
        "a_build_equals_live_gate": (a_build[0] if isinstance(a_build, list) and a_build else None)
                                    == st.get("live_build"),
    }
    ck.add("D4", "跨表交叉核验：21 臂计数 A == B，且 A/B/live 三处 build 同一",
           all(d4_terms.values()),
           {"terms": d4_terms, "diffs": diff[:12], "a_build": a_build, "b_build": b_build,
            "live_build": st.get("live_build")},
           {"diffs": [], "a_build": "== b_build == live sha256[:12]"},
           note="分布层是**按臂集**统计的，臂集来自 `measurement_valid`；两表若在一个臂上分叉，"
                "直方图就会分叉。本条把「比的是不是同一份事实」变成断言（裁定 18.2 的同源要求）。")

    # ---- D5：48 臂全集 4–9 == 3，且「全 48 臂」与「measurement_valid 47 臂」两个臂集结果相同 ----
    all_rows = list(_rows(a_doc).values())
    all_vals = [int(r["controlled_success"]) for r in all_rows
                if isinstance(r.get("controlled_success"), int)]
    valid_rows = [r for r in all_rows
                  if r.get("validity_class") in ("valid", "VALID_probe_exonerated")]
    valid_vals = [int(r["controlled_success"]) for r in valid_rows
                  if isinstance(r.get("controlled_success"), int)]
    in49_all = sorted(v for v in all_vals if 4 <= v <= 9)
    in49_valid = sorted(v for v in valid_vals if 4 <= v <= 9)
    arms49 = sorted(r["arm"] for r in all_rows
                    if isinstance(r.get("controlled_success"), int)
                    and 4 <= r["controlled_success"] <= 9)
    o_all = _set(dist, "official_all")
    o_val = _set(dist, "measurement_valid")
    d5_terms = {
        "n_arms_48": len(all_rows) == 48,
        "in_4_9_is_3": len(in49_all) == EXPECT_48_IN_4_9,
        "arm_set_48_equals_valid_47": in49_all == in49_valid,
        "reported_official_all_matches": ((o_all.get("intervals") or {}).get("forbidden_window_4_9")
                                          == len(in49_all)),
        "reported_valid_matches": ((o_val.get("intervals") or {}).get("forbidden_window_4_9")
                                   == len(in49_valid)),
    }
    ck.add("D5", "48 臂全集 4–9 == 3 臂；两套臂集（48 / valid 47）在该区间结果相同",
           all(d5_terms.values()),
           {"terms": d5_terms, "values_in_4_9": in49_all, "arms_in_4_9": arms49,
            "n_valid_arms": len(valid_rows)},
           {"in_4_9": EXPECT_48_IN_4_9,
            "why_same": "唯一 INVALID 臂受控成功 = 0，不落 4–9 ⇒ 换臂集不改这个区间"},
           note="B 表 `distribution_layer_note` 主张「全 48 与 valid 47 两套臂集结果相同」，"
                "A 在此**独立复算**而非采信。臂集不同结果就不同，这正是 裁定 30.4 要立的东西。")

    # ---- D6：禁用写法扫描（A 自己的文档，A 不自免）----
    hits, unpointered = [], []
    for name, lines in (st.get("docs") or {}).items():
        for i, line in enumerate(lines):
            for phrase in FORBIDDEN:
                if phrase not in line:
                    continue
                lo = max(0, i - POINTER_WINDOW)
                hi = min(len(lines), i + POINTER_WINDOW + 1)
                window = "\n".join(lines[lo:hi])
                rec = {"doc": name, "line": i + 1, "phrase": phrase,
                       "text": line.strip()[:160],
                       "pointer": any(m in window for m in POINTER_MARKERS)}
                hits.append(rec)
                if not rec["pointer"]:
                    unpointered.append(rec)
    ck.add("D6", "禁用写法扫描：出现「4–9 = 0 / 中间是空的」必须带更正指针",
           not unpointered,
           {"n_occurrences": len(hits), "n_without_pointer": len(unpointered),
            "without_pointer": unpointered[:12],
            "with_pointer": [f"{h['doc']}:{h['line']}" for h in hits if h["pointer"]][:12]},
           {"n_without_pointer": 0},
           note="裁定 30.2：**预登记原文不改**（append-only），只挂指向 裁定 30 / 增补七 §20 的更正指针。"
                "扫描范围 = A 线文档 + daily_report.md；D/B 的引用若在近邻窗口内自带裁定编号即放行"
                "（他们是在**说明该写法被禁用**，不是在主张某事实）。")

    # ---- D7：四限定齐备（裁定 30.3）----
    quals = dist.get("citation_requires_four_qualifiers") or []
    sets = dist.get("arm_sets") or {}
    per_set = {}
    for label, s in sets.items():
        per_set[label] = {
            "arm_set_label": bool(s.get("arm_set")),
            "arm_set_definition": bool(s.get("arm_set_definition")),
            "snapshot": bool(s.get("snapshot")),
            "middle_band_arms_key_present": "middle_band_arms" in s,
            "characterization": bool(s.get("characterization")),
        }
    d7_terms = {
        "four_qualifiers_listed": len(quals) == 4,
        "every_arm_set_has_qualifiers": all(all(v.values()) for v in per_set.values()) if per_set else False,
        "actlog_subset_present": "actlog_subset" in sets,
        "official_all_present": "official_all" in sets,
        "measurement_valid_present": "measurement_valid" in sets,
        "build_fingerprint_in_dist": bool((dist.get("build_fingerprint") or {}).get("gate_build")),
    }
    ck.add("D7", "引用双峰的四限定齐备（臂集 / 快照 / 构建 / 中间带孤立臂）",
           all(d7_terms.values()), {"terms": d7_terms, "per_arm_set": per_set,
                                    "n_qualifiers": len(quals)},
           {"four_qualifiers_listed": True, "arm_sets": ["official_all", "measurement_valid",
                                                         "actlog_subset"]},
           note="裁定 30.3：缺任一条即为**不可引用**。四个限定必须由产物回显，不能靠人记住。")

    # ---- D8：两层对构建的敏感性都有**实测**证据（裁定 30.4 + 30.5）----
    h_arms = list(_rows(h_doc).values())
    h_invalid = [r["arm"] for r in h_arms if r.get("citable") == "NOT_CITABLE_measurement_invalid"]
    h_counts = {k: sum(int(r.get(f"{k}_raw") or r.get(k) or 0) for r in h_arms)
                for k in ("controlled_success",)}
    b_sum = b_doc.get("summary") or {}
    a_totals = ((a_meta.get("totals") or {}).get("scope_all_48_products_supervisor_reconcile") or {})
    b_counts = {k: b_sum.get(k) for k in COUNT_KEYS if k in b_sum}
    a_counts = {k: a_totals.get(k) for k in COUNT_KEYS if k in a_totals}
    n_invalid_now = len(a_meta.get("invalid_arms") or [])
    # 裁定 35.2：v1.2.1 基线的三值必须在**两处操作数**上都停在旧值（刷成 v1.5 = 销毁迁移断言）
    h_meta3 = _meta3(h_doc)
    base_meta3 = _meta3(st.get("v121_doc"))
    d8_terms = {
        "historical_table_readable": bool(h_doc),
        "historical_n_artifacts_is_44": h_doc.get("n_artifacts") == 44,
        "historical_invalid_arms_7": len(h_invalid) == 7,
        "current_invalid_arms_1": n_invalid_now == 1,
        "invalid_arm_count_changed": len(h_invalid) != n_invalid_now,
        "target_arm_was_invalid_in_v121": any(
            r.get("arm") == TARGET_ARM and r.get("citable") == "NOT_CITABLE_measurement_invalid"
            for r in h_arms),
        "counting_layer_a_equals_b": {k: a_counts.get(k) for k in b_counts} == b_counts or not b_counts,
        "historical_meta_is_v121": h_meta3 == V121_META3 and base_meta3 == V121_META3,
    }
    ck.add("D8", "分布层构建相关 + 计数层构建不变，两侧都有实测证据",
           all(d8_terms.values()),
           {"terms": d8_terms, "historical_n_artifacts": h_doc.get("n_artifacts"),
            "historical_invalid_arms": len(h_invalid), "current_invalid_arms": n_invalid_now,
            "historical_controlled_sum": h_counts, "a_counts": a_counts, "b_counts": b_counts,
            "historical_meta3": list(h_meta3), "baseline_meta3": list(base_meta3),
            "historical_meta3_source": st["paths"].get("historical"),
            "baseline_meta3_source": st["paths"].get("v121_baseline")},
           {"historical_n_artifacts": 44, "historical_invalid_arms": 7, "current_invalid_arms": 1,
            "historical_meta_is_v121": list(V121_META3)},
           note="裁定 30.4 的**双向**证据：无效臂 7→1 证明分布层的臂集随构建变（所以必须带指纹）；"
                "计数层 A==B 证明逐局计数不随构建变（所以能力结论一字不变，裁定 28 ③）。"
                "裁定 30.5：v1.2.1 是 n_artifacts=44 的**不同臂集**，与 48 臂不可直接相减。"
                "裁定 35.2（增补十二 §41）：基线/历史口径文件的价值恰恰在于它**停在旧值**，"
                "刷它 = 把断言的左操作数改成右操作数 ⇒ `historical_meta_is_v121` 逐值比两处操作数。")

    # ---- D9（非 blocking）：引历史口径处必须报 n_artifacts ----
    bare = []
    for name, lines in (st.get("docs") or {}).items():
        for i, line in enumerate(lines):
            if not V121_COUNT_SIGNATURE.search(line):
                continue
            lo, hi = max(0, i - 4), min(len(lines), i + 5)
            if "n_artifacts" not in "\n".join(lines[lo:hi]) and "44" not in "\n".join(lines[lo:hi]):
                bare.append({"doc": name, "line": i + 1, "text": line.strip()[:140]})
    ck.add("D9", "引 v1.2.1 历史计数处必须同时报 n_artifacts（裁定 30.5）",
           not bare, {"n_bare_citations": len(bare), "bare": bare[:10]},
           {"n_bare_citations": 0}, blocking=False,
           note="非 blocking：这是引用纪律而非事实错误。但「计数层构建不变」若不带 n_artifacts，"
                "会被误读成「跨所有构建都不变」——裁定 30.5 专门补了这个限定。")

    # ---- D10：单构建纪律 + 三处指纹一致（裁定 16 / 29.1）----
    bd = a_meta.get("build_discipline") or {}
    d10_terms = {
        "single_build_only": bd.get("single_build_only") is True,
        "this_table_build_matches_rows": (bd.get("this_table_build") or {}).get("gate_build")
                                         == a_meta.get("gate_build"),
        "meta_gate_build_is_list_of_1": isinstance(a_meta.get("gate_build"), list)
                                        and len(a_meta["gate_build"]) == 1,
        "historical_builds_marked_superseded": all(
            x.get("status") == "superseded" for x in (bd.get("historical_builds_superseded") or []))
            if (bd.get("historical_builds_superseded") or []) else False,
    }
    ck.add("D10", "单构建纪律：一张表只允许一个 gate_build，旧构建标 superseded",
           all(d10_terms.values()), {"terms": d10_terms, "meta_gate_build": a_meta.get("gate_build"),
                                     "meta_gate_version": a_meta.get("gate_version")},
           {"single_build_only": True, "all_historical": "superseded"},
           note="禁跨 build 混引（裁定 16）。分布层陈述带的那个指纹，必须就是这一张表的指纹。")

    return ck


def report(ck: Checks, gate_open: bool, extra: dict) -> None:
    for r in ck.rows:
        tag = "PASS" if r["pass"] else ("FAIL" if r["blocking"] else "WARN")
        print(f"[{tag}] {r['id']:<4} {r['name']}")
        if not r["pass"]:
            print(f"           observed = {json.dumps(r['observed'], ensure_ascii=False)[:900]}")
            print(f"           required = {json.dumps(r['required'], ensure_ascii=False)[:400]}")
        if r["note"]:
            print(f"           note     = {r['note']}")
    print()
    print(f"DISTRIBUTION_LAYER_CHECK={'OPEN' if gate_open else 'CLOSED'}  "
          f"blocking_fail={ck.n_fail_blocking()}  warn={ck.n_warn()}  "
          f"total_checks={len(ck.rows)}")
    for line in extra.get("lines", []):
        print(line)
    if not gate_open:
        print("处置：按 裁定 30.2 **禁用**「4–9 臂数 = 0」「中间是空的」；引用双峰必须改述为"
              "「强间隙分离（gap-separated）：低簇 0–3 / 高簇 14–20 / 孤立 1 臂 = 9，"
              "空带是 4–8 与 10–13」，并带四限定（臂集 / 20k 快照 / 构建指纹 / 点出孤立臂）。")


# --------------------------------------------------------------------------
# 变异自检：证明这道闸**有牙**（不是恒真）。fixture 全在内存里，不写任何文件。
# --------------------------------------------------------------------------
def _mutate(st: dict, fn) -> dict:
    out = copy.deepcopy(st)
    fn(out)
    return out


def _fail_if(pred, msg):
    if pred:
        raise AssertionError(msg)


def selftest(st0: dict) -> int:
    base = run_checks(st0)
    cases: list[tuple[str, dict, tuple[str, ...], bool]] = []

    # S1 真实现场：必须 OPEN，且 D2 实测 4–9 == 1（裁定 30.6 的可红条件当前为绿）
    cases.append(("S1 真实现场（v1.5 / 21 臂 join）-> OPEN", st0, (), True))

    # S2 把免罪臂的受控成功改成 0（模拟「它没落进 4–9」）=> D2 必须抓住
    def m2(s):
        for r in (s["a_doc"].get("arms") or []):
            if r.get("arm") == TARGET_ARM:
                r["controlled_success"] = 0
        d = _dist(s)
        for lab in ("actlog_subset", "official_all", "measurement_valid"):
            setv = (d.get("arm_sets") or {}).get(lab) or {}
            iv = setv.get("intervals") or {}
            iv["forbidden_window_4_9"] = 0
            iv["low_0_3"] = int(iv.get("low_0_3") or 0) + 1
            setv["middle_band_arms"] = []
            setv["characterization"] = "bimodal_middle_empty"
    cases.append(("S2 免罪臂受控改 0（孤立臂消失）-> CLOSED(D2,D3)",
                  _mutate(st0, m2), ("D2", "D3"), False))

    # S3 反过来：把表里的 4–9 计数改成 0（= 把禁用写法当成事实写进产物）=> D2/D3/D5 必须抓住
    def m3(s):
        d = _dist(s)
        for lab in ("actlog_subset", "official_all", "measurement_valid"):
            setv = (d.get("arm_sets") or {}).get(lab) or {}
            (setv.get("intervals") or {})["forbidden_window_4_9"] = 0
    cases.append(("S3 产物把 4–9 计数写成 0（禁用写法进产物）-> CLOSED(D2,D3,D5)",
                  _mutate(st0, m3), ("D2", "D3", "D5"), False))

    # S4 删掉 distribution_layer 块（= 裁定 30.4 无代码承载）=> D1/D3/D7 必须抓住
    def m4(s):
        (s["a_doc"].get("meta") or {}).pop("distribution_layer", None)
    cases.append(("S4 删掉 distribution_layer（裁定无承载）-> CLOSED(D1,D3,D7)",
                  _mutate(st0, m4), ("D1", "D3", "D7"), False))

    # S5 spec 轴被当成生效条件（裁定 29.1 的地雷复活）=> D1 必须抓住
    def m5(s):
        (_dist(s).get("build_fingerprint") or {})["spec_axis"] = "must_match_c7fadabe8e3c"
    cases.append(("S5 spec 轴写成生效条件（裁定 29.1 地雷复活）-> CLOSED(D1)",
                  _mutate(st0, m5), ("D1",), False))

    # S6 A/B 两表在一个臂上分叉 => D4 必须抓住
    def m6(s):
        for r in (s["a_doc"].get("arms") or []):
            if r.get("arm") == TARGET_ARM:
                r["controlled_success"] = 10
    cases.append(("S6 A/B 两表逐格分叉 -> CLOSED(D4,D2)", _mutate(st0, m6), ("D4", "D2"), False))

    # S7 A 表 build 与 live 门禁不一致（B 解冻/升级而 A 没重出表）=> D4/D10 必须抓住
    def m7(s):
        s["a_doc"]["meta"]["gate_build"] = ["000000000000"]
        (_dist(s).get("build_fingerprint") or {})["gate_build"] = ["000000000000"]
        s["a_doc"]["meta"]["build_discipline"]["this_table_build"]["gate_build"] = ["000000000000"]
    cases.append(("S7 A 表 build 与 live 门禁不一致 -> CLOSED(D4)",
                  _mutate(st0, m7), ("D4",), False))

    # S8 文档里塞一句禁用写法、且不带指针 => D6 必须抓住（A 不自免）
    def m8(s):
        s["docs"] = dict(s.get("docs") or {})
        s["docs"]["docs/a_selftest_fixture.md"] = [
            "# fixture", "两族合并 21 个有 actlog 的臂里，受控成功落在 4–9 的臂数 = 0。", ""]
    cases.append(("S8 无指针的禁用写法 -> CLOSED(D6)", _mutate(st0, m8), ("D6",), False))

    # S9 同一句但**带**更正指针 => D6 必须放行（证明 D6 不是恒假）
    def m9(s):
        s["docs"] = dict(s.get("docs") or {})
        s["docs"]["docs/a_selftest_fixture.md"] = [
            "# fixture", "两族合并 21 个有 actlog 的臂里，受控成功落在 4–9 的臂数 = 0。",
            "> 更正指针（裁定 30 / DR-D29）：上句在 v1.5 口径下已被 1 臂证伪，"
            "准确定性是强间隙分离，空带是 4–8 与 10–13。", ""]
    cases.append(("S9 带更正指针的同一句 -> D6 放行（D6 非恒假）",
                  _mutate(st0, m9), (), True))

    # S10 历史表不可读（= 分布层构建相关失去证据）=> D8 必须抓住
    def m10(s):
        s["h_doc"] = None
    cases.append(("S10 v1.2.1 历史表不可读 -> CLOSED(D8)", _mutate(st0, m10), ("D8",), False))

    # S11 少一个臂集（actlog_subset 缺失）=> D7 必须抓住
    def m11(s):
        (_dist(s).get("arm_sets") or {}).pop("actlog_subset", None)
    cases.append(("S11 缺 actlog_subset 臂集 -> CLOSED(D7,D3)", _mutate(st0, m11), ("D7", "D3"), False))

    # S12 single_build_only 被关掉（跨 build 混引）=> D10 必须抓住
    def m12(s):
        s["a_doc"]["meta"]["build_discipline"]["single_build_only"] = False
    cases.append(("S12 跨 build 混引 -> CLOSED(D10)", _mutate(st0, m12), ("D10",), False))

    # S13/S14/S15：把 v1.2.1 基线的三值刷成 v1.5（裁定 35.2 的可红条件）。
    # **只在 fixture（内存深拷贝）里刷，绝不碰真文件** —— 动真文件本身就是裁定 35.1 禁止的事。
    def _refresh_top_meta3(doc):
        if isinstance(doc, dict):
            for k, v in zip(META3_KEYS, V15_META3):
                doc[k] = v

    def _refresh_nested_meta3(s):
        if not isinstance(s.get("v121_doc"), dict):
            s["v121_doc"] = {}
        meta = s["v121_doc"].setdefault("meta", {})
        for k, v in zip(META3_KEYS, V15_META3):
            meta[k] = [v]

    def m13(s):
        _refresh_top_meta3(s.get("h_doc"))
        _refresh_nested_meta3(s)

    def m14(s):
        _refresh_nested_meta3(s)

    def m15(s):
        _refresh_top_meta3(s.get("h_doc"))

    cases.append(("S13 刷 v1.2.1 基线 meta 成 v1.5（两处操作数）-> CLOSED(D8)",
                  _mutate(st0, m13), ("D8",), False))
    cases.append(("S14 只刷 arms_summary_v3.json 的 meta（A 当初点名的那处）-> CLOSED(D8)",
                  _mutate(st0, m14), ("D8",), False))
    cases.append(("S15 只刷 v1.2.1 历史表顶层三值 -> CLOSED(D8)",
                  _mutate(st0, m15), ("D8",), False))

    n_pass = 0
    print(f"{'变异自检':<58}{'期望':<26}结果")
    print("-" * 104)
    for name, st, expect_closed, expect_open in cases:
        ck = run_checks(st)
        got_closed = tuple(r["id"] for r in ck.rows if not r["pass"] and r["blocking"])
        if expect_open:
            ok = ck.open and not got_closed
            want = "OPEN"
        else:
            ok = (not ck.open) and all(c in got_closed for c in expect_closed)
            want = "CLOSED" + "(" + ",".join(expect_closed) + ")"
        got = ("OPEN" if ck.open else "CLOSED(" + ",".join(got_closed) + ")")
        print(f"    {name:<54}{want:<26}-> {'pass' if ok else 'FAIL'}   gate={got}")
        n_pass += 1 if ok else 0
    # 基线自检：真实现场必须 OPEN（否则整张表都不可信，先修现场再谈判据）
    if not base.open:
        print("    [FAIL] 真实现场不是 OPEN —— 判据自检无意义，先修现场")
        return 1
    print(f"\n  分布层闸自检：{n_pass}/{len(cases)} 通过")
    return 0 if n_pass == len(cases) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--a-table", default=A_TABLE)
    ap.add_argument("--b-table", default=B_TABLE)
    ap.add_argument("--historical-table", default=B_TABLE_V121)
    ap.add_argument("--actlog-diag", default=ACTLOG_DIAG)
    ap.add_argument("--b-gate", default=B_GATE)
    ap.add_argument("--v121-baseline", default=V121_BASELINE,
                    help="裁定 35.2 的第二处 v1.2.1 操作数（归属基线汇总表，meta 三值必须停在旧值）")
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--selftest", action="store_true", help="变异自检（不写任何文件）")
    args = ap.parse_args()

    st = load_state(args)
    if args.selftest:
        return selftest(st)

    ck = run_checks(st)
    dist = _dist(st)
    a21 = _set(dist, "actlog_subset")
    extra = {"lines": [
        f"  权威口径：{(st.get('a_doc') or {}).get('meta', {}).get('gate_version')} / "
        f"{(st.get('a_doc') or {}).get('meta', {}).get('gate_build')}"
        f"（裁定 29.1：不带 spec 值）",
        f"  21 actlog 臂（20k 快照）：低簇 0–3 = {(a21.get('intervals') or {}).get('low_0_3')}，"
        f"高簇 14–20 = {(a21.get('intervals') or {}).get('high_14_20')}，"
        f"孤立臂 = {[m.get('arm') for m in (a21.get('middle_band_arms') or [])]}"
        f"（受控 {[m.get('controlled_success') for m in (a21.get('middle_band_arms') or [])]}），"
        f"空带 4–8 = {(a21.get('intervals') or {}).get('empty_band_4_8')} / "
        f"10–13 = {(a21.get('intervals') or {}).get('empty_band_10_13')}",
        "  可引用写法：「强间隙分离（gap-separated）」；禁用写法：「4–9 臂数 = 0」「中间是空的」",
    ]}
    report(ck, ck.open, extra)

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "check": "a_distribution_layer_check",
            "ruling": "裁定 30 / DR-D29（增补七 §20）",
            "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "read_only": True,
            "verdict": "OPEN" if ck.open else "CLOSED",
            "blocking_fail": [r["id"] for r in ck.rows if r["blocking"] and not r["pass"]],
            "warn": [r["id"] for r in ck.rows if not r["blocking"] and not r["pass"]],
            "n_checks": len(ck.rows),
            "authoritative_citation": {
                "gate_version": (st.get("a_doc") or {}).get("meta", {}).get("gate_version"),
                "gate_build": (st.get("a_doc") or {}).get("meta", {}).get("gate_build"),
                "spec_axis": "observation_only（裁定 29.1）",
                "arm_set": "actlog_subset（21 臂）", "snapshot": "20k（checkpoints/last）",
                "characterization": "gap_separated",
                "isolated_middle_arm": [m.get("arm") for m in (a21.get("middle_band_arms") or [])],
            },
            "paths": st["paths"],
            "rows": ck.rows,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  留档 -> {args.json_out}")
    return 0 if ck.open else 1


if __name__ == "__main__":
    sys.exit(main())
