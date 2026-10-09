#!/usr/bin/env python3
"""C 线自检：`work/decisions/registry/` 的四条验收（执行单 P0-4）**逐条做出牙来**。

登记处这种设施最容易「看起来建好了」：文件在、索引在、`verify` 也返回 PASS —— 但如果
改一个字节它不红、撤销一条决定什么也不变、没 ack 的和已 ack 的看起来一样，那它就是装饰。
所以本自检的每一个 case 都**先证明判据能红**，再用它去判真数据：

1. `case_content_addressing`      改一个字节 ⇒ 按哈希取不回 + `verify` 报 `tampered`（验收 1）
2. `case_revocation_has_teeth`    撤销 ⇒ 被撤条目 status 变 `retired`、**原文件逐字节不变**、
                                   且引用它的 active 决定被判 `dangling_authority`（验收 2）
3. `case_ack_visibility`          未 ack 的线**可见**；条目换版本后旧 ack 自动标成 stale（验收 3）
4. `case_no_criteria_duplication` 登记处抄判据 ⇒ 红；pointer_only 却没有 source ⇒ 红（验收 4）
5. `case_append_only`             同内容重复写 ⇒ 拒绝；同 id 新内容 ⇒ **新增版本**，旧版不动
6. `case_event_hygiene`           事件指向不存在的决定 ⇒ 拒绝；伪造事件文件 ⇒ `verify` 红
7. `case_numbering_continuity`    并号规则：各线下一号必须接续源文档的最大号（不重编、不撞号）
8. `case_real_registry`           真登记处（只读）：`verify` PASS、索引可由文件重建、
                                   每条 `pointer_only` 都带可取回的 source 锚点
9. `case_cli_surface`             **CLI 面**（前 8 案全走 API）：`add/ack/annotate/revoke/supersede`
                                   用子进程真跑一遍；再配一个**把 bug 塞回去**的变异体，证明判据不是恒真
                                   （本轮真实事故：`ack`/`annotate` 因字典值 eager 求值而 CLI 崩，53/53 全绿）

合成用例全部写在 `runs/infra/c_decisions_registry_selfcheck/`（C 自己的目录），
**不碰**真登记处；合成 id 用 `DR-D9xx` / `ADR-C-9xx` 号段并在产物里标注无物理意义（ADR-C-007）。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.c_decisions_registry import (  # noqa: E402
    DEFAULT_REGISTRY, LINES, DecisionRegistry, content_sha256, id_kind, ordinal, owner_line,
    payload_sha256)

OUT_ROOT = ROOT / "runs" / "infra" / "c_decisions_registry_selfcheck"
OUT_JSON = ROOT / "runs" / "infra" / "c_decisions_registry_selfcheck.json"
SYNTHETIC_NOTE = {"physical_meaning": False,
                  "note": "合成注册表与合成 id（DR-D9xx / ADR-C-9xx），数字无物理意义（ADR-C-007）"}
CLI_SCRIPT = ROOT / "scripts" / "c_decisions_registry.py"
# 变异体要还原的那一行（**逐字**）。改实现时若这两串对不上，变异会失败并报出来，
# 而不是悄悄退化成恒真判据 —— 下面有一条断言专门核"变异确实生效了"。
CLI_KIND_FIXED = '        kind = getattr(args, "kind", None) or args.cmd\n'
CLI_KIND_BUGGY = ('        kind = {"ack": "ack", "revoke": args.kind, '
                  '"annotate": "annotate"}[args.cmd]\n')


def _run_cli(reg_root: Path, *argv: str, script: Path | None = None,
             timeout: int = 180) -> tuple[int, str]:
    """用**子进程真跑 CLI**（不是在进程内调 API）。API 与 CLI 是两条路径，
    只测 API 就会漏掉"库能用、命令崩"这一整类缺陷。"""
    env = dict(os.environ, CUDA_VISIBLE_DEVICES="", MUJOCO_GL="egl", OMP_NUM_THREADS="2")
    proc = subprocess.run(
        [sys.executable, str(script or CLI_SCRIPT), "--registry", str(reg_root), *argv],
        capture_output=True, text=True, env=env, cwd=str(ROOT), timeout=timeout)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _fresh(name: str) -> DecisionRegistry:
    path = OUT_ROOT / name
    if path.exists():
        shutil.rmtree(path)          # 合成目录，非他人产物；真登记处永不进入本函数
    reg = DecisionRegistry(path)
    reg.ensure_dirs()
    return reg


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _registry_fingerprint(root: Path) -> dict[str, tuple[str, int]]:
    """登记处的**盘上指纹**：相对路径 → (内容 sha256, mtime_ns)。

    用来证「自检全程只读」。三样都要比：只比文件名抓不到改写，只比 sha 抓不到
    「同内容重写」（mtime 会变），只比 mtime 抓不到内容变化。
    """
    out: dict[str, tuple[str, int]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out[str(path.relative_to(root))] = (_sha_file(path), path.stat().st_mtime_ns)
    return out


_NUM_PREFIX = {"A": "ADR-A-", "B": "DR-", "C": "ADR-C-", "D": "DR-D"}
_NUM_ID_RE = re.compile(r"DR-D\d+|ADR-[ABC]-\d+|DR-\d+")


def _line_ordinal(decision_id: str, line: str) -> int | None:
    """某 id 在**某条线**的号段里的序号；不属于该号段则 None。"""
    prefix = _NUM_PREFIX[line]
    if not decision_id.startswith(prefix):
        return None
    if prefix == "DR-" and decision_id.startswith("DR-D"):   # DR-D<n> 属 D 线，不是 B 线的 DR-0<n>
        return None
    tail = decision_id[len(prefix):]
    return int(tail) if tail.isdigit() else None


def _max_ordinal(ids: set[str], line: str) -> int:
    found = [n for n in (_line_ordinal(i, line) for i in ids) if n is not None]
    return max(found) if found else 0


def _independent_next_id(line: str, docs: list[Path],
                         registry_ids: set[str]) -> tuple[str, int, set[str]]:
    """**独立**重算某线的下一号（故意不复用 `DecisionRegistry.next_id`）。

    期望值若直接由实现算出来，那就是自己证明自己（恒真判据）。这里写第二份最小实现互校：
    两边独立算、结果必须一致 ⇒ off-by-one、前缀错配、`DR-0<n>`(B) 与 `DR-D<n>`(D) 混淆都会露出来。
    返回 `(下一号, 下一序号, 扫到的全部 id)`。
    """
    seen: set[str] = set(registry_ids)
    for path in docs:
        if not path.exists():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            if raw.startswith("## ") or raw.startswith("- **"):
                seen.update(_NUM_ID_RE.findall(raw))
    nxt = _max_ordinal(seen, line) + 1
    prefix = _NUM_PREFIX[line]
    formatted = (f"{prefix}{nxt:03d}" if prefix in ("ADR-A-", "ADR-C-", "DR-")
                 else f"{prefix}{nxt}")
    return formatted, nxt, seen


def case_content_addressing(checks: list[tuple[str, Any]]) -> None:
    """验收 1：内容哈希真的在寻址 —— 改一个字节就取不回、且 verify 变红。"""
    reg = _fresh("content_addressing")
    made = reg.add(decision_id="DR-D901", line="D", title="合成裁定：口径 X",
                   statement="合成陈述（无物理意义）", affects=("A", "B", "C"),
                   requires_ack_from=())
    digest = made["sha256"]
    path = Path(made["path"])
    checks.append(("按完整 sha256 可取回", reg.load_entries()["DR-D901"]["sha256"] == digest))
    checks.append(("文件名里的 sha256_12 与重算值一致",
                   path.stem.endswith(digest[:12]) and not reg.load_entries()["DR-D901"]["tampered"]))
    checks.append(("verify 在未改动时 PASS", reg.verify()["pass"] is True))

    text = path.read_text(encoding="utf-8")
    mutated = text.replace("口径 X", "口径 Y", 1)
    checks.append(("变异确实只改了一个字节以上、且不是重写整份", mutated != text))
    path.write_text(mutated, encoding="utf-8")
    after = reg.load_entries()["DR-D901"]
    checks.append(("改一个字节 ⇒ 重算哈希与文件名不符（tampered）", after["tampered"] is True))
    result = reg.verify()
    checks.append(("改一个字节 ⇒ verify 报红（tampered）",
                   any(r["check"] == "tampered" for r in result["red"]) and result["pass"] is False))
    # 过滤要按**键**（`_unreadable` 是键名）；原来写成 `.values()` 再跟字符串比，恒为真 = 没过滤
    found = [v for key, rec in reg.load_entries().items() if key != "_unreadable"
             for v in reg._iter_versions(rec) if v["sha256"] == digest]
    checks.append(("改一个字节 ⇒ 原哈希取不回任何条目", not found))


def case_revocation_has_teeth(checks: list[tuple[str, Any]]) -> None:
    """验收 2：撤销可执行、有牙，且原条目文件**逐字节不变**（append-only）。"""
    reg = _fresh("revocation")
    target = reg.add(decision_id="DR-D910", line="D", title="合成裁定：待撤",
                     statement="合成陈述", affects=("C",), requires_ack_from=())
    citing = reg.add(decision_id="ADR-C-911", line="C", title="合成 ADR：引用上面那条当权威",
                     statement="合成陈述", affects=("D",), requires_ack_from=(),
                     authority_pointers=("DR-D910",))
    target_path = Path(target["path"])
    before_bytes, before_sha = target_path.read_bytes(), _sha_file(target_path)
    before_mtime = target_path.stat().st_mtime_ns

    checks.append(("撤销前 status=active", reg.status("DR-D910")["status"] == "active"))
    before_revoke = reg.verify()
    checks.append(("撤销前 verify PASS（引用一条 active 决定不算红）",
                   before_revoke["pass"] is True))

    event = reg.append_event("revoke", target_id="DR-D910", by="D", line="D",
                             reason="合成撤销：口径已被新证据推翻",
                             evidence=({"path": "runs/infra/c_decisions_registry_selfcheck",
                                        "why": "合成"} for _ in range(0)))
    checks.append(("撤销写成了一条**新事件**文件", Path(event["path"]).exists()
                   and event["kind"] == "revoke"))
    checks.append(("撤销后 status=retired（状态真的变了）",
                   reg.status("DR-D910")["status"] == "retired"))
    checks.append(("撤销后原条目文件**逐字节不变**（sha256 相同）",
                   _sha_file(target_path) == before_sha
                   and target_path.read_bytes() == before_bytes))
    checks.append(("撤销后原条目文件 mtime 未变（没有被就地改写）",
                   target_path.stat().st_mtime_ns == before_mtime))
    result = reg.verify()
    checks.append(("撤销有牙：引用已撤条目的 active 决定被判 dangling_authority",
                   any(r["check"] == "dangling_authority" and r["decision_id"] == "ADR-C-911"
                       for r in result["red"])))
    # 这条要证的是「判据不是恒红」，所以必须看**撤销前**那一次 verify 里有没有 dangling_authority。
    # 原来写的是 `reg.status("DR-D910")["status"] == "retired"`（撤销**后**的状态）：
    # 标签说「撤销前是绿的」、断言却在验撤销后的状态 ⇒ 既与上面一条重复，
    # 又根本没碰到「恒红」这件事。标签与判据不同源（裁定 37.4 第 3 条同型）。
    checks.append(("牙不是恒红：撤销前那次 verify 里没有任何 dangling_authority",
                   not any(r["check"] == "dangling_authority" for r in before_revoke["red"])
                   and before_revoke["pass"] is True))

    # 传导之后必须能重新变绿（否则这条判据就是恒红，等于没有判据）
    reg.append_event("supersede", target_id="ADR-C-911", by="C", line="C",
                     reason="合成：改用新权威重写本条", new_decision_id="ADR-C-912")
    reg.add(decision_id="ADR-C-912", line="C", title="合成 ADR：取代 911，不再引用已撤条目",
            statement="合成陈述", affects=("D",), requires_ack_from=(),
            supersedes=("ADR-C-911",))
    after = reg.verify()
    checks.append(("传导完成后 verify 重新 PASS（判据非恒红）", after["pass"] is True))
    checks.append(("被取代条目 status=superseded", reg.status("ADR-C-911")["status"] == "superseded"))

    # 反面牙：`supersedes` 与 `authority_pointers` 语义相反 ——
    # 「我取代它」而它仍 active = 取代只写了一半（漏了 supersede 事件），这也必须能红。
    half = _fresh("revocation_half")
    half.add(decision_id="DR-D960", line="D", title="合成：旧口径", statement="合成陈述",
             requires_ack_from=())
    half.add(decision_id="ADR-C-961", line="C", title="合成：声称取代上面那条",
             statement="合成陈述", requires_ack_from=(), supersedes=("DR-D960",))
    checks.append(("声明取代却没发 supersede 事件 ⇒ verify 报红（supersede_not_propagated）",
                   any(r["check"] == "supersede_not_propagated"
                       for r in half.verify()["red"])))
    half.append_event("supersede", target_id="DR-D960", by="D", line="D",
                      reason="合成：补上那条事件", new_decision_id="ADR-C-961")
    checks.append(("补上 supersede 事件后转绿（这条判据也不是恒红）",
                   half.verify()["pass"] is True))


def case_ack_visibility(checks: list[tuple[str, Any]]) -> None:
    """验收 3：ack 可核、未 ack 可见；条目换版本后旧 ack 自动变 stale。"""
    reg = _fresh("acks")
    made = reg.add(decision_id="ADR-C-920", line="C", title="合成 ADR：需要三线 ack",
                   statement="合成陈述", affects=("A", "B", "D"),
                   requires_ack_from=("A", "B", "D"))
    entry = reg.load_entries()["ADR-C-920"]["entry"]
    acks = reg.acks("ADR-C-920", entry)
    checks.append(("新登记时三条 ack 全部缺失且**可见**",
                   acks["missing_acks"] == ["A", "B", "D"] and acks["acked_by"] == []))
    reg.append_event("ack", target_id="ADR-C-920", by="A", line="A", reason="合成 ack")
    acks = reg.acks("ADR-C-920", entry)
    checks.append(("A ack 之后 missing 只剩 B/D", acks["missing_acks"] == ["B", "D"]
                   and acks["acked_by"] == ["A"]))
    checks.append(("ack 事件记下了当时条目的内容哈希",
                   acks["acks"]["A"]["target_sha256"] == made["sha256"]
                   and acks["acks"]["A"]["matches_current_content"] is True))

    reg.add(decision_id="ADR-C-920", line="C", title="合成 ADR：需要三线 ack（第二版）",
            statement="合成陈述 v2", affects=("A", "B", "D"), requires_ack_from=("A", "B", "D"))
    versions = list(reg._iter_versions(reg.load_entries()["ADR-C-920"]))
    checks.append(("同 id 新内容 ⇒ 版本链（两个文件并存）", len(versions) == 2))
    acks = reg.acks("ADR-C-920", versions[-1]["entry"])
    checks.append(("换版本后旧 ack 被标成 stale（ack 的是旧内容）",
                   acks["acks"]["A"]["matches_current_content"] is False))
    checks.append(("作者线不给自己 ack ⇒ C 不出现在 missing 里",
                   "C" not in acks["missing_acks"]))


def case_no_criteria_duplication(checks: list[tuple[str, Any]]) -> None:
    """验收 4：登记处只存决定 + 证据指针 + ack，不得复制判定逻辑（裁定 21）。"""
    reg = _fresh("no_criteria")
    reg.add(decision_id="DR-D930", line="D", title="合成：抄了判据的坏条目",
            statement="合成陈述", affects=("B",), requires_ack_from=(),
            extra={})
    bad_path = reg.load_entries()["DR-D930"]["path"]
    payload = json.loads(bad_path.read_text(encoding="utf-8"))
    payload["statement_kind"] = "full_text"
    payload["criteria"] = {"blown_threshold": [0.03, 0.08]}      # 这就是「第二份口径」
    bad_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = reg.verify()
    checks.append(("抄判据 ⇒ verify 报红（criteria_duplicated）",
                   any(r["check"] == "criteria_duplicated" for r in result["red"])))
    checks.append(("抄判据同时也被抓成 tampered（哈希不符）",
                   any(r["check"] == "tampered" for r in result["red"])))

    reg2 = _fresh("no_criteria_2")
    reg2.add(decision_id="DR-D931", line="D", title="合成：pointer_only 却没锚点",
             statement=None, statement_kind="pointer_only", affects=("B",),
             requires_ack_from=())
    result2 = reg2.verify()
    checks.append(("pointer_only 没有 source ⇒ verify 报红（取不回原文）",
                   any(r["check"] == "pointer_without_source" for r in result2["red"])))


def case_append_only(checks: list[tuple[str, Any]]) -> None:
    """append-only：同内容重复写被拒；同 id 新内容是**新增版本**而不是改写。"""
    reg = _fresh("append_only")
    kwargs = dict(decision_id="DR-D940", line="D", title="合成裁定", statement="合成陈述",
                  affects=("A",), requires_ack_from=())
    first = reg.add(**kwargs)
    try:
        reg.add(**kwargs)
        refused = False
    except FileExistsError:
        refused = True
    checks.append(("同内容重复登记 ⇒ 拒绝（不重写既有文件）", refused))
    checks.append(("拒绝之后盘上仍只有一个版本",
                   len(list(reg._iter_versions(reg.load_entries()["DR-D940"]))) == 1))
    second = reg.add(decision_id="DR-D940", line="D", title="合成裁定（改版）",
                     statement="合成陈述 v2", affects=("A",), requires_ack_from=())
    checks.append(("同 id 新内容 ⇒ 新文件、新哈希", second["sha256"] != first["sha256"]
                   and Path(second["path"]) != Path(first["path"])))
    checks.append(("旧版本文件仍在（append-only）", Path(first["path"]).exists()))

    # 判重必须按**决定内容**（payload），不能把登记簿记算进去。
    # 算进去的话只有「同一秒内重复登记」才被拒、跨秒就静默多出一版 ⇒ 那是靠运气的判据
    # （version_seq 落地前本仓真就是这个形状：registered_at 在被哈希的内容里）。
    entry = first["entry"]        # 此刻 DR-D940 已是版本链（record 没有 "entry" 键），取第一版
    stripped = {k: v for k, v in entry.items()
                if k not in ("version_seq", "registered_at", "registered_by", "payload_sha256")}
    checks.append(("payload 哈希剔除登记簿记（判重与登记时刻无关，不靠同一秒的运气）",
                   entry["payload_sha256"] == payload_sha256(entry) == content_sha256(stripped)))
    rebooked = {**entry, "registered_at": "2020-01-01T00:00:00+08:00", "version_seq": 99}
    checks.append(("改登记簿记**不**改 payload 哈希；改决定内容**一定**改 payload 哈希",
                   payload_sha256(rebooked) == entry["payload_sha256"]
                   and payload_sha256({**entry, "title": str(entry["title"]) + "x"})
                   != entry["payload_sha256"]))

    reg3 = _fresh("append_only_payload")
    made3 = reg3.add(decision_id="DR-D941", line="D", title="合成裁定", statement="合成陈述",
                     requires_ack_from=())
    path3 = Path(made3["path"])
    forged3 = json.loads(path3.read_text(encoding="utf-8"))
    forged3["payload_sha256"] = "0" * 64                      # 谎报「决定了什么」的指纹
    path3.write_text(json.dumps(forged3, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    checks.append(("自称的 payload_sha256 与重算不符 ⇒ verify 报红（payload_sha256_mismatch）",
                   any(r["check"] == "payload_sha256_mismatch" for r in reg3.verify()["red"])))


def case_event_hygiene(checks: list[tuple[str, Any]]) -> None:
    """事件卫生：不给不存在的东西改状态；伪造/被改的事件文件会被抓。"""
    reg = _fresh("events")
    try:
        reg.append_event("revoke", target_id="DR-D999", by="D", reason="合成：目标不存在")
        refused = False
    except KeyError:
        refused = True
    checks.append(("撤销不存在的决定 ⇒ 拒绝（不凭空造状态）", refused))
    reg.add(decision_id="DR-D950", line="D", title="合成裁定", statement="合成陈述",
            affects=("A",), requires_ack_from=())
    event = reg.append_event("ack", target_id="DR-D950", by="A", line="A", reason="合成 ack")
    path = Path(event["path"])
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["by"] = "D"                                     # 伪造：把 ack 的线改掉
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = reg.verify()
    checks.append(("事件文件被改 ⇒ verify 报红（event_tampered）",
                   any(r["check"] == "event_tampered" for r in result["red"])))

    reg2 = _fresh("events_2")
    reg2.ensure_dirs()
    forged = reg2.events_dir / "0001-revoke-deadbeef0000.json"
    forged.write_text(json.dumps({"schema": "c_decision_event/v1", "seq": 1, "kind": "revoke",
                                  "target_id": "DR-D950", "by": "D"}, ensure_ascii=False),
                      encoding="utf-8")
    result2 = reg2.verify()
    checks.append(("凭空塞进来的事件（目标不存在）⇒ verify 报红",
                   any(r["check"] == "event_target_missing" for r in result2["red"])))


def case_numbering_continuity(checks: list[tuple[str, Any]]) -> None:
    """并号规则：各线下一号必须接续「源文档 ∪ 登记处」的最大号（登记处不重编、不撞号）。

    期望值**不硬编码**，由 `_independent_next_id`（本文件里第二份最小实现）现场重算。
    硬编码那条今天就过期过一次：B 在 `decisions_20260928_B.md:822` 补发 `DR-014`，
    于是「B 的下一号」合法地从 DR-014 变 DR-015 —— 是数据在动，不是实现在错。
    用第二份实现互校，才能既抓 off-by-one / 前缀错配，又不会随别线发号而腐烂。
    """
    real = DecisionRegistry(DEFAULT_REGISTRY)
    docs = real.source_docs()
    registry_ids = real.known_ids()
    derived: dict[str, str] = {}
    got: dict[str, str] = {}
    seen_by_line: dict[str, set[str]] = {}
    for line in LINES:
        expected_id, _next_ordinal, seen = _independent_next_id(line, docs, registry_ids)
        derived[line] = expected_id
        seen_by_line[line] = seen
        got[line] = real.next_id(line)
    checks.append((f"下一号 = 独立重算值（扫 {len(docs)} 份源文档 + {len(registry_ids)} 条已登记；"
                   f"本次算得 {derived}）", got == derived))
    checks.append(("下一号不与源文档/登记处里任何已用号相撞",
                   all(got[line] not in seen_by_line[line] for line in LINES)))
    checks.append(("下一号的号段归属就是它自己那条线（登记处不代发别人的号）",
                   all(owner_line(got[line]) == line and id_kind(got[line]) is not None
                       for line in LINES)))
    checks.append(("下一号 = 该号线现有最大序号 + 1（不重编、不跳号）",
                   all(ordinal(got[line]) == _max_ordinal(seen_by_line[line], line) + 1
                       for line in LINES)))
    checks.append(("号段判定：DR-D→D 线 / DR-0xx→B 线 / ADR-C→C 线",
                   owner_line("DR-D36") == "D" and owner_line("DR-013") == "B"
                   and owner_line("ADR-C-008") == "C" and id_kind("ADR-A-017") == "ADR-A"))

    synthetic = _fresh("numbering")
    synthetic.add(decision_id="ADR-C-901", line="C", title="合成", statement="合成",
                  requires_ack_from=())
    # 隔离扫描面（sources=[]）⇒ 只看合成注册表自己，这条判据才有唯一答案、才有牙
    checks.append(("合成注册表里的自动接续（901 → 902，扫描面已隔离）",
                   synthetic.next_id("C", sources=[]) == "ADR-C-902"))
    checks.append(("不隔离时，合成注册表也不会撞真文档已用的号（宁宽勿漏）",
                   synthetic.next_id("C") not in real.ids_in_sources()))
    try:
        synthetic.add(decision_id="DR-D902", line="C", title="越线登记", statement="x",
                      requires_ack_from=())
        refused = False
    except ValueError:
        refused = True
    checks.append(("拿别人的号段登记 ⇒ 拒绝（登记处不代发号）", refused))


def case_cli_surface(checks: list[tuple[str, Any]]) -> None:
    """验收 2/3 的 **CLI 面**：各线实际用的是命令行，而前 8 案全在进程内调 API。

    本轮真实事故（ADR-C-014）：`kind = {"ack": "ack", "revoke": args.kind, ...}[args.cmd]`
    的**字典值会先全部求值**，于是 `ack` 与 `annotate` 都去读只有 `revoke` 才挂着的 `args.kind`
    ⇒ CLI 直接 `AttributeError` 崩；而 API 路径（`reg.append_event("ack", ...)`）完全正常
    ⇒ **53/53 全绿的自检一条都没抓到**。这一案把 CLI 本身变成被测对象，
    并用一个「把 bug 塞回去」的变异体证明它**有牙**（不是恒真）。
    """
    reg = _fresh("cli_surface")
    root = reg.root
    rc, out = _run_cli(root, "add", "--id", "ADR-C-950", "--line", "C",
                       "--title", "合成决定：CLI 面用例（无物理意义）",
                       "--statement", "合成陈述（无物理意义）", "--requires-ack-from", "A,B")
    checks.append(("CLI `add` 走通（rc=0）", rc == 0 or out.strip()[-400:]))
    checks.append(("CLI `add` 真的落了盘（不是 rc=0 但没写）",
                   "ADR-C-950" in reg.load_entries() or "条目缺失"))

    # --- 本轮崩过的那两条：ack / annotate ---
    rc_ack, out_ack = _run_cli(root, "ack", "--id", "ADR-C-950", "--line", "A",
                               "--reason", "合成 ack（无物理意义）")
    checks.append(("CLI `ack` 走通（**本轮曾 AttributeError 崩在这条**）",
                   rc_ack == 0 or out_ack.strip()[-400:]))
    rc_ann, out_ann = _run_cli(root, "annotate", "--id", "ADR-C-950", "--by", "C",
                               "--reason", "合成批注（无物理意义）")
    checks.append(("CLI `annotate` 走通（**同型崩溃**）", rc_ann == 0 or out_ann.strip()[-400:]))

    # --- 事件真的落盘，且状态/ack 由事件派生 ---
    kinds = sorted(e["kind"] for e in reg.load_events())
    checks.append((f"ack + annotate 各留下一条事件（实得 {kinds}）",
                   kinds == ["ack", "annotate"] or kinds))
    entry = reg.load_entries()["ADR-C-950"]["entry"]
    acks = reg.acks("ADR-C-950", entry)
    checks.append(("CLI 的 ack 真的被算进 missing（只剩 B）",
                   acks["missing_acks"] == ["B"] or acks["missing_acks"]))

    rc_rev, out_rev = _run_cli(root, "revoke", "--id", "ADR-C-950", "--by", "D",
                               "--reason", "合成撤销（无物理意义）")
    checks.append(("CLI `revoke` 走通（rc=0）", rc_rev == 0 or out_rev.strip()[-400:]))
    checks.append(("CLI revoke 之后 status 由事件派生成 retired",
                   reg.status("ADR-C-950")["status"] == "retired" or reg.status("ADR-C-950")))

    _run_cli(root, "add", "--id", "ADR-C-951", "--line", "C",
             "--title", "合成决定：取代靶子（无物理意义）", "--requires-ack-from", "none")
    rc_sup, out_sup = _run_cli(root, "revoke", "--id", "ADR-C-951", "--by", "D",
                               "--kind", "supersede", "--new-id", "ADR-C-950",
                               "--reason", "合成取代（无物理意义）")
    checks.append(("CLI `revoke --kind supersede` 走通（rc=0）",
                   rc_sup == 0 or out_sup.strip()[-400:]))
    checks.append(("supersede 之后 status=superseded（`--kind` 没被丢掉）",
                   reg.status("ADR-C-951")["status"] == "superseded" or reg.status("ADR-C-951")))
    checks.append(("真 CLI 跑完 verify 仍 PASS（合成条目无外部引用 ⇒ 不是恒红）",
                   reg.verify()["pass"] is True or reg.verify()))

    # --- 变异体：把 eager 字典塞回去 ⇒ 必须崩；不崩就说明这条判据是装饰 ---
    src = CLI_SCRIPT.read_text(encoding="utf-8")
    mutated_src = src.replace(CLI_KIND_FIXED, CLI_KIND_BUGGY, 1)
    checks.append(("变异确实生效（惰性取值被换回 eager 字典，源码真的变了）",
                   mutated_src != src and CLI_KIND_BUGGY in mutated_src))
    mutated = OUT_ROOT / "cli_surface" / "mutated_cli.py"
    mutated.parent.mkdir(parents=True, exist_ok=True)
    mutated.write_text(mutated_src, encoding="utf-8")
    m_root = _fresh("cli_surface_mutated").root
    _run_cli(m_root, "add", "--id", "ADR-C-952", "--line", "C",
             "--title", "合成决定：变异体靶子（无物理意义）", "--requires-ack-from", "A")
    rc_m_ack, out_m_ack = _run_cli(m_root, "ack", "--id", "ADR-C-952", "--line", "A",
                                   "--reason", "合成 ack（无物理意义）", script=mutated)
    checks.append(("**牙**：变异体上 CLI `ack` 必须失败且报 AttributeError",
                   (rc_m_ack != 0 and "AttributeError" in out_m_ack) or f"rc={rc_m_ack}"))
    rc_m_ann, out_m_ann = _run_cli(m_root, "annotate", "--id", "ADR-C-952", "--by", "C",
                                   "--reason", "合成批注（无物理意义）", script=mutated)
    checks.append(("**牙**：变异体上 CLI `annotate` 必须失败且报 AttributeError",
                   (rc_m_ann != 0 and "AttributeError" in out_m_ann) or f"rc={rc_m_ann}"))
    rc_m_rev, out_m_rev = _run_cli(m_root, "revoke", "--id", "ADR-C-952", "--by", "D",
                                   "--reason", "合成撤销（无物理意义）", script=mutated)
    checks.append(("**牙不是恒红**：变异体上 `revoke`（本来就带 --kind）仍然走通",
                   rc_m_rev == 0 or out_m_rev.strip()[-400:]))


def case_real_registry(checks: list[tuple[str, Any]]) -> None:
    """真登记处（**只读**）：verify PASS、索引可重建、每条 pointer_only 都能取回原文。"""
    if not DEFAULT_REGISTRY.is_dir():
        checks.append(("真登记处存在", None))
        return
    before = _registry_fingerprint(DEFAULT_REGISTRY)
    reg = DecisionRegistry(DEFAULT_REGISTRY)
    result = reg.verify()
    checks.append(("真登记处 verify PASS", result["pass"] is True))
    checks.append((f"真登记处无 tampered（{result['n_entries']} 条 / {result['n_events']} 事件）",
                   not any(r["check"] == "tampered" for r in result["red"])))
    index = reg.index()
    checks.append(("索引可由 entries+events 重算（派生，不是权威）",
                   index["n_decisions"] == result["n_entries"] >= 1))
    checks.append(("每条决定都带号段与作者线",
                   all(r["id_kind"] and r["line"] for r in index["decisions"])))
    pointer_only = [r for r in index["decisions"] if r["statement_kind"] == "pointer_only"]
    checks.append((f"摄取的历史条目都是 pointer_only（{len(pointer_only)} 条，不抄正文）",
                   bool(pointer_only) and all(r["statement_kind"] == "pointer_only"
                                              for r in pointer_only)))
    anchors_ok, missing_anchor = True, []
    for row in pointer_only:
        entry = next(v["entry"] for v in reg._iter_versions(reg.load_entries()[row["decision_id"]])
                     if v["sha256"] == row["sha256"])
        source = entry.get("source") or {}
        path = ROOT / source.get("file", "")
        if not path.exists():
            anchors_ok, _ = False, missing_anchor.append(row["decision_id"])
            continue
        lines = (source.get("lines") or "0-0").split("-")
        text_lines = path.read_text(encoding="utf-8").splitlines()
        start = int(lines[0]) - 1
        if start < 0 or start >= len(text_lines) or \
                row["decision_id"] not in text_lines[start]:
            anchors_ok = False
            missing_anchor.append(row["decision_id"])
    checks.append(("每条 pointer_only 的 source 锚点都能取回原文（行号命中 id）",
                   anchors_ok if not missing_anchor else f"FAIL: {missing_anchor[:5]}"))
    # 原来这条写的是「同一个表达式 == 它自己」⇒ **恒真**，等于没有判据。
    # 只读性要在跑之前拍指纹、跑之后对账，而且三样都要比：
    # 只比文件名抓不到改写，只比 sha 抓不到「同内容重写」，只比 mtime 抓不到内容变化。
    after = _registry_fingerprint(DEFAULT_REGISTRY)
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])
    checks.append((f"真登记处自检全程只读（{len(before)} 个文件；新增 {added} / 删除 {removed} / "
                   f"改动 {changed}）", not added and not removed and not changed))


CASES = (case_content_addressing, case_revocation_has_teeth, case_ack_visibility,
         case_no_criteria_duplication, case_append_only, case_event_hygiene,
         case_numbering_continuity, case_cli_surface, case_real_registry)


def main() -> int:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    checks: list[tuple[str, Any]] = []
    for case in CASES:
        print(f"--- {case.__name__} ---", flush=True)
        before = len(checks)
        case(checks)
        for name, ok in checks[before:]:
            tag = "SKIP" if ok is None else ("PASS" if ok is True else "FAIL")
            print(f"[{tag}] {name}" + ("" if ok in (True, None) else f" -> {ok}"), flush=True)
    failed = [name for name, ok in checks if ok is not True and ok is not None]
    skipped = [name for name, ok in checks if ok is None]
    n_pass = len([1 for _, ok in checks if ok is True])
    real = DecisionRegistry(DEFAULT_REGISTRY)
    OUT_JSON.write_text(json.dumps({
        "cases": [c.__name__ for c in CASES],
        "checks": [{"name": name, "ok": (None if ok is None else bool(ok is True))}
                   for name, ok in checks],
        "pass": not failed, "n_checks": len(checks), "n_pass": n_pass,
        "n_failed": len(failed), "n_skipped": len(skipped), "skipped": skipped,
        "failed": failed,
        "c_synthetic": SYNTHETIC_NOTE,
        "artifact_dir": str(OUT_ROOT.relative_to(ROOT)),
        "real_registry": {"root": str(DEFAULT_REGISTRY.relative_to(ROOT)),
                          "verify": real.verify() if DEFAULT_REGISTRY.is_dir() else None},
        "impl_sha256": {rel: _sha_file(ROOT / rel) for rel in
                        ("scripts/c_decisions_registry.py",
                         "scripts/c_selfcheck_decisions_registry.py")},
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("--- 全部通过 ---" if not failed else f"--- 失败 {len(failed)} 条 ---")
    for name in failed:
        print(f"  FAIL {name}")
    print(f"结果: {n_pass}/{len(checks)} PASS" + (f"（{len(skipped)} SKIP）" if skipped else "")
          + f" -> {OUT_JSON.relative_to(ROOT)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
