#!/usr/bin/env python3
"""B 线：环境迁移后的**门禁不变性**断言闸（D→B 执行单 §1 / 验收 §8.1）。

背景：2026-09-29 14:35 起 `/root/venvs/rlrobot` 从容器内真实目录切成符号链接 →
`.codex-persist/envs/rlrobot`（自足 clean venv，`include-system-site-packages=false`）。
门禁产物的输入之一就是解释器（numpy/torch 的**实际生效值**），所以「环境换了但结论没变」
这句话**必须给可核断言**，不能只写「我验过了」（增补十 §34 全员条）。

本脚本读 `runs/infra/b_env_migration_invariance_20260929/` 下那批产物，
把 D §1 的判定逐条落成机器可判的断言，并与 **12:2x 迁移前基线**逐项对齐：

  · 五套自检通过数：可复现性 12 / 门禁回归 157 断言·39 用例 / 门禁变异 15-15 /
    黄金值 47 / T17 变异 6-6
  · `b_regate_all.py` 裁定变化 = **0 处**，且比对**非空洞**（`comparison_vacuous_sets == []`）
  · 权威表 `gate_version`/`gate_build`/`summary` 三键与 12:21 那份**逐格相同**，
    构建仍是 `v1.5 / f19f61341cbe`；`25/22/1`、`45/2/1`、`47/1`、`n_artifacts=48`、计数层 `235`
  · 落地校验：产物 mtime ≥ 对应脚本 mtime（B 自立的规矩）

**可红条件（裁定 27.1：判据必须写明怎样才能红）**
  1. 任一自检的通过数/断言数与基线常量不同 ⇒ RED（例：157→156、15→14、12→11、47→46、6→5）；
  2. 任一自检 `ok`/`all_ok`/`regression_ok` 为 False，或黄金值日志里出现 `[FAIL]` ⇒ RED；
  3. `n_verdict_changes != 0` ⇒ RED；`comparison_vacuous_sets` 非空 ⇒ RED
     （比对臂集为空时「0 处变化」是空洞真，必须单独红）；
  4. `gate_build != f19f61341cbe` 或 `summary` 与 12:21 基线任一键不同 ⇒ RED；
  5. 任一产物文件缺失 / JSON 解析失败 ⇒ RED（不当作「没有变化」）；
  6. 任一产物 mtime < 对应脚本 mtime ⇒ RED（改了脚本没重跑 = 未落地）；
  7. 黄金值那项**只读日志**：`b_selfcheck_golden_values.py --json` 是**输入**参数
     （`DEFAULT = docs/b_golden/async_td_golden_v1.json`），脚本本身不产出 JSON
     ⇒ 该项证据是 `golden_values.log`，日志缺失或没出现「47 项检查」⇒ RED。

**不红条件（反向，防恒红）**：`summary` 逐格相同但**非基线字段**不同（例如产物里的
`generated_at` / `git_commit` / 臂级明细顺序）⇒ 仍 GREEN。本闸比的是 D §1 点名的键，
不是整文件相等；`--selftest` 的 M8 专门盯这一条。

用法：
    python3 scripts/b_env_migration_invariance_check.py
    python3 scripts/b_env_migration_invariance_check.py --selftest
    python3 scripts/b_env_migration_invariance_check.py \
        --out-dir runs/infra/b_env_migration_invariance_20260929 \
        --json-out runs/infra/b_env_migration_invariance_20260929/invariance_verdict.json
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DEFAULT = ROOT / "runs/infra/b_env_migration_invariance_20260929"
BASELINE_RECLASS = ROOT / "runs/infra/b_official_arms/reclassification.json"   # 12:21 权威表

# ---- 迁移前基线常量（D §1 点名；改动这些常量等于改判据，须先报 D）----
GATE_VERSION = "v1.5"
GATE_BUILD = "f19f61341cbe"
# 六份产物里**携带** gate_build/gate_version 的份数（另两份是环境层/meta 自检，不携带）
N_BUILD_STAMPED = 4
BASE = {
    "repro_n_checks": 12,
    "reg_n_asserts": 157,
    "reg_n_asserts_ok": 157,
    "reg_n_cases": 39,
    "mut_n_mutations": 15,
    "mut_n_caught": 15,
    "golden_n_checks": 47,
    "t17_n_judged": 6,
    "reclass_n_artifacts": 48,
    "citable": {"citable_with_sensitivity_band": 25, "no_controlled_success_to_cite": 22,
                "NOT_CITABLE_measurement_invalid": 1},
    "ic_status": {"verified_ok": 45, "probe_exonerated": 2, "violated": 1},
    "in_disputed_band": 1,
    "insuff_pooled_n": 235,
}
# 产物 -> 生成它的脚本（落地校验用）
MTIME_PAIRS = [
    ("reproducibility.json", "scripts/b_selfcheck_reproducibility.py"),
    ("gate_regression.json", "scripts/b_selfcheck_gate_regression.py"),
    ("gate_mutation.json", "scripts/b_selfcheck_gate_mutation.py"),
    ("t17_mutation.json", "scripts/b_selfcheck_t17_mutation.py"),
    ("regate.json", "scripts/b_regate_all.py"),
    ("reclassification.json", "scripts/b_official_arms_reclassification.py"),
]


def _load(path: Path):
    """读 JSON；缺失/解析失败一律抛，由调用方记 RED（不静默当「无变化」）。"""
    return json.loads(path.read_text(encoding="utf-8"))


class Checker:
    def __init__(self):
        self.rows = []

    def ck(self, cid, ok, observed, required, note=""):
        self.rows.append({"id": cid, "ok": bool(ok), "observed": str(observed),
                          "required": str(required), "note": str(note)})
        print("  [%s] %-8s %s" % ("PASS" if ok else "FAIL", cid, note or required))
        return bool(ok)

    @property
    def n_pass(self):
        return sum(1 for r in self.rows if r["ok"])

    @property
    def n_fail(self):
        return sum(1 for r in self.rows if not r["ok"])


def evaluate(out_dir: Path, baseline_reclass: Path, root: Path = ROOT) -> dict:
    ck = Checker()
    errors = []
    docs = {}
    for name in ("reproducibility.json", "gate_regression.json", "gate_mutation.json",
                 "t17_mutation.json", "regate.json", "reclassification.json"):
        p = out_dir / name
        try:
            docs[name] = _load(p)
        except Exception as exc:                                   # noqa: BLE001
            errors.append("%s: %s: %s" % (name, type(exc).__name__, exc))
            docs[name] = None
    ck.ck("V0", not errors, "缺失/不可解析 %d 份" % len(errors),
          "六份 JSON 产物全部存在且可解析", "; ".join(errors)[:400])
    if errors:
        return _finish(ck, out_dir, docs, errors)

    # ---- V1 可复现性 12/12 ----
    d = docs["reproducibility.json"]
    checks = d.get("checks") or []
    n_bad = sum(1 for c in checks if not c.get("ok"))
    ck.ck("V1", len(checks) == BASE["repro_n_checks"] and n_bad == 0,
          "n_checks=%d 未过=%d" % (len(checks), n_bad),
          "可复现性 %d 项全过（基线 %d）" % (BASE["repro_n_checks"], BASE["repro_n_checks"]))

    # ---- V2 门禁回归 157 断言 / 39 用例 ----
    d = docs["gate_regression.json"]
    ck.ck("V2", d.get("ok") is True
          and d.get("n_asserts") == BASE["reg_n_asserts"]
          and d.get("n_asserts_ok") == BASE["reg_n_asserts_ok"]
          and d.get("n_cases") == BASE["reg_n_cases"],
          "ok=%s n_asserts=%s n_asserts_ok=%s n_cases=%s"
          % (d.get("ok"), d.get("n_asserts"), d.get("n_asserts_ok"), d.get("n_cases")),
          "门禁回归 %d/%d 断言、%d 用例全过" % (BASE["reg_n_asserts_ok"], BASE["reg_n_asserts"],
                                               BASE["reg_n_cases"]))

    # ---- V3 门禁变异 15/15 ----
    d = docs["gate_mutation.json"]
    ck.ck("V3", d.get("all_ok") is True and d.get("baseline_all_green") is True
          and d.get("n_mutations") == BASE["mut_n_mutations"]
          and d.get("n_caught") == BASE["mut_n_caught"],
          "all_ok=%s baseline_all_green=%s n_mutations=%s n_caught=%s"
          % (d.get("all_ok"), d.get("baseline_all_green"), d.get("n_mutations"), d.get("n_caught")),
          "门禁变异 %d/%d 被抓住（基线全绿 + 无漏判）" % (BASE["mut_n_caught"],
                                                        BASE["mut_n_mutations"]))

    # ---- V4 黄金值 47（只读日志：该脚本不产 JSON）----
    log = out_dir / "golden_values.log"
    txt = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    m = re.search(r"共\s*(\d+)\s*项检查", txt)
    n_golden = int(m.group(1)) if m else -1
    ck.ck("V4", log.exists() and n_golden == BASE["golden_n_checks"]
          and "[FAIL]" not in txt and "全部通过" in txt,
          "log_exists=%s n_checks=%d n_FAIL=%d" % (log.exists(), n_golden, txt.count("[FAIL]")),
          "黄金值 %d 项全过（`--json` 是输入参数 ⇒ 证据只能是日志，见 COMMANDS.md）"
          % BASE["golden_n_checks"])

    # ---- V5 T17 变异 6/6 ----
    d = docs["t17_mutation.json"]
    res = d.get("results") or []
    n_judged_pass = sum(1 for r in res if r.get("status") == "pass")
    ck.ck("V5", d.get("ok") is True and n_judged_pass == BASE["t17_n_judged"],
          "ok=%s n_judged_pass=%d/%d" % (d.get("ok"), n_judged_pass, len(res)),
          "T17 变异 %d/%d 判定符合预期" % (BASE["t17_n_judged"], BASE["t17_n_judged"]))

    # ---- V6 重判裁定变化 0 处，且比对非空洞 ----
    d = docs["regate.json"]
    vac = d.get("comparison_vacuous_sets") or []
    ck.ck("V6", d.get("n_verdict_changes") == 0 and d.get("regression_ok") is True and not vac,
          "n_verdict_changes=%s regression_ok=%s vacuous_sets=%s n_arms_matched=%s"
          % (d.get("n_verdict_changes"), d.get("regression_ok"), vac,
             d.get("n_arms_matched_vs_old")),
          "裁定变化 0 处 + §7 回归通过 + 比对臂集非空（空比对的「0 处」是空洞真，单独红）")

    # ---- V7 构建指纹未动 ----
    # 只有**带这两个键**的产物参与比对：reproducibility.json / t17_mutation.json 不携带构建指纹
    # （前者是环境层自检、后者是 meta 自检），把它们算进来会得到 None != f19f61341cbe 的**假红**
    # —— 本仓第 7 起同型事故（自检把自己的分母写错），登记见 DR-014 决定 7。
    # 携带份数本身也断言（== N_BUILD_STAMPED）：将来某份产物**不再**携带指纹时不会被静默忽略。
    builds = {k: v["gate_build"] for k, v in docs.items()
              if isinstance(v, dict) and "gate_build" in v}
    vers = {k: v["gate_version"] for k, v in docs.items()
            if isinstance(v, dict) and "gate_version" in v}
    bad_b = sorted(k for k, v in builds.items() if v != GATE_BUILD)
    bad_v = sorted(k for k, v in vers.items() if v != GATE_VERSION)
    ck.ck("V7", not bad_b and not bad_v
          and len(builds) == N_BUILD_STAMPED and len(vers) == N_BUILD_STAMPED,
          "携带指纹 %d/%d 份，gate_build 不一致=%s gate_version 不一致=%s"
          % (len(builds), N_BUILD_STAMPED, bad_b or "无", bad_v or "无"),
          "%d 份带构建指纹的产物全部 == %s / %s（构建冻结未被动过）"
          % (N_BUILD_STAMPED, GATE_VERSION, GATE_BUILD))

    # ---- V8 权威表三键与 12:21 基线逐格相同 + 分布层数字 ----
    new = docs["reclassification.json"]
    try:
        old = _load(baseline_reclass)
    except Exception as exc:                                       # noqa: BLE001
        old = None
        errors.append("baseline %s: %s" % (baseline_reclass.name, exc))
    same = {}
    if old is not None:
        for k in ("gate_version", "gate_build", "summary"):
            same[k] = old.get(k) == new.get(k)
    s = new.get("summary") or {}
    ck.ck("V8", old is not None and all(same.values())
          and new.get("n_artifacts") == BASE["reclass_n_artifacts"]
          and s.get("citable") == BASE["citable"]
          and s.get("ic_status") == BASE["ic_status"]
          and s.get("in_disputed_band") == BASE["in_disputed_band"]
          and (new.get("insuff_pooled") or {}).get("n") == BASE["insuff_pooled_n"],
          "三键相同=%s n_artifacts=%s citable=%s ic_status=%s in_disputed_band=%s insuff=%s"
          % (same, new.get("n_artifacts"), s.get("citable"), s.get("ic_status"),
             s.get("in_disputed_band"), (new.get("insuff_pooled") or {}).get("n")),
          "权威表与 12:21 逐格相同：25/22/1、45/2/1、争议带 1、n_artifacts 48、计数层 insuff 235")

    # ---- V9 落地校验：产物 mtime >= 脚本 mtime ----
    stale = []
    for art, scr in MTIME_PAIRS:
        a, sp = out_dir / art, root / scr
        if not a.exists() or not sp.exists():
            stale.append("%s(缺)" % art)
        elif a.stat().st_mtime < sp.stat().st_mtime:
            stale.append("%s<%s" % (art, scr))
    ck.ck("V9", not stale, "stale=%s" % (stale or "无"),
          "六份产物 mtime 均 >= 对应脚本 mtime（改脚本没重跑 = 未落地）")
    return _finish(ck, out_dir, docs, errors)


def _finish(ck, out_dir, docs, errors):
    n_fail = ck.n_fail
    ok = n_fail == 0
    interp = (out_dir / "interpreter.txt")
    itxt = interp.read_text(encoding="utf-8", errors="replace") if interp.exists() else ""

    def _grab(pat):
        m = re.search(pat, itxt, re.M)
        return m.group(1).strip() if m else "?"
    conclusion = (
        "在 realpath(prefix)=%s（经软链 /root/venvs/rlrobot）、include-system-site-packages=false、"
        "numpy=%s / torch=%s 生效的解释器上，5 套自检通过数与迁移前基线逐项相同"
        "（12 / 157·39 / 15-15 / 47 / 6-6），重判 %s 份裁定记录变化 0 处，"
        "权威表三键与 12:21 逐格相同，构建仍为 %s / %s。"
        % (_grab(r"realpath\(prefix\)\s*=\s*(\S+)"), _grab(r"^numpy\s*=\s*(\S+)"),
           _grab(r"^torch\s*=\s*(\S+)"),
           (docs.get("regate.json") or {}).get("n_arms_matched_vs_old", "?"),
           GATE_VERSION, GATE_BUILD))
    return {"spec": "环境迁移后的门禁不变性（D→B 执行单 §1 / 验收 §8.1）",
            "out_dir": str(out_dir), "ok": ok,
            "summary": {"pass": ck.n_pass, "fail": n_fail, "total": len(ck.rows)},
            "checks": ck.rows, "load_errors": errors,
            "baseline_constants": BASE, "gate_build_expected": GATE_BUILD,
            "conclusion": conclusion,
            "red_conditions": [
                "任一自检通过数与基线常量不同（12/157/39/15/47/6）",
                "任一 ok|all_ok|regression_ok 为 False，或黄金值日志出现 [FAIL]",
                "n_verdict_changes != 0，或 comparison_vacuous_sets 非空（空洞比对）",
                "gate_build != %s，或 summary 与 12:21 基线任一键不同" % GATE_BUILD,
                "任一产物缺失 / JSON 解析失败（不当作「无变化」）",
                "任一产物 mtime < 对应脚本 mtime（未落地）",
            ]}


# --------------------------------------------------------------------------
# --selftest：证明本闸**会红**。M1–M7 是正向变异（必须红），
# M8 是**反向变异**（非基线字段变了但基线键没变 ⇒ 必须仍绿，防恒红）。
# --------------------------------------------------------------------------
def _mutate(src: Path, dst: Path, fn) -> Path:
    shutil.copytree(src, dst, dirs_exist_ok=True)
    fn(dst)
    return dst


def selftest(out_dir: Path) -> int:
    def _edit(name, path_fn):
        def f(d):
            p = d / name
            doc = json.loads(p.read_text(encoding="utf-8"))
            path_fn(doc)
            p.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return f

    def _edit_log(name, old, new):
        def f(d):
            p = d / name
            p.write_text(p.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
        return f

    muts = [
        ("M0_unmutated", False, None, "正对照：原样必须绿"),
        ("M1_reg_assert_156", True,
         _edit("gate_regression.json", lambda d: d.update(n_asserts_ok=156)),
         "157->156 断言 ⇒ 必须红"),
        ("M2_verdict_change_1", True,
         _edit("regate.json", lambda d: d.update(n_verdict_changes=1)),
         "裁定变化 0->1 ⇒ 必须红"),
        ("M3_vacuous_comparison", True,
         _edit("regate.json", lambda d: d.update(comparison_vacuous_sets=["b_normclip"])),
         "比对臂集变空 ⇒「0 处变化」是空洞真 ⇒ 必须红"),
        ("M4_build_drift", True,
         _edit("reclassification.json", lambda d: d.update(gate_build="deadbeef0000")),
         "构建指纹漂移 ⇒ 必须红"),
        ("M5_t17_mutation_off", True,
         _edit("t17_mutation.json", lambda d: d.update(ok=False)),
         "T17 变异自检 ok=False ⇒ 必须红"),
        ("M6_golden_46", True,
         _edit_log("golden_values.log", "共 47 项检查", "共 46 项检查"),
         "黄金值 47->46 ⇒ 必须红"),
        ("M7_summary_citable_drift", True,
         _edit("reclassification.json",
               lambda d: d["summary"]["citable"].update(citable_with_sensitivity_band=24)),
         "权威表 25->24 ⇒ 必须红"),
        ("M8_non_baseline_field_drift", False,
         _edit("reclassification.json", lambda d: d.update(git_commit="0" * 40)),
         "**反向变异**：只改非基线字段（git_commit）⇒ 必须仍绿（防本闸恒红）"),
    ]
    print("=" * 100)
    print("%-30s %-8s %-8s %s" % ("变异", "期望红", "实际", "结论"))
    print("=" * 100)
    allok = True
    results = []
    for mid, expect_red, fn, why in muts:
        if fn is None:
            target = out_dir
        else:
            target = Path(tempfile.mkdtemp(prefix="b_invar_mut_")) / mid
            _mutate(out_dir, target, fn)
        rep = evaluate(target, BASELINE_RECLASS)
        got_red = not rep["ok"]
        status = "pass" if got_red == expect_red else "FAIL"
        if status == "FAIL":
            allok = False
        results.append({"id": mid, "expect_red": expect_red, "got_red": got_red,
                        "status": status, "why": why,
                        "n_fail": rep["summary"]["fail"],
                        "failed_ids": [r["id"] for r in rep["checks"] if not r["ok"]]})
        print("%-30s %-8s %-8s %s  %s" % (mid, expect_red, got_red, status, why))
    print("=" * 100)
    n_caught = sum(1 for r in results if r["status"] == "pass")
    print("selftest：%d/%d 符合预期 → 本闸%s有牙"
          % (n_caught, len(results), "" if allok else "**不**"))
    print("teeth.non_vacuous =", allok and n_caught == len(results))
    return 0 if allok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(OUT_DEFAULT))
    ap.add_argument("--baseline-reclass", default=str(BASELINE_RECLASS))
    ap.add_argument("--json-out", default=None,
                    help="缺省 = <out-dir>/invariance_verdict.json")
    ap.add_argument("--selftest", action="store_true",
                    help="跑正反变异证明本闸会红（不写产物）")
    a = ap.parse_args()
    out_dir = Path(a.out_dir)
    if a.selftest:
        return selftest(out_dir)
    rep = evaluate(out_dir, Path(a.baseline_reclass))
    outp = Path(a.json_out) if a.json_out else out_dir / "invariance_verdict.json"
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(rep, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("=" * 100)
    print("不变性：%d PASS / %d FAIL → %s" % (rep["summary"]["pass"], rep["summary"]["fail"],
                                            "成立" if rep["ok"] else "**不成立**"))
    print("结论：%s" % rep["conclusion"])
    print("产物：%s" % outp)
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
