#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""B2 · 裁定 85.5（§18.5）replay 闸**三条牙**的汇总验收件（一处可核，不叫 D 翻四份产物）。

裁定 85.5 把 replay 闸的硬判据砍到只剩一条：**状态逐位相等**；三相机像素一律**只登记不判红**
（新红线 `render_bitwise_equality_ban_on_egl`）。D 同时要求「三条牙随改判一起交」：

  牙① 绿证人：干净重放 ⇒ 绿。
  牙② 必红　：篡改任一维状态 **1 LSB** ⇒ 红。
  牙③ 专属牙：**篡改像素但保留状态 ⇒ 仍绿** —— 缺它就无法证明「像素已降级」。

本脚本**不重跑任何东西**，只读四份已落盘产物，逐条把「D 的要求 / 实测 / 判定」并排写出来，
并给每份源产物记 `(行数, sha256-12, mtime)`（裁定 64：引用带文件身份；裁定 78.11：落笔时刻重读）。
**判定按机器读的字段**，不采信任何 `summary` 文案：
  牙① `gates.verdict=="PASS"` 且 `n_red==0` 且 `n_unjudged==0` 且 `gates.ok is True`；
  牙② `mutation_verdict.tooth_verified is True` 且 `observed_red_ids==["G4_..."]` 且 `missed_red==[]`；
  牙③ `must_stay_green is True` 且 `stay_green_observed is True` 且 `n_red==0`
       且 **注入确实发生了**（`mutation_injected=true` 的行存在，且它 `exceeded_ruling_83_4_tolerance` 非空）
       —— 最后这半条是本脚本自己加的：一颗"没注入却绿"的牙等于没牙。

用法
----
    /root/venvs/rlrobot/bin/python scripts/b2_replay_teeth_verdict.py
    /root/venvs/rlrobot/bin/python scripts/b2_replay_teeth_verdict.py --run-root runs/vla/b2_sim_demo_bidir_20260930
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
CST = timezone(timedelta(hours=8))
G4_ID = "G4_replay_reproduces_bitwise"
G4B_PREFIX = "G4b"


def now_iso() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


def sha12(p: Path) -> Optional[str]:
    try:
        return hashlib.sha256(Path(p).read_bytes()).hexdigest()[:12]
    except OSError:
        return None


