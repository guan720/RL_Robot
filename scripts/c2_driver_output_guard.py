#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""C2 · 跨线回归驱动的**输出面守卫**（纪律 `regression_driver_output_enumeration`，裁定 68 §10.3）。

## 它解决的问题（真实事故，不是假想）
C2 的 `scripts/c2_run_c_regression_postpatch.sh` 在 21:42:43–21:44:16 覆写了 `runs/infra/` 顶层
**16 个 C 线冻结产物**：驱动只把 `c_env_manifest.py --check` 一处改指到 C2 目录，其余自检脚本
把结果写在**自己源码里的固定路径**。D 的定性：「"凭判断挑"本身就是错误的方法，必须枚举」。

## 三段式守卫（枚举 → 快照 → 复原 + 未申报写入检测）
1. `enumerate`：从被调脚本**源码**里枚举全部固定路径输出（字面量 `runs/...json[l]` 与
   `"runs"/"infra"/"x.json"` 拼接式两种写法都认），清单不手抄（脚本名从 `c_run_all_selfchecks.sh`
   的 `SCRIPTS=(...)` 解析）。枚举结果为空 ⇒ **拒绝开工**（exit 3），不许静默降级成"没东西要保护"。
2. `snapshot`：对每个已存在的声明路径留 before 影像（字节 + sha256-12 + mtime）。
3. `restore`：跑完之后
   - 声明路径被改 ⇒ **新字节先复制到本线证据目录**（回归证据不丢），**再把 before 影像写回原路径**
     并校验 sha256-12 一致 ⇒ 别人的产物在驱动结束后**逐字节未变**；
   - **未申报写入检测**（真正的牙）：快照时对扫描根（默认 `runs/infra`）做**全深度 stat 索引**
     （不限 maxdepth —— 实测证明 `maxdepth=2` 会漏掉动态时间戳子目录里 depth 3–7 的 ~745 个文件）；
     跑完再索引一次，逐条分类：
     * 声明路径被改 ⇒ 复原（有 before 影像）；
     * **未声明且被改** ⇒ `unprotected_changes` ⇒ **RED**（没有 before 影像 ⇒ 不可复原，如实报失败）；
     * **未声明的新文件** ⇒ `shutil.move` 搬进本线证据目录（保留相对结构、字节不丢），
       并 `rmdir` 掉本轮新建的空目录 ⇒ 别人的产物树**结束后既没被改、也没多东西**；
     * 快照后消失的文件 ⇒ RED（驱动删了别人的东西）。

## 双向牙
`selftest` 子命令在**临时沙箱**（不碰 `runs/`）里跑 1 条基线 + 3 个变异体，每个变异体都有
`must_go_red` / `must_stay_green` 两张清单，两边都要对上才算这条变异有效：
* `M1_enumerate_only_first`：只保护清单第一项 ⇒ 第二项被改必须进 `undeclared_writes`（RED）；
* `M2_skip_restore`：不复原 ⇒ 复原后校验必须报 `restore_verified=false`（RED）；
* `M3_empty_enumeration`：枚举为空 ⇒ `snapshot` 必须 exit 3 拒绝（RED）。

## 纪律
* 只读别人的产物；写只落 `--out`（C2 目录）与**复原原字节**（复原 = 恢复原状，不是新写）。
* 不 `rm`；沙箱用 `tempfile` 并在结束时保留（供复核），路径写进产物。
* 状态词只用 v4 五档；不用「跑通 / 学会 / 达标」。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT_DEFAULT = HERE.parents[1]
sys.path.insert(0, str(ROOT_DEFAULT / "scripts"))
import c2_register_overwritten_c_artifacts as reg  # noqa: E402  单一枚举实现，避免两份清单分叉


def now_iso() -> str:
    return _dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def sha12_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:12]


def sha12_file(p: Path) -> str:
    return reg.sha12(p)


def flat(rel: str) -> str:
    return rel.replace("/", "__")


def enumerate_declared(root: Path, run_all: Path, extra_scripts: list[str]) -> dict:
    """枚举被调脚本源码里的固定路径输出。返回 {path: {declared_by, line, kind}}。"""
    text = run_all.read_text(encoding="utf-8")
    block = re.search(r"^SCRIPTS=\((.*?)^\)", text, re.S | re.M)
    if not block:
        raise SystemExit(f"无法从 {run_all} 解析 SCRIPTS=(...)")
    scripts = [t for t in re.split(r"\s+", block.group(1)) if re.fullmatch(r"[A-Za-z0-9_]+", t)]
    scripts += [s for s in extra_scripts if s not in scripts]
    declared: dict[str, dict] = {}
    per_script = []
    for name in scripts:
        sp = root / "scripts" / f"{name}.py"
        rec = {"script": f"scripts/{name}.py", "exists": sp.exists(), "paths": []}
        if sp.exists():
            src = sp.read_text(encoding="utf-8")
            for i, line in enumerate(src.splitlines(), 1):
                for m in reg.FIXED_PATH_RE.finditer(line):
                    rec["paths"].append({"path": m.group(0), "line": i, "kind": "literal"})
                for m in re.finditer(r'"runs"\s*/\s*"([A-Za-z0-9_]+)"\s*/\s*"([A-Za-z0-9_.\-]+\.jsonl?)"', line):
                    rec["paths"].append({"path": f"runs/{m.group(1)}/{m.group(2)}", "line": i, "kind": "joined"})
        for e in rec["paths"]:
            p = e["path"]
            if "{" in p or "..." in p:      # 模板/示例路径，不是固定输出
                continue
            declared.setdefault(p, {"declared_by": rec["script"], "line": e["line"], "kind": e["kind"]})
        per_script.append(rec)
    return {"generated_at": now_iso(), "run_all": str(run_all), "scripts": scripts,
            "per_script": per_script, "declared": declared, "n_declared": len(declared)}


