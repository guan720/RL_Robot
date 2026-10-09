#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""B2 · 散文可核身份表（裁定 92.3：`prose_identity_must_be_verifiable_against_a_saved_artifact` **红线级**）。

## 为什么 B2 要自己产一份（而不是直接引 E 的表）
裁定 92.3 允许「B2/A2 可调用或自产**同 schema** 的表」。E 的 `scripts/e_write_identity_table.py`
的 `TARGETS` 是 E 线那 29 项，**不含 B2 的准入闸产物与 npz** ⇒ B2 散文里要引的身份串
（`admission_verdict.json` / `mutation_verdict.json` / `NORMALIZATION_LEDGER.json` /
`states_14d.npz` / 两份导出器身份）**没有一份在 E 的表里**。自己产一份同 schema 的表，
比在散文里手打 sha 安全：裁定 92.3 的根因就是「**把跑过一条命令当成值来自机器**」——
E 因此把 sha1 的前 12 位当成 sha256 的前 12 位写进散文，还**为它发明了一个不存在的「巧合」**
（缺陷类 ⑱ `fabricated_justification_for_a_wrong_value`）。

## schema（= 裁定 92.3 采为全仓最低标准的那一份，逐字段对齐 E）
- **两种算法都给**：`sha256_12`（= 本仓**唯一**可引用口径，`citation_algo: "sha256[:12]"`）
  与 `sha1_12`（**只为让算法错配一眼可见**，不得被引用）。
- **三种行数口径都给**：`n_lines`（换行符个数 = `wc -l`，与散文里的「N ln」一致）、
  `n_lines_splitlines`、`ends_with_newline`。两者不同就说明文件不以换行结尾（也是可核事实）。
- 每条带 `why_it_matters` + `citable_as`；表头带 `stale_by_construction`（**必然过期**的行点名，
  引用方必须重算，不得采信本表）。

## 比 E 的表多出来的一件（裁定 92.3-ii）
本表**自己就是一件清单/索引件** ⇒ 必须与不跟随符号链接的 `find -P -type f` 对一次账，
**差值必须能被解释**。E 的近失正是「清单漏登产物本体」（`e_coldstart_manifest.py` 第一版
漏登 `sandbox_root_venvs/pi05_sim`，靠那次「170 vs 42」的对账才照出来）。
⇒ 本表对每个声明的 `SCOPE_ROOTS` 都算 `n_found` / `n_listed` / `unlisted[]`：
**`unlisted` 非空且没有写 `unlisted_explanation` ⇒ rc != 0**（漏登不许静默）。
对账基数刻意用外部 `find -P`（**不跟随符号链接**）而不是 `Path.rglob`：`rglob` 跟随符号链接
是 E 本轮另一个已修缺陷（⇒ 清单越界），用它对账等于让对账本身被同一类问题骗过（D 补的那一句）。

## 用法
    /root/venvs/rlrobot/bin/python scripts/b2_identity_table.py
    /root/venvs/rlrobot/bin/python scripts/b2_identity_table.py --out <path> --force
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

GATE_DIR = "runs/vla/b2_env_admission_20260930"
STATES_DIR = "runs/vla/b2_states_14d_20260930"

