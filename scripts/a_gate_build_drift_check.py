#!/usr/bin/env python3
"""A 线：门禁构建漂移检查 + 重判前后逐臂逐局 diff（**只读**，不改任何裁定）。

为什么需要它：A-2 的预登记 `docs/a_bimodal_divergence_preregistration_20260928.md` §6 要求
「在 v1.2.1 单一构建上判」，但 `runs/infra/lerobot_act_env_20260928/ckptseq/` 的 16 份 gate
实测横跨 **7 个 gate_build**（B 在 21:16–21:52 期间实时升级门禁，`GATE_BUILD` = 脚本内容哈希）。
同一张表里的数字出自不同判据构建，跨臂/跨时间点比较不成立 —— 这正是
`scripts/a_regate_gate_current.py` docstring 与 `docs/b_handoff_to_a_20260928.md` §4 点名的
产物漂移，只不过这次漂在 A 自己的新产物里。

本脚本做两件事：
  1. `--check-single-build`：断言目录内所有 gate 的 (gate_version, gate_build, gate_spec_sha256)
     唯一，并与期望指纹比对。**期望指纹默认从权威表读**（`--authoritative-table`，见下），
     不在本脚本里硬编码 —— 硬编码正是本脚本要消灭的那类漂移（B 在
     `docs/b_handoff_to_a_20260928.md` §8.3bis 指出 A 原来的三个常量已被 v1.4 顶掉，A 采纳其选项 2）；
  2. `--diff-backup`：把重判后的 gate 与备份目录里的旧 gate 逐臂 diff
     （accounts 五计数 / measurement_valid / gate_pass / gate_reason / field_class /
       input_contract / **per_episode 逐局 verdict**），证明「换构建只换指纹、不换裁定」。

期望指纹的解析优先级（`--expect-version/--expect-build/--expect-spec` 三者可单独覆盖）：
  1. 命令行显式传入的 `--expect-*`；
  2. `--pin-a2-prereg`：钉到 A-2 预登记 §6 冻结的 v1.2.1 锚点（**故意**比对历史构建）；
  3. `--authoritative-table` 指向的权威表顶层 `gate_version/gate_build/gate_spec_sha256`
     （默认 `runs/infra/b_official_arms/reclassification.json`，B 每次升版本都会重跑并重写它
      ⇒ 默认值自动跟随「当前权威构建」，不会过期）；
  4. 都拿不到时回落到 A-2 锚点常量，并在输出里标 `expected_identity_source="fallback"`。

跨版本比对的口径（B §8.3bis 提醒，A 采纳）：v1.2.1 → v1.3 → v1.4 三次里**只有 v1.4 改了裁定语义**
（裁定 14 = `field_class != strict` 时弃权失效模式标签）。所以跨 v1.3/v1.4 比对时
**允许**出现「失效模式计数迁往 `n_unjudged`」这类差异（本脚本记为 `label_migration`）；
一旦 `controlled_success` 或 `provisional_pass` 变化就是**需要停下来查**的信号（记为 `stop_signal`）。

纪律：只读；旧 gate 一律 `mv` 进 `gate_build_drift_backup/`（禁 rm，见工作区 AGENTS.md）。

用法：
    # A-2：断言 ckptseq/ 钉在预登记 §6 的 v1.2.1 单一构建，并与漂移备份逐臂逐局对账
    python3 scripts/a_gate_build_drift_check.py --pin-a2-prereg \
        --dir runs/infra/lerobot_act_env_20260928/ckptseq \
        --diff-backup runs/infra/lerobot_act_env_20260928/ckptseq/gate_build_drift_backup \
        --json-out runs/infra/lerobot_act_env_20260928/ckptseq/build_drift_remediate_diff.json

    # 跨版本交叉核验（例：v1.4 重判写独立子目录后与 v1.2.1 对账，期望值默认跟随权威表）
    python3 scripts/a_gate_build_drift_check.py \
        --dir runs/infra/lerobot_act_env_20260928/ckptseq/v14_crosscheck \
        --diff-backup runs/infra/lerobot_act_env_20260928/ckptseq \
        --json-out runs/infra/lerobot_act_env_20260928/ckptseq/v14_crosscheck/crosscheck_diff.json
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

# A-2 预登记 §6 冻结的**历史锚点**（v1.2.1 = git commit 0137b33 的门禁脚本 + 同提交的 spec 文档）。
# 这不是「当前权威构建」——当前权威构建从 --authoritative-table 读，见下方解析优先级。
A2_PREREG_PINNED_VERSION = "v1.2.1"
A2_PREREG_PINNED_BUILD = "e4f5ec887788"
A2_PREREG_PINNED_SPEC = "494d5f5babf9"
# 「当前权威构建」的单一真值来源（B 每次升门禁都会重跑 b_regate_all 并重写它）
DEFAULT_AUTHORITATIVE_TABLE = "runs/infra/b_official_arms/reclassification.json"
# 跨版本比对时：这两个计数一变就必须停下查（B §8.3bis）
STOP_SIGNAL_COUNTS = ("controlled_success", "provisional_pass")
# 这两个计数的迁移（flick/insufficient_lift -> n_unjudged）是裁定 14 的预期效果，不算异常
LABEL_MIGRATION_COUNTS = ("flick", "insufficient_lift", "over_lift")

COUNT_KEYS = ("controlled_success", "provisional_pass", "over_lift", "flick", "insufficient_lift")
# gate_reason 不进 TOP_KEYS：它的人类可读文案随门禁版本变（v1.2.1 短句 / v1.3 附数值长句），
# 单独按 _reason_class() 比语义类别，文案差异记入 presentation_diffs。
TOP_KEYS = ("measurement_valid", "gate_pass", "field_class", "n_unjudged",
            "raw_success", "episodes_total", "n_provisional_pass", "n_over_lift",
            "composite_policy")
# input_contract 里**参与裁定**的键（改这些 = 改裁定）
IC_VERDICT_KEYS = ("status", "mean_blown_frames_frac", "tolerance", "violated", "unverified",
                   "not_applicable", "learned_policy", "rows_with_field", "rows_total")
# input_contract 里只做**表述/溯源**的键：v1.3 会多写 threshold_provenance / blown_metric_impl /
# artifact_gate_tolerance / gate_tolerance_matches，v1.2.1 不写；且 train_time_norm_absmax 在
# v1.2.1 取自 actlog 的 input_constraints（本项目 actlog 把它放在顶层 input_contract.blowup_threshold），
# 故 v1.2.1 报 null。这些都不改任何裁定，且溯源信息在 actlog 顶层 input_contract 里原样保留、
# a_ckptseq_verdict.py::collect 读的正是 actlog 那份（blowup_threshold/threshold_semantics/
# blown_metric_impl/stats_file 均取自 ic_eval），所以重判到 v1.2.1 **不丢溯源**。
IC_PRESENTATION_KEYS = ("train_time_norm_absmax", "note", "closed_loop_norm_absmax")


def _load(path: Path):
    try:
        doc = json.loads(path.read_text())
    except Exception:                                        # noqa: BLE001
        return None
    if isinstance(doc, list):
        return doc[0] if doc else None
    return doc


def _reason_class(g: dict) -> str:
    """gate_reason 的语义类别。v1.2.1 写短句（"measurement_invalid: 策略输入契约违例"），
    v1.3 写长句并附数值（"...: input_contract_violated: 闭环归一化输入超训练分布 0.0532 > 0.05"）。
    两者的**类别**相同 ⇒ 属表述差异，不是裁定差异。"""
    reason = str(g.get("gate_reason") or "")
    head = reason.split(":", 1)[0].strip()
    if head == "measurement_invalid":
        return "measurement_invalid"
    return head or reason


def _identity(g: dict) -> tuple:
    spec = g.get("gate_spec_sha256")
    return (g.get("gate_version"), g.get("gate_build"), (spec or "")[:12])


def _acct(g: dict, kind: str) -> dict:
    return (g.get("accounts") or {}).get(kind) or {}


def _ep_verdicts(g: dict) -> dict:
    out = {}
    for row in g.get("per_episode") or []:
        if isinstance(row, dict) and "seed" in row:
            out[int(row["seed"])] = row.get("verdict")
    return out


def read_current_authoritative(path: Path):
    """从权威表顶层读「当前权威构建」指纹。读不到返回 (None, None) 让调用方回落。"""
    doc = _load(path)
    if not isinstance(doc, dict):
        return None, None
    ident = (doc.get("gate_version"), doc.get("gate_build"),
             (doc.get("gate_spec_sha256") or "")[:12] or None)
    if all(ident):
        return ident, {"path": str(path), "git_commit": doc.get("git_commit"),
                       "n_artifacts": doc.get("n_artifacts")}
    return None, None


def scan(directory: Path) -> dict:
    """只收**门禁裁定**文档：必须同时有 gate_build 与 per_episode。
    否则本脚本自己写出的 gate_*.json 汇总（无这两个键）会被当成一份裁定扫进来。"""
    gates = {}
    for path in sorted(directory.glob("gate_*.json")):
        doc = _load(path)
        if doc and doc.get("gate_build") and "per_episode" in doc:
            gates[path.name] = doc
    return gates


def diff_one(name: str, old: dict, new: dict) -> dict:
    entry = {"gate": name, "old_identity": list(_identity(old)), "new_identity": list(_identity(new)),
             "identity_changed": _identity(old) != _identity(new),
             "verdict_diffs": [], "presentation_diffs": [], "episode_diffs": []}
    for key in TOP_KEYS:
        if old.get(key) != new.get(key):
            entry["verdict_diffs"].append({"field": key, "old": old.get(key), "new": new.get(key)})
    for kind in ("policy_independent", "system_assisted", "autonomous_learning"):
        o, n = _acct(old, kind), _acct(new, kind)
        if o.get("denominator") != n.get("denominator"):
            entry["verdict_diffs"].append({"field": f"{kind}.denominator",
                                           "old": o.get("denominator"), "new": n.get("denominator")})
        for ck in COUNT_KEYS:
            if o.get(ck) != n.get(ck):
                entry["verdict_diffs"].append({"field": f"{kind}.{ck}",
                                               "old": o.get(ck), "new": n.get(ck)})
    oic, nic = old.get("input_contract") or {}, new.get("input_contract") or {}
    for ik in IC_VERDICT_KEYS:
        if oic.get(ik) != nic.get(ik):
            entry["verdict_diffs"].append({"field": f"input_contract.{ik}",
                                           "old": oic.get(ik), "new": nic.get(ik)})
    for ik in IC_PRESENTATION_KEYS:
        if oic.get(ik) != nic.get(ik):
            entry["presentation_diffs"].append({"field": f"input_contract.{ik}",
                                                "old": oic.get(ik), "new": nic.get(ik)})
    entry["presentation_diffs"] += [
        {"field": f"input_contract.{k}_only_in_old", "old": oic.get(k), "new": None}
        for k in sorted(set(oic) - set(nic))]
    entry["presentation_diffs"] += [
        {"field": f"input_contract.{k}_only_in_new", "old": None, "new": nic.get(k)}
        for k in sorted(set(nic) - set(oic))]
    if _reason_class(old) != _reason_class(new):
        entry["verdict_diffs"].append({"field": "gate_reason_class",
                                       "old": _reason_class(old), "new": _reason_class(new)})
    if old.get("gate_reason") != new.get("gate_reason"):
        entry["presentation_diffs"].append({"field": "gate_reason_text",
                                            "old": old.get("gate_reason"),
                                            "new": new.get("gate_reason"),
                                            "same_class": _reason_class(old) == _reason_class(new)})
    oep, nep = _ep_verdicts(old), _ep_verdicts(new)
    for seed in sorted(set(oep) | set(nep)):
        if oep.get(seed) != nep.get(seed):
            entry["episode_diffs"].append({"seed": seed, "old": oep.get(seed), "new": nep.get(seed)})
    entry["verdict_identical"] = not entry["verdict_diffs"] and not entry["episode_diffs"]
    changed = {d["field"].rsplit(".", 1)[-1] for d in entry["verdict_diffs"]}
    entry["stop_signal_fields"] = sorted(f for f in changed
                                         if f.rsplit(".", 1)[-1] in STOP_SIGNAL_COUNTS)
    entry["label_migration_fields"] = sorted(
        f for f in changed
        if f.rsplit(".", 1)[-1] in LABEL_MIGRATION_COUNTS or f == "n_unjudged")
    entry["stop_signal"] = bool(entry["stop_signal_fields"])
    entry["label_migration_only"] = (not entry["verdict_identical"] and not entry["stop_signal"]
                                     and bool(entry["label_migration_fields"]))
    # 只换指纹/文案、不换裁定的判据：所有实体字段与逐局 verdict 都没变
    entry["fingerprint_only_change"] = entry["identity_changed"] and entry["verdict_identical"]
    return entry


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default="runs/infra/lerobot_act_env_20260928/ckptseq")
    ap.add_argument("--diff-backup", default=None,
                    help="重判前旧 gate 的备份目录（mv 进来的，不删）")
    ap.add_argument("--expect-version", default=None)
    ap.add_argument("--expect-build", default=None)
    ap.add_argument("--expect-spec", default=None)
    ap.add_argument("--pin-a2-prereg", action="store_true",
                    help="把期望指纹钉到 A-2 预登记 §6 的 v1.2.1 历史锚点（故意比对历史构建）")
    ap.add_argument("--authoritative-table", default=DEFAULT_AUTHORITATIVE_TABLE,
                    help="「当前权威构建」指纹的单一真值来源（顶层 gate_version/gate_build/gate_spec_sha256）")
    ap.add_argument("--check-single-build", action="store_true", default=True)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    # 期望指纹解析：显式 --expect-* > --pin-a2-prereg > 权威表 > 回落常量
    auth_ident, auth_meta = read_current_authoritative(Path(args.authoritative_table))
    if args.pin_a2_prereg:
        base = (A2_PREREG_PINNED_VERSION, A2_PREREG_PINNED_BUILD, A2_PREREG_PINNED_SPEC)
        source = "a2_preregistration_section6_pinned"
    elif auth_ident:
        base = auth_ident
        source = f"authoritative_table:{args.authoritative_table}"
    else:
        base = (A2_PREREG_PINNED_VERSION, A2_PREREG_PINNED_BUILD, A2_PREREG_PINNED_SPEC)
        source = "fallback_a2_prereg_pinned(权威表读不到)"
    expect_version = args.expect_version or base[0]
    expect_build = args.expect_build or base[1]
    expect_spec = args.expect_spec or base[2]
    if args.expect_version or args.expect_build or args.expect_spec:
        source = "cli_explicit_override"

    directory = Path(args.dir)
    gates = scan(directory)
    ids = sorted({_identity(g) for g in gates.values()})
    single = len(ids) == 1
    # 裁定 29 / DR-D28：**只有 build 轴能当钉子**。`GATE_BUILD = _sha12(门禁脚本自身)` 运行时现算
    # ⇒ 判据不可能在 build 不变时改变；`GATE_SPEC_SHA` 哈希的是**散文规格文档**，可在判据一字未动时
    # 被编辑（D 实测 35 分钟内移动 4 次）。所以 spec 不一致只作**观测**回显，不判 FAIL ——
    # 否则会周期性假红，把「B 改了一句文档」读成「判据漂移」。
    got_ident = list(ids[0]) if (single and ids) else None
    matches_version = bool(got_ident) and got_ident[0] == expect_version
    matches_build = bool(got_ident) and got_ident[1] == expect_build
    matches_spec = bool(got_ident) and got_ident[2] == expect_spec
    matches_expect = bool(got_ident) and matches_version and matches_build and matches_spec
    print(f"扫描 {directory}: {len(gates)} 份 gate，{len(ids)} 个不同 (version, build, spec)")
    for ident in ids:
        n = sum(1 for g in gates.values() if _identity(g) == ident)
        print(f"   {ident[0]:<8} build={ident[1]} spec={ident[2]}  x{n}")
    print(f"期望指纹 = {expect_version}/{expect_build}/spec {expect_spec}  (来源: {source})")
    if auth_ident:
        print(f"当前权威构建 = {auth_ident[0]}/{auth_ident[1]}/spec {auth_ident[2]}  "
              f"({args.authoritative_table})")
    print(f"SINGLE_BUILD={'PASS' if single else 'FAIL'}  "
          f"BUILD_AXIS_MATCHES_{expect_build}={'PASS' if matches_build else 'FAIL'}  "
          f"SPEC_AXIS={'match' if matches_spec else 'observation_only(裁定29:不判FAIL)'}")

    doc = {
        "check": "gate_build_drift_remediation",
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "script": "scripts/a_gate_build_drift_check.py",
        "read_only": True,
        "dir": str(directory),
        "n_gates": len(gates),
        "identities": [list(i) for i in ids],
        "single_build": single,
        "expected_identity": [expect_version, expect_build, expect_spec],
        "expected_identity_source": source,
        "current_authoritative_identity": (list(auth_ident) if auth_ident else None),
        "current_authoritative_meta": auth_meta,
        "matches_expected": matches_expect,
        "build_axis_matches": matches_build,
        "version_axis_matches": matches_version,
        "spec_axis_matches": matches_spec,
        "spec_axis_is_a_nail": False,
        "axis_ruling": ("裁定 29 / DR-D28：引用锚只在 **build 轴**（门禁脚本自身内容哈希，运行时现算）；"
                        "spec 轴哈希散文规格文档，可在判据一字未动时被编辑 ⇒ 只作观测，不判 FAIL。"
                        "权威口径的固定写法 = `v1.5 / f19f61341cbe`（**不带 spec 值**）。"),
        "why": ("A-2 预登记 §6 要求单一构建；本目录钉在 v1.2.1/"
                f"{A2_PREREG_PINNED_BUILD}/spec {A2_PREREG_PINNED_SPEC}（= 48 臂权威表落盘时所用指纹，"
                "git commit 0137b33）。当前权威构建可能已前进（见 current_authoritative_identity），"
                "跨版本比对用 --authoritative-table 的默认值即可。"),
        "pinned_gate_snapshot": "runs/infra/lerobot_act_env_20260928/gate_v121_pinned/",
        "per_arm": {name: {"identity": list(_identity(g)),
                           "measurement_valid": g.get("measurement_valid"),
                           "gate_pass": g.get("gate_pass"),
                           "gate_reason": g.get("gate_reason"),
                           "field_class": g.get("field_class"),
                           "raw_success": g.get("raw_success"),
                           "controlled_success": _acct(g, "policy_independent").get("controlled_success"),
                           "flick": _acct(g, "policy_independent").get("flick"),
                           "insufficient_lift": _acct(g, "policy_independent").get("insufficient_lift"),
                           "over_lift": _acct(g, "policy_independent").get("over_lift"),
                           "mean_blown_frames_frac": (g.get("input_contract") or {}).get("mean_blown_frames_frac")}
                    for name, g in sorted(gates.items())},
    }

    if args.diff_backup:
        backup = Path(args.diff_backup)
        olds = scan(backup)
        entries = []
        for name in sorted(set(olds) | set(gates)):
            old, new = olds.get(name), gates.get(name)
            if old is None or new is None:
                entries.append({"gate": name, "missing": "old" if old is None else "new",
                                "verdict_identical": False})
                continue
            entries.append(diff_one(name, old, new))
        n_ident = sum(1 for e in entries if e.get("verdict_identical"))
        n_fp = sum(1 for e in entries if e.get("fingerprint_only_change"))
        n_pres = sum(1 for e in entries if e.get("presentation_diffs"))
        doc["diff_backup"] = str(backup)
        doc["n_old_gates"] = len(olds)
        doc["n_compared"] = len(entries)
        doc["n_verdict_identical"] = n_ident
        doc["n_fingerprint_only_change"] = n_fp
        doc["n_with_presentation_only_diffs"] = n_pres
        doc["presentation_diff_policy"] = ("gate_reason 文案 / input_contract 溯源键（threshold_provenance、"
                                           "blown_metric_impl、train_time_norm_absmax、note 等）随门禁版本变化，"
                                           "不计入裁定差异；溯源在 actlog 顶层 input_contract 原样保留。")
        doc["all_verdicts_identical"] = (n_ident == len(entries) == len(olds) == len(gates))
        doc["n_stop_signal"] = sum(1 for e in entries if e.get("stop_signal"))
        doc["n_label_migration_only"] = sum(1 for e in entries if e.get("label_migration_only"))
        doc["stop_signal_counts"] = list(STOP_SIGNAL_COUNTS)
        doc["cross_version_policy"] = ("跨 v1.3/v1.4 比对允许「失效模式计数迁往 n_unjudged」(label_migration)；"
                                       "controlled_success / provisional_pass 一旦变化即 stop_signal，必须停下查。"
                                       "口径来源：docs/b_handoff_to_a_20260928.md §8.3bis。")
        doc["entries"] = entries
        print(f"\n与备份 {backup} 比对：{len(entries)} 臂，实体裁定完全一致 {n_ident}，"
              f"其中仅指纹变化 {n_fp}，含表述/溯源差异 {n_pres}")
        for e in entries:
            if not e.get("verdict_identical"):
                print(f"   VERDICT_DIFF {e['gate']}: "
                      f"{json.dumps(e.get('verdict_diffs'), ensure_ascii=False)[:300]}"
                      f" episodes={json.dumps(e.get('episode_diffs'), ensure_ascii=False)[:200]}")
            elif e.get("presentation_diffs"):
                fields = sorted({d["field"] for d in e["presentation_diffs"]})
                print(f"   presentation-only {e['gate']}: {fields}")
        print(f"ALL_VERDICTS_IDENTICAL={'PASS' if doc['all_verdicts_identical'] else 'FAIL'}  "
              f"STOP_SIGNAL={doc['n_stop_signal']}  LABEL_MIGRATION_ONLY={doc['n_label_migration_only']}")
        for e in entries:
            if e.get("stop_signal"):
                print(f"   STOP_SIGNAL {e['gate']}: {e['stop_signal_fields']} "
                      f"{json.dumps(e.get('verdict_diffs'), ensure_ascii=False)[:300]}")

    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
        print(f"\n写出: {args.json_out}")


if __name__ == "__main__":
    main()
