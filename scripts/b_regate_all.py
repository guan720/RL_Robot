#!/usr/bin/env python3
"""B 线：一键重判所有留档门禁产物，使其指纹与当前门禁构建一致。

为什么需要这个脚本：产物漂移的根因不是「忘了跑门禁」，而是**没有统一的重生成入口** ——
`runs/infra/b_normclip2/gate_all.json` 由手敲 CLI 生成、`runs/infra/b_normclip/gate_v12.json`
另敲一次、`runs/infra/b_gate_sensitivity/report.json` 又是第三条命令。
实测后果（本轮修的就是它）：门禁升到 v1.2 之后三份产物分别停在
`gate_build=22a7d92bec0a` / `800e1d08a174` / `28290b9c1b25` 三个不同构建上，
而文档里引用的又是第四个值 —— 没人能判断哪份裁定还算数。

本脚本做四件事，全部只读评测产物、不改任何评测器或 A/C 文件：
  1. 快照：覆盖前把旧产物按 `*.build_<旧指纹>.json` 留档（沿用 gate_v11.json 的既有纪律），
     使「重判前后裁定有没有变」可事后核对；
  2. 重判：三组臂集合各自重新生成 JSON；
  3. 差异：逐臂比对旧/新的 gate_pass、measurement_valid、四类失效计数，写成 diff 产物；
  4. 把关：最后跑 `b_selfcheck_gate_regression.py`（规格 §7 五条反例），不通过则整体退出非零。

注意退出码：与门禁 CLI 同约定 —— **只要有臂未过门禁就返回非零**，不要用 `&&` 串接。
需要「重判成功但臂可以红」的语义时看 `--allow-failing-arms`。

用法：
    python3 scripts/b_regate_all.py
    python3 scripts/b_regate_all.py --allow-failing-arms --json-out runs/infra/b_regate/report.json
"""
from __future__ import annotations
import argparse, glob as globmod, importlib.util, json, os, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "b_gate_controlled_success.py"
SENS = ROOT / "scripts" / "b_gate_threshold_sensitivity.py"
REGRESS = ROOT / "scripts" / "b_selfcheck_gate_regression.py"

NORMCLIP5 = [
    "runs/infra/b_normclip/noclip.json",
    "runs/infra/b_normclip/clip3.json",
    "runs/infra/b_normclip/clip5.json",
    "runs/infra/b_normclip/clip10.json",
    "runs/infra/b_normclip/clip24.json",
]
NORMCLIP_ALL = [
    "runs/infra/b_normclip/noclip.json",
    "runs/infra/b_normclip2/clip1.0.json",
    "runs/infra/b_normclip2/clip1.5.json",
    "runs/infra/b_normclip2/clip2.0.json",
    "runs/infra/b_normclip/clip3.json",
    "runs/infra/b_normclip2/clip4.0.json",
    "runs/infra/b_normclip/clip5.json",
    "runs/infra/b_normclip/clip10.json",
    "runs/infra/b_normclip2/clip3_dzdb0.1.json",
    "runs/infra/b_normclip2/clip3_dzdb0.2.json",
    "runs/infra/b_normclip/clip24.json",
]
# 敏感性报告覆盖的 12 个官方臂（与 docs/b_gate_threshold_sensitivity_20260928.md §1 同一集合）
OFFICIAL_GLOBS = [
    "runs/infra/lerobot_act_env_20260928/official_act_truth20_*gatefields*.json",
    "runs/infra/lerobot_act_env_20260928/official_act_truth20_trimdone0_minmax_lr1e-5_s20k_seed*.json",
]

COUNT_KEYS = ("controlled_success", "provisional_pass", "over_lift", "flick", "insufficient_lift")


def relkey(p) -> str:
    """把绝对/相对路径统一成仓库相对形式，供新旧产物比对。

    为什么需要：`judge_file` 的 `file` 字段就是 `str(path)`，喂绝对路径就写绝对路径。
    本轮实测踩到一次 —— 用绝对路径重判后，产物 `file` 字段从 `runs/infra/...` 变成
    `/workspace/.../runs/infra/...`，与旧产物逐臂比对全部失配，于是「裁定变化 0 处」
    变成了**空话**（0 个臂被真正比上）。留档样本：
    `runs/infra/b_regate/defect_abs_paths_gate_all.json`。
    """
    s = str(p)
    try:
        return str(Path(s).resolve().relative_to(ROOT))
    except Exception:                                   # noqa: BLE001
        return s.lstrip("./")


def load_gate():
    spec = importlib.util.spec_from_file_location("b_gate", str(GATE))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Args:
    def __init__(self, rise_cap, final_rise, assist_off=False):
        self.rise_cap = rise_cap
        self.final_rise = final_rise
        self.assist_off = assist_off


