from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Sequence

from loguru import logger

from src.tool.unisteer_rl_server import (
    UniSteerRLServerConfig,
    UniSteerRLTrainService,
    _log_noise_target_range,
)
from src.trainer.UniSteerTrainer import SFTReplayBuffer, UniSteerTrainer


def _server_section_getter(cfg: Any):
    section = (
        cfg.get("unisteer_server", {})
        if isinstance(cfg, dict)
        else getattr(cfg, "unisteer_server", {})
    )
    if isinstance(section, dict):
        return section.get
    return lambda key, default=None: getattr(section, key, default)


@dataclass
class UniSteerServerConfig(UniSteerRLServerConfig):
    two_stage_order: str = "sft_then_rl"
    sft_buffer_capacity: int = 10000
    sft_multi_grad_step: int = 10
    sft_min_updates: int = 10
    actor_sft_batch_size: int = 256
    actor_sft_log_every: int = 20
    actor_lambda_actor_prior: float = 1e-2
    actor_lambda_norm: float = 1e-4
    add_human_inverse_to_rl_buffer: bool = False

    @classmethod
    def from_cfg(
        cls, cfg: Any, *, checkpoint_dir: Optional[str] = None, auto_train: Optional[bool] = None
    ) -> "UniSteerServerConfig":
        base = UniSteerRLServerConfig.from_cfg(
            cfg, checkpoint_dir=checkpoint_dir, auto_train=auto_train
        )
        get = _server_section_getter(cfg)

        two_stage_order = str(get("two_stage_order", "sft_then_rl")).strip() or "sft_then_rl"
        if two_stage_order not in {"rl_then_sft", "sft_then_rl"}:
            raise ValueError(
                f"Unsupported unisteer_server.two_stage_order={two_stage_order!r}; "
                "expected 'rl_then_sft' or 'sft_then_rl'"
            )

        return cls(
            **asdict(base),
            two_stage_order=two_stage_order,
            sft_buffer_capacity=int(get("sft_buffer_capacity", 10000)),
            sft_multi_grad_step=int(get("sft_multi_grad_step", 10)),
            sft_min_updates=int(get("sft_min_updates", 10)),
            actor_sft_batch_size=int(get("actor_sft_batch_size", 256)),
            actor_sft_log_every=int(get("actor_sft_log_every", 20)),
            actor_lambda_actor_prior=float(get("actor_lambda_actor_prior", 1e-2)),
            actor_lambda_norm=float(get("actor_lambda_norm", 1e-4)),
            add_human_inverse_to_rl_buffer=bool(get("add_human_inverse_to_rl_buffer", False)),
        )


