"""
Normal-policy SFT trainer backed by original LeRobot OpenPI family policies.

This repo copy intentionally keeps only one active normal-policy path.
"""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timedelta
import math
import os
from pathlib import Path
import re
import threading
import time
from typing import Any, Dict, Optional

from lerobot.utils.constants import ACTION
from loguru import logger
import numpy as np
from omegaconf import OmegaConf, open_dict
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader
from torch.utils.data.distributed import DistributedSampler

from src.dataset.dataset import DistributedWeightedSampler, FinetuneDataset, FinetuneSampleDataset
from src.model.openpi.openpi_adapter import OpenPiAdapter, build_openpi_adapter
from src.model.openpi.openpi_common import resolve_openpi_policy_type, sync_normal_policy_horizon
from src.utils.optim import CosineAnnealingWarmupRestarts, optimizer_to


def _register_omegaconf_resolvers() -> None:
    OmegaConf.register_new_resolver("eval", eval, replace=True)
    OmegaConf.register_new_resolver("round_up", math.ceil, replace=True)
    OmegaConf.register_new_resolver("round_down", math.floor, replace=True)
    OmegaConf.register_new_resolver("now", lambda fmt: datetime.now().strftime(fmt), replace=True)


def _cfg_get(cfg: Any, key: str, default: Any = None) -> Any:
    if cfg is None:
        return default
    if isinstance(cfg, dict):
        return cfg.get(key, default)
    return getattr(cfg, key, default)


def _ensure_dir(path: str | Path) -> str:
    out = Path(path)
    out.mkdir(parents=True, exist_ok=True)
    return str(out)


def _checkpoint_step(path: str | Path) -> int:
    match = re.fullmatch(r"step(\d+)\.pt", Path(path).name)
    return int(match.group(1)) if match is not None else -1


