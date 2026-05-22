"""Telegram notifier adapter."""

from __future__ import annotations

import httpx

from photofactory.notifications.base import BatchNotification


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str, timeout_seconds: int = 10) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.timeout_seconds = timeout_seconds

    def notify_batch_finalized(self, payload: BatchNotification) -> None:
        batch_ref = payload.batch_id or payload.batch_key
        details_url = f"{payload.base_url.rstrip('/')}/api/batches/{batch_ref}"
        text = (
            f"📸 Новая пачка принята\n"
            f"Фотограф: {payload.photographer}\n"
            f"Пачка: {payload.batch_key}\n"
            f"Фото: {payload.file_count}\n"
            f"Размер: {payload.total_size_bytes} байт\n"
            f"Открыть: {details_url}"
        )
        response = httpx.post(
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            data={
                "chat_id": self.chat_id,
                "text": text,
                "disable_web_page_preview": "true",
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