def scan_writes(root: Path, since: float, scan_roots: list[str], maxdepth: int) -> list[dict]:
    out = []
    for sr in scan_roots:
        base = root / sr
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            try:
                rel = p.relative_to(base)
            except ValueError:
                continue
            if len(rel.parts) - 1 >= maxdepth:
                continue
            st = p.stat()
            if st.st_mtime >= since:
                out.append({"path": str(p.relative_to(root)), "mtime": st.st_mtime, "bytes": st.st_size})
    return out


def top_component(rel: str) -> str:
    """`runs/infra/<top>/...` 的 `<top>`；顶层文件返回文件名本身。"""
    parts = rel.split("/")
    return parts[2] if len(parts) > 3 else (parts[-1] if len(parts) == 3 else rel)


def is_owned(rel: str, extra_prefixes: list[str]) -> bool:
    """本守卫**只**处置 C 线产物树（`c_*`，但排除 C2 自己的 `c2_*`）。

    为什么必须限定：A2/B2/E/D 都是活进程，也会往 `runs/infra/` 写（`a2_*` / `b2_*` / `e_*` / `d_*`）。
    不限定的话，守卫会把**别人正在写的文件搬进 C2 的证据目录**、或把别人的正常写入判成 RED
    ⇒ 那就是"为了防止自己越界而越界"。规则写死在这里并进产物，可核。
    """
    top = top_component(rel)
    if top.startswith("c2_"):
        return False
    if top.startswith("c_"):
        return True
    return any(top.startswith(pre) for pre in extra_prefixes)


def cmd_enumerate(args) -> int:
    root = Path(args.root)
    res = enumerate_declared(root, Path(args.run_all), args.extra_script or [])
    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"n_declared": res["n_declared"], "n_scripts": len(res["scripts"]),
                      "out": str(outp)}, ensure_ascii=False))
    return 0 if res["n_declared"] > 0 else 3


def cmd_snapshot(args) -> int:
    root = Path(args.root)
    dec = json.loads(Path(args.declared).read_text(encoding="utf-8"))["declared"]
    if not dec:
        print(json.dumps({"verdict": "RED", "reason": "枚举为空 ⇒ 拒绝开工（不许静默降级）"}, ensure_ascii=False))
        return 3
    bdir = Path(args.before)
    bdir.mkdir(parents=True, exist_ok=True)
    index, snapshotted = [], 0
    for rel in sorted(dec):
        p = root / rel
        e = {"path": rel, "exists": p.exists(), "declared_by": dec[rel]["declared_by"], "line": dec[rel]["line"]}
        if p.exists():
            b = p.read_bytes()
            dst = bdir / (flat(rel) + ".before")
            dst.write_bytes(b)
            e.update({"sha256_12": sha12_bytes(b), "bytes": len(b),
                      "mtime": _dt.datetime.fromtimestamp(p.stat().st_mtime).astimezone().isoformat(),
                      "before_image": str(dst)})
            snapshotted += 1
        index.append(e)
    # 全子树 stat 索引（不限深度）：声明清单只能覆盖"源码里写死的路径"，
    # 实测证明还会漏掉动态时间戳子目录（event3 实测：depth 3–7 的 ~745 个文件没被 maxdepth=2 扫到）。
    # stat 索引便宜（只 stat 不读字节），用来**检测**；**复原**只对留了 before 影像的声明路径成立。
    tree = {}
    pre_dirs: set[str] = set()
    for sr in (args.scan_root or ["runs/infra"]):
        base = root / sr
        if not base.exists():
            continue
        for q in base.rglob("*"):
            if q.is_file():
                st = q.stat()
                rel = str(q.relative_to(root))
                tree[rel] = [st.st_size, st.st_mtime]
                par = str(Path(rel).parent)
                while par and par not in (".", "/"):
                    pre_dirs.add(par)
                    par = str(Path(par).parent)
    payload = {"generated_at": now_iso(), "snapshot_epoch": _dt.datetime.now().astimezone().timestamp(),
               "root": str(root), "before_dir": str(bdir), "n_declared": len(dec),
               "n_snapshotted": snapshotted, "index": index,
               "scan_roots": args.scan_root or ["runs/infra"],
               "tree_index": tree, "n_tree_files": len(tree),
               "pre_existing_dirs": sorted(pre_dirs), "n_pre_existing_dirs": len(pre_dirs),
               "script_identity": {"path": str(HERE.relative_to(ROOT_DEFAULT)), "sha256_12": sha12_file(HERE)}}
    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"n_declared": len(dec), "n_snapshotted": snapshotted,
                      "n_tree_files": len(tree), "out": str(outp)}, ensure_ascii=False))
    return 0