# (相对路径, 为什么这个身份重要, 可以被引用为什么)
TARGETS: list[tuple[str, str, str]] = [
    # ---- 准入闸（任务 1）----
    ("scripts/b2_env_admission_pi05.py",
     "π₀.₅ 准入闸本体：G1–G5 + V0–V9 复用 + V-pi05-1…8 + A0/A1/A3 装配判据 + 变异自检"
     "（世界层 M / 转录层 T / 特异性元判据 T / **归一台账层 N**）。散文里说的「gate_build」"
     "就是本件的 sha256[:12]，`A0_teeth_current` 拿它逐字比对 mutation_verdict.json",
     "gate_build / 准入闸构建"),
    ("scripts/b2_export_states_14d.py",
     "formal-40 的 npz 导出器。**裁定 87.6 的改判落在这一件**（`contract_conflict.status`："
     "`OPEN_needs_d_ruling` → `CLOSED_by_ruling_87_6`）。改判前后两个身份都要留：改判前 "
     "`8708d4a84d7f` / 986 ln 产出了 D 在裁定 90.4 独立验收的那份 npz",
     "导出器构建（改判后）"),
    ("scripts/b2_patch_manifest_addendum.py",
     "`demo_manifest.json` 的**披露式追加写**（裁定 88.5-1 三字段 + D §20.6-4 命名行）："
     "前后身份全留证 + 机器断言「只增不改」+ 数据集本体穷举计数不变",
     "追加写工具"),
    ("scripts/b2_probe_render_arm.py",
     "渲染臂端点复测（裁定 88.5-1 的补偿控制）⇒ `arm_stable="
     "post_run_independent_probe_same_caliber`（裁定 91.2-2 解除 `inferred` 限定词）",
     "渲染臂探针"),
    ("scripts/b2_replay_teeth_verdict.py",
     "replay 三颗牙的判定复算（裁定 85.5）",
     "replay 牙复算器"),
    ("scripts/b2_s1_generate_dataset.py",
     "S1 双向示范生成器（任务 2 本体）。**加项 1（渲染器硬 preflight 拒绝）仍欠**，"
     "裁定 91.2-3 定位为「下一次采集之前的前置」⇒ 引本件身份时必须同引这笔欠账。"
     "**RR-B2-18（裁定 96.1-③）已修 ⇒ 本件字节已不等于产出 formal-40 的那份生成器字节 "
     "`b6af48fc6d58`（4333 ln）**：网③ 与信号② 的判据由「裸关键字 / `args` 全文归线」改为"
     "「真实执行形态 ∧ 关键字 ∧ 非闲置」，牙由三条升为五条（新增牙④ 负向腿 / 牙⑤ 反漏检）。"
     "**formal-40 的数据内容一个字节未动**（本次只改共租判定，不重采）；引本件身份必须带 "
     "`as_of`，且不得再声称 `generator_sha_matches_formal_batch=true`（裁定 96.1-① / 缺陷类 ㉒）。"
     "修法证据 = `runs/vla/b2_cotenant_detector_fix_20260930/`（牙件 + 对齐件 + 负向腿件）",
     "S1 生成器"),
    ("scripts/b2_run_team_qc.py",
     "团队 `vla_pipeline` 的 validate→clean→qc 三段**只读复用**驱动（任务 2 的收口，不改团队代码）",
     "团队 QC 驱动"),
    # ---- 文书 ----
    ("docs/b2_bidirectional_demo_and_gates_20260929.md",
     "D→B2 handoff:117 指定的**主报告路径**。本轮之前从未落盘（B2 的 15 轮增量只写在 "
     "`daily_report.md` 的 §B2-1…§B2-15）⇒ 这是一笔 B2 自报的欠账，本轮首次落盘",
     "B2 主报告"),
    ("docs/b2_handoff_to_c2_formal40_20260930.md",
     "B2→C2 的 formal-40 交接（npz 身份 + 消费口径 + `stats_provenance` 命名）",
     "B2→C2 交接件"),
    ("docs/b2_gpu_window_incident_and_rr_20260930.md",
     "GPU 静默窗口事故自报 + S1 selftest 首轮 6 红归因 + **RR 续号 RR-B2-15…RR-B2-20**"
     "（并发事故 / 4 红是闸自己写错 / 成本拆分更正 / `contaminated_by_cotenant` 假阳性 / "
     "步数余量只剩 5 步 / A2 契约的 6 位小数）。"
     "**注意它不是 RR 总台账**：RR-B2-01/02/05/06/09 的 OPEN/CLOSED 权威状态在 "
     "`scripts/b2_env_admission_pi05.py` 的 `RR_STATUS` 表里（现场判定经 `ruling_requests` 落盘），"
     "RR-B2-21/22 在 `daily_report.md` 的 §B2-15 里",
     "GPU 窗口事故件 + RR-B2-15…20"),
    ("rl_harness_supervision/d_handoff_to_b2_20260929.md",
     "B2 的**权威任务书**（§15-5 = 裁定 78 的六件、§19.6-2 = contract_conflict 的 P1、"
     "§17-4 = npz 契约、:117 = 主报告路径）",
     "D→B2 权威文书"),
    ("work/decisions/decisions_20260929.md",
     "裁定正文（本轮引用：78 / 86.6-3 / 87.6 / 87.7 / 89.7 / 90.4 / 91.2 / 92.3 / 92.4 / 92.5）",
     "裁定正文"),
    ("daily_report.md",
     "多写者 append-only 广播件。**身份串保质期是分钟级**（裁定 88.6）⇒ 见 stale_by_construction",
     "广播件（不得引 sha）"),
    # ---- 准入闸产物 ----
    (f"{GATE_DIR}/admission_verdict.json",
     "正式判定件：顶层四元组 `n_red/n_warn/n_unjudged` + `n_pass` + `ok_criterion` + `non_green[]`"
     "（裁定 78.2 的最小公共 schema）。本轮实测 `RED ⇒ total=34 PASS=31 WARN=2 RED=1 UNJUDGED=0`",
     "准入判定"),
    (f"{GATE_DIR}/mutation_verdict.json",
     "变异自检产物（`all_ok` / `gate_build` / `specificity` / `layer_counts_declared_vs_measured`）。"
     "`A0_teeth_current` 要求它的 `gate_build` 逐字等于当前脚本构建 ⇒ 改判据不重跑自检就会红",
     "自检产物"),
    (f"{GATE_DIR}/normalized/NORMALIZATION_LEDGER.json",
     "归一台账（裁定 78.3：45 条 `id=null` 的修证）。它是 D 用来核「都修到了没有」的**索引件**，"
     "所以它自己必须与 `find -P -type f | wc -l` 对账（裁定 92.3-ii）⇒ 由 A3 + N1/N2/N3 看守",
     "归一台账"),
    (f"{GATE_DIR}/delegated_g1_g5_upstream_teeth.json",
     "甲层（判据层）产物：B2 **亲自复跑**上游 `--selftest` 的逐 G 覆盖统计（裁定 78.4 的①）。"
     "注意它被 `GUARD_DOC_EXCLUDE_NAMES` 排除在归一之外（名字前缀相同但没有 `checks[]`，"
     "曾被 glob 误吞 ⇒ 台账与 D 的计数对不上账）",
     "上游牙复跑件"),
    (f"{GATE_DIR}/delegated_g1_g5_freeze.json",
     "B 的冻结面溯源闸产物（只读复用，B2 不改判、只转录）",
     "委派产物（freeze）"),
    (f"{GATE_DIR}/delegated_g1_g5_a2env.json",
     "B 的闸跑在 A2 重建目录上的产物。本轮两条 WARN 的来源（真实成因 = 缺 "
     "`requirements.eval.lock.txt`，是**事实缺失的登记**不是违例）",
     "委派产物（a2env）"),
    (f"{GATE_DIR}/delegated_v0_v9.json",
     "V0–V9 不变性口径的委派产物（10/10 全过）",
     "委派产物（V0-V9）"),
    # ---- formal-40 / npz ----
    (f"{STATES_DIR}/formal40/states_14d.npz",
     "**C2 的 BC 硬闸认的就是这个 sha**（`a84a26079550…`）。裁定 90.4 D 独立验收；"
     "裁定 87.6 的改判**不动任何数组** ⇒ 三跑逐字节一致（见 conflictclosure 核验件）",
     "formal-40 npz（数据本体）"),
    (f"{STATES_DIR}/formal40/manifest.json",
     "npz 的 manifest（16 checks / `n_red=0` / `contract_conflict`）。**本轮被改判覆写**："
     "前像 `tmp/b2_before_images_formal40_conflictclosure/manifest.json`",
     "formal-40 manifest"),
    (f"{STATES_DIR}/formal40_conflictclosure_sha_verdict.json",
     "裁定 87.6 改判的**三跑逐字节核验**：原始导出器 + 改判后导出器 ×2 ⇒ raw file sha 全同、"
     "逐数组 bitwise 全同、manifest 0 键删除 / 9 键新增（全在 `contract_conflict` 下）",
     "改判核验件"),
    (f"{STATES_DIR}/formal40_dualrun_sha_verdict.json",
     "03:07 的**双跑**核验（同一导出器连跑两次 ⇒ `raw_file_sha_equal=true`）。"
     "它是「npz 是确定性的」这一命题的**既有实测**，也是推翻上一棒「重跑必变字节」断言的第一份证据",
     "双跑核验件"),
    (f"{STATES_DIR}/formal40_run4_conflictclosure.log",
     "改判后重跑 formal40 的 stdout 原文（`contract_conflict: CLOSED_by_ruling_87_6`、`verdict PASS`）",
     "重跑日志"),
    ("runs/vla/b2_sim_demo_bidir_20260930/formal/demo_manifest.json",
     "S1 formal-40 数据集本体的 manifest（含 `b2_patch_manifest_addendum.py` 追加的三字段："
     "`renderer_class_at_start` / `renderer_class_at_end` / `arm_stable`，以及如实登记的 "
     "`renderer_class_at_end_in_run = null`）",
     "数据集 manifest"),
    # ---- 日志（tmp/ 未入库，但落在 NFS ⇒ 可核）----
    ("tmp/b2_selftest_r86g.log",
     "本轮自检 stdout 原文：**86/86 ALL OK**、特异性 63 成立 / 0 不成立 / 3 显式不适用、"
     "层计数声明==实测 True、`gate_build` 与脚本 sha 逐字相同",
     "自检日志（N 系列首次全过）"),
    ("tmp/b2_formal_gate_20260930_r5.log",
     "本轮正式判定 stdout 原文：`准入：RED ⇒ total=34 PASS=31 WARN=2 RED=1 UNJUDGED=0`"
     "（A3 的假红已消，只剩 V-pi05-3 那条外部标记红）",
     "正式判定日志"),
]

