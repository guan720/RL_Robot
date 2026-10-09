#!/usr/bin/env python3
"""加载官方 LeRobot ACT checkpoint 的公共入口（绕过 lerobot 0.4.4 的一个 config 解析 bug）。

为什么不用 `ACTConfig.from_pretrained(dir)`：
lerobot 0.4.4 的 `PreTrainedConfig.from_pretrained`（`configs/policies.py`）在
`config.pop("type")` **之前**就先执行了一次 `draccus.parse(cls, config_file, args=[])`，
而它自己保存的 `config.json` 里带着 `"type": "act"`，于是解析必然抛
`DecodingError: The fields `type` are not valid for ACTConfig`。也就是说官方 checkpoint
用官方 API 直接加载会失败。这里复刻它 pop 之后的那半段逻辑：读 config.json -> 去掉
type -> 写临时文件 -> draccus 解析成 ACTConfig，再把 config 显式传给
`ACTPolicy.from_pretrained(..., config=cfg)`，权重仍由官方代码从 model.safetensors 加载。

processor 管线（normalizer / unnormalizer 及其 stats）走官方
`make_pre_post_processors(cfg, pretrained_path=...)`，stats 来自 checkpoint 自带的
`policy_preprocessor_step_*_normalizer_processor.safetensors`，不重新统计数据集。
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

CHECKPOINT_FILE = "model.safetensors"


def sha256_file(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def resolve_pretrained_dir(ckpt: str | Path) -> Path:
    """允许传 run 目录 / checkpoints/<step> / pretrained_model，自动往下找 model.safetensors。"""
    ckpt = Path(ckpt)
    for cand in (ckpt, ckpt / "pretrained_model", ckpt / "checkpoints" / "last" / "pretrained_model"):
        if (cand / CHECKPOINT_FILE).exists():
            return cand
    found = sorted(ckpt.glob("checkpoints/*/pretrained_model/" + CHECKPOINT_FILE))
    if found:
        return found[-1].parent
    raise SystemExit(f"[错误] 在 {ckpt} 下找不到 {CHECKPOINT_FILE}")


def load_act_config(pm_dir: Path):
    import draccus
    from lerobot.policies.act.configuration_act import ACTConfig

    raw = json.loads((pm_dir / "config.json").read_text())
    raw.pop("type", None)
    with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as handle:
        json.dump(raw, handle)
        tmp = handle.name
    with draccus.config_type("json"):
        return draccus.parse(ACTConfig, tmp, args=[])


def load_official_act(ckpt: str | Path, device: str | None = None):
    """返回 (torch, cfg, policy, preprocessor, postprocessor, pretrained_model_dir)。"""
    import torch
    from lerobot.policies.act.modeling_act import ACTPolicy
    from lerobot.policies.factory import make_pre_post_processors

    pm_dir = resolve_pretrained_dir(ckpt)
    cfg = load_act_config(pm_dir)
    if device:
        cfg.device = device
    policy = ACTPolicy.from_pretrained(pm_dir, config=cfg)
    if device:
        policy = policy.to(device)
    policy.eval()
    pre, post = make_pre_post_processors(cfg, pretrained_path=str(pm_dir))
    return torch, cfg, policy, pre, post, pm_dir
