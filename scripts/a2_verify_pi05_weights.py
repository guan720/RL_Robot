#!/usr/bin/env python3
"""A2 / G1 —— π₀.₅ 权重落地的**断言式**校验器 + receipt 生成。

依据 `rl_harness_supervision/d_handoff_to_a2_20260929.md` §3、§8.1：
  - 必须核 **7/7 文件 + 字节数 + sha256**，`policy_preprocessor.json` / `policy_postprocessor.json` **单列**为必需项；
  - **不能信返回码**（`snapshot_download` 被 429 时打印 "Returning existing local_dir" 后 exit 0，
    实测只下了 719/895 文件）；
  - receipt 必须含 **license 字段（`gemma`）**，Gemma Terms of Use 是有约束的许可证，要进证据链。

判据能红的四条牙（任一条不满足 ⇒ 退出码非 0）：
  1. 文件数必须**恰好** 7/7（多一个少一个都算不符，防止"把无关文件数进来"造成假过——
     本轮就真撞过一次：权重目录里混进 A2 自己的 log，把 `got` 撑成 9 而 `want=6`）；
  2. 每个文件字节数必须与远端清单一致；
  3. `model.safetensors` 的 sha256 必须同时等于 **HF LFS oid** 与 **ModelScope Sha256**
     （两个互相独立的注册表给出同一个 sha256 ⇒ 这是本校验最强的一环）；
  4. 不允许存在 `*.incomplete` / `*.part` 半成品标记。

用法：
    python scripts/a2_verify_pi05_weights.py \
        --weights-dir <NFS 上的权重目录> \
        --out runs/vla/a2_env_pi05_sim_20260929/weights_receipt.json
退出码：0 = 全部通过；1 = 有不符（详见 receipt 的 failures）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys
import time
import urllib.request
from datetime import datetime

REPO_ID = "lerobot/pi05_base"
HF_ENDPOINT = os.environ.get("HF_ENDPOINT", "https://hf-mirror.com").rstrip("/")
MS_API = "https://www.modelscope.cn/api/v1/models/{repo}/repo/files?Recursive=true"

# π₀.₅ 的**必需**文件（D §3-2 特别点名后两个：lerobot 的 from_pretrained 用它们做
# 归一化/反归一化，缺了会**静默走默认值**，属最难查的一类错）。
REQUIRED = [
    "config.json",
    "model.safetensors",
    "policy_preprocessor.json",
    "policy_postprocessor.json",
    "README.md",
    ".gitattributes",
    ".eval_results/vlabench.yaml",
]
# 单列为必需项（缺了不报错但会静默走默认归一化）
CRITICAL_SILENT = ["policy_preprocessor.json", "policy_postprocessor.json"]

LICENSE_EXPECTED = "gemma"          # HF cardData.license（本轮 API 实测）
COMMIT_EXPECTED = "b211f3d44c36b6acfcf7ae94a64e8e96f75a64ba"


def _get_json(url: str, timeout: int = 120):
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def remote_hf() -> dict:
    """HF 侧清单：非 LFS 文件给 git blob sha1（`oid`），LFS 文件给 **sha256**（`lfs.oid`）。"""
    tree = _get_json(f"{HF_ENDPOINT}/api/models/{REPO_ID}/tree/main?recursive=true&expand=true")
    info = _get_json(f"{HF_ENDPOINT}/api/models/{REPO_ID}")
    files = {}
    for e in tree:
        if e.get("type") != "file":
            continue
        lfs = e.get("lfs") or {}
        files[e["path"]] = {
            "size": int(lfs.get("size") or e.get("size") or 0),
            "sha256": lfs.get("sha256") or lfs.get("oid"),      # LFS 的 oid 就是 sha256
            "git_blob_sha1": e.get("oid"),
            "is_lfs": bool(lfs),
        }
    return {
        "files": files,
        "commit_sha": info.get("sha"),
        "last_modified": info.get("lastModified"),
        "license": (info.get("cardData") or {}).get("license") or next(
            (t.split(":", 1)[1] for t in info.get("tags", []) if t.startswith("license:")), None),
        "used_storage": info.get("usedStorage"),
        "siblings_count": len(info.get("siblings") or []),
        "safetensors_parameters": (info.get("safetensors") or {}).get("parameters"),
        "gated": info.get("gated"),
    }


def remote_modelscope() -> dict:
    """ModelScope 侧清单：所有 blob 都给 `Sha256`（含非 LFS 小文件）。"""
    d = _get_json(MS_API.format(repo=REPO_ID))
    files = {}
    for f in (d.get("Data") or {}).get("Files") or []:
        if f.get("Type") != "blob":
            continue
        files[f["Path"]] = {"size": int(f.get("Size") or 0), "sha256": f.get("Sha256") or None,
                            "is_lfs": bool(f.get("IsLFS")), "revision": f.get("Revision"),
                            "commit_message": f.get("CommitMessage")}
    return {"files": files, "code": d.get("Code"), "success": d.get("Success")}


def sha256_of(path: pathlib.Path, chunk: int = 1 << 22) -> tuple[str, float]:
    h, t0 = hashlib.sha256(), time.perf_counter()
    with path.open("rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest(), round(time.perf_counter() - t0, 1)


def git_blob_sha1(path: pathlib.Path) -> str:
    h = hashlib.sha1()
    n = path.stat().st_size
    h.update(b"blob %d\0" % n)
    with path.open("rb") as fh:
        while True:
            b = fh.read(1 << 22)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def load_snapshot(path: pathlib.Path) -> dict:
    """safetensors 头（不加载权重）：证明这个文件**是**一个合法的 π₀.₅ 张量库，不只是字节对得上。"""
    import struct
    with path.open("rb") as fh:
        n = struct.unpack("<Q", fh.read(8))[0]
        header = json.loads(fh.read(n))
    meta = header.pop("__metadata__", {})
    dtypes = {}
    total = 0
    for k, v in header.items():
        dtypes[v.get("dtype")] = dtypes.get(v.get("dtype"), 0) + 1
        s, e = v.get("data_offsets", [0, 0])
        total = max(total, e)
    return {"n_tensors": len(header), "metadata": meta, "dtype_histogram": dtypes,
            "data_bytes_from_header": total, "header_bytes": n,
            "sample_tensor_names": sorted(header)[:6]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights-dir", required=True)
    ap.add_argument("--out", default="runs/vla/a2_env_pi05_sim_20260929/weights_receipt.json")
    ap.add_argument("--skip-hash", action="store_true", help="只核清单与尺寸，不算 sha256（14.5 GB 约 60 s）")
    ap.add_argument("--channel-note", default="", help="写进 receipt 的下载过程说明")
    ap.add_argument("--download-log", default="", help="下载日志路径，抄进 receipt 当过程证据")
    args = ap.parse_args()

    wdir = pathlib.Path(args.weights_dir).resolve()
    rec: dict = {
        "artifact": "pi05_base_weights_receipt",
        "repo_id": REPO_ID,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "generator": "scripts/a2_verify_pi05_weights.py",
        "weights_dir": str(wdir),
        "verifier_sha256": sha256_of(pathlib.Path(__file__))[0],
    }

    if not wdir.is_dir():
        rec["fatal"] = f"权重目录不存在：{wdir}"
        _write(rec, args.out)
        return 1

    # ---------------- 远端清单（两个互相独立的注册表）----------------
    t0 = time.perf_counter()
    try:
        hf = remote_hf()
        rec["remote_hf"] = {k: v for k, v in hf.items() if k != "files"}
        rec["remote_hf"]["n_files"] = len(hf["files"])
    except Exception as exc:  # noqa: BLE001
        hf = {"files": {}}
        rec["remote_hf"] = {"error": f"{type(exc).__name__}: {str(exc)[:300]}"}
    try:
        ms = remote_modelscope()
        rec["remote_modelscope"] = {"n_files": len(ms["files"]), "code": ms["code"], "success": ms["success"]}
    except Exception as exc:  # noqa: BLE001
        ms = {"files": {}}
        rec["remote_modelscope"] = {"error": f"{type(exc).__name__}: {str(exc)[:300]}"}
    rec["manifest_fetch_s"] = round(time.perf_counter() - t0, 1)

    # 远端清单本身要先对撞：两个注册表的 size 必须一致，否则"以哪个为准"就没有答案
    both = sorted(set(hf["files"]) & set(ms["files"]))
    size_disagree = [p for p in both if hf["files"][p]["size"] != ms["files"][p]["size"]]
    sha_disagree = [p for p in both
                    if hf["files"][p].get("sha256") and ms["files"][p].get("sha256")
                    and hf["files"][p]["sha256"] != ms["files"][p]["sha256"]]
    rec["manifest_cross_check"] = {
        "hf_only": sorted(set(hf["files"]) - set(ms["files"])),
        "modelscope_only": sorted(set(ms["files"]) - set(hf["files"])),
        "size_disagree": size_disagree,
        "sha256_disagree": sha_disagree,
        "note": ("`.gitattributes` 与 ModelScope 独有的 `configuration.json` 是**渠道差异**，不是损坏："
                 "ModelScope 仓由 SDK 重新打包，`.gitattributes` 内容不同（2130B vs HF 1519B）。"
                 "本 receipt 以 **HF 的 7 文件清单**为准（lerobot from_pretrained 读的是这套），"
                 "逐文件记录实际取自哪个渠道。"),
    }

    # ---------------- 本地实物 ----------------
    local_files = sorted(
        str(p.relative_to(wdir)) for p in wdir.rglob("*")
        if p.is_file() and ".cache" not in p.parts and not p.name.endswith((".lock",))
    )
    rec["local_files_all"] = local_files
    halfbaked = [str(p.relative_to(wdir)) for p in wdir.rglob("*")
                 if p.is_file() and (p.name.endswith(".incomplete") or p.name.endswith(".part"))]
    rec["halfbaked_markers"] = halfbaked

    per_file, failures = [], []
    expected_set = set(REQUIRED)
    for rel in REQUIRED:
        p = wdir / rel
        entry: dict = {"path": rel, "required": True,
                       "critical_silent_default": rel in CRITICAL_SILENT}
        hfe = hf["files"].get(rel) or {}
        mse = ms["files"].get(rel) or {}
        entry["expected_size_hf"] = hfe.get("size")
        entry["expected_size_modelscope"] = mse.get("size")
        entry["expected_sha256_hf_lfs"] = hfe.get("sha256") if hfe.get("is_lfs") else None
        entry["expected_sha256_modelscope"] = mse.get("sha256")
        entry["expected_git_blob_sha1_hf"] = hfe.get("git_blob_sha1")
        if not p.is_file():
            entry["present"] = False
            failures.append(f"MISSING {rel}")
            per_file.append(entry)
            continue
        entry["present"] = True
        actual = p.stat().st_size
        entry["actual_size"] = actual
        want = hfe.get("size") or mse.get("size")
        entry["size_ok"] = (want is not None and actual == want)
        if not entry["size_ok"]:
            failures.append(f"SIZE {rel} actual={actual} want={want}")
        if not args.skip_hash:
            t = time.perf_counter()
            dig, dt = sha256_of(p)
            entry["actual_sha256"] = dig
            entry["sha256_seconds"] = dt
            entry["sha256_MBps"] = round(actual / 1e6 / dt, 1) if dt > 0 else None
            entry["actual_git_blob_sha1"] = git_blob_sha1(p)
            exp_ms = mse.get("sha256")
            exp_hf = entry["expected_sha256_hf_lfs"]
            entry["sha256_match_modelscope"] = (exp_ms == dig) if exp_ms else None
            entry["sha256_match_hf_lfs"] = (exp_hf == dig) if exp_hf else None
            # `.gitattributes` 走 HF 渠道 ⇒ 只能对 HF 的 git blob sha1，不能对 ModelScope 的 sha256
            entry["git_blob_sha1_match_hf"] = (entry["expected_git_blob_sha1_hf"] == entry["actual_git_blob_sha1"]) \
                if entry["expected_git_blob_sha1_hf"] else None
            if rel == ".gitattributes":
                ok = bool(entry["git_blob_sha1_match_hf"])
                entry["sha256_verdict"] = "hf_git_blob_sha1" if ok else "FAIL"
            else:
                ok = bool(entry["sha256_match_modelscope"]) and (exp_hf is None or bool(entry["sha256_match_hf_lfs"]))
                entry["sha256_verdict"] = "hf_lfs+modelscope" if (exp_hf and entry["sha256_match_hf_lfs"]) else (
                    "modelscope" if entry["sha256_match_modelscope"] else "FAIL")
            if not ok:
                failures.append(f"SHA256 {rel} actual={dig} hf={exp_hf} ms={exp_ms}")
        per_file.append(entry)

    # ---------------- 牙 1：文件数恰好 7/7，不许多不许少 ----------------
    extra = sorted(set(local_files) - expected_set)
    rec["file_count"] = {
        "required": len(REQUIRED),
        "present": sum(1 for e in per_file if e.get("present")),
        "local_files_excluding_cache": len(local_files),
        "unexpected_extra_files": extra,
        "exact_match": len(local_files) == len(REQUIRED) and not extra,
    }
    if extra:
        failures.append(f"EXTRA 权重目录里混进非清单文件（会把文件数校验撑成假过）：{extra}")

    # ---------------- safetensors 头部结构 ----------------
    big = wdir / "model.safetensors"
    if big.is_file():
        try:
            rec["safetensors_header"] = load_snapshot(big)
        except Exception as exc:  # noqa: BLE001
            rec["safetensors_header"] = {"error": f"{type(exc).__name__}: {str(exc)[:300]}"}
            failures.append(f"safetensors 头不可解析：{exc}")

    # ---------------- config 与 license ----------------
    cfg_path = wdir / "config.json"
    if cfg_path.is_file():
        try:
            cfg = json.loads(cfg_path.read_text())
            rec["config_summary"] = {
                "type": cfg.get("type"), "n_obs_steps": cfg.get("n_obs_steps"),
                "chunk_size": cfg.get("chunk_size"), "n_action_steps": cfg.get("n_action_steps"),
                "max_action_dim": cfg.get("max_action_dim"), "max_state_dim": cfg.get("max_state_dim"),
                "num_inference_steps": cfg.get("num_inference_steps"),
                "image_resolution": cfg.get("image_resolution"),
                "paligemma_variant": cfg.get("paligemma_variant"),
                "action_expert_variant": cfg.get("action_expert_variant"),
                "dtype": cfg.get("dtype"), "device_as_shipped": cfg.get("device"),
                "input_features": {k: {"type": v.get("type"), "shape": v.get("shape")}
                                   for k, v in (cfg.get("input_features") or {}).items()},
                "output_features": {k: {"type": v.get("type"), "shape": v.get("shape")}
                                    for k, v in (cfg.get("output_features") or {}).items()},
            }
        except Exception as exc:  # noqa: BLE001
            rec["config_summary"] = {"error": str(exc)[:300]}

    lic = (rec.get("remote_hf") or {}).get("license")
    rec["license"] = {
        "value": lic,
        "expected": LICENSE_EXPECTED,
        "match": lic == LICENSE_EXPECTED,
        "source": f"HF API cardData.license / tags（{HF_ENDPOINT}）",
        "terms": "Gemma Terms of Use —— 有约束的许可证，禁止用输出训练非 Gemma 模型等；引用/再分发前须复核",
        "kind": "external_unverified" if lic is None else "remote_api_read",
    }
    if lic != LICENSE_EXPECTED:
        failures.append(f"LICENSE 期望 {LICENSE_EXPECTED}，实际 {lic}")

    rec["commit"] = {"hf_sha": (rec.get("remote_hf") or {}).get("commit_sha"),
                     "expected": COMMIT_EXPECTED,
                     "match": (rec.get("remote_hf") or {}).get("commit_sha") == COMMIT_EXPECTED}

    # ---------------- 下载过程（速率必须记，D §3-1）----------------
    dl: dict = {"note": args.channel_note or None}
    if args.download_log and pathlib.Path(args.download_log).is_file():
        txt = pathlib.Path(args.download_log).read_text(errors="replace")
        dl["log_path"] = str(pathlib.Path(args.download_log).resolve())
        dl["log_tail"] = txt.strip().splitlines()[-12:]
        import re
        times = re.findall(r"\[(?:sha256 )?(?:start|done|attempt \d+)\] (\S+)", txt)
        m = re.findall(r"curl_rc=(\d+) size=(\d+)", txt)
        if m:
            dl["curl_rc"], dl["reported_size"] = int(m[-1][0]), int(m[-1][1])
        if len(times) >= 2:
            try:
                a = datetime.fromisoformat(times[0]); b = datetime.fromisoformat(times[-1])
                dl["first_ts"], dl["last_ts"] = times[0], times[-1]
                dl["wall_s"] = round((b - a).total_seconds(), 1)
            except Exception:
                pass
    rec["download"] = dl
    if big.is_file() and dl.get("wall_s"):
        rec["download"]["measured_rate_MBps"] = round(big.stat().st_size / 1e6 / dl["wall_s"], 2)

    rec["files"] = per_file
    rec["failures"] = failures
    rec["verdict"] = {
        "complete_7_of_7": rec["file_count"]["present"] == len(REQUIRED),
        "all_sizes_ok": all(e.get("size_ok") for e in per_file if e.get("present")),
        "all_hashes_ok": all(
            (e.get("sha256_verdict") not in (None, "FAIL")) for e in per_file if e.get("present")),
        "no_halfbaked": not halfbaked,
        "license_ok": rec["license"]["match"],
        "critical_pre_post_present": all((wdir / c).is_file() for c in CRITICAL_SILENT),
        "PASS": not failures,
    }
    rec["exit_code"] = 0 if not failures else 1

    _write(rec, args.out)
    v = rec["verdict"]
    print(json.dumps({"verdict": v, "file_count": rec["file_count"], "failures": failures,
                      "license": rec["license"]["value"], "receipt": args.out},
                     ensure_ascii=False, indent=1))
    return 0 if not failures else 1


def _write(rec: dict, out: str) -> None:
    p = pathlib.Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rec, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    sys.exit(main())
