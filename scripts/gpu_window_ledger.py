#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GPU 窗口登记处（裁定 100.7）：append-only JSONL + `declare` / `yield` / `check` 助手。D 写死的
上限：**≤120 行** · **不含判词语义**（不产 PASS/FAIL、不做准入裁定）· **不装牙** · **互斥判据一律复用
E 的 `card_busy()`**（`scripts/e_mainline_render_calib.py`）为唯一权威（RR4 / 裁定 85.0-2-① 红线
`card_busy_detector_must_include_fd_and_cmdline_nets`：**不得重造**）。它不是门禁、是资源互斥 ⇒ 不受
治理冻结（97.3-5 的冻结面不含本件）。三值纪律：`card_busy()` 取不到 ⇒ `null` + `not_measured` +
**非零退出**，**不用 false 顶替**。退出码 `0` = 读数齐 / `3` = 有 not_measured / `2` = 用法错。
写入面归 B2（infra 单写者）；申报由各线自己调 `declare`。**为满足 ≤120 行的硬上限，顶层函数之间
不留空行**（这是格式让步、不是语义让步；本件不装牙、不产判词，故无牙可读格式）。
"""
from __future__ import annotations
import argparse, datetime, hashlib, importlib.util, json, pathlib, sys

REPO = pathlib.Path(__file__).resolve().parent.parent
LEDGER = REPO / "runs" / "infra" / "gpu_window_ledger.jsonl"
CALIB = REPO / "scripts" / "e_mainline_render_calib.py"
AUTHORITY = "裁定 100.7（最小窗口登记处；写入面归 B2）"
def now() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")
def sha12(path: pathlib.Path):
    return None if not path.exists() else hashlib.sha256(path.read_bytes()).hexdigest()[:12]
def load_calib():
    """按 A2 已在用的同一形态加载 E 的模块（它有依赖 `sys.path` 的兄弟 import）。"""
    try:
        spec = importlib.util.spec_from_file_location("e_mainline_render_calib", CALIB)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["e_mainline_render_calib"] = mod
        spec.loader.exec_module(mod)
        return mod, None
    except Exception as exc:                                        # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"
def read_ledger(path: pathlib.Path):
    rows, unparsable = [], []
    if not path.exists():
        return rows, unparsable, False
    for idx, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:                                          # noqa: BLE001
            unparsable.append(idx)
    return rows, unparsable, True
def append_row(path: pathlib.Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
def open_windows(rows: list, at: str) -> list:
    """已 `declare`、尚未 `yield`、且 `declared_start <= at <= declared_end` 的窗口（只报事实）。"""
    yielded = {(r.get("line"), r.get("task_id")) for r in rows if r.get("event") == "yield"}
    out = []
    for r in rows:
        if r.get("event") != "declare" or (r.get("line"), r.get("task_id")) in yielded:
            continue
        start, end = r.get("declared_start"), r.get("declared_end")
        if not start or not end:
            continue
        if start <= at <= end:
            out.append(r)
        elif start > at:
            out.append(dict(r, state="queued_not_started"))
    return out
def build_check(path: pathlib.Path, at: str) -> tuple[dict, int]:
    rows, unparsable, exists = read_ledger(path)
    mod, err = load_calib()
    busy, status = None, "not_measured"
    if mod is not None and hasattr(mod, "card_busy"):
        try:
            busy, status = mod.card_busy(), "measured"
        except Exception as exc:                                   # noqa: BLE001
            err = f"card_busy() raised {type(exc).__name__}: {exc}"
    doc = {"artifact": "gpu_window_ledger_check", "as_of": now(), "at": at, "authority": AUTHORITY,
           "ledger": {"path": str(path.relative_to(REPO)) if path.is_relative_to(REPO) else str(path),
                      "exists": exists, "n_rows": len(rows), "n_unparsable_lines": len(unparsable),
                      "unparsable_line_numbers": unparsable, "sha256_12": sha12(path)},
           "open_or_queued_windows": open_windows(rows, at),
           "card_busy": busy, "card_busy_measurement_status": status, "card_busy_error": err,
           "mutex_authority": {"module": "scripts/e_mainline_render_calib.py", "function": "card_busy",
                               "sha256_12": sha12(CALIB), "reused_not_reimplemented": True,
                               "ruling": "RR4 / 裁定 85.0-2-①（三网：compute-apps + `/dev/nvidia*` fd + cmdline）"},
           "no_verdict_semantics": ("本件**不产判词、不装牙**（裁定 100.7）：只登记与并查读数；"
                                    "要不要起跑由申报线自己按 `card_busy` 的读数决定"),
           "policy_executed": False, "capability_claim": None, "gpu_used": False}
    return doc, (0 if status == "measured" else 3)
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="GPU 窗口登记处（裁定 100.7）")
    ap.add_argument("cmd", choices=["declare", "yield", "check"])
    ap.add_argument("--line"); ap.add_argument("--task-id")
    ap.add_argument("--start"); ap.add_argument("--end")
    ap.add_argument("--gpu-index", type=int, default=0)
    ap.add_argument("--note", default=""); ap.add_argument("--at", default=None)
    ap.add_argument("--ledger", default=str(LEDGER)); ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    path = pathlib.Path(a.ledger)
    if a.cmd == "check":
        doc, rc = build_check(path, a.at or now())
        text = json.dumps(doc, ensure_ascii=False, indent=1) + "\n"
        if a.out:
            outp = pathlib.Path(a.out); outp.parent.mkdir(parents=True, exist_ok=True)
            outp.write_text(text, encoding="utf-8")
        print(text, end="")
        return rc
    need = ["--line", "--task-id"] + (["--start", "--end"] if a.cmd == "declare" else [])
    if any(getattr(a, k.lstrip("-").replace("-", "_")) in (None, "") for k in need):
        print(f"{a.cmd} 需要 {' '.join(need)}", file=sys.stderr)
        return 2
    row = {"event": a.cmd, "line": a.line, "task_id": a.task_id, "gpu_index": a.gpu_index,
           "recorded_at": now(), "note": a.note, "authority": AUTHORITY}
    if a.cmd == "declare":
        row.update({"declared_start": a.start, "declared_end": a.end})
    append_row(path, row)
    print(json.dumps({"appended": a.cmd, "ledger": str(path), "sha256_12": sha12(path),
                      "row": row}, ensure_ascii=False, indent=1))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