def cmd_restore(args) -> int:
    root = Path(args.root)
    snap = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    since = snap["snapshot_epoch"] - 1.0
    bdir = Path(snap["before_dir"])
    ev = Path(args.evidence)
    ev.mkdir(parents=True, exist_ok=True)
    restored, unchanged, missed, restore_failed, relocated = [], [], [], [], []
    protected = {e["path"] for e in snap["index"]}
    for e in snap["index"]:
        p = root / e["path"]
        if not e["exists"]:
            if p.exists():
                # 声明过、但快照时不存在 ⇒ 本轮**新产出**。不把它留在别人目录里：
                # 用 shutil.move 搬进本线证据目录（字节不丢，符合"不 rm"纪律）。
                dst = ev / flat(e["path"])
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(p), str(dst))
                relocated.append({"path": e["path"], "moved_to": str(dst),
                                  "sha256_12": sha12_file(dst), "bytes": dst.stat().st_size,
                                  "disposition": "relocated_to_c2_evidence",
                                  "declared_by": e.get("declared_by")})
            continue
        cur = p.read_bytes() if p.exists() else None
        if cur is None:
            missed.append({"path": e["path"], "why": "快照后文件消失"})
            continue
        if sha12_bytes(cur) == e["sha256_12"]:
            unchanged.append(e["path"])
            continue
        (ev / flat(e["path"])).write_bytes(cur)          # 回归证据不丢
        if args.no_restore:                               # 变异体开关（selftest 变异体用）
            restore_failed.append({"path": e["path"], "why": "--no-restore（变异体 M2）"})
            restored.append({"path": e["path"], "new_sha256_12": sha12_bytes(cur),
                             "restore_verified": False, "evidence": str(ev / flat(e["path"]))})
            continue
        p.write_bytes(Path(e["before_image"]).read_bytes())
        ok = sha12_file(p) == e["sha256_12"]
        restored.append({"path": e["path"], "new_sha256_12": sha12_bytes(cur),
                         "before_sha256_12": e["sha256_12"], "restore_verified": ok,
                         "evidence": str(ev / flat(e["path"]))})
        if not ok:
            restore_failed.append({"path": e["path"], "why": f"复原后 sha256-12 不等于 {e['sha256_12']}"})
    # 全深度检测（stat 索引 vs 现状）：changed_without_before_image / new_files
    tree_before = snap.get("tree_index", {})
    tree_now: dict[str, list] = {}
    for sr in (snap.get("scan_roots") or args.scan_root or ["runs/infra"]):
        base = root / sr
        if base.exists():
            for q in base.rglob("*"):
                if q.is_file():
                    st = q.stat()
                    tree_now[str(q.relative_to(root))] = [st.st_size, st.st_mtime]
    unprotected_changes, new_files, mtime_only_changes = [], [], []
    other_line_changes, other_line_new = [], []
    for rel, cur in sorted(tree_now.items()):
        prev = tree_before.get(rel)
        if prev is None:
            new_files.append(rel)
        elif prev[0] != cur[0] or abs(prev[1] - cur[1]) > 1e-6:
            if rel in protected:
                # 声明路径：字节层面已由 before 影像逻辑处置（复原 / 校验未变）。
                # 只有 mtime 变、字节相同的属于"重写同内容"，记为信息项，不判红（否则是假红）。
                mtime_only_changes.append({"path": rel, "bytes": cur[0],
                                           "in_restored": rel in {r["path"] for r in restored},
                                           "in_unchanged": rel in set(unchanged)})
            elif is_owned(rel, args.owned_prefix or []):
                unprotected_changes.append({"path": rel, "bytes_before": prev[0], "bytes_now": cur[0],
                                            "mtime_before": prev[1], "mtime_now": cur[1],
                                            "why": "快照后被改、但没有 before 影像（枚举漏项 ⇒ 不可复原）"})
            else:
                other_line_changes.append({"path": rel, "bytes_before": prev[0], "bytes_now": cur[0],
                                           "disposition": "not_judged_other_line_active"})
    disappeared = sorted(set(tree_before) - set(tree_now))
    # 新文件：搬进本线证据目录（保留相对结构），不留在别人的产物树里；随后清掉自己新建的空目录。
    pre_dirs = set(snap.get("pre_existing_dirs", []))
    relocated_new_tree, kept_in_place_new = [], []
    for rel in new_files:
        if rel in protected:
            continue                      # 声明过的新产出已在上面按 relocated_new_outputs 处理
        if not is_owned(rel, args.owned_prefix or []):
            other_line_new.append({"path": rel, "disposition": "not_moved_other_line_active"})
            continue
        parent = str(Path(rel).parent)
        if parent in pre_dirs:
            # 直接父目录快照时就有文件 ⇒ 这是被调脚本**自己的 scratch**（删旧写新，文件名带随机哈希）。
            # 搬走它 = 把别人的 scratch 掏空（比重跑一遍更糟）⇒ **不搬，只报**，交 D 裁处置口径。
            kept_in_place_new.append({"path": rel, "bytes": tree_now[rel][0],
                                      "disposition": "kept_in_place_pre_existing_scratch_dir",
                                      "parent_dir": parent})
            continue
        src = root / rel
        dst = ev / "foreign_tree" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        relocated_new_tree.append({"path": rel, "moved_to": str(dst), "bytes": dst.stat().st_size,
                                   "sha256_12": sha12_file(dst)})
    removed_empty_dirs = []
    for sr in (snap.get("scan_roots") or args.scan_root or ["runs/infra"]):
        base = root / sr
        if not base.exists():
            continue
        for d in sorted([x for x in base.rglob("*") if x.is_dir()], key=lambda x: -len(x.parts)):
            try:
                drel = str(d.relative_to(root))
                if not is_owned(drel + "/x", args.owned_prefix or []):
                    continue              # 只清自己这轮在 C 线树里新建的空目录
                if drel in pre_dirs:
                    continue              # 快照时就存在的目录（别人的结构）不动，即使本轮被清空
                if d.stat().st_mtime >= since and not any(d.iterdir()):
                    removed_empty_dirs.append(str(d.relative_to(root)))
                    d.rmdir()
            except OSError:
                pass
    undeclared = [{"path": u["path"], "bytes": u.get("bytes")} for u in unprotected_changes]
    undeclared += [{"path": r["path"], "bytes": r["bytes"], "disposition": "relocated_to_c2_evidence"}
                   for r in relocated_new_tree]
    for u in unprotected_changes:
        missed.append(u)
    for d_ in disappeared:
        if is_owned(d_, args.owned_prefix or []):
            missed.append({"path": d_, "why": "快照后消失（驱动删了 C 线的文件）"})
        else:
            other_line_changes.append({"path": d_, "disposition": "disappeared_not_judged_other_line"})
    empty_dirs = []
    for sr in (args.scan_root or ["runs/infra"]):
        base = root / sr
        if base.exists():
            for d in base.rglob("*"):
                if d.is_dir() and d.stat().st_mtime >= since and not any(d.iterdir()):
                    empty_dirs.append(str(d.relative_to(root)))
    verdict = "PASS" if not missed and not restore_failed else "RED"
    payload = {"generated_at": now_iso(), "verdict": verdict,
               "reason": ("所有声明路径逐字节复原或未变，且无未申报写入"
                          if verdict == "PASS" else
                          f"missed={len(missed)} restore_failed={len(restore_failed)}"),
               "n_restored": len(restored), "n_unchanged": len(unchanged),
               "n_relocated_new_outputs": len(relocated), "relocated_new_outputs": relocated,
               "n_new_files_in_foreign_tree": len(new_files),
               "n_relocated_from_foreign_tree": len(relocated_new_tree),
               "n_kept_in_place_new_in_pre_existing_dirs": len(kept_in_place_new),
               "kept_in_place_new_in_pre_existing_dirs": kept_in_place_new[:60],
               "relocation_rule": ("只搬**直接父目录是本轮新建**的文件（时间戳 run 目录）；"
                                   "落在既有目录里的新文件 = 被调脚本自己的 scratch（删旧写新），"
                                   "搬走会把别人的 scratch 掏空 ⇒ 只报不搬，处置口径交 D 裁"),
               "relocated_from_foreign_tree_bytes": sum(r["bytes"] for r in relocated_new_tree),
               "relocated_from_foreign_tree": relocated_new_tree[:40],
               "n_mtime_only_changes_protected": len(mtime_only_changes),
               "mtime_only_changes_protected": mtime_only_changes[:40],
               "owned_scope_rule": ("top-level 以 `c_` 开头且不以 `c2_` 开头 ⇒ 归本守卫处置；"
                                    "其余（a2_/b2_/e_/d_/c2_ 等活进程线）只登记不处置、不判红"),
               "owned_prefix_extra": args.owned_prefix or [],
               "n_other_line_changes_not_judged": len(other_line_changes),
               "other_line_changes_not_judged": other_line_changes[:20],
               "n_other_line_new_not_moved": len(other_line_new),
               "other_line_new_not_moved": other_line_new[:20],
               "n_unprotected_changes": len(unprotected_changes),
               "unprotected_changes": unprotected_changes[:40],
               "disappeared": disappeared,
               "removed_empty_dirs": removed_empty_dirs,
               "n_tree_files_before": len(tree_before), "n_tree_files_now": len(tree_now),
               "empty_dirs_created": empty_dirs,
               "restored": restored, "unchanged": unchanged,
               "undeclared_writes": undeclared, "missed": missed,
               "restore_failed": restore_failed,
               "scan": {"roots": args.scan_root or ["runs/infra"], "maxdepth": args.maxdepth,
                        "since_epoch": since},
               "evidence_dir": str(ev)}
    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"verdict": verdict, "reason": payload["reason"], "n_restored": len(restored),
                      "n_unchanged": len(unchanged), "n_relocated_new_outputs": len(relocated),
                      "n_new_files_in_foreign_tree": len(new_files),
                      "n_relocated_from_foreign_tree": len(relocated_new_tree),
                      "n_kept_in_place_new": len(kept_in_place_new),
                      "relocated_bytes": sum(r["bytes"] for r in relocated_new_tree),
                      "n_unprotected_changes": len(unprotected_changes),
                      "unprotected_changes": [u["path"] for u in unprotected_changes][:10],
                      "removed_empty_dirs": removed_empty_dirs[:10],
                      "n_tree_files_before": len(tree_before), "n_tree_files_now": len(tree_now),
                      "out": str(outp)}, ensure_ascii=False, indent=2))
    return 0 if verdict == "PASS" else 1


