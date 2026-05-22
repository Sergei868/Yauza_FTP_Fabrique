"""CLI entrypoint for batch watcher service."""

from __future__ import annotations

import argparse
import logging

from photofactory.config import load_config
from photofactory.db.session import build_session_factory
from photofactory.notifications.factory import build_notifier
from photofactory.watcher.service import BatchWatcher


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run photofactory batch watcher.")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to YAML config (default: config.yaml).",
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Run a single scan iteration and exit.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = load_config(args.config)
    session_factory = build_session_factory(config)
    notifier = build_notifier(config, session_factory=session_factory)
    watcher = BatchWatcher(config, session_factory=session_factory, notifier=notifier)
    if args.run_once:
        watcher.run_once()
        return
    watcher.run_forever()


if __name__ == "__main__":
    main()