# 裁定 92.3-ii 的对账作用域：本表点名的件落在这些目录下 ⇒ 目录里**没被点名**的件必须被解释。
SCOPE_ROOTS: list[tuple[str, str | None]] = [
    (GATE_DIR,
     "未点名的件分三类，全部是**可重生成件或逐份身份另有登记处**：① `normalized/` 下的 14 份"
     "归一副本（11 份有效 + 3 份 `_superseded_layout1_*` 旧副本）—— 逐份身份（sha256_12 前后、"
     "bytes、id 修正数）在 `NORMALIZATION_LEDGER.json` 里，本表只登台账本身；② 4 份 `.log`"
     "（委派子进程的 stdout 原文）—— 与同名 `.json` 一一对应，身份随 json 走；③ `live_probe.json`"
     "与 `B2_IDENTITY_TABLE_*.json`（本表自己）—— 前者是运行内采集的探针读数、后者按定义"
     "无法登记自己（见 stale_by_construction）；④ `before_images/`（本表被 `--force` 重写时留下的"
     "**前像**，裁定 89.7 / 92.2 的 `overwrite_own_artifact` 纪律 ⇒ 前像本身不登记，"
     "它是被登记件的历史值）"),
    (STATES_DIR,
     "未点名的件是**旁证/中间态目录**：`formal40_dualrun_sha_check/`、"
     "`formal40_postaddendum_sha_check/`、`formal40_conflictclosure_sha_check/`、`pilot5/`"
     "（每个都含一份 `states_14d.npz` + `manifest.json`）与 `formal40_run1/2/3.log`。"
     "它们的 npz 与 `formal40/states_14d.npz` **逐字节同 sha**（三份核验件已实测），"
     "所以本表只登权威那一份；`pilot5/` 是 5 集先导批（命名说明行见 §B2-13.2）"),
]