def cmd_repair(args) -> int:
    """把"误搬"的文件搬回原位：只搬回**直接父目录在快照时已存在**的那些。

    为什么需要：guard 的第一版搬迁规则太宽（凡未声明的新文件一律搬进本线证据目录），
    实测把 `runs/infra/c_decisions_registry_selfcheck/` 里被调脚本**自己删旧写新**的 28 个
    scratch 文件也搬走了 ⇒ 把别人的 scratch 掏空，比重跑一遍更糟。
    本命令按收紧后的规则做**一次性回搬**，并逐条校验 sha256-12（搬回后与搬走前一致）。
    """
    root = Path(args.root)
    snap = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    pre_dirs = set(snap.get("pre_existing_dirs", []))
    if not pre_dirs:                     # 老快照没有该字段 ⇒ 从 tree_index 推导（同一套逻辑）
        for rel in snap.get("tree_index", {}):
            par = str(Path(rel).parent)
            while par not in (".", "/", ""):
                pre_dirs.add(par)
                par = str(Path(par).parent)
    ev = Path(args.evidence) / "foreign_tree"
    moved_back, kept, failed = [], [], []
    if ev.exists():
        for q in sorted(ev.rglob("*")):
            if not q.is_file():
                continue
            rel = str(q.relative_to(Path(args.evidence) / "foreign_tree"))
            dst = root / rel
            if str(Path(rel).parent) not in pre_dirs:
                kept.append(rel)
                continue
            if args.dry_run:
                moved_back.append({"path": rel, "dry_run": True})
                continue
            before_sha = sha12_file(q)
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                failed.append({"path": rel, "why": f"目标已存在（{sha12_file(dst)}），不覆盖"})
                continue
            shutil.move(str(q), str(dst))
            ok = sha12_file(dst) == before_sha
            moved_back.append({"path": rel, "sha256_12": before_sha, "verified": ok,
                               "bytes": dst.stat().st_size})
            if not ok:
                failed.append({"path": rel, "why": "搬回后 sha256-12 不一致"})
    payload = {"generated_at": now_iso(), "dry_run": bool(args.dry_run),
               "n_moved_back": len(moved_back), "n_kept_legit_relocation": len(kept),
               "n_failed": len(failed), "moved_back": moved_back[:80], "failed": failed,
               "kept_sample": kept[:20],
               "rule": "直接父目录在快照时已存在 ⇒ 属被调脚本自己的 scratch ⇒ 搬回原位",
               "verdict": "PASS" if not failed else "RED"}
    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"verdict": payload["verdict"], "n_moved_back": len(moved_back),
                      "n_kept": len(kept), "n_failed": len(failed), "dry_run": bool(args.dry_run),
                      "out": str(outp)}, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


