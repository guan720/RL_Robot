#!/usr/bin/env python3
"""C2 · 广播面的**安全追加**器（多写者面纪律：前像 + 只追加 + 追加后自证）。

为什么需要单独一件工具（而不是 `cat >>`）：
* `daily_report.md` 是**多写者面**（A2/B2/C2/E/F/D 都往里追加）。裁定 105.9-③ 刚记了
  D 自己在这张面上**覆盖了 B2 的节标题**（⑲ 第 22 件），根因是「用行数/计数派生索引」。
  本工具**不用任何行号索引**：只做「读原字节 → 落前像 → `ab` 追加 → 复算前缀 sha」。
* 纪律：**前像以「改前 sha」命名**（`<name>.before_<sha12>`）、`cp -p` 保全 mtime、
  **追加不覆写**、追加后必须自证「我的节之前的全部字节与前像逐字节相同」。
* 三值纪律：任何一步读不到 ⇒ `not_measured` + `why`，**不写 false、不猜**。

只读他线、只写：① 目标件的**末尾追加**（不改动既有字节）、② 前像目录、③ 自己目录里的记录件。
不 `rm`（前像与记录件都留着）。不 `git`（B2 是唯一 git 写者）。
"""
from __future__ import annotations

import datetime
import hashlib
import json
import pathlib
import shutil
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
SELF_REL = "scripts/c2_safe_append_broadcast.py"
N_LINES_CALIBER = ("裁定 98.5：`n_lines_splitlines` = `len(read_text().splitlines())`；"
                   "`n_lines_wc` = 换行符个数（`wc -l`）。**对账的唯一约束性判据 = "
                   "`sha256[:12]`**，行数只作辅证且必须点名口径。")


def sha12_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:12]


def sha12_file(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def safe_append(*, target_rel: str, section_rel: str, before_dir_rel: str,
                record_rel: str, section_label: str) -> dict:
    as_of = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    tgt = REPO / target_rel
    sec = REPO / section_rel
    bdir = REPO / before_dir_rel
    rec: dict = {
        "artifact": "c2_safe_append_record", "as_of": as_of, "section_label": section_label,
        "tool": {"path": SELF_REL, "sha256_12": sha12_file(REPO / SELF_REL)},
        "target": target_rel, "section_source": section_rel,
        "measurement_status": "not_measured",
        "method": ("读原字节 → `cp -p` 前像（以改前 sha 命名）→ `open(...,'ab')` 追加 → "
                   "复算「前 N 字节 sha == 前像 sha」∧「尾部字节 == 节字节」。**不使用任何行号索引**"
                   "（裁定 105.9-③）。"),
        "n_lines_caliber": N_LINES_CALIBER,
    }
    if not tgt.is_file():
        rec["why"] = f"目标件不在盘：{target_rel}"
        return rec
    if not sec.is_file():
        rec["why"] = f"节件不在盘：{section_rel}"
        return rec

    before_bytes = tgt.read_bytes()
    before_sha = sha12_bytes(before_bytes)
    before_n = len(before_bytes)
    sec_bytes = sec.read_bytes()

    bdir.mkdir(parents=True, exist_ok=True)
    before_path = bdir / f"{pathlib.Path(target_rel).name}.before_{before_sha}"
    # `existed_before_copy` 必须在 copy **之前**取 —— 修前它写在 `shutil.copy2` 之后，
    # 于是恒为 `true`（一把永远不会说"没有"的尺 = 缺陷类 ⑲ 同族）。C2 自报并已修。
    existed_before_copy = bool(before_path.exists())
    if not existed_before_copy:
        shutil.copy2(tgt, before_path)          # copy2 = 保全 mtime（`cp -p` 语义）
    rec["before_image"] = {
        "path": before_path.relative_to(REPO).as_posix(),
        "sha256_12": sha12_file(before_path),
        "n_bytes": before_path.stat().st_size,
        "n_lines_wc": before_bytes.decode("utf-8", "replace").count("\n"),
        "n_lines_splitlines": len(before_bytes.decode("utf-8", "replace").splitlines()),
        "existed_before_copy": existed_before_copy,
        "copy_performed_this_run": bool(not existed_before_copy),
        "measurement_status": "measured",
    }

    with tgt.open("ab") as fh:                  # 追加，不覆写
        fh.write(sec_bytes)
        fh.flush()
        import os
        os.fsync(fh.fileno())

    after_bytes = tgt.read_bytes()
    prefix_ok = sha12_bytes(after_bytes[:before_n]) == before_sha
    tail_ok = after_bytes[before_n:before_n + len(sec_bytes)] == sec_bytes
    after_txt = after_bytes.decode("utf-8", "replace")
    rec.update({
        "measurement_status": "measured",
        "prefix_bytes_checked": before_n,
        "prefix_sha256_12_after_append": sha12_bytes(after_bytes[:before_n]),
        "prefix_sha_equals_before_image": bool(prefix_ok),
        "appended_tail_equals_section_bytes": bool(tail_ok),
        "n_bytes_appended": len(sec_bytes),
        "section_n_lines_wc": sec_bytes.decode("utf-8", "replace").count("\n"),
        "section_n_lines_splitlines": len(sec_bytes.decode("utf-8", "replace").splitlines()),
        "after": {"sha256_12": sha12_bytes(after_bytes), "n_bytes": len(after_bytes),
                  "n_lines_wc": after_txt.count("\n"),
                  "n_lines_splitlines": len(after_txt.splitlines())},
        "other_writer_appended_in_between": bool(len(after_bytes) != before_n + len(sec_bytes)),
        "verdict": ("GREEN" if (prefix_ok and tail_ok) else "RED"),
        "verdict_caliber": ("**这里的 GREEN 只指「追加纯度自证通过」**（我的节之前的字节一个没改、"
                            "尾部逐字节等于节件），**不是**任何 policy / 能力判词（裁定 46/101.3）。"),
        "capability_claim": False, "policy_executed": False, "gpu_used": False,
    })
    rp = REPO / record_rel
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    rec["record_identity"] = {"path": record_rel, "sha256_12": sha12_file(rp),
                              "n_bytes": rp.stat().st_size}
    return rec


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--section", required=True)
    ap.add_argument("--before-dir", required=True)
    ap.add_argument("--record", required=True)
    ap.add_argument("--label", required=True)
    a = ap.parse_args(argv)
    rec = safe_append(target_rel=a.target, section_rel=a.section,
                      before_dir_rel=a.before_dir, record_rel=a.record,
                      section_label=a.label)
    print(json.dumps(rec, ensure_ascii=False, indent=1))
    return 0 if rec.get("verdict") == "GREEN" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