def summarize(row):
    """抽取用于新旧比对的最小裁定摘要。"""
    acct = (row.get("accounts") or {}).get("policy_independent", {}) or {}
    return {"gate_pass": row.get("gate_pass"), "gate_reason": row.get("gate_reason"),
            "measurement_valid": row.get("measurement_valid"),
            "input_contract_status": (row.get("input_contract") or {}).get("status"),
            "raw_success": row.get("raw_success"),
            # 复合 policy 标注也是裁定的一部分：v1.2.1 那次改动 gate_pass 与四类计数全不变，
            # 唯一变的就是这两个字段。摘要里没有它们，diff 就会报「16 臂全部一致」——
            # 而实际上 9 个 clip 臂的 composite_policy 从 false 翻成了 true。
            # 工具自己少报了一次故意做的改动，这类漏报必须堵上。
            "composite_policy": row.get("composite_policy"),
            "active_constraints": row.get("active_constraints"),
            **{k: acct.get(k) for k in COUNT_KEYS}}


def snapshot_if_stale(path: Path, cur_build: str) -> str | None:
    """旧产物指纹与当前构建不同时留档，返回快照路径。"""
    if not path.exists():
        return None
    try:
        old = json.loads(path.read_text())
    except Exception:                                   # noqa: BLE001
        return None
    rows = old if isinstance(old, list) else [old]
    builds = {r.get("gate_build") for r in rows if isinstance(r, dict)}
    builds.discard(None)
    if builds == {cur_build}:
        return None
    tag = "-".join(sorted(b for b in builds if b)) or "nofingerprint"
    snap = path.with_name("%s.build_%s.json" % (path.stem, tag))
    shutil.copy2(path, snap)
    return str(snap.relative_to(ROOT))


