#!/usr/bin/env python3
"""裁定 100 / 补单六-②「搬迁一批授权」的**执行件**（一次做完、不分批）。

授权原文要点（`rl_harness_supervision/d_handoff_to_c2_20260930.md` 补单六 §二）：
  · 目标 = `runs/vla/c2_docs_ruling99/`（**D 定死**，不是 C2 提的 `ruling98`）；
  · 范围 = C2 自己枚举的 28 件（22 前像 + 5 探针产物 + 1 标记件），**51 份顶层便利副本不得搬**；
  · 同一批必须包含：① 每一处已发布引用的追平 ② `MOVE_RECORD.json`（逐件 from→to +
    搬前/搬后 `sha256[:12]`，`mv` 不改字节 ⇒ 两个 sha 必须相同，这一列就是自证）
    ③ 搬完后的 `G20` 重计数（**枚举命令逐字记进产物**）。

本件只做「搬 + 记账 + 重计数」，**不改判据、不重跑闸、不上卡、不重生成 stats**（补单六 §七）。
纪律：**全程不用 `rm`**（`files_deleted = 0`）；搬运用 `os.replace`（同设备原子改名，保留 mtime）；
每一件搬前先断言目标不存在（**不覆盖**）；搬后断言 sha/bytes/mtime 三值相同。
三值纪律：没测到的一律 `not_measured`。裁定 46：本件不含任何 policy 指标。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
NORM_DIR = ROOT / "runs/vla/c2_norm_contract_20260929"
NORM_REL = "runs/vla/c2_norm_contract_20260929/"
TARGET_DIR = ROOT / "runs/vla/c2_docs_ruling99"
TARGET_REL = "runs/vla/c2_docs_ruling99/"
AUDIT_DIR = ROOT / "runs/vla/c2_move_dependency_audit_ruling99"
PLAN_ARTIFACT = AUDIT_DIR / "MOVE_DEPENDENCY_AUDIT.json"
MOVE_RECORD = TARGET_DIR / "MOVE_RECORD.json"
REPOINT_RECORD = TARGET_DIR / "REPOINT_RECORD.json"
BEFORE_IMAGE_DIR = TARGET_DIR / "before_images"
GATE_SRC = ROOT / "scripts/c2_gate_norm_contract.py"
# 闸的 G20 排除面：本轮权威跑（裁定 97.2 红二那一轮）的 run 目录。
EXCLUDED_RUN_REL = "runs/vla/c2_norm_contract_20260929/gate/run_20260930_133156"
D_PROXY_CUTOFF = "2026-09-30 13:33:51"          # D 数出 28 件的那个截止时刻（补单六-③）
MAX_TEXT_BYTES_FOR_LINES = 8 << 20


def _now() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def sha12(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()[:12]


def identity(p: pathlib.Path) -> dict:
    """一件文件的身份读数。**行数字段一律点名口径**（裁定 98.3-②③），不用裸 `n_lines`。"""
    rel = str(p.relative_to(ROOT)) if p.is_absolute() and ROOT in p.parents else str(p)
    if not p.exists():
        return {"path": rel, "measurement_status": "not_measured", "why": "path_absent"}
    st = p.stat()
    out = {"path": rel, "measurement_status": "measured", "bytes": st.st_size,
           "sha256_12": sha12(p),
           "mtime": _dt.datetime.fromtimestamp(st.st_mtime).astimezone().isoformat(timespec="seconds"),
           "ctime": _dt.datetime.fromtimestamp(st.st_ctime).astimezone().isoformat(timespec="seconds"),
           "mtime_epoch": st.st_mtime, "ctime_epoch": st.st_ctime, "inode": st.st_ino,
           "device": st.st_dev}
    if st.st_size <= MAX_TEXT_BYTES_FOR_LINES:
        try:
            txt = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            out["n_lines_wc"] = None
            out["n_lines_splitlines"] = None
            out["line_count_caliber_note"] = "not_measured（非 UTF-8 文本或读失败）"
        else:
            out["n_lines_wc"] = len(txt.split("\n")) - 1
            out["n_lines_splitlines"] = len(txt.splitlines())
    return out


def gate_exceptions() -> dict:
    """从**闸源码本身**读例外清单（只读加载，不执行闸）⇒ 判据不靠散文转述。"""
    spec = importlib.util.spec_from_file_location("gate_ro_mover", GATE_SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return {"source": {"path": str(GATE_SRC.relative_to(ROOT)), "sha256_12": sha12(GATE_SRC)},
            "G20_DECLARED_WRITE_EXCEPTIONS": dict(mod.G20_DECLARED_WRITE_EXCEPTIONS),
            "criterion_anchors_verbatim": {
                "cutoff": "cutoff = t_start（`t_start = time.time()` 在 run 目录 mkdir 之后）",
                "test": "if p.stat().st_mtime >= cutoff:  ⇒ **只看 mtime**",
                "exclusion": "not str(p).startswith(str(run_dir))",
                "exception_membership": "t not in G20_DECLARED_WRITE_EXCEPTIONS（**精确路径**成员判定）",
                "sentinel": "enumerator_sees_known = (NORM_DIR / \"matrix.json\") in enumerated",
                "ok_expression": "(not touched_undeclared) and enumerator_sees_known and len(enumerated) > 0"}}


def recount(cutoff_label: str, cutoff_str: str, cutoff_epoch: float, exc: dict) -> dict:
    """**搬后 G20 重计数**：两条独立实现互为对照（`find` 逐字命令 vs 纯 Python 复刻闸的循环）。

    报四个数，缺一不可（否则就是把口径混着用）：
      · `mtime`（= 闸当前判据）在 D 的代理截止时刻 / 在「下一轮开闸时刻」两种 cutoff 下的计数；
      · `mtime ∨ ctime`（= 99.4-② 待授权的 P2 形态）同样两种 cutoff 下的计数。
    """
    exceptions = set(exc["G20_DECLARED_WRITE_EXCEPTIONS"])
    find_argv_mtime = ["find", NORM_REL.rstrip("/"), "-type", "f", "-newermt", cutoff_str, "-print"]
    find_argv_ctime = ["find", NORM_REL.rstrip("/"), "-type", "f", "-newerct", cutoff_str, "-print"]
    procs = {}
    for name, argv in (("mtime", find_argv_mtime), ("ctime", find_argv_ctime)):
        t0 = time.time()
        pr = subprocess.run(argv, cwd=str(ROOT), capture_output=True, text=True, timeout=900)
        raw = [ln for ln in pr.stdout.splitlines() if ln.strip()]
        keep = [ln for ln in raw if not ln.startswith(EXCLUDED_RUN_REL + "/")
                and ln not in exceptions]
        _FIND_CACHE[" ".join(argv)] = set(keep)          # 与 Python 复刻用**同一把排除尺**，才对得上账
        procs[name] = {"argv_verbatim": " ".join(argv), "cwd": str(ROOT),
                       "returncode": pr.returncode, "elapsed_s": round(time.time() - t0, 2),
                       "stderr_head": pr.stderr.strip()[:300] or None,
                       "n_raw_hits": len(raw),
                       "n_after_gate_exclusions": len(keep),
                       "paths_head": sorted(keep)[:12]}
    py = {"mtime": [], "ctime": [], "mtime_or_ctime": []}
    enumerated = 0
    sentinel_seen = False
    t0 = time.time()
    for p in NORM_DIR.rglob("*"):
        if not p.is_file() or str(p).startswith(str(ROOT / EXCLUDED_RUN_REL)):
            continue
        enumerated += 1
        if p.name == "matrix.json" and p.parent == NORM_DIR:
            sentinel_seen = True
        try:
            st = p.stat()
        except OSError:
            continue
        rel = str(p.relative_to(ROOT))
        if rel in exceptions:
            continue
        m = st.st_mtime >= cutoff_epoch
        c = st.st_ctime >= cutoff_epoch
        if m:
            py["mtime"].append(rel)
        if c:
            py["ctime"].append(rel)
        if m or c:
            py["mtime_or_ctime"].append(rel)
    py_elapsed = round(time.time() - t0, 2)
    find_mtime_set = sorted(_find_set(find_argv_mtime))
    find_ctime_set = sorted(_find_set(find_argv_ctime))
    recon = {
        "mtime_find_vs_python": {"find_n": len(find_mtime_set), "python_n": len(py["mtime"]),
                                 "symmetric_difference": sorted(
                                     set(find_mtime_set) ^ set(py["mtime"]))[:20],
                                 "agree": len(find_mtime_set) == len(py["mtime"])
                                 and not (set(find_mtime_set) ^ set(py["mtime"]))},
        "ctime_find_vs_python": {"find_n": len(find_ctime_set), "python_n": len(py["ctime"]),
                                 "symmetric_difference": sorted(
                                     set(find_ctime_set) ^ set(py["ctime"]))[:20],
                                 "agree": len(find_ctime_set) == len(py["ctime"])
                                 and not (set(find_ctime_set) ^ set(py["ctime"]))}}
    return {"as_of": _now(), "cutoff_label": cutoff_label,
            "cutoff_verbatim": cutoff_str, "cutoff_epoch": cutoff_epoch,
            "criterion_source": "闸源码 `scripts/c2_gate_norm_contract.py`（只读加载；见 `gate_criterion`）",
            "exclusions": {"run_dir": EXCLUDED_RUN_REL,
                           "declared_write_exceptions": sorted(exceptions)},
            "find_commands_verbatim": {k: v["argv_verbatim"] for k, v in procs.items()},
            "find_runs": procs,
            "python_replication": {"elapsed_s": py_elapsed,
                                   "n_touched_by_mtime": len(py["mtime"]),
                                   "n_touched_by_ctime": len(py["ctime"]),
                                   "n_touched_by_mtime_or_ctime": len(py["mtime_or_ctime"]),
                                   "touched_by_mtime": sorted(py["mtime"]),
                                   "touched_by_ctime_head": sorted(py["ctime"])[:20],
                                   "touched_by_mtime_or_ctime_head": sorted(py["mtime_or_ctime"])[:20],
                                   "n_enumerated_outside_run_dir": enumerated,
                                   "enumerator_sees_matrix_json": sentinel_seen},
            "reconciliation": recon,
            "g20_would_be": {
                "verdict_by_current_criterion_mtime": (
                    "GREEN-able（未声明写入 = 0）" if not py["mtime"] else
                    f"RED（未声明写入 {len(py['mtime'])} 件）"),
                "verdict_if_p2_mtime_or_ctime_adopted": (
                    "GREEN-able（未声明写入 = 0）" if not py["mtime_or_ctime"] else
                    f"RED（未声明写入 {len(py['mtime_or_ctime'])} 件）"),
                "non_vacuity_sentinel": ("成立（`matrix.json` 在枚举集内、枚举集非空 "
                                         f"= {enumerated} 件）" if (sentinel_seen and enumerated > 0)
                                         else "**不成立** ⇒ 枚举为空 = 恒真"),
                "note": ("**本件不重跑闸**（补单六 §七）；这一段只是把闸的判据在**搬后**的目录状态上"
                         "只读复算一遍，报「若此刻开闸会数到几件」。裁定 46：不含 policy 指标。")}}


_FIND_CACHE: dict = {}


def _find_set(argv: list) -> set:
    """取上面 `find` 那一路的结果（同一条命令、同一把排除尺）⇒ 不重复跑 `find`、也不换口径。"""
    key = " ".join(argv)
    if key not in _FIND_CACHE:                            # 防御：不该发生（上面已填缓存）
        pr = subprocess.run(argv, cwd=str(ROOT), capture_output=True, text=True, timeout=900)
        _FIND_CACHE[key] = {ln for ln in pr.stdout.splitlines()
                            if ln.strip() and not ln.startswith(EXCLUDED_RUN_REL + "/")}
    return _FIND_CACHE[key]


def load_plan(expect_sha12: str | None) -> dict:
    idn = identity(PLAN_ARTIFACT)
    if expect_sha12 and idn.get("sha256_12") != expect_sha12:
        raise SystemExit(f"计划件身份不符：期望 {expect_sha12}，实测 {idn.get('sha256_12')} ⇒ 拒绝执行"
                         "（不按计划散文搬，按**指名身份**的那一份搬）")
    doc = json.loads(PLAN_ARTIFACT.read_text(encoding="utf-8"))
    seg = doc["E_move_execution_plan"]
    if seg.get("target_dir") != TARGET_REL:
        raise SystemExit(f"计划件的目标目录 = {seg.get('target_dir')} ≠ 授权的 {TARGET_REL} ⇒ 拒绝执行")
    return {"plan_identity": idn, "segment": seg, "plan_rows": seg["plan"],
            "blocking_rule_verbatim": seg.get("blocking_rule_verbatim"),
            "audit_artifact_as_of": doc.get("as_of")}


def do_move(plan: dict, dry_run: bool) -> dict:
    rows = plan["plan_rows"]
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    n_moved = n_failed = 0
    for r in rows:
        src = ROOT / r["path"]
        rec = {"decision": r["decision"], "reason": r["reason"],
               "in_authorized_scope": r["in_authorized_scope"],
               "blocking_owners": r.get("blocking_owners") or [],
               "blocking_references": r.get("blocking_references") or [],
               "n_blocking_references": r.get("n_blocking_references", 0),
               "consumer_record_hits_input_keyish": r.get("consumer_record_hits_input_keyish", 0),
               "published_doc_citations_to_repoint": r.get("published_doc_citations_to_repoint") or [],
               "repoint_owner_split": r.get("repoint_owner_split") or {}}
        if r["decision"] != "move":
            rec.update({"from": r["path"], "to": None, "action": "hold_back（原地不动）",
                        "hold_back_evidence": ("他线活代码按路径/通配引用它（见 `blocking_references`）；"
                                               "补单六-②-1 要求同批追平，而追平不在 C2 的写入面内")})
            items.append(rec)
            continue
        tail = r["path"][len(NORM_REL):]
        dst = TARGET_DIR / tail
        before = identity(src)
        rec["from"] = r["path"]
        rec["to"] = str(dst.relative_to(ROOT))
        rec["before"] = before
        if before["measurement_status"] != "measured":
            rec.update({"action": "failed", "why": "source_absent"})
            n_failed += 1
            items.append(rec)
            continue
        if dst.exists():
            rec.update({"action": "refused_dest_exists（不覆盖）",
                        "dest_identity": identity(dst)})
            n_failed += 1
            items.append(rec)
            continue
        if dry_run:
            rec.update({"action": "dry_run（未搬）"})
            items.append(rec)
            continue
        if before["device"] != TARGET_DIR.stat().st_dev:
            rec.update({"action": "failed", "why": "cross_device（`os.replace` 不适用；"
                                                    "本件不做 copy+delete，因为纪律是不用 `rm`）"})
            n_failed += 1
            items.append(rec)
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.replace(src, dst)
        after = identity(dst)
        src_after = identity(src)
        same = (before["sha256_12"] == after["sha256_12"]
                and before["bytes"] == after["bytes"]
                and before["mtime"] == after["mtime"])
        rec.update({"action": "moved（`os.replace`，同设备原子改名）", "after": after,
                    "source_still_exists": src_after["measurement_status"] == "measured",
                    "byte_identity_proof": {
                        "sha256_12_before": before["sha256_12"],
                        "sha256_12_after": after["sha256_12"],
                        "sha_equal": before["sha256_12"] == after["sha256_12"],
                        "bytes_equal": before["bytes"] == after["bytes"],
                        "mtime_equal": before["mtime"] == after["mtime"],
                        "ctime_changed": before["ctime"] != after["ctime"],
                        "ctime_change_is_inherent": ("`os.replace` 改的是目录项（inode 元数据）⇒ ctime 必变；"
                                                     "字节与 mtime 不变 ⇒ 补单六-②-2 要的自证列是 sha 相等"),
                        "inode_unchanged": before["inode"] == after["inode"],
                        "all_three_equal": same},
                    "verified": same})
        if same:
            n_moved += 1
        else:
            n_failed += 1
        items.append(rec)
    return {"items": items, "n_moved": n_moved, "n_failed": n_failed, "dry_run": dry_run}


def scan_repoints() -> dict:
    """**追平台账（机器导出，不手打）**：本轮所有前像都落在 `runs/vla/c2_docs_ruling99/before_images/`，
    前像文件名按纪律内嵌**改前** sha12（`<name>.before_<sha12>` / `<name>.pre_<tag>_<sha12>`）⇒
    扫这个目录就能导出「谁被改了 + 改前身份」，再实测改后身份，两两配对。
    """
    if not BEFORE_IMAGE_DIR.exists():
        return {"as_of": _now(), "n_before_images": 0, "rows": [],
                "note": "本轮尚无追平动作（`before_images/` 不存在）"}
    rows = []
    for q in sorted(BEFORE_IMAGE_DIR.iterdir()):
        if not q.is_file():
            continue
        name = q.name
        stem, _, tag = name.rpartition(".before_")
        if not stem:
            stem, _, tag = name.rpartition(".pre_")
            kind = "pre_tag"
        else:
            kind = "before_sha"
        rows.append({"before_image": str(q.relative_to(ROOT)),
                     "before_image_identity": identity(q),
                     "target_name": stem or None, "suffix_tag": tag or None,
                     "naming_kind": kind,
                     "note": ("前像文件名内嵌的是**改前** sha12（`before_sha` 那类）；"
                              "`pre_tag` 那类内嵌的是标签 + sha12，同样指改前身份")})
    return {"as_of": _now(), "n_before_images": len(rows), "rows": rows,
            "derivation": "**由目录扫描导出**，不手打清单（裁定 100.4-(d) 的同族纪律：断言要有承载件）"}


def _obligations(rows: list) -> dict:
    """**只从「真搬走的行」导出追平义务**。
    第一版把 `hold_back` 的行也算进并集 ⇒ 光标记件一件就带进 164 处文书引用、13 份他线文书，
    而它**根本没搬**（引用一处都没悬空）⇒ 会把 D 支去追一批不存在的账。这是本执行件自己的一个缺陷，
    在 finalize 第一跑的产物里可见（保留为 `REPOINT_RECORD.v_*.json` / `MOVE_RECORD.v_*.json`）。
    被排除的量**照旧报出、不吞掉**（裁定 93.8）。"""
    moved = [r_ for r_ in rows if r_["decision"] == "move"]
    held = [r_ for r_ in rows if r_["decision"] != "move"]

    def _union(rs, key):
        return sorted({f for r_ in rs for f in (r_.get("repoint_owner_split") or {}).get(key, [])})

    return {
        "scope_rule": "**只取 `decision = move` 的行**；`hold_back` 的行没搬 ⇒ 引用没悬空 ⇒ 不产义务",
        "n_rows_moved": len(moved), "n_rows_held_back": len(held),
        "c2_owned_and_repointed_by_c2": _union(moved, "c2_owned_docs_i_will_repoint"),
        "other_line_docs_handed_to_D": _union(moved, "other_line_docs_handed_to_D"),
        "consumer_records_handed_to_D": _union(moved, "consumer_records_handed_to_D"),
        "excluded_because_row_not_moved": {
            "c2_owned_docs": _union(held, "c2_owned_docs_i_will_repoint"),
            "other_line_docs": _union(held, "other_line_docs_handed_to_D"),
            "consumer_records": _union(held, "consumer_records_handed_to_D"),
            "held_rows": [r_["path"] for r_ in held],
            "why_excluded": ("这些行**原地未动**（他线活代码引用 ⇒ `hold_back`），"
                             "对它们的引用**没有失效** ⇒ 不构成追平义务。")},
        "note": ("他线文书/他线产物里的引用**不由 C2 改**（写入面纪律）⇒ 逐条交 D，"
                 "由 D 在下一轮裁定里追平或令该线自追。"),
    }


def write_record(doc: dict, path: pathlib.Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():                                   # 不覆盖：旧字节留成版本件
        old = identity(path)
        keep = path.with_name(f"{path.stem}.v_{old['sha256_12']}{path.suffix}")
        if not keep.exists():
            os.replace(path, keep)
        doc["prior_version_preserved"] = str(keep.relative_to(ROOT))
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return identity(path)


def main() -> int:
    ap = argparse.ArgumentParser(description="裁定 100 / 补单六-② 的搬迁执行件")
    ap.add_argument("--plan-sha12", default=None, help="计划件的 sha256[:12]（指名身份才执行）")
    ap.add_argument("--dry-run", action="store_true", help="只记账不搬")
    ap.add_argument("--phase", choices=("move", "finalize"), default="move")
    args = ap.parse_args()

    exc = gate_exceptions()
    plan = load_plan(args.plan_sha12)
    started = _now()
    now_epoch = time.time()
    now_str = _dt.datetime.fromtimestamp(now_epoch).astimezone().strftime("%Y-%m-%d %H:%M:%S")

    if args.phase == "move":
        res = do_move(plan, args.dry_run)
        pre = recount("D 的代理截止时刻（补单六-③ 数出 28 件的那把尺）",
                      D_PROXY_CUTOFF,
                      _dt.datetime.fromisoformat("2026-09-30T13:33:51+08:00").timestamp(), exc)
        nxt = recount("下一轮开闸时刻（`cutoff = t_start` 的语义，即 P2 会不会恒红）",
                      now_str, now_epoch, exc)
        doc = {
            "artifact": "MOVE_RECORD（裁定 100 / 补单六-②-2）",
            "generated_at": started, "as_of": _now(),
            "phase": "move", "dry_run": args.dry_run,
            "authority": {"ruling": "裁定 100 §100.5 / 补单六-②（`rl_harness_supervision/d_handoff_to_c2_20260930.md`）",
                          "target_dir": TARGET_REL,
                          "target_dir_is_d_fixed": True,
                          "scope_rule": "计划件 `E_move_execution_plan`（26 搬 / 3 留），51 份顶层便利副本不在范围内",
                          "plan_artifact": plan["plan_identity"],
                          "blocking_rule_verbatim": plan["blocking_rule_verbatim"],
                          "generator": identity(pathlib.Path(__file__).resolve())},
            "gate_criterion": exc,
            "summary": {"n_rows_in_plan": len(plan["plan_rows"]),
                        "n_moved": res["n_moved"], "n_failed": res["n_failed"],
                        "n_hold_back": sum(1 for i in res["items"] if i["decision"] == "hold_back"),
                        "all_moved_byte_identical": (
                            res["n_failed"] == 0 and res["n_moved"] > 0
                            and all(i.get("verified") for i in res["items"]
                                    if i["decision"] == "move" and not args.dry_run)),
                        "files_deleted": 0, "rm_used": False,
                        "gate_source_modified": False, "gate_products_modified": False,
                        "stats_modified": False, "gpu_used": False,
                        "policy_executed": False, "capability_claim": None,
                        "toplevel_convenience_copies_moved": 0},
            "post_move_g20_recount": {
                "at_d_proxy_cutoff": pre, "at_next_run_cutoff": nxt,
                "how_to_read": ("**两个 cutoff 都要看**：D 数的 28/29 是 `13:33:51` 那把尺（历史截止）；"
                                "而闸真正用的是 `cutoff = t_start`（下一轮开闸时刻）。"
                                "`mtime` 那两列对应当前判据，`mtime ∨ ctime` 那两列对应 99.4-② 待授权的 P2。"),
                "expected_by_d": "补单六-②-3 的预期是「未申报写入 → 0」",
                "residual_and_why": ("**残值 = 3 件（全部 hold_back）**：标记件被 B2 的 "
                                     "`P_C2_TOPLEVEL_MARKER` 常量与 A2 的 `--c2-broadcast-json` 入参消费；"
                                     "两份 `c2_to_a2_bc_stats_handoff_20260930.md.before_*` 被 B2 的 "
                                     "`bi_dir.glob(...)` 当归因证据（空 glob 会把 B2 的 `verdict` 翻成 "
                                     "`unattributed_defect`、`ok` 翻回 `false`）。"
                                     "追平这三处不在 C2 的写入面内 ⇒ 请 D 裁：令 B2/A2 同批改常量，"
                                     "C2 一分钟内补搬；或接受这个非零残值。")},
            "repoint_status": "pending（同批的 ①「引用追平」由 `--phase finalize` 落 `REPOINT_RECORD.json` 后回填）",
            "items": res["items"],
            "line_count_caliber_declaration": ("行数字段一律点名口径（`n_lines_wc` / `n_lines_splitlines`）；"
                                               "代码行号只作 `line_no_as_of` 时点读数；约束性对账只用 `sha256[:12]`"),
            "no_policy_metrics": True,
        }
        idn = write_record(doc, MOVE_RECORD)
        print(json.dumps({"phase": "move", "move_record": idn,
                          "summary": doc["summary"],
                          "recount_at_d_proxy_cutoff": {
                              "mtime": pre["python_replication"]["n_touched_by_mtime"],
                              "mtime_or_ctime": pre["python_replication"]["n_touched_by_mtime_or_ctime"],
                              "find_agrees_mtime": pre["reconciliation"]["mtime_find_vs_python"]["agree"],
                              "find_agrees_ctime": pre["reconciliation"]["ctime_find_vs_python"]["agree"],
                              "enumerated": pre["python_replication"]["n_enumerated_outside_run_dir"],
                              "sentinel": pre["python_replication"]["enumerator_sees_matrix_json"]},
                          "recount_at_next_run_cutoff": {
                              "mtime": nxt["python_replication"]["n_touched_by_mtime"],
                              "mtime_or_ctime": nxt["python_replication"]["n_touched_by_mtime_or_ctime"],
                              "find_agrees_mtime": nxt["reconciliation"]["mtime_find_vs_python"]["agree"],
                              "find_agrees_ctime": nxt["reconciliation"]["ctime_find_vs_python"]["agree"]},
                          "moved_head": [i["to"] for i in res["items"]
                                         if i["decision"] == "move"][:5]},
                         ensure_ascii=False, indent=2))
        return 0 if res["n_failed"] == 0 else 1

    # ---- finalize：把「引用追平」落成机器导出的台账，并回填 MOVE_RECORD ----
    rp = scan_repoints()
    docs = {
        "artifact": "REPOINT_RECORD（裁定 100 / 补单六-②-1）",
        "as_of": _now(),
        "authority": "补单六-②-1「每一处已发布引用的追平」必须与搬迁同批",
        "method": rp["derivation"],
        "before_images": rp,
        "obligation_split_from_plan": _obligations(plan["plan_rows"]),
        "path_mapping_rule": {
            "old_prefix": NORM_REL, "new_prefix": TARGET_REL,
            "form": "`runs/vla/c2_norm_contract_20260929/<tail>` → `runs/vla/c2_docs_ruling99/<tail>`",
            "byte_identity": "逐件 sha256[:12] 搬前 = 搬后（见 `MOVE_RECORD.json` 的 `byte_identity_proof`）",
            "not_moved": ["51 份顶层便利副本（D 明令不搬）", "3 件 hold_back（他线活代码引用）"]},
        "no_policy_metrics": True,
    }
    rp_idn = write_record(docs, REPOINT_RECORD)
    prior = json.loads(MOVE_RECORD.read_text(encoding="utf-8")) if MOVE_RECORD.exists() else {}
    prior_idn = identity(MOVE_RECORD)
    if prior:
        prior_gen = (prior.get("authority") or {}).get("generator") or {}
        cur_gen = identity(pathlib.Path(__file__).resolve())
        chain = prior.get("generator_version_chain") or []
        if prior_gen.get("sha256_12") and prior_gen.get("sha256_12") != cur_gen.get("sha256_12"):
            chain.append({"sha256_12": prior_gen.get("sha256_12"), "bytes": prior_gen.get("bytes"),
                          "n_lines_wc": prior_gen.get("n_lines_wc"),
                          "what_it_did": ("**真正执行了那 26 件搬迁**（`--phase move`）并写了 "
                                          "`MOVE_RECORD` 的第一版；它的 `finalize` 第一跑把 `hold_back` 行"
                                          "也算进了追平义务并集（缺陷，已在下一版修）"),
                          "superseded_by": cur_gen.get("sha256_12")})
        prior["authority"]["generator"] = cur_gen
        prior["authority"]["generator_version_chain"] = chain
        prior["authority"]["generator_change_note"] = (
            "**执行件改版不等于重搬**：本版只重跑 `--phase finalize`（改的是追平义务的取值范围），"
            "**没有再移动任何文件**（`summary.n_moved` 仍是第一版那次实测值，`files_deleted = 0`）。")
        versions = []
        for v in sorted(TARGET_DIR.glob("MOVE_RECORD*.json")):
            if v.name == "MOVE_RECORD.json":
                continue
            versions.append(identity(v))
        prior["version_chain"] = {
            "prior_versions_preserved": versions,
            "why": ("`write_record` 不覆盖：每次 finalize 都把上一版留成 `MOVE_RECORD.v_<sha12>.json`"
                    "（dry-run 那一份留成 `MOVE_RECORD.dryrun_<sha12>.json`）⇒ **已发布散文里引用的"
                    "那一版永远可按 sha 取回**。"),
            "published_citations_superseded_note": (
                "C2 的 `docs/c2_handoff_to_d_20260930.md` §10.10/§10.11 与 `daily_report.md` §C2-4 "
                "引的是**第一版**（`MOVE_RECORD.v_ce7945fab219.json`，即搬迁刚落盘那一版）的身份；"
                "此后两次 finalize 只改**记账**（追平义务的取值范围、生成器版本链），"
                "**没有再移动任何文件**。活件现值一律以盘上实测为准（裁定 96.1-①／98.10-三 的分层口径）。")}
        prior["phase"] = "move+finalize"
        prior["as_of"] = _now()
        prior["repoint_status"] = "done（台账 = `REPOINT_RECORD.json`，身份见下）"
        prior["repoint_record"] = rp_idn
        prior["move_record_prior_version_identity"] = prior_idn
        now_epoch2 = time.time()
        now_str2 = _dt.datetime.fromtimestamp(now_epoch2).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        prior["post_move_g20_recount"]["at_d_proxy_cutoff"] = recount(
            "D 的代理截止时刻（追平动作之后再复算一次）", D_PROXY_CUTOFF,
            _dt.datetime.fromisoformat("2026-09-30T13:33:51+08:00").timestamp(), exc)
        prior["post_move_g20_recount"]["at_next_run_cutoff"] = recount(
            "下一轮开闸时刻（追平动作之后再复算一次）", now_str2, now_epoch2, exc)
        final_idn = write_record(prior, MOVE_RECORD)
    else:
        final_idn = {"measurement_status": "not_measured", "why": "MOVE_RECORD 不存在（未先跑 --phase move）"}
    print(json.dumps({"phase": "finalize", "repoint_record": rp_idn,
                      "move_record_final": final_idn,
                      "n_before_images_in_batch": rp["n_before_images"],
                      "c2_owned_repointed": docs["obligation_split_from_plan"]["c2_owned_and_repointed_by_c2"],
                      "n_other_line_docs_handed_to_D": len(
                          docs["obligation_split_from_plan"]["other_line_docs_handed_to_D"]),
                      "n_consumer_records_handed_to_D": len(
                          docs["obligation_split_from_plan"]["consumer_records_handed_to_D"])},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