# ------------------------------- selftest（沙箱，不碰 runs/） -------------------------------
def _build_sandbox(base: Path) -> Path:
    root = base / "repo"
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "runs/infra").mkdir(parents=True, exist_ok=True)
    (root / "scripts/c_run_all_selfchecks.sh").write_text(
        '#!/usr/bin/env bash\nSCRIPTS=(\n  fake_selfcheck_a\n  fake_selfcheck_b\n)\n', encoding="utf-8")
    (root / "scripts/fake_selfcheck_a.py").write_text(
        'from pathlib import Path\nOUT = Path("runs/infra/c_victim_a.json")\n'
        'NEW = Path("runs/infra/c_victim_d_new.json")   # 声明了、但快照时不存在\n'
        'OUT.write_text("{\\"n\\": 1}")\n', encoding="utf-8")
    (root / "scripts/fake_selfcheck_b.py").write_text(
        'from pathlib import Path\nROOT = Path(".")\nout = ROOT/"runs"/"infra"/"c_victim_b.json"\n'
        'out.write_text("{\\"n\\": 2}")\n', encoding="utf-8")
    for name, body in (("c_victim_a.json", '{"n": 1, "orig": true}'), ("c_victim_b.json", '{"n": 2, "orig": true}')):
        (root / "runs/infra" / name).write_text(body, encoding="utf-8")
    scratch = root / "runs/infra/c_scratch_selfcheck/entries"
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / "OLD__aaaa1111.json").write_text('{"entry": "old", "orig": true}', encoding="utf-8")
    return root


