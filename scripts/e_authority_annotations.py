#!/usr/bin/env python
"""裁定 92.1 的**两个机器可读标注**的生成器（T-E-9-1）。

为什么要有这个脚本而不是手写 JSON：裁定 92.3 把 `prose_identity_must_be_verifiable_against_a_saved_artifact`
升为**红线级**，并加两条硬要求 —— **(i) 身份串必须由工具在落笔时刻生成，人不碰**；
(ii) 工具必须同时落算法名与本仓可引用口径。本件里出现的每一个 sha / 行数 / 退出码 / 像素抖动值
都由本脚本**从被标注的那件产物里现场读出来**，E 一个数字都不手抄。

**为什么是旁证件而不是改 v3**：裁定 92.2 明令「v3 manifest 原字节保留不得覆写」，
且 v3 是已被 D 验收（裁定 89.5-1 / 92.1）的**唯一权威冷启动证据** ⇒ 标注必须**挂在旁边**，
不得动 v3 一个字节。这与 `invalidation_never_renames_the_original` 同族。

**本件标注的三个 scope（不要混）**：
  A `coldstart_evidence_v3.tooth_relink.exit_code` —— 裁定 **92.1(a)/(b)** 点名的那一维。
    v3 记的 `0` 是**修法前 `.sh` 行为下的历史值**；当前期望值是 **5**。
  B `render_determinism.team_480x640` —— D 的 T-E-9.1 交接单里描述的相机槽 `{top,left_wrist,right_wrist}`
    属于**这一轮**（T-E-DET-480）。
  C `render_determinism.pi05_collect_224sq` —— `0.052%` 这个数**属于这一轮**（相机集是 `{angle,left_wrist,right_wrist}`）。
  ⇒ **B 与 C 是两轮不同口径**（分辨率不同、相机集不同），交接单把它们并在了一句里；
     本件按裁定 71 `caliber_transplant_ban` **分开登记、各自带出处**，不选一个也不平均。

退出码：0 = 三个 scope 全部机器取到值且内部一致；1 = 任一 scope 取不到值或与预期不符；
3 = 目标已存在（拒绝覆写）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CD = REPO / "runs/infra/e_egl_coldstart_20260930"
CAL = REPO / "runs/infra/e_mainline_calib_20260929"
DEFAULT_OUT = CD / "COLDSTART_EVIDENCE_v3.ANNOTATIONS.json"

# 裁定 94.9-5（缺陷类 ⑳ `preregistered_condition_without_a_consumer`）：
# 预登记的可推翻条件**必须写明谁在什么时刻核它**，否则它等于没写。
CHECKED_BY = ("E（本旁证件的维护线）。**核它的人不是写下它的人就够了** —— D 按 §94.9-5 抽查 "
              "`checked_by`/`checked_when` 是否真被填、以及到点有没有真被跑")
CHECKED_WHEN = ("每次有人**重导 v3**（即裁定 92.1 的可推翻条件被触发的那一刻）之后的第一个动作；"
                "以及每轮 E 开工时对 A2 的 S4b 产物做一次 `renderer_class` 搭车核对（T-E-10）")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ident(p: Path) -> dict:
    """身份三元组 + 两种算法（裁定 92.3 的全仓最低标准）。`n_lines` = `wc -l` 口径。"""
    b = p.read_bytes()
    return {"path": str(p.relative_to(REPO)), "n_lines": b.count(b"\n"),
            "n_lines_splitlines": len(b.splitlines()), "bytes": len(b),
            "ends_with_newline": b.endswith(b"\n"),
            "sha256_12": hashlib.sha256(b).hexdigest()[:12],
            "sha1_12": hashlib.sha1(b).hexdigest()[:12],
            "mtime": time.strftime("%Y-%m-%dT%H:%M:%S %Z", time.localtime(p.stat().st_mtime))}


def per_cam_worst(d: dict, backend: str) -> dict:
    out = {}
    for cam, c in ((d.get("per_backend", {}).get(backend) or {}).get("cams") or {}).items():
        out[cam] = {"bitwise_deterministic_in_process_all_reps": c.get("bitwise_deterministic_in_process_all_reps"),
                    "cross_process_same_sha": c.get("cross_process_same_sha"),
                    "max_abs_diff_worst": c.get("max_abs_diff_worst"),
                    "max_frac_diff_px_worst": c.get("max_frac_diff_px_worst"),
                    "max_frac_diff_px_worst_percent": (None if c.get("max_frac_diff_px_worst") is None
                                                       else round(c["max_frac_diff_px_worst"] * 100, 6)),
                    "n_unique_shas_per_rep": c.get("n_unique_shas_per_rep")}
    worst = [v["max_frac_diff_px_worst"] for v in out.values() if v["max_frac_diff_px_worst"] is not None]
    return {"per_camera": out,
            "n_cams": len(out),
            "worst_frac_diff_px": max(worst) if worst else None,
            "worst_frac_diff_px_percent": (round(max(worst) * 100, 6) if worst else None),
            "worst_max_abs_diff": (max(v["max_abs_diff_worst"] for v in out.values()
                                       if v["max_abs_diff_worst"] is not None) if worst else None),
            "all_bitwise": (all(v["bitwise_deterministic_in_process_all_reps"] is True
                                for v in out.values()) if out else None),
            "empty_set_note": ("相机集为空 ⇒ 上面三个聚合值必须是 null（裁定 88.3-2），不是 0"
                               if not out else f"聚合是在 {len(out)} 个非空相机槽上做的")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()
    out = Path(args.out)
    if out.exists():
        print(json.dumps({"verdict": "REFUSE", "reason": f"目标已存在，拒绝覆写（裁定 82 §2-4 / 83.5）: {out}",
                          "existing_sha256_12": sha256_file(out)[:12]}, ensure_ascii=False))
        return 3

    v3p = CD / "COLDSTART_EVIDENCE_v3.json"
    rtp = CD / "COLDSTART_EVIDENCE_relinktooth_exit5.json"
    r2p = CAL / "RENDER_DETERMINISM_TEAM480x640_EGL_REPS5_r2.json"
    osp = CAL / "RENDER_DETERMINISM_TEAM480x640_OSMESA_REPS5.json"
    p224 = CAL / "RENDER_DETERMINISM_REPS5.json"
    shp = REPO / "scripts/e_coldstart_gpu_render.sh"
    v4p = CD / "PERSIST_MANIFEST_v4.json"
    missing = [str(p) for p in (v3p, rtp, r2p, osp, p224, shp, v4p) if not p.is_file()]
    if missing:
        print(json.dumps({"verdict": "not_measured", "reason": "被标注的产物缺失 ⇒ 不给通过形状的读数",
                          "missing": missing}, ensure_ascii=False))
        return 1

    v3 = json.loads(v3p.read_text()); rt = json.loads(rtp.read_text())
    r2 = json.loads(r2p.read_text()); os_ = json.loads(osp.read_text()); d224 = json.loads(p224.read_text())
    sh_text = shp.read_text()

    hist_exit = v3["tooth_relink"]["exit_code"]            # 实测：从 v3 里读，不手抄
    cur_exit = rt["tooth_relink"]["exit_code"]             # 实测：从 exit5 牙产物里读
    exit5_line = next((i + 1 for i, ln in enumerate(sh_text.splitlines())
                       if ln.strip() == "exit 5"), None)   # 实测：当前 .sh 里那一行的行号

    b = per_cam_worst(r2, "egl_nvidia")
    c = per_cam_worst(d224, "egl_nvidia")
    ctrl = per_cam_worst(os_, "osmesa")

    checks = []

    def chk(name, ok, observed, why):
        checks.append({"check": name, "ok": bool(ok), "observed": observed, "why_it_matters": why})

    chk("v3_tooth_relink_exit_code_is_historical_zero", hist_exit == 0, f"v3 tooth_relink.exit_code={hist_exit}",
        "标注 (a) 的前提：v3 记的确实是 0，否则这条标注无的放矢")
    chk("current_expectation_is_5", cur_exit == 5, f"relinktooth 牙产物 exit_code={cur_exit}",
        "标注 (a) 的后件：当前期望值确实是 5（实测，不是散文断言）")
    chk("current_sh_has_exit_5_branch", exit5_line is not None, f"scripts/e_coldstart_gpu_render.sh:{exit5_line}",
        "5 这个码在当前 .sh 里真有落地行（否则「当前期望 5」无从复现）")
    chk("v3_authority_intact", v3["delivery_status"] == "COLDSTART_VERIFIED" and v3["all_teeth_proven"] is True,
        f"delivery_status={v3['delivery_status']} all_teeth_proven={v3['all_teeth_proven']} stages_skipped={v3['stages_skipped']}",
        "标注不改权威：v3 仍是 COLDSTART_VERIFIED（裁定 92.1）")
    chk("team480_egl_all_three_slots_non_bitwise",
        b["n_cams"] == 3 and b["all_bitwise"] is False, f"n_cams={b['n_cams']} all_bitwise={b['all_bitwise']}",
        "scope B 的形状与交接单描述一致（三个槽、全不逐位）")
    chk("team480_worst_frac_is_0p0225_not_0p052",
        b["worst_frac_diff_px"] == 0.000225, f"worst_frac_diff_px={b['worst_frac_diff_px']}",
        "**交接单的 0.052% 不属于这一轮**；本轮（480×640）实测最差 = 0.000225 = 0.0225%")
    chk("pi05_224_worst_frac_is_0p000518",
        c["worst_frac_diff_px"] == 0.000518, f"worst_frac_diff_px={c['worst_frac_diff_px']}",
        "0.052% = 0.000518 **属于 224² 采集臂那一轮**（相机集 angle/left_wrist/right_wrist）")
    chk("osmesa_control_all_bitwise",
        ctrl["all_bitwise"] is True and ctrl["worst_max_abs_diff"] == 0,
        f"n_cams={ctrl['n_cams']} all_bitwise={ctrl['all_bitwise']} worst_max_abs_diff={ctrl['worst_max_abs_diff']}",
        "对照后端必须逐位（否则「egl 不逐位」就没有对照，结论不成立）")

    failed = [x["check"] for x in checks if not x["ok"]]

    payload = {
        "artifact": str(out.relative_to(REPO)), "agent": "E",
        "task": "T-E-9-1（裁定 92.1 的两个必须落的条件 (a)(b)，**机器可读**）",
        "ruling": "裁定 92.1（`work/decisions/decisions_20260929.md:3164`）+ D 的 T-E-9.1（`rl_harness_supervision/d_handoff_to_e_20260930.md`）",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S %Z"),
        "generator": {"script": str(Path(__file__).resolve().relative_to(REPO)),
                      "sha256_12": sha256_file(Path(__file__).resolve())[:12],
                      "n_lines": Path(__file__).read_bytes().count(b"\n"),
                      "why": "裁定 92.3(i)：身份串必须由工具在落笔时刻生成，人不碰"},
        "citation_algo": "sha256[:12]",
        "line_count_convention": "`n_lines` = 换行符个数（= `wc -l`）；另给 `n_lines_splitlines` 与 `ends_with_newline`",
        "annotation_kind": "sidecar（**旁证件**）",
        "annotated_artifact": ident(v3p),
        "annotated_artifact_bytes_untouched": {
            "claim": "本件**不修改** v3 一个字节；v3 仍是唯一权威冷启动证据",
            "v3_identity_at_annotation_time": ident(v3p),
            "before_image": "runs/infra/e_restart_readiness_20260930/before_images/round1_prefix_v4/COLDSTART_EVIDENCE_v3.json.beforeV4",
            "before_image_sha256_12": sha256_file(REPO / "runs/infra/e_restart_readiness_20260930/before_images/round1_prefix_v4/COLDSTART_EVIDENCE_v3.json.beforeV4")[:12],
            "bytes_identical_to_before_image": (sha256_file(v3p) == sha256_file(
                REPO / "runs/infra/e_restart_readiness_20260930/before_images/round1_prefix_v4/COLDSTART_EVIDENCE_v3.json.beforeV4"))},
        "why_sidecar_not_inplace": ("裁定 92.2「v3 原字节保留不得覆写」+ v3 已被 D 验收（89.5-1 / 92.1）⇒ "
                                    "标注必须挂在旁边。与 `invalidation_never_renames_the_original` 同族。"),

        "annotation_a_tooth_relink_exit_code_is_historical": {
            "ruling": "92.1(a)",
            "field_in_v3": "tooth_relink.exit_code",
            "historical_value_in_v3": hist_exit,
            "current_expected_value": cur_exit,
            "why_they_differ": ("v3 落盘（03:02:38）时 `scripts/e_coldstart_gpu_render.sh` 的 `E_SKIP_GPU=1` 分支还 `exit 0`；"
                                "§E12.10 查出那是**退出码层面的假绿**（0 会被只读 `$?` 的调用方当成「GPU 渲染可用」），"
                                "根因修把它改成 **`exit 5`**（精确等值断言 `exit_partial_5`，**不是放宽**）。"
                                "v3 的 `baseline`/`mutant` 两臂都不走 `E_SKIP_GPU` 分支（E 已逐臂核过、D 已复核），"
                                "⇒ **只有 `tooth_relink.exit_code` 这一维受影响**。"),
            "current_sh_exit5_line": exit5_line,
            "measured_from": {"v3": ident(v3p), "exit5_tooth_artifact": ident(rtp), "current_sh": ident(shp)},
            "machine_readable_warning": ("**将来任何人「复现 v3」都会得到 `exit_code=5` 而不是 0。这不是 v3 错了、"
                                         "也不是复现失败，而是脚本行为按裁定改过。**若不落本字段，"
                                         "复现者会得到一个无法解释的不一致（D 在 92.1(a) 里点名的就是这个后果）。"),
            "does_not_downgrade_v3": True,
        },

        "reproduction_caliber_gap": {
            "ruling": "92.1(b) + D 的 T-E-9.1",
            "semantics": ("**三态纪律用在可复现性上**：不可逐位复现 ≠ 失效，但必须显式标出，不得留给读者去推"
                          "（与裁定 88.3-1 同族）。本字段按 **scope** 分开登记 —— 因为「哪一维不可逐位复现」"
                          "在两份不同的权威产物上指的是**两件不同的事**，混在一起写会造出一个谁都对不上的口径。"),
            "scope_A_coldstart_evidence_v3": {
                "dimension_not_bitwise_reproducible": "tooth_relink.exit_code",
                "v3_value": hist_exit, "value_current_script_would_produce": cur_exit,
                "reason": "脚本行为按 §E12.10 的根因修改变（`E_SKIP_GPU=1` 分支 `exit 0` → `exit 5`）",
                "all_other_dimensions_unaffected": True,
                "how_other_dimensions_were_checked": ("E 逐臂核过：`baseline` 与 `mutant` 两臂都不经过 `E_SKIP_GPU` 分支，"
                                                      "其断言与退出码未受修法影响（D 在 92.1 里独立复核并接受）"),
                "falsification_condition": ("若任何人重导 v3 时发现 `baseline`/`mutant` 两臂的断言或退出码**也**随修法变了 "
                                            "⇒ 本 scope 的标注不够，**v4 立即升 P0**（裁定 92.1 的可推翻条件，E 按 85.7 重新申报窗口）"),
                "falsification_condition_consumer": {"checked_by": CHECKED_BY, "checked_when": CHECKED_WHEN,
                                                     "ruling": "94.9-5 / 缺陷类 ⑳"},
                "authority_still": "COLDSTART_EVIDENCE_v3.json",
                "coldstart_evidence_v4_needed": False,
                "coldstart_evidence_v4_status": "用户待批 ⑧（裁定 92.1；若用户要求「权威件每个字段都必须由当前版脚本产生」⇒ v4 升 P0）",
            },
            "scope_B_render_determinism_team_480x640": {
                "artifact": ident(r2p),
                "task": "T-E-DET-480（裁定 86.3）· 480×640 团队三槽 · reps=5 · regime=same_state_repeat_render",
                "cam_set": sorted((r2.get("per_backend", {}).get("egl_nvidia") or {}).get("cams", {}).keys()),
                "dimensions_not_bitwise_reproducible": [f"egl_nvidia/{x}" for x in
                                                        sorted((r2.get("per_backend", {}).get("egl_nvidia") or {}).get("cams", {}).keys())],
                "measured": b,
                "control_backend_osmesa": {"artifact": ident(osp), "measured": ctrl,
                                           "role": "对照后端：三相机**全逐位**（进程内 + 跨进程）⇒ 证明「不逐位」是 egl 后端的性质，不是脚本或机器的性质"},
                "hard_rule": "sha / 逐位相等**不能**做渲染保真闸（裁定 85.2-2 红线 `render_bitwise_equality_ban_on_egl`）",
                "falsification_condition": ("若有人拿本 scope 的 `max_abs_diff=1` 当**判红阈值**用（而不是登记带），"
                                            "或把 scope C 的 `0.052%` 搬到 scope B 的相机名上 ⇒ 口径被移植，本标注失效"),
                "falsification_condition_consumer": {"checked_by": CHECKED_BY, "checked_when": CHECKED_WHEN,
                                                     "ruling": "94.9-5 / 缺陷类 ⑳ + 裁定 71 caliber_transplant_ban"},
            },
            "scope_C_render_determinism_pi05_collect_224sq": {
                "artifact": ident(p224),
                "task": "π₀.₅ 采集臂 224² · reps=5（裁定 83.3 / 83.4 的那一轮）",
                "cam_set": sorted((d224.get("per_backend", {}).get("egl_nvidia") or {}).get("cams", {}).keys()),
                "measured": c,
                "note": "**`0.052%`（= 0.000518）这个数属于这一轮**，相机集是 `{angle,left_wrist,right_wrist}`、分辨率 224²",
            },
            "caliber_separation_note": {
                "why_B_and_C_are_separate": ("两轮的**分辨率不同**（480×640 vs 224²）、**相机集不同**"
                                             "（`{top,left_wrist,right_wrist}` vs `{angle,left_wrist,right_wrist}`）⇒ "
                                             "把 C 的最差值安到 B 的相机名上 = 裁定 71 `caliber_transplant_ban` 禁止的动作。"),
                "handoff_wording_observed": ("D 的 T-E-9.1 原文把「`egl_nvidia/{top,left_wrist,right_wrist}`」"
                                             "（= scope B 的相机名）与「`frac_diff_px` 最差 `0.052%`」（= scope C 的值）写在同一句里。"),
                "e_action": ("**不选一个、不平均、不猜 D 想要哪个** —— 两个 scope 各自带出处分开登记，"
                             "并把差异如实报给 D（见 daily_report §E13）。E 不代 D 改交接单。"),
                "measured_both": {"scope_B_worst_frac_diff_px": b["worst_frac_diff_px"],
                                  "scope_B_worst_percent": b["worst_frac_diff_px_percent"],
                                  "scope_C_worst_frac_diff_px": c["worst_frac_diff_px"],
                                  "scope_C_worst_percent": c["worst_frac_diff_px_percent"],
                                  "ratio_C_over_B": (round(c["worst_frac_diff_px"] / b["worst_frac_diff_px"], 4)
                                                     if b["worst_frac_diff_px"] else None)},
            },
        },

        "related_authority_pointers": {
            "coldstart_evidence_authority": {"file": "COLDSTART_EVIDENCE_v3.json", "identity": ident(v3p),
                                             "status": "唯一权威（裁定 92.1：不需要 v4）"},
            "persist_manifest_authority": {"file": "PERSIST_MANIFEST_v4.json", "identity": ident(v4p),
                                           "status": "当前权威持久化清单（裁定 92.2；`supersedes = PERSIST_MANIFEST_v3.json`）",
                                           "note": "**这不是冷启动证据换权威** —— 冷启动证据仍是 v3；换的只是持久化清单"},
            "persist_manifest_v3": {"file": "PERSIST_MANIFEST_v3.json",
                                    "identity": ident(CD / "PERSIST_MANIFEST_v3.json"),
                                    "status": "已被 v4 取代（原字节保留，未覆写）"},
        },
        "self_checks": checks,
        "verdict": "PASS" if not failed else "FAIL",
        "failed_checks": failed,
        "gpu_window_used": False,
        "ruling_94_9_5_self_audit": {
            "requirement": "所有预登记的可推翻条件必须带 `checked_by` + `checked_when`（缺陷类 ⑳）",
            "n_falsification_conditions_in_this_artifact": 2,
            "n_with_consumer": 2,
            "all_have_consumer": True,
            "checked_by": CHECKED_BY, "checked_when": CHECKED_WHEN,
            "note": ("E 名下另有 5 条可推翻条件在 `RESTART_READINESS.json` 的 `falsification_condition` 里，"
                     "已由 `scripts/e_restart_readiness.py` 统一注入 `checked_by`/`checked_when`（该件项 5 有自证行 "
                     "`falsification_conditions_all_have_consumer`）")},
        "loadavg": list(os.getloadavg()),
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"artifact": str(out.relative_to(REPO)), "verdict": payload["verdict"],
                      "failed_checks": failed,
                      "annotation_a": {"historical": hist_exit, "current_expected": cur_exit,
                                       "sh_exit5_line": exit5_line},
                      "scope_B_worst_frac_diff_px": b["worst_frac_diff_px"],
                      "scope_C_worst_frac_diff_px": c["worst_frac_diff_px"],
                      "osmesa_all_bitwise": ctrl["all_bitwise"],
                      "v3_bytes_untouched": payload["annotated_artifact_bytes_untouched"]["bytes_identical_to_before_image"],
                      "loadavg": payload["loadavg"],
                      "exit": 0 if not failed else 1}, ensure_ascii=False, indent=1))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
