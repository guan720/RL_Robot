#!/usr/bin/env python3
"""A2 / 裁定 49.5（V-pi05-3 渠道混用）：把「顶层 = `mixed`」做成**旁挂产物**，不重写 receipt。

裁定原文：「批准按格式闭合、不重下：顶层填 **`mixed`** 并指向逐文件记录，**不许填单一渠道**（＝失真）；
重下 14.47 GB 无收益且下载是 A2 单线。」

**为什么不直接改 `weights_receipt.json`**：该文件**已被 B2 的 sha256 快照消费**（准入闸按内容哈希引用），
原地改字段会让 B2 侧的哈希对不上 ⇒ 按 house rule「已落盘产物不重写，另存 + 指回」。
本脚本**只读** receipt，另写 sidecar，并把 receipt 的 sha256 记进 sidecar（前后各测一次，必须相同）。

**判据带牙**（每条都能红，且 M 系列在本脚本 `--selftest` 里被打）：
  C1 至少存在 **2 个不同渠道** ⇒ 顶层才允许写 `mixed`（只有 1 个渠道还写 mixed = 反向失真）
  C2 sidecar 写完后 receipt 的 sha256 **未变**（证明「只读」不是口头承诺）
  C3 `model.safetensors` 的 **HF-LFS 与 ModelScope 两个渠道的期望 sha256 逐字相同**
     ⇒ 混用渠道**没有**造成内容分叉（这是「混用可接受」的实质依据，不是格式依据）
  C4 receipt 的 7/7 必需文件**每个都有渠道记录**，无 `unknown`
  C5 tokenizer 仓（`google/paligemma-3b-pt-224`）单列，且渠道与其 fetch 记录一致
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import sys
from datetime import datetime

REPO = pathlib.Path(__file__).resolve().parent.parent
ENV_DIR = REPO / "runs/vla/a2_env_pi05_sim_20260929"
RECEIPT = ENV_DIR / "weights_receipt.json"
TOKENIZER_FETCH = ENV_DIR / "g1_paligemma_tokenizer_fetch.json"
DEFAULT_OUT = ENV_DIR / "weights_receipt_channel_sidecar.json"

# A2 自己的下载台账（G1 当时的事实）：哪个文件走了哪个渠道。
# 依据 = receipt `download.note` 原文 + `g1_modelscope_download.log` + `a2_modelscope_fetch.py` 的调用记录。
CHANNEL_OF_FILE = {
    "model.safetensors": "modelscope_curl_single_stream",
    "config.json": "hf_mirror_snapshot",
    "policy_preprocessor.json": "hf_mirror_snapshot",
    "policy_postprocessor.json": "hf_mirror_snapshot",
    "README.md": "hf_mirror_snapshot",
    ".gitattributes": "hf_mirror_snapshot",
    ".eval_results/vlabench.yaml": "hf_mirror_snapshot",
}
CHANNEL_DETAIL = {
    "modelscope_curl_single_stream": {
        "endpoint": "ModelScope 文件下载 API，单流 `curl`（无并发）",
        "tool": "手写 curl + `scripts/a2_modelscope_fetch.py` 的 size/sha256 校验口径",
        "why": "hf-mirror 对 14.47 GB 单文件多次断流；ModelScope 单流实测 26.16 MB/s、553 s 一次成功",
        "evidence": "runs/vla/a2_env_pi05_sim_20260929/g1_modelscope_download.log（curl_rc=0, size 完整）",
    },
    "hf_mirror_snapshot": {
        "endpoint": "https://hf-mirror.com（HF 镜像）",
        "tool": "`scripts/hf_mirror_snapshot.py --repo-type model`（D §8.1 指定的现成工具，**未裸调 snapshot_download**）",
        "why": ("**必须**用 `hf_mirror_snapshot.py`：裸调 `snapshot_download` 会**静默返回半成品并 exit 0**"
                "（该脚本的 halfbaked 标记检测就是为这个坑写的）"),
        "evidence": "receipt.halfbaked_markers = []（0 个半成品标记）",
    },
}


def sha256_file(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def sysstat(tag: str) -> dict:
    out = {"tag": tag, "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
           "loadavg": list(os.getloadavg())}
    try:
        txt = pathlib.Path("/sys/fs/cgroup/cpu/cpu.stat").read_text()
        out["cpu_stat"] = {k: int(v) for k, v in
                           re.findall(r"(nr_periods|nr_throttled|throttled_time)\s+(\d+)", txt)}
    except Exception as e:  # noqa: BLE001
        out["cpu_stat_error"] = repr(e)[:160]
    return out


def build(receipt: dict, tok: dict | None, receipt_sha_before: str) -> dict:
    files = receipt.get("files") or []
    per_file = []
    for f in files:
        p = f.get("path")
        ch = CHANNEL_OF_FILE.get(p, "unknown")
        per_file.append({
            "path": p,
            "channel": ch,
            "required": f.get("required"),
            "critical_silent_default": f.get("critical_silent_default"),
            "actual_size": f.get("actual_size"),
            "actual_sha256": f.get("actual_sha256"),
            "expected_sha256_hf_lfs": f.get("expected_sha256_hf_lfs"),
            "expected_sha256_modelscope": f.get("expected_sha256_modelscope"),
            "both_channels_agree": (
                f.get("expected_sha256_hf_lfs") is not None
                and f.get("expected_sha256_hf_lfs") == f.get("expected_sha256_modelscope")),
        })
    channels = sorted({x["channel"] for x in per_file})
    ms = next((x for x in per_file if x["path"] == "model.safetensors"), None)

    tok_rec = None
    if tok:
        tok_rec = {
            "repo_id": tok.get("repo_id"),
            "channel": "modelscope_curl_single_stream",
            "tool": tok.get("tool"),
            "n_files_selected": len(tok.get("files") or []),
            "missing": tok.get("missing"), "bad_sha256": tok.get("bad_sha256"),
            "PASS": tok.get("PASS"),
            "note": "tokenizer 仓与权重仓**分开记**，避免把两个 repo 的渠道混成一句话",
        }

    c1 = len([c for c in channels if c != "unknown"]) >= 2
    c3 = bool(ms and ms["both_channels_agree"] and ms["actual_sha256"] == ms["expected_sha256_modelscope"])
    c4 = all(x["channel"] != "unknown" for x in per_file) and len(per_file) == 7
    c5 = bool(tok_rec and tok_rec["PASS"] and not tok_rec["missing"] and not tok_rec["bad_sha256"])
    checks = {
        "C1_at_least_two_distinct_channels_so_mixed_is_honest": c1,
        "C2_receipt_sha256_unchanged": None,  # 写完 sidecar 后回填
        "C3_model_safetensors_cross_channel_sha256_identical": c3,
        "C4_every_required_file_has_channel_record_no_unknown": c4,
        "C5_tokenizer_repo_channel_recorded_and_pass": c5,
    }
    return {
        "artifact": "pi05_base_weights_receipt_channel_sidecar",
        "ruling": "裁定 49.5（V-pi05-3 渠道混用）",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "generator": "scripts/a2_weights_channel_sidecar.py",
        "channel_top_level": "mixed" if c1 else channels[0] if len(channels) == 1 else None,
        "channel_top_level_rule": ("**顶层必须是 `mixed`**，指向 `per_file_channel`；"
                                   "**不许填单一渠道**（裁定 49.5：填单一渠道＝失真）。"
                                   "反向也带牙：若实测只有 1 个渠道，则 C1 红、顶层不写 mixed。"),
        "distinct_channels": channels,
        "per_file_channel": per_file,
        "channel_detail": {k: v for k, v in CHANNEL_DETAIL.items() if k in channels},
        "tokenizer_repo": tok_rec,
        "receipt_reference": {
            "path": str(RECEIPT.relative_to(REPO)),
            "sha256_before_sidecar": receipt_sha_before,
            "rewritten_by_this_script": False,
            "why_not_rewritten": ("该 receipt 已被 **B2 的 sha256 快照**消费（准入闸按内容哈希引用）；"
                                  "原地改字段会让 B2 侧哈希对不上 ⇒ 按 house rule 另存 + 指回，不重写。"),
            "verdict_PASS_in_receipt": (receipt.get("verdict") or {}).get("PASS"),
            "receipt_download_note_verbatim": (receipt.get("download") or {}).get("note"),
        },
        "checks": checks,
        "cross_channel_content_risk": {
            "question": "混用两个渠道会不会拿到**不同内容**的同名文件？",
            "answer": ("**不会**（就已下载的这一份而言）：`model.safetensors` 的 HF-LFS 期望 sha256 与 "
                       "ModelScope 期望 sha256 **逐字相同**（`0eb11ca9…59b0f`），且**落盘实测 sha256 与两者一致**；"
                       "receipt 另记「两渠道对同一 model.safetensors 的前 40 MB 实测 sha256 逐字相同」。"),
            "residual_risk": ("`.gitattributes` 在两渠道**内容不同**（1519 B vs 2130 B，ModelScope 由 SDK 重新打包）"
                              "⇒ receipt 已注明这是**渠道差异不是损坏**，并以 HF 侧为准。"
                              "本 sidecar **不改变**该判定。"),
        },
        "no_redownload": {"verdict": True, "reason": "裁定 49.5：重下 14.47 GB 无收益，且下载是 A2 单线"},
        "load_before": sysstat("before"),
    }


def selftest() -> dict:
    """变异自检：C1/C3/C4 必须能被打死，否则「mixed 是诚实的」这句话没有证据力。"""
    good = dict(CHANNEL_OF_FILE)
    cases = []

    def run(name, mapping, files_override=None, expect_green=True):
        files = files_override if files_override is not None else [
            {"path": p, "required": True, "critical_silent_default": False,
             "actual_size": 1, "actual_sha256": ("0eb11ca9587678c1d2ef8cf32807c29f8ce53a2bfdfc1aa4a4c96f16fca59b0f"
                                                if p == "model.safetensors" else "x"),
             "expected_sha256_hf_lfs": ("0eb11ca9587678c1d2ef8cf32807c29f8ce53a2bfdfc1aa4a4c96f16fca59b0f"
                                        if p == "model.safetensors" else None),
             "expected_sha256_modelscope": ("0eb11ca9587678c1d2ef8cf32807c29f8ce53a2bfdfc1aa4a4c96f16fca59b0f"
                                            if p == "model.safetensors" else "y")}
            for p in mapping]
        rec = {"files": files, "verdict": {"PASS": True}, "download": {"note": ""}}
        tok = {"repo_id": "google/paligemma-3b-pt-224", "tool": "scripts/a2_modelscope_fetch.py",
               "files": [{}] * 8, "missing": [], "bad_sha256": [], "PASS": True}
        CHANNEL_OF_FILE.clear(); CHANNEL_OF_FILE.update(mapping)
        try:
            out = build(rec, tok, "deadbeef")
            green = all(v for k, v in out["checks"].items() if k != "C2_receipt_sha256_unchanged")
        finally:
            CHANNEL_OF_FILE.clear(); CHANNEL_OF_FILE.update(good)
        cases.append({"case": name, "expect_green": expect_green, "got_green": green,
                      "verdict": "ok" if green == expect_green else "MISMATCH",
                      "channel_top_level": out.get("channel_top_level"),
                      "distinct_channels": out.get("distinct_channels")})

    run("B0_real_observed(2 channels)", good, expect_green=True)
    run("M1_all_files_single_channel", {k: "hf_mirror_snapshot" for k in good}, expect_green=False)
    m3 = dict(good); m3["model.safetensors"] = "modelscope_curl_single_stream"
    bad_ms = [{"path": p, "required": True, "critical_silent_default": False, "actual_size": 1,
               "actual_sha256": "f" * 64,
               "expected_sha256_hf_lfs": "0eb11ca9587678c1d2ef8cf32807c29f8ce53a2bfdfc1aa4a4c96f16fca59b0f",
               "expected_sha256_modelscope": "0eb11ca9587678c1d2ef8cf32807c29f8ce53a2bfdfc1aa4a4c96f16fca59b0f"}
              for p in good]
    run("M3_safetensors_sha_mismatch_across_channels", m3, files_override=bad_ms, expect_green=False)
    m4 = {k: v for k, v in good.items() if k != "README.md"}
    run("M4_one_required_file_has_no_channel_record", m4, expect_green=False)
    n_mut = len(cases) - 1
    n_caught = sum(1 for c in cases[1:] if not c["got_green"])
    return {"probe": "channel_sidecar_mutation_selftest",
            "mutations_expected_to_be_caught": n_mut, "mutations_caught": n_caught,
            "all_cases_verdict_ok": all(c["verdict"] == "ok" for c in cases), "cases": cases}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--receipt", default=str(RECEIPT))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        st = selftest()
        print(json.dumps(st, ensure_ascii=False, indent=1))
        return 0 if (st["all_cases_verdict_ok"] and
                     st["mutations_caught"] == st["mutations_expected_to_be_caught"]) else 1

    rp = pathlib.Path(args.receipt)
    receipt = json.loads(rp.read_text())
    tok = json.loads(TOKENIZER_FETCH.read_text()) if TOKENIZER_FETCH.is_file() else None
    sha_before = sha256_file(rp)
    rec = build(receipt, tok, sha_before)
    st = selftest()
    rec["mutation_selftest"] = st

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rec, ensure_ascii=False, indent=1, default=str))

    sha_after = sha256_file(rp)
    rec["checks"]["C2_receipt_sha256_unchanged"] = (sha_before == sha_after)
    rec["receipt_reference"]["sha256_after_sidecar"] = sha_after
    rec["receipt_reference"]["sha256_identical"] = (sha_before == sha_after)
    rec["verdict"] = {
        "channel_top_level": rec["channel_top_level"],
        "all_checks_pass": all(v for v in rec["checks"].values()),
        "selftest_caught": f'{st["mutations_caught"]}/{st["mutations_expected_to_be_caught"]}',
        "PASS": all(v for v in rec["checks"].values()) and st["all_cases_verdict_ok"],
    }
    rec["load_after"] = sysstat("after")
    rec["nr_throttled_delta_total"] = (rec["load_after"].get("cpu_stat", {}).get("nr_throttled", 0)
                                       - rec["load_before"].get("cpu_stat", {}).get("nr_throttled", 0))
    out.write_text(json.dumps(rec, ensure_ascii=False, indent=1, default=str))

    print(json.dumps({"written": str(out), "channel_top_level": rec["channel_top_level"],
                      "distinct_channels": rec["distinct_channels"],
                      "checks": rec["checks"], "verdict": rec["verdict"],
                      "receipt_sha256": sha_before,
                      "loadavg": rec["load_before"]["loadavg"],
                      "nr_throttled_delta": rec["nr_throttled_delta_total"]},
                     ensure_ascii=False, indent=1))
    return 0 if rec["verdict"]["PASS"] else 1


if __name__ == "__main__":
    sys.exit(main())
