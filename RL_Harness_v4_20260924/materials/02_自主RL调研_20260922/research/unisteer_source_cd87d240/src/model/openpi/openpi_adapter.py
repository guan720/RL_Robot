from __future__ import annotations

from typing import Any

from src.model.openpi.openpi_common import resolve_openpi_policy_type
from src.model.openpi.pi0_original import Pi0OriginalAdapter
from src.model.openpi.pi05_original import Pi05OriginalAdapter

OpenPiAdapter = Pi0OriginalAdapter | Pi05OriginalAdapter


def build_openpi_adapter(
    cfg: Any, *, dataset_statistics: dict[str, Any], device: str
) -> OpenPiAdapter:
    policy_type = resolve_openpi_policy_type(cfg)
    if policy_type == "pi0":
        return Pi0OriginalAdapter(cfg, dataset_statistics=dataset_statistics, device=device)
    if policy_type == "pi05":
        return Pi05OriginalAdapter(cfg, dataset_statistics=dataset_statistics, device=device)
    raise ValueError(f"Unsupported openpi_policy_type={policy_type!r}")