def _snapshot_to_cpu_tree(value: Any) -> Any:
    if isinstance(value, torch.Tensor):
        return value.detach().cpu().clone()
    if isinstance(value, dict):
        return {key: _snapshot_to_cpu_tree(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_snapshot_to_cpu_tree(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_snapshot_to_cpu_tree(item) for item in value)
    return value


@dataclass
class SFTModeConfig:
    max_updates_total: int
    max_epochs: int
    eval_interval: int
    eval_batches: int


class SFTTrainer:
    def __init__(self, cfg: Any):
        _register_omegaconf_resolvers()
        self.cfg = cfg
        sync_normal_policy_horizon(self.cfg)

        self.ds_train: Optional[FinetuneDataset] = None
        self.ds_val: Optional[FinetuneDataset] = None
        self.train_dataset: Optional[FinetuneSampleDataset] = None
        self.val_dataset: Optional[FinetuneSampleDataset] = None
        self.train_sampler: Optional[Any] = None
        self.train_dataloader: Optional[DataLoader] = None
        self.val_dataloader: Optional[DataLoader] = None

        self.policy_type = resolve_openpi_policy_type(self.cfg)
        self.adapter: Optional[OpenPiAdapter] = None
        self.model: Optional[torch.nn.Module] = None
        self.base_model: Optional[torch.nn.Module] = None
        self.action_optimizer: Optional[torch.optim.Optimizer] = None
        self.action_lr_scheduler = None
        self.trainable_parameters: list[torch.nn.Parameter] = []

        self.cnt_batch = 0
        self.cnt_update = 0
        self.cnt_epoch = 0
        self.current_checkpoint_path = ""
        self.async_checkpoint_save = False
        self._checkpoint_save_thread: Optional[threading.Thread] = None
        self._checkpoint_save_error: Exception | None = None
        self._checkpoint_save_path = ""

        self._dataset_initialized = False
        self._model_initialized = False

        self._setup_hardware()
        self._auto_batchsize()
        self._setup_params()
        self._setup_resume()

        if self.main_rank:
            logger.info(f"Original {self.policy_type} SFTTrainer initialization complete.")

    def _setup_hardware(self) -> None:
        cfg = self.cfg
        self.gpu_id = int(_cfg_get(cfg, "gpu_id", 0))
        self.multi_gpu = bool(_cfg_get(cfg, "multi_gpu", False))
        self.world_size = 1
        self.local_rank = 0
        self.global_rank = 0
        self.local_world_size = 1
        self.group_rank = 0

        if self.multi_gpu:
            import torch.distributed as dist

            self.global_rank = int(os.environ["RANK"])
            self.local_rank = int(os.environ["LOCAL_RANK"])
            self.local_world_size = int(os.environ["LOCAL_WORLD_SIZE"])
            self.world_size = int(os.environ["WORLD_SIZE"])
            self.group_rank = int(os.environ.get("GROUP_RANK", 0))
            self.gpu_id = self.local_rank
            torch.cuda.set_device(self.local_rank)
            if not dist.is_initialized():
                dist.init_process_group(
                    backend="nccl", init_method="env://", timeout=timedelta(hours=6)
                )

        self.device = torch.device(f"cuda:{self.gpu_id}" if torch.cuda.is_available() else "cpu")
        self.main_rank = (not self.multi_gpu) or (self.global_rank == 0)
        if not self.main_rank:
            logger.remove()

        if self.device.type == "cuda":
            self.gpu_memory_gb = torch.cuda.get_device_properties(self.gpu_id).total_memory / (
                1024**3
            )
        else:
            self.gpu_memory_gb = 0.0
        logger.info(f"Using device {self.device} | vram={self.gpu_memory_gb:.1f}GB")

    def _auto_batchsize(self) -> None:
        cfg = self.cfg
        if self.gpu_memory_gb < 20:
            auto_batch_size = 2
        elif self.gpu_memory_gb < 45:
            auto_batch_size = 4
        elif self.gpu_memory_gb < 90:
            auto_batch_size = 32
        elif self.gpu_memory_gb < 120:
            auto_batch_size = 40
        else:
            auto_batch_size = 64

        if _cfg_get(cfg, "per_device_batch_size", None) is None:
            cfg.per_device_batch_size = auto_batch_size
        global_bs = int(_cfg_get(cfg, "global_batch_size", 256))
        self.grad_accumulation_steps = max(
            global_bs // (int(cfg.per_device_batch_size) * max(self.world_size, 1)), 1
        )
        logger.info(
            f"per_device_batch_size={cfg.per_device_batch_size} | grad_accumulation_steps={self.grad_accumulation_steps}"
        )

    def _setup_params(self) -> None:
        cfg = self.cfg
        self.log_dir = str(_cfg_get(cfg, "log_dir", "./logs"))
        self.checkpoint_dir = _ensure_dir(
            str(_cfg_get(cfg, "checkpoint_dir", os.path.join(self.log_dir, "checkpoint")))
        )
        self.optimizer_checkpoint_dir = _ensure_dir(
            str(
                _cfg_get(
                    cfg,
                    "optimizer_checkpoint_dir",
                    os.path.join(self.log_dir, "optimizer_checkpoint"),
                )
            )
        )
        self.log_freq = int(_cfg_get(cfg, "log_freq", 16))
        self.save_model_freq = int(_cfg_get(cfg, "save_model_freq", 100))
        self.save_model_start = int(_cfg_get(cfg, "save_model_start", 0))
        self.save_optimizer_freq = int(_cfg_get(cfg, "save_optimizer_freq", 0))
        self.save_optimizer_on_final = bool(_cfg_get(cfg, "save_optimizer_on_final", False))
        self.max_grad_norm = float(_cfg_get(cfg, "max_grad_norm", 1.0))
        self.use_amp = bool(_cfg_get(cfg, "use_amp", True)) and self.device.type == "cuda"
        self.amp_dtype = torch.bfloat16 if bool(_cfg_get(cfg, "use_bf16", True)) else torch.float32
        self.empty_cache_freq = int(_cfg_get(cfg, "empty_cache_freq", 0))

        mode = str(_cfg_get(cfg, "mode", "offline")).lower()
        if mode != "offline":
            raise ValueError(f"SFTTrainer only supports mode='offline', got {mode!r}")
        self.mode_cfg = SFTModeConfig(
            max_updates_total=int(
                _cfg_get(cfg, "max_updates_total", _cfg_get(cfg, "n_updates", 2000))
            ),
            max_epochs=max(0, int(_cfg_get(cfg, "max_epochs", 0))),
            eval_interval=int(_cfg_get(cfg, "eval_interval", 0)),
            eval_batches=int(_cfg_get(cfg, "eval_batches", 20)),
        )
        self.async_checkpoint_save = bool(_cfg_get(cfg, "async_checkpoint_save", True))
        self.run_eval = (
            hasattr(cfg, "data")
            and hasattr(cfg.data, "finetune_val")
            and self.mode_cfg.eval_interval > 0
        )
        logger.info(
            f"Mode=offline | max_updates_total={self.mode_cfg.max_updates_total} | "
            f"max_epochs={self.mode_cfg.max_epochs}"
        )

    def _setup_resume(self) -> None:
        cfg = self.cfg
        resume_path = str(_cfg_get(cfg, "resume_checkpoint_path", "") or "").strip()
        latest_optimizer = self._latest_checkpoint_path_in_dir(self.optimizer_checkpoint_dir)
        if (
            resume_path
            and latest_optimizer
            and _checkpoint_step(latest_optimizer) > _checkpoint_step(resume_path)
        ):
            with open_dict(cfg):
                cfg.resume_checkpoint_path = latest_optimizer
            logger.info(
                f"Override resume_checkpoint_path with newer optimizer checkpoint in current run dir: "
                f"{latest_optimizer} > {resume_path}"
            )
            resume_path = latest_optimizer
        elif not resume_path:
            latest = latest_optimizer or self._latest_checkpoint_path_in_dir(self.checkpoint_dir)
            if latest:
                with open_dict(cfg):
                    cfg.resume_checkpoint_path = latest
                resume_path = latest
                logger.info(f"Auto-resume from latest checkpoint: {resume_path}")

        self.current_checkpoint_path = resume_path or self._infer_model_source_from_cfg()

    @staticmethod
    def _latest_checkpoint_path_in_dir(checkpoint_dir: str | Path) -> str:
        checkpoint_dir = Path(checkpoint_dir)
        if not checkpoint_dir.exists():
            return ""
        best_num = -1
        best_path = ""
        for path in checkpoint_dir.glob("step*.pt"):
            match = re.fullmatch(r"step(\d+)\.pt", path.name)
            if match is None:
                continue
            step = int(match.group(1))
            if step > best_num:
                best_num = step
                best_path = str(path)
        return best_path

    def _latest_checkpoint_path(self) -> str:
        optimizer_path = self._latest_checkpoint_path_in_dir(self.optimizer_checkpoint_dir)
        if optimizer_path:
            return optimizer_path
        return self._latest_checkpoint_path_in_dir(self.checkpoint_dir)

    def _infer_model_source_from_cfg(self) -> str:
        for key in ("resume_checkpoint_path", "init_ckpt", "pretrained_model_path"):
            value = str(_cfg_get(self.cfg, key, "") or "").strip()
            if value:
                return value
        return ""

    def _estimate_steps_per_epoch(self, num_samples: int) -> int:
        effective_batch_size = max(
            1,
            int(self.cfg.per_device_batch_size)
            * max(self.world_size, 1)
            * max(self.grad_accumulation_steps, 1),
        )
        return max(1, math.ceil(int(num_samples) / effective_batch_size))

    def _rebuild_train_dataloader(self) -> None:
        assert self.ds_train is not None
        if self.train_dataset is None:
            self.train_dataset = FinetuneSampleDataset(self.ds_train)
        else:
            self.train_dataset.rebuild_items()

        sample_weights = self.train_dataset.sample_weights()
        if sample_weights is not None:
            self.train_sampler = DistributedWeightedSampler(
                sample_weights,
                num_replicas=self.world_size if self.multi_gpu else 1,
                rank=self.global_rank if self.multi_gpu else 0,
                seed=int(_cfg_get(self.cfg, "seed", 0)),
            )
            shuffle = False
            if self.main_rank:
                logger.info(
                    "Policy SFT weighted data mix enabled\n" + self.ds_train.data_mix_summary_str()
                )
        elif self.multi_gpu:
            self.train_sampler = DistributedSampler(
                self.train_dataset,
                num_replicas=self.world_size,
                rank=self.global_rank,
                shuffle=True,
                drop_last=False,
            )
            shuffle = False
        else:
            self.train_sampler = None
            shuffle = True

        self.train_dataloader = DataLoader(
            self.train_dataset,
            batch_size=int(self.cfg.per_device_batch_size),
            pin_memory=bool(_cfg_get(self.cfg, "pin_memory", True)),
            num_workers=int(_cfg_get(self.cfg, "num_workers", 4)),
            prefetch_factor=2 if int(_cfg_get(self.cfg, "num_workers", 4)) > 0 else None,
            persistent_workers=int(_cfg_get(self.cfg, "num_workers", 4)) > 0,
            sampler=self.train_sampler,
            shuffle=shuffle,
            drop_last=False,
        )

    def _setup_dataset(self) -> None:
        cfg = self.cfg
        logger.info("Loading training dataset...")
        self.ds_train = FinetuneDataset(cfg.data.finetune, train=True)
        logger.info("Training normalization ranges\n" + self.ds_train.normalization_summary_str())
        self._rebuild_train_dataloader()
        logger.info(
            f"Policy SFT sample view | samples={len(self.train_dataset)} | "
            f"steps_per_epoch={self._estimate_steps_per_epoch(len(self.train_dataset))}"
        )
        if self.run_eval:
            self._run_evaluation()
            self.val_dataloader = DataLoader(
                self.val_dataset,
                batch_size=int(cfg.per_device_batch_size),
                pin_memory=bool(_cfg_get(cfg, "pin_memory", True)),
                num_workers=int(_cfg_get(cfg, "val_num_workers", 0)),
                shuffle=False,
                drop_last=False,
            )
        self._dataset_initialized = True

    def _setup_model_optimizer(self) -> None:
        assert self.ds_train is not None
        self.adapter = build_openpi_adapter(
            self.cfg, dataset_statistics=self.ds_train.dataset_statistics, device=str(self.device)
        )
        checkpoint_path = (
            str(_cfg_get(self.cfg, "resume_checkpoint_path", "") or "").strip() or None
        )
        model, checkpoint_payload = self.adapter.load_policy(checkpoint_path)
        self.current_checkpoint_path = checkpoint_path or self.current_checkpoint_path
        model.to(self.device)

        if self.multi_gpu:
            import torch.distributed as dist
            from torch.nn.parallel import DistributedDataParallel as DDP

            model = DDP(
                model,
                device_ids=[self.local_rank],
                # OpenPI policies keep a small set of trainable parameters that
                # do not participate in the action loss every step. Single-GPU
                # training tolerates this, but DDP requires explicit unused-param
                # detection to keep reduction state consistent.
                find_unused_parameters=True,
                gradient_as_bucket_view=True,
            )
            dist.barrier()
            self.base_model = model.module
        else:
            self.base_model = model
        self.model = model

        self.trainable_parameters = [p for p in self.base_model.parameters() if p.requires_grad]
        if not self.trainable_parameters:
            raise RuntimeError(f"No trainable parameters found for original {self.policy_type} SFT")

        policy_cfg = self.adapter.policy_config
        self.action_optimizer = torch.optim.AdamW(
            self.trainable_parameters,
            lr=float(policy_cfg.optimizer_lr),
            betas=tuple(policy_cfg.optimizer_betas),
            eps=float(policy_cfg.optimizer_eps),
            weight_decay=float(policy_cfg.optimizer_weight_decay),
        )
        self.action_lr_scheduler = CosineAnnealingWarmupRestarts(
            self.action_optimizer,
            first_cycle_steps=int(policy_cfg.scheduler_decay_steps),
            cycle_mult=1.0,
            max_lr=float(policy_cfg.optimizer_lr),
            min_lr=float(policy_cfg.scheduler_decay_lr),
            warmup_steps=int(policy_cfg.scheduler_warmup_steps),
            gamma=1.0,
        )

        if (
            checkpoint_payload is not None
            and checkpoint_payload.get("action_optimizer") is not None
        ):
            self.cnt_update = int(checkpoint_payload.get("cnt_update", 0))
            self.cnt_batch = int(checkpoint_payload.get("cnt_batch", 0))
            self.cnt_epoch = int(checkpoint_payload.get("cnt_epoch", 0))
            opt_state = checkpoint_payload.get("action_optimizer", None)
            self.action_optimizer.load_state_dict(opt_state)
            optimizer_to(self.action_optimizer, self.device)
            sched_state = checkpoint_payload.get("action_lr_scheduler", None)
            if sched_state is not None:
                self.action_lr_scheduler.load_state_dict(sched_state)
            logger.info(f"Resumed optimizer state from {checkpoint_path}")
        elif checkpoint_payload is not None:
            logger.info(f"Loaded model-only checkpoint from {checkpoint_path}")

        self._model_initialized = True
        if self.main_rank:
            try:
                OmegaConf.save(self.cfg, os.path.join(self.log_dir, "config.yaml"))
            except Exception as exc:
                logger.warning(f"Failed to save config.yaml: {exc}")

    def _ensure_initialized(self) -> None:
        if not self._dataset_initialized:
            self._setup_dataset()
        if not self._model_initialized:
            self._setup_model_optimizer()

    def _prepare_batch(self, batch: Dict[str, Any], include_action: bool) -> Dict[str, Any]:
        assert self.adapter is not None
        assert self.ds_train is not None
        return self.adapter.finetune_batch_to_model_batch(
            batch, dataset=self.ds_train, include_action=include_action
        )

    def _complete_optimizer_step(self) -> None:
        assert self.action_optimizer is not None
        assert self.action_lr_scheduler is not None
        torch.nn.utils.clip_grad_norm_(self.trainable_parameters, max_norm=self.max_grad_norm)
        self.action_optimizer.step()
        self.action_lr_scheduler.step()
        self.action_optimizer.zero_grad(set_to_none=True)
        self.cnt_update += 1

    def _post_optimizer_step(self) -> None:
        if self.main_rank:
            self._maybe_finalize_async_checkpoint_save()
        if (
            self.run_eval
            and self.mode_cfg.eval_interval > 0
            and self.cnt_update > 0
            and self.cnt_update % self.mode_cfg.eval_interval == 0
        ):
            self._run_evaluation()

        final_by_updates = (
            self.mode_cfg.max_epochs <= 0 and self.cnt_update >= self.mode_cfg.max_updates_total
        )
        if (
            self.cnt_update % self.save_model_freq == 0 and self.cnt_update >= self.save_model_start
        ) or final_by_updates:
            self.save_training(self.cnt_update, self.cnt_batch, is_final=final_by_updates)
        if (
            self.save_optimizer_freq > 0
            and self.cnt_update > 0
            and self.cnt_update % self.save_optimizer_freq == 0
        ) or (final_by_updates and self.save_optimizer_on_final):
            self.save_optimizer_checkpoint(
                self.cnt_update, self.cnt_batch, is_final=final_by_updates
            )

    def _maybe_log_progress(self, recent_losses: list[float], start_time: float) -> None:
        if self.cnt_batch % self.log_freq != 0 or not self.main_rank:
            return
        assert self.action_optimizer is not None
        peak_vram = (
            torch.cuda.max_memory_reserved(self.gpu_id) / (1024**3)
            if self.device.type == "cuda"
            else 0.0
        )
        avg_loss = (
            float(np.mean(recent_losses[-self.log_freq :])) if recent_losses else float("nan")
        )
        logger.info(
            f"Batch {self.cnt_batch} Update {self.cnt_update} Epoch {self.cnt_epoch}: "
            f"t {time.time() - start_time:8.3f} | vram {peak_vram:6.3f} | "
            f"loss {avg_loss:8.6f} | lr {self.action_optimizer.param_groups[0]['lr']:.8f}"
        )

    def _run_evaluation(self) -> Dict[str, float]:
        if not self.run_eval or self.val_dataloader is None or self.ds_val is None:
            return {}
        assert self.model is not None
        assert self.base_model is not None
        assert self.adapter is not None

        self.model.eval()
        losses = []
        l1_losses = []
        with torch.inference_mode():
            for idx, batch in enumerate(self.val_dataloader):
                if idx >= self.mode_cfg.eval_batches:
                    break
                processed = self.adapter.finetune_batch_to_model_batch(
                    batch, dataset=self.ds_val, include_action=True
                )
                with torch.autocast(device_type="cuda", dtype=self.amp_dtype, enabled=self.use_amp):
                    loss, _ = self.base_model(processed)
                    pred_norm = self.base_model.predict_action_chunk(
                        {k: v for k, v in processed.items() if k != ACTION}
                    )
                pred = self.adapter.postprocess_action(pred_norm)
                target = self.adapter.postprocess_action(processed[ACTION])
                losses.append(float(loss.detach().cpu().item()))
                l1_losses.append(float(F.l1_loss(pred, target).detach().cpu().item()))

        self.model.train()
        if not losses:
            return {}
        metrics = {"eval loss": float(np.mean(losses)), "eval l1": float(np.mean(l1_losses))}
        logger.info(f"Eval | loss={metrics['eval loss']:.6f} | l1={metrics['eval l1']:.6f}")
        return metrics

    def _maybe_finalize_async_checkpoint_save(self) -> None:
        thread = self._checkpoint_save_thread
        if thread is None or thread.is_alive():
            return
        savepath = self._checkpoint_save_path
        thread.join()
        self._checkpoint_save_thread = None
        self._checkpoint_save_path = ""
        if self._checkpoint_save_error is not None:
            exc = self._checkpoint_save_error
            self._checkpoint_save_error = None
            raise RuntimeError(f"Async checkpoint save failed for {savepath}: {exc}") from exc

    def _wait_for_async_checkpoint_save(self) -> None:
        thread = self._checkpoint_save_thread
        if thread is None:
            return
        savepath = self._checkpoint_save_path
        thread.join()
        self._checkpoint_save_thread = None
        self._checkpoint_save_path = ""
        if self._checkpoint_save_error is not None:
            exc = self._checkpoint_save_error
            self._checkpoint_save_error = None
            raise RuntimeError(f"Async checkpoint save failed for {savepath}: {exc}") from exc

    def _build_checkpoint_payload(
        self, *, cnt_update: int, cnt_batch: int, is_final: bool, include_optimizer: bool
    ) -> dict[str, Any]:
        if self.model is None:
            raise RuntimeError("model is not initialized")
        state_dict = self.model.module.state_dict() if self.multi_gpu else self.model.state_dict()
        return {
            "cnt_update": int(cnt_update),
            "cnt_batch": int(cnt_batch),
            "cnt_epoch": int(self.cnt_epoch),
            "model": _snapshot_to_cpu_tree(state_dict),
            "action_optimizer": (
                _snapshot_to_cpu_tree(self.action_optimizer.state_dict())
                if include_optimizer and self.action_optimizer is not None
                else None
            ),
            "action_lr_scheduler": (
                _snapshot_to_cpu_tree(self.action_lr_scheduler.state_dict())
                if include_optimizer and self.action_lr_scheduler is not None
                else None
            ),
            "is_final": bool(is_final),
            "checkpoint_type": "optimizer" if include_optimizer else "model",
        }

    def _write_checkpoint_payload(
        self, payload: dict[str, Any], savepath: str, *, cnt_update: int, cnt_batch: int
    ) -> None:
        torch.save(payload, savepath)
        logger.info(
            f"Saved checkpoint: {savepath} | update={cnt_update} | batch={cnt_batch} | "
            f"epoch={payload['cnt_epoch']} | checkpoint_type={payload['checkpoint_type']}"
        )

    def _start_async_checkpoint_save(
        self, payload: dict[str, Any], savepath: str, *, cnt_update: int, cnt_batch: int
    ) -> None:
        self._checkpoint_save_error = None
        self._checkpoint_save_path = savepath

        def _worker() -> None:
            try:
                self._write_checkpoint_payload(
                    payload, savepath, cnt_update=cnt_update, cnt_batch=cnt_batch
                )
            except Exception as exc:  # pragma: no cover - surfaced on next join/finalize
                self._checkpoint_save_error = exc

        self._checkpoint_save_thread = threading.Thread(
            target=_worker, name=f"sft-ckpt-save-{cnt_update}", daemon=False
        )
        self._checkpoint_save_thread.start()
        logger.info(
            f"Queued async checkpoint save: {savepath} | update={cnt_update} | batch={cnt_batch} | "
            f"epoch={payload['cnt_epoch']}"
        )

    def save_training(self, cnt_update: int, cnt_batch: int, is_final: bool = False) -> str:
        savepath = os.path.join(self.checkpoint_dir, f"step{cnt_update}.pt")
        use_async_save = self.async_checkpoint_save and not is_final

        if self.multi_gpu:
            import torch.distributed as dist

            if self.main_rank:
                self._wait_for_async_checkpoint_save()
                payload = self._build_checkpoint_payload(
                    cnt_update=cnt_update,
                    cnt_batch=cnt_batch,
                    is_final=is_final,
                    include_optimizer=False,
                )
                if use_async_save:
                    self._start_async_checkpoint_save(
                        payload, savepath, cnt_update=cnt_update, cnt_batch=cnt_batch
                    )
                else:
                    self._write_checkpoint_payload(
                        payload, savepath, cnt_update=cnt_update, cnt_batch=cnt_batch
                    )
            dist.barrier()
        else:
            self._wait_for_async_checkpoint_save()
            payload = self._build_checkpoint_payload(
                cnt_update=cnt_update,
                cnt_batch=cnt_batch,
                is_final=is_final,
                include_optimizer=False,
            )
            if use_async_save:
                self._start_async_checkpoint_save(
                    payload, savepath, cnt_update=cnt_update, cnt_batch=cnt_batch
                )
            else:
                self._write_checkpoint_payload(
                    payload, savepath, cnt_update=cnt_update, cnt_batch=cnt_batch
                )
        self.current_checkpoint_path = savepath
        return savepath if self.main_rank else ""

    def save_optimizer_checkpoint(
        self, cnt_update: int, cnt_batch: int, is_final: bool = False
    ) -> str:
        savepath = os.path.join(self.optimizer_checkpoint_dir, f"step{cnt_update}.pt")

        if self.multi_gpu:
            import torch.distributed as dist

            if self.main_rank:
                self._wait_for_async_checkpoint_save()
                payload = self._build_checkpoint_payload(
                    cnt_update=cnt_update,
                    cnt_batch=cnt_batch,
                    is_final=is_final,
                    include_optimizer=True,
                )
                self._write_checkpoint_payload(
                    payload, savepath, cnt_update=cnt_update, cnt_batch=cnt_batch
                )
            dist.barrier()
        else:
            self._wait_for_async_checkpoint_save()
            payload = self._build_checkpoint_payload(
                cnt_update=cnt_update,
                cnt_batch=cnt_batch,
                is_final=is_final,
                include_optimizer=True,
            )
            self._write_checkpoint_payload(
                payload, savepath, cnt_update=cnt_update, cnt_batch=cnt_batch
            )
        return savepath if self.main_rank else ""

    def _train_updates(self, num_updates: int) -> None:
        assert self.train_dataloader is not None
        assert self.model is not None
        assert self.base_model is not None
        assert self.action_optimizer is not None
        assert self.action_lr_scheduler is not None

        self.model.train()
        self.action_optimizer.zero_grad(set_to_none=True)
        target_update = min(self.cnt_update + int(num_updates), self.mode_cfg.max_updates_total)
        recent_losses: list[float] = []
        start_time = time.time()

        while self.cnt_update < target_update:
            if self.train_sampler is not None:
                self.train_sampler.set_epoch(self.cnt_epoch)
            for batch in self.train_dataloader:
                processed = self._prepare_batch(batch, include_action=True)
                is_grad_step = (self.cnt_batch + 1) % self.grad_accumulation_steps == 0
                sync_ctx = (
                    self.model.no_sync() if (self.multi_gpu and not is_grad_step) else nullcontext()
                )
                with sync_ctx:
                    with torch.autocast(
                        device_type="cuda", dtype=self.amp_dtype, enabled=self.use_amp
                    ):
                        loss, _ = self.model(processed)
                    (loss / self.grad_accumulation_steps).backward()

                recent_losses.append(float(loss.detach().cpu().item()))

                if is_grad_step:
                    self._complete_optimizer_step()
                    self._post_optimizer_step()

                self._maybe_log_progress(recent_losses, start_time)

                self.cnt_batch += 1
                if (
                    self.empty_cache_freq > 0
                    and self.cnt_batch % self.empty_cache_freq == 0
                    and self.device.type == "cuda"
                ):
                    torch.cuda.empty_cache()
                if self.cnt_update >= target_update:
                    return
            self.cnt_epoch += 1

    def _train_epochs(self, num_epochs: int) -> None:
        assert self.train_dataloader is not None
        assert self.model is not None
        assert self.base_model is not None
        assert self.action_optimizer is not None
        assert self.action_lr_scheduler is not None

        self.model.train()
        self.action_optimizer.zero_grad(set_to_none=True)
        target_epoch = self.cnt_epoch + int(num_epochs)
        recent_losses: list[float] = []
        start_time = time.time()

        while self.cnt_epoch < target_epoch:
            if self.train_sampler is not None:
                self.train_sampler.set_epoch(self.cnt_epoch)
            batches_in_pass = len(self.train_dataloader)
            for local_batch_idx, batch in enumerate(self.train_dataloader):
                group_start = (
                    local_batch_idx // self.grad_accumulation_steps
                ) * self.grad_accumulation_steps
                group_end = min(group_start + self.grad_accumulation_steps, batches_in_pass)
                group_size = max(1, group_end - group_start)
                is_grad_step = (local_batch_idx + 1) == group_end
                processed = self._prepare_batch(batch, include_action=True)
                sync_ctx = (
                    self.model.no_sync() if (self.multi_gpu and not is_grad_step) else nullcontext()
                )
                with sync_ctx:
                    with torch.autocast(
                        device_type="cuda", dtype=self.amp_dtype, enabled=self.use_amp
                    ):
                        loss, _ = self.model(processed)
                    (loss / group_size).backward()

                recent_losses.append(float(loss.detach().cpu().item()))

                if is_grad_step:
                    self._complete_optimizer_step()
                    self._post_optimizer_step()

                self._maybe_log_progress(recent_losses, start_time)

                self.cnt_batch += 1
                if (
                    self.empty_cache_freq > 0
                    and self.cnt_batch % self.empty_cache_freq == 0
                    and self.device.type == "cuda"
                ):
                    torch.cuda.empty_cache()

            self.cnt_epoch += 1

    def train_offline(self) -> None:
        self._ensure_initialized()
        if self.mode_cfg.max_epochs > 0:
            remaining_epochs = self.mode_cfg.max_epochs - self.cnt_epoch
            if remaining_epochs <= 0:
                logger.info("Already reached max_epochs, skip offline training.")
                return
            logger.info(f"Offline training: remaining_epochs={remaining_epochs}")
            self._train_epochs(remaining_epochs)
            self.save_training(self.cnt_update, self.cnt_batch, is_final=True)
            return

        remaining = self.mode_cfg.max_updates_total - self.cnt_update
        if remaining <= 0:
            logger.info("Already reached max_updates_total, skip offline training.")
            return
        logger.info(f"Offline training: remaining_updates={remaining}")
        self._train_updates(remaining)

    def close(self, *, destroy_process_group: bool = True) -> None:
        if self.main_rank:
            self._wait_for_async_checkpoint_save()
        if not self.multi_gpu:
            return
        if not destroy_process_group:
            return
        import torch.distributed as dist

        if dist.is_initialized():
            dist.barrier()
            dist.destroy_process_group()
