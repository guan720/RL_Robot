#!/usr/bin/env python3
"""A2 / G2 前置 —— **逐张量**验证 π₀.₅ 权重是否真的进了模型（不许用"加载成功"当证据）。

背景（本轮实测到的坑）：`PI05Policy.from_pretrained` 会打印
  `Warning: Could not remap state dict keys: Error(s) in loading state_dict for PI05Policy:
   Missing key(s) in state_dict: "model.paligemma_with_expert.paligemma.model.language_model.embed_tokens.weight"`
而 `modeling_pi05.py:1021` 是 `model.load_state_dict(remapped_state_dict, strict=strict)`（strict 默认 True）
⇒ 抛 RuntimeError ⇒ 被 `modeling_pi05.py:1046` 的**裸 except** 吞掉 ⇒ 只打一行 warning 就 `return model`。
**这种形态最危险**：看起来加载完了，实际可能有一张量是随机初始化。

本脚本做的三件事：
 1. 读 `model.safetensors` 的 header，取出 `__metadata__`（safetensors 的**共享张量/tied weights** 记录）；
 2. 复刻 `from_pretrained` 的 key 修复 + `model.` 前缀重映射，然后**逐张量 bitwise 比对**
    内存里的模型参数 vs 文件里的张量（`torch.equal`），统计 exact / differ / unaccounted；
 3. 单独验 tied 那一条：`embed_tokens.weight` 与 `lm_head.weight` 是否**同一块存储**（data_ptr），
    且其数值是否 bitwise 等于文件里存的那个孪生张量。

结论只能是三种之一，写进 JSON：`all_bitwise_equal` / `partial_mismatch` / `not_loaded`。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import struct
import sys
import time
from datetime import datetime

import os
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


def load_snapshot():
    la = os.getloadavg()
    stat = {}
    for cand in ("/sys/fs/cgroup/cpu.stat", "/sys/fs/cgroup/cpu/cpu.stat"):
        try:
            for line in pathlib.Path(cand).read_text().splitlines():
                p = line.split()
                if len(p) == 2 and p[1].lstrip("-").isdigit():
                    stat[p[0]] = int(p[1])
            break
        except Exception:
            continue
    return {"loadavg_1m": round(la[0], 2), "loadavg_5m": round(la[1], 2),
            "cpu_stat": stat, "ts": datetime.now().astimezone().isoformat(timespec="seconds")}


def rss_gib() -> float:
    """本进程 RSS（GiB），用来盯内存水位（本节点 cgroup limit 225 GiB）。"""
    try:
        pages = int(pathlib.Path("/proc/self/statm").read_text().split()[1])
        return pages * os.sysconf("SC_PAGE_SIZE") / 2**30
    except Exception:
        return -1.0


def safetensors_header(path):
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        return json.loads(f.read(n))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--max-report-diffs", type=int, default=20)
    args = ap.parse_args()

    import torch
    from lerobot.policies.pi05.modeling_pi05 import PI05Policy

    wdir = pathlib.Path(args.weights_dir)
    st_path = wdir / "model.safetensors"
    hdr = safetensors_header(st_path)
    meta = {k: v for k, v in hdr.items() if k == "__metadata__"}.get("__metadata__", {})
    file_keys = [k for k in hdr if k != "__metadata__"]

    rep = {"probe": "a2_verify_pi05_load", "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
           "generator": "scripts/a2_verify_pi05_load.py", "args": vars(args),
           "morphology": "aloha_bimanual_14d",
           "load_before": load_snapshot(),
           "safetensors": {"path": str(st_path), "bytes": st_path.stat().st_size,
                           "n_tensors_in_file": len(file_keys),
                           "tied_weight_metadata": meta,
                           "metadata_meaning": ("safetensors 把**共享存储(tied)**的张量只存一份，"
                                                "别名关系记在 __metadata__ 里：{被省略的键: 实际存下来的键}")},
           "versions": {}}
    import importlib.metadata as md
    for m in ("torch", "transformers", "lerobot", "safetensors"):
        try:
            rep["versions"][m] = md.version(m)
        except Exception:
            rep["versions"][m] = None
    rep["versions"]["torch.__version__"] = torch.__version__

    t0 = time.perf_counter()
    policy = PI05Policy.from_pretrained(str(wdir))
    rep["from_pretrained_s"] = round(time.perf_counter() - t0, 2)
    policy = policy.to(args.device).eval()
    if args.device.startswith("cuda") and torch.cuda.is_available():
        torch.cuda.synchronize()
        rep["gpu"] = {"allocated_MiB": round(torch.cuda.memory_allocated() / 2**20, 1),
                      "max_allocated_MiB": round(torch.cuda.max_memory_allocated() / 2**20, 1),
                      "device": torch.cuda.get_device_name(0)}
    n_params = sum(p.numel() for p in policy.parameters())
    rep["n_parameters"] = n_params
    rep["n_parameters_billion"] = round(n_params / 1e9, 4)
    print(f"[load] {rep['from_pretrained_s']}s params={n_params/1e9:.4f}B", flush=True)

    # ---- 1) tied 那一条单独验（就是 warning 里点名的那个键）----
    tie_checks = []
    msd = dict(policy.state_dict())
    for alias, stored in meta.items():
        model_alias = alias if alias.startswith("model.") else f"model.{alias}"
        model_stored = stored if stored.startswith("model.") else f"model.{stored}"
        ent = {"alias_key_in_ckpt_metadata": alias, "stored_twin_key": stored,
               "alias_present_in_model": model_alias in msd,
               "twin_present_in_model": model_stored in msd}
        if model_alias in msd and model_stored in msd:
            a, b = msd[model_alias], msd[model_stored]
            ent["same_storage_data_ptr"] = bool(a.data_ptr() == b.data_ptr())
            ent["shape_alias"] = list(a.shape)
            ent["shape_twin"] = list(b.shape)
            if a.shape == b.shape:
                ent["bitwise_equal_in_model"] = bool(torch.equal(a.detach().cpu(), b.detach().cpu()))
        tie_checks.append(ent)
    rep["tied_weight_checks"] = tie_checks
    print(f"[tied] {json.dumps(tie_checks, ensure_ascii=False)[:500]}", flush=True)

    # ---- 2) 全量逐张量比对（**惰性**：一次只把一个张量读进内存）----
    # 不用 load_file() 整包读：本节点 cgroup 内存 limit=225 GiB、cache 已占 ~222 GiB，
    # 14.5 GB×2 的峰值会把后台任务挤死（本轮已实测到两次静默消失）。
    from safetensors import safe_open

    t0 = time.perf_counter()
    exact, differ, shape_mismatch, unaccounted = [], [], [], []
    diffs_reported = []
    covered = set()
    n_fixed_keys = 0
    with safe_open(str(st_path), framework="pt", device="cpu") as f:
        file_key_list = list(f.keys())
        for i, k in enumerate(file_key_list):
            t_file = f.get_tensor(k)
            fixed = policy._fix_pytorch_state_dict_keys({k: t_file}, policy.config)
            n_fixed_keys += len(fixed)
            for fk, fv in fixed.items():
                mk = fk if fk.startswith("model.") else f"model.{fk}"
                if mk not in msd:
                    unaccounted.append(fk)
                    continue
                vm_t = msd[mk]
                if tuple(vm_t.shape) != tuple(fv.shape):
                    shape_mismatch.append({"key": mk, "model": list(vm_t.shape), "file": list(fv.shape)})
                    covered.add(mk)
                    continue
                a = vm_t.detach().to("cpu", copy=True)
                if torch.equal(a, fv.detach().cpu()):
                    exact.append(mk)
                else:
                    d = float((a.float() - fv.detach().cpu().float()).abs().max())
                    differ.append({"key": mk, "max_abs_diff": d})
                    if len(diffs_reported) < args.max_report_diffs:
                        diffs_reported.append({"key": mk, "max_abs_diff": d})
                del a
                covered.add(mk)
            del t_file, fixed
            if (i + 1) % 100 == 0:
                print(f"[cmp] {i + 1}/{len(file_key_list)} exact={len(exact)} "
                      f"differ={len(differ)} rss_GiB={rss_gib():.2f}", flush=True)
    rep["remap"] = {"n_keys_in_file": len(file_key_list), "n_keys_after_fix": n_fixed_keys,
                    "s": round(time.perf_counter() - t0, 2)}

    # 模型里有、但 ckpt（含 tied 别名）没覆盖到的键 —— 这些才是真·随机初始化
    covered |= {(a if a.startswith("model.") else f"model.{a}") for a in meta.keys()}
    model_only = [k for k in msd if k not in covered]
    rep["compare"] = {
        "n_compared": len(exact) + len(differ) + len(shape_mismatch),
        "n_bitwise_exact": len(exact),
        "n_differ": len(differ),
        "n_shape_mismatch": len(shape_mismatch),
        "n_ckpt_keys_not_in_model": len(unaccounted),
        "ckpt_keys_not_in_model_sample": unaccounted[:20],
        "differ_sample": diffs_reported,
        "shape_mismatch_sample": shape_mismatch[:20],
        "n_model_keys_not_covered_by_ckpt": len(model_only),
        "model_keys_not_covered_sample": model_only[:30],
        "model_keys_not_covered_note": ("这些键在 ckpt 里找不到对应张量（也不是 tied 别名）⇒ **它们保持随机初始化**。"
                                        "若为空，说明权重是完整落进模型的。"),
    }
    ok = (len(differ) == 0 and len(shape_mismatch) == 0 and len(model_only) == 0
          and all(t.get("bitwise_equal_in_model", False) for t in tie_checks))
    rep["verdict"] = "all_bitwise_equal" if ok else ("partial_mismatch" if len(exact) > 0 else "not_loaded")
    rep["verdict_explanation"] = (
        "ckpt 的每个张量都在模型里找到对应参数且 **bitwise 相等**；warning 里点名的 "
        "embed_tokens.weight 是 safetensors 的 tied 别名（与 lm_head.weight 同一块存储），"
        "lerobot 0.4.4 的 from_pretrained 不展开 __metadata__ ⇒ strict=True 抛错被裸 except 吞掉，"
        "**但 PyTorch 在抛错前已经把匹配的张量拷进去了**，所以这是一条**良性告警**（已逐张量证明）。"
        if ok else
        "**权重没有完整落进模型**：存在 differ/shape_mismatch/未覆盖键，见 compare 字段。"
        "此状态下任何 zero-shot 数字都无意义，必须报 D。")
    rep["load_after"] = load_snapshot()

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1, default=str))
    print(f"[verdict] {rep['verdict']}  exact={rep['compare']['n_bitwise_exact']} "
          f"differ={rep['compare']['n_differ']} shape_mm={rep['compare']['n_shape_mismatch']} "
          f"model_keys_uncovered={rep['compare']['n_model_keys_not_covered_by_ckpt']}", flush=True)
    print(f"[written] {out}", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