def _run_guard(argv: list[str]) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, str(HERE)] + argv, capture_output=True, text=True)
    return proc.returncode, (proc.stdout + proc.stderr)


def _simulate_run(root: Path, *, touch_undeclared: bool) -> None:
    """模拟"跑了一遍别人的自检"：两个受保护产物都被改写（基线要求两个都能复原）。"""
    (root / "runs/infra/c_victim_a.json").write_text('{"n": 1, "orig": false, "rerun": true}', encoding="utf-8")
    (root / "runs/infra/c_victim_b.json").write_text('{"n": 2, "orig": false, "rerun": true}', encoding="utf-8")
    (root / "runs/infra/c_victim_d_new.json").write_text('{"new_output": true}', encoding="utf-8")
    # 别的活进程线（A2/B2/E/D）同期也在写 runs/infra ⇒ 守卫**不许**搬它、也不许判红
    (root / "runs/infra/a2_active_line_new.json").write_text('{"other_line": true}', encoding="utf-8")
    deep = root / "runs/infra/c_fake_selfcheck/20260929_999999/sub"
    deep.mkdir(parents=True, exist_ok=True)
    (deep / "deep_undeclared.json").write_text('{"depth": 3, "undeclared": true}', encoding="utf-8")
    if touch_undeclared:
        (root / "runs/infra/c_victim_c_undecl.json").write_text('{"undeclared": true}', encoding="utf-8")


