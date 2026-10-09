from __future__ import annotations

import argparse
from pathlib import Path

from loguru import logger
from omegaconf import OmegaConf, open_dict

from src.trainer.SFTTrainer import SFTTrainer


def _existing_path(value: str, *, name: str) -> str:
    path = Path(value).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"{name} not found: {path}")
    return str(path)


def build_config(args: argparse.Namespace):
    config_path = _existing_path(args.config, name="config")
    data_root = _existing_path(args.data_root, name="data root")
    base_model = _existing_path(args.base_model, name="base model")
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    cfg = OmegaConf.load(config_path)
    with open_dict(cfg):
        cfg.data.finetune.data_path = data_root
        cfg.data.finetune.stats_data_path = data_root
        cfg.init_ckpt = base_model
        cfg.log_dir = str(output_dir)
        cfg.checkpoint_dir = str(output_dir / "checkpoint")
        cfg.optimizer_checkpoint_dir = str(output_dir / "optimizer_checkpoint")
        cfg.gpu_id = int(args.gpu_id)
        if args.tokenizer:
            cfg.openpi_tokenizer_path = _existing_path(args.tokenizer, name="tokenizer")
        if args.max_updates is not None:
            cfg.max_updates_total = int(args.max_updates)
            cfg.max_epochs = 0
        if args.num_workers is not None:
            cfg.num_workers = int(args.num_workers)
    return cfg


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local OpenPI warmup SFT")
    parser.add_argument("--config", required=True)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--base-model", required=True)
    parser.add_argument("--tokenizer", default=None)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--gpu-id", type=int, default=0)
    parser.add_argument("--max-updates", type=int, default=None)
    parser.add_argument("--num-workers", type=int, default=None)
    args = parser.parse_args()

    cfg = build_config(args)
    logger.info(
        "Starting warmup SFT "
        f"policy={cfg.openpi_policy_type} data={cfg.data.finetune.data_path} "
        f"output={cfg.log_dir}"
    )
    trainer = SFTTrainer(cfg)
    try:
        trainer.train_offline()
    finally:
        trainer.close()


if __name__ == "__main__":
    main()
