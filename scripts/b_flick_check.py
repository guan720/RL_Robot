#!/usr/bin/env python3
"""共用 flick 门禁：对任意 audit_truth*.json 复核「受控抬起」还是「弹射」。

监管 P0 要求 Lift 成功必须是可重复的非零 grasp_verified 且不是 flick，但
scripts/eval_act_lift_truth.py 只记录 max_rise，缺 final_rise / held / phase_at_end，
因此对弹射是盲的。本脚本从已有逐局 JSON 事后判定，不修改任何评测脚本或 checkpoint。

判据（三条同时满足才算受控成功 controlled_success）：
  1. success_raw 且 grasp_verified；
  2. max_rise <= --rise-cap（默认 0.15 m；scripted base 实测 0.076 m）；
  3. 局末仍处于夹持/保持：phase_trace 末元素属于 --hold-phases（默认 hold/done/grasp），
     若 JSON 里带 final_rise 则额外要求 final_rise >= --final-rise（默认 0.04 m）。
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

HOLD_OK = {"hold", "done", "grasp"}


def judge(path, rise_cap, final_rise_min, hold_phases):
    d = json.loads(Path(path).read_text())
    rows = d.get("rows", [])
    n = len(rows)
    raw = sum(bool(r.get("success_raw", r.get("success"))) for r in rows)
    gv = sum(bool(r.get("grasp_verified")) for r in rows)
    sgv = sum(bool(r.get("success_grasp_verified")) for r in rows)
    controlled, flick, per = 0, 0, []
    for r in rows:
        ok_raw = bool(r.get("success_raw", r.get("success")))
        if not ok_raw:
            continue
        rise = float(r.get("max_rise", 0.0))
        pt = r.get("phase_trace") or []
        end_phase = r.get("phase_at_end") or (pt[-1] if pt else "unknown")
        fin = r.get("final_rise")
        c_rise = rise <= rise_cap
        c_end = end_phase in hold_phases
        c_fin = True if fin is None else float(fin) >= final_rise_min
        ok = c_rise and c_end and c_fin and bool(r.get("grasp_verified"))
        controlled += int(ok); flick += int(not ok)
        per.append({"seed": r.get("seed"), "max_rise": round(rise, 4),
                    "final_rise": (round(float(fin), 4) if fin is not None else None),
                    "end_phase": end_phase, "controlled": ok,
                    "failed_checks": [n2 for n2, c in (("rise_cap", c_rise), ("end_phase", c_end),
                                                        ("final_rise", c_fin)) if not c]})
    return {"file": str(path), "controller": d.get("controller"), "episodes": n,
            "success_raw": raw, "grasp_verified": gv, "success_grasp_verified": sgv,
            "controlled_success": controlled, "flick_success": flick,
            "flick_frac_of_success": (flick / raw) if raw else None,
            "mean_max_rise": d.get("mean_max_rise"),
            "has_final_rise_field": any("final_rise" in r for r in rows),
            "per_success": per}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--rise-cap", type=float, default=0.15)
    ap.add_argument("--final-rise", type=float, default=0.04)
    ap.add_argument("--hold-phases", default="hold,done,grasp")
    ap.add_argument("--json-out", default=None)
    a = ap.parse_args()
    hold = set(a.hold_phases.split(","))
    out = [judge(p, a.rise_cap, a.final_rise, hold) for p in a.paths]
    hdr = "%-52s %5s %5s %5s %6s %6s %7s %s"
    print(hdr % ("file", "raw", "grip", "sgv", "ctrl", "flick", "flick%", "final_rise?"))
    for r in out:
        print(hdr % (Path(r["file"]).parent.name[:50], r["success_raw"], r["grasp_verified"],
                     r["success_grasp_verified"], r["controlled_success"], r["flick_success"],
                     ("n/a" if r["flick_frac_of_success"] is None else f"{r['flick_frac_of_success']*100:.0f}%"),
                     ("yes" if r["has_final_rise_field"] else "NO-blind")))
        for e in r["per_success"]:
            flag = "OK " if e["controlled"] else "FLICK"
            print("      %s seed=%s max_rise=%.3f final_rise=%s end=%s %s"
                  % (flag, e["seed"], e["max_rise"], e["final_rise"], e["end_phase"],
                     ("(failed: " + ",".join(e["failed_checks"]) + ")") if e["failed_checks"] else ""))
    if a.json_out:
        Path(a.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json_out).write_text(json.dumps(out, indent=2))
        print("\nwrote", a.json_out)
    bad = [r["file"] for r in out if not r["has_final_rise_field"]]
    if bad:
        print("\n[warn] 以下评测产物缺 final_rise 字段，flick 判定只能靠 phase_trace 兜底：", file=sys.stderr)
        for b in bad:
            print("       ", b, file=sys.stderr)


if __name__ == "__main__":
    main()
