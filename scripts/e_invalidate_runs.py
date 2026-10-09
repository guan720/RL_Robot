#!/usr/bin/env python
"""E 线口径更正件生成器：**点名作废哪些产物、为什么、用什么替代**。

背景：`scripts/e_mainline_render_calib.py` 早期版本在被测 env 同进程里建了一次裸
`mujoco.Renderer` 取 GL 身份（顺序 = `raw_after`），实测该动作会让 GPU 臂后续所有
`physics.render` 退化（返回冻结/垃圾缓冲），**渲染吞吐虚高 +27%～+95%**。
取证见同目录 `RAW_PROBE_INTERFERENCE.json`。

本脚本不手抄数字：直接从三轮 `summary_*.json` 现算对照，输出 `INVALIDATED_RUNS.json`。
判据（每条都可复核）：
  ① 有探针轮 vs 无探针轮，**GPU 臂渲染类分量**显著虚高（≥ 阈值）；
  ② 同两轮 **`physics_only` 不变**（证明不是整机变快，是渲染在空转）；
  ③ 同两轮 **osmesa 臂不变**（证明污染是 GPU 臂特有）；
  ④ 有探针轮 **GPU util 反而更低**（渲染没真在算）。

用法：
  python3 scripts/e_invalidate_runs.py            # 生成 INVALIDATED_RUNS.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import e_gpu_egl_verify as ev  # noqa: E402
import e_egl_probe as ep       # noqa: E402

OUT_DIR = REPO_ROOT / "runs" / "infra" / "e_mainline_calib_20260929"
RENDER_COMPS = ["render_3cam_224", "render_native_3cam_480x640",
                "env_step_native", "env_step_plus_3cam_224"]
INFLATION_INVALIDATE_PCT = 15.0   # 与 e_rawprobe_interference.INFLATION_HARM_PCT 同值同义


def agg_by(summary: dict, mode: str, workers: int, comp: str) -> list[float]:
    vals = []
    for b in summary.get("batches", []):
        if b.get("mode") == mode and b.get("workers") == workers:
            a = (b.get("aggregate") or {}).get(comp)
            if a:
                vals.append(a["aggregate_ctrl_steps_per_s"])
    return vals


def util_of(summary: dict, mode: str, workers: int) -> list:
    return [b.get("gpu_util_max") for b in summary.get("batches", [])
            if b.get("mode") == mode and b.get("workers") == workers]


# ── 手工登记：不由 summary 对照现算的作废件（裁定 88.5-3 强制） ─────────────────
# 为什么需要它：本脚本原先只登记「探针污染」那一类（从 clean/polluted 两轮 summary 现算）。
# 裁定 88.5-3 要求把 §88.2-1 的**假绿件**也登进这个注册表，理由是可 grep 性 ——
# D 在裁定 85.1 立的自检 `invalidation_registry_must_be_grepped_before_adopting_authoritative`
# 意味着未来的读者（含 D 自己）**只 grep 这个注册表**来避开作废件；
# ⇒「散文里说了、注册表里没有」= 对 grep 的读者而言它**仍然是权威件**（缺陷类⑩的镜像）。
# 这个常量被「只追加」与「重生成」两条路径**共用** ⇒ 重生成不会把登记冲掉。
MANUAL_INVALIDATIONS = [
    {
        "file": "RENDER_DETERMINISM_TEAM480x640_EGL_REPS5.json",
        "path": "runs/infra/e_mainline_calib_20260929/RENDER_DETERMINISM_TEAM480x640_EGL_REPS5.json",
        "reason_class": "vacuous_all_reps_skipped_no_measurement",
        "ruling": "裁定 88.2-1（缺陷类 ⑯ `vacuous_truth_over_empty_set`）/ 88.3-2 `aggregate_over_empty_set_must_be_null`",
        "identity": {"sha256_12": "ba1d1f56ab93", "bytes": 18064, "n_lines_wc_l": 598,
                     "mtime": "2026-09-30 02:22", "generated_at": "2026-09-30 02:22:38 CST",
                     "generator": "scripts/e_render_determinism.py", "generator_sha256_12": "d592983ca264",
                     "identity_recomputed_by": "E 于 02:3x 用 sha256sum/wc -l 就地重算（非手抄）"},
        "what_is_invalid": ("**整件不得作为确定性证据引用**。产物里 5 个 rep **全部** `ok=false` + "
                            "`skipped_reason=gpu_yield_gate_card_busy`、`per_backend={}`（空集），"
                            "而 `verdict.all_bitwise_deterministic` 却写着 **`true`** —— 旧版汇总只在 `ok=true` 的 rep 上算，"
                            "**空集 ⇒ `non_deterministic_backend_cam_pairs=[]` ⇒ 平凡真**（`all([])==True` 的语言层陷阱）。"),
        "what_is_STILL_valid": ("**让位闸的行为本身是对的、且是本仓第一次实战自证**：`02:22:37` 起跑前批级闸读到 `busy=true`，"
                                "fd 网抓到 PID 388252（B2 的 `--mutation replay-image-pixel-only --selftest`）持 "
                                "`/dev/nvidia2`+`/dev/nvidiactl`，而当时 `--query-compute-apps` **空**、`memory.used` 只 12 MiB "
                                "⇒ 只有 fd 网看得见（裁定 85.0-2-1 的又一次实证）。`gpu_yield_gate.checks[*]` 的三网读数可用；"
                                "**渲染确定性的任何数值不可用**（一个 rep 都没测）。"),
        "must_not_be_cited_as": ("480×640 团队三槽的确定性/登记带证据；B2 的 G4d 容差基础；"
                                 "任何 `all_bitwise_deterministic` 的引用"),
        "fix": {"file": "scripts/e_render_determinism.py",
                "gate": ("第四道闸：臂内 `ok=true` 的 rep 数为 0 ⇒ `measurement_status=\"not_measured_*\"` + "
                         "`verdict.all_bitwise_deterministic=null` + `verdict.not_a_pass` + **exit 4**（D 在 88.3-2 采为范式）"),
                "mutant_proof": ("runs/infra/e_egl_coldstart_20260930/gate_mutation/GATE_MUTATION_SELFTEST_20260930_023715.json："
                                 "M1 must_go_red（exit 4 ✓）+ M2 must_stay_green（exit 0 + measured ✓），"
                                 "`verdict_set_crosscheck=GREEN`、`two_sided_proof_present=true`、全程不触卡")},
        "replacement": ("① 480×640 的 **osmesa 对照臂已测得且有效**：`RENDER_DETERMINISM_TEAM480x640_OSMESA_REPS5.json`"
                        "（三槽 5/5 全逐位、`max_abs_diff=0`、纯 CPU 未触卡）；"
                        "② **egl 臂待重跑**（裁定 88.5-4：清洁卡、5 reps 一个都不许跳过；若跳过 ⇒ 记 `not_measured`、"
                        "不发布登记带、重跑）⇒ 替代件将是 `RENDER_DETERMINISM_TEAM480x640_EGL_REPS5_r2.json`"),
        "why_the_file_is_kept": ("按 append-only（裁定 82 §2-4 / 83.5）**原字节保留**：它是「让位闸在真实抢卡场景下确实生效」的"
                                 "**唯一实证**，删了等于毁证。就地另有标记件 `VACUOUS_ARTIFACT_20260930_0222.md` 与"
                                 "机器可读旁证件 `RENDER_DETERMINISM_TEAM480x640_EGL_REPS5.INVALIDATED.json`。"),
        "citation_rule": "引用它必须同引本条 + 那两个就地标记件（照裁定 85.1 对 `172.32` 的处理办法）",
        "registered_at": "2026-09-30 02:5x CST", "registered_by": "E（裁定 88.5-3，排在其它一切 E 工作之前）",
    },
]


def merge_manual(doc: dict) -> dict:
    """把手工登记并进 `doc`，并重建**单一 grep 入口** `invalidated_index`。
    **只追加**：既有 `invalidated` 两条与所有既有字段的值与键序一律不动（裁定 82 §2-4）。"""
    doc["invalidated_manual"] = MANUAL_INVALIDATIONS
    auto = [i.get("file") for i in (doc.get("invalidated") or [])]
    manual = [i["file"] for i in MANUAL_INVALIDATIONS]
    doc["invalidated_index"] = {
        "purpose": ("**单一 grep 入口**：本注册表里所有作废件的文件名（自动现算的 + 手工登记的）。"
                    "裁定 85.1 的自检 `invalidation_registry_must_be_grepped_before_adopting_authoritative` "
                    "靠它执行 —— 引用任何 E 的渲染产物之前，先在这里 grep 它的文件名。"),
        "n_total": len(auto) + len(manual),
        "from_summary_comparison": auto,
        "manual": manual,
        "grep_hint": "grep -n '<文件名或 reason_class>' runs/infra/e_mainline_calib_20260929/INVALIDATED_RUNS.json",
    }
    doc["manual_registration_note"] = (
        "`invalidated`（自动，从 clean/polluted 两轮 summary 现算）与 `invalidated_manual`（手工登记，"
        "不由 summary 现算）**并列存在、语义不同**：前者的作废范围只覆盖 GPU 渲染类分量数字，"
        "后者逐条写清 `what_is_invalid` / `what_is_STILL_valid`。两者都进 `invalidated_index`。"
        "**手工登记写在本脚本的 `MANUAL_INVALIDATIONS` 常量里**（单一真源）⇒ 重生成不会把它冲掉。")
    return doc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clean", default="summary_20260929_220400.json",
                    help="无探针轮（GPU 数字有效的参照轮）")
    ap.add_argument("--polluted", default="summary_20260929_221443.json,summary_20260929_222019.json",
                    help="含探针轮（逗号分隔）")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--append-manual-only", action="store_true",
                    help="**只追加**手工登记（裁定 88.5-3）到既有 INVALIDATED_RUNS.json：读入 → merge_manual() → 写回；"
                         "不重算 summary 对照、既有键值逐字不动。默认路径（重生成）在目标已存在时会 REFUSE。")
    ap.add_argument("--allow-regenerate", action="store_true",
                    help="显式允许**原地重生成**（会改变被裁定 85.1 引用过的字节身份）。默认拒绝：append-only。")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    target = out_dir / "INVALIDATED_RUNS.json"
    if args.append_manual_only:
        if not target.exists():
            print(json.dumps({"verdict": "REFUSE",
                              "reason": f"--append-manual-only 需要既有注册表，但 {target} 不存在"},
                             ensure_ascii=False))
            return 3
        before = target.read_bytes()
        doc = merge_manual(json.loads(before.decode("utf-8")))
        target.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        after = target.read_bytes()
        print(json.dumps({"mode": "append_manual_only", "artifact": str(target),
                          "sha256_12_before": hashlib.sha256(before).hexdigest()[:12],
                          "sha256_12_after": hashlib.sha256(after).hexdigest()[:12],
                          "bytes_before": len(before), "bytes_after": len(after),
                          "n_invalidated_auto": len(doc.get("invalidated") or []),
                          "n_invalidated_manual": len(doc["invalidated_manual"]),
                          "invalidated_index": doc["invalidated_index"]["manual"]
                          + doc["invalidated_index"]["from_summary_comparison"]},
                         ensure_ascii=False, indent=1))
        return 0
    if target.exists() and not args.allow_regenerate:
        print(json.dumps({"verdict": "REFUSE",
                          "reason": f"{target} 已存在（其字节被裁定 85.1 引用过：sha256-12 0ccd9b586668）；"
                                    "本件 append-only，重生成会改变被引用的字节身份",
                          "hint": ("要登记新的作废件 ⇒ 用 --append-manual-only（只追加）；"
                                   "确要重生成 ⇒ 先留前像（C2 守卫 snapshot）再显式给 --allow-regenerate")},
                         ensure_ascii=False))
        return 3
    clean_path = out_dir / args.clean
    clean = json.loads(clean_path.read_text(encoding="utf-8"))
    polluted = {}
    for name in [x.strip() for x in args.polluted.split(",") if x.strip()]:
        p = out_dir / name
        polluted[name] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    comparison = []
    for name, pol in polluted.items():
        if pol is None:
            comparison.append({"file": name, "error": "文件不存在"})
            continue
        rows = []
        for mode in ("egl_nvidia", "osmesa"):
            for w in sorted({b["workers"] for b in clean.get("batches", []) if b["mode"] == mode}):
                for comp in (["physics_only"] + RENDER_COMPS):
                    a = agg_by(clean, mode, w, comp)
                    b = agg_by(pol, mode, w, comp)
                    if not a or not b:
                        continue
                    ma, mb = statistics.median(a), statistics.median(b)
                    rows.append({"mode": mode, "workers": w, "component": comp,
                                 "clean_median": round(ma, 2), "polluted_median": round(mb, 2),
                                 "delta_pct": round(100 * (mb - ma) / ma, 1)})
        gpu_render = [r for r in rows if r["mode"] == "egl_nvidia" and r["component"] in RENDER_COMPS]
        # C2 的对照必须限定在**受污染的那条臂自身**（egl_nvidia）：问的是"同一批 GPU 进程里，
        # 只有渲染变快了、物理没变快吗"。把 osmesa 的 physics_only 混进来会被 CPU 共租噪声
        # （实测 ±41%）淹掉，那是另一个问题，单独记为 C5。
        phys = [r for r in rows if r["component"] == "physics_only" and r["mode"] == "egl_nvidia"]
        phys_cpu = [r for r in rows if r["component"] == "physics_only" and r["mode"] == "osmesa"]
        cpu_render = [r for r in rows if r["mode"] == "osmesa" and r["component"] in RENDER_COMPS]
        comparison.append({
            "file": name,
            "generated_at_of_that_run": pol.get("timestamp"),
            "n_batches": len(pol.get("batches", [])),
            "cotenant_label_in_filename": pol.get("cotenant"),
            "cotenant_blocked": pol.get("cotenant_blocked"),
            "rows": rows,
            "criteria": {
                "C1_gpu_render_inflated": {
                    "fired": bool(gpu_render) and max(r["delta_pct"] for r in gpu_render) >= INFLATION_INVALIDATE_PCT,
                    "max_delta_pct": max((r["delta_pct"] for r in gpu_render), default=None),
                    "min_delta_pct": min((r["delta_pct"] for r in gpu_render), default=None),
                    "threshold_pct": INFLATION_INVALIDATE_PCT,
                },
                "C2_physics_unchanged": {
                    "fired": bool(phys) and max(abs(r["delta_pct"]) for r in phys) < INFLATION_INVALIDATE_PCT,
                    "max_abs_delta_pct": max((abs(r["delta_pct"]) for r in phys), default=None),
                    "rows": phys,
                    "scope": "仅 egl_nvidia 臂（受污染臂自身的对照）",
                    "meaning": ("**同一批 GPU 进程里物理分量不变、只有渲染分量虚高** ⇒ 不是整机变快，"
                                "是渲染在空转"),
                },
                "C3_osmesa_unchanged": {
                    "fired": bool(cpu_render) and max(abs(r["delta_pct"]) for r in cpu_render) < INFLATION_INVALIDATE_PCT,
                    "max_abs_delta_pct": max((abs(r["delta_pct"]) for r in cpu_render), default=None),
                    "meaning": "CPU 臂不受影响 ⇒ 污染是 **GPU 臂特有**（与 RAW_PROBE_INTERFERENCE 一致）",
                },
                "C4_gpu_util_dropped": {
                    "clean_w8_util": util_of(clean, "egl_nvidia", 8),
                    "polluted_w8_util": util_of(pol, "egl_nvidia", 8),
                    "clean_w1_util": util_of(clean, "egl_nvidia", 1),
                    "polluted_w1_util": util_of(pol, "egl_nvidia", 1),
                    "meaning": "'更快'的那轮 GPU 占用反而更低 ⇒ 渲染没真在算（旁证，非独立判据）",
                },
                "C5_osmesa_physics_noise": {
                    "rows": phys_cpu,
                    "max_abs_delta_pct": max((abs(r["delta_pct"]) for r in phys_cpu), default=None),
                    "meaning": ("**附带观察（非作废判据）**：osmesa 臂的 `physics_only` 跨轮摆动可达 ±41%，"
                                "远大于 GPU 臂的 ±4%。原因是 CPU 侧共租（本机 loadavg≈38、cgroup 12 核），"
                                "而 osmesa 的渲染线程本身也在抢 CPU。⇒ 引用 osmesa 的**物理**分量时必须带"
                                "轮次与 loadavg；osmesa 的**渲染**分量则稳定（见 C3，≤±12%）。"),
                },
            },
        })

    doc = {
        "artifact": "INVALIDATED_RUNS.json",
        "agent": "E",
        "task": "E3-2/3/4 口径更正：点名作废受 raw-probe 污染的产物",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "generator": "scripts/e_invalidate_runs.py",
        "generator_sha256_12": ev.sha256_of(str(Path(__file__)))[:12],
        "self_report": ("**E 自报测量事故**：本线自己写的探针污染了自己两轮产物。"
                        "根因、机理、修复与判据见同目录 `RAW_PROBE_INTERFERENCE.json`；"
                        "本文件只负责点名'哪些数字不能用、用什么替代'。"),
        "clean_reference_round": {
            "file": args.clean,
            "sha256_12": (ev.sha256_of(str(clean_path)) or "")[:12],
            "timestamp": clean.get("timestamp"),
            "why_valid": "该轮 `e_mainline_render_calib.py` **尚未加入**裸 mujoco 探针 ⇒ GPU 数字未受污染",
            "known_gap": ("该轮早于 `label_integrity` / `gl_identity_probe` / 渲染双闸的引入 ⇒ "
                          "**缺批级 GL 标签实证与渲染健康闸**。数字可用，但证据链弱于后续轮；"
                          "权威口径以修复后重跑的轮次为准。"),
        },
        "invalidated": [],
        "comparison": comparison,
        "boundary_guard": ep.boundary_guard(),
        "load": ev.cpu_stat(),
    }

    for c in comparison:
        if "criteria" not in c:
            continue
        k = c["criteria"]
        fired = [n for n in ("C1_gpu_render_inflated", "C2_physics_unchanged", "C3_osmesa_unchanged")
                 if k[n]["fired"]]
        if k["C1_gpu_render_inflated"]["fired"]:
            doc["invalidated"].append({
                "file": c["file"],
                "scope": "**仅 GPU 臂（egl_nvidia）的渲染类分量数字作废**",
                "still_valid": ("osmesa 臂数字仍有效（C3 实测未受影响）；`physics_only` 仍有效（C2）；"
                                "`images_at_reset_w0` 仍有效（探针在其之后才跑）"),
                "invalid_components": RENDER_COMPS,
                "criteria_fired": fired,
                "max_gpu_render_inflation_pct": k["C1_gpu_render_inflated"]["max_delta_pct"],
                "reason": ("被测 env 同进程内的裸 `mujoco.Renderer` 探针（raw_after 顺序）使 GPU 渲染退化，"
                           "渲染吞吐虚高；同轮 `physics_only` 与 osmesa 臂不变 ⇒ 排除'整机变快'"),
                "extra_defect": (None if not c.get("cotenant_blocked") else
                                 "另外：文件名里的 `proxy_a2` 是**误标**（假体从未启动），"
                                 "真实共租方见 COTENANT_CORRECTION.json"),
                "replacement": "见 `replacement_authority` 字段",
            })

    doc["replacement_authority"] = {
        "rule": ("权威 GPU 数字 = **修复后重跑**且满足 `all_ok` + `render_health_all_ok`"
                 "（liveness+fidelity）+ `label_integrity_ok` + `cotenant_actual` 为空（独占卡）的轮次；"
                 "在 `build_sweep` 里不满足即进 `_excluded_batches`，**不静默丢弃**。"),
        "how_to_verify": ("打开对应 `summary_*.json`，逐批核对 `render_health_all_ok` / "
                          "`label_integrity_ok` / `gl_identity_probe_ok` / "
                          "`cotenant_actual.compute_procs_observed_during_batch` 是否为空"),
    }
    doc["cross_line_note"] = {
        "a2_is_safe": ("A2 `scripts/a2_egl_latency_remeasure.py` 的裸 Renderer 探针在 `make_env` **之前**"
                       "（`:702` vs `:761`/`:771`）⇒ 属 `raw_first`，实测无害；"
                       "`gl_identity_after_dm_render`（`:195`）只调 `glGetString`、不建 Renderer ⇒ 亦安全。"),
        "discipline_proposal": ("建议 D 立为全线纪律：**不得在被测 env 同进程、且已发生过 dm_control 渲染之后**"
                               "创建/关闭裸 `mujoco.Renderer`；需要 GL 身份就另起独立子进程。"),
    }

    path = out_dir / "INVALIDATED_RUNS.json"
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"artifact": str(path),
                      "n_invalidated": len(doc["invalidated"]),
                      "invalidated_files": [i["file"] for i in doc["invalidated"]],
                      "criteria_summary": [{ "file": c.get("file"),
                                             **{k: v.get("fired") for k, v in (c.get("criteria") or {}).items()
                                                if isinstance(v, dict) and "fired" in v}}
                                           for c in comparison]},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