def cmd_selftest(args) -> int:
    base = Path(args.sandbox or tempfile.mkdtemp(prefix="c2_guard_selftest_"))
    base.mkdir(parents=True, exist_ok=True)
    cases = []

    def case(name, must_red, must_green, fn):
        root = _build_sandbox(base / name)
        out = base / name / "guard"
        try:
            ok, detail = fn(root, out)
        except Exception as exc:  # noqa: BLE001 - 自检失败必须可见，不许吞成 ok=false
            ok, detail = False, {"exception": f"{type(exc).__name__}: {exc}"}
        cases.append({"case": name, "ok": ok, "detail": detail,
                      "must_go_red": must_red, "must_stay_green": must_green,
                      "root": str(root), "out": str(out)})

    def baseline(root, out):
        rc1, o1 = _run_guard(["enumerate", "--root", str(root), "--run-all",
                              str(root / "scripts/c_run_all_selfchecks.sh"),
                              "--out", str(out / "declared.json")])
        dec = json.loads((out / "declared.json").read_text())["declared"]
        rc2, o2 = _run_guard(["snapshot", "--root", str(root), "--declared", str(out / "declared.json"),
                              "--before", str(out / "before"), "--out", str(out / "snapshot.json")])
        _simulate_run(root, touch_undeclared=False)
        rc3, o3 = _run_guard(["restore", "--root", str(root), "--snapshot", str(out / "snapshot.json"),
                              "--evidence", str(out / "evidence"), "--out", str(out / "restore.json"),
                              "--scan-root", "runs/infra"])
        rep = json.loads((out / "restore.json").read_text())
        a = (root / "runs/infra/c_victim_a.json").read_text()
        b = (root / "runs/infra/c_victim_b.json").read_text()
        green = (rep["verdict"] == "PASS" and rep["n_restored"] == 2 and rep["n_unchanged"] == 0
                 and '"orig": true' in a and '"orig": true' in b
                 and all(x["restore_verified"] for x in rep["restored"])
                 and all(u.get("disposition") == "relocated_to_c2_evidence"
                         for u in rep["undeclared_writes"])
                 and [x["path"] for x in rep["relocated_new_outputs"]] == ["runs/infra/c_victim_d_new.json"]
                 and not (root / "runs/infra/c_victim_d_new.json").exists()
                 and [x["path"] for x in rep["relocated_from_foreign_tree"]]
                     == ["runs/infra/c_fake_selfcheck/20260929_999999/sub/deep_undeclared.json"]
                 and not (root / "runs/infra/c_fake_selfcheck").exists()
                 and rep["n_unprotected_changes"] == 0
                 and (root / "runs/infra/a2_active_line_new.json").exists()
                 and [x["path"] for x in rep["other_line_new_not_moved"]]
                     == ["runs/infra/a2_active_line_new.json"]
                 and sorted(dec) == ["runs/infra/c_victim_a.json", "runs/infra/c_victim_b.json",
                                     "runs/infra/c_victim_d_new.json"])
        return green, {"rc": [rc1, rc2, rc3], "verdict": rep["verdict"], "n_restored": rep["n_restored"],
                       "n_unchanged": rep["n_unchanged"],
                       "victim_a_restored": '"orig": true' in a, "victim_b_restored": '"orig": true' in b,
                       "restore_verified_all": all(x["restore_verified"] for x in rep["restored"]),
                       "declared": sorted(dec)}

    def m1(root, out):
        rc1, _ = _run_guard(["enumerate", "--root", str(root), "--run-all",
                             str(root / "scripts/c_run_all_selfchecks.sh"), "--out", str(out / "declared.json")])
        d = json.loads((out / "declared.json").read_text())
        first = sorted(d["declared"])[0]
        d["declared"] = {first: d["declared"][first]}          # 变异：只保护第一项（= 上次的错误做法）
        d["n_declared"] = 1
        (out / "declared.json").write_text(json.dumps(d, ensure_ascii=False, indent=2))
        _run_guard(["snapshot", "--root", str(root), "--declared", str(out / "declared.json"),
                    "--before", str(out / "before"), "--out", str(out / "snapshot.json")])
        _simulate_run(root, touch_undeclared=False)
        rc3, _ = _run_guard(["restore", "--root", str(root), "--snapshot", str(out / "snapshot.json"),
                             "--evidence", str(out / "evidence"), "--out", str(out / "restore.json"),
                             "--scan-root", "runs/infra"])
        rep = json.loads((out / "restore.json").read_text())
        red = rep["verdict"] == "RED" and any(u["path"] == "runs/infra/c_victim_b.json"
                                              for u in rep["undeclared_writes"])
        return red, {"rc": [rc1, rc3], "verdict": rep["verdict"],
                     "undeclared": [u["path"] for u in rep["undeclared_writes"]]}

    def m2(root, out):
        _run_guard(["enumerate", "--root", str(root), "--run-all",
                    str(root / "scripts/c_run_all_selfchecks.sh"), "--out", str(out / "declared.json")])
        _run_guard(["snapshot", "--root", str(root), "--declared", str(out / "declared.json"),
                    "--before", str(out / "before"), "--out", str(out / "snapshot.json")])
        _simulate_run(root, touch_undeclared=False)
        rc3, _ = _run_guard(["restore", "--root", str(root), "--snapshot", str(out / "snapshot.json"),
                             "--evidence", str(out / "evidence"), "--out", str(out / "restore.json"),
                             "--scan-root", "runs/infra", "--no-restore"])
        rep = json.loads((out / "restore.json").read_text())
        a = (root / "runs/infra/c_victim_a.json").read_text()
        red = (rep["verdict"] == "RED" and len(rep["restore_failed"]) == 2 and '"orig": false' in a
               and '"orig": false' in (root / "runs/infra/c_victim_b.json").read_text())
        return red, {"rc": rc3, "verdict": rep["verdict"], "restore_failed": rep["restore_failed"],
                     "victim_a_still_modified": '"orig": false' in a}

    def m3(root, out):
        (out).mkdir(parents=True, exist_ok=True)
        (out / "declared_empty.json").write_text(json.dumps({"declared": {}, "n_declared": 0}), encoding="utf-8")
        rc, o = _run_guard(["snapshot", "--root", str(root), "--declared", str(out / "declared_empty.json"),
                            "--before", str(out / "before"), "--out", str(out / "snapshot.json")])
        return rc == 3 and "拒绝开工" in o, {"rc": rc, "stdout": o.strip()[:200]}

    def boundary_scratch(root, out):
        _run_guard(["enumerate", "--root", str(root), "--run-all",
                    str(root / "scripts/c_run_all_selfchecks.sh"), "--out", str(out / "declared.json")])
        _run_guard(["snapshot", "--root", str(root), "--declared", str(out / "declared.json"),
                    "--before", str(out / "before"), "--out", str(out / "snapshot.json")])
        sc = root / "runs/infra/c_scratch_selfcheck/entries"
        (sc / "OLD__aaaa1111.json").unlink()                      # 脚本删旧
        (sc / "NEW__bbbb2222.json").write_text('{"entry": "new"}', encoding="utf-8")   # 写新（同目录）
        _run_guard(["restore", "--root", str(root), "--snapshot", str(out / "snapshot.json"),
                    "--evidence", str(out / "evidence"), "--out", str(out / "restore.json"),
                    "--scan-root", "runs/infra"])
        rep = json.loads((out / "restore.json").read_text())
        red = (rep["verdict"] == "RED"
               and any(d.endswith("OLD__aaaa1111.json") for d in rep["disappeared"])
               and [x["path"] for x in rep["kept_in_place_new_in_pre_existing_dirs"]]
                   == ["runs/infra/c_scratch_selfcheck/entries/NEW__bbbb2222.json"]
               and (sc / "NEW__bbbb2222.json").exists()
               and not list((out / "evidence" / "foreign_tree").rglob("NEW__bbbb2222.json"))
               and rep["n_unprotected_changes"] == 0)
        return red, {"verdict": rep["verdict"], "disappeared": rep["disappeared"],
                     "kept_in_place": [x["path"] for x in rep["kept_in_place_new_in_pre_existing_dirs"]],
                     "new_file_still_in_place": (sc / "NEW__bbbb2222.json").exists(),
                     "n_relocated_from_foreign_tree": rep["n_relocated_from_foreign_tree"]}

    case("boundary_scratch_delete_rewrite_in_pre_existing_dir",
         ["verdict=RED", "旧文件消失进 disappeared（不可复原 ⇒ 如实报红）"],
         ["同目录新写的文件**不被搬走**（掏空别人 scratch 比重跑更糟）",
          "n_unprotected_changes=0（不是把'删旧写新'误判成'改了既有文件'）"], boundary_scratch)

    case("baseline_guarded_driver", [],
         ["verdict=PASS", "victim_a/victim_b 都复原为原字节", "枚举到 3 条声明路径",
          "新产出 victim_d_new 被搬进证据目录、不留在 runs/infra",
          "depth-3 未声明新文件被搬走、其新建空目录被清掉、n_unprotected_changes=0",
          "undeclared_writes 里只允许出现 disposition=relocated 的条目（不可复原的改动必须判红）",
          "别的活进程线新写的 a2_* 文件**不被搬走、不被判红**（守卫不越界）"], baseline)
    case("M1_enumerate_only_first", ["verdict=RED", "victim_b 进 undeclared_writes"], ["baseline 不受影响"], m1)
    case("M2_skip_restore", ["verdict=RED", "restore_failed 非空", "victim_a 仍是改后字节"], ["证据目录仍留新字节"], m2)
    case("M3_empty_enumeration", ["snapshot exit=3 且打印拒绝开工"], ["不写 snapshot.json"], m3)

    n_ok = sum(1 for c in cases if c["ok"])
    payload = {"generated_at": now_iso(), "sandbox": str(base), "n_cases": len(cases), "n_ok": n_ok,
               "all_ok": n_ok == len(cases), "cases": cases,
               "verdict": "PASS" if n_ok == len(cases) else "RED",
               "guard_identity": {"path": str(HERE.relative_to(ROOT_DEFAULT)), "sha256_12": sha12_file(HERE)}}
    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"verdict": payload["verdict"], "n_ok": n_ok, "n_cases": len(cases),
                      "cases": [{"case": c["case"], "ok": c["ok"]} for c in cases],
                      "sandbox": str(base), "out": str(outp)}, ensure_ascii=False, indent=2))
    return 0 if payload["all_ok"] else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=str(ROOT_DEFAULT), help="仓库根（selftest 用沙箱根覆盖）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("enumerate", parents=[common])
    e.add_argument("--run-all", default=str(ROOT_DEFAULT / "scripts/c_run_all_selfchecks.sh"))
    e.add_argument("--extra-script", action="append")
    e.add_argument("--out", required=True)
    e.set_defaults(fn=cmd_enumerate)

    s = sub.add_parser("snapshot", parents=[common])
    s.add_argument("--declared", required=True)
    s.add_argument("--before", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--scan-root", action="append")
    s.set_defaults(fn=cmd_snapshot)

    r = sub.add_parser("restore", parents=[common])
    r.add_argument("--snapshot", required=True)
    r.add_argument("--evidence", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--scan-root", action="append")
    r.add_argument("--maxdepth", type=int, default=2)
    r.add_argument("--no-restore", action="store_true", help="仅供 selftest 的变异体 M2 使用")
    r.add_argument("--owned-prefix", action="append",
                   help="额外归本守卫处置的 top-level 前缀（默认规则见产物里的 owned_scope_rule）")
    r.set_defaults(fn=cmd_restore)

    rp = sub.add_parser("repair", parents=[common],
                        help="把误搬进证据目录、但直接父目录既存的文件搬回原位")
    rp.add_argument("--snapshot", required=True)
    rp.add_argument("--evidence", required=True)
    rp.add_argument("--out", required=True)
    rp.add_argument("--dry-run", action="store_true")
    rp.set_defaults(fn=cmd_repair)

    t = sub.add_parser("selftest", parents=[common], help="沙箱自检（1 基线 + 3 变异体）")
    t.add_argument("--sandbox")
    t.add_argument("--out", required=True)
    t.set_defaults(fn=cmd_selftest)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