# **必然过期**的行：引用方必须重算，不得采信本表。
STALE_BY_CONSTRUCTION = [
    "① 本表自己（`files` 在写盘前采集 ⇒ 本表无法登记自己的终值，与 E 的表同理）",
    "② `daily_report.md`（多写者、append-only ⇒ **身份串保质期是分钟级**，裁定 88.6）",
    "③ `docs/b2_bidirectional_demo_and_gates_20260929.md`（B2 主报告：本轮仍在补写，"
    "且下一次增量会继续 append ⇒ 引用时重算）",
    "③b `docs/b2_handoff_to_c2_formal40_20260930.md`（B2→C2 交接件，同样 append-only："
    "本轮 §11 与后续每一次知会都会继续追加 ⇒ 引用时重算）",
    "④ `runs/vla/b2_env_admission_*/admission_verdict.json` 与 `mutation_verdict.json`"
    "（**可重生成件**：再跑一次闸就会重写；引用必须带 `gate_build` 一起引，否则读者无法判"
    "这份判定出自哪一版判据）",
]


def sha_of(p: Path, algo: str) -> str:
    h = hashlib.new(algo)
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def find_p_type_f(root: Path) -> dict:
    """不跟随符号链接的 `find -P <root> -type f`（裁定 92.3-ii 的对账基数）。

    `n = -1` 表示**没测到**（不得当 0 读）—— 这是本仓已经栽过两次的坑：把「没测到」读成
    「没有问题」（三值纪律的反面）。
    """
    out = {"command": "find -P %s -type f" % root, "n": -1, "rc": None, "error": None,
           "paths": []}
    if not root.exists():
        out["error"] = "root 不存在：%s（⇒ 没测到，不是 0）" % root
        return out
    try:
        p = subprocess.run(["find", "-P", str(root), "-type", "f"],
                           capture_output=True, text=True, timeout=300)
    except Exception as e:                                    # noqa: BLE001
        out["error"] = "%s: %s" % (type(e).__name__, e)
        return out
    out["rc"] = p.returncode
    if p.returncode != 0:
        out["error"] = "find rc=%s stderr=%s" % (p.returncode, (p.stderr or "")[:300])
        return out
    out["paths"] = sorted(ln.strip() for ln in p.stdout.splitlines() if ln.strip())
    out["n"] = len(out["paths"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(REPO / GATE_DIR
                                         / ("B2_IDENTITY_TABLE_%s.json"
                                            % time.strftime("%Y%m%d_%H%M"))))
    ap.add_argument("--force", action="store_true",
                    help="目标已存在时允许重写，但**先把旧件移进 before_images/**（裁定 89.7）")
    a = ap.parse_args()

    out = Path(a.out)
    if not out.is_absolute():
        out = REPO / out
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        if not a.force:
            print(json.dumps({"ok": False, "exit": 3,
                              "error": ("拒绝覆写已存在的身份表：%s（换一个 --out 名字，"
                                        "或 --force 且自动留前像）" % out)}, ensure_ascii=False))
            return 3
        bdir = out.parent / "before_images"
        bdir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(out, bdir / ("%s.before%s" % (out.name, time.strftime("%Y%m%d_%H%M%S"))))

    rows, missing = {}, []
    for rel, why, citable in TARGETS:
        p = REPO / rel
        if not p.is_file():
            missing.append(rel)
            rows[rel] = {"missing": True, "why_it_matters": why, "citable_as": citable}
            continue
        b = p.read_bytes()
        st = p.stat()
        rows[rel] = {
            "missing": False,
            "bytes": len(b),
            "n_lines": b.count(b"\n"),                    # wc -l 口径
            "n_lines_splitlines": len(b.splitlines()),
            "ends_with_newline": b.endswith(b"\n"),
            "sha256_12": sha_of(p, "sha256"),
            "sha1_12": sha_of(p, "sha1"),
            "mtime": time.strftime("%Y-%m-%dT%H:%M:%S %Z", time.localtime(st.st_mtime)),
            "why_it_matters": why,
            "citable_as": citable,
        }

    # ---- 裁定 92.3-ii：本表自己是清单件 ⇒ 与 `find -P -type f` 对账，差值必须被解释 ----
    bad, scopes = [], []
    listed_abs = {str((REPO / rel).resolve()) for rel, _, _ in TARGETS}
    for root_rel, explanation in SCOPE_ROOTS:
        root = REPO / root_rel
        f = find_p_type_f(root)
        if f["n"] < 0:
            bad.append("`find -P` 在 `%s` 上**没测到**（error=%s）⇒ 不得当 0 读，本作用域弃权"
                       % (root_rel, f["error"]))
            scopes.append({"root": root_rel, "find": {k: f[k] for k in
                                                      ("command", "n", "rc", "error")}})
            continue
        listed = sorted(p for p in f["paths"] if p in listed_abs)
        unlisted = sorted(p for p in f["paths"] if p not in listed_abs)
        explained = bool(explanation) or not unlisted
        if not explained:
            bad.append("`%s` 下有 %d 份件**没被本表点名**且没有写 `unlisted_explanation`"
                       "（E 的近失同型：清单漏登产物本体）⇒ 必须逐份点名或解释"
                       % (root_rel, len(unlisted)))
        scopes.append({
            "root": root_rel,
            "find": {k: f[k] for k in ("command", "n", "rc", "error")},
            "n_found": f["n"], "n_listed": len(listed), "n_unlisted": len(unlisted),
            "listed": [str(Path(p).relative_to(REPO)) for p in listed],
            "unlisted": [str(Path(p).relative_to(REPO)) for p in unlisted],
            "unlisted_explanation": explanation,
            "difference_explained": explained,
            "identity": "n_found == n_listed + n_unlisted",
            "identity_holds": (f["n"] == len(listed) + len(unlisted)),
        })
        if f["n"] != len(listed) + len(unlisted):
            bad.append("`%s`：n_found %d != n_listed %d + n_unlisted %d ⇒ 恒等式不成立"
                       % (root_rel, f["n"], len(listed), len(unlisted)))
    if len(rows) != len(TARGETS):
        bad.append("本表自己的行数对不上：rows %d != TARGETS %d" % (len(rows), len(TARGETS)))
    if missing:
        bad.append("有 %d 个目标在盘上不存在：%s（散文若引了它们的 sha 就是 `unbacked_citation`）"
                   % (len(missing), missing))

    # ---- `why_it_matters` 的**内容**也要对账（不只对文件存在性）----
    # 本轮真实事故：B2 给 `docs/b2_gpu_window_incident_and_rr_20260930.md` 写的
    # `why_it_matters` 是「RR 请示单台账（含 **RR-B2-01/02/05/09** 的 OPEN/CLOSED 状态）」，
    # 而该件实测只含 **RR-B2-15…RR-B2-20**；01/02/05/06/09 的权威状态在
    # `scripts/b2_env_admission_pi05.py` 的 `RR_STATUS` 表里。**那是一句关于文件内容的假话，
    # 写在一件机器可读的产物里**（裁定 92.5 缺陷类 ⑱ 的近亲：值错了还配一个站得住-looking 的说明）。
    # 根因：`why_it_matters` 是散文，**没有人核过它说的内容在不在那个文件里**。
    # ⇒ 规则：散文里点名的 RR 号，**默认必须出现在该行的目标件里**；只有当同一段（按 `；`/`。`/换行
    #   切）里**显式改指到另一个目标件的路径**时，才允许它不在本件里（那正是「本件不是该 RR 的
    #   权威出处」的正确写法）。不成立 ⇒ `rc=7`。
    rr_re = re.compile(r"RR-B2-\d+")
    seg_re = re.compile(r"[；。\n]")
    prose_claims, prose_bad = [], []
    for rel, why, citable in TARGETS:
        p = REPO / rel
        mentioned = sorted(set(rr_re.findall(why + " " + citable)))
        if not mentioned:
            continue
        try:
            body = p.read_text(encoding="utf-8", errors="strict")
        except Exception:                                       # noqa: BLE001
            # 二进制件（`.npz`）读不出文本 ⇒ 散文里就**不许**点名 RR 号（无从核 = 不许写）
            prose_claims.append({"file": rel, "mentioned": mentioned, "verifiable": False,
                                 "unverifiable_reason": "目标件不是 utf-8 文本 ⇒ 散文不得点名 RR 号"})
            prose_bad.append("`%s` 不是文本件，但 `why_it_matters` 点名了 %s ⇒ 无从核（不得写）"
                             % (rel, mentioned))
            continue
        other_paths = [r for r, _, _ in TARGETS if r != rel]
        own, redirected = [], []
        for seg in seg_re.split(why + " " + citable):
            ids = sorted(set(rr_re.findall(seg)))
            if not ids:
                continue
            if any(op in seg for op in other_paths):
                redirected.extend(ids)          # 同一段显式改指到别的件 ⇒ 允许不在本件里
            else:
                own.extend(ids)
        own, redirected = sorted(set(own)), sorted(set(redirected))
        not_found = [i for i in own if i not in body]
        prose_claims.append({"file": rel, "verifiable": True, "mentioned": mentioned,
                             "must_be_in_this_file": own,
                             "redirected_to_another_target": redirected,
                             "not_found_in_this_file": not_found,
                             "holds": (not not_found)})
        if not_found:
            prose_bad.append("`%s` 的 `why_it_matters` 点名了 %s，但该件正文里**找不到** ⇒ "
                             "散文对文件内容说了假话（要么改文案，要么在同一段里显式改指到权威件）"
                             % (rel, not_found))
    prose_ok = (not prose_bad)

    table = {
        "artifact": str(out.relative_to(REPO)) if out.is_relative_to(REPO) else str(out),
        "agent": "B2",
        "purpose": ("散文可核身份表：裁定 89.7 立的 "
                    "`prose_identity_must_be_verifiable_against_a_saved_artifact` 在裁定 92.3 "
                    "**升为红线级**后的 B2 落地件。**散文里引用的 sha 必须与本表相等**；"
                    "本表没有的路径，散文只引路径、不引 sha"),
        "citation_algo": "sha256[:12]",
        "citation_algo_why": ("本仓口径 = `hashlib.sha256(...).hexdigest()[:12]`（与 E 的 "
                              "`e_write_identity_table.py`、C2 的 `c2_cite.py`、D 的 §D88 抬头同口径）。"
                              "`sha1_12` 一并给出，**只为让「算法错配」一眼可见**，不得被引用"),
        "line_count_convention": "n_lines = 换行符个数（= `wc -l`），与散文里的「N ln」一致",
        "stale_by_construction": STALE_BY_CONSTRUCTION,
        "schema_source": ("裁定 92.3：「采 E 的 schema 为全仓最低标准（**不改 E 的文件名**）」⇒ "
                          "逐字段对齐 `scripts/e_write_identity_table.py`，只多一块 "
                          "`scope_reconciliation_find_p_type_f`（裁定 92.3-ii 要求清单件自己对账）"),
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "generator": {"file": "scripts/b2_identity_table.py",
                      "sha256_12": sha_of(Path(__file__).resolve(), "sha256"),
                      "n_lines": len(Path(__file__).read_text(encoding="utf-8").splitlines())},
        "loadavg": list(os.getloadavg()),
        "n_targets": len(TARGETS),
        "n_present": len(TARGETS) - len(missing),
        "n_missing": len(missing),
        "missing": missing,
        "scope_reconciliation_find_p_type_f": {
            "ruling": ("裁定 92.3-ii：任何清单/索引件生成后必须与 `find -type f | wc -l`"
                       "（**不跟随符号链接**）对一次行数，差值必须能被解释；D 补：对账基数"
                       "**不得**用会跟随符号链接的 `rglob`"),
            "scopes": scopes,
            "unexplained_differences": bad,
            "identity_holds": (not bad),
            "note": "本块只对**作用域/漏登**负责；散文内容对账见 `prose_content_reconciliation`",
            "why_it_matters": ("本表是散文 sha 的**唯一事实源**；它自己漏登/越界的话，"
                               "下游会把「没登记」读成「不存在」，进而引一个盘上没有的 sha"),
        },
        "prose_content_reconciliation": {
            "ruling": ("裁定 92.3（散文身份必须可核）+ 裁定 92.5 缺陷类 ⑱。这一块核的**不是 sha**，"
                       "而是 `why_it_matters` 里那些**关于文件内容的断言**"),
            "rule": ("散文点名的 `RR-B2-NN` 默认必须出现在该行的目标件正文里；只有同一段（按 `；`/`。`/"
                     "换行切）显式改指到另一个目标件的路径时才允许不在（= 正确写出「本件不是该 RR 的"
                     "权威出处」）。不成立 ⇒ `rc=7`"),
            "why_this_tooth_exists": ("本轮真实事故：B2 给 "
                                      "`docs/b2_gpu_window_incident_and_rr_20260930.md` 写的 "
                                      "`why_it_matters` 说它「含 RR-B2-01/02/05/09 的 OPEN/CLOSED 状态」，"
                                      "实测该件只含 RR-B2-15…RR-B2-20（01/02/05/06/09 的权威状态在 "
                                      "`scripts/b2_env_admission_pi05.py` 的 `RR_STATUS`）。"
                                      "**那是一句写在机器可读产物里的、关于文件内容的假话**，"
                                      "而 `n_missing=0` 与 sha 对账都照不到它 ⇒ 必须有这一颗牙"),
            "n_rows_with_rr_claims": len(prose_claims),
            "rows": prose_claims,
            "holds": prose_ok,
            "detection_limit": ("**这颗牙的检出下限，必须与它一起被引用**（裁定 91.3 的写法：一条判据"
                                "的裕度不是形式条款）：① 正则只认 `RR-B2-<数字>` 的**完整形态**，"
                                "所以「RR-B2-01/02/05/09」这种斜杠缩写只提出 `RR-B2-01` 一个"
                                "（本轮实测：`must_be_in_this_file` 与 `redirected` 里都只有 01/15/20/21，"
                                "02/05/06/09/22 没被提出）⇒ **它挡得住「整串号都是编的」，"
                                "挡不住「缩写里某一个是编的」**；② 它只核 `RR-B2-NN` 这一类标识符，"
                                "不核 sha / 行数 / 计数（那三类由 `files` 与 "
                                "`scope_reconciliation_find_p_type_f` 各自负责）；③「同一段显式改指」"
                                "的判据是**该段里出现了另一个目标件的相对路径串**，是**字面**判据 —— "
                                "散文若用别的写法改指（例如只写「在准入闸脚本里」而不给路径），"
                                "会被判成本件必须有 ⇒ 会**假红**，此时正确修法是**把路径写全**，"
                                "不是放宽这颗牙"),
            "reverse_proven": ("把 B2 本轮真犯过的那句假话（「含 RR-B2-01/02/05/09 的 OPEN/CLOSED "
                               "状态」）原样喂回 ⇒ **rc=7**，`unexplained_differences` 逐字点名"
                               "「该件正文里找不到」。证据 `tmp/b2_idtable_prosetooth_expected_rc7.json`"
                               "（**文件名即结论**，不是失败件）。裁定 27.1：没咬过的守卫不算保护层"),
        },
        "files": rows,
    }
    if not rows:
        print(json.dumps({"ok": False, "exit": 4,
                          "error": "空清单 ⇒ 不生成（裁定 88.3-2）"}, ensure_ascii=False))
        return 4
    out.write_text(json.dumps(table, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    all_bad = bad + prose_bad
    rc = 0 if (not missing and not all_bad) else (5 if missing else (7 if not prose_ok else 6))
    print(json.dumps({"ok": (rc == 0), "exit": rc,
                      "artifact": str(out.relative_to(REPO)) if out.is_relative_to(REPO) else str(out),
                      "n_targets": len(TARGETS), "n_present": len(TARGETS) - len(missing),
                      "n_missing": len(missing), "missing": missing,
                      "scope_reconciliation_ok": (not bad),
                      "prose_content_reconciliation_ok": prose_ok,
                      "unexplained_differences": all_bad,
                      "sha256_12": sha_of(out, "sha256"),
                      "sha1_12": sha_of(out, "sha1"),
                      "n_lines": out.read_bytes().count(b"\n")}, ensure_ascii=False, indent=1))
    return rc


if __name__ == "__main__":
    sys.exit(main())
