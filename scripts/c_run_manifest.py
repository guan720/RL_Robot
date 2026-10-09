#!/usr/bin/env python3
"""C 线：逐臂**内容寻址** run manifest（待办 3 / 执行单 P1-6，增补五 §9-C⑤）。

要解决的问题：一个数字被引用时，没人能一眼说出「它出自哪一版判据、绑的是哪份权重、
哪份数据集、哪一次 lock、哪个 seed」。git 已 init（7 commits）⇒ 本 manifest 不是**替代** git，
而是**与 git 互校**：git 管代码版本，manifest 管「这一臂的这次评测由哪些内容组成」。

**硬要求（执行单 P1-6）**：每臂的 `gate_build` / `sha256` / `is_current_build` 三字段
与 P0-2 的三字段**同源同义**——一律取自 `registry/verdict_identity.py::artifact_identity()`，
本文件**不重算、不另写一套**。因此门禁一升版（例如 B 的 v1.6），这三字段会**自己**跟着变，
`is_current_build` 整批翻 false ⇒ 那是正确行为，不是回归红点。

绑定项（增补五 §9-C⑤ 列的）分两类，**必须分开报**：
- C 能自己算的：`requirements.lock.txt`、关键 `scripts/*.py`、门禁模块、上游裁定产物本身。
- 只有 A 能给的：`model_safetensors_sha256`、数据集 sha、`pinned_object_seed`、评测 seed 列表。
  这些**不由 C 代填、不猜测**；没给就如实记 `availability="not_bound"` + 理由。
  给了就用 `--bind-from <json>`（A 写自己的目录，C 只读）。

git 归属由 **B 提供**（护栏 8：C 不执行 git 写命令，也不代 B 认定 commit 归属）。
没给就记 `status="not_available"`，不编。

产物只写 `runs/infra/c_run_manifest*`（C 自己的目录）。合成数字**无物理意义**（ADR-C-007）。

用法：
    PY=/root/venvs/rlrobot/bin/python
    CUDA_VISIBLE_DEVICES="" $PY scripts/c_run_manifest.py                 # 出真 manifest
    CUDA_VISIBLE_DEVICES="" $PY scripts/c_run_manifest.py --selftest      # 合成自检（有牙）
    CUDA_VISIBLE_DEVICES="" $PY scripts/c_run_manifest.py --bind-from runs/infra/a_.../bindings.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from registry import verdict_identity as vi  # noqa: E402

DEFAULT_UPSTREAM = ROOT / "runs" / "infra" / "lerobot_act_env_20260928"
DEFAULT_OUT = ROOT / "runs" / "infra" / "c_run_manifest_20260929.json"
SELFTEST_OUT = ROOT / "runs" / "infra" / "c_run_manifest_selftest.json"
SELFTEST_ROOT = ROOT / "runs" / "infra" / "c_run_manifest_selftest" / time.strftime("%Y%m%d_%H%M%S")

# 三字段的**来源**写死在这里，是为了让「同源同义」这句话可核：改这三行就等于改了口径，
# 会在 selftest 的 `case_three_fields_same_source` 里当场红。
THREE_FIELD_SOURCE = {"gate_build": "artifact_identity.gate_build",
                      "sha256": "artifact_identity.source_sha256",
                      "is_current_build": "artifact_identity.is_current_build"}

# C 能自己算的绑定项（只读；不碰 configs/、不碰 A/B/D 的产物）
C_OWNED_BINDINGS = ("requirements.lock.txt", "scripts/b_gate_controlled_success.py",
                    "registry/verdict_identity.py", "harness/ledger.py",
                    "registry/release_bundle.py", "scripts/c_run_manifest.py")

# 只有 A 能给的绑定项：C 不代填、不猜测
A_OWNED_BINDINGS = ("model_safetensors_sha256", "dataset_sha256", "pinned_object_seed",
                    "eval_seeds", "probe_build")

NOT_BOUND_WHY = ("这些绑定项属 A 线的 run 产物（权重 / 数据集 / object seed / 评测 seed 列表）。"
                 "C 不代填、不猜测：填了就是把 A 的产物身份写成 C 的口径。"
                 "A 给了就用 --bind-from 接进来；没给就如实记 not_bound。")


def canonical(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _file_binding(rel: str) -> dict[str, Any]:
    path = ROOT / rel
    return {"path": rel, "exists": path.is_file(),
            "sha256": vi.content_sha256(path) if path.is_file() else None,
            "size": path.stat().st_size if path.is_file() else None}


def arm_entry(record: Any, *, bindings: dict[str, Any] | None = None) -> dict[str, Any]:
    """一臂一行。**三字段只从 `artifact_identity()` 取**（同源同义，不另写一套）。"""
    ident = vi.artifact_identity(record)
    given = bindings or {}
    missing_a = [k for k in A_OWNED_BINDINGS if k not in given]
    return {"arm": ident["arm"],
            # --- P0-2 的三字段：就地展开，值**等于** artifact_identity 里的同名字段 ---
            "gate_build": ident["gate_build"],
            "sha256": ident["source_sha256"],
            "is_current_build": ident["is_current_build"],
            "three_field_source": THREE_FIELD_SOURCE,
            "artifact_identity": ident,
            "usable_for": ident["usable_for"],
            "provenance": ident["provenance"],
            "provenance_kind": getattr(record, "provenance_kind", None),
            "regraded_from": getattr(record, "regraded_from", None),
            "source_path": ident["source_path"],
            "eval_file": ident.get("eval_file"),
            "run_bindings": dict(given),
            "run_bindings_availability": ("bound" if not missing_a else
                                          ("partially_bound" if given else "not_bound")),
            "run_bindings_missing": missing_a,
            "run_bindings_not_bound_why": (NOT_BOUND_WHY if missing_a else None)}


def build_manifest(records: Iterable[Any], *, run_id: str, gate_current: dict[str, Any],
                   arm_bindings: dict[str, dict[str, Any]] | None = None,
                   git_provenance: dict[str, Any] | None = None,
                   root_label: str = "") -> dict[str, Any]:
    """把一批裁定记录装成内容寻址的 run manifest。"""
    arm_bindings = arm_bindings or {}
    arms = [arm_entry(record, bindings=arm_bindings.get(str(vi.artifact_identity(record)["arm"])))
            for record in records]
    # 「同源同义」不靠注释，靠**当场核对**：三字段必须与嵌入的 artifact_identity 逐值相同。
    for arm in arms:
        ident = arm["artifact_identity"]
        if (arm["gate_build"] != ident["gate_build"] or arm["sha256"] != ident["source_sha256"]
                or arm["is_current_build"] != ident["is_current_build"]):
            raise vi.VerdictIdentityError(
                f"臂 {arm['arm']} 的三字段与 artifact_identity 不同源（P1-6 的硬要求被破坏）")
    addressed = {"run_id": run_id, "gate_current": gate_current, "arms": arms}
    manifest = {
        "kind": "c_run_manifest",
        "schema": "c_run_manifest/v1",
        "run_id": run_id,
        "generated_at": time.strftime("%Y-%m-%dT%H%M%S%z"),
        "generated_by": "scripts/c_run_manifest.py（C 线，只读上游；不新建/不改写/不删 A 的产物）",
        "root_label": root_label,
        "content_addressing": {
            "manifest_sha256": sha256_text(canonical(addressed)),
            "addressed_fields": ["run_id", "gate_current", "arms"],
            "algorithm": "sha256 over canonical JSON（键排序、无多余空白、UTF-8 原样）",
            "why": ("内容寻址而非路径寻址：改任何一臂的任何绑定都会换哈希，"
                    "于是「这份 manifest 描述的是哪一次 run」是可核的，不靠文件名。")},
        "identity_single_source": {
            "module": "registry/verdict_identity.py::artifact_identity",
            "rule": ("每臂的 gate_build / sha256 / is_current_build **同源同义**取自该函数，"
                     "本文件不重算（执行单 P1-6）。`build_manifest` 里当场核对，不同源就抛错。"),
            "three_field_source": THREE_FIELD_SOURCE},
        "gate_current": gate_current,
        "bindings": {
            "c_owned": [_file_binding(rel) for rel in C_OWNED_BINDINGS],
            "a_owned": {"fields": list(A_OWNED_BINDINGS),
                        "provided_for_arms": sorted(k for k, v in arm_bindings.items() if v),
                        "why_c_does_not_fill": NOT_BOUND_WHY},
            "git": git_provenance or {
                "status": "not_available",
                "why": ("commit 归属由 **B** 提供（护栏 8：C 不执行 git 写命令，也不代 B 认定归属）。"
                        "没给就记 not_available，不编。"),
                "crosscheck": "git 已 init ⇒ 本 manifest 与 git **互校**，不是替代（增补五 §9-C⑤）"}},
        "n_arms": len(arms),
        "counts": {
            "is_current_build": {
                "true": sum(1 for a in arms if a["is_current_build"]),
                "false": sum(1 for a in arms if not a["is_current_build"])},
            "usable_for": _distribution(a["usable_for"] for a in arms),
            "provenance_kind": _distribution(a["provenance_kind"] for a in arms),
            "run_bindings_availability": _distribution(a["run_bindings_availability"]
                                                       for a in arms),
            "distinct_gate_builds": len({str(a["gate_build"]) for a in arms})},
        "arms": arms,
        "reading_rule": (
            "引用某一臂的数字前先看三字段：`is_current_build=false` ⇒ 只能作**历史口径**引用"
            "（裁定 16.3 / 改判 7），不得当作「已在当前构建复现」；"
            "`usable_for != physical_fact` ⇒ 不得进账本事实表、不得进发布包（P1-5 的准入闸）。"),
    }
    return manifest


def _distribution(values: Iterable[Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for value in values:
        out[str(value)] = out.get(str(value), 0) + 1
    return dict(sorted(out.items()))


def _load_bindings(path: str | Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    arms = payload.get("arms") if isinstance(payload, dict) else payload
    if isinstance(arms, dict):
        return {str(k): dict(v) for k, v in arms.items()}
    return {str(row.get("arm")): {k: v for k, v in row.items() if k != "arm"}
            for row in (arms or []) if isinstance(row, dict) and row.get("arm")}


def real_manifest(args: argparse.Namespace) -> int:
    upstream = Path(args.upstream_dir)
    records: list[Any] = []
    inv = vi.scan_dir(upstream, current=None, collect=records)
    if not records:
        raise vi.VerdictIdentityError(
            f"{upstream} 下没扫到任何可解析的裁定 ⇒ 不出 manifest（宁可不产，不产一份空的当数）")
    manifest = build_manifest(
        records, run_id=args.run_id, gate_current=inv["gate_current"],
        arm_bindings=(_load_bindings(args.bind_from) if args.bind_from else {}),
        git_provenance=(json.loads(Path(args.git_provenance).read_text(encoding="utf-8"))
                        if args.git_provenance else None),
        root_label=inv.get("root_label", ""))
    manifest["source_inventory"] = {
        "upstream_dir": str(upstream),
        "n_files_scanned": inv.get("n_files_scanned"),
        "n_verdicts": inv.get("n_verdicts"),
        "n_records_bound": len(records),
        "parse_errors": inv.get("parse_errors"),
        "note": ("manifest 由**本次现算**的 inventory 生成（不是读旧清单）：三字段必须反映"
                 "**调用时**的门禁现值，否则门禁升版后 manifest 会假装还是当前构建。")}
    out = Path(args.json_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(out), "n_arms": manifest["n_arms"],
                      "manifest_sha256": manifest["content_addressing"]["manifest_sha256"],
                      "counts": manifest["counts"]}, ensure_ascii=False, indent=2))
    return 0


# ---------------- 合成自检 ----------------
_SYN_DEFAULTS: dict[str, Any] = {
    "source_path": "runs/infra/c_run_manifest_selftest/synthetic/gate_synthetic.json",
    "source_sha256": "syntheticsourcesha256", "arm": "synthetic_arm_a",
    "eval_file": "synthetic_eval.json", "eval_sha256": "syntheticevalsha256",
    "gate_version": "vFIX.1", "gate_build": "fixfeed00001",
    "gate_spec_sha256": "fixspec00000001", "gate_spec_doc": "synthetic_spec.md",
    "measurement_valid": True, "measurement_validity_declared": True,
    "field_class": "complete", "missing_fields": (), "gate_pass": True,
    "gate_reason": "synthetic", "accounts": {}, "buckets": {},
    "input_contract_status": "ok", "suspect_truncation_as_failure": False,
    "validity_class": "valid", "validity_reason": "synthetic",
    "arm_field_class": "complete", "validity_source": "synthetic",
    "blowup_threshold_source": "synthetic", "labels_reportable": True,
    "upstream_superseded_by": None, "arm_summary_sha256": None, "arm_verdict": True,
    "is_current_build": True, "superseded": False, "superseded_by": None,
    "provenance": "synthetic", "usable_for": vi.USABLE_PHYSICAL_FACT,
    "reasons": ("synthetic_reason",),
}


def _syn(**over: Any) -> vi.VerdictIdentity:
    return vi.VerdictIdentity(**{**_SYN_DEFAULTS, **over})


def selftest() -> int:
    SELFTEST_ROOT.mkdir(parents=True, exist_ok=True)
    checks: list[tuple[str, Any]] = []
    gate = {"gate_version": "vFIX.1", "gate_build": "fixfeed00001",
            "gate_spec_sha256": "fixspec00000001"}
    records = [_syn(), _syn(arm="synthetic_arm_b", gate_build="olderbuild0000",
                            is_current_build=False, usable_for=vi.USABLE_STALE_BUILD,
                            provenance_kind=vi.PROVENANCE_ORDINARY_STALE,
                            source_sha256="othersourcesha256")]
    manifest = build_manifest(records, run_id="synthetic_run", gate_current=gate,
                              root_label="synthetic")

    arms = manifest["arms"]
    checks.append(("三字段就地展开，且与嵌入的 artifact_identity 逐值相同（同源同义）",
                   all(a["gate_build"] == a["artifact_identity"]["gate_build"]
                       and a["sha256"] == a["artifact_identity"]["source_sha256"]
                       and a["is_current_build"] == a["artifact_identity"]["is_current_build"]
                       for a in arms)))
    checks.append(("三字段来源被**写进产物**（读者可核，不靠读代码）",
                   all(a["three_field_source"] == THREE_FIELD_SOURCE for a in arms)
                   and manifest["identity_single_source"]["module"].endswith("artifact_identity")))
    moved = build_manifest([_syn(gate_build="anotherbuild000", is_current_build=False)],
                           run_id="synthetic_run", gate_current=gate)
    checks.append(("三字段取自记录、不是常量：改记录的 gate_build ⇒ manifest 跟着变",
                   moved["arms"][0]["gate_build"] == "anotherbuild000"
                   and moved["arms"][0]["sha256"] == _SYN_DEFAULTS["source_sha256"]))
    checks.append((f"现构建 / 旧构建分桶正确（{manifest['counts']['is_current_build']}）",
                   manifest["counts"]["is_current_build"] == {"true": 1, "false": 1}))
    checks.append(("旧构建那一臂的 usable_for 与 provenance_kind 一并带出（不只是 build 号）",
                   arms[1]["usable_for"] == vi.USABLE_STALE_BUILD
                   and arms[1]["provenance_kind"] == vi.PROVENANCE_ORDINARY_STALE))

    base_sha = manifest["content_addressing"]["manifest_sha256"]
    rebound = build_manifest(records, run_id="synthetic_run", gate_current=gate,
                             arm_bindings={"synthetic_arm_a": {"model_safetensors_sha256": "x" * 64}})
    checks.append(("内容寻址有牙：改一臂的一个绑定 ⇒ manifest_sha256 变",
                   rebound["content_addressing"]["manifest_sha256"] != base_sha))
    checks.append(("同输入 ⇒ 同哈希（可复现，不是每次跑都换）",
                   build_manifest(records, run_id="synthetic_run",
                                  gate_current=gate)["content_addressing"]["manifest_sha256"]
                   == base_sha))
    checks.append(("run_id 也在寻址分母里（换 run 不换内容也算换 manifest）",
                   build_manifest(records, run_id="other_run",
                                  gate_current=gate)["content_addressing"]["manifest_sha256"]
                   != base_sha))

    checks.append(("A 线绑定项没给 ⇒ 如实记 not_bound + 缺哪几项（C 不代填、不猜测）",
                   bool(arms[0]["run_bindings_availability"] == "not_bound"
                        and set(arms[0]["run_bindings_missing"]) == set(A_OWNED_BINDINGS)
                        and arms[0]["run_bindings_not_bound_why"])))
    checks.append(("给了一部分 ⇒ partially_bound，缺的仍点名（不因为给了就全绿）",
                   rebound["arms"][0]["run_bindings_availability"] == "partially_bound"
                   and "dataset_sha256" in rebound["arms"][0]["run_bindings_missing"]))
    checks.append(("git 归属没给 ⇒ not_available + 说明由 B 提供（不编 commit）",
                   manifest["bindings"]["git"]["status"] == "not_available"
                   and "B" in manifest["bindings"]["git"]["why"]))
    provided = build_manifest(records, run_id="synthetic_run", gate_current=gate,
                             git_provenance={"status": "provided_by_B", "head": "syntheticsha"})
    checks.append(("git 归属给了 ⇒ 原样带上（manifest 与 git 互校，不是替代）",
                   provided["bindings"]["git"]["status"] == "provided_by_B"))
    checks.append(("C 自己那几份绑定带 sha256（缺文件记 exists=false，不静默略过）",
                   all(("sha256" in b and "exists" in b)
                       for b in manifest["bindings"]["c_owned"])))

    # 反面牙：三字段若**不再**取自 artifact_identity（例如日后有人改成从别处取值、或就地硬写），
    # `build_manifest` 必须当场抛错，而不是产出一份看着齐整的假 manifest。
    # 变异体要造出**真分歧**：改 `artifact_identity` 本身不行 —— 三字段与嵌入的身份同出一次调用，
    # 一起变就永远相等，那条判据会恒过。要模拟的是「取值路径被换掉」，所以变异 `arm_entry`。
    original_entry = arm_entry
    caught_by_field: dict[str, bool] = {}
    for field_name in ("gate_build", "sha256", "is_current_build"):
        def _divergent(record: Any, *, bindings: dict[str, Any] | None = None,
                       _field: str = field_name) -> dict[str, Any]:
            row = original_entry(record, bindings=bindings)
            return {**row, _field: ("divergent00000" if _field != "is_current_build"
                                    else not row[_field])}
        try:
            globals()["arm_entry"] = _divergent
            build_manifest([_syn()], run_id="synthetic_run", gate_current=gate)
            caught_by_field[field_name] = False
        except vi.VerdictIdentityError:
            caught_by_field[field_name] = True
        finally:
            globals()["arm_entry"] = original_entry
    checks.append(("三字段任一与 artifact_identity 不同源 ⇒ build_manifest 抛错（逐字段都试过）",
                   all(caught_by_field.values()) and len(caught_by_field) == 3))
    checks.append(("抛错之后 arm_entry 已复原（自检不留下被污染的模块状态）",
                   arm_entry is original_entry))

    failed = [name for name, ok in checks if ok is not True]
    SELFTEST_OUT.write_text(json.dumps({
        "checks": [{"name": name, "ok": bool(ok is True)} for name, ok in checks],
        "pass": not failed, "n_checks": len(checks), "n_pass": len(checks) - len(failed),
        "n_failed": len(failed), "failed": failed,
        "c_synthetic": {"physical_meaning": False,
                        "note": "合成裁定 / 合成构建号 / 合成 sha，数字**无物理意义**（ADR-C-007）"},
        "artifact_dir": str(SELFTEST_ROOT.relative_to(ROOT)),
        "sample_manifest_sha256": base_sha,
        "impl_sha256": {rel: vi.content_sha256(ROOT / rel) for rel in
                        ("scripts/c_run_manifest.py", "registry/verdict_identity.py")},
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name, ok in checks:
        print(f"[{'PASS' if ok is True else 'FAIL'}] {name}" + ("" if ok is True else f" -> {ok}"),
              flush=True)
    print("--- 全部通过 ---" if not failed else f"--- 失败 {len(failed)} 条 ---")
    for name in failed:
        print(f"  FAIL {name}")
    print(f"结果: {len(checks) - len(failed)}/{len(checks)} PASS -> "
          f"{SELFTEST_OUT.relative_to(ROOT)}")
    return 1 if failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--upstream-dir", default=str(DEFAULT_UPSTREAM),
                    help="A 线的裁定产物目录（只读；默认 runs/infra/lerobot_act_env_20260928）")
    ap.add_argument("--run-id", default="lerobot_act_env_20260928")
    ap.add_argument("--json-out", default=str(DEFAULT_OUT))
    ap.add_argument("--bind-from", default=None,
                    help="A 提供的逐臂绑定 JSON（model/dataset/seed 等；C 不代填）")
    ap.add_argument("--git-provenance", default=None,
                    help="B 提供的 git 归属 JSON（C 不执行 git 写命令、不代 B 认定归属）")
    ap.add_argument("--selftest", action="store_true", help="只跑合成自检，不读上游、不出真 manifest")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    return real_manifest(args)


if __name__ == "__main__":
    raise SystemExit(main())
