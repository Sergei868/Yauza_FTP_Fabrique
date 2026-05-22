"""MAX notifier adapter.

The implementation uses configurable webhook endpoint as transport.
"""

from __future__ import annotations

import httpx

from photofactory.notifications.base import BatchNotification


class MaxNotifier:
    def __init__(self, webhook_url: str, auth_token: str = "", timeout_seconds: int = 10) -> None:
        self.webhook_url = webhook_url
        self.auth_token = auth_token
        self.timeout_seconds = timeout_seconds

    def notify_batch_finalized(self, payload: BatchNotification) -> None:
        batch_ref = payload.batch_id or payload.batch_key
        details_url = f"{payload.base_url.rstrip('/')}/api/batches/{batch_ref}"
        body = {
            "event": "batch_finalized",
            "batch_key": payload.batch_key,
            "batch_id": payload.batch_id,
            "photographer": payload.photographer,
            "file_count": payload.file_count,
            "total_size_bytes": payload.total_size_bytes,
            "details_url": details_url,
        }
        headers: dict[str, str] = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        response = httpx.post(
            self.webhook_url,
            json=body,
            headers=headers,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
