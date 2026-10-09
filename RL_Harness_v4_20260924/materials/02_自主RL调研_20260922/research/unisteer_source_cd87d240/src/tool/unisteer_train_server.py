from __future__ import annotations

import argparse

from flask import Response
from loguru import logger

from src.tool.unisteer_rl_server import (
    UniSteerRLServerApp,
    _json_response,
    _register_omegaconf_resolvers,
    build_service_from_cli,
)
from src.tool.unisteer_train_service import UniSteerServerConfig, UniSteerTrainService


class UniSteerTrainServerApp(UniSteerRLServerApp):
    def handle_health(self) -> Response:
        return _json_response({"status": "ok", "service": "unisteer_train_server"})

    def handle_status(self) -> Response:
        return _json_response(
            {"status": "ok", "service": "unisteer_train_server", "state": self.service.status()}
        )

    def run(self, host: str = "127.0.0.1", port: int = 9200) -> None:
        logger.info(f"Starting unisteer_train_server on {host}:{port}")
        self.app.run(host=host, port=port, threaded=True)


def main() -> None:
    _register_omegaconf_resolvers()

    parser = argparse.ArgumentParser(description="UniSteer training server")
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
        "[unisteer_train_server] CLI startup "
        f"(host={args.host}, port={args.port}, auto_train={args.auto_train}, "
        f"checkpoint_dir={args.checkpoint_dir})"
    )
    service = build_service_from_cli(
        args, service_cls=UniSteerTrainService, server_config_cls=UniSteerServerConfig
    )
    app = UniSteerTrainServerApp(service)
    logger.info(f"[unisteer_train_server] Starting Flask app on {args.host}:{args.port}")
    app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
