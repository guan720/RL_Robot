"""
UniSteer latent-noise RL training server.

The server owns a single training path:

- observations are `{"pixels", "state"}`
- RL action is the latent/noise action
- rewards/masks/discounts come from the rollout sidecars
"""

from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
import csv
from dataclasses import asdict, dataclass
import html
import io
import json
import math
from pathlib import Path
from statistics import mean
import sys
import threading
import time
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Sequence
from urllib.parse import urlparse

from flask import Flask, Response, request
from loguru import logger
import msgpack
import numpy as np
from PIL import Image
import requests
import torch

try:
    from omegaconf import OmegaConf, open_dict
except Exception:  # pragma: no cover
    OmegaConf = None

    @contextmanager
    def open_dict(cfg):
        yield cfg


from src.dataset.dataset import (
    load_traj_image_frame_chw_uint8,
    load_traj_proprio_action,
    resolve_traj_image_array_path,
)
from src.tool.binary_reward import (
    BINARY_REWARD_BACKEND,
    build_binary_reward_sequence,
    validate_binary_reward_sidecar,
)
from src.trainer import RLTrainer

if TYPE_CHECKING:
    from src.agent.inference_agent import InferenceAgent


def _json_default(obj: Any) -> Any:
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    if isinstance(obj, bytes):
        return base64.b64encode(obj).decode("utf-8")
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _json_response(payload: Dict[str, Any], status: int = 200) -> Response:
    return Response(
        response=json.dumps(payload, default=_json_default),
        status=status,
        mimetype="application/json",
    )


def _format_scalar_metrics(metrics: Mapping[str, Any]) -> str:
    parts: List[str] = []
    for key, value in metrics.items():
        if isinstance(value, bool):
            parts.append(f"{key}={value}")
        elif isinstance(value, (int, np.integer)):
            parts.append(f"{key}={int(value)}")
        elif isinstance(value, (float, np.floating)):
            parts.append(f"{key}={float(value):.6g}")
        elif isinstance(value, str):
            parts.append(f"{key}={value}")
    return " ".join(parts)


def _is_scalar_number(value: Any) -> bool:
    return isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, bool)


def _finite_float(value: Any) -> Optional[float]:
    if not _is_scalar_number(value):
        return None
    out = float(value)
    return out if math.isfinite(out) else None


def _format_plot_value(value: float) -> str:
    if abs(value) >= 1000.0 or (0.0 < abs(value) < 0.01):
        return f"{value:.2e}"
    if abs(value) >= 100.0:
        return f"{value:.0f}"
    if abs(value) >= 10.0:
        return f"{value:.1f}"
    return f"{value:.3g}"


def _metric_values(
    history: Sequence[Mapping[str, Any]], metric: str
) -> tuple[list[float], list[float]]:
    xs: list[float] = []
    ys: list[float] = []
    for row in history:
        y = _finite_float(row.get(metric))
        if y is None:
            continue
        x = _finite_float(row.get("step"))
        if x is None:
            x = _finite_float(row.get("round_update"))
        if x is None:
            continue
        xs.append(float(x))
        ys.append(float(y))
    return xs, ys


def _nice_metric_range(values: Sequence[float]) -> tuple[float, float]:
    low = float(min(values))
    high = float(max(values))
    if low == high:
        pad = abs(low) * 0.1 + 1.0
        return low - pad, high + pad
    pad = (high - low) * 0.08
    return low - pad, high + pad


def _linear_ticks(low: float, high: float, count: int = 4) -> list[float]:
    if count <= 1 or low == high:
        return [float(low)]
    return [float(low + (high - low) * idx / (count - 1)) for idx in range(count)]


def _polyline_points(
    xs: Sequence[float],
    ys: Sequence[float],
    *,
    x0: float,
    y0: float,
    width: float,
    height: float,
    xmin: float,
    xmax: float,
    ymin: float,
    ymax: float,
) -> str:
    points: list[str] = []
    for x, y in zip(xs, ys):
        px = x0 + width * 0.5 if xmax == xmin else x0 + (float(x) - xmin) / (xmax - xmin) * width
        py = (
            y0 + height * 0.5
            if ymax == ymin
            else y0 + height - (float(y) - ymin) / (ymax - ymin) * height
        )
        points.append(f"{px:.2f},{py:.2f}")
    return " ".join(points)


def _write_rl_metrics_artifacts(
    *, history: Sequence[Mapping[str, Any]], output_dir: Path, title: str
) -> Dict[str, str]:
    if not history:
        return {}
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics = sorted(
        key
        for key in {k for row in history for k in row}
        if any(_finite_float(row.get(key)) is not None for row in history)
    )
    ordered = ["round_update", "total_updates", "step", "wall_elapsed_sec"]
    fieldnames = [key for key in ordered if key in metrics]
    fieldnames.extend(key for key in metrics if key not in set(fieldnames))

    csv_path = output_dir / "metrics.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in history:
            writer.writerow({key: row.get(key, "") for key in fieldnames})

    summary_path = output_dir / "summary.txt"
    with summary_path.open("w", encoding="utf-8") as handle:
        handle.write(f"title: {title}\n")
        handle.write(f"num_points: {len(history)}\n")
        handle.write(f"first_step: {history[0].get('step', '')}\n")
        handle.write(f"last_step: {history[-1].get('step', '')}\n")
        handle.write("metrics:\n")
        for metric in fieldnames:
            if metric in {"round_update", "total_updates"}:
                continue
            _, values = _metric_values(history, metric)
            if values:
                handle.write(
                    f"  {metric}: min={min(values):.6g} mean={mean(values):.6g} "
                    f"max={max(values):.6g} final={values[-1]:.6g}\n"
                )

    plot_metrics = [
        key for key in fieldnames if key not in {"round_update", "total_updates", "step"}
    ]
    plot_metrics = [key for key in plot_metrics if _metric_values(history, key)[1]]
    svg_path = output_dir / "all_metrics.svg"
    if plot_metrics:
        colors = [
            "#1f77b4",
            "#ff7f0e",
            "#2ca02c",
            "#d62728",
            "#9467bd",
            "#8c564b",
            "#e377c2",
            "#7f7f7f",
            "#bcbd22",
            "#17becf",
        ]
        cols = 3
        subplot_w = 420
        subplot_h = 180
        margin_l = 76
        margin_r = 28
        margin_t = 74
        margin_b = 56
        gap_x = 34
        gap_y = 50
        rows = int(math.ceil(len(plot_metrics) / cols))
        width = margin_l + cols * subplot_w + (cols - 1) * gap_x + margin_r
        height = margin_t + rows * subplot_h + (rows - 1) * gap_y + margin_b
        x_values = [
            _finite_float(row.get("step"))
            if _finite_float(row.get("step")) is not None
            else _finite_float(row.get("round_update"))
            for row in history
        ]
        x_values = [float(v) for v in x_values if v is not None]
        xmin = min(x_values)
        xmax = max(x_values)
        svg: list[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            "<style>text{font-family:DejaVu Sans,Arial,sans-serif;} .small{font-size:10px;fill:#4b5563;} "
            ".axis{stroke:#9ca3af;stroke-width:1;} .grid{stroke:#e5e7eb;stroke-width:1;} "
            ".title{font-size:22px;font-weight:700;fill:#111827;} .metric{font-size:13px;font-weight:700;fill:#111827;} "
            ".label{font-size:12px;fill:#111827;}</style>",
            '<rect width="100%" height="100%" fill="#ffffff"/>',
            f'<text x="{margin_l}" y="34" class="title">{html.escape(title)}</text>',
            f'<text x="{margin_l}" y="55" class="small">points={len(history)}; x-axis uses trainer step.</text>',
        ]
        for idx, metric in enumerate(plot_metrics):
            row_idx = idx // cols
            col_idx = idx % cols
            x0 = margin_l + col_idx * (subplot_w + gap_x)
            y0 = margin_t + row_idx * (subplot_h + gap_y)
            xs, ys = _metric_values(history, metric)
            ymin, ymax = _nice_metric_range(ys)
            svg.append(
                f'<rect x="{x0}" y="{y0}" width="{subplot_w}" height="{subplot_h}" fill="#fafafa" stroke="#e5e7eb"/>'
            )
            for tick in _linear_ticks(ymin, ymax):
                gy = (
                    y0 + subplot_h * 0.5
                    if ymax == ymin
                    else y0 + subplot_h - (tick - ymin) / (ymax - ymin) * subplot_h
                )
                svg.append(
                    f'<line x1="{x0}" x2="{x0 + subplot_w}" y1="{gy:.2f}" y2="{gy:.2f}" class="grid"/>'
                )
                svg.append(
                    f'<text x="{x0 - 8}" y="{gy + 4:.2f}" text-anchor="end" class="small">{_format_plot_value(tick)}</text>'
                )
            for tick in _linear_ticks(xmin, xmax):
                gx = (
                    x0 + subplot_w * 0.5
                    if xmax == xmin
                    else x0 + (tick - xmin) / (xmax - xmin) * subplot_w
                )
                svg.append(
                    f'<line x1="{gx:.2f}" x2="{gx:.2f}" y1="{y0}" y2="{y0 + subplot_h}" class="grid"/>'
                )
                svg.append(
                    f'<text x="{gx:.2f}" y="{y0 + subplot_h + 16}" text-anchor="middle" class="small">{_format_plot_value(tick)}</text>'
                )
            svg.append(f'<line x1="{x0}" x2="{x0}" y1="{y0}" y2="{y0 + subplot_h}" class="axis"/>')
            svg.append(
                f'<line x1="{x0}" x2="{x0 + subplot_w}" y1="{y0 + subplot_h}" y2="{y0 + subplot_h}" class="axis"/>'
            )
            color = colors[idx % len(colors)]
            svg.append(
                f'<polyline points="{_polyline_points(xs, ys, x0=x0, y0=y0, width=subplot_w, height=subplot_h, xmin=xmin, xmax=xmax, ymin=ymin, ymax=ymax)}" '
                f'fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
            )
            final_x = xs[-1]
            final_y = ys[-1]
            px = (
                x0 + subplot_w * 0.5
                if xmax == xmin
                else x0 + (final_x - xmin) / (xmax - xmin) * subplot_w
            )
            py = (
                y0 + subplot_h * 0.5
                if ymax == ymin
                else y0 + subplot_h - (final_y - ymin) / (ymax - ymin) * subplot_h
            )
            svg.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="3" fill="{color}"/>')
            svg.append(f'<text x="{x0}" y="{y0 - 10}" class="metric">{html.escape(metric)}</text>')
            stats = f"min {_format_plot_value(min(ys))} | mean {_format_plot_value(mean(ys))} | max {_format_plot_value(max(ys))} | final {_format_plot_value(ys[-1])}"
            svg.append(
                f'<text x="{x0 + subplot_w}" y="{y0 - 10}" text-anchor="end" class="small">{html.escape(stats)}</text>'
            )
        svg.append(
            f'<text x="{width / 2:.1f}" y="{height - 18}" text-anchor="middle" class="label">trainer step</text>'
        )
        svg.append("</svg>")
        svg_path.write_text("\n".join(svg), encoding="utf-8")

    return {
        "metrics_csv": str(csv_path),
        "metrics_summary": str(summary_path),
        "metrics_svg": str(svg_path),
    }


