"""CLI entrypoint to run FastAPI server."""

from __future__ import annotations

import argparse

import uvicorn

from photofactory.api.app import create_app
from photofactory.config import load_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run photofactory API server.")
    parser.add_argument("--config", default="config.yaml", help="Path to YAML config.")
    parser.add_argument("--reload", action="store_true", help="Enable uvicorn reload mode.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = load_config(args.config)
    app = create_app(config)
    uvicorn.run(app, host=config.api.host, port=config.api.port, reload=args.reload)


if __name__ == "__main__":
    main()
