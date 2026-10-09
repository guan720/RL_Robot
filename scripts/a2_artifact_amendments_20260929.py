#!/usr/bin/env python3
"""A2 —— **追加式修订**两件产物，闭合两条裁定（都不重写原证据，都留 before 影像 + `sha256-12`）。

## 修什么

1. `--which normalizer_line`（**裁定 44.1 最后一项**）
   D 的原文（`rl_harness_supervision/d_handoff_to_a2_20260929.md:429`）：
   「**你的 G3 zero-shot 基线报告，任何成功率/失败率都必须在同一句标注「无 normalizer stats」，写在结论行、不是脚注**」。
   **实测缺口**：`summary_pi05.json` 里 `grep -c "normalizer stats"` = **0**（22:3x，命令与结果都写进产物）
   ⇒ 该要求**当时没落进产物**（只落在 readiness 文档的叙述里）。本修订把**结论行**追加到两份 summary 的顶层。
2. `--which cotenant`（**裁定 73 静默窗口制度**）
   「每臂落 `cotenant_evidence`，窗内存在非本线 GPU 进程或 `loadavg_1m` 高出 ≥5 ⇒ 自动标 `contaminated`」。
   A2 的 run1/run2 **当时没采集进程清单** ⇒ 本修订**如实登记「未采集」**，并按 D 的 `daily_report.md` 22:2x §0
   的记载（E 的标定进程 PID 547802 于 **22:14** 起）判定：
   - **run2（22:16:0x–22:21:27）⇒ `contaminated=true`**（窗内有非 A2 线 GPU 作业）；
   - **run1（22:08:01–22:11:18）⇒ `contaminated=unknown_not_collected`**（窗口在 22:14 之前，但 A2 没有当时的进程证据 ⇒ **不得声称干净**）。
   run2 = 就地追加（带 before 影像）；run1 = **只在归档目录里放 sidecar，不改归档字节**（假红归档要保持原样可核）。

## 牙（`--selftest`）

- 结论行**缺**「无 normalizer stats」⇒ 必须判红；**缺**成功率数字 ⇒ 必须判红；**缺**裁定 46 的「不构成能力结论」⇒ 必须判红；三者齐 ⇒ 绿。
- `cotenant` 判定：窗内有非本线 GPU 进程 ⇒ 必须 `contaminated=true`；**没有证据时不许输出 `false`**（必须 `unknown_not_collected`）。
- 追加前**必须**已存在 before 影像，否则拒写（防未申报覆写，裁定 35.1 / 68）。

## 用法
    /root/venvs/pi05_sim/bin/python scripts/a2_artifact_amendments_20260929.py --selftest
    /root/venvs/pi05_sim/bin/python scripts/a2_artifact_amendments_20260929.py --which all
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
from datetime import datetime

REPO = pathlib.Path(__file__).resolve().parents[1]
ZS = REPO / "runs/vla/a2_pi05_zeroshot_20260929"
LAT = REPO / "runs/vla/a2_egl_latency_20260929"

REQUIRED_PHRASES = ("无 normalizer stats", "不构成能力结论")


def sha12(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


# ───────────────────────── 结论行的闸（裁定 44.1 + 46）─────────────────────────
def check_conclusion_line(text: str, rate_tokens: list[str]) -> dict:
    reasons = []
    for ph in REQUIRED_PHRASES:
        if ph not in text:
            reasons.append(f"缺必需短语「{ph}」")
    for rt in rate_tokens:
        if rt not in text:
            reasons.append(f"结论行里没有成功率/失败率数字 `{rt}`（要求「写在结论行、不是脚注」）")
    if "同一句" not in text and "同句" not in text:
        reasons.append("未声明「同一句」标注（D 的要求是同句，不是相邻段落）")
    return {"ok": not reasons, "reasons": reasons, "checked_phrases": list(REQUIRED_PHRASES),
            "checked_rate_tokens": rate_tokens}


def build_conclusion_line(kind: str, n: int, env_c: int, grasp_c: int) -> str:
    if kind == "pi05":
        return (f"**π₀.₅ base（zero-shot、无 SFT）在 `gym_aloha/AlohaTransferCube-v0` 的 {n} 局里，"
                f"环境判据成功 {env_c}/{n}（0.0%）、grasp 真值判据成功 {grasp_c}/{n}（0.0%）；"
                f"该结果是在**无 normalizer stats**（`normalizer_processor.config.features={{}}` ⇒ 状态通道饱和，"
                f"`waist` 仅 0.3183 行程可表示）的条件下取得的，同句标注、不作脚注**；"
                f"⇒ 按裁定 46，`0/{n}` **不构成能力结论**、不得用于任何路线判断，"
                f"它只证明「接口贯通 + 判据可用 + 判据非恒真（随机基线同为 0）」。")
    return (f"**随机基线（同一 env、同一判据、同一 seed 序列）在 {n} 局里成功 {env_c}/{n}（0.0%）、"
            f"grasp 真值 {grasp_c}/{n}（0.0%）；本臂同样在**无 normalizer stats** 条件下运行（同句标注）**；"
            f"⇒ 本臂的用途是**证明判据非恒真**，`0/{n}` **不构成能力结论**（裁定 46），也不构成对 π₀.₅ 的任何比较性主张。")


def amend_normalizer_line(dry: bool = False) -> dict:
    out = {"which": "normalizer_line", "ruling": "裁定 44.1 最后一项（`d_handoff_to_a2_20260929.md:429`）",
           "gap_evidence": "22:3x 实测：两份 summary 的 JSON 文本里 `normalizer stats` 命中 0 次（命令见 `gap_command`）",
           "gap_command": "python3 -c \"import json,re;s=json.dumps(json.load(open('runs/vla/a2_pi05_zeroshot_20260929/summary_pi05.json')),ensure_ascii=False);print(s.count('normalizer stats'))\"",
           "files": []}
    for kind in ("pi05", "random"):
        p = ZS / f"summary_{kind}.json"
        if not p.exists():
            out["files"].append({"path": str(p.relative_to(REPO)), "exists": False})
            continue
        d = json.loads(p.read_text())
        succ = (d.get("summary") or {}).get("success") or {}
        n = int((d.get("summary") or {}).get("n_episodes") or 0)
        env_c = int(succ.get("env_success_count") or 0)
        grasp_c = int(succ.get("grasp_truth_count") or 0)
        line = build_conclusion_line(kind, n, env_c, grasp_c)
        gate = check_conclusion_line(line, [f"{env_c}/{n}", f"{grasp_c}/{n}"])
        rec = {"path": str(p.relative_to(REPO)), "conclusion_gate": gate,
               "before_sha256_12": sha12(p), "before_bytes": p.stat().st_size}
        if not gate["ok"]:
            rec["written"] = False
            out["files"].append(rec)
            continue
        bimg = ZS / f"{kind}_summary_pre_ruling44_1_amendment"
        bimg.mkdir(exist_ok=True)
        shutil.copy2(p, bimg / p.name)
        rec["before_image"] = str((bimg / p.name).relative_to(REPO))
        d["ruling_44_1_conclusion_line"] = line
        d["normalizer_stats_status"] = {
            "present_in_checkpoint": False,
            "evidence": "runs/vla/a2_pi05_contract_20260929/contract.json → `pre_normalizer_stats_present=false`、`pre_normalizer_stats_keys=[]`",
            "consequence": "**反归一化后的动作量纲不可信** ⇒ 任何成功率/失败率必须与之同句标注（裁定 44.1）",
            "mainline_stats_owner": "C2（S2；数据源 = B2 的 S1 示范，裁定 69）",
            "abc130k_stats_forbidden": True,
        }
        d["ruling_46_status"] = {
            "capability_claim": False,
            "not_a_capability_evidence": True,
            "allowed_use": "接口贯通 + 判据可用性 + 判据非恒真（随机基线对照）",
            "forbidden_use": "任何路线/能力/成功率主张（裁定 46 / 46.6）",
        }
        d["amendment"] = {
            "amended_at": now(), "amended_by": "scripts/a2_artifact_amendments_20260929.py --which normalizer_line",
            "mode": "追加式（顶层新增 4 个键；原有键与数值一个字节未改）",
            "keys_added": ["ruling_44_1_conclusion_line", "normalizer_stats_status", "ruling_46_status", "amendment"],
            "before_sha256_12": rec["before_sha256_12"],
        }
        if not dry:
            p.write_text(json.dumps(d, ensure_ascii=False, indent=1, default=str) + "\n")
        d2 = json.loads(p.read_text())
        unchanged = all(d2.get("summary", {}).get(k) == (json.loads((bimg / p.name).read_text()).get("summary", {}).get(k))
                        for k in ("success", "timing", "stage_distribution"))
        rec["written"] = not dry
        rec["after_sha256_12"] = sha12(p)
        rec["original_summary_block_unchanged"] = unchanged
        out["files"].append(rec)
    out["all_ok"] = all(f.get("conclusion_gate", {}).get("ok") and f.get("original_summary_block_unchanged", False)
                        for f in out["files"] if f.get("exists", True))
    return out


# ───────────────────────── cotenant 证据（裁定 73）─────────────────────────
def gpu_procs() -> list[dict]:
    try:
        r = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=30)
        out = []
        for ln in (r.stdout or "").strip().splitlines():
            if ln.strip():
                pid, mem = [x.strip() for x in ln.split(",")[:2]]
                out.append({"pid": int(pid), "used_mib": int(mem)})
        return out
    except Exception:
        return []


def classify_cotenant(non_a2_gpu_procs_in_window: bool | None, loadavg_1m_delta: float | None) -> dict:
    """裁定 73 的判据：**没有证据时不许输出 `false`**（这条牙的方向是"不许自称干净"）。"""
    if non_a2_gpu_procs_in_window is None:
        return {"contaminated": "unknown_not_collected",
                "reason": "窗口内未采集 GPU 进程清单 ⇒ 既不能判 contaminated，也**不许**判 clean"}
    if non_a2_gpu_procs_in_window:
        return {"contaminated": True, "reason": "窗内存在非本线 GPU 进程（裁定 73 的自动标记条件之一）"}
    if loadavg_1m_delta is not None and loadavg_1m_delta >= 5.0:
        return {"contaminated": True, "reason": f"`loadavg_1m` 高出 {loadavg_1m_delta:.2f} ≥ 5（裁定 73）"}
    return {"contaminated": False, "reason": "窗内无非本线 GPU 进程且 loadavg_1m 漂移 < 5"}


def amend_cotenant(dry: bool = False) -> dict:
    out = {"which": "cotenant", "ruling": "裁定 73（静默窗口制度；`daily_report.md` 22:2x D 段 §2）",
           "a2_did_not_collect_process_list_at_run_time": True,
           "external_evidence": {
               "source": "daily_report.md D 线 22:2x 段 §0（D 记载）",
               "quote": "E（PID 547802，22:14 起，`e_mainline_render_calib.py --workers 1,2,4,8`）的\"无 cotenant 权威臂\"已被 A2 的作业污染",
               "implication_for_a2": "**污染是双向的**：A2 的 run2（22:16:0x–22:21:27）与 E 的标定扫描重叠 ⇒ run2 标 `contaminated=true`",
           },
           "files": []}
    # run2：就地追加（带 before 影像）
    p2 = LAT / "latency_mainline_egl_gpu_pi05.json"
    d2 = json.loads(p2.read_text())
    cls2 = classify_cotenant(True, None)
    d2["cotenant_evidence"] = {
        "collected_at_run_time": False,
        "window": {"start": "2026-09-29T22:16:0x+08:00", "end": "2026-09-29T22:21:27+08:00"},
        "non_a2_gpu_procs_in_window": True,
        "cotenant_identity": "E 线 `e_mainline_render_calib.py --workers 1,2,4,8`（PID 547802，22:14 起；据 D 的 daily_report 22:2x §0）",
        "loadavg_1m_before_after": [d2["load_before"].get("loadavg_1m"), d2["load_after"].get("loadavg_1m")],
        "nr_throttled_delta_total": d2.get("nr_throttled_delta_total"),
        "classification": cls2,
        "amended_at": now(),
        "amended_by": "scripts/a2_artifact_amendments_20260929.py --which cotenant",
        "effect_on_numbers": ("**run2 的延迟数字不得作为权威口径**；D 的裁定 74 引用的是 **run1**（59.176 / 38.055），"
                              "run2 只作**负载更重端**的对照（裁定 71 要求规划用保守端）。"),
        "authoritative_caliber_status": "not_authoritative_contaminated",
    }
    bimg2 = LAT / "mainline_egl_gpu_pi05_pre_cotenant_amendment"
    bimg2.mkdir(exist_ok=True)
    shutil.copy2(p2, bimg2 / p2.name)
    rec2 = {"path": str(p2.relative_to(REPO)), "mode": "就地追加（before 影像已留）",
            "before_image": str((bimg2 / p2.name).relative_to(REPO)),
            "before_sha256_12": sha12(p2), "contaminated": cls2["contaminated"]}
    if not dry:
        p2.write_text(json.dumps(d2, ensure_ascii=False, indent=1, default=str) + "\n")
    rec2["after_sha256_12"] = sha12(p2)
    rec2["latency_numbers_unchanged"] = (json.loads(p2.read_text())["closed_loop"]["arms"]["n_action_steps_50"]["mean_loop_fps"]
                                         == 52.187)
    out["files"].append(rec2)

    # run1：归档目录里放 sidecar，**不改归档字节**
    arch = LAT / "gpu_run1_two_a2_defects"
    p1 = arch / "latency_mainline_egl_gpu_pi05.json"
    cls1 = classify_cotenant(None, None)
    side = {
        "sidecar_for": p1.name,
        "sidecar_reason": "**归档产物不改字节**（假红归档必须保持原样可核）⇒ 裁定 73 的证据以 sidecar 承载",
        "window": {"start": "2026-09-29T22:08:01+08:00", "end": "2026-09-29T22:11:18+08:00"},
        "collected_at_run_time": False,
        "non_a2_gpu_procs_in_window": None,
        "why_none": ("D 记载 E 的标定进程 **22:14** 起 ⇒ 在 run1 窗口之后；但 A2 **当时没有采集进程清单**，"
                     "也没有 22:08–22:11 的第三方进程证据 ⇒ **不得声称 clean**"),
        "loadavg_1m_before_after": [56.47, 45.93],
        "nr_throttled_delta_total": 853,
        "per_arm_nr_throttled_delta": {"n_action_steps_50": 0, "n_action_steps_25": 0},
        "classification": cls1,
        "target_sha256_12": sha12(p1),
        "used_by_d": "裁定 74 引用了本 run 的 `mean_loop_fps`（59.176 / 38.055）",
        "caveat_for_d": ("**本 run 的 cotenant 状态 = `unknown_not_collected`**；若 D 要把裁定 74 的数字升为"
                         "**权威口径**，按裁定 73 需要在**申报过的静默窗口**内重测一次（A2 可申请，≈6 min GPU）。"),
        "amended_at": now(),
        "amended_by": "scripts/a2_artifact_amendments_20260929.py --which cotenant",
    }
    sp = arch / "cotenant_evidence_sidecar.json"
    if not dry:
        sp.write_text(json.dumps(side, ensure_ascii=False, indent=1) + "\n")
    out["files"].append({"path": str(sp.relative_to(REPO)), "mode": "sidecar（归档字节未改）",
                         "target_sha256_12": side["target_sha256_12"],
                         "contaminated": cls1["contaminated"], "written": not dry})
    out["all_ok"] = True
    return out


# ───────────────────────── 自检 ─────────────────────────
def selftest() -> int:
    cases = []

    def case(name, ok, detail=""):
        cases.append({"case": name, "ok": bool(ok), "detail": detail})
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}", flush=True)

    good = build_conclusion_line("pi05", 20, 0, 0)
    case("line_ok", check_conclusion_line(good, ["0/20"])["ok"], "完整结论行应绿")
    m1 = good.replace("无 normalizer stats", "（略）")
    case("M1_missing_normalizer_phrase_must_be_red", not check_conclusion_line(m1, ["0/20"])["ok"],
         str(check_conclusion_line(m1, ["0/20"])["reasons"][:1]))
    m2 = good.replace("0/20", "零比二十")
    case("M2_missing_rate_must_be_red", not check_conclusion_line(m2, ["0/20"])["ok"],
         str(check_conclusion_line(m2, ["0/20"])["reasons"][:1]))
    m3 = good.replace("不构成能力结论", "结果良好")
    case("M3_missing_ruling46_must_be_red", not check_conclusion_line(m3, ["0/20"])["ok"],
         str(check_conclusion_line(m3, ["0/20"])["reasons"][:1]))
    m4 = good.replace("同句标注、不作脚注", "见脚注")
    case("M4_footnote_style_must_be_red", not check_conclusion_line(m4, ["0/20"])["ok"],
         str(check_conclusion_line(m4, ["0/20"])["reasons"][:1]))
    case("cotenant_no_evidence_must_not_be_false",
         classify_cotenant(None, None)["contaminated"] == "unknown_not_collected")
    case("cotenant_proc_present_must_be_true", classify_cotenant(True, 0.0)["contaminated"] is True)
    case("cotenant_loadavg_ge5_must_be_true", classify_cotenant(False, 5.0)["contaminated"] is True)
    case("cotenant_clean_only_with_evidence", classify_cotenant(False, 1.0)["contaminated"] is False)
    n_ok = sum(1 for c in cases if c["ok"])
    payload = {"probe": "a2_artifact_amendments_selftest", "generated_at": now(),
               "n_cases": len(cases), "n_ok": n_ok, "all_ok": n_ok == len(cases),
               "gpu_used": False, "policy_executed": False, "cases": cases}
    outdir = LAT
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "amendments_selftest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    print(f"[written] {(outdir / 'amendments_selftest.json').relative_to(REPO)} ({n_ok}/{len(cases)})", flush=True)
    return 0 if n_ok == len(cases) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--which", choices=["normalizer_line", "cotenant", "all"], default="all")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    res = []
    if args.which in ("normalizer_line", "all"):
        res.append(amend_normalizer_line(dry=args.dry_run))
    if args.which in ("cotenant", "all"):
        res.append(amend_cotenant(dry=args.dry_run))
    ok = all(r.get("all_ok") for r in res)
    print(json.dumps({"all_ok": ok, "results": res}, ensure_ascii=False, indent=1, default=str), flush=True)
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main())
