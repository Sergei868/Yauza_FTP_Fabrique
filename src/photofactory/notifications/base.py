"""Base notification contracts."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Protocol

LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True)
class BatchNotification:
    batch_key: str
    batch_id: str | None
    photographer: str
    file_count: int
    broken_files_count: int
    total_size_bytes: int
    base_url: str


class Notifier(Protocol):
    def notify_batch_finalized(self, payload: BatchNotification) -> None:
        """Send notification about finalized batch."""


class NullNotifier:
    def notify_batch_finalized(self, payload: BatchNotification) -> None:
        _ = payload


class CompositeNotifier:
    def __init__(self, notifiers: list[Notifier]) -> None:
        self.notifiers = notifiers

    def notify_batch_finalized(self, payload: BatchNotification) -> None:
        for notifier in self.notifiers:
            try:
                notifier.notify_batch_finalized(payload)
            except Exception:
                # Do not break pipeline because one channel failed.
                LOGGER.exception("Notifier channel failed")
                continue
