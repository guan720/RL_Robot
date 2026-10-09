#!/usr/bin/env python3
"""T-B2-20 的自检件：`registry/verdict_identity.py` 的**多门禁并存**（D→B2 执行单 2026-09-30 §二）。

D 的裁定原文（四条，逐条都要有牙）：
  ① `GATE_MODULE_PATH` 由单值改为**按 `gate_id` 索引的映射**；
  ② **默认仍是 ACT 冻结基线**（`0928` 两份 lock、`arms_summary_v3.json`、`requirements.lock.txt`、
     `clip*.json` 一个字节不动 ⇒ 冻结面不破）；
  ③ 新增 `gate_id="pi05_norm_contract"` → C2 的 `scripts/c2_gate_norm_contract.py`；
  ④ **verdict_identity 必须带 `gate_id`；跨 gate 的身份串不得互认**（拿 ACT 门禁的身份去认
     π₀.₅ 闸的产物 ⇒ **必须红**），变异体两向：① 用 ACT 的 gate_id 查 π₀.₅ 闸 ⇒ 红；
     ② 各自查各自 ⇒ 绿。

为什么现在做：裁定 93.4 要求 **A2 的 BC 入口自己复算闸产物 sha 并与 C2 声明值对账**，
`registry/` 是这条对账的身份源；它此前只认 ACT 门禁 ⇒ A2 无处对账。

纪律：
- **只读上游**（B 的 guard、C2 的闸与产物、A 的权威表）；本脚本只写自己的 run 目录
  `runs/vla/b2_registry_multigate_20260930/`（B2 写入面，裁定 38.3）与 `tmp/`；不用 `rm`。
- **不复制判据**：冻结面是否完好由 B 的 `b_env_provenance_guard.py`（freeze 模式）判，
  本脚本只**委派**它并登记 D 点名的那些件的 sha256（观测，不是判据）。
- **三值**：取不到的写 `None` + `measurement_status="not_measured"`，不写 `false`/`0` 顶替。
- **裁定 93.8**（红线族 `reference_auditor_must_prove_its_own_pattern_coverage` / 缺陷类 ⑲）：
  本脚本里有三处**模式/清单/判定审计器**（`infer_gate_id` 的产物归属推断、冻结面清单对账、
  「归属不可判 ⇒ 拒收」那条链路），各自带对照探针（注入已知坏形态 ⇒ 抓不到就是审计器自己红；
  并且各带**负对照**证明不是恒红），产物落 `pattern_coverage_probe`。

用法：/root/venvs/rlrobot/bin/python scripts/b2_selfcheck_registry_multigate.py [--quiet]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from registry import verdict_identity as vi          # noqa: E402

OUT_DIR = ROOT / "runs/vla/b2_registry_multigate_20260930"
SYNTH_DIR = OUT_DIR / "synthetic"
GUARD = ROOT / "scripts/b_env_provenance_guard.py"
GUARD_REBUILD_DIR = "runs/infra/a_lerobot_env_rebuild_20260929"
PI05_GATE_ARTIFACT = ("runs/vla/c2_norm_contract_20260929/gate/run_20260930_073852/gate_verdict.json")
ACT_UPSTREAM_DIR = ROOT / "runs/infra/lerobot_act_env_20260928"
# D 点名的冻结面（判据归 B 的 guard，这里只**登记身份**作观测）
FROZEN_SURFACE = [
    "runs/infra/c_lerobot_env_locks_backup_20260928/requirements.lock.txt",
    "runs/infra/c_lerobot_env_locks_backup_20260928/requirements.eval.lock.txt",
    "runs/infra/lerobot_act_env_20260928/requirements.lock.txt",
    "runs/infra/lerobot_act_env_20260928/requirements.eval.lock.txt",
    "runs/infra/lerobot_act_env_20260928/attribution/arms_summary_v3.json",
    "requirements.lock.txt",
]
SHA12_RE = re.compile(r"^[0-9a-f]{12}$")
N_TEETH = 13
TOOTH_IDS = ["MG%d" % i for i in range(1, N_TEETH + 1)]


def sha12(p: Path) -> str | None:
    if not p.is_file():
        return None
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def ident_row(rel: str) -> dict:
    p = (ROOT / rel) if not Path(rel).is_absolute() else Path(rel)
    exists = p.is_file()
    full = None
    if exists:
        h = hashlib.sha256()
        with p.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        full = h.hexdigest()
    return {"path": rel, "exists": exists, "n_bytes": (p.stat().st_size if exists else None),
            "sha256_12": (full[:12] if full else None),
            "measurement_status": ("measured" if exists else "not_measured")}


def write_synth(name: str, payload) -> Path:
    SYNTH_DIR.mkdir(parents=True, exist_ok=True)
    p = SYNTH_DIR / name
    p.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def arm_row(gate_build: str, *, accounts: bool = True, valid: bool = True,
            gate_id: str | None = None, artifact: str | None = None,
            gate_spec_sha256: str | None = None,
            arm_file: str = "synthetic_arm.json") -> dict:
    row: dict = {"file": arm_file, "gate_build": gate_build, "gate_version": "synthetic",
                 "measurement_valid": valid, "gate_pass": True,
                 "terminal_semantics": {"suspect_truncation_labeled_as_failure": False},
                 "input_contract": {"status": "ok"}}
    if accounts:
        row["accounts"] = {"policy_independent": {"controlled_success": 1},
                           "system_assisted": {"controlled_success": 1},
                           "autonomous_learning": {"controlled_success": 1}}
    if gate_id:
        row["gate_id"] = gate_id
    if artifact:
        row["artifact"] = artifact
    if gate_spec_sha256:
        row["gate_spec_sha256"] = gate_spec_sha256
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description="T-B2-20 多门禁并存的自检件（B2 数据与判据线）")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--json-out", default=None)
    a = ap.parse_args()

    rows: list[dict] = []
    probe_blocks: dict[str, dict] = {}

    def rec(tid, target, want, got, ok, desc, evidence=None, probe=None):
        rows.append({"id": tid, "target": target, "want": want, "got": got,
                     "ok": (None if ok is None else bool(ok)), "desc": desc,
                     "evidence": evidence or {}, "pattern_coverage_probe": probe,
                     "layer": "registry_multigate"})
        if not a.quiet:
            print("%-5s %-34s %-26s %-26s ⇒ %s" % (
                tid, target[:34], str(want)[:26], str(got)[:26],
                ("成立" if ok else ("**不成立**" if ok is False else "not_measured"))))
            if ok is False:
                print("      %s" % desc[:300])

    t0 = time.time()
    act = vi.current_gate_identity(refresh=True)
    pi05 = vi.current_gate_identity(vi.PI05_GATE_ID, refresh=True)

    # ---- MG1：默认门禁仍是 ACT 冻结基线，且既有调用方行为逐字不变 ----
    mg1_checks = {
        "default_gate_id_is_act": vi.DEFAULT_GATE_ID == "act_controlled_success",
        "gate_module_path_is_the_map_default": (vi.GATE_MODULE_PATH
                                                == vi.GATE_MODULE_PATHS[vi.DEFAULT_GATE_ID]),
        "gate_module_path_points_at_b_gate": vi.GATE_MODULE_PATH.name == "b_gate_controlled_success.py",
        "act_identity_carries_gate_id": act.get("gate_id") == vi.DEFAULT_GATE_ID,
        "act_version_build_specsha_all_present": bool(act.get("gate_version"))
                                                 and bool(act.get("gate_build"))
                                                 and bool(act.get("gate_spec_sha256")),
        "act_build_is_module_sha12": act.get("gate_build") == act.get("module_sha256", "")[:12],
        "act_build_provenance_is_upstream": act.get("gate_build_provenance")
                                            == "upstream_module_attr:GATE_BUILD",
        "act_fingerprint_is_gate_scoped": str(act.get("gate_identity_fingerprint", "")).startswith(
            vi.DEFAULT_GATE_ID + "@"),
    }
    rec("MG1", "默认门禁 = ACT 冻结基线", "8/8 成立",
        "%d/8 成立" % sum(1 for v in mg1_checks.values() if v),
        all(mg1_checks.values()),
        "D→B2 §二 ②：默认仍是 ACT，`GATE_MODULE_PATH` 这个名字与其指向都保持（C 的自检 "
        "`scripts/c_selfcheck_verdict_identity.py:79/95/98/121` 直接读它）",
        evidence={"checks": mg1_checks, "act_identity": act})

    # ---- MG2：冻结面不破（判据归 B 的 guard，本脚本只委派 + 登记）----
    guard_out = OUT_DIR / "delegated_g1_g5_freeze_after_tb220.json"
    cmd = [sys.executable, str(GUARD), "--root", str(ROOT), "--json-out", str(guard_out),
           "--quiet", "--venv", "/root/venvs/rlrobot", "--rebuild-dir",
           str(ROOT / GUARD_REBUILD_DIR)]
    gp = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    gdoc = json.loads(guard_out.read_text(encoding="utf-8")) if guard_out.is_file() else {}
    gchecks = {c.get("check_id"): c.get("status") for c in (gdoc.get("checks") or [])}
    frozen = [ident_row(x) for x in FROZEN_SURFACE]
    n_clip = len(sorted((ROOT / "runs/infra").glob("b_normclip*/clip*.json")))
    mg2_ok = ((gdoc.get("summary") or {}).get("verdict") == "PASS"
              and all(v == "PASS" for v in gchecks.values()) and len(gchecks) == 5
              and gp.returncode == 0
              and all(f["measurement_status"] == "measured" for f in frozen))
    rec("MG2", "冻结面不破（委派 B 的 G1–G5 freeze）", "verdict=PASS 且 G1–G5 全 PASS",
        "rc=%s verdict=%s %s" % (gp.returncode, (gdoc.get("summary") or {}).get("verdict"),
                                 "%d/5 PASS" % sum(1 for v in gchecks.values() if v == "PASS")),
        mg2_ok,
        "D→B2 §二 ②：`0928` 两份 lock、`arms_summary_v3.json`、`requirements.lock.txt`、"
        "`clip*.json` 一个字节不动。**不复制判据**：完好性由 B 的 guard 判（本脚本只委派），"
        "B2 侧只登记 D 点名那些件的 sha256 作观测 + 数 `clip*.json` 的份数",
        evidence={"guard_cmd": cmd, "guard_rc": gp.returncode, "guard_verdict":
                  (gdoc.get("summary") or {}).get("verdict"), "guard_checks": gchecks,
                  "guard_build": gdoc.get("guard_build"), "guard_artifact": str(guard_out),
                  "frozen_surface": frozen, "n_clip_json_under_b_normclip": n_clip,
                  "n_frozen_not_measured": sum(1 for f in frozen
                                               if f["measurement_status"] != "measured")})

    # ---- MG3：π₀.₅ 门禁的身份可得，且 provenance 诚实 ----
    pi05_module_sha12 = sha12(ROOT / "scripts/c2_gate_norm_contract.py")
    idfiles = {r["path"]: r for r in (pi05.get("identity_files") or [])}
    mg3_checks = {
        "gate_id_is_pi05": pi05.get("gate_id") == "pi05_norm_contract",
        "module_path_is_c2_gate": pi05.get("module_path") == "scripts/c2_gate_norm_contract.py",
        "build_equals_recomputed_module_sha12": pi05.get("gate_build") == pi05_module_sha12,
        "build_provenance_is_registry_computed": pi05.get("gate_build_provenance")
                                                 == "registry_computed_module_sha256_12",
        "criteria_module_in_identity_face": ("harness/norm_contract.py" in idfiles
                                             and idfiles["harness/norm_contract.py"]["role"]
                                             == "criteria_module"
                                             and idfiles["harness/norm_contract.py"]["measurement_status"]
                                             == "measured"),
        "fingerprint_is_gate_scoped": str(pi05.get("gate_identity_fingerprint", "")).startswith(
            "pi05_norm_contract@"),
        "missing_upstream_fields_disclosed": bool(pi05.get("missing_upstream_identity_fields")),
        "builder_registered_but_not_in_fingerprint": any(
            r["path"] == "scripts/c2_build_norm_stats.py" and r["in_fingerprint"] is False
            and r.get("why_not_in_fingerprint")
            for r in (pi05.get("related_files") or [])),
    }
    rec("MG3", "π₀.₅ 门禁身份可得 + provenance 诚实", "8/8 成立",
        "%d/8 成立" % sum(1 for v in mg3_checks.values() if v),
        all(mg3_checks.values()),
        "D→B2 §二 ③④：新增 gate_id → C2 的闸；身份必须带 gate_id。C2 的闸模块**不公布** "
        "GATE_BUILD/GATE_VERSION（实测只有 GATE_ROOT）⇒ 本层按 ACT 的同一约定自己算，"
        "并标 `registry_computed_module_sha256_12`（与上游公布的值**不得混读**）；"
        "判据面必须含 `harness/norm_contract.py`（判据本体在那里，只认闸壳会在判据变动时纹丝不动）",
        evidence={"checks": mg3_checks, "pi05_identity": pi05,
                  "recomputed_module_sha12": pi05_module_sha12})

    # ---- MG4：与 C2 声明值对账（裁定 93.4 的地基）----
    art_path = ROOT / PI05_GATE_ARTIFACT
    declared = None
    art_doc = {}
    if art_path.is_file():
        art_doc = json.loads(art_path.read_text(encoding="utf-8"))
        declared = ((art_doc.get("evidence") or {}).get("gate_sha256_12"))
    mg4_ok = (isinstance(declared, str) and bool(SHA12_RE.match(declared))
              and pi05.get("gate_build") is not None)
    rec("MG4", "与 C2 声明的闸 sha 可对账", "声明值存在且是 12 位十六进制",
        "declared=%r registry=%r equal=%s" % (declared, pi05.get("gate_build"),
                                              declared == pi05.get("gate_build")),
        mg4_ok,
        "裁定 93.4：A2 的 BC 入口必须**自己复算**闸产物 sha 并与 C2 声明值对账 ⇒ registry 必须"
        "能提供可比的那一个值。相等与否是**观测**（闸脚本可能在跑后又被改）；"
        "牙的失败条件是「声明值缺失/形态不对 ⇒ A2 无从对账」",
        evidence={"artifact": PI05_GATE_ARTIFACT, "artifact_identity": ident_row(PI05_GATE_ARTIFACT),
                  "declared_gate_sha256_12": declared, "registry_computed": pi05.get("gate_build"),
                  "equal": (declared == pi05.get("gate_build")),
                  "declared_contract_module": (art_doc.get("evidence") or {}).get("contract_module"),
                  "note_if_unequal": ("不等不等于谁错：C2 的这份产物 as_of 07:40，闸脚本此后可能"
                                      "被改过 ⇒ 引用必须带 as_of（citation_sha_as_of_discipline）")})

    # ---- MG5：变异①（D 点名）拿 ACT 的 gate_id 去认 π₀.₅ 闸的产物 ⇒ **必须红** ----
    mg5_ev: dict = {}
    # (a) 真件：C2 的 gate_verdict.json，用**默认（ACT）**身份解析
    recs_a = vi.parse_verdict(art_path)          # gate_id 缺省 = ACT
    mg5_ev["a_real_artifact_under_act_identity"] = {
        "n_records": len(recs_a),
        "usable_for": sorted({r.usable_for for r in recs_a}),
        "all_wrong_gate": bool(recs_a) and all(r.usable_for == vi.USABLE_WRONG_GATE for r in recs_a),
        "gate_id_on_record": sorted({r.gate_id for r in recs_a}),
        "artifact_gate_id": sorted({str(r.artifact_gate_id) for r in recs_a}),
        "mismatch_sample": (recs_a[0].gate_id_mismatch if recs_a else None),
        "admitted": [vi.admit_as_physical_fact(r, current=act)["admitted"] for r in recs_a],
        "refusal_names_cross_gate": [
            any("跨门禁" in x for x in vi.admit_as_physical_fact(r, current=act)["refusal_reasons"])
            for r in recs_a],
    }
    # (b1) 合成 π₀.₅ 逐臂裁定（构建号 = π₀.₅ 现值），却拿 ACT 现值去认
    p_b1 = write_synth("pi05_arm_verdict_build_pi05.json",
                       [arm_row(pi05["gate_build"], artifact="c2_norm_contract_gate")])
    recs_b1 = vi.parse_verdict(p_b1, current=act)
    # (b2) **伪造**：把构建号写成 ACT 的现值（最危险的形态：构建号对得上、门禁对不上）
    p_b2 = write_synth("pi05_arm_verdict_build_forged_act.json",
                       [arm_row(act["gate_build"], artifact="c2_norm_contract_gate")])
    recs_b2 = vi.parse_verdict(p_b2, current=act)
    mg5_ev["b1_pi05_arm_under_act_identity"] = {
        "usable_for": [r.usable_for for r in recs_b1],
        "admitted": [vi.admit_as_physical_fact(r, current=act)["admitted"] for r in recs_b1]}
    mg5_ev["b2_forged_act_build_under_act_identity"] = {
        "usable_for": [r.usable_for for r in recs_b2],
        "admitted": [vi.admit_as_physical_fact(r, current=act)["admitted"] for r in recs_b2],
        "why_this_is_the_dangerous_form": ("构建号被伪造成 ACT 的现值 ⇒ 只比 `gate_build` 的闸"
                                           "会**放行**；跨门禁档必须由 gate 归属判，"
                                           "不能由构建号判（这正是 D 说的『身份串不得互认』）")}
    mg5_ok = (mg5_ev["a_real_artifact_under_act_identity"]["all_wrong_gate"]
              and all(u == vi.USABLE_WRONG_GATE for r in (recs_b1 + recs_b2)
                      for u in [r.usable_for])
              and not any(mg5_ev["b1_pi05_arm_under_act_identity"]["admitted"])
              and not any(mg5_ev["b2_forged_act_build_under_act_identity"]["admitted"])
              and all(mg5_ev["a_real_artifact_under_act_identity"]["refusal_names_cross_gate"]))
    rec("MG5", "变异①：ACT 身份去认 π₀.₅ 产物", "全部 wrong_gate_identity 且拒收",
        "a=%s b1=%s b2=%s" % (mg5_ev["a_real_artifact_under_act_identity"]["usable_for"],
                              mg5_ev["b1_pi05_arm_under_act_identity"]["usable_for"],
                              mg5_ev["b2_forged_act_build_under_act_identity"]["usable_for"]),
        mg5_ok,
        "D→B2 §二 ④ 的变异①：拿 ACT 门禁的身份去认 π₀.₅ 闸的产物 ⇒ **必须红**。"
        "三个形态都要红：真件（聚合形态）、合成逐臂裁定、以及**把构建号伪造成 ACT 现值**的那一份",
        evidence=mg5_ev)

    # ---- MG6：变异②（D 点名）各自查各自 ⇒ **绿** ----
    p_p = write_synth("pi05_arm_verdict_own_gate.json",
                      [arm_row(pi05["gate_build"], artifact="c2_norm_contract_gate",
                               gate_id="pi05_norm_contract")])
    recs_p = vi.parse_verdict(p_p, gate_id="pi05_norm_contract")
    adm_p = [vi.admit_as_physical_fact(r) for r in recs_p]      # 不给 current ⇒ 按记录自己的 gate 取现值
    p_a = write_synth("act_arm_verdict_own_gate.json", [arm_row(act["gate_build"])])
    recs_a2 = vi.parse_verdict(p_a)                             # 缺省 = ACT
    adm_a = [vi.admit_as_physical_fact(r) for r in recs_a2]
    mg6_checks = {
        "pi05_under_pi05_is_physical_fact": all(r.usable_for == vi.USABLE_PHYSICAL_FACT
                                                for r in recs_p) and bool(recs_p),
        "pi05_under_pi05_admitted": all(x["admitted"] for x in adm_p) and bool(adm_p),
        "pi05_admit_used_pi05_gate": all(x["gate_id"] == "pi05_norm_contract" for x in adm_p),
        "act_under_act_is_physical_fact": all(r.usable_for == vi.USABLE_PHYSICAL_FACT
                                              for r in recs_a2) and bool(recs_a2),
        "act_under_act_admitted": all(x["admitted"] for x in adm_a) and bool(adm_a),
        "act_admit_used_act_gate": all(x["gate_id"] == vi.DEFAULT_GATE_ID for x in adm_a),
        "records_carry_gate_id": all(bool(r.gate_id) for r in recs_p + recs_a2),
        "records_carry_fingerprint": all(bool(r.gate_identity_fingerprint) for r in recs_p + recs_a2),
    }
    rec("MG6", "变异②：各自查各自", "8/8 成立（两边都 physical_fact 且准入）",
        "%d/8 成立" % sum(1 for v in mg6_checks.values() if v), all(mg6_checks.values()),
        "D→B2 §二 ④ 的变异②：各自查各自 ⇒ 绿。同时钉住「记录必须带 gate_id 与门禁作用域指纹」"
        "（D 的原话：verdict_identity 必须带 gate_id）",
        evidence={"checks": mg6_checks,
                  "pi05_records": [r.to_dict() for r in recs_p],
                  "act_records": [r.to_dict() for r in recs_a2],
                  "pi05_admission": adm_p, "act_admission": adm_a})

    # ---- MG7：表里没有的 gate_id ⇒ 报错，不猜、不落默认 ----
    mg7_ev = {}
    for fn, call in (("current_gate_identity", lambda: vi.current_gate_identity("no_such_gate")),
                     ("parse_verdict", lambda: vi.parse_verdict(p_p, gate_id="no_such_gate")),
                     ("admit_via_record", lambda: vi.admit_as_physical_fact(
                         vi.parse_verdict(p_p, gate_id="pi05_norm_contract")[0],
                         current={"gate_id": "no_such_gate", "gate_build": pi05["gate_build"],
                                  "gate_identity_fingerprint": pi05["gate_identity_fingerprint"]}))):
        try:
            out = call()
            mg7_ev[fn] = {"raised": False, "returned": (str(out)[:200] if not isinstance(out, dict)
                                                         else {"admitted": out.get("admitted"),
                                                               "refusal": out.get("refusal_reason")})}
        except vi.VerdictIdentityError as exc:
            mg7_ev[fn] = {"raised": True, "error": str(exc)[:200]}
    mg7_ok = (mg7_ev["current_gate_identity"]["raised"] and mg7_ev["parse_verdict"]["raised"]
              and mg7_ev["admit_via_record"].get("returned", {}).get("admitted") is False)
    rec("MG7", "未知 gate_id 不得被猜", "两处抛 VerdictIdentityError + 准入拒收",
        "raise=%s/%s admit=%s" % (mg7_ev["current_gate_identity"]["raised"],
                                  mg7_ev["parse_verdict"]["raised"],
                                  mg7_ev["admit_via_record"].get("returned", {}).get("admitted")),
        mg7_ok,
        "不猜、不静默落到默认门禁：跨门禁认错身份比认错构建更贵（本层的由来就是"
        "「同一目录里同时存在多个 gate_build」）",
        evidence=mg7_ev)

    # ---- MG8：身份串**构造上**不可能跨门禁相等 ----
    fake_files = [{"path": "x.py", "role": "gate_module", "sha256": "aa" * 32,
                   "in_fingerprint": True}]
    fp_a = vi.gate_identity_fingerprint({"gate_id": vi.DEFAULT_GATE_ID, "identity_files": fake_files})
    fp_b = vi.gate_identity_fingerprint({"gate_id": vi.PI05_GATE_ID, "identity_files": fake_files})
    mg8_checks = {
        "same_face_different_gate_gives_different_string": fp_a != fp_b,
        "prefix_is_gate_id_a": fp_a.split("@")[0] == vi.DEFAULT_GATE_ID,
        "prefix_is_gate_id_b": fp_b.split("@")[0] == vi.PI05_GATE_ID,
        "real_two_gates_differ": act["gate_identity_fingerprint"] != pi05["gate_identity_fingerprint"],
        "deterministic": vi.gate_identity_fingerprint(
            {"gate_id": vi.PI05_GATE_ID, "identity_files": fake_files}) == fp_b,
    }
    rec("MG8", "身份串跨门禁不可互认（构造性）", "5/5 成立",
        "%d/5 成立" % sum(1 for v in mg8_checks.values() if v), all(mg8_checks.values()),
        "**同一份身份面**、只换 gate_id ⇒ 串必须不同（这不是概率问题，是构造问题）；"
        "两个真门禁的串也必须不同",
        evidence={"checks": mg8_checks, "fp_same_face_act": fp_a, "fp_same_face_pi05": fp_b,
                  "fp_real_act": act["gate_identity_fingerprint"],
                  "fp_real_pi05": pi05["gate_identity_fingerprint"]})

    # ---- MG9：判据面变动能被指纹抓到（`gate_build` 抓不到的那一部分）----
    ident_same_build = dict(pi05)
    ident_same_build["identity_files"] = [
        (dict(r, sha256=("bb" * 32), sha256_12=("bb" * 6))
         if r["path"] == "harness/norm_contract.py" else dict(r))
        for r in (pi05.get("identity_files") or [])]
    fp_moved = vi.gate_identity_fingerprint(ident_same_build)
    rec_moved = vi.parse_verdict(p_p, gate_id="pi05_norm_contract")[0]
    fake_current = dict(pi05, gate_identity_fingerprint=fp_moved)
    adm_moved = vi.admit_as_physical_fact(rec_moved, current=fake_current)
    mg9_checks = {
        "gate_build_unchanged": fake_current["gate_build"] == rec_moved.gate_build,
        "fingerprint_changed": fp_moved != pi05["gate_identity_fingerprint"],
        "admission_refused": adm_moved["admitted"] is False,
        "refusal_names_fingerprint": any("身份面指纹不符" in x
                                         for x in adm_moved["refusal_reasons"]),
        "control_same_fingerprint_admitted": vi.admit_as_physical_fact(
            rec_moved, current=dict(pi05))["admitted"] is True,
    }
    rec("MG9", "判据面（norm_contract）变动 ⇒ 拒收", "5/5 成立",
        "%d/5 成立" % sum(1 for v in mg9_checks.values() if v), all(mg9_checks.values()),
        "π₀.₅ 的判据本体在 `harness/norm_contract.py`，**只比闸脚本的 `gate_build` 会在判据变动"
        "而闸壳不动时放过**（本轮实测：11:4x 时 norm_contract 已由 43d19a876af1 变到 "
        "a030e951787e，而闸脚本仍是 3f44225a5fa1）⇒ 指纹必须覆盖判据面，且准入闸要比它",
        evidence={"checks": mg9_checks, "fp_now": pi05["gate_identity_fingerprint"],
                  "fp_after_criteria_move": fp_moved, "admission": adm_moved})

    # ---- MG10：ACT 既有行为**无回归**（真目录清单）----
    inv = vi.scan_dir(ACT_UPSTREAM_DIR)
    recs = inv["records"]
    mg10_checks = {
        "parse_errors_empty": inv["parse_errors"] == [],
        "n_verdicts_positive": inv["n_verdicts"] > 0,
        "all_levels_in_enum": all(r["usable_for"] in vi.USABLE_LEVELS for r in recs),
        "no_wrong_gate_on_act_dir": inv["n_wrong_gate"] == 0,
        "every_record_carries_act_gate_id": all(r["gate_id"] == vi.DEFAULT_GATE_ID for r in recs),
        "physical_fact_still_present": inv["usable_for_distribution"].get(
            vi.USABLE_PHYSICAL_FACT, 0) > 0,
        "multi_build_coexistence_still_visible": len(inv["build_distribution"]) > 1,
        "inventory_reports_gate_scope": bool(inv.get("gate_id")) and bool(
            inv.get("gate_identity_fingerprint")),
    }
    rec("MG10", "ACT 真目录清单无回归", "8/8 成立",
        "%d/8 成立（n=%d，wrong_gate=%d）" % (sum(1 for v in mg10_checks.values() if v),
                                             inv["n_verdicts"], inv["n_wrong_gate"]),
        all(mg10_checks.values()),
        "改判不得把 ACT 那一路改坏：真目录（A 的 0928 权威目录）扫出来必须与改判前同一形态 —— "
        "全部可解析、档位都在枚举内、`physical_fact` 仍在、多构建并存仍可见、**且没有一条被误判"
        "成跨门禁**（假红方向）",
        evidence={"checks": mg10_checks, "dir": str(ACT_UPSTREAM_DIR),
                  "n_verdicts": inv["n_verdicts"],
                  "usable_for_distribution": inv["usable_for_distribution"],
                  "build_distribution_n": len(inv["build_distribution"]),
                  "gate_id_distribution": inv["gate_id_distribution"],
                  "artifact_gate_id_distribution": inv["artifact_gate_id_distribution"]})

    # MG11 的**如实披露**要引用这个实测量：ACT 权威目录里归属推断不出的记录数
    # （= 13 行没有 `gate_spec_*` 键的旧格式逐臂裁定 + 若干聚合报告；后者本来就 `not_a_verdict`）。
    act_no_attr = inv["artifact_gate_id_distribution"].get("<not_declared_by_artifact>", 0)

    # ---- MG11：裁定 93.8 对照探针 · 产物归属推断（`infer_gate_id` 是模式审计器）----
    # 形态表**跟着标记表走**：本轮把 ACT 一栏从「通用裁定形状键」收窄成「门禁专属键」
    # （`gate_spec_sha256` / `gate_spec_doc`），所以 ACT 的坏形态也换成**实测形态**；
    # 旧形态（`accounts` / `measurement_valid` / `gate_build`）现在**必须**回 None ——
    # 它作为负对照留在下面第 4 条，钉住「通用键不是门禁证据」这条改判本身。
    bad_forms = [
        ({"artifact": "c2_norm_contract_gate"}, vi.PI05_GATE_ID, "π₀.₅ 真件的实测形态"),
        ({"artifact": "c2_norm_contract_gate_v2"}, vi.PI05_GATE_ID, "同一族的另一个值（前缀相同）"),
        ({"artifact": "c2_norm_contract", "n_checks": 48}, vi.PI05_GATE_ID, "带别的键也不该干扰"),
        ({"gate_spec_sha256": "0" * 12,
          "gate_spec_doc": "docs/b_controlled_success_v1_20260928.md"}, vi.DEFAULT_GATE_ID,
         "ACT 逐臂裁定的实测形态（0928 权威目录 234 行里 221 行带这两个键）"),
        ({"gate_spec_doc": "docs/b_controlled_success_v1_20260928.md"}, vi.DEFAULT_GATE_ID,
         "只带专属键之一也要认得出（标记语义是「任一命中即算」）"),
        ({"gate_id": "pi05_norm_contract"}, None, "**只有 gate_id 字段、没有标记键** ⇒ 归属"
                                                   "不由 `infer_gate_id` 判（它读的是标记），"
                                                   "由 `parse_verdict` 的 declared 分支判 ⇒ "
                                                   "这里必须回 None（不猜）"),
    ]
    good_controls = [
        ({}, None, "空件：无从推断 ⇒ None（不是 ACT）"),
        ({"artifact": "c2_norm_contract_gate", "gate_spec_sha256": "0" * 12}, None,
         "**两个门禁的专属标记都在** ⇒ 必须 None（本层不替上游裁归属）。这一形态**不是**安全的："
         "它另由 MG13 判**拒收**（`artifact_gate_ambiguous`），不能因为 infer 回 None 就没事"),
        ({"artifact": "something_else", "n_checks": 1}, None, "前缀不同的无关件"),
        ({"gate_build": "x", "measurement_valid": True, "accounts": {}}, None,
         "**通用裁定形状键不是门禁证据**（本轮改判的核心）：π₀.₅ 写逐臂裁定也会带这三个键，"
         "把它们当 ACT 的标记会让**每一份** π₀.₅ 逐臂产物变成「归属不可判」⇒ 系统性假红；"
         "而 MG5 的 b2 洞（伪造构建号被准入）当年正是从「多命中 ⇒ None ⇒ 当作没有不一致」"
         "这条路上漏过去的"),
    ]
    # 结构性检查：标记表里**不得**混进通用裁定形状键（否则上面第 4 条负对照迟早会被改坏）。
    generic_in_marker_table = sorted(
        {k for gid in vi.GATE_ARTIFACT_MARKERS for (k, _pfx) in vi.GATE_ARTIFACT_MARKERS[gid]}
        & set(vi.GENERIC_VERDICT_SHAPE_KEYS))
    probe_rows = []
    for payload, want, why in bad_forms + good_controls:
        got = vi.infer_gate_id(payload)
        probe_rows.append({"injected_form": payload, "why": why, "expected": want,
                           "detected": (got == want), "got": got,
                           "kind": ("bad_form" if (payload, want, why) in bad_forms
                                    else "negative_control")})
    probe11 = {
        "ruling": ("裁定 93.8 `reference_auditor_must_prove_its_own_pattern_coverage`"
                   "（红线族；缺陷类 ⑲ `green_verdict_from_an_under_covered_audit_pattern`）"),
        "auditor_under_test": "`infer_gate_id`（模式表 = `GATE_ARTIFACT_MARKERS`）",
        "injected_bad_form": [r["injected_form"] for r in probe_rows if r["kind"] == "bad_form"],
        "n_bad_forms": sum(1 for r in probe_rows if r["kind"] == "bad_form"),
        "n_negative_controls": sum(1 for r in probe_rows if r["kind"] == "negative_control"),
        "rows": probe_rows,
        "marker_table_excludes_generic_shape_keys": {
            "intersection": generic_in_marker_table,
            "clean": (generic_in_marker_table == []),
            "why": ("标记表里混进 `GENERIC_VERDICT_SHAPE_KEYS` 的键，归属推断就会把"
                    "「这是一条裁定行」读成「这是 ACT 的裁定行」⇒ MG5 的 b2 形态"
                    "（构建号伪造成 ACT 现值）就是这么被放行的")},
        "detected": (all(r["detected"] for r in probe_rows) and not generic_in_marker_table),
        "measurement_status": ("measured" if (all(r["detected"] for r in probe_rows)
                                              and not generic_in_marker_table)
                               else "not_measured"),
        "known_coverage_gap_disclosed": (
            "**如实披露模式窄的那一处**：一份**不带任何标记键**的 π₀.₅ 产物（既无 `artifact`，"
            "也无 `gate_id` 字段）推断不出归属 ⇒ 记 `None`（`not_measured`，不猜），"
            "于是它不会被判成跨门禁红，而会按调用方声明的门禁走下去（多半落到 "
            "`not_a_verdict` / `unidentified_build`，仍然是拒收，只是**理由不同**）。"
            "这是「宁可记 not_measured 也不猜」的三值纪律与「跨门禁必须红」之间的取舍："
            "猜归属会造成假红（把 ACT 的产物说成 π₀.₅ 的）。要收紧就得让 C2 在产物里写 "
            "`gate_id` 字段 —— 那是**上游的写入面**，B2 不代改（已作为一条知会记进日报）。"
            "**同一取舍在 ACT 侧的实测代价**：ACT 的专属标记只覆盖 0928 权威目录里 "
            "221/234 条逐臂行（其余 13 行是旧格式、没有 `gate_spec_*` 键）⇒ 本层实测 "
            "%d/%d 条记录归属为 `not_declared_by_artifact`。它们按缺省门禁（ACT）对账，"
            "分级与准入**不变**（MG10 已证无回归）；代价只在**反方向**：这 %d 条若被拿去"
            "按 π₀.₅ 门禁对账，不会被标成 `wrong_gate_identity`，而是靠构建号不符拒收"
            "（结论仍是拒收，**理由不同**）" % (act_no_attr, inv["n_verdicts"], act_no_attr)),
    }
    probe_blocks["infer_gate_id"] = probe11
    rec("MG11", "对照探针 · 产物归属推断", "10/10 与期望一致",
        "%d/10 一致" % sum(1 for r in probe_rows if r["detected"]),
        probe11["detected"],
        "裁定 93.8：归属推断是**模式审计器**，必须先证明自己的模式覆盖得住形态空间"
        "（6 条坏形态 + 4 条负对照，含「两个门禁的专属标记都在 ⇒ 必须 None」「空件 ⇒ 必须 None」"
        "与「通用裁定形状键 ⇒ 必须 None」）+ 一条结构性检查（标记表不含通用键）；"
        "覆盖不到的那一处**如实披露**（含 ACT 侧 13/234 的实测代价），不装作全覆盖",
        evidence={"n_rows": len(probe_rows),
                  "generic_keys_in_marker_table": generic_in_marker_table,
                  "act_dir_records_without_attribution": act_no_attr}, probe=probe11)

    # ---- MG12：裁定 93.8 对照探针 · 冻结面清单对账（`ident_row` 是清单审计器）----
    real = FROZEN_SURFACE[0]
    real_row = ident_row(real)
    bad_manifest = [
        dict(real_row, sha256_12="0" * 12, detect_field="sha256_12",
             why="sha 与盘上不符（清单说谎：登记了一个盘上不存在的内容身份）"),
        # 这一条**必须是「说谎的登记表」**，不能是「审计器的正确输出」：只把 path 换成不存在的件、
        # 同时把 exists/sha/n_bytes/status 一并改成 not_measured 的话，注入形态与实读结果逐字相同
        # ⇒ 探针永远抓不到（本轮首跑就是这么假红了一条：2/3）。真正要抓的坏形态是：
        # 清单声称「在册、已测、有 sha 与字节数」，而盘上根本没有这个件。
        dict(real_row, path="runs/infra/definitely_not_here.lock.txt", detect_field="measurement_status",
             why="**清单声称在册**（exists=True / measured / 带 sha 与字节数）**而盘上没有这个件** ⇒ "
                 "审计器必须回 not_measured + None（三值纪律：不许写 false/0 顶替），"
                 "也就必须与这份说谎的登记表不符"),
        dict(real_row, n_bytes=(real_row["n_bytes"] or 0) + 1, detect_field="n_bytes",
             why="字节数与盘上不符（内容被动过而 sha 没重算的形态）"),
    ]
    probe12_rows = []
    for bad in bad_manifest:
        live = ident_row(bad["path"])
        fld = bad["detect_field"]
        # **按注入的那一个字段**判是否抓到（不是「任一字段不同就算抓到」——那样一条坏形态
        # 可以被另一条的副作用蒙过去）。
        caught = (live[fld] != bad[fld])
        probe12_rows.append({"injected_bad_form": {k: bad[k] for k in
                                                   ("path", "exists", "sha256_12", "n_bytes",
                                                    "measurement_status")},
                             "detect_field": fld, "claimed_by_manifest": bad[fld],
                             "live_measurement_of_that_field": live[fld],
                             "why_it_is_bad": bad["why"], "detected": bool(caught),
                             "live_measurement": live})
    good12 = ident_row(real)
    live12 = ident_row(real)
    fp12 = (good12["sha256_12"] == live12["sha256_12"] and good12["n_bytes"] == live12["n_bytes"]
            and good12["measurement_status"] == live12["measurement_status"])
    probe12 = {
        "ruling": "裁定 93.8（同上）",
        "auditor_under_test": "`ident_row` / 冻结面清单对账（MG2 用它登记 D 点名的件）",
        "injected_bad_form": [r["injected_bad_form"] for r in probe12_rows],
        "n_bad_forms": len(probe12_rows), "n_negative_controls": 1,
        "rows": probe12_rows,
        "negative_control": {"form": good12, "false_positive": (not fp12)},
        "detected": all(r["detected"] for r in probe12_rows) and fp12,
        "measurement_status": ("measured" if (all(r["detected"] for r in probe12_rows) and fp12)
                               else "not_measured"),
        "why_this_auditor_counts": ("MG2 的观测面就是这份清单；若它对「sha 不符 / 件不在 / "
                                    "字节数不符」三种形态都无感，那 MG2 登记的「冻结面身份」就是"
                                    "一份好看的登记表（缺陷类 ⑲ 的形态）"),
    }
    probe_blocks["frozen_surface_manifest"] = probe12
    rec("MG12", "对照探针 · 冻结面清单对账", "3 条坏形态全抓到 + 1 条好形态不误报",
        "%d/3 抓到，负对照误报=%s" % (sum(1 for r in probe12_rows if r["detected"]), not fp12),
        probe12["detected"],
        "裁定 93.8：清单审计器必须自带对照探针（注入已知坏形态：sha 不符 / 件不存在 / "
        "字节数不符），抓不到 ⇒ 审计器自己红",
        evidence={"real_row": real_row}, probe=probe12)

    # ---- MG13：归属不可判（两个门禁的**专属**标记同时命中）⇒ 必须拒收，不得静默走下去 ----
    # MG5 那个洞的**另一半**。洞有两段：① 标记表过宽（把通用裁定形状键当 ACT 归属证据）
    # ⇒ π₀.₅ 的逐臂产物**一律**变成多命中；② 多命中被 `infer_gate_id` 压成 `None`，而
    # `None` 又被读成「产物没有自述门禁 ⇒ 没有不一致」⇒ 跨门禁检查静默落空 ⇒
    # 构建号一对上就 `physical_fact` + **准入**。①由 MG5 的三形态钉住（现已全部
    # `wrong_gate_identity`），②由这一条钉住：**未测（0 命中）与不可判（≥2 命中）分开记**，
    # 后者拒收。档位沿用 `unidentified_build`（语义正是「连出自哪一版判据体系都说不清」），
    # 不新造词（裁定 31.4：词汇表扩项须先过 D）。
    p_amb = write_synth("ambiguous_both_gates_specific_markers.json",
                        [arm_row(act["gate_build"], artifact="c2_norm_contract_gate",
                                 gate_spec_sha256="0" * 12)])
    amb_row = json.loads(p_amb.read_text(encoding="utf-8"))[0]
    amb_cands = vi.infer_gate_id_candidates(amb_row)
    r_amb = vi.parse_verdict(p_amb)[0]                       # 缺省门禁 = ACT
    adm_amb = vi.admit_as_physical_fact(r_amb)
    # 负对照①：同一行去掉 ACT 的专属键 ⇒ 归属**可判**（π₀.₅）⇒ 不得被标成不可判
    p_unamb = write_synth("pi05_arm_unambiguous_control.json",
                          [arm_row(act["gate_build"], artifact="c2_norm_contract_gate")])
    r_unamb = vi.parse_verdict(p_unamb)[0]
    # 负对照②：一条纯 ACT 行、构建号=现值 ⇒ 不可判=False 且**准入**（证明这条牙不是恒红）
    p_act = write_synth("act_arm_plain_control.json", [arm_row(act["gate_build"])])
    r_act = vi.parse_verdict(p_act)[0]
    adm_act = vi.admit_as_physical_fact(r_act)
    mg13_checks = {
        "candidates_are_both_gates": amb_cands == (vi.DEFAULT_GATE_ID, vi.PI05_GATE_ID),
        "infer_gate_id_refuses_to_guess": vi.infer_gate_id(amb_row) is None,
        "record_flagged_ambiguous": (r_amb.artifact_gate_ambiguous is True),
        "level_is_unidentified_not_wrong_gate": (r_amb.usable_for == vi.USABLE_UNIDENTIFIED
                                                 and r_amb.gate_id_mismatch is None),
        "refused": (adm_amb["admitted"] is False),
        "refusal_names_the_reason": any("归属不可判" in x for x in adm_amb["refusal_reasons"]),
        "control1_unambiguous_not_flagged": (r_unamb.artifact_gate_ambiguous is False
                                             and r_unamb.usable_for == vi.USABLE_WRONG_GATE),
        "control2_plain_act_still_admitted": (r_act.artifact_gate_ambiguous is False
                                              and adm_act["admitted"] is True),
    }
    probe13 = {
        "ruling": ("裁定 93.8（同上）+ 裁定 27.1（牙必须双向）：这条牙自己也要证明"
                   "**不是恒红** —— 负对照②（纯 ACT 现构建行）必须仍然准入"),
        "auditor_under_test": ("归属不可判的检测与拒收链路：`infer_gate_id_candidates` → "
                               "`parse_verdict.artifact_gate_ambiguous` → `classify` → "
                               "`admit_as_physical_fact`"),
        "injected_bad_form": [amb_row],
        "n_bad_forms": 1, "n_negative_controls": 2,
        "negative_controls": [
            {"form": "同一行去掉 ACT 的专属键（归属**可判** = π₀.₅）",
             "expected": "artifact_gate_ambiguous=False，且由跨门禁那一路拒收（wrong_gate_identity）",
             "false_positive": bool(r_unamb.artifact_gate_ambiguous)},
            {"form": "一条纯 ACT 行、构建号 = 门禁现值",
             "expected": "artifact_gate_ambiguous=False 且**准入**（牙非恒红）",
             "false_positive": bool(r_act.artifact_gate_ambiguous or not adm_act["admitted"])},
        ],
        "detected": all(mg13_checks.values()),
        "measurement_status": ("measured" if all(mg13_checks.values()) else "not_measured"),
        "why_this_auditor_counts": ("这一段是 MG5 首跑**真红**的那一条路径：当时伪造构建号的 "
                                    "π₀.₅ 行被判成 `physical_fact` 且 `admitted=True`。"
                                    "若这条链路上任一环对「不可判」无感，那个洞就还在，"
                                    "而 MG5 的三形态**看不出来**（它们的归属现在是可判的）"),
    }
    probe_blocks["gate_attribution_ambiguity"] = probe13
    rec("MG13", "归属不可判 ⇒ 拒收（不得读成「没有不一致」）", "8/8 成立",
        "%d/8 成立" % sum(1 for v in mg13_checks.values() if v), all(mg13_checks.values()),
        "「未测」与「不可判」必须分开：0 命中 ⇒ `not_measured`、按声明门禁走下去；"
        "≥2 命中 ⇒ 归属不可判 ⇒ `unidentified_build` + **准入闸自己再判一次**拒收。"
        "两向都有牙：坏形态（专属标记同时命中 + 构建号伪造成现值）必须拒收，"
        "负对照（纯 ACT 现构建行）必须仍然准入",
        evidence={"checks": mg13_checks, "candidates": list(amb_cands),
                  "usable_for": r_amb.usable_for,
                  "admitted": adm_amb["admitted"],
                  "refusal_reasons": adm_amb["refusal_reasons"],
                  "control1": {"usable_for": r_unamb.usable_for,
                               "ambiguous": r_unamb.artifact_gate_ambiguous},
                  "control2": {"usable_for": r_act.usable_for, "admitted": adm_act["admitted"],
                               "ambiguous": r_act.artifact_gate_ambiguous}}, probe=probe13)

    # ---- 汇总 ----
    n_ok = sum(1 for r in rows if r["ok"] is True)
    n_bad = sum(1 for r in rows if r["ok"] is False)
    n_nm = sum(1 for r in rows if r["ok"] is None)
    declared_vs_measured = {"declared": {"teeth": N_TEETH, "ids": TOOTH_IDS},
                            "measured": {"teeth": len(rows),
                                         "ids": [r["id"] for r in rows]},
                            "agree": (len(rows) == N_TEETH
                                      and [r["id"] for r in rows] == TOOTH_IDS)}
    all_ok = (n_ok == len(rows) and n_bad == 0 and n_nm == 0 and declared_vs_measured["agree"]
              and all(p["detected"] for p in probe_blocks.values()))
    doc = {
        "artifact": "b2_registry_multigate_selfcheck",
        "task": "T-B2-20（D→B2 执行单 2026-09-30 §二）：registry/ 多门禁并存",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "generated_by": "scripts/b2_selfcheck_registry_multigate.py（B2 数据与判据线）",
        "module_under_test": ident_row("registry/verdict_identity.py"),
        "read_only_upstream": True, "policy_executed": False, "capability_claim": False,
        "gpu_touched": False,
        "all_ok": all_ok,
        "all_ok_criterion": ("每条牙 ok=True（无 False、无 not_measured）**且** 声明牙数==实测牙数"
                             "（裁定 92.3-ii）**且** 三个对照探针（`infer_gate_id` / "
                             "`frozen_surface_manifest` / `gate_attribution_ambiguity`）"
                             "都 `detected=true`（裁定 93.8）"),
        "n_teeth": len(rows), "n_ok": n_ok, "n_failed": n_bad, "n_not_measured": n_nm,
        "layer_counts_declared_vs_measured": declared_vs_measured,
        "gate_identities": {"act_controlled_success": act, "pi05_norm_contract": pi05},
        "pattern_coverage_probe": probe_blocks,
        "elapsed_s": round(time.time() - t0, 2),
        "teeth": rows,
        "write_scope": [str(OUT_DIR.relative_to(ROOT)) + "/**"],
        "ruling_refs": ["D→B2 执行单 2026-09-30 §二（T-B2-20）", "裁定 93.4（BC 准入对账）",
                        "裁定 93.8（对照探针 / 缺陷类 ⑲）", "裁定 92.3-ii（清单对账）",
                        "裁定 27.1（牙必须双向）", "裁定 21（判据单一来源）"],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    jp = Path(a.json_out) if a.json_out else (OUT_DIR / "MULTIGATE_SELFCHECK.json")
    if not jp.is_absolute():
        jp = ROOT / jp
    jp.write_text(json.dumps(doc, indent=1, ensure_ascii=False, default=str) + "\n",
                  encoding="utf-8")
    if not a.quiet:
        print("-" * 100)
        print("多门禁自检：%d/%d 成立（failed=%d not_measured=%d）⇒ all_ok=%s"
              % (n_ok, len(rows), n_bad, n_nm, all_ok))
        print("对照探针（裁定 93.8）：%s"
              % {k: v["detected"] for k, v in probe_blocks.items()})
        print("写出:", jp)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
