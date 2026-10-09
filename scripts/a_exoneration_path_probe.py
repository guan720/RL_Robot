#!/usr/bin/env python3
"""A 线取证探针：「只改免罪册能不能让 `k2 seed0` 免罪」——把三条代码级前置**实测**出来。

为什么要有这个脚本（2026-09-29）：
移交单 `docs/a_handoff_to_b_probe_exoneration_gap_20260928.md` §4 原先把 48 臂表停在 24/22/2 归因为
「免罪册 `_doc` 的『带外 >0.08 一律不受理』文案挡住了 裁定 10 通道」，并给出「改 `_doc` + 加一条条目」
的最小修复面。09-29 复核 B 的门禁源码（`scripts/b_gate_controlled_success.py`，v1.4 / `b9379fdb1089`）
发现**该归因不完整**：`probe_kind` 在门禁里从不参与分支（只被回显），挡住目标臂的是三条**代码级**前置。
迁移闸（`scripts/a_migration_gate_preflight.py` 的 G1/G2/L9）已把它们写成断言，但那是**文本判读**；
本脚本用 B 的门禁**本尊**跑一遍，把预测变成观测，免得 B 白跑一轮「改册子 → 全量重判 → 还是 24/22/2」。

四个场景 + 一个阳性对照（全部只读 B 的代码与产物）：
  P0 现状          ：B 的真册子（无目标臂条目）        → 预期 `probe_exoneration=null`
  P1 照抄 scope=arm：只加册子条目，scope 抄现册那条     → 预期 `scope_requires_known_impl`（L9）
  P2 scope=artifact：只加册子条目，绕开臂级指纹前置     → 预期 `out_of_band_refused`（G2）
  P3 P2 + 扩带     ：再在**内存里**把带上限扩到 0.30    → 预期 `exonerated` 但 `ic_status` **仍 violated**（G1）
  C1 阳性对照      ：stdfloor 的 **reblown** 产物 + B 的真册子 → 预期 `ic_status=probe_exonerated`

C1 是本脚本的**反恒真判据**：它证明这条管线**能观测到一次成功的免罪**。没有 C1，P1–P3 的「不成功」
可能只是探针自己坏了（本仓有过恒真判据事故：`work/decisions/decisions_20260928_B.md` DR-003 验收判据 3）。

纪律：只读 B 的门禁与产物；**不改** `configs/`、不改 `scripts/b_*`；临时册子写 A 自己的
`runs/infra/lerobot_act_env_20260928/migration_gate/exoneration_path_probe/`（不纳版控）；
对门禁常量的改动只在**本进程内存里**（`DISPUTED_BLOWN_BAND`），跑完即弃，不落盘、不影响任何留档产物；
禁 `rm`（工作区 AGENTS.md）；不执行 git 写命令（DR-003 决定 8 单写者纪律）。

用法：
    python3 scripts/a_exoneration_path_probe.py \\
      --json-out runs/infra/lerobot_act_env_20260928/migration_gate/exoneration_path_probe.json
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

TARGET_ARM = "trimdone0_minmax_k2_lr1e-5_s20k_seed0"
TARGET_ARM_C = 12.469445
TARGET_PLAIN = ("runs/infra/lerobot_act_env_20260928/"
                f"official_act_truth20_{TARGET_ARM}.json")
TARGET_PROBE = ("runs/infra/lerobot_act_env_20260928/clipprobe/"
                f"official_act_truth20_{TARGET_ARM}_clipC12p469445.json")
STDFLOOR_REBLOWN = ("runs/infra/lerobot_act_env_20260928/reblown/"
                    "official_act_truth20_trimdone0_stdfloor_minmax_k2_lr1e-5_s20k_seed0.json")
B_GATE = "scripts/b_gate_controlled_success.py"
B_LEDGER = "configs/b_probe_exonerations.json"
DEFAULT_OUTDIR = ("runs/infra/lerobot_act_env_20260928/migration_gate/exoneration_path_probe")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_gate_module(repo_root: Path):
    """按路径加载 B 的门禁模块（只读；不 import 到 sys.modules 以外的任何副作用）。"""
    path = repo_root / B_GATE
    spec = importlib.util.spec_from_file_location("a_probe_b_gate", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"无法加载门禁模块：{path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["a_probe_b_gate"] = mod
    spec.loader.exec_module(mod)
    return mod


def build_entry(repo_root: Path, scope: str) -> dict:
    """裁定 16.4 要求的条目内容（移交单 §5 已备齐），只改 `scope` 这一项做对照。

    ⚠️ **历史取证件，形状停在 v1.4**（裁定 29 之后不要再照它读现值）：本 fixture 用的是
    `condN_*` **平铺**在条目顶层 + legacy 会签键 `countersigned_by`。B 落地 v1.5（DR-008）后，
    门禁改成只读 `ruling10_conditions` 里的五个精确键 + `cosign` 对象（`by` / `fact_basis`），
    所以本 fixture 在 v1.5 上会被判 `entry_conditions_incomplete` / `cosign_missing`。
    这**不是**门禁退化，而是本探针的结论已被现实超越：它当时要证明的「只改册子不足以免罪」
    已由 B 改代码 + D 复签闭环（裁定 26 / 28）。现值判据看
    `scripts/a_migration_gate_preflight.py` 的 **G2 端到端实测**。
    """
    probe = repo_root / TARGET_PROBE
    return {
        "scope": scope,
        "probe_kind": "clip_at_train_absmax",
        "artifact": TARGET_PROBE,
        "sha256": _sha256(probe) if probe.is_file() else None,
        "ruling_ref": ("supervisor_memo_20260928.md 增补五 裁定 16.4 + 裁定 10（D 已核可事实基础，"
                       "增补四 §3）；A 侧断言见 summarize_lerobot_act_arms.py::probe_exoneration"),
        "C": TARGET_ARM_C,
        "gate_build": "e4f5ec887788",
        "gate_version": "v1.2.1",
        "countersigned_by": "D",
        "countersign_ref": "增补四 §3（事实基础已核可）",
        "reason": "取证探针 fixture：验证「条目内容齐备」时门禁是否放行；不是真实登记",
        "cond1_C_equals_train_absmax": True,
        "cond2_verdicts_and_counts_identical": True,
        "cond3_diffs_enumerated_and_verdict_same": True,
        "cond4_probe_path_C_build_recorded": True,
        "cond5_scope_measurement_valid_only": True,
    }


def run_gate(mod, repo_root: Path, artifact_rel: str, json_out: Path) -> dict:
    """用 B 的门禁本尊判一份产物，取回那一行裁定。stdout 全部吞掉（本脚本只要 JSON）。"""
    argv = [B_GATE, str(artifact_rel), "--json-out", str(json_out), "--quiet"]
    old_argv = sys.argv
    sys.argv = argv
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            mod.main()
    finally:
        sys.argv = old_argv
    doc = json.loads(json_out.read_text(encoding="utf-8"))
    row = doc[0] if isinstance(doc, list) and doc else (doc if isinstance(doc, dict) else {})
    return row if isinstance(row, dict) else {}


def summarize(row: dict, scenario: str, ledger_rel: str | None, patched: dict) -> dict:
    exo = row.get("probe_exoneration") or {}
    ic = row.get("input_contract") or {}
    acc = ((row.get("accounts") or {}).get("policy_independent") or {})
    return {
        "scenario": scenario,
        "artifact": row.get("file"),
        "ledger": ledger_rel or B_LEDGER,
        "patched_in_memory": patched,
        "gate_version": row.get("gate_version"),
        "gate_build": row.get("gate_build"),
        "field_class": row.get("field_class"),
        "probe_exoneration_status": (exo.get("status") if isinstance(exo, dict) else exo),
        "probe_exoneration_note": (exo.get("note") if isinstance(exo, dict) else None),
        "ic_status": row.get("ic_status") or ic.get("status"),
        "measurement_valid": row.get("measurement_valid"),
        "gate_pass": row.get("gate_pass"),
        "gate_reason": row.get("gate_reason"),
        "mean_blown_frames_frac": ic.get("mean_blown_frames_frac"),
        "blown_metric_impl": ic.get("blown_metric_impl"),
        "blown_metric_impl_status": ic.get("blown_metric_impl_status"),
        "in_disputed_band": ic.get("in_disputed_band"),
        "controlled_success": acc.get("controlled_success"),
        "exonerated_label_applied": (row.get("ic_status") or ic.get("status")) == "probe_exonerated",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--outdir", default=DEFAULT_OUTDIR, help="临时册子与逐场景裁定的留档目录（A 侧）")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    root = Path(args.repo_root).resolve()
    outdir = (root / args.outdir) if not Path(args.outdir).is_absolute() else Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    mod = load_gate_module(root)
    orig_ledger = mod.EXONERATION_DOC
    orig_band = tuple(mod.DISPUTED_BLOWN_BAND)
    print(f"门禁本尊：gate_version={mod.GATE_VERSION} gate_build={mod.GATE_BUILD} "
          f"DISPUTED_BLOWN_BAND={orig_band} KNOWN_BLOWN_IMPLS={list(mod.KNOWN_BLOWN_IMPLS)}")
    print(f"册子（B 的，只读）：{orig_ledger}；临时册子写 {outdir.relative_to(root)}/\n")

    results: list[dict] = []

    def scenario(name: str, artifact: str, ledger_rel: str | None, entry_scope: str | None,
                 band: tuple[float, float] | None) -> dict:
        """跑一个场景：换册子 / 换带（都只在内存与 A 侧目录里），跑完恢复原状。"""
        patched: dict = {"EXONERATION_DOC": None, "DISPUTED_BLOWN_BAND": None}
        ledger_used: str | None = None
        if entry_scope is not None:
            tmp = outdir / f"probe_ledger_{name}.json"
            tmp.write_text(json.dumps(
                {"_doc": f"A 线取证探针的临时册子（场景 {name}），**不是**真实登记册；真实册子由 B 写、D 会签",
                 "entries": {TARGET_ARM: build_entry(root, entry_scope)}},
                ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            ledger_used = str(tmp.relative_to(root))
            mod.EXONERATION_DOC = ledger_used
            patched["EXONERATION_DOC"] = ledger_used
        if band is not None:
            mod.DISPUTED_BLOWN_BAND = band
            patched["DISPUTED_BLOWN_BAND"] = list(band)
        try:
            row = run_gate(mod, root, artifact, outdir / f"gate_{name}.json")
        finally:
            mod.EXONERATION_DOC = orig_ledger
            mod.DISPUTED_BLOWN_BAND = orig_band
        rec = summarize(row, name, ledger_used, patched)
        results.append(rec)
        print("  %-16s exo=%-26s ic_status=%-18s mv=%-5s ctrl=%s"
              % (name, str(rec["probe_exoneration_status"]), str(rec["ic_status"]),
                 str(rec["measurement_valid"]), str(rec["controlled_success"])))
        return rec

    print("场景（每个都用 B 的门禁本尊重判同一份产物）：")
    scenario("P0_baseline", TARGET_PLAIN, None, None, None)
    scenario("P1_scope_arm", TARGET_PLAIN, None, "arm", None)
    scenario("P2_scope_artifact", TARGET_PLAIN, None, "artifact", None)
    scenario("P3_band_widened", TARGET_PLAIN, None, "artifact", (0.03, 0.30))
    control = scenario("C1_control_stdfloor", STDFLOOR_REBLOWN, None, None, None)

    by = {r["scenario"]: r for r in results}
    findings = {
        "L9_scope_arm_declined": by["P1_scope_arm"]["probe_exoneration_status"] == "scope_requires_known_impl",
        "G2_out_of_band_refused": by["P2_scope_artifact"]["probe_exoneration_status"] == "out_of_band_refused",
        "G1_violated_never_exonerated": (
            by["P3_band_widened"]["probe_exoneration_status"] == "exonerated"
            and not by["P3_band_widened"]["exonerated_label_applied"]
            and by["P3_band_widened"]["ic_status"] == "violated"),
        "P0_no_entry_no_exoneration": by["P0_baseline"]["probe_exoneration_status"] in (None, "null"),
        "C1_control_positive": control["exonerated_label_applied"],
    }
    ledger_only_sufficient = not (findings["L9_scope_arm_declined"]
                                  or findings["G2_out_of_band_refused"]
                                  or findings["G1_violated_never_exonerated"])

    print("\n实测结论：")
    print(f"  阳性对照 C1 观测到成功免罪（ic_status=probe_exonerated）: {findings['C1_control_positive']}"
          "   ← 没有这条，上面三个「不成功」可能只是探针坏了")
    print(f"  L9 照抄 scope=arm 被当场拒绝（scope_requires_known_impl）: {findings['L9_scope_arm_declined']}")
    print(f"  G2 scope=artifact 绕开指纹前置后仍被判带外不受理（out_of_band_refused）: "
          f"{findings['G2_out_of_band_refused']}")
    print(f"  G1 连 band 都扩到 0.30、证据齐备且 status=exonerated 之后，ic_status 仍是 violated: "
          f"{findings['G1_violated_never_exonerated']}")
    print(f"\n  ⇒ 只改免罪册（不动门禁代码）足以让目标臂免罪？ {'是' if ledger_only_sufficient else '否'}")
    if not ledger_only_sufficient:
        print("    必须改 `scripts/b_gate_controlled_success.py` 的 ic_status 转移白名单（含 violated）"
              "与带外受理通道（按 probe_kind 分通道）⇒ GATE_BUILD 变 ⇒ 新版本 + 全量重判 + 改判 7 登记义务；")
        print("    D 的会签范围也随之从「一条册子条目」变成「一次门禁语义变更」。")

    doc = {
        "check": "exoneration_path_probe",
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "script": "scripts/a_exoneration_path_probe.py",
        "read_only_wrt_b": True,
        "gate_under_test": {"path": B_GATE, "gate_version": mod.GATE_VERSION,
                            "gate_build": mod.GATE_BUILD,
                            "sha256_12": _sha256(root / B_GATE)[:12],
                            "DISPUTED_BLOWN_BAND": list(orig_band),
                            "KNOWN_BLOWN_IMPLS": list(mod.KNOWN_BLOWN_IMPLS)},
        "target_arm": TARGET_ARM,
        "target_arm_C": TARGET_ARM_C,
        "ruling_ref": ("supervisor_memo_20260928.md 增补五 裁定 16.4 / 裁定 10 / 裁定 12；"
                       "work/decisions/decisions_20260928_A.md ADR-A-006 裁定 2"),
        "cross_ref": ("docs/a_handoff_to_b_probe_exoneration_gap_20260928.md §4/§5（原归因不完整，"
                      "本探针是它的实测更正）；scripts/a_migration_gate_preflight.py 的 G1/G2/L9"),
        "scenarios": results,
        "findings": findings,
        "ledger_only_sufficient": ledger_only_sufficient,
        "control_note": ("C1 是反恒真判据的阳性对照：同一条管线在 stdfloor 的 reblown 产物上"
                         "**能**观测到 ic_status=probe_exonerated，故 P1–P3 的失败不是探针自身失效"),
        "outdir": str(outdir.relative_to(root)),
    }
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\n写出: {out}")
    return 0 if findings["C1_control_positive"] else 1


if __name__ == "__main__":
    sys.exit(main())
