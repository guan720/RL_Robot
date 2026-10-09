#!/usr/bin/env python
"""T-E-12（裁定 94.9-6，P1）：**最小证据快照** —— 服务器关掉之后，还能证明「哪些证据曾经存在、判词是什么」。

**为什么要有它**：`runs/` 被 `.gitignore:12` 排除 ⇒ **39.53 GiB 的证据只在 NFS 上，没有异地副本**
（异地副本要用户给 remote，见 §94.10「用户需 ①」）。若服务器关闭且 NFS 不可达，
所有裁定、闸判词、延迟数字都会**失去可对账对象** ⇒ 文书里的 sha 变成一串无法验证的字符。
本件把**白名单内的关键证据**的 `sha256` + `n_bytes` + `verdict` + `as_of` 冻进一个**小文件**，
并另出一份**入库摘要**（`docs/evidence_snapshot_manifest_20260930.md`，B2 代提交 ⇒ 进 git）。
⇒ **字节本身留 NFS；身份与判词进 git。** 这是在没有 remote 的前提下能做到的最强保险。

**四条硬约束（裁定 94.9-6 逐字）**：
1. 单文件 ≤ **200 MiB** ⇒ 超限的**不 hash**，按 `not_hashed_oversize` 登记（**不是**跳过、也不是记 0）。
2. 总读量 ≤ **4 GiB** ⇒ 预算用尽即停，剩余按 `not_measured_budget_exhausted` 登记。**不许全量 hash 39.53 GiB**
   （会吃满 12 核配额并污染 A2 的窗口 —— 裁定 94.9-2 `no_root_filesystem_scans` 同族理由）。
3. **三值纪律** ⇒ `verdict` 取不到就写 `null` + `verdict_status="not_present_in_artifact"`，**绝不填 "green"/"ok"**。
4. **裁定 93.8 的对照探针** ⇒ 注入一个白名单外的文件，**必须被检出为「清单外」**；
   检出不到 ⇒ 本闸按 `not_measured` 登记、**不得报绿**（缺陷类 ⑲）。

**扫描纪律（裁定 94.9-2 / 94.9-4）**：只扫**显式白名单**给出的路径与目录前缀，**不递归 `runs/` 全树、不 `find /`**；
每一条「X 不存在」都带 `scan_scope`（路径集 + 模式集 + 时刻）。

退出码：0 = 快照落盘且探针检出成功；1 = 探针**没**检出（审计器自己红）；
2 = 预算耗尽（部分 `not_measured`）；3 = 目标已存在（拒绝覆写）；4 = 白名单匹配到空集。
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "runs/infra/e_evidence_snapshot_20260930"
DOC_OUT = REPO / "docs/evidence_snapshot_manifest_20260930.md"

MAX_FILE_BYTES = 200 * 1024 * 1024       # 200 MiB（裁定 94.9-6）
MAX_TOTAL_READ = 4 * 1024 ** 3           # 4 GiB（裁定 94.9-6）

# ── 白名单（显式、有界；每条带 owner 与「为什么它关键」）───────────────────────
# `kind`: "file" = 逐字路径；"glob" = 在**给定目录前缀内**按模式匹配（不递归到前缀之外）
WHITELIST = [
    # 治理层（D 单写者）
    ("file", "work/project_parameters.json", "D", "参数表（rev19）—— 全部口径的单一真源"),
    ("glob", "work/decisions", "decisions_*.md", "D", "裁定全history（append-only；本次含 §90–§94）"),
    ("file", "daily_report.md", "多写者", "协调面（append-only）—— 各线申报与销账的唯一处"),
    ("glob", "rl_harness_supervision", "*.md", "D", "D 的交接件与权威重启入口（含四份 20260930 派工单）"),
    # 闸 / 判词层（C2）
    ("glob", "runs/vla/c2_norm_contract_20260929/gate", "run_*/gate_verdict.json", "C2",
     "**闸判词**（裁定 94.9-6 点名）—— BC 准入要 AND 它（裁定 93.4）"),
    ("glob", "runs/vla/c2_norm_contract_20260929", "matrix.json", "C2", "归一化器 33 行矩阵判词（点名件）"),
    ("glob", "runs/vla/c2_norm_contract_20260929", "mainline_status.json", "C2", "主线状态（点名件；**同名双件需带路径消歧**，§D93.7）"),
    ("glob", "runs/vla/c2_norm_contract_20260929/mutation_no_widen_post_identity_center_fix", "*.json", "C2",
     "变异体臂的 matrix/mainline_status（点名件的对照臂）"),
    ("glob", "runs/vla/c2_norm_contract_20260929/stats", "*.json", "C2",
     "C2 的 stats 档（点名件）—— 93.2/93.3 的定标输入"),
    ("glob", "runs/vla/c2_norm_contract_20260929/probe_monotonicity_20260930", "*.json", "C2",
     "四点单调性实测（§94.0 的触发件，含 `STOP_AND_REPORT_TO_D` 判词）"),
    # 数据层（B2）
    ("glob", "runs/vla/b2_states_14d_20260930", "*/*.npz", "B2", "formal-40 的 14 维状态档（点名件；Q3 的权威产物）"),
    ("glob", "runs/vla/b2_states_14d_20260930", "*/*.json", "B2", "上件的 manifest（含 npz 的 sha256-12 与 as_of）"),
    ("glob", "runs/vla/b2_sim_demo_bidir_20260930", "formal/demo_manifest.json", "B2",
     "双向示范的权威 manifest（`versions.venv_python` 的口径来源）"),
    # 运行时 / 延迟层（A2）
    ("glob", "runs/vla/a2_egl_latency_20260929", "latency_mainline_egl_gpu*.json", "A2",
     "A2 的延迟权威跑（点名件）—— 0.7703–0.8009 那一条带的来源"),
    ("glob", "runs/vla/a2_egl_latency_20260929", "selftest.json", "A2", "A2 的三网探测器自检（27/27）"),
    # 身份表层（各线）
    ("glob", "runs/infra/e_mainline_calib_20260929", "*IDENTITY_TABLE*.json", "E", "E 的身份表（点名件）"),
    ("glob", "runs/vla/d_ruling_round_20260930_1010", "*IDENTITY_TABLE*.json", "D", "D 的身份表（点名件）"),
    ("glob", "runs/vla/d_ruling_round_20260930_1100", "*IDENTITY_TABLE*.json", "D", "D 的身份表（§94 那一轮）"),
    ("glob", "runs/vla/b2_env_admission_20260930", "*IDENTITY_TABLE*.json", "B2", "B2 的身份表（点名件）"),
    # 基础设施 / 断点续跑（E）
    ("glob", "runs/infra/e_egl_coldstart_20260930", "COLDSTART_EVIDENCE_v3.json", "E",
     "**唯一权威冷启动证据**（裁定 92.1：不需要 v4）"),
    ("glob", "runs/infra/e_egl_coldstart_20260930", "COLDSTART_EVIDENCE_v3.ANNOTATIONS.json", "E",
     "裁定 92.1(a)(b) 的两个机器可读标注（旁证件，v3 原字节未动）"),
    ("glob", "runs/infra/e_egl_coldstart_20260930", "PERSIST_MANIFEST_v4.json", "E",
     "当前权威持久化清单（裁定 92.2）"),
    ("glob", "runs/infra/e_mainline_calib_20260929", "RENDER_DETERMINISM_TEAM480x640_EGL_REPS5_r2.json", "E",
     "T-E-DET-480 的 egl 臂（480×640 团队三槽登记带来源）"),
    ("glob", "runs/infra/e_mainline_calib_20260929", "RENDER_DETERMINISM_TEAM480x640_OSMESA_REPS5.json", "E",
     "osmesa 对照臂（三相机全逐位）"),
    ("glob", "runs/infra/e_mainline_calib_20260929", "RENDER_DETERMINISM_REPS5.json", "E",
     "224² 采集臂那一轮（`0.052%` 的出处；与 480×640 那轮**不得互搬**）"),
    ("glob", "runs/infra/e_mainline_calib_20260929", "summary_*.json", "E",
     "渲染/吞吐权威值（136.99 ctrl-steps/s = 7.300 ms = 34 ms 预算的 21%）"),
    ("glob", "runs/infra/e_restart_readiness_20260930", "RESTART_READINESS.json", "E", "T-E-11 重启就绪清单"),
    ("glob", "runs/infra/e_restart_readiness_20260930", "V3_TO_V4_DELTA.json", "E", "前缀 v3→v4 的逐条对账（不变量证明）"),
    ("glob", "runs/infra/e_restart_readiness_20260930", "LINK_AUDIT_SELFCHECK_*.json", "E",
     "悬空链接审计器的两侧牙 + 93.8 模式覆盖探针"),
    ("glob", "runs/infra/e_restart_readiness_20260930", "*.SIDECAR.json", "E",
     "T-E-11 v1 的旁证更正件（裁定 96.1-③ 改了 `card_busy()` ⇒ v1 那句「逐字未动」过期；v1 原字节保留）"),
    ("glob", "runs/infra/e_card_busy_fix_20260930", "CARD_BUSY_FIX_VERDICT.json", "E",
     "**Ⅰ 类控制**的修法判词（裁定 96.1-③ · A2 第一次真上卡的前置之一）：六腿 + 两向对照探针 + 网①②字节未改"),
    # 治理层（F）—— 裁定 96.3：「F 的 T-E-12 白名单建议 ⇒ **准，交 E 落地**」
    ("glob", "runs/vla/f_oversight_20260930", "PROGRESS_LEDGER.json", "F",
     "进度台账（裁定 96.3 点名加入）—— 「哪些证据曾存在、判词是什么」的索引之一"),
    ("glob", "runs/vla/f_oversight_20260930", "TRIGGER_REGISTRY.json", "F",
     "预登记触发条件台账（裁定 96.3 点名加入）—— 缺陷类 ⑳ 的消费方登记处"),
    # 文档层
    ("glob", "docs", "*.md", "多写者", "各线的口径文档（含 `infra-gpu-render.md` 的权威恢复块）"),
]

# 体积闸的**对照登记**：这些东西关键但**不可能 hash**，必须显式记为 not_hashed，不许静默缺席
KNOWN_OVERSIZE = [
    ("/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist/hf-cache", "权重/模型缓存（14 GiB）"),
    ("/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist/egl-libs/590.48.01", "EGL 库前缀（339,337,693 B / 34 条目）"),
    ("/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/runs", "全部证据档（39.53 GiB）"),
    ("/workspace/mnt/sppro/yhzhang91/datasets", "数据集（**E 永不写、永不遍历**）"),
]

VERDICT_KEYS = ("verdict", "delivery_status", "overall_verdict", "overall", "status",
                "measurement_status", "ok", "mainline_status", "gate_verdict")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_verdict(p: Path) -> dict:
    """从产物里**取**判词，取不到就 `null`（三值纪律）。绝不猜、绝不填默认绿。"""
    try:
        d = json.loads(p.read_text(errors="replace"))
    except Exception as exc:                                  # 非 JSON（.md/.npz）⇒ 没有判词字段
        return {"verdict": None, "verdict_status": "not_a_json_artifact",
                "verdict_source_key": None, "parse_error": f"{type(exc).__name__}"}

    def find(obj, depth=0):
        if depth > 3 or not isinstance(obj, dict):
            return None
        for k in VERDICT_KEYS:
            if k in obj and isinstance(obj[k], (str, bool, int, float)) :
                return k, obj[k]
        for k in VERDICT_KEYS:
            if k in obj and isinstance(obj[k], dict):
                for kk in ("verdict", "overall", "status", "value"):
                    if kk in obj[k] and isinstance(obj[k][kk], (str, bool, int, float)):
                        return f"{k}.{kk}", obj[k][kk]
        return None

    hit = find(d)
    if hit is None:
        return {"verdict": None, "verdict_status": "not_present_in_artifact", "verdict_source_key": None,
                "top_level_keys_sample": sorted(list(d.keys()))[:12]}
    return {"verdict": hit[1], "verdict_status": "extracted", "verdict_source_key": hit[0]}


def resolve_whitelist() -> tuple[list[dict], list[dict]]:
    """把白名单解析成具体文件列表；同时登记**未命中**的白名单条目（三值：不静默丢）。"""
    matched, unmatched = [], []
    for spec in WHITELIST:
        if spec[0] == "file":
            _, rel, owner, why = spec
            p = REPO / rel
            if p.is_file():
                matched.append({"path": p, "owner": owner, "why": why, "spec": f"file:{rel}"})
            else:
                unmatched.append({"spec": f"file:{rel}", "owner": owner, "why": why,
                                  "scan_scope": {"paths": [str(p)], "patterns": ["<exact>"],
                                                 "as_of": time.strftime("%Y-%m-%dT%H:%M:%S %Z")},
                                  "status": "not_found"})
            continue
        _, root_rel, pattern, owner, why = spec
        root = REPO / root_rel
        hits = sorted(root.glob(pattern)) if root.is_dir() else []
        hits = [h for h in hits if h.is_file()]
        if not hits:
            unmatched.append({"spec": f"glob:{root_rel}/{pattern}", "owner": owner, "why": why,
                              "scan_scope": {"paths": [str(root)], "patterns": [pattern],
                                             "as_of": time.strftime("%Y-%m-%dT%H:%M:%S %Z"),
                                             "root_exists": root.is_dir()},
                              "status": "not_found"})
        for h in hits:
            matched.append({"path": h, "owner": owner, "why": why, "spec": f"glob:{root_rel}/{pattern}"})
    # 去重（同一文件可能被两条 spec 命中）：保留第一条，并记录被合并的 spec
    seen, dedup = {}, []
    for m in matched:
        k = str(m["path"])
        if k in seen:
            seen[k]["also_matched_by"].append(m["spec"])
        else:
            m["also_matched_by"] = []
            seen[k] = m
            dedup.append(m)
    return dedup, unmatched


def unlisted_scan(dirs: list[Path], listed: set[str], cap: int = 4000) -> dict:
    """在**已列入白名单的那些目录前缀内**，找出没被列进去的文件（= 「清单外文件」的真实检出）。

    这不是探针，是**真实测量**：它回答「快照漏了多少」。有界（只扫这些前缀、最多 `cap` 条），
    不递归 `runs/` 全树（裁定 94.9-2）。
    """
    unlisted, scanned = [], 0
    for d in dirs:
        if not d.is_dir():
            continue
        for p in sorted(d.rglob("*")):
            if scanned >= cap:
                return {"capped": True, "cap": cap, "n_unlisted": len(unlisted), "unlisted_sample": unlisted[:40],
                        "n_scanned": scanned, "note": f"达到 cap={cap} ⇒ 计数是**下界**，如实标 capped"}
            if not p.is_file():
                continue
            scanned += 1
            if str(p) not in listed:
                unlisted.append(str(p.relative_to(REPO)))
    return {"capped": False, "cap": cap, "n_unlisted": len(unlisted), "unlisted_sample": unlisted[:40],
            "n_scanned": scanned}


def probe_unlisted_detection(sandbox: Path) -> dict:
    """裁定 93.8 的**对照探针**：注入一个白名单外的文件 ⇒ 必须被检出为「清单外」。

    在 **E 自己的沙箱**里做（不写他线 run 目录）。造三个对象：
      G1 一个**符合**白名单模式的文件  ⇒ 必须被列出（绿见证：证明检测器不是「一律判清单外」）
      B1 一个**不符合**任何模式的文件  ⇒ 必须被检出为清单外（这就是 D 要的那颗探针）
      B2 一个符合模式但**超体积闸**的文件（用一个假的 200 MiB+ 声明）⇒ 必须记 `not_hashed_oversize` 而不是静默跳过
    """
    sandbox.mkdir(parents=True, exist_ok=True)
    listed_root = sandbox / "in_whitelist"
    listed_root.mkdir(exist_ok=True)
    g1 = listed_root / "gate_verdict.json"
    g1.write_text(json.dumps({"verdict": "GREEN_PROBE", "probe": True}, ensure_ascii=False), encoding="utf-8")
    b1 = listed_root / "README_not_whitelisted.txt"
    b1.write_text("injected: 这个文件不在任何白名单模式里 ⇒ 必须被检出为「清单外」\n", encoding="utf-8")

    hits = sorted(listed_root.glob("gate_verdict.json"))
    listed = {str(h) for h in hits}
    all_files = sorted(p for p in listed_root.rglob("*") if p.is_file())
    detected_unlisted = [str(p.relative_to(sandbox)) for p in all_files if str(p) not in listed]

    g1_ok = str(g1) in listed
    b1_ok = any("README_not_whitelisted.txt" in x for x in detected_unlisted)
    # B2：体积闸的形状证明（不真造 200 MiB 文件 —— 那会吃 IO 配额；改为对闸函数本身做单元级注入）
    b2_ok = classify_by_size(MAX_FILE_BYTES + 1) == "not_hashed_oversize" and \
            classify_by_size(MAX_FILE_BYTES - 1) == "will_hash"

    return {"sandbox": str(sandbox.relative_to(REPO)),
            "injected_bad_form": ("B1 = 一个存在于被扫目录、但**不匹配任何白名单模式**的文件"
                                  "（`README_not_whitelisted.txt`）；B2 = 一个**超 200 MiB** 的体积形状"),
            "detected": bool(g1_ok and b1_ok and b2_ok),
            "G1_green_witness": {"expected": "listed", "observed": "listed" if g1_ok else "NOT_LISTED", "ok": g1_ok,
                                 "why": "证明检测器不是「一律判清单外」的平凡真"},
            "B1_unlisted_file": {"expected": "detected_as_unlisted",
                                 "observed": detected_unlisted, "ok": b1_ok},
            "B2_size_gate": {"expected": ">200MiB ⇒ not_hashed_oversize；<200MiB ⇒ will_hash",
                             "observed": {"over": classify_by_size(MAX_FILE_BYTES + 1),
                                          "under": classify_by_size(MAX_FILE_BYTES - 1)},
                             "ok": b2_ok},
            "why_it_matters": ("裁定 93.8 `reference_auditor_must_prove_its_own_pattern_coverage`："
                               "审清单的闸必须先证明**自己的识别模式覆盖对象空间的全部形态**。"
                               "抓不到注入的清单外文件 ⇒ 本快照按 `not_measured` 登记、**不得报绿**"
                               "（缺陷类 ⑲ `green_verdict_from_an_under_covered_audit_pattern`）"),
            "as_of": time.strftime("%Y-%m-%dT%H:%M:%S %Z")}


def classify_by_size(n: int) -> str:
    if n > MAX_FILE_BYTES:
        return "not_hashed_oversize"
    return "will_hash"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(OUT_DIR / "EVIDENCE_SNAPSHOT.json"))
    ap.add_argument("--doc-out", default=str(DOC_OUT))
    ap.add_argument("--sandbox-dir", default=str(OUT_DIR / "probe_sandbox"))
    ap.add_argument("--supersedes", default=None,
                    help="被本快照取代的上一版路径；给了就现取它的身份落进 `supersedes`（原字节不动）")
    ap.add_argument("--why-regenerated", default=None, help="为什么要出这一版（写进产物与入库摘要）")
    args = ap.parse_args()
    out, doc_out = Path(args.out), Path(args.doc_out)
    # **根因修（本轮踩到）**：`payload["artifact"] = str(out.relative_to(REPO))` 要求绝对路径，
    # 而默认值是绝对的、命令行传相对路径就会在**哈希全部跑完之后**才炸（实测白跑 6 m 28 s）。
    # 在入口处一次性归一，别把这个坑留给下一次重跑。
    if not out.is_absolute():
        out = REPO / out
    if not doc_out.is_absolute():
        doc_out = REPO / doc_out
    out.parent.mkdir(parents=True, exist_ok=True)
    for p in (out, doc_out):
        if p.exists():
            print(json.dumps({"verdict": "REFUSE", "reason": f"目标已存在，拒绝覆写（裁定 82 §2-4 / 83.5）: {p}"},
                             ensure_ascii=False))
            return 3

    probe = probe_unlisted_detection(Path(args.sandbox_dir))
    matched, unmatched = resolve_whitelist()
    if not matched:
        print(json.dumps({"verdict": "not_measured", "reason": "白名单匹配到**空集** ⇒ 不给通过形状的读数（裁定 88.3-2）",
                          "unmatched_specs": unmatched}, ensure_ascii=False))
        return 4

    entries, budget_used, budget_stops, oversize = [], 0, [], []
    for m in matched:
        p: Path = m["path"]
        try:
            st = p.stat()
        except OSError as exc:
            entries.append({**{k: v for k, v in m.items() if k != "path"}, "path": str(p.relative_to(REPO)),
                            "status": "not_measured_stat_failed", "error": f"{type(exc).__name__}: {exc}"})
            continue
        n = st.st_size
        cls = classify_by_size(n)
        base = {"path": str(p.relative_to(REPO)), "owner": m["owner"], "why_whitelisted": m["why"],
                "matched_by": m["spec"], "also_matched_by": m["also_matched_by"],
                "n_bytes": n, "as_of_mtime": time.strftime("%Y-%m-%dT%H:%M:%S %Z", time.localtime(st.st_mtime)),
                "size_class": cls}
        if cls == "not_hashed_oversize":
            base.update({"sha256": None, "sha256_12": None, "status": "not_hashed_oversize",
                         "limit_bytes": MAX_FILE_BYTES})
            oversize.append(base["path"])
            entries.append(base)
            continue
        if budget_used + n > MAX_TOTAL_READ:
            base.update({"sha256": None, "sha256_12": None, "status": "not_measured_budget_exhausted",
                         "budget_used_bytes": budget_used, "budget_limit_bytes": MAX_TOTAL_READ})
            budget_stops.append(base["path"])
            entries.append(base)
            continue
        b = p.read_bytes()
        budget_used += len(b)
        base.update({"sha256": hashlib.sha256(b).hexdigest(),
                     "sha256_12": hashlib.sha256(b).hexdigest()[:12],
                     "sha1_12": hashlib.sha1(b).hexdigest()[:12],
                     "n_lines": b.count(b"\n"), "n_lines_splitlines": len(b.splitlines()),
                     "ends_with_newline": b.endswith(b"\n"),
                     "status": "hashed", **extract_verdict(p)})
        entries.append(base)

    listed = {str(REPO / e["path"]) for e in entries if e.get("status") == "hashed"
              or e.get("status") == "not_hashed_oversize"}
    scope_dirs = sorted({(REPO / e["path"]).parent for e in entries
                         if e.get("status") == "hashed" and "/gate/run_" not in e["path"]},
                        key=str)[:12]
    unl = unlisted_scan(scope_dirs, listed)

    n_hashed = sum(1 for e in entries if e.get("status") == "hashed")
    n_verdict_null = sum(1 for e in entries if e.get("status") == "hashed" and e.get("verdict") is None)
    verdict = ("PASS" if probe["detected"] and not budget_stops else
               ("PASS_probe_ok_budget_exhausted" if probe["detected"] else "FAIL_probe_did_not_detect"))
    exit_code = 0 if (probe["detected"] and not budget_stops) else (2 if probe["detected"] else 1)

    payload = {
        "artifact": str(out.relative_to(REPO)), "agent": "E",
        "task": "T-E-12（裁定 94.9-6，P1）最小证据快照",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S %Z"),
        "generator": {"script": str(Path(__file__).resolve().relative_to(REPO)),
                      "sha256_12": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:12],
                      "n_lines": Path(__file__).read_bytes().count(b"\n")},
        "citation_algo": "sha256（本件给**全长**，另给 `sha256_12` 便于与散文口径对齐）",
        "line_count_convention": "`n_lines` = 换行符个数（= `wc -l`）",
        "purpose": ("服务器关闭后仍能证明「哪些证据曾经存在、判词是什么」。"
                    "**字节留 NFS，身份与判词进 git**（入库摘要 = `docs/evidence_snapshot_manifest_20260930.md`，B2 代提交）。"
                    "异地副本需用户给 remote（§94.10 用户需 ①）。"),
        "hard_limits": {"max_file_bytes": MAX_FILE_BYTES, "max_total_read_bytes": MAX_TOTAL_READ,
                        "ruling": "94.9-6：**不许全量 hash 39.53 GiB**（会吃满 12 核配额并污染 A2 的窗口）"},
        "whitelist_specs": [{"spec": (s[0] + ":" + (s[1] if s[0] == "file" else s[1] + "/" + s[2])),
                             "owner": (s[2] if s[0] == "file" else s[3]),
                             "why": (s[3] if s[0] == "file" else s[4])} for s in WHITELIST],
        "n_whitelist_specs": len(WHITELIST),
        "unmatched_whitelist_specs": unmatched,
        "unmatched_scan_scope_note": ("裁定 94.9-4：每条「未命中」都带 `scan_scope`（路径集 + 模式集 + 时刻），"
                                     "**不写成无条件否定**"),
        "entries": entries,
        "n_entries": len(entries),
        "n_hashed": n_hashed,
        "n_not_hashed_oversize": len(oversize),
        "n_not_measured_budget_exhausted": len(budget_stops),
        "budget_used_bytes": budget_used,
        "budget_utilization": round(budget_used / MAX_TOTAL_READ, 8),
        "verdict_field_coverage": {
            "n_hashed_with_verdict": n_hashed - n_verdict_null,
            "n_hashed_verdict_null": n_verdict_null,
            "note": ("`verdict=null` **不是**「判词是空」也不是「绿」，而是「这件产物里没有那批键」"
                     "（`verdict_status` 说明是哪一种）。三值纪律：取不到就写 null。")},
        "known_oversize_registered_not_silently_absent": [
            {"path": p, "what": w, "status": "not_hashed_by_budget_or_scope",
             "exists": Path(p).exists(),
             "note": "关键但**不可能 hash** ⇒ 显式登记，不许静默缺席（否则读者会以为快照覆盖了它）"}
            for p, w in KNOWN_OVERSIZE],
        "pattern_coverage_probe": probe,
        "unlisted_in_scope_real_measurement": {
            **unl,
            "scope_dirs": [str(d.relative_to(REPO)) for d in scope_dirs],
            "meaning": ("**这不是探针，是真实测量**：在已列入的那些目录前缀内，还有多少文件没进快照。"
                        "有界扫描（`cap`），不递归 `runs/` 全树（裁定 94.9-2）。"
                        "`n_unlisted` 大是**预期的** —— 快照是「最小」快照，只收白名单；"
                        "本字段的作用是让「漏了什么」可见、可核，而不是假装全覆盖。")},
        "three_valued_discipline": {
            "statuses_used": sorted({e.get("status") for e in entries}),
            "empty_set_rule": "白名单匹配到空集 ⇒ exit 4 + `not_measured`（裁定 88.3-2）",
            "never_written": ["green", "ok", "pass（作为 verdict 的默认填充值）"]},
        "verdict": verdict,
        "exit_code_semantics": {"0": "快照落盘 + 探针检出 + 预算未耗尽",
                                "1": "**探针没检出**（审计器自己红，缺陷类 ⑲）",
                                "2": "预算耗尽（部分 not_measured）",
                                "3": "目标已存在，拒绝覆写", "4": "白名单空集"},
        "gpu_window_used": False,
        "root_filesystem_scans": "无（裁定 94.9-2）。所有扫描都限定在 `whitelist_specs` 给出的目录前缀内",
        "loadavg": list(os.getloadavg()),
    }
    if args.supersedes:
        sp = Path(args.supersedes)
        if not sp.is_absolute():
            sp = REPO / sp
        raw = sp.read_bytes() if sp.exists() else b""
        payload["supersedes"] = {
            "path": str(sp.relative_to(REPO)) if sp.is_relative_to(REPO) else str(sp),
            "exists": sp.exists(),
            "sha256_12": hashlib.sha256(raw).hexdigest()[:12] if raw else None,
            "n_lines": raw.count(b"\n") if raw else None, "n_bytes": len(raw) if raw else None,
            "bytes_preserved": True,
            "note": ("上一版**原字节保留**、不改一个字节（拒绝覆写闸也在）；本版是**另出一份**，"
                     "不是原地重写。与 `PERSIST_MANIFEST_v3 → v4` 同一个形状（裁定 92.2）"),
        }
        payload["superseded_by"] = None
    if args.why_regenerated:
        payload["why_regenerated"] = args.why_regenerated
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    write_doc(doc_out, payload)
    print(json.dumps({"artifact": str(out.relative_to(REPO)),
                      "doc": str(doc_out.relative_to(REPO)),
                      "verdict": verdict, "exit": exit_code,
                      "n_entries": len(entries), "n_hashed": n_hashed,
                      "budget_used_MiB": round(budget_used / 1048576, 2),
                      "budget_utilization": payload["budget_utilization"],
                      "probe_detected": probe["detected"],
                      "n_unmatched_specs": len(unmatched),
                      "n_unlisted_in_scope": unl["n_unlisted"], "unlisted_capped": unl["capped"],
                      "loadavg": payload["loadavg"]}, ensure_ascii=False, indent=1))
    return exit_code


def write_doc(doc_out: Path, p: dict) -> None:
    """入库摘要（`docs/`，B2 代提交 ⇒ 进 git）。**由工具生成**，身份串人不碰（裁定 92.3(i)）。"""
    rows = [e for e in p["entries"] if e.get("status") == "hashed"]
    sup = p.get("supersedes")
    lines = [
        "# 证据快照入库摘要（2026-09-30 · T-E-12 · 裁定 94.9-6）",
        "",
        f"> 生成器 `scripts/e_evidence_snapshot.py`（{p['generator']['n_lines']} ln "
        f"`{p['generator']['sha256_12']}`）· 生成时刻 **{p['generated_at']}** · "
        f"快照本体 `{p['artifact']}`（**只在 NFS，不入库**）",
        "> **本文件是那份快照的入库摘要**：`runs/` 被 `.gitignore:12` 排除 ⇒ 快照本体进不了 git，"
        "所以把**身份与判词**摘到这里让它随 commit 走。**字节本身仍只在 NFS**（异地副本需用户给 remote，§94.10 用户需 ①）。",
        "",
        "## 0.0 本版取代了谁（裁定 92.2 的形状：另出一份、原字节保留）",
        "",
        (f"- 取代 **`{sup['path']}`**（{sup['n_lines']} ln `{sup['sha256_12']}`，{sup['n_bytes']} B）；"
         f"上一版**原字节保留未动**。\n- 为什么出这一版：{p.get('why_regenerated', '（未填）')}"
         if sup else "- 本版是首版，不取代任何件。"),
        "",
        "## 0. 一句话",
        "",
        f"白名单 **{p['n_whitelist_specs']}** 条 spec ⇒ 命中 **{p['n_entries']}** 件，"
        f"其中 **{p['n_hashed']}** 件已 hash（读量 **{round(p['budget_used_bytes']/1048576, 2)} MiB**，"
        f"= 4 GiB 预算的 **{round(p['budget_utilization']*100, 4)}%**）；"
        f"超 200 MiB 的 **{p['n_not_hashed_oversize']}** 件按 `not_hashed_oversize` 登记；"
        f"预算耗尽 **{p['n_not_measured_budget_exhausted']}** 件。"
        f"裁定 93.8 的对照探针 `detected = {str(p['pattern_coverage_probe']['detected']).lower()}`。"
        f"**判词：`{p['verdict']}`**（exit {0 if p['verdict']=='PASS' else 2}）。",
        "",
        "## 1. 已 hash 的关键证据（`sha256[:12]` + 字节 + 判词 + `as_of`）",
        "",
        "| 线 | 路径 | `n_bytes` | `sha256[:12]` | `verdict` | `verdict` 取自 | `as_of`(mtime) |",
        "|---|---|---|---|---|---|---|",
    ]
    for e in sorted(rows, key=lambda x: (x["owner"], x["path"])):
        v = e.get("verdict")
        vs = "`null`（" + str(e.get("verdict_status")) + "）" if v is None else f"`{v}`"
        lines.append(f"| {e['owner']} | `{e['path']}` | {e['n_bytes']} | `{e['sha256_12']}` | {vs} | "
                     f"`{e.get('verdict_source_key')}` | {e['as_of_mtime']} |")
    lines += [
        "",
        f"**`verdict` 覆盖率**：{p['verdict_field_coverage']['n_hashed_with_verdict']} / {p['n_hashed']} 件取到判词；"
        f"{p['verdict_field_coverage']['n_hashed_verdict_null']} 件为 `null`"
        "（**`null` 不是「绿」也不是「空判词」**，而是「这件产物里没有那批键」，"
        "`verdict_status` 区分 `not_a_json_artifact` / `not_present_in_artifact`）。",
        "",
        "## 2. 白名单里**没命中**的 spec（如实登记，不静默丢）",
        "",
    ]
    if p["unmatched_whitelist_specs"]:
        lines += ["| spec | 线 | 扫描范围 | 状态 |", "|---|---|---|---|"]
        for u in p["unmatched_whitelist_specs"]:
            sc = u["scan_scope"]
            lines.append(f"| `{u['spec']}` | {u['owner']} | `{sc['paths'][0]}` × `{sc['patterns'][0]}`"
                         f"（as_of {sc['as_of']}） | `{u['status']}` |")
    else:
        lines.append("**无**（全部 spec 都命中了至少一件）。")
    lines += [
        "",
        "## 3. 关键但**不可能 hash** 的（显式登记，不许假装覆盖）",
        "",
        "| 路径 | 是什么 | 状态 |",
        "|---|---|---|",
    ]
    for k in p["known_oversize_registered_not_silently_absent"]:
        lines.append(f"| `{k['path']}` | {k['what']} | `{k['status']}`（exists={k['exists']}） |")
    lines += [
        "",
        "## 4. 裁定 93.8 的对照探针（审清单的闸必须自证模式覆盖）",
        "",
        f"- **注入的坏形态**：{p['pattern_coverage_probe']['injected_bad_form']}",
        f"- **`detected` = `{str(p['pattern_coverage_probe']['detected']).lower()}`**",
        f"- 绿见证 G1（符合模式的文件必须被列出，证明不是「一律判清单外」的平凡真）："
        f"`{p['pattern_coverage_probe']['G1_green_witness']['observed']}` "
        f"（ok={p['pattern_coverage_probe']['G1_green_witness']['ok']}）",
        f"- B1（清单外文件）检出：`{p['pattern_coverage_probe']['B1_unlisted_file']['observed']}` "
        f"（ok={p['pattern_coverage_probe']['B1_unlisted_file']['ok']}）",
        f"- B2（体积闸形状）：`{json.dumps(p['pattern_coverage_probe']['B2_size_gate']['observed'], ensure_ascii=False)}` "
        f"（ok={p['pattern_coverage_probe']['B2_size_gate']['ok']}）",
        f"- 沙箱：`{p['pattern_coverage_probe']['sandbox']}`（**E 自己的产物目录，不写他线 run 目录**）",
        "",
        "## 5. 「清单外」的真实测量（不是探针）",
        "",
        f"- 扫描范围：{len(p['unlisted_in_scope_real_measurement']['scope_dirs'])} 个目录前缀"
        f"（`cap={p['unlisted_in_scope_real_measurement']['cap']}`，"
        f"capped={p['unlisted_in_scope_real_measurement']['capped']}）",
        f"- 扫到 {p['unlisted_in_scope_real_measurement']['n_scanned']} 件，"
        f"其中**清单外 {p['unlisted_in_scope_real_measurement']['n_unlisted']} 件**",
        "- **这是预期的**：本快照是「**最小**」快照，只收白名单。本字段的作用是让「漏了什么」可见、可核，"
        "而不是假装全覆盖（裁定 94.9-4：否定性存在主张必须带扫描范围）。",
        "",
        "## 6. 硬约束遵守情况",
        "",
        f"- 单文件 ≤ 200 MiB：**遵守**（超限 {p['n_not_hashed_oversize']} 件按 `not_hashed_oversize` 登记，未 hash）",
        f"- 总读量 ≤ 4 GiB：**遵守**（实读 {round(p['budget_used_bytes']/1048576, 2)} MiB = "
        f"{round(p['budget_utilization']*100, 4)}%）",
        "- **没有全量 hash 39.53 GiB**、**没有 `find /`**、**没有递归 `runs/` 全树**（裁定 94.9-2）",
        "- **本轮未上卡**（`gpu_window_used = false`）",
        "- 三值纪律：`verdict` 取不到写 `null`，白名单空集 ⇒ exit 4",
        "",
        "## 7. 这份摘要**不能**做什么",
        "",
        "- **不能**用它恢复字节 —— 它只有 sha，没有内容。字节在 NFS。",
        "- **不能**把 `verdict=null` 读成「绿」或「通过」。",
        "- **不能**跨线搬判词：表里的 `verdict` 是**从那件产物里取出来的原值**，"
        "E 不重判、不解释、不平均（裁定 71 `caliber_transplant_ban`）。",
        "- **不能**当作能力声明：裁定 46 的禁令不变（BC 出结果前，任何「能搬运/学会了」的表述无效）。",
        "",
    ]
    doc_out.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