def judge_set(gate, args, files, out_path: Path, cur_build: str, log: list):
    rows, missing = [], []
    for f in files:
        p = ROOT / f
        if not p.exists():
            missing.append(f)
            log.append("  [warn] 夹具缺失，跳过（不影响其它臂）: %s" % f)
            continue
        # 传**相对路径**：产物里的 `file` 字段必须是仓库相对形式，否则跨机器/跨挂载点不可比。
        rows.append(gate.judge_file(f, args))
    snap = snapshot_if_stale(out_path, cur_build)
    old = None
    if out_path.exists():
        try:
            old = json.loads(out_path.read_text())
        except Exception:                               # noqa: BLE001
            old = None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
    log.append("  写出 %s（%d 臂%s）" % (out_path.relative_to(ROOT), len(rows),
                                         ("，旧产物快照 %s" % snap) if snap else ""))
    # 逐臂 diff
    old_by_file = ({relkey(r.get("file")): r for r in old if isinstance(r, dict)}
                   if isinstance(old, list) else {})
    diffs = []
    for r in rows:
        prev = old_by_file.get(relkey(r.get("file")))
        if prev is None:
            diffs.append({"file": r.get("file"), "matched": False, "changed": None,
                          "note": "旧产物无此臂"})
            continue
        new_s, old_s = summarize(r), summarize(prev)
        changed = {k: {"old": old_s.get(k), "new": new_s.get(k)}
                   for k in new_s if old_s.get(k) != new_s.get(k)}
        diffs.append({"file": r.get("file"), "matched": True, "changed": changed or None,
                      "old_build": prev.get("gate_build"), "new_build": r.get("gate_build")})
    # 「匹配上」与「有变化」是两件事：matched=False 和 matched=True&changed=None 曾经
    # 都打印成 [NEW]，把「比上了且没变」误报成「旧产物里没有这个臂」。
    n_matched = sum(1 for d in diffs if d.get("matched"))
    # 空比对护栏：旧产物存在却一个臂都没比上，说明 key 口径又错了 ——
    # 这时「无变化」不是结论，是测量失败，必须显式报出来。
    vacuous = bool(old_by_file) and n_matched == 0
    if vacuous:
        log.append("  [**ERROR**] %s 的新旧比对一个臂都没匹配上（旧产物 %d 臂）——"
                   "「裁定无变化」不成立，先修路径口径" % (out_path.name, len(old_by_file)))
    return {"out": str(out_path.relative_to(ROOT)), "n_arms": len(rows), "missing": missing,
            "snapshot": snap, "diffs": diffs, "n_matched_vs_old": n_matched,
            "n_old_arms": len(old_by_file), "comparison_vacuous": vacuous}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-out", default=str(ROOT / "runs/infra/b_regate/report.json"))
    ap.add_argument("--allow-failing-arms", action="store_true",
                    help="臂未过门禁不视为本脚本失败（只看重判与回归自检是否成功）")
    ap.add_argument("--skip-sensitivity", action="store_true")
    ap.add_argument("--skip-regression", action="store_true")
    a = ap.parse_args()

    # 统一 cwd：保证传给 judge_file 的相对路径可解析，且产物 `file` 字段是仓库相对形式。
    os.chdir(ROOT)

    gate = load_gate()
    args = Args(gate.RISE_CAP, gate.FINAL_RISE_MIN)
    cur_build, cur_spec = gate.GATE_BUILD, gate.GATE_SPEC_SHA
    log: list[str] = []

    print("=" * 100)
    print("一键重判：使所有留档门禁产物的指纹与当前构建一致")
    print("当前构建：gate_version=%s gate_build=%s spec_sha256=%s"
          % (gate.GATE_VERSION, cur_build, cur_spec))
    print("=" * 100)

    report = {"gate_version": gate.GATE_VERSION, "gate_build": cur_build,
              "gate_spec_sha256": cur_spec, "rise_cap": gate.RISE_CAP,
              "final_rise_min": gate.FINAL_RISE_MIN, "sets": {}}

    print("\n[1/3] b_normclip 五臂 -> runs/infra/b_normclip/gate_v12.json")
    report["sets"]["normclip5"] = judge_set(
        gate, args, NORMCLIP5, ROOT / "runs/infra/b_normclip/gate_v12.json", cur_build, log)

    print("\n[2/3] normclip 全 11 臂 -> runs/infra/b_normclip2/gate_all.json")
    report["sets"]["normclip_all"] = judge_set(
        gate, args, NORMCLIP_ALL, ROOT / "runs/infra/b_normclip2/gate_all.json", cur_build, log)

    print("\n[3/3] 官方臂阈值敏感性 -> runs/infra/b_gate_sensitivity/report.json")
    if a.skip_sensitivity:
        print("  跳过（--skip-sensitivity）")
        report["sets"]["sensitivity"] = {"skipped": True}
    else:
        files = sorted({p for g in OFFICIAL_GLOBS for p in globmod.glob(str(ROOT / g))})
        rel = [str(Path(p).relative_to(ROOT)) for p in files]
        print("  命中 %d 个官方臂产物" % len(rel))
        snap = snapshot_if_stale(ROOT / "runs/infra/b_gate_sensitivity/report.json", cur_build)
        cmd = [sys.executable, str(SENS)] + rel
        r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
        log.append("  敏感性脚本 rc=%d%s" % (r.returncode, ("，旧产物快照 %s" % snap) if snap else ""))
        if r.returncode != 0:
            log.append("  敏感性脚本 stderr 尾部：%s" % (r.stderr or "")[-400:])
        report["sets"]["sensitivity"] = {"n_arms": len(rel), "rc": r.returncode,
                                         "snapshot": snap, "arms": rel,
                                         "stdout_tail": (r.stdout or "")[-600:]}

    for line in log:
        print(line)

    # 裁定变化汇总
    print("\n--- 重判前后裁定变化（无变化 = 新构建未改判，只换指纹）---")
    n_changed, n_matched_total, vacuous_sets = 0, 0, []
    for name, s in report["sets"].items():
        if s.get("comparison_vacuous"):
            vacuous_sets.append(name)
        n_matched_total += s.get("n_matched_vs_old", 0)
        for d in (s.get("diffs") or []):
            if d.get("changed"):
                n_changed += 1
                print("  [CHANGED] %s" % d["file"])
                for k, v in d["changed"].items():
                    print("      %-22s %s -> %s" % (k, v["old"], v["new"]))
            elif not d.get("matched"):
                print("  [NEW]     %s" % d["file"])
            else:
                print("  [SAME]    %s（%s -> %s）"
                      % (d["file"], d.get("old_build"), d.get("new_build")))
    if vacuous_sets:
        print("  **%s 的新旧比对为空，无法宣称一致**" % ",".join(vacuous_sets))
    elif n_matched_total == 0:
        print("  本轮没有可比对的旧产物（首次生成），「无变化」不构成结论。")
    elif n_changed == 0:
        print("  %d 臂全部与旧产物裁定一致（仅 gate_build/gate_spec_sha256 更新）。"
              % n_matched_total)
    report["n_verdict_changes"] = n_changed
    report["n_arms_matched_vs_old"] = n_matched_total
    report["comparison_vacuous_sets"] = vacuous_sets

    reg_ok = None
    if not a.skip_regression:
        print("\n--- 规格 §7 反例回归 ---")
        r = subprocess.run([sys.executable, str(REGRESS)], cwd=str(ROOT),
                           capture_output=True, text=True)
        tail = [l for l in (r.stdout or "").splitlines() if l.startswith("结论")]
        print("  rc=%d  %s" % (r.returncode, tail[0] if tail else "(无结论行)"))
        if r.returncode != 0:
            print((r.stdout or "")[-1500:])
        reg_ok = (r.returncode == 0)
        report["regression_ok"] = reg_ok
    else:
        report["regression_ok"] = None

    print("\n" + "=" * 100)
    print("重判完成：%d 臂、裁定变化 %d 处、§7 回归 %s"
          % (report["sets"]["normclip_all"]["n_arms"], n_changed,
             {True: "通过", False: "**未通过**", None: "跳过"}[reg_ok]))
    if vacuous_sets:
        print("** 存在空比对的臂集合：%s —— 本轮「裁定变化 %d 处」不可采信 **"
              % (",".join(vacuous_sets), n_changed))
    print("=" * 100)

    outp = Path(a.json_out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print("写出:", outp)

    if reg_ok is False:
        return 1
    if vacuous_sets:
        return 1
    if not a.allow_failing_arms:
        # 与门禁 CLI 同约定：有臂未过 -> 非零。这里以重判产物为准。
        rows = json.loads((ROOT / "runs/infra/b_normclip2/gate_all.json").read_text())
        if not all(r.get("gate_pass") for r in rows if isinstance(r, dict) and "error" not in r):
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
