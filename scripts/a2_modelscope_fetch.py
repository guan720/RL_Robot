#!/usr/bin/env python3
"""ModelScope 通道的**清单驱动 + 按 size/sha256 校验 + 可续传**取数器。

为什么必须有它（不是"第三个下载器"，是**另一条通道的对应物**）：
  - `runs/infra/maniskill_state_probe_20260929/hf_mirror_snapshot.py` / `hf_mirror_fetch.py`
    都绑死 hf-mirror 且 URL 是 dataset 专用（`/api/datasets/...`、`/datasets/{repo}/resolve/main/...`）；
  - 本轮 π₀.₅ 相关的两个仓在 hf-mirror 上**都不通**：
      * `lerobot/pi05_base` 的 blob 一度 429（D §1 实测），本轮恢复但单流仅 0.84 MB/s；
      * `google/paligemma-3b-pt-224` 是 **gated=manual**，hf-mirror **强制执行门控 ⇒ HTTP 403**
        （"Please enable access to public gated repositories in your fine-grained token settings"）；
  - ModelScope 侧两个仓都**可达且不设门**，实测 `lerobot/pi05_base` 单流 **26.2 MB/s**（hf-mirror 的 31×）。

沿用 `hf_mirror_fetch.py` 的纪律（D §8.1：**不能信返回码**）：
  远端清单 → 逐文件 size 校验 → sha256 校验 → 缺哪个补哪个 → 全对才 exit 0。
单实例锁同样保留：并发跑两个实例会让 `curl -C -` 对同一文件重复追加，把文件撑大。

用法：
  python scripts/a2_modelscope_fetch.py <repo_id> <local_dir> [--only 'tokenizer*'] [--jobs 3]
退出码：0 = 清单内全部文件 size+sha256 双对；2 = 有缺失/不符；3 = 已有实例在跑。
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

API = "https://www.modelscope.cn/api/v1/models/{repo}/repo/files?Recursive=true"
RESOLVE = "https://www.modelscope.cn/api/v1/models/{repo}/repo?Revision=master&FilePath={path}"


def fetch_manifest(repo: str, timeout: int = 180) -> list[dict]:
    req = urllib.request.Request(API.format(repo=repo), headers={"User-Agent": "curl/8"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        d = json.loads(resp.read().decode("utf-8"))
    if d.get("Code") != 200 or not d.get("Success"):
        raise RuntimeError(f"ModelScope 清单请求失败：Code={d.get('Code')} Message={str(d.get('Message'))[:200]}")
    files = [f for f in (d.get("Data") or {}).get("Files") or [] if f.get("Type") == "blob"]
    if not files:
        raise RuntimeError("ModelScope 清单为空（仓不存在或全是目录）")
    return files


def match_any(path: str, pats) -> bool:
    if not pats:
        return True
    name = pathlib.PurePosixPath(path).name
    return any(fnmatch.fnmatch(path, p) or fnmatch.fnmatch(name, p) for p in pats)


def sha256_of(p: pathlib.Path, chunk: int = 1 << 22) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def download_one(item: dict) -> dict:
    item["local"].parent.mkdir(parents=True, exist_ok=True)
    cmd = ["curl", "-sL", "--retry", "6", "--retry-delay", "4", "--retry-all-errors",
           "--max-time", "7200", "-C", "-", "-o", str(item["local"]), item["url"]]
    if os.environ.get("http_proxy"):
        cmd[1:1] = ["-x", os.environ["http_proxy"]]
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    dt = time.perf_counter() - t0
    got = item["local"].stat().st_size if item["local"].is_file() else -1
    return {"path": item["path"], "curl_rc": proc.returncode, "wall_s": round(dt, 1),
            "got_size": got, "want_size": item["size"],
            "rate_MBps": round(got / 1e6 / dt, 2) if dt > 0 and got > 0 else None,
            "stderr": proc.stderr.strip()[:200]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo_id")
    ap.add_argument("local_dir")
    ap.add_argument("--only", action="append", default=[], help="glob，可重复；默认取全部 blob")
    ap.add_argument("--exclude", action="append", default=[], help="glob，可重复")
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--skip-hash", action="store_true")
    ap.add_argument("--report", default="", help="把过程写成 JSON（速率/耗时/rc 都留档）")
    args = ap.parse_args()

    dest = pathlib.Path(args.local_dir).resolve()
    dest.mkdir(parents=True, exist_ok=True)

    lock_fh = open(dest / ".a2_modelscope_fetch.lock", "w")
    try:
        import fcntl
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(f"[abort] 已有实例在下载 {dest}，不并发跑（会损坏 -C - 续传）", flush=True)
        return 3

    print(f"== 1/3 取 ModelScope 清单 {args.repo_id} ==", flush=True)
    manifest = fetch_manifest(args.repo_id)
    # `match_any(x, [])` 的约定是"无过滤=全匹配"，所以 exclude 为空时**不能**取反，
    # 否则会把全部文件排掉 —— 然后"完整 0/0"照样 exit 0，正是本工具要防的静默假过。
    # 本轮第一次跑就中过：--only 给了 6 个 glob，结果"本次要 0 个"。
    want = [f for f in manifest
            if match_any(f["Path"], args.only)
            and not (args.exclude and match_any(f["Path"], args.exclude))
            and f["Path"] != ".a2_modelscope_fetch.lock"]
    if not want:
        print(f"[abort] 清单有 {len(manifest)} 个 blob，但 --only/--exclude 过滤后为 0 个。"
              f"这几乎一定是过滤条件写错，不许当成『没东西要下』而 exit 0。\n"
              f"        远端前 20 个路径：{[f['Path'] for f in manifest[:20]]}", flush=True)
        return 4
    print(f"   远端 blob 共 {len(manifest)}，本次要 {len(want)} 个，"
          f"合计 {sum(int(f.get('Size') or 0) for f in want)/1e6:.2f} MB", flush=True)

    todo, skipped = [], []
    for f in want:
        rel, size = f["Path"], int(f.get("Size") or 0)
        local = dest / rel
        if local.is_file() and (size == 0 or local.stat().st_size == size):
            skipped.append(rel)
            continue
        todo.append({"path": rel, "size": size, "local": local,
                     "sha256_expected": f.get("Sha256") or None,
                     "url": RESOLVE.format(repo=args.repo_id, path=urllib.parse.quote(rel))})
    print(f"== 2/3 本地已齐 {len(skipped)}，待下 {len(todo)}，并发 {args.jobs}，可续传 ==", flush=True)

    t0 = time.perf_counter()
    results = []
    if todo:
        total = sum(t["size"] for t in todo)
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            for i, r in enumerate(pool.map(download_one, todo), 1):
                results.append(r)
                flag = "ok " if r["got_size"] == r["want_size"] and r["curl_rc"] == 0 else "FAIL"
                print(f"   [{i}/{len(todo)}] {flag} {r['path']} got={r['got_size']:,} "
                      f"want={r['want_size']:,} {r['rate_MBps']} MB/s rc={r['curl_rc']}", flush=True)
        wall = time.perf_counter() - t0
        got_bytes = sum(r["got_size"] for r in results if r["got_size"] > 0)
        print(f"   下载 {got_bytes/1e6:.2f} MB / {wall:.1f} s = {got_bytes/1e6/wall:.2f} MB/s（聚合）", flush=True)
    else:
        wall = 0.0

    print("== 3/3 校验（size + sha256，不信返回码）==", flush=True)
    rows, miss, bad_size, bad_hash = [], [], [], []
    for f in want:
        rel, size = f["Path"], int(f.get("Size") or 0)
        local = dest / rel
        row = {"path": rel, "want_size": size, "want_sha256": f.get("Sha256") or None,
               "revision": f.get("Revision"), "is_lfs": f.get("IsLFS")}
        if not local.is_file():
            miss.append(rel); row["present"] = False; rows.append(row); continue
        row["present"] = True
        row["actual_size"] = local.stat().st_size
        if size and row["actual_size"] != size:
            bad_size.append((rel, row["actual_size"], size))
        if not args.skip_hash and f.get("Sha256"):
            t = time.perf_counter()
            row["actual_sha256"] = sha256_of(local)
            row["sha256_seconds"] = round(time.perf_counter() - t, 1)
            row["sha256_ok"] = row["actual_sha256"] == f["Sha256"]
            if not row["sha256_ok"]:
                bad_hash.append(rel)
        rows.append(row)
        print(f"   {'OK  ' if row.get('sha256_ok', True) and row['present'] else 'BAD '} {rel:34s} "
              f"{row.get('actual_size',0):>14,} sha256_ok={row.get('sha256_ok')}", flush=True)

    ok = not miss and not bad_size and not bad_hash
    print(f"\n完整 {len(want)-len(miss)-len(bad_size)-len(bad_hash)}/{len(want)}  "
          f"缺失 {len(miss)}  尺寸不符 {len(bad_size)}  sha256 不符 {len(bad_hash)}", flush=True)
    for p in miss[:10]: print("  MISS", p, flush=True)
    for p, g, w in bad_size[:10]: print(f"  BAD-SIZE {p} got={g} want={w}", flush=True)
    for p in bad_hash[:10]: print("  BAD-SHA256", p, flush=True)

    if args.report:
        rp = pathlib.Path(args.report)
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(json.dumps({
            "tool": "scripts/a2_modelscope_fetch.py", "repo_id": args.repo_id, "local_dir": str(dest),
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "args": vars(args), "manifest_blob_count": len(manifest), "selected": len(want),
            "already_present": skipped, "downloads": results,
            "download_wall_s": round(wall, 1),
            "aggregate_rate_MBps": round(sum(r["got_size"] for r in results)/1e6/wall, 2) if wall > 0 else None,
            "files": rows, "missing": miss, "bad_size": bad_size, "bad_sha256": bad_hash,
            "loadavg": list(os.getloadavg()), "PASS": ok,
        }, ensure_ascii=False, indent=1, default=str))
        print(f"[written] {rp}", flush=True)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
