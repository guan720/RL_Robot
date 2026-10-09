#!/usr/bin/env python3
"""B 线：门禁阈值 ±0.005 敏感性报告（监管备忘 2026-09-28 §二.B.2 与 §二.A.3 共担项）。

为什么需要：受控成功判据 v1.2 有两个**硬阈值**——
    C5 `final_rise >= FINAL_RISE_MIN`（默认 0.04 m）
    C3 `max_rise  <= RISE_CAP`       （默认 0.15 m）
而实测受控局的 rise 只有 0.0415–0.0466（监管 改判 1 引用的证据），**贴着 0.04 门槛**。
贴着门槛的数字有两种完全不同的含义：
  (a) 策略确实稳定抬过阈值，阈值只是碰巧在下方 -> 结论稳健；
  (b) 阈值稍微一动结论就翻 -> 「受控成功 2/20」是阈值产物，不是能力。
分不清这两者就没法判断 改判 1 的证据等级，所以必须把敏感性量出来。

本脚本是**只读后处理**：对同一批评测产物，在 final_rise × rise_cap 的 ±0.005 网格上
反复调用 `scripts/b_gate_controlled_success.py::judge_file`，报告受控成功数是否变化、
以及哪些 seed 落在边界带里（即「决定敏感性的那几局」）。

判读口径：
  threshold_robust      网格内受控成功数恒定（且 >0）-> 结论不依赖阈值取值
  threshold_sensitive   网格内受控成功数变化 -> 报告时**必须**同时给出阈值与变化范围，
                        不得只写一个数
  not_claimable         该产物 measurement_valid=False（输入契约违例/未验证）->
                        敏感性无意义，先补测量再谈阈值

用法：
    python3 scripts/b_gate_threshold_sensitivity.py <eval.json> [<eval2.json> ...]
    python3 scripts/b_gate_threshold_sensitivity.py --glob 'runs/infra/lerobot_act_env_20260928/official_act_truth20_*gatefields*.json'
    ... --delta 0.005 --json-out runs/infra/b_gate_sensitivity/report.json
"""
from __future__ import annotations
import argparse, glob as globmod, importlib.util, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "b_gate_controlled_success.py"