def ident(p: Path) -> dict:
    st = None
    try:
        st = p.stat()
    except OSError:
        pass
    lines = None
    try:
        lines = len(p.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        pass
    return {"path": str(p.relative_to(ROOT)) if p.is_absolute() and str(p).startswith(str(ROOT))
            else str(p),
            "exists": p.exists(), "sha256_12": sha12(p), "bytes": st.st_size if st else None,
            "lines": lines,
            "mtime": (datetime.fromtimestamp(st.st_mtime, CST).isoformat(timespec="seconds")
                      if st else None)}


def load(p: Path) -> Optional[Any]:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def gates_of(manifest: dict) -> dict:
    g = manifest.get("gates")
    return g if isinstance(g, dict) else {}


def checks_of(doc: dict) -> List[dict]:
    """两种产物形态都要吃：`demo_manifest.json` 的 `gates` 是 **dict**（带 `checks`），
    `mutation_verdict_*.json` 的 `gates` 直接就是 **checks 列表**。不兼容就会 AttributeError。"""
    g = doc.get("gates")
    if isinstance(g, list):
        return [c for c in g if isinstance(c, dict)]
    if isinstance(g, dict):
        return [c for c in (g.get("checks") or []) if isinstance(c, dict)]
    return []


def check_by_prefix(doc: dict, prefix: str) -> Optional[dict]:
    for c in checks_of(doc):
        if str(c.get("id", "")).startswith(prefix):
            return c
    return None


def injected_rows(manifest: dict) -> List[dict]:
    c = check_by_prefix(manifest, G4B_PREFIX) or {}
    obs = c.get("observed") or {}
    return [r for r in (obs.get("rows") or []) if r.get("mutation_injected")]


def tooth1(manifest: Optional[dict]) -> dict:
    req = "干净重放 ⇒ 绿（裁定 85.5 牙①）"
    if not manifest:
        return {"tooth": "①绿证人", "required": req, "status": "UNJUDGED",
                "reason": "baseline manifest 读不到"}
    g = gates_of(manifest)
    ok = (g.get("verdict") == "PASS" and g.get("n_red") == 0 and g.get("n_unjudged") == 0
          and g.get("ok") is True)
    return {"tooth": "①绿证人（clean replay ⇒ green）", "required": req,
            "status": "PASS" if ok else "RED",
            "observed": {"verdict": g.get("verdict"), "n_checks": g.get("n_checks"),
                         "n_red": g.get("n_red"), "n_warn": g.get("n_warn"),
                         "n_a": g.get("n_a"), "n_unjudged": g.get("n_unjudged"),
                         "ok": g.get("ok"), "red_ids": g.get("red_ids"),
                         "pixel_judges_red": g.get("pixel_judges_red"),
                         "g4_status": ((check_by_prefix(manifest, G4_ID) or {}).get("status")),
                         "cotenant_contaminated":
                             (manifest.get("cotenant_evidence") or {}).get("contaminated_by_cotenant"),
                         "renderer_class": (manifest.get("gl_identity") or {}).get("renderer_class")},
            "red_when": "verdict!=PASS / n_red>0 / n_unjudged>0 / gates.ok!=true"}


def tooth2(mv: Optional[dict]) -> dict:
    req = "篡改任一维状态 **1 LSB** ⇒ G4 必须红（裁定 85.5 牙②）"
    if not mv:
        return {"tooth": "②状态1LSB必红", "required": req, "status": "UNJUDGED",
                "reason": "mutation_verdict 读不到"}
    ok = (mv.get("tooth_verified") is True and mv.get("observed_red_ids") == [G4_ID]
          and mv.get("missed_red") == [] and mv.get("n_red") == 1)
    return {"tooth": "②状态 1 LSB ⇒ 必红", "required": req,
            "status": "PASS" if ok else "RED",
            "observed": {"mutation": mv.get("mutation"),
                         "expected_must_go_red": mv.get("expected_must_go_red"),
                         "observed_red_ids": mv.get("observed_red_ids"),
                         "missed_red": mv.get("missed_red"),
                         "extra_red_beyond_expected": mv.get("extra_red_beyond_expected"),
                         "all_expected_red_caught": mv.get("all_expected_red_caught"),
                         "tooth_verified": mv.get("tooth_verified"), "n_red": mv.get("n_red"),
                         "verdict": mv.get("verdict"),
                         "perturbation_how": _perturb(mv)},
            "red_when": "tooth_verified!=true / observed_red_ids!=[G4] / missed_red 非空 / n_red!=1"}


def _perturb(mv: dict) -> Optional[dict]:
    """扰动的**可核痕迹**：mutation_verdict 只带 gates ⇒ 从 G4 的 violations 原文取。

    为什么要它：牙②若只报「G4 红了」，无法区分"被 1 ULP 扰动咬红"与"因为别的原因红"。
    violations 原文里带着 `max_abs_diff`（1 ULP ≈ 1e-16 量级）⇒ 红的**原因**可核。
    """
    for c in (mv.get("gates") or []):
        if c.get("id") == G4_ID:
            obs = c.get("observed") or {}
            return {"violations": obs.get("violations"),
                    "per_episode_bitwise": [{k: r.get(k) for k in
                                             ("ep", "norender_vs_expert", "recorded_vs_norender",
                                              "recorded_vs_expert")}
                                            for r in (obs.get("per_episode") or [])]}
    return None


def tooth3(mv: Optional[dict]) -> dict:
    req = ("**篡改像素但保留状态 ⇒ 仍绿**（裁定 85.5 牙③，本裁定专属：缺它则「像素已降级」"
           "无法被证明）")
    if not mv:
        return {"tooth": "③只改像素必仍绿", "required": req, "status": "UNJUDGED",
                "reason": "mutation_verdict 读不到"}
    inj = injected_rows(mv)
    inj_exceeded = [r for r in inj if r.get("exceeded_ruling_83_4_tolerance")]
    stayed_green = (mv.get("must_stay_green") is True and mv.get("stay_green_observed") is True
                    and mv.get("n_red") == 0 and mv.get("observed_red_ids") == []
                    and mv.get("verdict") == "PASS")
    injection_really_happened = bool(inj_exceeded)
    ok = bool(stayed_green and injection_really_happened)
    g4b = check_by_prefix(mv, G4B_PREFIX) or {}
    obs4b = g4b.get("observed") or {}
    return {"tooth": "③只改像素、状态不动 ⇒ 必须仍绿", "required": req,
            "status": "PASS" if ok else "RED",
            "observed": {
                "must_stay_green": mv.get("must_stay_green"),
                "stay_green_observed": mv.get("stay_green_observed"),
                "tooth_verified": mv.get("tooth_verified"),
                "n_red": mv.get("n_red"), "verdict": mv.get("verdict"),
                "observed_red_ids": mv.get("observed_red_ids"),
                "injection_really_happened": injection_really_happened,
                "injected_rows": [{k: r.get(k) for k in
                                   ("ep", "slot", "camera", "max_abs_diff", "frac_diff_px",
                                    "mean_abs_diff", "within_ruling_83_4_tolerance",
                                    "exceeded_ruling_83_4_tolerance", "exceeded_register_band",
                                    "register_band_e_reps5")} for r in inj_exceeded],
                "g4b_mode": obs4b.get("mode"),
                "g4b_status": g4b.get("status"),
                "g4b_blocking": g4b.get("blocking"),
                "pixel_judges_red": obs4b.get("pixel_judges_red"),
                "would_have_been_red_under_ruling_17_6":
                    obs4b.get("would_have_been_red_under_ruling_17_6"),
                "counterfactual_note": ("`would_have_been_red_under_ruling_17_6` 非空 = 机器现算出"
                                        "『按 §17-6 的过渡期口径这批必红』，而按裁定 85.5 它 n_red=0 "
                                        "⇒ 降级**确实生效**，不是『因为闸根本没看像素』")},
            "unjudged_when": "读不到产物 ⇒ UNJUDGED（不当作通过）",
            "red_when": ("stay_green_observed!=true / n_red>0 / verdict!=PASS，"
                         "**或注入根本没发生**（`injected_rows` 里没有超 83.4 容差的行 ⇒ 牙是空的）")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run-root", default="runs/vla/b2_sim_demo_bidir_20260930")
    ap.add_argument("--baseline", default="teeth1_green_witness")
    ap.add_argument("--mv-state", default="mutation_verdict_replay-state-1lsb.json")
    ap.add_argument("--mv-pixel", default="mutation_verdict_replay-image-pixel-only.json")
    ap.add_argument("--detector-teeth", default="cotenant_detector_teeth.json")
    ap.add_argument("--out", default="replay_teeth_ruling_85_5.json")
    a = ap.parse_args()

    rr = ROOT / a.run_root
    base_p = rr / a.baseline / "demo_manifest.json"
    mvs_p = rr / a.mv_state
    mvp_p = rr / a.mv_pixel
    det_p = rr / a.detector_teeth
    base, mvs, mvp, det = load(base_p), load(mvs_p), load(mvp_p), load(det_p)

    teeth = [tooth1(base), tooth2(mvs), tooth3(mvp)]
    n_pass = sum(1 for t in teeth if t["status"] == "PASS")
    n_red = sum(1 for t in teeth if t["status"] == "RED")
    n_unj = sum(1 for t in teeth if t["status"] == "UNJUDGED")
    det_ok = bool(det and det.get("ok") is True and det.get("n_teeth") == det.get("n_pass"))
    doc = {
        "artifact": "b2_replay_teeth_verdict",
        "generated_at": now_iso(),
        "generator": "scripts/b2_replay_teeth_verdict.py",
        "generator_sha256_12": sha12(HERE),
        "ruling": ("裁定 85.5 / d_handoff_to_b2 §18.5：replay 闸**硬判据只剩「状态逐位」**；"
                   "三相机像素一律只登记不判红；新红线 `render_bitwise_equality_ban_on_egl`"),
        "supersedes": ("§17-6 / 裁定 82⑤-3 / 83.4 的过渡期口径（状态逐位 + angle 逐位 + wrist 容差判红）"),
        "judged_by": "**机器读字段**，不采信任何 summary 文案",
        "sources": {"baseline_manifest": ident(base_p), "mutation_verdict_state_1lsb": ident(mvs_p),
                    "mutation_verdict_pixel_only": ident(mvp_p),
                    "cotenant_detector_teeth": ident(det_p),
                    "generator_under_test": ident(ROOT / "scripts" / "b2_s1_generate_dataset.py"),
                    "e_measurement_basis": ident(ROOT / "runs" / "infra" /
                                                 "e_mainline_calib_20260929" /
                                                 "RENDER_DETERMINISM_REPS5.json")},
        "teeth": teeth,
        "n_teeth": len(teeth), "n_pass": n_pass, "n_red": n_red, "n_unjudged": n_unj,
        "cotenant_detector_teeth": {
            "included_because": ("裁定 85.6-2 的三条牙（探测器三网化）与 85.5 的三条牙（replay 判据）"
                                 "是同一轮改判的两半，放在一处便于 D 一次核完"),
            "ok": det_ok,
            "n_pass": (det or {}).get("n_pass"), "n_red": (det or {}).get("n_red"),
            "n_unjudged": (det or {}).get("n_unjudged"),
            "per_tooth": [{"tooth": t.get("tooth"), "status": t.get("status"),
                           "expect_detected": t.get("expect_detected"),
                           "observed_detected": t.get("observed_detected"),
                           "detected_by": ((t.get("sample") or {}).get("detected_by"))}
                          for t in ((det or {}).get("teeth") or [])]},
        "ok": bool(n_red == 0 and n_unj == 0 and det_ok),
        "status_wording_discipline": "只用 PASS/RED/UNJUDGED/N_A；不用「跑通/学会/达标」",
        "policy_executed": False, "capability_claim": False, "not_a_capability_claim": True,
    }
    out = rr / a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"out": str(out), "n_pass": n_pass, "n_red": n_red, "n_unjudged": n_unj,
                      "cotenant_detector_ok": det_ok, "ok": doc["ok"],
                      "per_tooth": [{"tooth": t["tooth"], "status": t["status"]} for t in teeth]},
                     ensure_ascii=False, indent=1))
    return 0 if doc["ok"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