class UniSteerTrainService(UniSteerRLTrainService):
    """Online UniSteer trainer: UniSteer RL core plus human inverse-SFT."""

    def __init__(
        self,
        cfg: Any,
        *,
        server_cfg: UniSteerRLServerConfig,
        inference_agent: Optional["InferenceAgent"] = None,
        trainer: Optional[Any] = None,
    ):
        super().__init__(
            cfg, server_cfg=server_cfg, inference_agent=inference_agent, trainer=trainer
        )
        self.unisteer_trainer = UniSteerTrainer(
            cfg,
            server_cfg=server_cfg,
            trainer=self.trainer,
            agent=self.agent,
            checkpoint_path_getter=lambda: self.last_checkpoint_path,
        )
        self.sft_buffer = self.unisteer_trainer.sft_buffer
        self.human_sft_source_buffer = self.unisteer_trainer.human_sft_source_buffer

    def _sft_image_cfg(self) -> Dict[str, Any]:
        return self.unisteer_trainer.sft_image_cfg()

    def _image_aug_cfg(self) -> Any:
        return self.unisteer_trainer.image_aug_cfg()

    def _dynamic_sft_aug_enabled(self) -> bool:
        return self.unisteer_trainer.dynamic_sft_aug_enabled()

    def _dynamic_sft_aug_num_samples(self) -> int:
        return self.unisteer_trainer.dynamic_sft_aug_num_samples()

    def _dynamic_sft_aug_buffer_size(self) -> int:
        return self.unisteer_trainer.dynamic_sft_aug_buffer_size()

    def _build_human_rl_actor_targets(self, human_dirs: Sequence[Path]) -> Dict[str, Any]:
        return self.unisteer_trainer.build_human_rl_actor_targets(human_dirs)

    def _build_human_sft_original_actor_targets(self, human_dirs: Sequence[Path]) -> Dict[str, Any]:
        return self.unisteer_trainer.build_human_sft_original_actor_targets(human_dirs)

    def _build_human_sft_actor_targets(self, human_dirs: Sequence[Path]) -> Dict[str, Any]:
        return self.unisteer_trainer.build_human_sft_actor_targets(human_dirs)

    def _build_dynamic_sft_actor_targets(self) -> Dict[str, Any]:
        return self.unisteer_trainer.build_dynamic_sft_actor_targets()

    def _ingest_sft_entries(
        self, entries: Sequence[Dict[str, Any]], *, target_buffer: Optional[SFTReplayBuffer] = None
    ) -> int:
        return self.unisteer_trainer.ingest_sft_entries(entries, target_buffer=target_buffer)

    def _bootstrap_human_sft(self, human_dirs: Sequence[Path]) -> Dict[str, Any]:
        if not human_dirs:
            return {
                "num_human_trajectories": 0,
                "num_sft_entries": 0,
                "sft_buffer_size": int(self.sft_buffer.size),
            }
        if int(self.sft_buffer.size) != 0:
            raise RuntimeError(
                "Human SFT bootstrap requires an empty SFT buffer, got "
                f"size={int(self.sft_buffer.size)}"
            )

        if self._dynamic_sft_aug_enabled():
            self.human_sft_source_buffer.add_traj_dirs(
                human_dirs, max_trajectories=self._dynamic_sft_aug_buffer_size()
            )
            target_result = self._build_human_sft_original_actor_targets(human_dirs)
        else:
            target_result = self._build_human_sft_actor_targets(human_dirs)

        num_human_chunks = int(target_result.get("num_human_samples", 0))
        num_target_views = int(target_result.get("num_target_views", num_human_chunks))
        target_entries = target_result.pop("target_entries", None)
        if not isinstance(target_entries, list):
            raise TypeError(
                "Human SFT bootstrap target construction must return in-memory target_entries"
            )
        _log_noise_target_range(target_entries, tag="[unisteer_train_server] bootstrap inverse")
        num_ingested = self._ingest_sft_entries(target_entries)
        if num_ingested != num_target_views:
            raise RuntimeError(
                "Human SFT bootstrap ingest mismatch: "
                f"human_chunks={num_human_chunks}, target_views={num_target_views}, ingested={num_ingested}"
            )

        return {
            "num_human_trajectories": int(len(human_dirs)),
            "num_human_chunks": num_human_chunks,
            "num_sft_entries": int(num_ingested),
            "sft_buffer_size": int(self.sft_buffer.size),
        }

    def _build_human_episode_payloads_from_target_entries(
        self, target_entries: Sequence[Dict[str, Any]], *, request_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        return self.unisteer_trainer.build_human_episode_payloads_from_target_entries(
            target_entries, request_id=request_id
        )

    def _run_sft_updates(
        self, num_updates: int, *, source_buffer: Optional[SFTReplayBuffer] = None
    ) -> Dict[str, Any]:
        return self.unisteer_trainer.run_sft_updates(num_updates, source_buffer=source_buffer)

    def train_mixed_rollout(
        self,
        *,
        model_traj_dirs: List[str],
        human_traj_dirs: List[str],
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        model_dirs = self._normalize_traj_dirs(model_traj_dirs)
        human_dirs = self._normalize_traj_dirs(human_traj_dirs)
        if not model_dirs and not human_dirs:
            raise ValueError("train_mixed_rollout requires at least one model or human trajectory")

        rollout_results: List[Dict[str, Any]] = []
        human_rollout_results: List[Dict[str, Any]] = []
        final_train_metrics: Optional[Dict[str, Any]] = None
        actor_target_result: Optional[Dict[str, Any]] = None
        human_rl_target_result: Optional[Dict[str, Any]] = None
        actor_sft_result: Optional[Dict[str, Any]] = None
        rl_update_result: Optional[Dict[str, Any]] = None
        sft_training_buffer: Optional[SFTReplayBuffer] = None
        trained_any = False
        num_model_chunks = 0
        num_human_rl_chunks = 0
        num_human_sft_chunks = 0
        num_new_human_sft_chunks = 0
        num_target_views = 0
        sft_target_future: Optional[Future] = None
        sft_target_executor: Optional[ThreadPoolExecutor] = None
        dynamic_sft_aug_enabled = self._dynamic_sft_aug_enabled()
        add_human_inverse_to_rl_buffer = bool(self.server_cfg.add_human_inverse_to_rl_buffer)
        for rollout_idx, rollout_dir in enumerate(model_dirs):
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

        def build_sft_targets() -> Dict[str, Any]:
            if dynamic_sft_aug_enabled:
                original_target_result = None
                if human_dirs:
                    original_target_result = self._build_human_sft_original_actor_targets(
                        human_dirs
                    )
                dynamic_target_result = self._build_dynamic_sft_actor_targets()
                return {
                    "mode": "dynamic_aug",
                    "original_target_result": original_target_result,
                    "dynamic_target_result": dynamic_target_result,
                    "human_sft_source_trajectories": int(self.human_sft_source_buffer.size),
                    "dynamic_aug_buffer_size": int(self._dynamic_sft_aug_buffer_size()),
                    "dynamic_aug_num_samples": int(self._dynamic_sft_aug_num_samples()),
                }
            return {
                "mode": "static",
                "target_result": self._build_human_sft_actor_targets(human_dirs),
            }

        def process_sft_target_result(result: Dict[str, Any]) -> None:
            nonlocal actor_target_result
            nonlocal num_human_sft_chunks
            nonlocal num_new_human_sft_chunks
            nonlocal num_target_views
            nonlocal sft_training_buffer

            mode = str(result.get("mode", "static"))
            if mode == "dynamic_aug":
                original_target_result = result.get("original_target_result")
                if original_target_result is not None:
                    if not isinstance(original_target_result, dict):
                        raise TypeError(
                            "dynamic_aug original target construction did not return original_target_result"
                        )
                    original_chunks = int(original_target_result.get("num_human_samples", 0))
                    num_new_human_sft_chunks = int(original_chunks)
                    original_views = int(
                        original_target_result.get("num_target_views", original_chunks)
                    )
                    original_target_entries = original_target_result.pop("target_entries", None)
                    if not isinstance(original_target_entries, list):
                        raise TypeError(
                            "dynamic_aug original target construction must return in-memory target_entries"
                        )
                    num_ingested_original = self._ingest_sft_entries(original_target_entries)
                    if num_ingested_original != original_views:
                        raise RuntimeError(
                            f"Original SFT target ingest mismatch: built_views={original_views} "
                            f"base_human_chunks={original_chunks} ingested={num_ingested_original}"
                        )

                dynamic_target_result = result.get("dynamic_target_result")
                if not isinstance(dynamic_target_result, dict):
                    raise TypeError(
                        "dynamic_aug target construction did not return dynamic_target_result"
                    )
                num_human_sft_chunks = int(dynamic_target_result.get("num_human_samples", 0))
                num_target_views = int(
                    dynamic_target_result.get("num_target_views", num_human_sft_chunks)
                )
                dynamic_target_entries = dynamic_target_result.pop("target_entries", None)
                if not isinstance(dynamic_target_entries, list):
                    raise TypeError(
                        "dynamic_aug target construction must return in-memory target_entries"
                    )
                _log_noise_target_range(
                    dynamic_target_entries, tag="[unisteer_rl_server] dynamic_aug inverse"
                )
                sft_training_buffer = SFTReplayBuffer(max(1, num_target_views))
                num_ingested_dynamic = self._ingest_sft_entries(
                    dynamic_target_entries, target_buffer=sft_training_buffer
                )
                if num_ingested_dynamic != num_target_views:
                    raise RuntimeError(
                        f"Dynamic SFT target ingest mismatch: built_views={num_target_views} "
                        f"base_human_chunks={num_human_sft_chunks} ingested={num_ingested_dynamic}"
                    )
                dynamic_target_summary = dict(dynamic_target_result)
                actor_target_result = {
                    **result,
                    "dynamic_target_result": dynamic_target_summary,
                    "transient_sft_buffer_size": int(sft_training_buffer.size),
                }
                return

            if mode != "static":
                raise ValueError(f"Unsupported SFT target result mode: {mode}")
            static_target_result = result.get("target_result")
            if not isinstance(static_target_result, dict):
                raise TypeError("static target construction did not return target_result")
            num_human_sft_chunks = int(static_target_result.get("num_human_samples", 0))
            num_new_human_sft_chunks = int(num_human_sft_chunks)
            num_target_views = int(
                static_target_result.get("num_target_views", num_human_sft_chunks)
            )
            static_target_entries = static_target_result.pop("target_entries", None)
            if not isinstance(static_target_entries, list):
                raise TypeError("static target construction must return in-memory target_entries")
            num_ingested_sft = self._ingest_sft_entries(static_target_entries)
            if num_ingested_sft != num_target_views:
                raise RuntimeError(
                    f"SFT target ingest mismatch: built_views={num_target_views} "
                    f"base_human_chunks={num_human_sft_chunks} ingested={num_ingested_sft}"
                )
            actor_target_result = static_target_result

        if human_dirs:
            if add_human_inverse_to_rl_buffer:
                human_rl_target_result = self._build_human_rl_actor_targets(human_dirs)
                expected_human_rl_chunks = int(human_rl_target_result.get("num_human_samples", 0))
                expected_human_rl_views = int(
                    human_rl_target_result.get("num_target_views", expected_human_rl_chunks)
                )
                if expected_human_rl_views != expected_human_rl_chunks:
                    raise RuntimeError(
                        f"Human RL inverse must be original-only: chunks={expected_human_rl_chunks} "
                        f"views={expected_human_rl_views}"
                    )

                human_rl_target_entries = human_rl_target_result.pop("target_entries", None)
                if not isinstance(human_rl_target_entries, list):
                    raise TypeError(
                        "human RL inverse construction must return in-memory target_entries"
                    )
                human_episode_payloads = self._build_human_episode_payloads_from_target_entries(
                    human_rl_target_entries, request_id=request_id
                )
                num_human_rl_chunks = sum(
                    int(len(payload["transitions"])) for payload in human_episode_payloads
                )
                if num_human_rl_chunks != expected_human_rl_chunks:
                    raise RuntimeError(
                        f"Human RL transition count mismatch: inverse_chunks={expected_human_rl_chunks} "
                        f"rl_transitions={num_human_rl_chunks}"
                    )
                for payload in human_episode_payloads:
                    payload["train_now"] = False
                    payload["save_checkpoint"] = False
                    result = self.ingest_episode(payload)
                    human_rollout_results.append(
                        {"episode_id": payload["episode_id"], "result": result}
                    )
            else:
                human_rl_target_result = {
                    "enabled": False,
                    "skipped": True,
                    "reason": "unisteer_server.add_human_inverse_to_rl_buffer=false",
                    "num_human_samples": 0,
                    "num_target_views": 0,
                }

            if dynamic_sft_aug_enabled:
                dynamic_aug_buffer_size = self._dynamic_sft_aug_buffer_size()
                num_added_sources, num_evicted_sources = self.human_sft_source_buffer.add_traj_dirs(
                    human_dirs, max_trajectories=dynamic_aug_buffer_size
                )
                logger.info(
                    f"[unisteer_rl_server] dynamic_aug source buffer add={num_added_sources} "
                    f"evict={num_evicted_sources} capacity={dynamic_aug_buffer_size} "
                    f"total_trajectories={self.human_sft_source_buffer.size}"
                )

        should_build_sft_targets = bool(human_dirs)
        if dynamic_sft_aug_enabled and self.human_sft_source_buffer.size > 0:
            should_build_sft_targets = True
        if should_build_sft_targets:
            use_async_sft_target_build = self.server_cfg.two_stage_order != "sft_then_rl"
            if use_async_sft_target_build:
                sft_target_executor = ThreadPoolExecutor(max_workers=1)
                sft_target_future = sft_target_executor.submit(build_sft_targets)
            else:
                process_sft_target_result(build_sft_targets())

        num_rl_chunks = int(num_model_chunks + num_human_rl_chunks)

        def _finalize_sft_targets() -> None:
            nonlocal sft_target_future, sft_target_executor
            sft_error: Optional[BaseException] = None
            if sft_target_future is not None:
                try:
                    sft_target_result = sft_target_future.result()
                except BaseException as exc:
                    sft_error = exc
                finally:
                    assert sft_target_executor is not None
                    sft_target_executor.shutdown(wait=True)
                if sft_error is None:
                    process_sft_target_result(sft_target_result)
                sft_target_future = None
                sft_target_executor = None
            if sft_error is not None:
                raise sft_error

        def _run_sft_stage() -> None:
            nonlocal actor_sft_result, final_train_metrics, trained_any
            sft_anchor_chunks = int(
                num_new_human_sft_chunks if human_dirs else num_human_sft_chunks
            )
            active_sft_buffer = sft_training_buffer or self.sft_buffer
            if self.server_cfg.auto_train and sft_anchor_chunks > 0 and active_sft_buffer.size > 0:
                num_sft_updates = max(
                    1, sft_anchor_chunks * int(self.server_cfg.sft_multi_grad_step)
                )
                actor_sft_result = self._run_sft_updates(
                    num_sft_updates, source_buffer=active_sft_buffer
                )
                actor_sft_result.update(
                    {
                        "sft_anchor_chunks": int(sft_anchor_chunks),
                        "num_new_human_sft_chunks": int(num_new_human_sft_chunks),
                        "num_human_sft_chunks": int(num_human_sft_chunks),
                        "source_buffer_size": int(active_sft_buffer.size),
                    }
                )
                final_train_metrics = actor_sft_result.get("train_metrics") or final_train_metrics
                trained_any = True

        def _run_rl_stage() -> None:
            nonlocal rl_update_result, final_train_metrics, trained_any
            rl_error: Optional[BaseException] = None
            try:
                if (
                    self.server_cfg.auto_train
                    and num_rl_chunks > 0
                    and int(self.server_cfg.multi_grad_step) > 0
                    and self._trajectory_warmup_complete()
                    and self.trainer.ready()
                ):
                    num_rl_updates = self._default_rollout_num_updates(
                        num_transitions=num_rl_chunks
                    )
                    rl_update_result = {
                        "num_updates": int(num_rl_updates),
                        "num_rl_chunks": int(num_rl_chunks),
                        "train_metrics": self._run_updates(
                            num_rl_updates, progress_label="unisteer"
                        ),
                    }
                    final_train_metrics = (
                        rl_update_result.get("train_metrics") or final_train_metrics
                    )
                    trained_any = True
            except BaseException as exc:
                rl_error = exc
            if rl_error is not None:
                raise rl_error

        if self.server_cfg.two_stage_order == "sft_then_rl":
            _finalize_sft_targets()
            _run_sft_stage()
            _run_rl_stage()
        else:
            _run_rl_stage()
            _finalize_sft_targets()
            _run_sft_stage()

        sft_anchor_chunks = int(num_new_human_sft_chunks if human_dirs else num_human_sft_chunks)
        final_checkpoint: Optional[Dict[str, Any]] = None
        final_infer_reload: Optional[Dict[str, Any]] = None
        if self.server_cfg.auto_train and trained_any:
            checkpoint_tag = str(request_id or f"mixed_{int(time.time())}")
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
            "num_human_trajectories": len(human_dirs),
            "num_model_chunks": int(num_model_chunks),
            "num_human_chunks": int(num_human_sft_chunks),
            "num_new_human_sft_chunks": int(num_new_human_sft_chunks),
            "num_human_sft_chunks": int(num_human_sft_chunks),
            "num_sft_anchor_chunks": int(sft_anchor_chunks),
            "num_human_sft_target_views": int(num_target_views),
            "num_human_rl_chunks": int(num_human_rl_chunks),
            "add_human_inverse_to_rl_buffer": bool(add_human_inverse_to_rl_buffer),
            "two_stage_order": str(self.server_cfg.two_stage_order),
            "dynamic_sft_aug_enabled": bool(dynamic_sft_aug_enabled),
            "human_sft_source_trajectories": int(self.human_sft_source_buffer.size),
            "dynamic_aug_buffer_size": int(self._dynamic_sft_aug_buffer_size()),
            "rollouts": rollout_results,
            "human_rollouts": human_rollout_results,
            "human_rl_target_result": human_rl_target_result,
            "actor_target_result": actor_target_result,
            "rl_update_result": rl_update_result,
            "actor_sft_result": actor_sft_result,
            "checkpoint": final_checkpoint,
            "infer_reload": final_infer_reload,
            "train_metrics": final_train_metrics,
        }

    def status(self) -> Dict[str, Any]:
        status = super().status()
        status.update(
            {
                "sft_buffer_size": int(self.sft_buffer.size),
                "human_sft_source_trajectories": int(self.human_sft_source_buffer.size),
                "dynamic_aug_buffer_size": int(self._dynamic_sft_aug_buffer_size()),
            }
        )
        return status


try:
    from src.agent.inference_agent import InferenceAgent
except Exception:  # pragma: no cover
    InferenceAgent = Any
