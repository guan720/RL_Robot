#!/usr/bin/env python
"""`link_audit()` 的**两侧牙 + 模式覆盖对照探针**（裁定 92.2-③ / 93.8，纯 CPU，**不触卡**）。

为什么需要这一件（红线族 `reference_auditor_must_prove_its_own_pattern_coverage`）：
`link_audit()` 是裁定 92.2-③ 新加进 `PERSIST_MANIFEST` 的**审计器**（审「悬空符号链接」）。
93.8 规定：任何审引用/审清单/审命名的闸，必须先证明**自己的识别模式覆盖对象空间的全部形态**，
做法 = **对照探针**（注入一条已知形态的坏对象，抓不到 ⇒ 审计器自己红）。
本件就是那颗对照探针，并且**把形态覆盖做全**：悬空链接不止「绝对路径」一种形态。

**关键的形态学论证（这也是 92.2-② 那个修法不能兼任检测器的原因）**：
92.2-② 的 `relativize_abs_symlink()` 只处理 `readlink` 以 `/` 开头的那一类；
若检测器也按「绝对路径」判悬空，就会漏掉**相对路径的悬空链接**（`libfoo.so.1 -> libfoo.so.9`
而同目录没有 `libfoo.so.9`）⇒ 那正是缺陷类 ⑲ `green_verdict_from_an_under_covered_audit_pattern`。
`link_audit()` 的判据是 `Path.exists()`（跟随链接的真实 stat），**与字符串形状无关** ⇒
本探针用 P3（相对悬空）与 P4（绝对但存在）两条**反向形态**把这个主张钉死：
P3 必须被抓到（否则模式窄）、P4 必须**不**被抓到（否则是「一律红」的平凡真）。

五个注入形态（全部在**沙箱前缀**里造，真前缀一个字节不碰）：
  P1 绝对路径 + 目标不存在  ⇒ 必须 `dangling=true`   （= 真前缀里那条 `libnvidia-vksc-core.so.1` 的同型）
  P2 相对路径 + 目标存在    ⇒ 必须 `dangling=false`  （绿见证：修好之后就是这个形态）
  P3 相对路径 + 目标不存在  ⇒ 必须 `dangling=true`   （**模式覆盖的命门**：字符串形状判据会漏它）
  P4 绝对路径 + 目标存在    ⇒ 必须 `dangling=false`  （绿见证：证明判据不是「绝对即坏」）
  P5 真文件（不是链接）     ⇒ 必须**不进审计集**（`n_links_audited` 不含它）

三值纪律（裁定 88.3-2）：另跑两条空集臂 —— 空目录、不存在的目录 ⇒ 必须 `verdict=not_measured`
且聚合值为 `null`，**不许给出「0 条悬空」这种"通过"形状的读数**。

退出码：**0 = 五形态全部按预期 + 两条空集臂都是 not_measured**；1 = 任一臂不符；
3 = 目标产物已存在（拒绝覆写，裁定 82 §2-4 / 83.5）；4 = 沙箱里没有任何注入形态（空集）。
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
sys.path.insert(0, str(REPO / "scripts"))
import e_egl_coldstart as ec        # noqa: E402  复用 link_audit，不另写一套（裁定 46.4）

DEFAULT_OUT = REPO / "runs/infra/e_restart_readiness_20260930/LINK_AUDIT_SELFCHECK.json"

# ── 注入形态表（`expect_dangling` 就是牙的期望值；`None` = 不该进审计集）────────────
FORMS = [
    {"id": "P1", "name": "libabs_dangling.so.1", "kind": "symlink",
     "target": "/definitely/not/here/libabs_dangling.so.999", "expect_dangling": True,
     "why": "绝对路径 + 目标不存在。**真前缀里那条 `libnvidia-vksc-core.so.1` 的同型**"},
    {"id": "P2", "name": "librel_ok.so.1", "kind": "symlink",
     "target": "librel_ok.so.999", "expect_dangling": False,
     "why": "相对路径 + 目标存在 = 裁定 92.2-① 修好之后的形态（绿见证）"},
    {"id": "P3", "name": "librel_dangling.so.1", "kind": "symlink",
     "target": "librel_dangling_absent.so.999", "expect_dangling": True,
     "why": "**模式覆盖的命门**：相对路径 + 目标不存在。按「绝对路径」判悬空的审计器会漏它 ⇒ 缺陷类 ⑲"},
    {"id": "P4", "name": "libabs_ok.so.1", "kind": "symlink",
     "target": None, "expect_dangling": False,
     "why": "绝对路径 + 目标存在（指向沙箱内真文件）。证明判据不是「绝对即坏」的平凡真"},
    {"id": "P5", "name": "libreal_file.so.999", "kind": "file",
     "target": None, "expect_dangling": None,
     "why": "真文件不是符号链接 ⇒ **不该进审计集**（`n_links_audited` 必须只数链接）"},
]


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cpu_stat() -> dict:
    return {"loadavg": list(os.getloadavg()),
            "nr_throttled": ec.ev.cpu_stat().get("nr_throttled"),
            "as_of": time.strftime("%Y-%m-%dT%H:%M:%S %Z")}


def build_sandbox(root: Path) -> list[dict]:
    root.mkdir(parents=True, exist_ok=True)
    made = []
    for form in FORMS:
        p = root / form["name"]
        if form["kind"] == "file":
            p.write_bytes(b"\x7fELF probe payload (not a real .so)\n")
            made.append({**form, "created": str(p), "creation": "regular file"})
            continue
        tgt = form["target"]
        if tgt is None:                       # P4：绝对路径指向沙箱内的真文件
            real = root / "librel_ok.so.999"
            real.write_bytes(b"\x7fELF target payload for P4\n")
            tgt = str(real.resolve())
        elif not tgt.startswith("/"):         # 相对目标：P2 需要一个真文件供它指
            if form["id"] == "P2":
                (root / tgt).write_bytes(b"\x7fELF target payload for P2\n")
        os.symlink(tgt, str(p))
        made.append({**form, "created": str(p), "creation": f"symlink -> {tgt}"})
    return made


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--sandbox-dir",
                    default=str(REPO / "runs/infra/e_restart_readiness_20260930/sandbox_link_audit"))
    args = ap.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        print(json.dumps({"verdict": "REFUSE",
                          "reason": f"目标已存在，拒绝覆写（append-only，裁定 82 §2-4 / 83.5）: {out}",
                          "existing_sha256_12": sha256_file(out)[:12],
                          "hint": "换 --out 另落新件"}, ensure_ascii=False))
        return 3

    sandbox = Path(args.sandbox_dir)
    made = build_sandbox(sandbox)
    if not made:
        print(json.dumps({"verdict": "not_measured", "reason": "沙箱里没有任何注入形态 ⇒ 空集，不给通过形状的读数"},
                         ensure_ascii=False))
        return 4

    load_before = cpu_stat()
    sb = ec.link_audit(sandbox)
    real = ec.link_audit(ec.PREFIX)
    empty_dir = sandbox / "_empty_arm"
    empty_dir.mkdir(exist_ok=True)
    arms = {"sandbox_injected": sb,
            "empty_directory": ec.link_audit(empty_dir),
            "missing_directory": ec.link_audit(sandbox / "_no_such_dir"),
            "real_prefix_readonly": real}

    by_name = {x["name"]: x for x in (sb.get("links") or [])}
    checks, failed = [], []
    for form in FORMS:
        got = by_name.get(form["name"])
        exp = form["expect_dangling"]
        if exp is None:                                   # P5：不该进审计集
            ok = got is None
            observed = "not_in_audit_set" if ok else f"IN_AUDIT_SET dangling={got.get('dangling')}"
        else:
            ok = bool(got) and got.get("dangling") is exp
            observed = None if got is None else f"dangling={got.get('dangling')} link_target_exists={got.get('link_target_exists')}"
        checks.append({"form_id": form["id"], "injected_bad_form": form["why"],
                       "name": form["name"], "expect_dangling": exp, "observed": observed,
                       "detected": ok, "why_it_matters": form["why"]})
        if not ok:
            failed.append(form["id"])

    # 空集两臂：必须 not_measured + 聚合值 null（裁定 88.3-2）
    for arm in ("empty_directory", "missing_directory"):
        a = arms[arm]
        ok = a["verdict"] == "not_measured" and a["n_dangling"] is None and a["dangling"] is None
        checks.append({"form_id": arm, "injected_bad_form": "空集臂：审计集为空 ⇒ 必须 not_measured + null",
                       "expect_dangling": None, "observed": f"verdict={a['verdict']} n_dangling={a['n_dangling']}",
                       "detected": ok, "why_it_matters": "aggregate_over_empty_set_must_be_null（88.3-2）"})
        if not ok:
            failed.append(arm)

    # 计数牙：审计集必须只数符号链接（4 条），不含真文件 P5
    n_expect = sum(1 for f in FORMS if f["kind"] == "symlink")
    ok_count = sb.get("n_links_audited") == n_expect
    checks.append({"form_id": "audit_set_scope", "injected_bad_form": f"审计集必须恰好 {n_expect} 条链接（P5 真文件不算）",
                   "expect_dangling": None, "observed": f"n_links_audited={sb.get('n_links_audited')}",
                   "detected": ok_count, "why_it_matters": "把真文件也算进链接审计集 = 计数口径漂移"})
    if not ok_count:
        failed.append("audit_set_scope")

    # 93.8 要求的那个字段（逐字键名）
    pattern_coverage_probe = {
        "injected_bad_form": ("P1 绝对悬空 / P3 **相对悬空**（模式覆盖的命门）两条坏形态；"
                             "P2 相对完好 / P4 绝对完好两条绿见证；P5 真文件（不该进审计集）"),
        "detected": (not failed) and sb.get("n_dangling") == 2,
        "n_forms_injected": len(FORMS),
        "n_forms_behaved_as_expected": sum(1 for c in checks if c["detected"]),
        "forms_failed": failed,
        "sandbox_n_dangling_measured": sb.get("n_dangling"),
        "sandbox_dangling_names": sb.get("dangling"),
        "why_it_matters": ("93.8：审计器必须自证识别模式覆盖对象空间的全部形态。"
                          "本审计器的判据是 `Path.exists()`（跟随链接的真实 stat），"
                          "**与 `readlink` 的字符串形状无关** ⇒ P3（相对悬空）必须被抓到、"
                          "P4（绝对但存在）必须不被抓到。缺这颗探针 ⇒ 该闸按 `not_measured` 登记、不得报绿。"),
        "citable": True,
    }

    payload = {
        "artifact": str(out), "agent": "E",
        "task": "T-E-9-②/③ 的自证件（裁定 92.2-③ 新字段的两侧牙 + 93.8 模式覆盖对照探针）",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S %Z"),
        "auditor_under_test": {"module": "scripts/e_egl_coldstart.py", "function": "link_audit()",
                               "sha256_12": sha256_file(REPO / "scripts/e_egl_coldstart.py")[:12],
                               "n_lines": len((REPO / "scripts/e_egl_coldstart.py").read_text().splitlines())},
        "sandbox_prefix": str(sandbox),
        "real_prefix": str(ec.PREFIX),
        "real_prefix_untouched": "本件只对真前缀做**只读** `link_audit()`；沙箱建在 E 自己的产物目录里",
        "injected_forms": made,
        "arms": arms,
        "checks": checks,
        "pattern_coverage_probe": pattern_coverage_probe,
        "verdict": "PASS" if not failed else "FAIL",
        "failed_forms": failed,
        "two_sided_proof_present": bool(sb.get("n_dangling")) and any(
            f["expect_dangling"] is False for f in FORMS),
        "gpu_touched": False,
        "boundary_guard": ec.ep.boundary_guard(),
        "load_before": load_before, "load_after": cpu_stat(),
    }
    payload["boundary_clean_no_system_write"] = (
        payload["boundary_guard"]["ok"] and not payload["boundary_guard"]["forbidden_paths_present"])
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"artifact": str(out), "verdict": payload["verdict"],
                      "pattern_coverage_probe_detected": pattern_coverage_probe["detected"],
                      "sandbox_n_dangling": sb.get("n_dangling"),
                      "real_prefix_n_dangling": real.get("n_dangling"),
                      "real_prefix_verdict": real.get("verdict"),
                      "failed_forms": failed,
                      "loadavg": [load_before["loadavg"], payload["load_after"]["loadavg"]],
                      "nr_throttled": [load_before["nr_throttled"], payload["load_after"]["nr_throttled"]],
                      "boundary_clean_no_system_write": payload["boundary_clean_no_system_write"],
                      "exit": 0 if not failed else 1}, ensure_ascii=False, indent=1))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