def load_gate():
    spec = importlib.util.spec_from_file_location("b_gate", str(GATE))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Args:
    """judge_file 只读这三个属性。"""
    def __init__(self, rise_cap, final_rise):
        self.rise_cap = rise_cap
        self.final_rise = final_rise
        self.assist_off = False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--glob", action="append", default=[], help="可重复；对匹配到的文件逐个判定")
    ap.add_argument("--delta", type=float, default=0.005, help="阈值扰动幅度（默认 ±0.005 m）")
    ap.add_argument("--final-rise", type=float, default=0.04)
    ap.add_argument("--rise-cap", type=float, default=0.15)
    ap.add_argument("--json-out", default=str(ROOT / "runs/infra/b_gate_sensitivity/report.json"))
    a = ap.parse_args()

    paths = list(a.paths)
    for g in a.glob:
        paths.extend(sorted(globmod.glob(g)))
    if not paths:
        print("没有输入文件（用位置参数或 --glob）")
        return 2

    gate = load_gate()
    fr_grid = [round(a.final_rise - a.delta, 6), a.final_rise, round(a.final_rise + a.delta, 6)]
    rc_grid = [round(a.rise_cap - a.delta, 6), a.rise_cap, round(a.rise_cap + a.delta, 6)]

    report = {"gate_build": getattr(gate, "GATE_BUILD", None),
              "gate_spec_sha256": getattr(gate, "GATE_SPEC_SHA", None),
              "baseline": {"final_rise": a.final_rise, "rise_cap": a.rise_cap},
              "delta": a.delta, "final_rise_grid": fr_grid, "rise_cap_grid": rc_grid,
              "arms": []}

    print("=" * 108)
    print("门禁阈值敏感性：final_rise ∈ %s × rise_cap ∈ %s（±%.3f m）" % (fr_grid, rc_grid, a.delta))
    print("=" * 108)
    print("%-46s %6s %6s %6s %6s  %-18s %s"
          % ("arm", "base", "min", "max", "spread", "ic_status", "裁定"))
    print("-" * 108)

    for p in paths:
        cells, boundary = {}, []
        for fr in fr_grid:
            for rc in rc_grid:
                r = gate.judge_file(p, Args(rc, fr))
                if "error" in r:
                    cells[(fr, rc)] = {"error": r["error"]}
                    continue
                pi = r["accounts"]["policy_independent"]
                cells[(fr, rc)] = {"controlled": pi["controlled_success"],
                                   "denominator": pi["denominator"],
                                   "gate_pass": r["gate_pass"],
                                   "ic_status": r["input_contract"]["status"],
                                   "insufficient_lift": pi.get("insufficient_lift"),
                                   "over_lift": pi["over_lift"], "flick": pi["flick"]}
                if (fr, rc) == (a.final_rise, a.rise_cap):
                    base_row = r
        vals = [c["controlled"] for c in cells.values() if "controlled" in c]
        if not vals:
            print("%-46s ERROR %s" % (Path(p).name[:46], list(cells.values())[0].get("error")))
            report["arms"].append({"file": str(p), "error": list(cells.values())[0].get("error")})
            continue
        ic = base_row["input_contract"]["status"]
        # 边界带：final_rise 或 max_rise 落在阈值 ±delta 内的局 —— 它们决定敏感性
        for e in base_row["per_episode"]:
            fin, mx = e.get("final_rise"), e.get("max_rise")
            near_c5 = fin is not None and abs(fin - a.final_rise) <= a.delta
            near_c3 = mx is not None and abs(mx - a.rise_cap) <= a.delta
            if near_c5 or near_c3:
                boundary.append({"seed": e["seed"], "verdict": e["verdict"], "final_rise": fin,
                                 "max_rise": mx, "near": ("C5" if near_c5 else "") + ("/C3" if near_c3 else "")})
        spread = max(vals) - min(vals)
        if ic != "verified_ok":
            verdict = "not_claimable（输入契约 %s，先补测量）" % ic
        elif max(vals) == 0:
            verdict = "no_controlled_success（阈值放宽到 +%.3f 仍为 0）" % a.delta
        elif spread == 0:
            verdict = "threshold_robust（%d 局，网格内恒定）" % vals[0]
        else:
            verdict = "threshold_sensitive（%d→%d，报告必须带阈值）" % (min(vals), max(vals))
        name = Path(p).name[:46]
        print("%-46s %6d %6d %6d %6d  %-18s %s"
              % (name, cells[(a.final_rise, a.rise_cap)].get("controlled", -1),
                 min(vals), max(vals), spread, ic, verdict))
        report["arms"].append({
            "file": str(p), "arm": Path(p).stem, "ic_status": ic,
            "measurement_valid": base_row["measurement_valid"],
            "baseline_controlled": cells[(a.final_rise, a.rise_cap)].get("controlled"),
            "denominator": cells[(a.final_rise, a.rise_cap)].get("denominator"),
            "controlled_min": min(vals), "controlled_max": max(vals), "spread": spread,
            "verdict": verdict,
            "grid": {"final_rise=%s|rise_cap=%s" % (fr, rc): c
                     for (fr, rc), c in sorted(cells.items())},
            "boundary_seeds": boundary,
        })
        if boundary:
            for b in boundary[:6]:
                print("      边界局 seed=%-6s %-17s final_rise=%s max_rise=%s  靠近 %s"
                      % (b["seed"], b["verdict"], b["final_rise"], b["max_rise"], b["near"].strip("/")))

    print("=" * 108)
    n_rob = sum(1 for x in report["arms"] if x.get("verdict", "").startswith("threshold_robust"))
    n_sen = sum(1 for x in report["arms"] if x.get("verdict", "").startswith("threshold_sensitive"))
    n_nc = sum(1 for x in report["arms"] if x.get("verdict", "").startswith("not_claimable"))
    print("合计 %d 臂：robust %d / sensitive %d / not_claimable %d / 其他 %d"
          % (len(report["arms"]), n_rob, n_sen, n_nc,
             len(report["arms"]) - n_rob - n_sen - n_nc))
    print("判读：sensitive 臂的成功率**不得**只写一个数；not_claimable 臂先补输入契约再谈阈值。")

    outp = Path(a.json_out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print("写出:", outp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