def _normalize_loopback_url(value: str, *, name: str) -> str:
    url = str(value).strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise ValueError(f"{name} must use http or https with a loopback host, got {value!r}")
    return url


def _decode_image_bytes(data: bytes) -> np.ndarray:
    pil_img = Image.open(io.BytesIO(data)).convert("RGB")
    img_array = np.array(pil_img, dtype=np.uint8)
    return np.transpose(img_array, (2, 0, 1))


class _TerminalProgressBar:
    def __init__(self, *, label: str, total: int):
        self.label = str(label)
        self.total = max(1, int(total))
        self.width = 30
        self.started_at = time.time()
        self._last_render_len = 0
        self._last_render_time = 0.0
        self._last_completed = 0
        self._min_refresh_sec = 0.2
        self._min_refresh_steps = 10

    def update(self, completed: int, *, force: bool = False) -> None:
        completed = max(0, min(int(completed), self.total))
        now = time.time()
        if not force and completed < self.total:
            if completed != 1:
                enough_time = (now - self._last_render_time) >= self._min_refresh_sec
                enough_steps = (completed - self._last_completed) >= self._min_refresh_steps
                if not (enough_time or enough_steps):
                    return
        frac = completed / float(self.total)
        filled = int(self.width * frac)
        bar = "#" * filled + "-" * (self.width - filled)
        elapsed = now - self.started_at
        line = (
            f"\r[{self.label}] train [{bar}] "
            f"{completed}/{self.total} ({frac * 100.0:5.1f}%) "
            f"elapsed {elapsed:6.1f}s"
        )
        pad = max(0, self._last_render_len - len(line))
        sys.stderr.write(line + (" " * pad))
        sys.stderr.flush()
        self._last_render_len = len(line)
        self._last_render_time = now
        self._last_completed = completed

    def close(self) -> None:
        self.update(self.total, force=True)
        sys.stderr.write("\n")
        sys.stderr.flush()


def _image_to_chw_uint8(value: Any, *, field_name: str) -> np.ndarray:
    if value is None:
        raise ValueError(f"{field_name} is required")

    if isinstance(value, (bytes, bytearray)):
        arr = _decode_image_bytes(bytes(value))
    elif isinstance(value, str):
        path = Path(value).expanduser()
        arr = np.transpose(np.array(Image.open(path).convert("RGB"), dtype=np.uint8), (2, 0, 1))
    else:
        arr = np.asarray(value)
        if arr.ndim == 4 and arr.shape[0] == 1:
            arr = arr[0]
        if arr.ndim != 3:
            raise ValueError(f"{field_name} must be rank-3 image data, got shape={list(arr.shape)}")
        if arr.shape[0] in (1, 3):
            pass
        elif arr.shape[-1] in (1, 3):
            arr = np.transpose(arr, (2, 0, 1))
        else:
            raise ValueError(
                f"{field_name} must be CHW or HWC image data, got shape={list(arr.shape)}"
            )

    arr = np.asarray(arr, dtype=np.uint8)
    if arr.shape[0] == 1:
        arr = np.repeat(arr, 3, axis=0)
    if arr.shape[0] != 3:
        raise ValueError(
            f"{field_name} must have 3 channels after conversion, got shape={list(arr.shape)}"
        )
    return arr


def _normalize_state(state: Any) -> np.ndarray:
    arr = np.asarray(state, dtype=np.float32)
    if arr.ndim == 1:
        arr = arr[:, None]
    elif arr.ndim == 2 and arr.shape[-1] == 1:
        pass
    else:
        raise ValueError(f"UniSteer state must have shape [D] or [D, 1], got {list(arr.shape)}")
    return np.ascontiguousarray(arr.astype(np.float32, copy=False))


def _flatten_float32(value: Any, name: str) -> np.ndarray:
    arr = np.asarray(value, dtype=np.float32).reshape(-1)
    if arr.size == 0:
        raise ValueError(f"{name} must not be empty")
    return arr


