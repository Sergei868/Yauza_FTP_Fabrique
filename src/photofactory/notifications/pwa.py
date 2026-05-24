"""PWA push notifier adapter."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from pywebpush import WebPushException, webpush
from sqlalchemy.orm import Session, sessionmaker

from photofactory.db.repository import deactivate_push_subscription, list_active_push_subscriptions
from photofactory.notifications.base import BatchNotification

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PwaSendResult:
    sent: int
    failed: int
    deactivated: int


class PwaNotifier:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        vapid_private_key: str,
        vapid_subject: str,
    ) -> None:
        self.session_factory = session_factory
        self.vapid_private_key = vapid_private_key
        self.vapid_subject = vapid_subject

    def notify_batch_finalized(self, payload: BatchNotification) -> None:
        total_mb = round(payload.total_size_bytes / (1024 * 1024))
        body = f"{payload.photographer} {payload.file_count} файлов {total_mb} МБ"
        if payload.broken_files_count > 0:
            body += f" {payload.broken_files_count} битых"
        result = self.send_raw_payload(
            {
                "type": "batch_finalized",
                "title": "Bildboard Yauza",
                "body": body,
                "batch_id": payload.batch_id,
                "batch_key": payload.batch_key,
                "url": "/bild",
            }
        )
        LOGGER.info(
            "PWA push result sent=%d failed=%d deactivated=%d",
            result.sent,
            result.failed,
            result.deactivated,
        )

    def send_raw_payload(self, payload: dict[str, object]) -> PwaSendResult:
        body = json.dumps(payload, ensure_ascii=True)
        sent = 0
        failed = 0
        deactivated = 0
        with self.session_factory() as session:
            subscriptions = list_active_push_subscriptions(session)
            for item in subscriptions:
                subscription_info = {
                    "endpoint": item.endpoint,
                    "keys": {
                        "p256dh": item.p256dh,
                        "auth": item.auth,
                    },
                }
                try:
                    webpush(
                        subscription_info=subscription_info,
                        data=body,
                        vapid_private_key=self.vapid_private_key,
                        vapid_claims={"sub": self.vapid_subject},
                    )
                    sent += 1
                except WebPushException as exc:
                    failed += 1
                    status_code = getattr(getattr(exc, "response", None), "status_code", None)
                    if status_code in (404, 410):
                        deactivate_push_subscription(session, item.endpoint)
                        deactivated += 1
                    LOGGER.warning("PWA push failed endpoint=%s status=%s", item.endpoint, status_code)
            session.commit()
        return PwaSendResult(sent=sent, failed=failed, deactivated=deactivated)
