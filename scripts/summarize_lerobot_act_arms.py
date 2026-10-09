#!/usr/bin/env python3
"""把官方 LeRobot ACT 各臂的闭环真值评测 + 受控成功门禁汇总成一张表（只读）。

为什么需要它：一轮下来臂数超过 10 条（数据变体 × 训练 seed × 步数 × 归一化 × 重规划频率），
手工从 JSON 里拼数字容易出错、也容易把不同口径的臂混在一起比。本脚本只做三件事：
  1. 扫 `official_act_truth20_*.json`，从 checkpoint 的 `train_config.json` 反查
     数据集 / 步数 / 训练 seed / 归一化，从评测 JSON 反查闭环 replan 周期；
  2. 扫 `gate_*.json`，按 `file` 字段匹配回每条臂的受控成功裁定；
  3. 打印一张按「数据 -> 步数 -> seed -> replan」排序的表，并显式标注口径不可直接互比的地方。

2026-09-28 增补四起的额外职责（本脚本是 `arms_summary.json` 的**唯一**生产者，不要再写第二个）：
  4. **权威裁定合并**：5 个「盲臂」的留档产物缺 10 个逐局门禁字段（`field_class=partial`），
     其权威裁定改取 `blindfix/regate_current/`（补测产物，共有字段已证逐位相同），
     行内写 `superseded_by` 指回补测产物路径；留档原件一字节不动。
  5. **`validity_class`**（裁定 10）：三取值 `valid` / `VALID_probe_exonerated` / `invalid`，
     **不得**把免罪简写成 `valid`。免罪资格由 `probe_exoneration()` 在代码里逐条断言 5 项准入
     （含「C 必须 == 该 ckpt 自己的 `blowup_threshold`」），不靠约定。
  6. **`blowup_threshold_source`**（裁定 11）：每个 blown 数字都带阈值来源（哪个 ckpt 的哪份 stats、
     语义、数值），跨族不得混用同一把尺子。
  7. **裁定 8 推广**：失效模式标签（`flick` / `insufficient_lift` / `over_lift`）只在
     `field_class=strict` 下输出；非 strict 行一律显示 `-` 且**不进合计**。
     因此本表不再给出「48 臂合计受控 134 / insuff 219 / flick 23」这类混口径总数——
     它们把 INVALID 臂与非 strict 臂混进了分子，落盘后**禁止引用**。
  8. **显式分母**：`meta.denominators` 写清三分类计数（免罪前 / 免罪后）与各自的臂数基数。

2026-09-29 增补六（`rl_harness_supervision/supervisor_memo_20260929.md`）起的额外职责：
  9. **产物归属回显**（裁定 18.2）：一个臂的权威产物 = `supersedes` 链末端那一份；本表逐臂回显
     `adjudicated_artifact`（路径）+ `adjudicated_artifact_sha256`，并在 `meta.artifact_attribution.arm_paths`
     汇成一张 arm→产物 的表。动机是 D 实测出的真缺陷：同一臂名，B 的表指向 `reblown/` 链末端、
     A 的表固定指主目录旧产物 ⇒ 「计数层逐格相同」成立**只是因为重测恰好复现了同组计数**（运气不是机制）；
     换一个「重测后计数变了」的臂，两表会在**计数层**分叉而逐臂比数值的对账抓不到。
     回显路径 + sha256 之后，「比的是不是同一份东西」变成可核事实（对账判据在
     `scripts/a_migration_gate_preflight.py` 的 B6）。
 10. **行级 `provisional_pass` 列 + `counts_withheld_reason`**（裁定 20①②）：三套账的五项计数必须
     在**同一层级**可比（缺列会让 48×8 格逐臂对账永远差 48 格，把真分歧埋进噪声）；
     `measurement_valid=false` 的行行级失效模式计数**维持 `null`**（裁定 12：blown 超阈只作测量有效性门禁，
     不得当失败原因读），但必须写明 withhold 理由，且 `meta` 里声明「合计层包含被 withheld 的行级计数」，
     否则 `null` 与「未测量」不可区分、并会出现「行级求和 ≠ 合计」的表观矛盾。

不训练、不评测、不修改任何产物。

用法：
    python3 scripts/summarize_lerobot_act_arms.py \
        [--dir runs/infra/lerobot_act_env_20260928] [--json-out 路径]
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def ckpt_meta(pretrained_dir: str) -> dict:
    """从 checkpoint 的 train_config.json 反查训练侧口径。"""
    root = Path(pretrained_dir)
    for cand in (root, root.parent, root.parent.parent):
        cfg = cand / "train_config.json"
        if cfg.exists():
            try:
                d = json.loads(cfg.read_text())
            except json.JSONDecodeError:
                return {}
            ds = d.get("dataset", {})
            pol = d.get("policy", {})
            norm = pol.get("normalization_mapping") or {}
            return {
                "dataset_root": str(ds.get("root", "")),
                "steps": d.get("steps"),
                "train_seed": d.get("seed"),
                "batch_size": d.get("batch_size"),
                "action_norm": str(norm.get("ACTION", "")),
                "lr": pol.get("optimizer_lr"),
                "kl_weight": pol.get("kl_weight"),
                "use_vae": pol.get("use_vae"),
                "chunk_size": pol.get("chunk_size"),
            }
    return {}


def load_gate_index(directory: Path) -> dict:
    """把所有 gate/flick JSON 按它们记录的输入文件路径索引起来。"""
    idx = {}
    # 读取顺序 = 覆盖优先级（后读的赢）：
    #   1. flick_gate_*：最早的宽松口径（缺 final_rise 时判定偏松）；
    #   2. gate_*：受控成功判据的留档裁定（可能是旧构建）；
    #   3. regate_current/gate_*：由 scripts/a_regate_gate_current.py 用**当前**门禁构建重判的版本。
    # 这样表里的数字始终出自单一构建，且旧裁定一字节不改（改判前后可逐臂核对）。
    #   4. blindfix/regate_current/gate_*：5 个盲臂的**补测**裁定（增补三 §9.A②）。
    #      补测产物与留档在共有字段上逐位相同（blindfix/blindfix_vs_archived.json），
    #      但补齐了 10 个逐局门禁字段，field_class 由 partial 转 strict —— 所以它是权威裁定，
    #      排在最后（优先级最高）。留档产物与留档裁定都不改。
    #   5. reblown/regate_current/gate_*：blown 口径单一来源化（ADR-A-001）之后的**重测**裁定。
    #      重测产物与留档在共有字段上逐位相同（reblown/reblown_vs_archived_stdfloor_seed0.json：
    #      verdict=PASS、n_value_diffs_violating=0，唯一差异是 rows[].elapsed_sec + 新增键），
    #      但它是 B 表登记的 `supersedes` 链末端 ⇒ 按裁定 18.2 它才是该臂的权威产物，优先级最高。
    #      注意 basename 与主目录产物**同名**（同臂同题集的重测），所以本索引必须记 collision。
    sources = (sorted(directory.glob("flick_gate_*.json"))
               + sorted(directory.glob("gate_*.json"))
               + sorted((directory / "regate_current").glob("gate_*.json"))
               + sorted((directory / "blindfix" / "regate_current").glob("gate_*.json"))
               + sorted((directory / "reblown" / "regate_current").glob("gate_*.json")))
    collisions: dict[str, list[str]] = {}
    for path in sources:
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        entries = data if isinstance(data, list) else [data]
        for entry in entries:
            if not isinstance(entry, dict) or "file" not in entry:
                continue
            acct = (entry.get("accounts") or {}).get("policy_independent") or {}
            # 三种产物的「盲区」字段名不同，都要认，否则旧产物会被当成严格判定：
            #   早期 b_gate_controlled_success.py -> field_blindness
            #   b_flick_check.py                  -> has_final_rise_field=false
            #   v1.2 起的 b_gate_controlled_success.py -> field_class（strict / blind）
            blind = (entry.get("field_blindness") is not None
                     or entry.get("has_final_rise_field") is False
                     or (entry.get("field_class") is not None
                         and entry.get("field_class") != "strict"))
            ic = entry.get("input_contract") or {}
            indep = (entry.get("accounts") or {}).get("policy_independent") or {}
            bname = Path(entry["file"]).name
            prev = idx.get(bname)
            if prev is not None and prev.get("gate_artifact_file") != entry.get("file"):
                # 同一 basename、不同产物路径（主目录留档 vs blindfix/reblown 重测）。
                # 后读的赢（= 链末端），但必须留痕：否则「表里的数字出自哪份产物」不可核。
                seen = collisions.setdefault(bname, [prev.get("gate_artifact_file")])
                if entry.get("file") not in seen:
                    seen.append(entry.get("file"))
            idx[bname] = {
                "gate_file": str(path.relative_to(directory)) if path.is_relative_to(directory) else path.name,
                "gate_source_kind": ("blindfix_remeasure" if "blindfix" in path.parts
                                     else ("reblown_remeasure" if "reblown" in path.parts
                                           else ("regate_current" if path.parent.name == "regate_current"
                                                 else "archived"))),
                # 裁定 18.2：裁定 JSON 自己声明它判的是哪份产物 —— 归属回显以此为准，不靠 basename 猜
                "gate_artifact_file": entry.get("file"),
                "controlled": acct.get("controlled_success", entry.get("controlled_success")),
                "denominator": acct.get("denominator", entry.get("episodes_total")),
                "flick": acct.get("flick", entry.get("flick_success")),
                # v1.2 起「夹住了但没抬够」从 flick 里分出，指向的修复动作完全不同
                # （flick = 真脱手，insufficient_lift = dz 幅度不足），两列必须分开报。
                "insufficient_lift": acct.get("insufficient_lift"),
                "over_lift": acct.get("over_lift"),
                "provisional_pass": acct.get("provisional_pass", entry.get("provisional_pass")),
                "gate_pass": entry.get("gate_pass"),
                "measurement_valid": entry.get("measurement_valid"),
                "gate_reason": entry.get("gate_reason"),
                "field_class": entry.get("field_class"),
                "gate_version": entry.get("gate_version"),
                "gate_build": entry.get("gate_build"),
                "gate_spec_sha256": entry.get("gate_spec_sha256"),
                "composite_policy": entry.get("composite_policy"),
                # v1.5（DR-008 决定 5）起**门禁自己就会晋级** ic_status，并把通道 / 带检查 /
                # 会签 build 一致性回显在 `probe_exoneration` 对象里。A 必须读它，否则
                # 「门禁已判 probe_exonerated、A 却按旧逻辑重算」会把标签静默退回 valid
                # （违反 裁定 10「不得简写 valid」）。
                "_probe_exoneration_raw": (entry.get("probe_exoneration")
                                           if isinstance(entry.get("probe_exoneration"), dict) else {}),
                "probe_exoneration_status": ((entry.get("probe_exoneration") or {}).get("status")
                                             if isinstance(entry.get("probe_exoneration"), dict)
                                             else entry.get("probe_exoneration")),
                "probe_kind": ((entry.get("probe_exoneration") or {}).get("probe_kind")
                               if isinstance(entry.get("probe_exoneration"), dict) else None),
                "probe_band_checked": ((entry.get("probe_exoneration") or {}).get("band_checked")
                                       if isinstance(entry.get("probe_exoneration"), dict) else None),
                "probe_cosign_build": ((entry.get("probe_exoneration") or {}).get("cosign_gate_build")
                                       or (entry.get("probe_exoneration") or {}).get("cosign_build_at_cosign")
                                       if isinstance(entry.get("probe_exoneration"), dict) else None),
                "probe_cosign_build_current": ((entry.get("probe_exoneration") or {}).get("cosign_build_current")
                                               if isinstance(entry.get("probe_exoneration"), dict) else None),
                "probe_cosign_build_matches": ((entry.get("probe_exoneration") or {}).get("cosign_build_matches")
                                               if isinstance(entry.get("probe_exoneration"), dict) else None),
                "blind": blind,
                # 裁定 8 推广 / 裁定 10 / 裁定 11 需要的字段
                "_input_contract_raw": ic,
                "ic_status": ic.get("status"),
                "ic_mean_blown": ic.get("mean_blown_frames_frac"),
                "ic_tolerance": ic.get("tolerance"),
                "ic_closed_loop_absmax": ic.get("closed_loop_norm_absmax"),
                "accounts_independent": {k: indep.get(k) for k in
                                         ("controlled_success", "provisional_pass", "over_lift",
                                          "flick", "insufficient_lift", "denominator")},
                "per_episode_verdicts": {int(e["seed"]): e.get("verdict")
                                         for e in (entry.get("per_episode") or [])
                                         if isinstance(e, dict) and "seed" in e},
            }
    return idx, collisions


COUNT_KEYS = ("controlled_success", "provisional_pass", "over_lift", "flick", "insufficient_lift")


def threshold_source(eval_doc: dict, gate: dict | None = None) -> dict:
    """裁定 11：blown 阈值必须带来源。跨族不得混用同一把尺子（train24 族 23.8450 vs trimdone0 族 12.469445）。"""
    ic = eval_doc.get("input_contract") or {}
    gic = ((gate or {}).get("_input_contract_raw") or {})
    ck = eval_doc.get("checkpoint") or {}
    pm = ck.get("pretrained_model_dir", "")
    fam = ""
    meta = ckpt_meta(pm)
    if meta.get("dataset_root"):
        fam = Path(meta["dataset_root"]).name
    return {
        "blowup_threshold": ic.get("blowup_threshold"),
        "threshold_semantics": ic.get("threshold_semantics"),
        "stats_file": ic.get("stats_file"),
        "source_ckpt": pm,
        "dataset_family": fam or None,
        "blown_metric_impl": ic.get("blown_metric_impl"),
        "blown_metric_impl_note": (None if ic.get("blown_metric_impl") else
                                   "产物早于 blown 口径单一来源化补丁，未记录实现指纹；"
                                   "阈值语义与现行口径同（见 reblown/ 恒等回归证据）"),
        # 门禁侧的 ic 字段（status / tolerance / 闭环 absmax）与评测侧不同源，两边都要留证
        "gate_ic_status": gic.get("status"),
        "gate_ic_tolerance": gic.get("tolerance"),
        "gate_ic_mean_blown_frames_frac": gic.get("mean_blown_frames_frac"),
        "gate_ic_closed_loop_norm_absmax": gic.get("closed_loop_norm_absmax"),
        "gate_ic_train_time_norm_absmax": gic.get("train_time_norm_absmax"),
        "note": ("阈值按**该 checkpoint 自己的 normalizer stats** 现算，不是全局常量；"
                 "0.05 这条容差的强度依赖阈值，跨族引用必须写明来源。"),
    }


def _load_gate(directory: Path, rel: str):
    path = directory / rel
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    if isinstance(data, list):
        return data[0] if data else None
    return data if isinstance(data, dict) else None


def probe_exoneration(directory: Path, arm: str, eval_doc: dict, gate: dict) -> dict:
    """裁定 10：`measurement_invalid` 能否降级为 `VALID_probe_exonerated`——**5 条准入在代码里断言**。

    只有「blown 超阈」（`ic_status == "violated"`）的臂才走这条救济通道；「缺字段」（`unverified`）
    的正确处置是补测（`blindfix/`），不是免罪。
    """
    out = {"eligible": False, "arm": arm, "reason": "", "conditions": {}, "probe": None,
           "residual_row_diffs": []}
    if gate.get("measurement_valid") is not False:
        out["reason"] = "not_invalid"
        return out
    if gate.get("ic_status") != "violated":
        out["reason"] = f"invalid_for_other_reason:{gate.get('ic_status')}"
        return out

    ic = eval_doc.get("input_contract") or {}
    thr = ic.get("blowup_threshold")
    cdir = directory / "clipprobe"
    cands = sorted(cdir.glob(f"official_act_truth20_{arm}_clipC*.json"))
    if not cands:
        out["reason"] = "no_probe_product"
        return out

    plain_gate = _load_gate(directory, f"regate_current/gate_{arm}.json")
    best = None
    for cp in cands:
        try:
            cdoc = json.loads(cp.read_text())
        except json.JSONDecodeError:
            continue
        cval = (cdoc.get("execution_constraints") or {}).get("norm_input_clip")
        probe_stem = cp.name[len("official_act_truth20_"):-len(".json")]
        pgate = _load_gate(directory, f"clipprobe/regate_current/gate_{probe_stem}.json")
        rec = {"probe_file": str(cp.relative_to(directory)), "C": cval,
               "gate_file": f"clipprobe/regate_current/gate_{probe_stem}.json" if pgate else None,
               "gate_build": (pgate or {}).get("gate_build"),
               "gate_version": (pgate or {}).get("gate_version"),
               "probe_blown_metric_impl": ((cdoc.get("input_contract") or {}).get("blown_metric_impl")),
               "archived_blown_metric_impl": ((eval_doc.get("input_contract") or {}).get("blown_metric_impl"))}
        # 准入 1：C 必须**等于**该 ckpt 自己的训练期归一化 |x| 上界，不得用任意更紧的值。
        # （D 实测：同臂 C=5.0 的探针会翻转 seed 5007 的 verdict、把 insufficient_lift 从 1 打到 0，
        #   即「截得越紧越安全」是错的——紧到改变行为，它就不再是免罪探针，而是另一个策略。）
        rec["cond1_C_equals_train_absmax"] = bool(cval is not None and thr is not None
                                                  and float(cval) == float(thr))
        if not rec["cond1_C_equals_train_absmax"] or pgate is None or plain_gate is None:
            rec["cond2_verdicts_and_counts_identical"] = None
            best = best or rec
            continue
        pv = {int(e["seed"]): e.get("verdict") for e in (plain_gate.get("per_episode") or [])}
        qv = {int(e["seed"]): e.get("verdict") for e in (pgate.get("per_episode") or [])}
        pa = ((plain_gate.get("accounts") or {}).get("policy_independent") or {})
        qa = ((pgate.get("accounts") or {}).get("policy_independent") or {})
        verdict_diff = sorted(s for s in set(pv) | set(qv) if pv.get(s) != qv.get(s))
        count_diff = {k: [pa.get(k), qa.get(k)] for k in COUNT_KEYS if pa.get(k) != qa.get(k)}
        # 准入 2：逐局 verdict 全同 + accounts 五项计数全同（**裁定级不变**，不是逐位相同）
        rec["cond2_verdicts_and_counts_identical"] = not verdict_diff and not count_diff
        rec["verdict_diff_seeds"] = verdict_diff
        rec["count_diff"] = count_diff
        # 准入 3：仍有差异的逐局字段必须**枚举**（seed + 字段名），且这些局两条路径 verdict 相同
        diffs = []
        prows = {int(r["seed"]): r for r in cdoc.get("rows", [])}
        for r in eval_doc.get("rows", []):
            q = prows.get(int(r["seed"]))
            if not q:
                continue
            for k in sorted(set(r) & set(q)):
                if k == "elapsed_sec":
                    continue
                if r[k] != q[k]:
                    diffs.append({"seed": int(r["seed"]), "field": k,
                                  "plain": r[k], "probe": q[k],
                                  "verdict_plain": pv.get(int(r["seed"])),
                                  "verdict_probe": qv.get(int(r["seed"])),
                                  "verdict_same": pv.get(int(r["seed"])) == qv.get(int(r["seed"]))})
        rec["residual_row_diffs"] = diffs
        rec["cond3_diffs_enumerated_and_verdict_same"] = (
            all(d["verdict_same"] for d in diffs) if diffs else True)
        # 准入 4：探针路径 / C / gate_build 已登记（本 rec 即登记体）
        rec["cond4_probe_path_C_build_recorded"] = bool(rec["probe_file"] and rec["C"]
                                                        and rec["gate_build"])
        rec["all_conditions"] = all(rec[k] for k in (
            "cond1_C_equals_train_absmax", "cond2_verdicts_and_counts_identical",
            "cond3_diffs_enumerated_and_verdict_same", "cond4_probe_path_C_build_recorded"))
        if rec["all_conditions"]:
            best = rec
            break
        best = best or rec
    if best is None:
        out["reason"] = "no_usable_probe_gate"
        return out
    out["probe"] = best
    out["residual_row_diffs"] = best.get("residual_row_diffs", [])
    out["eligible"] = bool(best.get("all_conditions"))
    out["reason"] = "eligible" if out["eligible"] else "conditions_not_met"
    # 准入 5：免罪只作用于 measurement_valid，不改 composite_policy 与三套账（由调用方保证）
    out["cond5_scope_measurement_valid_only"] = True
    return out


VALIDITY_CLASSES = ("valid", "VALID_probe_exonerated", "invalid")


def probe_exoneration_citation(gate: dict, exon: dict | None) -> dict | None:
    """把「引用这条免罪必须带的东西」汇成一个块：C、探针路径 + sha256、五条准入、会签。

    来源优先级（裁定 21：门禁是 裁定 10 判据的**唯一来源**）：
      1. **门禁自己的回显**（v1.5 起 `judge_file` 把 `registered_clip_C` / `evidence_artifact` /
         `ruling10_conditions` / `cosign` 全写进 `probe_exoneration` 对象）；
      2. 回落：A 自己那份五条准入重算（`probe_exoneration()`，只在旧构建的留档裁定上才会走到）。
    为什么必须有这一列：`validity_class_definitions` 明文要求「引用时必须带 C 与探针路径」。
    v1.5 之后门禁**自己**就晋级了，A 的重算路径不再触发（`exon=None`），若只从 `exon` 取 C
    会把 C 和探针路径**静默丢成 null** —— 迁移当天就实测到了这个退化，故补本函数。
    """
    raw = gate.get("_probe_exoneration_raw") or {}
    if raw:
        return {
            "source": "gate_echo（门禁 v1.5 回显，裁定 21 的唯一来源）",
            "status": raw.get("status"),
            "probe_kind": raw.get("probe_kind"),
            "channel": raw.get("channel"),
            "scope": raw.get("scope"),
            "band_checked": raw.get("band_checked"),
            "C": raw.get("registered_clip_C"),
            "probe_clip_C": raw.get("probe_clip_C"),
            "artifact_train_absmax": raw.get("artifact_train_absmax"),
            "probe_artifact": raw.get("evidence_artifact"),
            "probe_sha256": raw.get("evidence_sha256"),
            "ruling10_conditions": raw.get("ruling10_conditions"),
            "cosign": raw.get("cosign"),
            "cosign_build_matches": raw.get("cosign_build_matches"),
            "ruling_ref": raw.get("ruling_ref"),
            "registry": raw.get("registry"),
            "registry_key": raw.get("key"),
        }
    if exon and exon.get("eligible"):
        probe = exon.get("probe") or {}
        return {
            "source": "a_side_recomputation（旧构建留档：门禁未回显，A 按 裁定 10 自算五条准入）",
            "status": "exonerated",
            "probe_kind": PROBE_KIND_CLIP,
            "C": probe.get("C"),
            "probe_artifact": probe.get("probe_file"),
            "probe_sha256": None,
            "ruling10_conditions": {k: v for k, v in exon.get("conditions", {}).items()
                                    if k.startswith("cond")},
            "ruling_ref": "裁定 10 / 裁定 16.4（A 侧重算，历史口径）",
        }
    return None

# 裁定 24⑤（DR-D21）：A 的 `VALID_probe_exonerated` 与 B 的 `ic_status=probe_exonerated`
# **不是同一概念**，v1.5 起长期是 1 对 2。A 的标签**只**对应 clip_at_train_absmax 通道
# （「原判 invalid 被 裁定 10 探针救回」）；reblown_single_source 通道在 A 表里维持 `valid`，
# 但**另列一列**回显 `probe_kind`。两表在「多少臂被豁免」上必然差 1，属**设计差异不是缺陷**；
# 任何对账必须按 probe_kind 分组比，不得直接比 `probe_exonerated` 计数。
PROBE_KIND_CLIP = "clip_at_train_absmax"
PROBE_KIND_REBLOWN = "reblown_single_source"
DEFAULT_B_TABLE = "runs/infra/b_official_arms/reclassification.json"


def classify_validity(gate: dict, exon: dict | None) -> tuple[str, str]:
    """裁定 10：把每条臂归入 `valid` / `VALID_probe_exonerated` / `invalid`（**不得**把免罪简写成 valid）。

    - `measurement_valid=False` 且 blown 超阈（`ic_status=violated`）→ 走探针救济，5 条准入全过才免罪；
    - `measurement_valid=False` 但根因是缺字段（`unverified`）→ 只能补测（`blindfix/`），维持 invalid；
    - `field_class != strict` → invalid（失效模式标签不可输出，裁定 8）。
    """
    if not gate:
        return "invalid", "no_gate_product:主目录/regate_current/blindfix 都找不到该产物的门禁裁定"
    mv = gate.get("measurement_valid")
    fc = gate.get("field_class")
    # ---- v1.5（DR-008 决定 5）：门禁**自己**就会把 ic_status 升为 probe_exonerated ----
    # 裁定 21：裁定 10 五条准入判据由**门禁独家执行**；A 不再自算一遍与之竞争。
    # 裁定 24⑤：只有 clip_at_train_absmax 通道对应 A 的 VALID_probe_exonerated；
    # reblown_single_source 通道维持 valid（另由 `probe_kind` 列回显），因为 A 的这个标签
    # 语义是「原判 invalid 被探针救回」，而 reblown 通道的臂从来没被判过 invalid。
    if gate.get("ic_status") == "probe_exonerated":
        kind = gate.get("probe_kind")
        if kind == PROBE_KIND_CLIP:
            return ("VALID_probe_exonerated",
                    "裁定10探针免罪（**门禁 v1.5 判定，A 不重算**）：ic_status 已由 violated 升为 "
                    "probe_exonerated，probe_kind=clip_at_train_absmax、band_checked=false；"
                    "只改 measurement_valid，三套账与 composite_policy 不动")
        return ("valid",
                f"门禁判 probe_exonerated 但走的是 {kind or '（未回显 kind）'} 通道 ⇒ 按 裁定 24⑤ "
                "在 A 表里维持 valid（该通道解除的是「blown 尺子不确定」的保留，不是「原判 invalid 被救回」）；"
                "通道由 probe_kind 列回显，不得与 clip 通道混计")
    if mv is False:
        if exon and exon.get("eligible"):
            return ("VALID_probe_exonerated",
                    "裁定10探针免罪：5 条准入在 probe_exoneration 里逐条断言通过；"
                    "只改 measurement_valid，三套账与 composite_policy 不动")
        why = (exon or {}).get("reason") or gate.get("gate_reason") or "measurement_invalid"
        return "invalid", f"measurement_invalid:{why}"
    if fc is not None and fc != "strict":
        return "invalid", f"field_class={fc}:缺逐局门禁字段，处置是补测不是免罪"
    if mv is None:
        return "invalid", "gate 未记录 measurement_valid"
    return "valid", ""


def scope_totals(sel: list[dict]) -> dict:
    """只对 `field_class=strict` 且非 invalid 的臂合计（裁定 8 推广 + 裁定 12）。"""
    t = {"arms": len(sel), "episodes": 0, "raw_success": 0, "controlled_success": 0,
         "provisional_pass": 0, "over_lift": 0, "flick": 0, "insufficient_lift": 0}
    for r in sel:
        t["episodes"] += int(r.get("episodes") or 0)
        t["raw_success"] += int(r.get("success_raw") or 0)
        t["controlled_success"] += int(r.get("controlled_success") or 0)
        if r.get("labels_reportable"):
            for k in ("provisional_pass", "over_lift", "flick", "insufficient_lift"):
                v = r.get(k)
                t[k] += int(v) if isinstance(v, int) else 0
    return t


def scope_totals_all(rows: list[dict]) -> dict:
    """全产物合计（**含 INVALID 臂**），只为与监管增补五 §3 的权威表逐格对账而存在。

    引用这一行必须同时说明：其中 `flick` 的 7 局有 5 局落在 2 个 INVALID 臂上（裁定 12：
    INVALID 只说明测量无效，不能当失败原因），可引用的 `flick` 只有 2 局 / 920。
    """
    t = {"arms": len(rows), "episodes": 0, "raw_success": 0, "controlled_success": 0,
         "provisional_pass": 0, "over_lift": 0, "flick": 0, "insufficient_lift": 0}
    for r in rows:
        t["episodes"] += int(r.get("episodes") or 0)
        t["raw_success"] += int(r.get("success_raw") or 0)
        t["controlled_success"] += int(r.get("controlled_success") or 0)
        for k, src in (("over_lift", "over_lift_raw"), ("flick", "flick_raw"),
                       ("insufficient_lift", "insufficient_lift_raw"),
                       # 裁定 20①：五项计数要在同一层级可比，合计层不再靠「行级没有这一列」偶然得 0
                       ("provisional_pass", "provisional_pass_raw")):
            v = r.get(src)
            t[k] += int(v) if isinstance(v, int) else 0
    valid_rows = [r for r in rows if r["validity_class"] == "valid"]
    t["citable_flick"] = {"episodes": sum(int(r.get("flick_raw") or 0) for r in valid_rows),
                          "denominator": sum(int(r.get("episodes") or 0) for r in valid_rows),
                          "note": "只在 measurement_valid 的臂上计数（裁定 12）"}
    t["reconciles_with"] = ("rl_harness_supervision/supervisor_memo_20260928.md 增补五 §3"
                            "（受控 135 / insuff 235 / flick 7 / over_lift 0 / provisional 0，"
                            "有效 46 / 无效 2，免罪后 47 / 1）")
    return t


# ---------------------------------------------------------------------------
# 裁定 30 / DR-D29：**计数层构建不变，分布层构建相关**。
#
#   - 计数层（逐局 verdict 计数）= 构建不变：v1.4→v1.5 实测 135/235/7/0/0/377 一格未动。
#   - 分布层（直方图 / 区间计数 / 极差 / 族均值的 n）= **构建相关**：它按 `measurement_valid`
#     的**臂集**统计，而臂集会被免罪 / 降级改变（实测无效臂 v1.2.1 = 7 → v1.5 = 1）。
#
# ⇒ 任何分布类陈述都必须同时带 ① 臂集 ② 快照 ③ 构建指纹 ④ 中间带孤立臂，缺一即不可引用。
# 下面的数字**全部从行里算**，一个都不写死（写死的版本号 / 计数在门禁每升一次后就过期一次）。
GAP_BAND_LOW = (0, 3)          # 裁定 30.1：低簇
GAP_BAND_HIGH = (14, 20)       # 裁定 30.1：高簇
# 裁定 30.2 的**禁用写法**。它们不是「措辞不雅」，而是**在现口径下为假**：
# 「4–9 臂数 = 0」在 v1.2.1 口径下成立（那时免罪臂是 INVALID、不在分布里），
# 在 v1.5 下被恰好 1 臂证伪 —— 那一臂就是 裁定 10 的免罪臂本尊（9/20）。
FORBIDDEN_DISTRIBUTION_PHRASINGS = (
    "受控成功落在 4–9 的臂数 = 0",
    "4–9 的臂数 = 0",
    "4–9 臂数 = 0",
    "中间是空的",
    "严格双峰、中间全空",
)
DISTRIBUTION_SNAPSHOT = "checkpoints/last（=020000，20k 快照）"


def _controlled_values(sel: list[dict]) -> list[int]:
    return sorted(int(r["controlled_success"]) for r in sel
                  if isinstance(r.get("controlled_success"), int))


def distribution_arm_set(label: str, definition: str, sel: list[dict]) -> dict:
    """一个**臂集**上的分布层事实（裁定 30.3 的四个限定里，前两个在这里回显）。"""
    vals = _controlled_values(sel)
    hist: dict[str, int] = {}
    for v in vals:
        hist[str(v)] = hist.get(str(v), 0) + 1
    lo, hi = GAP_BAND_LOW[0], GAP_BAND_LOW[1]
    hlo, hhi = GAP_BAND_HIGH[0], GAP_BAND_HIGH[1]

    def _in(a: int, b: int) -> int:
        return sum(1 for v in vals if a <= v <= b)

    middle = [r for r in sel
              if isinstance(r.get("controlled_success"), int)
              and (GAP_BAND_LOW[1] < r["controlled_success"] < GAP_BAND_HIGH[0])]
    return {
        "arm_set": label,
        "arm_set_definition": definition,
        "n_arms": len(sel),
        "n_with_controlled_success": len(vals),
        "snapshot": DISTRIBUTION_SNAPSHOT,
        "sorted_controlled_success": vals,
        "histogram": {k: hist[k] for k in sorted(hist, key=int)},
        "intervals": {
            f"low_{lo}_{lo + 3}": _in(lo, hi),
            "empty_band_4_8": _in(4, 8),
            "empty_band_10_13": _in(10, 13),
            f"high_{hlo}_{hhi}": _in(hlo, hhi),
            # 保留 4–9 的计数，但**只作为「禁用写法为何为假」的证据**，不得当结论引用
            "forbidden_window_4_9": _in(4, 9),
        },
        "middle_band_arms": [{"arm": r["arm"],
                              "controlled_success": r["controlled_success"],
                              "validity_class": r["validity_class"],
                              "probe_kind": r.get("probe_kind")} for r in middle],
        "range": {"min": vals[0] if vals else None, "max": vals[-1] if vals else None},
        # 裁定 30.1：准确定性是「强间隙分离」，不是「严格双峰、中间全空」
        "characterization": ("gap_separated" if middle and _in(4, 8) == 0 and _in(10, 13) == 0
                             else ("bimodal_middle_empty" if not middle else "mixed")),
    }


def distribution_layer(rows: list[dict], actlog_arms: list[str] | None,
                       gate_version: list[str], gate_build: list[str]) -> dict:
    """裁定 30.4 的代码承载：分布层统计**必须**随构建指纹一起出。"""
    valid = [r for r in rows if r["validity_class"] == "valid"]
    exonerated = [r for r in rows if r["validity_class"] == "VALID_probe_exonerated"]
    sets = {
        "official_all": distribution_arm_set(
            "official_all", f"官方集全 {len(rows)} 臂（含 INVALID；产物级）", rows),
        "measurement_valid": distribution_arm_set(
            "measurement_valid",
            f"`measurement_valid` 的 {len(valid) + len(exonerated)} 臂"
            f"（valid {len(valid)} + VALID_probe_exonerated {len(exonerated)}）",
            valid + exonerated),
    }
    if actlog_arms:
        by_name = {r["arm"]: r for r in rows}
        sub = [by_name[a] for a in actlog_arms if a in by_name]
        sets["actlog_subset"] = distribution_arm_set(
            "actlog_subset",
            f"`closed_loop_dz_diag_A.json` 的 {len(actlog_arms)} 个 actlog 臂"
            f"（join 命中 {len(sub)}）—— A-2 双峰预登记 §1 用的就是这个臂集",
            sub)
        sets["actlog_subset"]["join_missing_arms"] = [a for a in actlog_arms if a not in by_name]
    totals = scope_totals_all(rows)
    return {
        "ruling": "裁定 30 / DR-D29（增补七 §20）+ 裁定 29.1（引用锚只在 build 轴）",
        "build_fingerprint": {"gate_version": gate_version, "gate_build": gate_build,
                              "spec_axis": "observation_only（裁定 29.1：spec 不是钉子，不参与效力判定）"},
        "counting_layer": {
            "build_invariant": True,
            "values": {k: totals[k] for k in ("controlled_success", "insufficient_lift", "flick",
                                              "over_lift", "provisional_pass", "raw_success")},
            "rule": ("逐局 verdict 计数 = 构建不变（v1.4→v1.5 实测一格未动，裁定 28 ③）。"
                     "**限定在同一臂集（48 臂）内**：跨 n_artifacts 不同的历史口径不得直接相减（裁定 30.5）。"),
        },
        "distribution_layer": {
            "build_dependent": True,
            "rule": ("直方图 / 区间计数 / 极差 / 族均值的 n 按 `measurement_valid` 的**臂集**统计，"
                     "免罪或降级会改这个臂集 ⇒ **分布类陈述一律带构建指纹**（裁定 30.4）。"),
            "n_invalid_arms_this_build": len([r for r in rows if r["validity_class"] == "invalid"]),
            "n_invalid_arms_v1_2_1": 7,
        },
        "arm_sets": sets,
        "citation_requires_four_qualifiers": [
            "① 臂集（official_all / measurement_valid / actlog_subset）",
            f"② 快照（{DISTRIBUTION_SNAPSHOT}）",
            "③ 构建（`gate_version / gate_build`，见 build_fingerprint；**不带 spec**）",
            "④ 显式点出中间带的孤立臂（见各臂集 middle_band_arms）",
        ],
        "forbidden_phrasings": list(FORBIDDEN_DISTRIBUTION_PHRASINGS),
        "forbidden_phrasings_why": (
            "「4–9 = 0 / 中间是空的」在 v1.2.1 口径下成立（免罪臂当时是 INVALID、不在分布里），"
            "在 v1.5 下被恰好 1 臂证伪。空带是 **4–8 与 10–13**，不是「4–9」。"),
        "historical_citation_rule": {
            "must_report_n_artifacts": True,
            "why": ("裁定 30.5：v1.2.1 历史表 n_artifacts=44、计数 132/208/23/0/1/364，与本表 "
                    "48 臂 / 135/235/7/0/0/377 **不可直接相减**（多出 4 臂是 blindfix/reblown 重测世代）。"),
        },
        "executable_check": "scripts/a_distribution_layer_check.py（含禁用写法扫描 + 非恒真自检）",
    }


# 裁定 18.2 / 20 的改动必须是**纯附加**的：归属回显 + 两个行级字段，不动任何数字。
# 本函数把这句话变成可执行断言 —— 与留档基线逐臂逐键比对，只允许「归属类」键变化，
# 任何数值 / 分母 / 合计 / 分类变化都判 FAIL 并 exit 2（且**不写** --json-out，留档表不被污染）。
ATTRIBUTION_ALLOWED_DIFF_KEYS = ("gate_file", "gate_source_kind", "authoritative_eval_file",
                                 "blowup_threshold_source")
# 只有 `--allow-build-change`（= 一次真迁移）才允许这些键变：它们全是**判据构建的函数**，
# 门禁升版就会动。反过来说，**计数类**键（controlled_success / insufficient_lift / flick /
# over_lift / provisional_pass / *_raw / episodes / success_raw）与 meta 的分母、合计
# **一律不许动** —— 这正是 DR-008 验收判据 3「计数层一格不动」的可执行形式，也是 裁定 28
# 「能力结论一个字都不变」的机器担保。迁移时若这些数变了，说明迁的不是判据而是数据 ⇒ 必须 FAIL。
BUILD_MIGRATION_ALLOWED_DIFF_KEYS = (
    "gate_version", "gate_build", "gate_spec_sha256", "gate_file", "gate_source_kind",
    "gate_reason", "gate_pass", "gate_blind", "field_class",
    "measurement_valid", "ic_status", "ic_tolerance",
    "validity_class", "validity_reason", "citable",
    "probe_kind", "probe_exoneration", "probe_exoneration_status",
    "probe_exoneration_band_checked", "probe_cosign_build_matches",
    "authoritative_eval_file", "blowup_threshold_source",
    "insufficient_lift", "over_lift", "flick", "provisional_pass",
    "counts_withheld_reason", "labels_reportable",
)
# 计数类键：迁移时**绝对不许动**（与上面的白名单取交集只可能是标签可报性变化导致的 null↔int，
# 所以单独列出来做**显式**断言，比「不在白名单里」更能说明意图）。
COUNT_INVARIANT_KEYS = ("episodes", "success_raw", "insufficient_lift_raw", "over_lift_raw",
                        "flick_raw", "provisional_pass_raw", "gate_denominator",
                        "accounts_independent", "per_episode_verdicts")


def _denominator_numbers(meta: dict) -> dict:
    """从 meta.denominators 里只取**数字**（忽略 exonerated_arms 这类明细，迁移时它会新增 kind 字段）。"""
    den = (meta or {}).get("denominators") or {}
    out = {}
    for blk, val in den.items():
        if isinstance(val, dict):
            out[blk] = {k: v for k, v in val.items()
                        if isinstance(v, (int, float)) and not isinstance(v, bool)}
        elif isinstance(val, (int, float)) and not isinstance(val, bool):
            out[blk] = val
    return out


def regression_check(meta: dict, rows: list[dict], baseline: Path,
                     allow_build_change: bool = False) -> tuple[bool, dict]:
    old = json.loads(baseline.read_text(encoding="utf-8"))
    old_rows = {r["arm"]: r for r in (old.get("arms") or [])}
    new_arms = {r["arm"] for r in rows}
    diffs: list[dict] = []
    unexpected: list[dict] = []
    for r in rows:
        # 与基线比之前先把新行 JSON 往返一次：`per_episode_verdicts` 在内存里是 int 键，
        # 落盘再读回来是 str 键，不先归一会把 48 行全报成「非预期差异」（本断言自己抓到过这个坑）。
        r = json.loads(json.dumps(r, ensure_ascii=False))
        o = old_rows.get(r["arm"])
        if o is None:
            unexpected.append({"arm": r["arm"], "problem": "基线里没有这条臂"})
            continue
        for k, ov in o.items():
            if ov == r.get(k):
                continue
            item = {"arm": r["arm"], "key": k, "old": ov, "new": r.get(k)}
            allowed = ATTRIBUTION_ALLOWED_DIFF_KEYS
            if allow_build_change:
                allowed = allowed + BUILD_MIGRATION_ALLOWED_DIFF_KEYS
            if k in COUNT_INVARIANT_KEYS:
                # 计数层不变是 DR-008 验收判据 3；迁移也不例外 ⇒ 永远算 unexpected
                item["problem"] = "计数层变了（DR-008 验收判据 3：一格都不许动）"
                unexpected.append(item)
            elif k in allowed:
                diffs.append(item)
            else:
                unexpected.append(item)
    for arm in sorted(set(old_rows) - new_arms):
        unexpected.append({"arm": arm, "problem": "新表里少了这条臂"})

    old_meta = old.get("meta") or {}
    meta = json.loads(json.dumps(meta, ensure_ascii=False))
    if allow_build_change:
        # 迁移时分母/合计**仍然不许动**（只比数字，忽略 exonerated_arms 里新增的 kind 明细）
        if _denominator_numbers(old_meta) != _denominator_numbers(meta):
            unexpected.append({"meta_block": "denominators",
                               "problem": "迁移改动了三分类分母（应当只改判据构建，不改分母）",
                               "old": _denominator_numbers(old_meta),
                               "new": _denominator_numbers(meta)})
        if (old_meta.get("totals") or {}).get("scope_all_48_products_supervisor_reconcile") \
                != (meta.get("totals") or {}).get("scope_all_48_products_supervisor_reconcile"):
            unexpected.append({"meta_block": "totals.scope_all_48_products_supervisor_reconcile",
                               "problem": "迁移改动了 48 臂合计（DR-008 验收判据 3）",
                               "old": (old_meta.get("totals") or {}).get(
                                   "scope_all_48_products_supervisor_reconcile"),
                               "new": (meta.get("totals") or {}).get(
                                   "scope_all_48_products_supervisor_reconcile")})
    else:
        for blk in ("denominators", "totals"):
            if old_meta.get(blk) != meta.get(blk):
                unexpected.append({"meta_block": blk, "problem": "分母 / 合计发生变化",
                                   "old": old_meta.get(blk), "new": meta.get(blk)})
    if not allow_build_change:
        for k in ("gate_version", "gate_build", "gate_spec_sha256"):
            if old_meta.get(k) != meta.get(k):
                unexpected.append({"meta_block": k, "old": old_meta.get(k), "new": meta.get(k),
                                   "problem": "裁定构建变了（只有迁移才允许，需 --allow-build-change）"})
    ok = not unexpected
    sample_old = next(iter(old_rows.values())) if old_rows else {}
    return ok, {
        "check": ("arms_summary_build_migration_regression" if allow_build_change
                  else "arms_summary_attribution_regression"),
        "mode": ("build_migration（--allow-build-change：允许判据构建相关键变；"
                 "计数层 / 分母 / 合计仍不许动，DR-008 验收判据 3）" if allow_build_change
                 else "attribution_additive（只允许归属类键变 + 新增键）"),
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "baseline": str(baseline),
        # 裁定 35.3 / DR-D34（memo 增补十二 §42）：把护栏搬进断言产物本身。
        # 旁挂 README_BASELINE.md 是散文，下一个来「修口径」的人不会先读它 ⇒ 产物自带基线三值，
        # 基线一旦被刷，diff 一眼可见（机器护栏 = a_distribution_layer_check.py 的 D8
        # term `historical_meta_is_v121`，变异 S13/S14/S15 演示它会红）。
        "baseline_meta": {k: old_meta.get(k)
                          for k in ("gate_version", "gate_build", "gate_spec_sha256")},
        "baseline_meta_must_not_be_refreshed": (
            "DR-D34 / 裁定 35.1（memo 增补十二 §40）：本报告是 v1.2.1 -> v1.5 的**迁移断言**，"
            "baseline 的 meta 三值必须**停在 v1.2.1 / e4f5ec887788 / 494d5f5babf9**。"
            "把它刷成当前口径 = 把断言的左操作数改成右操作数，断言会退化成「v1.5 与 v1.5 比、差异 0」"
            "的恒真判据，DR-008 验收判据 3 与 裁定 28③ 就此失去机器担保。**不得刷新。**"),
        "verdict": "PASS" if ok else "FAIL",
        "rule": ("逐臂逐键比对：只允许归属类键（%s）变化 + 新增键；任何数值 / 分母 / 合计 / 分类变化判 FAIL"
                 % " / ".join(ATTRIBUTION_ALLOWED_DIFF_KEYS)),
        "n_rows": len(rows), "n_baseline_rows": len(old_rows),
        "new_row_keys": sorted(k for k in (rows[0] if rows else {}) if k not in sample_old),
        "n_expected_attribution_diffs": len(diffs),
        "expected_attribution_diffs": diffs,
        "n_unexpected": len(unexpected),
        "unexpected": unexpected[:200],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default="runs/infra/lerobot_act_env_20260928")
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--regression-baseline", default=None,
                    help="留档基线表；给了就跑「归属改动是纯附加的」断言，FAIL 则 exit 2 且不写 --json-out")
    ap.add_argument("--regression-out", default=None, help="断言报告的留档路径")
    ap.add_argument("--allow-build-change", action="store_true",
                    help="迁移到新 gate_build 时用：允许判据构建相关键变化；计数层 / 分母 / 合计仍不许动")
    ap.add_argument("--b-table", default=DEFAULT_B_TABLE,
                    help="B 的权威表（只读），用于 meta.exoneration_reconciliation 按 probe_kind 分组对账"
                         "（裁定 24⑤）；读不到就只登记 A 侧计数 + 规则，不阻断")
    ap.add_argument("--b-gate", default="scripts/b_gate_controlled_success.py",
                    help="门禁源码路径（只读），用来算 live GATE_BUILD = sha256[:12]，写进 cosign_provenance")
    ap.add_argument("--actlog-diag", default="closed_loop_dz_diag_A.json",
                    help="A-2 双峰预登记的 actlog 臂名单（只读，默认在 --dir 下找同名文件）；"
                         "用于 meta.distribution_layer 的 actlog_subset 臂集（裁定 30）。读不到就跳过该臂集，不阻断")
    args = ap.parse_args()

    directory = Path(args.dir)
    gates, gate_collisions = load_gate_index(directory)
    rows = []
    for path in sorted(directory.glob("official_act_truth20_*.json")):
        arm = path.name.replace("official_act_truth20_", "").replace(".json", "")
        gate = gates.get(path.name, {})
        # 增补三 §9.A②：5 个盲臂的**权威**产物是 blindfix/ 的补测（共有字段已证逐位相同，
        # 只是补齐了 10 个逐局门禁字段）。整行数字都取权威产物，避免「评测数字来自留档、
        # 门禁数字来自补测」的混源行；留档原件一字节不动，用 superseded_by 指过去。
        doc = json.loads(path.read_text())
        superseded_by, eval_source = None, path.name
        attribution_kind = "main_dir_only"
        if gate.get("gate_source_kind") == "blindfix_remeasure":
            bf = directory / "blindfix" / path.name
            if bf.exists():
                doc = json.loads(bf.read_text())
                superseded_by = f"blindfix/{path.name}"
                eval_source = superseded_by
                attribution_kind = "blindfix_remeasure"
        elif gate.get("gate_source_kind") == "reblown_remeasure":
            # 裁定 18.2：臂的权威产物 = `supersedes` 链末端。stdfloor seed0 的链末端是 reblown/ 的重测产物。
            # **故意不设 `superseded_by`**：该字段在本表专指「权威产物在本表另有其行」的 blind 重测组，
            # 设了会把这条**互异实验**从 dedup 分母里踢掉（43 → 42），属口径事故。归属改用
            # `adjudicated_artifact` / `attribution_kind` 表达（见下）。
            rb = directory / "reblown" / path.name
            if rb.exists():
                doc = json.loads(rb.read_text())
                eval_source = f"reblown/{path.name}"
                attribution_kind = "reblown_remeasure"
        # 裁定 18.2：回显「本行数字实际出自哪份产物」+ 它的 sha256，并列出该臂的 supersedes 链
        adj_path = directory / eval_source
        adjudicated_artifact = _rel(adj_path)
        adjudicated_sha = _sha256_file(adj_path)
        chain = [_rel(directory / f"{pfx}{path.name}") for pfx in ("", "blindfix/", "reblown/")
                 if (directory / f"{pfx}{path.name}").is_file()]
        ck = doc.get("checkpoint", {})
        meta = ckpt_meta(ck.get("pretrained_model_dir", ""))
        ds_root = meta.get("dataset_root", "")
        data = Path(ds_root).name if ds_root else "?"
        rises = [r["max_rise"] for r in doc.get("rows", [])]

        # 免罪只对「blown 超阈」开放；缺字段的 invalid 不走这条通道（见 classify_validity）
        exon = None
        if gate.get("measurement_valid") is False and gate.get("ic_status") == "violated":
            exon = probe_exoneration(directory, arm, doc, gate)
        validity, validity_reason = classify_validity(gate, exon)
        labels_reportable = (gate.get("field_class") == "strict" and validity != "invalid")
        ctrl = gate.get("controlled")
        # 裁定 20②：行级失效模式计数维持 null（裁定 12），但必须写明为什么 withhold
        if labels_reportable:
            counts_withheld_reason = None
        elif gate.get("measurement_valid") is False:
            counts_withheld_reason = "measurement_invalid"
        else:
            counts_withheld_reason = "field_class_not_strict"

        # 裁定 24⑤：`probe_kind` 是**独立一列**，不管走哪条通道都回显（无豁免的臂为 null）。
        # 门禁 v1.5 起自己回显 kind；旧构建（v1.2.1 留档）下 kind 由 A 自己的免罪重算得出，
        # 而那条重算路径只可能是 clip 通道（probe_exoneration() 就是照 裁定 10 写的）。
        probe_kind = gate.get("probe_kind")
        if not probe_kind and exon and exon.get("eligible"):
            probe_kind = PROBE_KIND_CLIP

        rows.append({
            "arm": arm,
            "file": path.name,
            "authoritative_eval_file": eval_source,
            "superseded_by": superseded_by,
            "gate_source_kind": gate.get("gate_source_kind"),
            "attribution_kind": attribution_kind,
            "adjudicated_artifact": adjudicated_artifact,
            "adjudicated_artifact_sha256": adjudicated_sha,
            "supersedes_chain": chain,
            "data": data,
            "steps": meta.get("steps"),
            "train_seed": meta.get("train_seed"),
            "action_norm": (meta.get("action_norm") or "").replace("NormalizationMode.", ""),
            "lr": meta.get("lr"),
            "kl_weight": meta.get("kl_weight"),
            "use_vae": meta.get("use_vae"),
            "replan_every": doc.get("replan_every", doc.get("n_action_steps")),
            "chunk_size": doc.get("chunk_size"),
            "episodes": doc.get("episodes"),
            "success_raw": doc.get("success_raw"),
            "grasp_verified": doc.get("grasp_verified"),
            "success_rise": doc.get("success_rise"),
            "mean_max_rise": round(float(doc.get("mean_max_rise", 0.0)), 4),
            "mean_final_rise": (round(float(doc["mean_final_rise"]), 4)
                                if doc.get("mean_final_rise") is not None else None),
            "held_at_end": doc.get("held_at_end_count"),
            "max_rise_p90": round(float(np.percentile(rises, 90)), 4) if rises else None,
            "failure_phases": doc.get("failure_phase_counts"),
            "controlled_success": ctrl,
            "gate_denominator": gate.get("denominator"),
            "gate_pass": gate.get("gate_pass"),
            "gate_blind": gate.get("blind"),
            "field_class": gate.get("field_class"),
            "measurement_valid": gate.get("measurement_valid"),
            "ic_status": gate.get("ic_status"),
            "ic_mean_blown_frames_frac": gate.get("ic_mean_blown"),
            "ic_tolerance": gate.get("ic_tolerance"),
            "gate_reason": gate.get("gate_reason"),
            "gate_version": gate.get("gate_version"),
            "gate_build": gate.get("gate_build"),
            "gate_spec_sha256": gate.get("gate_spec_sha256"),
            "composite_policy": gate.get("composite_policy"),
            # 裁定 8 推广：非 strict 行的失效模式标签一律置 None，且不进任何合计
            "insufficient_lift": gate.get("insufficient_lift") if labels_reportable else None,
            "over_lift": gate.get("over_lift") if labels_reportable else None,
            "flick": gate.get("flick") if labels_reportable else None,
            "insufficient_lift_raw": gate.get("insufficient_lift"),
            "over_lift_raw": gate.get("over_lift"),
            "flick_raw": gate.get("flick"),
            # 裁定 20①：行级补 provisional_pass 列（值来自同一份裁定 JSON，不重跑评测）
            "provisional_pass": gate.get("provisional_pass") if labels_reportable else None,
            "provisional_pass_raw": gate.get("provisional_pass"),
            "labels_reportable": labels_reportable,
            "counts_withheld_reason": counts_withheld_reason,
            "accounts_independent": gate.get("accounts_independent"),
            "per_episode_verdicts": gate.get("per_episode_verdicts"),
            # 裁定 10 / 11 / 24⑤
            "validity_class": validity,
            "validity_reason": validity_reason or None,
            "probe_kind": probe_kind,
            "probe_exoneration_citation": (probe_exoneration_citation(gate, exon)
                                           if (validity == "VALID_probe_exonerated" or probe_kind)
                                           else None),
            "probe_exoneration_status": gate.get("probe_exoneration_status"),
            "probe_exoneration_band_checked": gate.get("probe_band_checked"),
            "probe_cosign_build_matches": gate.get("probe_cosign_build_matches"),
            "probe_exoneration": exon,
            "blowup_threshold_source": threshold_source(doc, gate),
            "citable": bool(validity != "invalid" and isinstance(ctrl, int) and ctrl > 0),
            "gate_file": gate.get("gate_file"),
            "ckpt_sha8": (ck.get("model_safetensors_sha256") or "")[:8],
        })

    def sort_key(r):
        return (str(r["data"]), str(r["steps"]), str(r["train_seed"]),
                str(r["action_norm"]), str(r["kl_weight"]), int(r["replan_every"] or 0), r["arm"])

    rows.sort(key=sort_key)

    # ---- 三分类分母（显式，禁止再引混口径的 134/219/23）--------------------
    invalid = [r for r in rows if r["validity_class"] == "invalid"]
    exonerated = [r for r in rows if r["validity_class"] == "VALID_probe_exonerated"]
    valid = [r for r in rows if r["validity_class"] == "valid"]
    citable_pre = [r for r in valid if r["citable"]]
    zero_pre = [r for r in valid if not r["citable"]]
    citable_post = [r for r in valid + exonerated if r["citable"]]
    zero_post = [r for r in valid + exonerated if not r["citable"]]
    dedup = [r for r in valid + exonerated if not r["superseded_by"]]
    dedup_citable = [r for r in dedup if r["citable"]]
    # dedup 口径与「免罪后」同基准：被免罪的臂不再算 invalid
    dedup_invalid = len(invalid)

    # ---- 裁定 24⑤：A / B 两表的豁免计数**按 probe_kind 分组**对账（不得直接比裸计数）----
    a_by_kind: dict[str, int] = {}
    for r in rows:
        if r.get("probe_kind"):
            a_by_kind[r["probe_kind"]] = a_by_kind.get(r["probe_kind"], 0) + 1
    b_doc: dict = {}
    b_path = Path(args.b_table)
    if not b_path.is_absolute():
        b_path = Path.cwd() / b_path
    if b_path.is_file():
        try:
            b_doc = json.loads(b_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            b_doc = {}
    b_sum = (b_doc.get("summary") or {}) if isinstance(b_doc, dict) else {}
    b_by_kind = b_sum.get("probe_exoneration_by_kind") or {}
    b_n_exo = ((b_sum.get("ic_status") or {}).get("probe_exonerated")
               if isinstance(b_sum.get("ic_status"), dict) else None)
    exon_recon = {
        "ruling": "裁定 24⑤ / DR-D21（增补登记 09-29 11:0x）+ 裁定 21（门禁是 裁定 10 判据唯一来源）",
        "rule": ("**按 probe_kind 分组比**，不得直接比 `probe_exonerated` 计数。A 的 "
                 "`VALID_probe_exonerated` 只对应 clip_at_train_absmax（语义 = 「原判 invalid 被探针救回」）；"
                 "B 的 `ic_status=probe_exonerated` 含两条通道 ⇒ 两表被豁免臂数**必然差 1**，"
                 "属**设计差异不是缺陷**。"),
        "a_side": {"n_VALID_probe_exonerated": len(exonerated),
                   "arms": [{"arm": r["arm"], "probe_kind": r["probe_kind"]} for r in exonerated],
                   "probe_kind_column_counts": a_by_kind,
                   "note": ("`probe_kind` 是**独立一列**，与 validity_class 解耦：走 reblown 通道的臂在 A 表里"
                            "维持 `valid`，但仍回显 kind（裁定 24⑤ 明文要求）")},
        "b_side": {"table": str(b_path) if b_doc else None,
                   "readable": bool(b_doc),
                   "gate_version": b_doc.get("gate_version") if b_doc else None,
                   "gate_build": b_doc.get("gate_build") if b_doc else None,
                   "n_probe_exonerated": b_n_exo,
                   "probe_exoneration_by_kind": b_by_kind},
        "design_difference": ((b_n_exo - len(exonerated))
                              if isinstance(b_n_exo, int) else None),
        "clip_channel_agrees": (b_by_kind.get(PROBE_KIND_CLIP) == len(exonerated))
        if isinstance(b_by_kind, dict) and b_by_kind else None,
        "reblown_channel_arms_in_a": [r["arm"] for r in rows
                                      if r.get("probe_kind") == PROBE_KIND_REBLOWN],
        "cross_check": ("scripts/a_migration_gate_preflight.py 的 B8（B 表可按 kind 分组）+ "
                        "P7（A 表按 kind 分组对账）"),
    }

    # ---- 裁定 30 / DR-D29：分布层统计必须随构建指纹一起出（计数层构建不变、分布层构建相关）----
    actlog_arms: list[str] = []
    actlog_path = Path(args.actlog_diag)
    if not actlog_path.is_absolute():
        actlog_path = directory / Path(args.actlog_diag).name
    if actlog_path.is_file():
        try:
            dz = json.loads(actlog_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            dz = {}
        raw_arms = dz.get("arms") if isinstance(dz, dict) else None
        if isinstance(raw_arms, list):
            actlog_arms = [a if isinstance(a, str) else str(a.get("arm") or a.get("name"))
                           for a in raw_arms]
    dist_layer = distribution_layer(
        rows, actlog_arms or None,
        sorted({str(r.get("gate_version")) for r in rows if r.get("gate_version")}),
        sorted({str(r.get("gate_build")) for r in rows if r.get("gate_build")}))
    dist_layer["actlog_source"] = (str(actlog_path) if actlog_arms else None)

    # ---- 裁定 27：会签锚在哪个 build 上是**可核事实**，必须随数字一起走 ----
    live_build = None
    gate_src_path = Path(args.b_gate)
    if not gate_src_path.is_absolute():
        gate_src_path = Path.cwd() / gate_src_path
    if gate_src_path.is_file():
        live_build = hashlib.sha256(gate_src_path.read_bytes()).hexdigest()[:12]
    exo_arms_cosign = [{"arm": r["arm"], "probe_kind": r["probe_kind"],
                        "cosign_build_matches": r.get("probe_cosign_build_matches"),
                        "band_checked": r.get("probe_exoneration_band_checked")}
                       for r in rows if r.get("probe_kind")]
    n_not_matched = sum(1 for a in exo_arms_cosign if a["cosign_build_matches"] is False)
    cosign_provenance = {
        "ruling": "裁定 16.4（条目由 B 写、**D 会签**）+ DR-008 决定 7 + 裁定 25 / DR-D22 + 裁定 27",
        "live_gate_build": live_build,
        "per_arm": exo_arms_cosign,
        "n_cosign_build_mismatch": n_not_matched,
        "tri_state_semantics": ("`cosign_build_matches`：**True** = 会签已锚在 live build；"
                                "**False** = 会签锚在旧 build、待 D 复签换块（按决定 7 **不拒判**）；"
                                "**null** = 该通道**不要求** D 会签（reblown_single_source 走增补三 §12，"
                                "门禁只在 裁定 10 的 clip 通道里产出这个字段）。三者不得混为一谈。"),
        "citation_rule": ("引用本表任何被豁免臂的数字时，必须**同时**注明它的 `probe_kind` 与 "
                          "`cosign_build_matches`；matches=False 期间还要注明「按 DR-008 决定 7 不拒判但待复签换块」"
                          "（裁定 27）。"),
        "pending_bucket_ref": ("B 表 `summary.pending_cosign_reverify`（裁定 25 护栏①）；A 侧对账判据 = "
                               "scripts/a_migration_gate_preflight.py 的 B7 / B7b"),
    }

    thr_families = {}
    for r in rows:
        ts = r["blowup_threshold_source"] or {}
        key = (ts.get("dataset_family"), ts.get("blowup_threshold"))
        thr_families.setdefault(str(key[0]), {"blowup_threshold": key[1], "arms": 0,
                                              "stats_file": ts.get("stats_file"),
                                              "threshold_semantics": ts.get("threshold_semantics")})
        thr_families[str(key[0])]["arms"] += 1

    meta = {
        "schema_version": 3,
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "producer": "scripts/summarize_lerobot_act_arms.py",
        "producer_sha256_12": hashlib.sha256(
            Path(__file__).read_bytes()).hexdigest()[:12],
        "source_dir": str(directory),
        "read_only": True,
        "gate_version": sorted({str(r.get("gate_version")) for r in rows if r.get("gate_version")}),
        "gate_build": sorted({str(r.get("gate_build")) for r in rows if r.get("gate_build")}),
        "gate_spec_sha256": sorted({str(r.get("gate_spec_sha256")) for r in rows
                                    if r.get("gate_spec_sha256")}),
        "arm_basis": {
            "counting_unit": "主目录一份 official_act_truth20_*.json = 一臂一行（产物级计数）",
            "total_arms": len(rows),
            "duplicate_remeasure_groups": [
                {"arm": r["arm"], "archived": r["file"], "authoritative": r["authoritative_eval_file"],
                 "gatefields_sibling": (f"official_act_truth20_{r['arm']}_gatefields.json"
                                        if (directory / f"official_act_truth20_{r['arm']}_gatefields.json").exists()
                                        else None)}
                for r in rows if r["superseded_by"]
            ],
            "note": ("5 个盲臂各有 3 份产物（留档 blind / 主目录 *_gatefields 重测 / blindfix 补测），"
                     "本表按**产物级**计数，因此 blind 行与 _gatefields 行都各占一行；"
                     "blind 行的权威数字取 blindfix（superseded_by），二者共有字段已证逐位相同"
                     "（blindfix/blindfix_vs_archived.json，5/5 IDENTICAL_ON_COMMON_FIELDS）。"
                     "要按**互异训练 run** 计数必须先去重，本表不做去重，以与 24/22/2 口径一致。"),
        },
        # 裁定 18.2（增补六 §2.2）：产物归属回显 —— 让「比的是同一份东西」成为可核事实
        "artifact_attribution": {
            "ruling": "裁定 18.2（rl_harness_supervision/supervisor_memo_20260929.md §2.2）",
            "rule": ("一个臂的**权威产物 = `supersedes` 链末端那一份**，不得固定指主目录；"
                     "逐臂回显被裁定产物路径 + sha256。对账判据在 "
                     "scripts/a_migration_gate_preflight.py 的 B6（A 表 vs B 表逐臂比归属）。"),
            "arm_paths": {r["arm"]: {"adjudicated_artifact": r["adjudicated_artifact"],
                                     "sha256": r["adjudicated_artifact_sha256"],
                                     "chain": r["supersedes_chain"],
                                     "attribution_kind": r["attribution_kind"]}
                          for r in rows},
            "remeasure_groups": [
                {"arm": r["arm"], "attribution_kind": r["attribution_kind"],
                 "adjudicated_artifact": r["adjudicated_artifact"], "chain": r["supersedes_chain"],
                 "identity_regression_evidence": (
                     "runs/infra/lerobot_act_env_20260928/reblown/reblown_vs_archived_stdfloor_seed0.json"
                     if r["attribution_kind"] == "reblown_remeasure"
                     else "runs/infra/lerobot_act_env_20260928/blindfix/blindfix_vs_archived.json")}
                for r in rows if r["attribution_kind"] != "main_dir_only"],
            "gate_index_basename_collisions": gate_collisions,
            "why_not_superseded_by": (
                "`superseded_by` 在本表专指「权威产物在本表**另有其行**」的 blind 重测组（它参与 dedup 分母的剔除）。"
                "reblown 重测**没有**自己的行，若也写 superseded_by 会把该臂这条互异实验从 dedup 分母里踢掉"
                "（43 → 42）⇒ 属口径事故。归属改用 adjudicated_artifact / attribution_kind 表达，"
                "dedup 分母一字节不变。"),
            "collision_note": ("`gate_index_basename_collisions` 记「同一 basename、不同产物路径」的裁定索引冲突"
                               "（主目录留档 vs 重测）。后读的赢 = 链末端；留痕是为了让「表里数字出自哪份产物」可核。"),
        },
        "denominators": {
            "total_arms": len(rows),
            "pre_probe_exoneration": {
                "citable": len(citable_pre), "valid_zero_success": len(zero_pre),
                # 免罪前口径下，被免罪的那条臂仍算 invalid（这正是「免罪前/后」两个分母的区别）
                "invalid": len(invalid) + len(exonerated),
                "identity": (f"{len(rows)} = {len(citable_pre)} + {len(zero_pre)} + "
                             f"{len(invalid) + len(exonerated)}"),
            },
            "post_probe_exoneration": {
                "citable": len(citable_post), "valid_zero_success": len(zero_post),
                "invalid": len(invalid),
                "identity": f"{len(rows)} = {len(citable_post)} + {len(zero_post)} + {len(invalid)}",
                "exonerated_arms": [{"arm": r["arm"],
                                     "probe_kind": r["probe_kind"],
                                     "C": (r.get("probe_exoneration_citation") or {}).get("C"),
                                     "probe_artifact": (r.get("probe_exoneration_citation") or {})
                                     .get("probe_artifact"),
                                     "cosign_build_matches": (r.get("probe_exoneration_citation") or {})
                                     .get("cosign_build_matches"),
                                     "controlled_success": r["controlled_success"]}
                                    for r in exonerated],
            },
            "archived_only_basis_superseded": {
                "citable": 23, "valid_zero_success": 18, "invalid": 7,
                "status": "superseded",
                "note": ("**主目录留档口径**：5 个盲臂按「留档产物缺字段」记 INVALID。"
                         "已被 blindfix 补测取代（增补三 §9.A②），只用于追溯旧文档里的 41/48、46/48 说法。"),
            },
            "dedup_distinct_experiments_post_exoneration": {
                "citable": len(dedup_citable),
                "valid_zero_success": len(dedup) - len(dedup_citable),
                "invalid": dedup_invalid,
                "identity": (f"{len(dedup) + dedup_invalid} = {len(dedup_citable)} + "
                             f"{len(dedup) - len(dedup_citable)} + {dedup_invalid}"),
                "note": ("互异实验口径（48 产物 - 5 份 blind 重测 = 43 行，其中 1 个 INVALID）。"
                         "与产物级 48/25/22/1 并存，引用时必须写明用哪一个。"),
            },
            "basis_44_arms_superseded": {
                "citable": 23, "valid_zero_success": 19, "invalid": 2,
                "status": "superseded",
                "note": ("A 早前的 23/19/2 是 **44 臂口径**（48 = 44 留档 + 4 个新增 K=1 seed2-5，"
                         "其中 seed3 可引用、seed2/4/5 有效零成功 ⇒ 24/22/2）。不得与 48 臂口径混引。"),
            },
        },
        "validity_class_definitions": {
            "valid": "门禁 measurement_valid=true 且 field_class=strict；数字可直接引用。",
            "VALID_probe_exonerated": ("裁定 10：原判 measurement_invalid（blown 超阈），"
                                       "但同 ckpt 的 clip 探针满足 5 条准入 ⇒ 测量有效。"
                                       "**不得简写成 valid**，引用时必须带 C 与探针路径。"
                                       "裁定 24⑤：本标签**只**对应 `probe_kind=clip_at_train_absmax`；"
                                       "v1.5 起由**门禁**判定（A 不再自算一遍与之竞争，裁定 21）。"),
            "invalid": "测量无效（blown 超阈且无合格探针，或缺逐局门禁字段）；能力未知，不得引用为失败。",
        },
        "label_reporting_rule": ("裁定 8 推广：失效模式标签（insufficient_lift / flick / over_lift）"
                                 "只在 field_class=strict 且 validity_class != invalid 的行输出；"
                                 "其余行本表写 `-` 且不进合计（原始值仍留在 *_raw 字段里备查）。"),
        "counts_withheld_note": (
            "裁定 20②（增补六 §4）：`measurement_valid=false`（或非 strict）的行，行级 "
            "flick / over_lift / insufficient_lift / provisional_pass 写 `null` 并带 `counts_withheld_reason`；"
            "**合计层包含这些被 withheld 的行级计数**（totals.scope_all_48_products_supervisor_reconcile "
            "从 *_raw 求和），所以「行级求和 ≠ 合计」是设计如此、不是缺数。"
            "理由：裁定 12 规定 blown 超阈只作测量有效性门禁，行级给失效模式标签会被读成能力主张。"),
        "blowup_threshold_sources": thr_families,
        "totals": {
            "counting_unit": "产物级（与 48 臂分母同口径）",
            # 与监管增补五 §3 的权威表逐格对账用：全 48 产物、标签不做有效性过滤
            "scope_all_48_products_supervisor_reconcile": scope_totals_all(rows),
            "scope_strict_and_valid_pre_exoneration": scope_totals(valid),
            "scope_strict_and_valid_post_exoneration": scope_totals(valid + exonerated),
            "scope_dedup_post_exoneration": scope_totals(dedup),
            "dedup_note": ("5 个盲臂各有 blind 行与 *_gatefields 行两份产物，指向**同一次训练+同一次评测口径**，"
                           "产物级合计会把它们双计。dedup 口径 = 去掉 5 个 blind 行（其权威数字已由 blindfix 提供，"
                           "且与 _gatefields 行逐位相同），因此 dedup 是**互异实验**口径，"
                           "跨臂比较与合计一律优先引 dedup；三分类分母仍按产物级 48 报，两者都要写明。"),
        },
        "forbidden_headline_numbers": {
            "numbers": ["134", "219", "23"],
            "label": "blindfix 前口径（**已作废**）",
            "reason": ("blindfix 合并前的 48 臂合计：5 个 partial 臂走了门禁的弱证据分支，"
                       "16 局被误判成 flick、1 局 provisional_pass 未升级；把 INVALID 臂也混进了分子。"),
            "authoritative_replacement": "受控 135 / insufficient_lift 235 / flick 7 / over_lift 0 / provisional 0"
                                         "（= meta.totals.scope_all_48_products_supervisor_reconcile）",
            "citable_flick_only": "2 局 / 920（其余 5 局落在 2 个 INVALID 臂上，裁定 12）",
        },
        "build_discipline": {
            "ruling": "裁定 16（增补五 §11）+ 裁定 16.3 改判 7 + 裁定 28（DR-D27）",
            # 从行里**推**出来，不写死：写死的版本号在门禁每升一次后就过期一次（本仓已发生三次）
            "this_table_build": {"gate_version": sorted({str(r.get("gate_version")) for r in rows
                                                         if r.get("gate_version")}),
                                 "gate_build": sorted({str(r.get("gate_build")) for r in rows
                                                       if r.get("gate_build")}),
                                 "gate_spec_sha256": sorted({str(r.get("gate_spec_sha256")) for r in rows
                                                             if r.get("gate_spec_sha256")})},
            "single_build_only": len({str(r.get("gate_build")) for r in rows if r.get("gate_build")}) <= 1,
            "historical_builds_superseded": [
                {"gate_version": "v1.2.1", "gate_build": "e4f5ec887788", "status": "superseded",
                 "note": "免罪前 24/22/2 与 A 自算免罪后 25/22/1 的口径；裁定 28 起降级为历史口径"},
                {"gate_version": "v1.4", "gate_build": "b9379fdb1089", "status": "superseded",
                 "note": "B 侧 24/22/2；裁定 10 通道尚未落地（三处代码级阻塞，裁定 17）"},
            ],
            "rules": [
                "禁跨 build 混引：一张表里只允许一个 gate_build（`single_build_only` 必须为 true）；",
                "GATE_BUILD 是门禁脚本内容哈希 ⇒ 门禁一改，本表**必须重出一次**，旧表降级为历史口径"
                "（不作废、不得当现值引用）—— 裁定 16.3 改判 7，本轮已第三次触发；",
                "重出表只许改**判据构建相关**的键；计数层 / 分母 / 合计一格不许动"
                "（DR-008 验收判据 3，由 --regression-baseline + --allow-build-change 断言）；",
                "本脚本是 arms_summary.json 的**唯一**生产者，不要再写第二个。",
            ],
        },
        # 裁定 27：「会签锚在哪个 build 上是可核事实，必须随数字一起走」
        "cosign_provenance": cosign_provenance,
        # 裁定 24⑤ / DR-D21：A 与 B 的豁免计数**必然差 1**，对账必须按 probe_kind 分组
        "exoneration_reconciliation": exon_recon,
        # 裁定 30 / DR-D29：计数层构建不变、分布层构建相关 ⇒ 分布类陈述一律带构建指纹
        "distribution_layer": dist_layer,
        "invalid_arms": [{"arm": r["arm"], "reason": r["validity_reason"],
                          "ic_mean_blown_frames_frac": r["ic_mean_blown_frames_frac"],
                          "blowup_threshold": (r["blowup_threshold_source"] or {}).get("blowup_threshold"),
                          "probe_exoneration_reason": (r.get("probe_exoneration") or {}).get("reason")}
                         for r in invalid],
    }

    # ---- 打印 ---------------------------------------------------------------
    hdr = (f"{'arm':46}{'data':18}{'steps':>7}{'ts':>3}{'norm':>9}{'R':>3}{'src':>4}"
           f"{'raw':>7}{'gv':>5}{'srise':>6}{'m_rise':>8}{'m_final':>8}{'ctrl':>7}"
           f"{'insuf':>6}{'flick':>6}{'validity':>22}")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        ctrl = ("-" if r["controlled_success"] is None else
                f"{r['controlled_success']}/{r['gate_denominator'] or r['episodes']}")
        raw = f"{r['success_raw']}/{r['episodes']}"
        m_final = "-" if r["mean_final_rise"] is None else f"{r['mean_final_rise']:.4f}"
        # 裁定 8 推广：非 strict / invalid 行的失效模式标签显示 `-`
        insuf = "-" if r.get("insufficient_lift") is None else str(r["insufficient_lift"])
        flick = "-" if r.get("flick") is None else str(r["flick"])
        src = "补测" if r["superseded_by"] else "留档"
        print(f"{r['arm'][:45]:46}{str(r['data'])[:17]:18}{str(r['steps']):>7}"
              f"{str(r['train_seed']):>3}{str(r['action_norm'])[:8]:>9}{str(r['replan_every']):>3}"
              f"{src:>4}{raw:>7}{str(r['grasp_verified']):>5}{str(r['success_rise']):>6}"
              f"{r['mean_max_rise']:>8.4f}{m_final:>8}{ctrl:>7}"
              f"{insuf:>6}{flick:>6}{r['validity_class']:>22}")

    print("\n口径提示：")
    d = meta["denominators"]
    print(f"  - 分母（产物级，{len(rows)} 臂）：可引用 {d['pre_probe_exoneration']['citable']} / "
          f"有效零成功 {d['pre_probe_exoneration']['valid_zero_success']} / "
          f"无效 {d['pre_probe_exoneration']['invalid']}；"
          f"裁定 10 免罪后 {d['post_probe_exoneration']['citable']} / "
          f"{d['post_probe_exoneration']['valid_zero_success']} / "
          f"{d['post_probe_exoneration']['invalid']}。")
    dd = d["dedup_distinct_experiments_post_exoneration"]
    print(f"  - 互异实验口径（去掉 5 份 blind 重测，43 行）：可引用 {dd['citable']} / "
          f"有效零成功 {dd['valid_zero_success']} / 无效 {dd['invalid']}；"
          f"跨臂合计优先引这一口径，产物级口径只用于对齐 48 臂分母。")
    print("  - 旧口径（**禁止再引**）：blindfix 前合计 134/219/23（已作废）、"
          "主目录留档 23/18/7（41/48 有效）、44 臂 23/19/2。")
    print("  - validity：valid=可直接引用；VALID_probe_exonerated=裁定 10 探针免罪（**不得简写 valid**，"
          "引用须带 C 与探针路径）；invalid=测量无效，能力未知（不是「策略失败」）。")
    print("  - src=补测 的 5 行：留档产物缺 10 个逐局门禁字段，权威数字取 blindfix/（superseded_by），"
          "留档原件一字节未改。")
    print("  - R = 闭环 replan 周期（每 R 个 20 Hz tick 重新推理一次）。R 不同的臂不可直接互比。")
    print("  - ctrl = 受控成功/分母，按 scripts/b_gate_controlled_success.py 的严格 C5"
          "（final_rise >= 0.04 m）。")
    print("  - insuf / flick 只对 field_class=strict 且非 invalid 的臂输出（裁定 8 推广）；"
          "非 strict 行显示 `-`，原始值留在 JSON 的 *_raw 字段。")
    print(f"  - 本表裁定构建：gate_version={meta['gate_version']}，gate_build={meta['gate_build']}，"
          f"spec={meta['gate_spec_sha256']}。")
    fam_txt = "、".join(f"{k} 族 {v['blowup_threshold']:.6f}（{v['arms']} 臂）"
                        for k, v in sorted(thr_families.items()) if v["blowup_threshold"] is not None)
    print(f"  - blown 阈值按族分开（裁定 11，跨族不混尺）：{fam_txt}；详见每行 blowup_threshold_source。")
    print("  - raw = robosuite 真值成功局数；srise = max_rise >= 0.04 的局数；"
          "m_rise / m_final = 全 20 局的 max_rise / final_rise 均值（m）。")
    print("  - 参考上界：scripted base-only 同口径 raw 20/20、mean_max_rise 0.0764 m。")
    for scope, t in meta["totals"].items():
        if not isinstance(t, dict):
            continue
        print(f"  - 合计[{scope}]：臂 {t['arms']}、局 {t['episodes']}、raw {t['raw_success']}、"
              f"受控 {t['controlled_success']}、insuff {t['insufficient_lift']}、flick {t['flick']}、"
              f"over_lift {t['over_lift']}、provisional {t['provisional_pass']}。")

    attr = meta["artifact_attribution"]
    n_remeasure = len(attr["remeasure_groups"])
    print(f"  - 产物归属（裁定 18.2）：{len(rows)} 臂全部回显 adjudicated_artifact + sha256；"
          f"其中 {n_remeasure} 臂的权威产物是重测链末端（blindfix / reblown），"
          f"gate 索引 basename 冲突 {len(attr['gate_index_basename_collisions'])} 处（已留痕）。")

    if args.regression_baseline:
        base = Path(args.regression_baseline)
        if not base.is_file():
            print(f"\n回归基线不存在 ⇒ 跳过断言：{base}")
        else:
            ok, rep = regression_check(meta, rows, base, args.allow_build_change)
            tag = "构建迁移" if args.allow_build_change else "归属"
            print(f"\n{tag}回归断言（基线 {base}）：{rep['verdict']}   "
                  f"预期差异 {rep['n_expected_attribution_diffs']} 处 / 非预期 {rep['n_unexpected']} 处")
            print(f"  新增行级键：{rep['new_row_keys']}")
            shown = collections.Counter(i["key"] for i in rep["expected_attribution_diffs"])
            for k, n in sorted(shown.items(), key=lambda kv: -kv[1]):
                print(f"  [{tag}] {k} × {n}")
            for item in rep["unexpected"][:20]:
                print(f"  [非预期] {json.dumps(item, ensure_ascii=False)[:300]}")
            if args.regression_out:
                rout = Path(args.regression_out)
                rout.parent.mkdir(parents=True, exist_ok=True)
                rout.write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n")
                print(f"  写出: {rout}")
            if not ok:
                print("  ⇒ 断言不通过：**不写** --json-out（留档表不被污染），按 ADR-A-006 报回 D")
                sys.exit(2)

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"meta": meta, "arms": rows}, ensure_ascii=False, indent=2) + "\n")
        print(f"\n写出: {out}")


if __name__ == "__main__":
    main()