def _bool_mask(value: Any, *, name: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        return float(value)
    return float(bool(value))


def _log_noise_target_range(entries: Sequence[Mapping[str, Any]], *, tag: str) -> None:
    if not entries:
        logger.info(f"{tag} noise stats skipped: no entries")
        return

    noise_targets = np.stack(
        [np.asarray(entry["noise_target"], dtype=np.float32).reshape(-1) for entry in entries],
        axis=0,
    )
    l2 = np.linalg.norm(noise_targets, axis=1)
    logger.info(
        f"{tag} noise stats: "
        f"num_entries={int(noise_targets.shape[0])} "
        f"noise_dim={int(noise_targets.shape[1])} "
        f"value_min={float(noise_targets.min()):.6f} "
        f"value_max={float(noise_targets.max()):.6f} "
        f"value_mean={float(noise_targets.mean()):.6f} "
        f"value_std={float(noise_targets.std()):.6f} "
        f"abs_max={float(np.abs(noise_targets).max()):.6f} "
        f"l2_mean={float(l2.mean()):.6f} "
        f"l2_min={float(l2.min()):.6f} "
        f"l2_max={float(l2.max()):.6f}"
    )


@dataclass
class UniSteerRLServerConfig:
    auto_train: bool = True
    updates_per_cycle: int = 1
    num_initial_traj_collect: int = 1
    multi_grad_step: int = 1
    discount_horizon_steps: Optional[int] = None
    use_first_episode_grad_steps: bool = True
    first_episode_grad_steps: int = 5000
    truncate_success_on_done_index: bool = False
    keep_last_n_checkpoints: int = 5
    checkpoint_dir: str = "./logs/unisteer_checkpoint"
    default_train_now: bool = False
    save_checkpoint_on_train_now: bool = True
    infer_server_url: Optional[str] = "http://127.0.0.1:8000"
    image_key: str = "primary_image_crop"
    wrist_key: Optional[str] = None
    image_extension: str = "jpg"
    rl_min_updates: int = 0
    rl_log_freq: int = 50
    rl_plot_metrics: bool = True
    rl_metrics_dir: Optional[str] = None
    rollout_bootstrap_root: Optional[str] = None

    def resolved_discount_horizon(self, cfg: Any) -> int:
        raw_value = self.discount_horizon_steps
        if raw_value is None:
            raw_value = getattr(cfg, "horizon_steps", 1)
        value = int(raw_value)
        if value <= 0:
            raise ValueError(
                f"unisteer_server.discount_horizon_steps must be positive, got {value}"
            )
        return value

    @classmethod
    def from_cfg(
        cls, cfg: Any, *, checkpoint_dir: Optional[str] = None, auto_train: Optional[bool] = None
    ) -> "UniSteerRLServerConfig":
        section = (
            cfg.get("unisteer_server", {})
            if isinstance(cfg, dict)
            else getattr(cfg, "unisteer_server", {})
        )
        get = section.get if isinstance(section, dict) else lambda k, d=None: getattr(section, k, d)
        raw_discount_horizon = get("discount_horizon_steps", None)
        if raw_discount_horizon in (None, "", "null"):
            discount_horizon_steps = None
        else:
            discount_horizon_steps = int(raw_discount_horizon)
            if discount_horizon_steps <= 0:
                raise ValueError(
                    f"unisteer_server.discount_horizon_steps must be positive, got {discount_horizon_steps}"
                )
        infer_server_url = str(get("infer_server_url", "http://127.0.0.1:8000")).strip() or None
        if infer_server_url:
            infer_server_url = _normalize_loopback_url(
                infer_server_url, name="Inference server URL"
            )
        return cls(
            auto_train=bool(get("auto_train", True) if auto_train is None else auto_train),
            updates_per_cycle=int(get("updates_per_cycle", 1)),
            num_initial_traj_collect=int(get("num_initial_traj_collect", 1)),
            multi_grad_step=int(get("multi_grad_step", 1)),
            discount_horizon_steps=discount_horizon_steps,
            use_first_episode_grad_steps=bool(get("use_first_episode_grad_steps", True)),
            first_episode_grad_steps=int(get("first_episode_grad_steps", 5000)),
            truncate_success_on_done_index=bool(get("truncate_success_on_done_index", False)),
            keep_last_n_checkpoints=int(get("keep_last_n_checkpoints", 5)),
            checkpoint_dir=str(
                checkpoint_dir or get("checkpoint_dir", "./logs/unisteer_checkpoint")
            ),
            default_train_now=bool(get("default_train_now", False)),
            save_checkpoint_on_train_now=bool(get("save_checkpoint_on_train_now", True)),
            infer_server_url=infer_server_url,
            image_key=str(get("image_key", "primary_image_crop")),
            wrist_key=(
                str(get("wrist_key")).strip()
                if get("wrist_key", None) not in (None, "", "null")
                else None
            ),
            image_extension=str(get("image_extension", "jpg")),
            rl_min_updates=int(get("rl_min_updates", 0)),
            rl_log_freq=int(get("rl_log_freq", 50)),
            rl_plot_metrics=bool(get("rl_plot_metrics", True)),
            rl_metrics_dir=str(get("rl_metrics_dir", "")).strip() or None,
            rollout_bootstrap_root=str(get("rollout_bootstrap_root", "")).strip() or None,
        )


class UniSteerRLTrainService:
    def __init__(
        self,
        cfg: Any,
        *,
        server_cfg: UniSteerRLServerConfig,
        inference_agent: Optional["InferenceAgent"] = None,
        trainer: Optional[RLTrainer] = None,
    ):
        init_started_at = time.time()
        self.cfg = cfg
        self.server_cfg = server_cfg
        self.checkpoint_dir = Path(server_cfg.checkpoint_dir).expanduser().resolve()
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "[unisteer_rl_server] Initializing service "
            f"(checkpoint_dir={self.checkpoint_dir}, auto_train={self.server_cfg.auto_train})"
        )
        agent_started_at = time.time()
        self.agent = inference_agent or self._build_inference_agent(cfg)
        logger.info(
            f"[unisteer_rl_server] Inference agent ready in {time.time() - agent_started_at:.2f}s"
        )

        trainer_started_at = time.time()
        self.trainer = trainer or RLTrainer(cfg)
        logger.info(
            f"[unisteer_rl_server] UniSteer trainer ready in {time.time() - trainer_started_at:.2f}s"
        )
        finetune_cfg = getattr(getattr(self.cfg, "data", None), "finetune", None)
        self.unisteer_use_gripper_master = bool(getattr(finetune_cfg, "use_gripper_master", False))
        self.unisteer_discount_horizon = self.server_cfg.resolved_discount_horizon(self.cfg)

        self.lock = threading.RLock()

        self.transitions_received = 0
        self.episodes_received = 0
        self.last_metrics: Dict[str, Any] = {}
        self.last_error: Optional[str] = None
        self.last_checkpoint_path: Optional[str] = None
        self.last_actor_checkpoint_path: Optional[str] = None
        self.last_checkpoint_step: int = 0
        self.rollout_bootstrap_result: Optional[Dict[str, Any]] = None
        self.started_at = time.time()
        self._job_lock = threading.Lock()
        self._busy = False
        self._last_job: Dict[str, Any] = {}
        logger.info(
            f"[unisteer_rl_server] Service initialization complete in {time.time() - init_started_at:.2f}s"
        )

    def _build_inference_agent(self, cfg: Any) -> "InferenceAgent":
        from src.agent.inference_agent import InferenceAgent

        with open_dict(cfg):
            cfg.multi_gpu = False
            cfg.gpu_id = int(getattr(cfg, "gpu_id", 0))
        logger.info("Loading OpenPI inference agent for UniSteer observation reconstruction")
        return InferenceAgent(cfg)

    def close(self) -> None:
        return None

    def _trajectory_warmup_complete(self) -> bool:
        return int(self.episodes_received) >= int(self.server_cfg.num_initial_traj_collect)

    def _default_rollout_num_updates(self, *, num_transitions: int) -> int:
        if (
            bool(self.server_cfg.use_first_episode_grad_steps)
            and int(self.trainer.update_step) == 0
        ):
            return int(self.server_cfg.first_episode_grad_steps)
        return max(1, int(num_transitions) * int(self.server_cfg.multi_grad_step))

    def _run_updates(
        self, num_updates: int, *, progress_label: Optional[str] = None
    ) -> Dict[str, Any]:
        with self.lock:
            total_updates = max(1, int(num_updates))
            started_at = time.time()
            log_freq = max(1, int(self.server_cfg.rl_log_freq))
            label = str(progress_label or "unisteer")
            progress = _TerminalProgressBar(label=label, total=total_updates)
            metrics: Dict[str, Any] = {}
            history: List[Dict[str, Any]] = []
            for step_idx in range(total_updates):
                metrics = self.trainer.update(num_updates=1)
                row: Dict[str, Any] = {
                    "round_update": int(step_idx + 1),
                    "total_updates": int(total_updates),
                    "wall_elapsed_sec": float(time.time() - started_at),
                }
                row.update(
                    {
                        key: value
                        for key, value in metrics.items()
                        if _finite_float(value) is not None
                    }
                )
                history.append(row)
                progress.update(step_idx + 1)
                update_idx = step_idx + 1
                if update_idx == 1 or update_idx % log_freq == 0 or update_idx == total_updates:
                    logger.info(
                        f"[{label}] RL update {update_idx}/{total_updates} "
                        f"elapsed={time.time() - started_at:.2f}s "
                        f"{_format_scalar_metrics(metrics)}"
                    )
            progress.close()
            logger.info(
                f"[{label}] RL update done: num_updates={total_updates} "
                f"elapsed={time.time() - started_at:.2f}s "
                f"{_format_scalar_metrics(metrics)}"
            )
            if self.server_cfg.rl_plot_metrics:
                safe_label = (
                    "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in label).strip(
                        "_"
                    )
                    or "unisteer"
                )
                metrics_root = (
                    Path(self.server_cfg.rl_metrics_dir).expanduser().resolve()
                    if self.server_cfg.rl_metrics_dir
                    else self.checkpoint_dir / "rl_metrics"
                )
                artifact_dir = (
                    metrics_root
                    / f"{int(time.time())}_{safe_label}_step{int(self.trainer.update_step)}_n{total_updates}"
                )
                artifacts = _write_rl_metrics_artifacts(
                    history=history,
                    output_dir=artifact_dir,
                    title=f"{safe_label} RL metrics step={int(self.trainer.update_step)} updates={total_updates}",
                )
                metrics.update({f"rl_{key}": value for key, value in artifacts.items()})
                logger.info(
                    f"[{label}] RL metrics artifacts: "
                    f"{_format_scalar_metrics({f'rl_{key}': value for key, value in artifacts.items()})}"
                )
            return metrics

    def _notify_infer_reload(self, checkpoint: str) -> None:
        infer_url = (self.server_cfg.infer_server_url or "").rstrip("/")
        if not infer_url:
            return
        response = requests.post(
            f"{infer_url}/reload_actor", json={"checkpoint": checkpoint}, timeout=600
        )
        if response.status_code != 200:
            raise RuntimeError(f"infer reload_actor failed: {response.status_code} {response.text}")

    def _finalize_train_now(
        self,
        *,
        num_updates: int,
        save_checkpoint: bool,
        checkpoint_tag: Optional[str] = None,
        progress_label: Optional[str] = None,
        reload_infer: bool = False,
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "train_metrics": self._run_updates(num_updates, progress_label=progress_label)
        }
        if save_checkpoint:
            ckpt_local = self._save_checkpoint_locked(tag=checkpoint_tag)
            actor_ckpt = self._save_actor_checkpoint_locked(tag=checkpoint_tag)
            result["checkpoint"] = {"trainer": ckpt_local, "actor": actor_ckpt}
            self.last_checkpoint_step = int(self.trainer.update_step)
            if reload_infer:
                self._notify_infer_reload(actor_ckpt)
                result["infer_reload"] = {"status": "ok", "checkpoint": actor_ckpt}
        return result

    def _load_traj_task_instruction(self, traj_dir: Path) -> str:
        txt = traj_dir / "task_instruction.txt"
        if txt.exists():
            return txt.read_text(encoding="utf-8").strip()
        meta_json = traj_dir / "meta.json"
        if meta_json.exists():
            payload = json.loads(meta_json.read_text(encoding="utf-8"))
            task = str(payload.get("task", "")).strip()
            if task:
                return task
        raise FileNotFoundError(f"Could not find task instruction under {traj_dir}")

    def _load_traj_meta(self, traj_dir: Path) -> Dict[str, Any]:
        meta_path = traj_dir / "meta.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"Missing trajectory meta.json under {traj_dir}")
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise TypeError(f"Invalid trajectory meta payload in {meta_path}")
        return payload

    def _load_traj_proprio_series(self, traj_dir: Path) -> np.ndarray:
        proprio, _ = load_traj_proprio_action(
            traj_dir, use_gripper_master=self.unisteer_use_gripper_master
        )
        return proprio.astype(np.float32)

    def _load_traj_raw_observation(
        self, traj_dir: Path, *, step_index: int, proprio_series: np.ndarray, task_description: str
    ) -> Dict[str, Any]:
        if step_index < 0 or step_index >= proprio_series.shape[0]:
            raise IndexError(
                f"step_index out of range for {traj_dir}: step_index={step_index}, num_steps={proprio_series.shape[0]}"
            )

        image_path = resolve_traj_image_array_path(traj_dir, self.server_cfg.image_key)
        if not image_path.is_file():
            raise FileNotFoundError(
                f"Missing primary trajectory image array for step_index={step_index}: {image_path}"
            )
        image = load_traj_image_frame_chw_uint8(traj_dir, self.server_cfg.image_key, step_index)

        wrist_image = None
        if self.server_cfg.wrist_key:
            wrist_path = resolve_traj_image_array_path(traj_dir, self.server_cfg.wrist_key)
            if wrist_path.is_file():
                wrist_image = load_traj_image_frame_chw_uint8(
                    traj_dir, self.server_cfg.wrist_key, step_index
                )

        return {
            "image": image,
            "image_wrist": wrist_image,
            "proprio": proprio_series[step_index].astype(np.float32).copy(),
            "task_description": task_description,
        }

    def _build_pixels_from_raw_observation(self, observation: Mapping[str, Any]) -> np.ndarray:
        image = _image_to_chw_uint8(observation["image"], field_name="image")
        image_t = torch.from_numpy(image[None, ...])

        wrist_t = None
        wrist_value = observation.get("image_wrist")
        if wrist_value is not None:
            wrist = _image_to_chw_uint8(wrist_value, field_name="image_wrist")
            wrist_t = torch.from_numpy(wrist[None, ...])

        pixels = self.agent.build_unisteer_pixels(image=image_t, image_wrist=wrist_t)
        return np.asarray(pixels, dtype=np.uint8)

    def _build_observation_from_explicit_state(
        self, *, state: Any, raw_observation: Mapping[str, Any]
    ) -> Dict[str, np.ndarray]:
        return {
            "pixels": self._build_pixels_from_raw_observation(raw_observation),
            "state": _normalize_state(state),
        }

    def _build_observation_from_raw(
        self, raw_observation: Mapping[str, Any]
    ) -> Dict[str, np.ndarray]:
        image = _image_to_chw_uint8(raw_observation["image"], field_name="image")
        image_t = torch.from_numpy(image[None, ...])

        wrist_t = None
        wrist_value = raw_observation.get("image_wrist")
        if wrist_value is not None:
            wrist = _image_to_chw_uint8(wrist_value, field_name="image_wrist")
            wrist_t = torch.from_numpy(wrist[None, ...])

        proprio = np.asarray(raw_observation["proprio"], dtype=np.float32).reshape(1, 1, -1)
        proprio_t = torch.from_numpy(proprio)
        task = [str(raw_observation["task_description"])]

        obs = self.agent.build_unisteer_observation(
            image=image_t, image_wrist=wrist_t, proprio=proprio_t, task_description=task
        )
        return {
            "pixels": np.asarray(obs["pixels"], dtype=np.uint8),
            "state": _normalize_state(obs["state"]),
        }

    @staticmethod
    def _discover_rollout_dirs(root_dir: str) -> List[Path]:
        root = Path(root_dir).expanduser().resolve()
        if not root.exists():
            raise FileNotFoundError(f"trajectory_dir not found: {root}")
        if (root / "unisteer_episode.msgpack").exists():
            return [root]

        rollout_dirs = sorted(
            {path.parent.resolve() for path in root.rglob("unisteer_episode.msgpack")},
            key=lambda p: str(p),
        )
        if not rollout_dirs:
            raise FileNotFoundError(
                f"No UniSteer rollout sidecars found under {root}; expected unisteer_episode.msgpack"
            )
        return rollout_dirs

    def _discover_bootstrap_trajectory_dirs(self, root_dir: str) -> tuple[List[Path], List[Path]]:
        root = Path(root_dir).expanduser().resolve()
        if not root.exists():
            raise FileNotFoundError(f"rollout_bootstrap_root not found: {root}")

        meta_paths = [root / "meta.json"] if (root / "meta.json").exists() else []
        meta_paths.extend(root.rglob("meta.json"))
        model_dirs: List[Path] = []
        human_dirs: List[Path] = []
        for meta_path in sorted(
            {path.resolve() for path in meta_paths}, key=lambda path: str(path)
        ):
            meta_payload = self._load_traj_meta(meta_path.parent)
            if "human_collect" not in meta_payload:
                continue
            if bool(meta_payload["human_collect"]):
                human_dirs.append(meta_path.parent)
                continue
            if not (meta_path.parent / "unisteer_episode.msgpack").exists():
                continue
            is_human_path = meta_path.parent / "is_human.npy"
            if is_human_path.exists():
                is_human = np.asarray(np.load(is_human_path, mmap_mode="r"), dtype=bool).reshape(-1)
                if bool(np.any(is_human)):
                    continue
            model_dirs.append(meta_path.parent)
        return model_dirs, human_dirs

    def _bootstrap_model_replay(self, model_dirs: Sequence[Path]) -> Dict[str, Any]:
        if not model_dirs:
            return {
                "num_model_trajectories": 0,
                "num_success": 0,
                "num_failure": 0,
                "num_rl_transitions": 0,
                "replay_size": int(self.trainer.replay_buffer.size),
            }
        with self.lock:
            if int(self.trainer.replay_buffer.size) != 0:
                raise RuntimeError(
                    "Replay bootstrap requires an empty replay buffer, got "
                    f"size={int(self.trainer.replay_buffer.size)}"
                )

        num_success = 0
        num_failure = 0
        num_transitions = 0
        for traj_idx, traj_dir in enumerate(model_dirs, start=1):
            payload = self._build_episode_payload_from_rollout_dir(
                str(traj_dir), relabel_current_reward=True
            )
            payload["train_now"] = False
            payload["save_checkpoint"] = False
            self.ingest_episode(payload)
            trajectory_success = bool(payload["trajectory_success"])
            num_success += int(trajectory_success)
            num_failure += int(not trajectory_success)
            num_transitions += int(len(payload["transitions"]))
            logger.info(
                "[unisteer_rl_server] Replay bootstrap trajectory "
                f"{traj_idx}/{len(model_dirs)} path={traj_dir} "
                f"success={trajectory_success} chunks={len(payload['transitions'])}"
            )

        replay_size = int(self.trainer.replay_buffer.size)
        if replay_size != num_transitions:
            raise RuntimeError(
                f"Replay bootstrap size mismatch: transitions={num_transitions}, replay_size={replay_size}"
            )

        return {
            "num_model_trajectories": int(len(model_dirs)),
            "num_success": int(num_success),
            "num_failure": int(num_failure),
            "num_rl_transitions": int(num_transitions),
            "replay_size": replay_size,
        }

    def _bootstrap_human_sft(self, human_dirs: Sequence[Path]) -> Dict[str, Any]:
        return {
            "num_human_trajectories": int(len(human_dirs)),
            "num_sft_entries": 0,
            "sft_buffer_size": 0,
        }

    def bootstrap_from_rollout_root(self, root_dir: str) -> Dict[str, Any]:
        root = Path(root_dir).expanduser().resolve()
        model_dirs, human_dirs = self._discover_bootstrap_trajectory_dirs(str(root))
        if not model_dirs and not human_dirs:
            raise ValueError(
                f"No model or human trajectories found under rollout_bootstrap_root: {root}"
            )

        update_step_before = int(self.trainer.update_step)
        logger.info(
            "[unisteer_rl_server] Bootstrapping rollout data "
            f"root={root} model_trajectories={len(model_dirs)} human_trajectories={len(human_dirs)}"
        )
        model_result = self._bootstrap_model_replay(model_dirs)
        human_result = self._bootstrap_human_sft(human_dirs)
        if not model_dirs and int(human_result["num_sft_entries"]) == 0:
            raise ValueError(f"Rollout bootstrap loaded no trainable data from: {root}")
        if int(self.trainer.update_step) != update_step_before:
            raise RuntimeError(
                "Rollout bootstrap unexpectedly changed trainer update_step: "
                f"before={update_step_before}, after={int(self.trainer.update_step)}"
            )

        result = {
            "root": str(root),
            **model_result,
            **human_result,
            "update_step": int(self.trainer.update_step),
        }
        self.rollout_bootstrap_result = result
        logger.info(
            f"[unisteer_rl_server] Rollout bootstrap complete: {_format_scalar_metrics(result)}"
        )
        return result

    @staticmethod
    def _normalize_traj_dirs(paths: List[str]) -> List[Path]:
        resolved = [Path(str(p)).expanduser().resolve() for p in paths]
        dedup = sorted({p for p in resolved}, key=lambda p: str(p))
        for path in dedup:
            if not path.exists():
                raise FileNotFoundError(f"trajectory_dir not found: {path}")
            if not path.is_dir():
                raise NotADirectoryError(f"trajectory_dir is not a directory: {path}")
        return dedup

    def _build_current_binary_rewards(
        self, *, num_chunks: int, success: bool
    ) -> tuple[List[float], float]:
        section = (
            self.cfg.get("unisteer_server", {})
            if isinstance(self.cfg, dict)
            else getattr(self.cfg, "unisteer_server", {})
        )
        get = (
            section.get
            if isinstance(section, dict)
            else lambda key, default=None: getattr(section, key, default)
        )
        reward_backend = str(get("reward_backend", "")).strip()
        if reward_backend != BINARY_REWARD_BACKEND:
            raise ValueError(
                "Rollout bootstrap requires unisteer_server.reward_backend="
                f"{BINARY_REWARD_BACKEND!r}, got {reward_backend!r}"
            )

        discount = float(self.trainer.cfg.discount**self.unisteer_discount_horizon)
        rewards = build_binary_reward_sequence(num_chunks=int(num_chunks), success=bool(success))
        return rewards, discount

    def _build_episode_payload_from_rollout_dir(
        self,
        trajectory_dir: str,
        *,
        request_id: Optional[str] = None,
        relabel_current_reward: bool = False,
    ) -> Dict[str, Any]:
        traj_dir = Path(trajectory_dir).expanduser().resolve()
        episode_path = traj_dir / "unisteer_episode.msgpack"
        reward_path = traj_dir / "unisteer_reward_result.json"
        if not episode_path.exists():
            raise FileNotFoundError(f"Missing UniSteer episode sidecar: {episode_path}")
        if not reward_path.exists():
            raise FileNotFoundError(f"Missing UniSteer reward sidecar: {reward_path}")

        episode_payload = msgpack.unpackb(episode_path.read_bytes(), raw=False)
        if not isinstance(episode_payload, dict):
            raise TypeError(f"Invalid UniSteer episode payload in {episode_path}")
        steps = episode_payload.get("steps")
        if not isinstance(steps, list) or not steps:
            raise ValueError(f"Invalid UniSteer episode steps in {episode_path}")

        reward_result = json.loads(reward_path.read_text(encoding="utf-8"))
        if not isinstance(reward_result, dict):
            raise TypeError(f"Invalid reward payload in {reward_path}")
        meta_payload = self._load_traj_meta(traj_dir)
        if "success" not in meta_payload:
            raise KeyError(f"Missing 'success' in trajectory meta.json under {traj_dir}")
        trajectory_success = bool(meta_payload["success"])
        step_indices = [int(step["step_index"]) for step in steps]

        decision_scores = reward_result.get("decision_scores") or {}
        summary = reward_result.get("summary") or {}
        reward_backend = str(summary.get("backend", ""))
        expected_discount = float(self.trainer.cfg.discount**self.unisteer_discount_horizon)
        if relabel_current_reward:
            if reward_backend != BINARY_REWARD_BACKEND:
                raise ValueError(f"Unsupported reward backend {reward_backend!r} in {reward_path}")
            if bool(meta_payload.get("is_reset", False)):
                trajectory_success = False
            rewards, transition_discount = self._build_current_binary_rewards(
                num_chunks=len(steps), success=trajectory_success
            )
            decision_indices = step_indices
            is_binary_reward = True
        else:
            is_binary_reward = reward_backend == BINARY_REWARD_BACKEND
            if not is_binary_reward:
                raise ValueError(f"Unsupported reward backend {reward_backend!r} in {reward_path}")
            if bool(meta_payload.get("is_reset", False)):
                trajectory_success = False
            rewards = decision_scores.get("reward")
            decision_indices = decision_scores.get("decision_indices")
            transition_discount = expected_discount

        if not isinstance(rewards, list):
            raise ValueError(f"Missing decision_scores.reward in {reward_path}")
        if len(rewards) != len(steps):
            raise ValueError(
                f"Reward length mismatch in {reward_path}: rewards={len(rewards)} steps={len(steps)}"
            )

        proprio_series = self._load_traj_proprio_series(traj_dir)
        task_description = str(
            episode_payload.get("task_description") or self._load_traj_task_instruction(traj_dir)
        )
        final_frame_index = int(proprio_series.shape[0] - 1)
        final_raw_observation = self._load_traj_raw_observation(
            traj_dir,
            step_index=final_frame_index,
            proprio_series=proprio_series,
            task_description=task_description,
        )

        if decision_indices is not None:
            parsed_decision_indices = [int(v) for v in decision_indices]
            if parsed_decision_indices != step_indices:
                raise ValueError(
                    f"Decision index mismatch between {episode_path} and {reward_path}: "
                    f"steps={step_indices} rewards={parsed_decision_indices}"
                )
        if not relabel_current_reward:
            validate_binary_reward_sidecar(
                summary=summary,
                decision_scores=decision_scores,
                success=trajectory_success,
                num_chunks=len(steps),
                final_decision_index=step_indices[-1],
            )

        terminal_transition_idx = len(steps) - 1
        terminal_frame_index = final_frame_index
        if trajectory_success and self.server_cfg.truncate_success_on_done_index:
            frame_done_index = summary.get("done_index")
            if frame_done_index is not None:
                frame_done_index = int(frame_done_index)
                terminal_frame_index = min(final_frame_index, frame_done_index)
                mapped_idx = None
                for idx, step_index in enumerate(step_indices):
                    if step_index <= terminal_frame_index:
                        mapped_idx = idx
                    else:
                        break
                if mapped_idx is None:
                    raise ValueError(
                        f"Success done_index={frame_done_index} occurs before the first decision step in {episode_path}"
                    )
                terminal_transition_idx = int(mapped_idx)

        transitions: List[Dict[str, Any]] = []
        for idx, step in enumerate(steps[: terminal_transition_idx + 1]):
            if not isinstance(step, Mapping):
                raise TypeError(f"Invalid step payload at idx={idx} in {episode_path}")

            step_index = int(step["step_index"])
            state = _normalize_state(step["state"])
            raw_observation = self._load_traj_raw_observation(
                traj_dir,
                step_index=step_index,
                proprio_series=proprio_series,
                task_description=task_description,
            )
            observation = self._build_observation_from_explicit_state(
                state=state, raw_observation=raw_observation
            )

            is_last_transition = idx == terminal_transition_idx
            is_terminal = bool(is_last_transition and is_binary_reward)
            if not is_terminal:
                if is_last_transition:
                    next_observation = self._build_observation_from_raw(final_raw_observation)
                else:
                    next_step = steps[idx + 1]
                    next_step_index = int(next_step["step_index"])
                    next_raw_observation = self._load_traj_raw_observation(
                        traj_dir,
                        step_index=next_step_index,
                        proprio_series=proprio_series,
                        task_description=task_description,
                    )
                    next_observation = self._build_observation_from_explicit_state(
                        state=next_step["state"], raw_observation=next_raw_observation
                    )
                mask = 1.0
            else:
                next_observation = self._build_observation_from_raw(final_raw_observation)
                mask = 0.0

            transitions.append(
                {
                    "observation": observation,
                    "next_observation": next_observation,
                    "noise_action": _flatten_float32(step["noise_action"], "noise_action").tolist(),
                    "reward": float(rewards[idx]),
                    "mask": float(mask),
                    "discount": float(transition_discount),
                }
            )

        episode_id = str(episode_payload.get("request_id") or request_id or traj_dir.name)
        return {
            "episode_id": episode_id,
            "checkpoint_tag": f"{episode_id}_{int(time.time())}",
            "trajectory_success": trajectory_success,
            "transitions": transitions,
        }

    def train_rollout_dir(
        self, trajectory_dir: str, *, request_id: Optional[str] = None
    ) -> Dict[str, Any]:
        rollout_dirs = self._discover_rollout_dirs(trajectory_dir)
        return self.train_mixed_rollout(
            model_traj_dirs=[str(path) for path in rollout_dirs],
            human_traj_dirs=[],
            request_id=request_id,
        )

    def train_mixed_rollout(
        self,
        *,
        model_traj_dirs: List[str],
        human_traj_dirs: List[str],
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        model_dirs = self._normalize_traj_dirs(model_traj_dirs)
        human_dirs = self._normalize_traj_dirs(human_traj_dirs)
        if human_dirs:
            raise ValueError(
                "UniSteer train server is RL-only; use unisteer_train_server for human inverse SFT"
            )
        if not model_dirs:
            raise ValueError("UniSteer train_mixed_rollout requires at least one model trajectory")

        rollout_results: List[Dict[str, Any]] = []
        final_train_metrics: Optional[Dict[str, Any]] = None
        rl_update_result: Optional[Dict[str, Any]] = None
        trained_any = False
        num_model_chunks = 0

        for rollout_dir in model_dirs:
            per_request_id = request_id
            if request_id and len(model_dirs) > 1:
                per_request_id = f"{request_id}:{rollout_dir.name}"
            payload = self._build_episode_payload_from_rollout_dir(
                str(rollout_dir), request_id=per_request_id
            )
            num_model_chunks += int(len(payload["transitions"]))
            payload["train_now"] = False
            payload["save_checkpoint"] = False

            result = self.ingest_episode(payload)
            rollout_results.append(
                {
                    "trajectory_dir": str(rollout_dir),
                    "episode_id": payload["episode_id"],
                    "result": result,
                }
            )

        if (
            self.server_cfg.auto_train
            and num_model_chunks > 0
            and int(self.server_cfg.multi_grad_step) > 0
            and self._trajectory_warmup_complete()
            and self.trainer.ready()
        ):
            num_rl_updates = self._default_rollout_num_updates(num_transitions=num_model_chunks)
            rl_update_result = {
                "num_updates": int(num_rl_updates),
                "num_rl_chunks": int(num_model_chunks),
                "train_metrics": self._run_updates(num_rl_updates, progress_label="unisteer"),
            }
            final_train_metrics = rl_update_result.get("train_metrics") or final_train_metrics
            trained_any = True

        final_checkpoint: Optional[Dict[str, Any]] = None
        final_infer_reload: Optional[Dict[str, Any]] = None
        if self.server_cfg.auto_train and trained_any:
            checkpoint_tag = str(request_id or f"rollout_{int(time.time())}")
            ckpt_local = self.save_checkpoint(tag=checkpoint_tag)
            actor_ckpt = self.save_actor_checkpoint(tag=checkpoint_tag)
            final_checkpoint = {"trainer": ckpt_local, "actor": actor_ckpt}
            self.last_checkpoint_step = int(self.trainer.update_step)
            if self.server_cfg.infer_server_url:
                self._notify_infer_reload(actor_ckpt)
                final_infer_reload = {"status": "ok", "checkpoint": actor_ckpt}

        return {
            "num_rollouts": len(rollout_results),
            "num_model_trajectories": len(model_dirs),
            "num_model_chunks": int(num_model_chunks),
            "rollouts": rollout_results,
            "rl_update_result": rl_update_result,
            "checkpoint": final_checkpoint,
            "infer_reload": final_infer_reload,
            "train_metrics": final_train_metrics,
        }

    def _save_checkpoint_locked(
        self, *, tag: Optional[str] = None, path: Optional[str] = None
    ) -> str:
        if path is None:
            step = int(self.trainer.update_step)
            suffix = tag or f"step_{step:08d}"
            path = str(self.checkpoint_dir / f"unisteer_{suffix}.pt")
        ckpt_path = self.trainer.save_checkpoint(path)
        self.last_checkpoint_path = ckpt_path
        self._prune_old_checkpoints()
        return ckpt_path

    def _save_actor_checkpoint_locked(
        self, *, tag: Optional[str] = None, path: Optional[str] = None
    ) -> str:
        if path is None:
            step = int(self.trainer.update_step)
            suffix = tag or f"step_{step:08d}"
            path = str(self.checkpoint_dir / f"actor_{suffix}.pt")
        ckpt_path = self.trainer.save_actor_checkpoint(path)
        self.last_actor_checkpoint_path = ckpt_path
        self._prune_old_checkpoints()
        return ckpt_path

    def _prune_old_checkpoints(self) -> None:
        keep = max(0, int(self.server_cfg.keep_last_n_checkpoints))
        if keep <= 0:
            return
        ckpts = sorted(
            self.checkpoint_dir.glob("unisteer_*.pt"), key=lambda p: p.stat().st_mtime, reverse=True
        )
        for stale in ckpts[keep:]:
            try:
                stale.unlink()
            except FileNotFoundError:
                pass
        actor_ckpts = sorted(
            self.checkpoint_dir.glob("actor_*.pt"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for stale in actor_ckpts[keep:]:
            try:
                stale.unlink()
            except FileNotFoundError:
                pass

    def save_checkpoint(self, *, tag: Optional[str] = None, path: Optional[str] = None) -> str:
        with self.lock:
            return self._save_checkpoint_locked(tag=tag, path=path)

    def save_actor_checkpoint(
        self, *, tag: Optional[str] = None, path: Optional[str] = None
    ) -> str:
        with self.lock:
            return self._save_actor_checkpoint_locked(tag=tag, path=path)

    def load_checkpoint(self, path: str) -> None:
        with self.lock:
            self.trainer.load_checkpoint(path)
            self.last_checkpoint_path = str(Path(path).expanduser().resolve())
            self.last_checkpoint_step = int(self.trainer.update_step)

    def _parse_request_payload(self) -> Dict[str, Any]:
        # Keep the raw body cached so Flask can still decode JSON from the same request.
        raw = request.get_data(cache=True)
        content_type = (request.content_type or "").lower()
        if "msgpack" in content_type:
            payload = msgpack.unpackb(raw, raw=False)
        else:
            payload = {} if not raw else request.get_json(force=True, silent=False)
        if not isinstance(payload, dict):
            raise TypeError("Request payload must decode to a JSON/msgpack object")
        return payload

    def _normalize_direct_observation(
        self, observation: Mapping[str, Any]
    ) -> Dict[str, np.ndarray]:
        if "pixels" in observation and "state" in observation:
            return {
                "pixels": np.asarray(observation["pixels"], dtype=np.uint8),
                "state": _normalize_state(observation["state"]),
            }
        raise ValueError("Direct UniSteer observation payload must contain 'pixels' and 'state'")

    def _ingest_transition(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        observation = self._normalize_direct_observation(payload["observation"])
        next_observation = self._normalize_direct_observation(payload["next_observation"])
        noise_action = _flatten_float32(payload["noise_action"], "noise_action")
        reward = float(payload["reward"])
        mask = _bool_mask(payload.get("mask", 1.0), name="mask")
        discount = float(payload.get("discount", self.trainer.cfg.discount))

        self.trainer.add_transition(
            observation=observation,
            next_observation=next_observation,
            noise_action=noise_action,
            reward=reward,
            mask=mask,
            discount=discount,
        )
        self.transitions_received += 1

        result = {
            "state_dim": int(observation["state"].shape[0]),
            "noise_action_dim": int(noise_action.size),
            "pixel_shape": list(observation["pixels"].shape),
            "replay_size": int(self.trainer.replay_buffer.size),
            "ready": bool(self.trainer.ready()),
        }
        train_now = bool(payload.get("train_now", False))
        if train_now and self.trainer.ready():
            num_updates = int(payload.get("num_updates", self.server_cfg.updates_per_cycle))
            save_checkpoint = bool(
                payload.get("save_checkpoint", self.server_cfg.save_checkpoint_on_train_now)
            )
            checkpoint_tag = payload.get("checkpoint_tag")
            result.update(
                self._finalize_train_now(
                    num_updates=num_updates,
                    save_checkpoint=save_checkpoint,
                    checkpoint_tag=str(checkpoint_tag) if checkpoint_tag else None,
                    reload_infer=bool(self.server_cfg.infer_server_url),
                )
            )
        return result

    def ingest_transition(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        with self.lock:
            return self._ingest_transition(payload)

    def ingest_episode(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        transitions = payload.get("transitions")
        if not isinstance(transitions, list) or not transitions:
            raise ValueError("transitions must be a non-empty list")

        episode_results: List[Dict[str, Any]] = []
        with self.lock:
            for transition in transitions:
                if not isinstance(transition, Mapping):
                    raise TypeError("Each transition must be a mapping")
                episode_results.append(self._ingest_transition(transition))
            self.episodes_received += 1

            response: Dict[str, Any] = {
                "num_transitions": len(transitions),
                "replay_size": int(self.trainer.replay_buffer.size),
                "ready": bool(self._trajectory_warmup_complete() and self.trainer.ready()),
                "last_transition": episode_results[-1],
            }
            train_now = bool(payload.get("train_now", self.server_cfg.default_train_now))
            if train_now and self._trajectory_warmup_complete() and self.trainer.ready():
                if "num_updates" in payload:
                    num_updates = int(payload["num_updates"])
                else:
                    num_updates = self._default_rollout_num_updates(
                        num_transitions=len(transitions)
                    )
                save_checkpoint = bool(
                    payload.get("save_checkpoint", self.server_cfg.save_checkpoint_on_train_now)
                )
                checkpoint_tag = payload.get("checkpoint_tag")
                response.update(
                    self._finalize_train_now(
                        num_updates=num_updates,
                        save_checkpoint=save_checkpoint,
                        checkpoint_tag=str(checkpoint_tag) if checkpoint_tag else None,
                        progress_label=str(
                            payload.get("episode_id") or checkpoint_tag or "episode"
                        ),
                        reload_infer=bool(self.server_cfg.infer_server_url),
                    )
                )
            return response

    def status(self) -> Dict[str, Any]:
        with self.lock:
            replay_size = int(self.trainer.replay_buffer.size)
            update_step = int(self.trainer.update_step)
        return {
            "uptime_sec": time.time() - self.started_at,
            "auto_train": bool(self.server_cfg.auto_train),
            "busy": bool(self._busy),
            "last_job": self._last_job,
            "worker_alive": False,
            "transitions_received": int(self.transitions_received),
            "episodes_received": int(self.episodes_received),
            "replay_size": replay_size,
            "ready": bool(self._trajectory_warmup_complete() and self.trainer.ready()),
            "trajectory_warmup_complete": bool(self._trajectory_warmup_complete()),
            "update_step": update_step,
            "last_metrics": self.last_metrics,
            "last_checkpoint_path": self.last_checkpoint_path,
            "last_actor_checkpoint_path": self.last_actor_checkpoint_path,
            "rollout_bootstrap": self.rollout_bootstrap_result,
            "last_error": self.last_error,
            "trainer_cfg": asdict(self.trainer.cfg),
            "server_cfg": asdict(self.server_cfg),
        }


class UniSteerRLServerApp:
    def __init__(self, service: UniSteerRLTrainService):
        self.service = service
        self.app = Flask(__name__)
        self.app.route("/health", methods=["GET"])(self.handle_health)
        self.app.route("/status", methods=["GET"])(self.handle_status)
        self.app.route("/train_rollout", methods=["POST"])(self.handle_train_rollout)

    def handle_health(self) -> Response:
        return _json_response({"status": "ok", "service": "unisteer_rl_server"})

    def handle_status(self) -> Response:
        return _json_response({"status": "ok", "service": self.service.status()})

    def handle_train_rollout(self) -> Response:
        try:
            payload = request.get_json(force=True, silent=False) or {}
            rollout_dir = payload.get("trajectory_dir")
            request_id = payload.get("request_id", "unknown")
            model_trajectory_dirs = payload.get("model_trajectory_dirs") or []
            human_trajectory_dirs = payload.get("human_trajectory_dirs") or []
            if not rollout_dir and not model_trajectory_dirs and not human_trajectory_dirs:
                return _json_response(
                    {"status": "error", "message": "missing trajectory_dir"}, status=400
                )
            if rollout_dir:
                rollout_dir = str(Path(str(rollout_dir)).expanduser().resolve())
                if not Path(rollout_dir).exists():
                    return _json_response(
                        {"status": "error", "message": f"trajectory_dir not found: {rollout_dir}"},
                        status=400,
                    )

            with self.service._job_lock:
                if self.service._busy:
                    return _json_response({"status": "busy"}, status=409)
                self.service._busy = True

            def _train_job() -> None:
                try:
                    logger.info(
                        f"[unisteer_rl_server] train_rollout request_id={request_id} "
                        f"trajectory_dir={rollout_dir} "
                        f"model_trajectories={len(model_trajectory_dirs)} "
                        f"human_trajectories={len(human_trajectory_dirs)}"
                    )
                    if model_trajectory_dirs or human_trajectory_dirs:
                        result = self.service.train_mixed_rollout(
                            model_traj_dirs=[str(p) for p in model_trajectory_dirs],
                            human_traj_dirs=[str(p) for p in human_trajectory_dirs],
                            request_id=str(request_id),
                        )
                    else:
                        result = self.service.train_rollout_dir(
                            rollout_dir, request_id=str(request_id)
                        )
                    with self.service._job_lock:
                        self.service._last_job = {
                            "status": "ok",
                            "request_id": request_id,
                            "trajectory_dir": rollout_dir,
                            "model_trajectory_dirs": model_trajectory_dirs,
                            "human_trajectory_dirs": human_trajectory_dirs,
                            "result": result,
                        }
                except Exception as exc:
                    logger.exception(f"[unisteer_rl_server] train_rollout failed: {exc}")
                    with self.service._job_lock:
                        self.service._last_job = {
                            "status": "error",
                            "request_id": request_id,
                            "trajectory_dir": rollout_dir,
                            "model_trajectory_dirs": model_trajectory_dirs,
                            "human_trajectory_dirs": human_trajectory_dirs,
                            "message": str(exc),
                        }
                finally:
                    with self.service._job_lock:
                        self.service._busy = False

            threading.Thread(target=_train_job, daemon=True).start()
            return _json_response({"status": "accepted", "request_id": request_id}, status=202)
        except Exception as exc:
            logger.exception(f"[unisteer_rl_server] train_rollout request failed: {exc}")
            return _json_response({"status": "error", "message": str(exc)}, status=500)

    def run(self, host: str = "127.0.0.1", port: int = 9200) -> None:
        logger.info(f"Starting unisteer_rl_server on {host}:{port}")
        self.app.run(host=host, port=port, threaded=True)


def _register_omegaconf_resolvers() -> None:
    from datetime import datetime
    import math

    if OmegaConf is None:
        return
    OmegaConf.register_new_resolver("eval", eval, replace=True)
    OmegaConf.register_new_resolver("round_up", math.ceil, replace=True)
    OmegaConf.register_new_resolver("round_down", math.floor, replace=True)
    OmegaConf.register_new_resolver("now", lambda fmt: datetime.now().strftime(fmt), replace=True)


def build_service_from_cli(
    args: argparse.Namespace,
    service_cls: type[UniSteerRLTrainService] = UniSteerRLTrainService,
    server_config_cls: type[UniSteerRLServerConfig] = UniSteerRLServerConfig,
) -> UniSteerRLTrainService:
    if OmegaConf is None:
        raise ImportError("omegaconf is required to run unisteer_rl_server.py")

    cfg = OmegaConf.load(str(Path(args.config).expanduser().resolve()))

    with open_dict(cfg):
        if args.base_checkpoint:
            cfg.inference_checkpoint_path = str(args.base_checkpoint)
        else:
            cfg.inference_checkpoint_path = str(
                getattr(cfg, "inference_checkpoint_path", None) or cfg.init_ckpt
            )
        if args.infer_server_url:
            cfg.unisteer_server.infer_server_url = _normalize_loopback_url(
                args.infer_server_url, name="Inference server URL"
            )

    server_cfg = server_config_cls.from_cfg(
        cfg, checkpoint_dir=args.checkpoint_dir, auto_train=args.auto_train
    )
    if args.infer_server_url:
        server_cfg.infer_server_url = _normalize_loopback_url(
            args.infer_server_url, name="Inference server URL"
        )

    logger.info(
        "[unisteer_rl_server] Building service from CLI "
        f"(config={Path(args.config).expanduser().resolve()}, "
        f"base_checkpoint={cfg.inference_checkpoint_path}, "
        f"unisteer_checkpoint={args.unisteer_checkpoint or 'none'})"
    )
    service_started_at = time.time()
    service = service_cls(cfg, server_cfg=server_cfg)
    logger.info(
        f"[unisteer_rl_server] Service constructed in {time.time() - service_started_at:.2f}s"
    )
    if args.unisteer_checkpoint:
        ckpt_started_at = time.time()
        logger.info(
            f"[unisteer_rl_server] Loading UniSteer checkpoint from {args.unisteer_checkpoint}"
        )
        service.load_checkpoint(args.unisteer_checkpoint)
        logger.info(
            f"[unisteer_rl_server] UniSteer checkpoint load complete in {time.time() - ckpt_started_at:.2f}s"
        )
    if server_cfg.rollout_bootstrap_root:
        bootstrap_started_at = time.time()
        service.bootstrap_from_rollout_root(server_cfg.rollout_bootstrap_root)
        logger.info(
            "[unisteer_rl_server] Rollout bootstrap load complete in "
            f"{time.time() - bootstrap_started_at:.2f}s"
        )
    return service


def main() -> None:
    _register_omegaconf_resolvers()

    parser = argparse.ArgumentParser(description="Local UniSteer training service")
    parser.add_argument("--config", type=str, required=True)
    parser.add_argument("--base_checkpoint", type=str, default=None)
    parser.add_argument("--unisteer_checkpoint", type=str, default=None)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9200)
    parser.add_argument("--checkpoint_dir", type=str, default=None)
    parser.add_argument(
        "--auto_train", type=lambda x: str(x).lower() in {"1", "true", "yes"}, default=None
    )
    parser.add_argument("--infer_server_url", type=str, default=None)
    args = parser.parse_args()

    logger.info(
        "[unisteer_rl_server] CLI startup "
        f"(host={args.host}, port={args.port}, auto_train={args.auto_train}, "
        f"checkpoint_dir={args.checkpoint_dir})"
    )
    service = build_service_from_cli(args)
    app = UniSteerRLServerApp(service)
    logger.info(f"[unisteer_rl_server] Starting Flask app on {args.host}:{args.port}")
    app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
