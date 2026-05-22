"""Notifier factory."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session, sessionmaker

from photofactory.config import AppConfig
from photofactory.notifications.base import CompositeNotifier, Notifier, NullNotifier
from photofactory.notifications.max import MaxNotifier
from photofactory.notifications.pwa import PwaNotifier
from photofactory.notifications.telegram import TelegramNotifier

LOGGER = logging.getLogger(__name__)


def build_notifier(
    config: AppConfig,
    session_factory: sessionmaker[Session] | None = None,
) -> Notifier:
    notifications = config.notifications
    if not notifications.enabled:
        LOGGER.info("Notifications disabled in config")
        return NullNotifier()

    channels: list[Notifier] = []

    if "telegram" in notifications.channels:
        token = notifications.telegram.bot_token.strip()
        chat_id = notifications.telegram.default_chat_id.strip()
        if not token or token.startswith("YOUR_") or "CHANGE_ME" in token:
            LOGGER.warning("Telegram notifier is enabled but bot token is not configured")
        elif not chat_id:
            LOGGER.warning("Telegram notifier is enabled but chat_id is not configured")
        else:
            LOGGER.info("Telegram notifier enabled")
            channels.append(TelegramNotifier(bot_token=token, chat_id=chat_id))

    if "max" in notifications.channels:
        webhook_url = config.notifications.max.webhook_url.strip()
        auth_token = config.notifications.max.auth_token.strip()
        if not webhook_url:
            LOGGER.warning("MAX notifier is enabled but webhook_url is not configured")
        else:
            LOGGER.info("MAX notifier enabled")
            channels.append(MaxNotifier(webhook_url=webhook_url, auth_token=auth_token))

    if "pwa" in notifications.channels or notifications.pwa.enabled:
        private_key = notifications.pwa.vapid_private_key.strip()
        subject = notifications.pwa.vapid_subject.strip()
        if session_factory is None:
            LOGGER.warning("PWA notifier needs database session factory")
        elif not private_key:
            LOGGER.warning("PWA notifier enabled but vapid_private_key is not configured")
        elif not subject:
            LOGGER.warning("PWA notifier enabled but vapid_subject is not configured")
        else:
            LOGGER.info("PWA notifier enabled")
            channels.append(
                PwaNotifier(
                    session_factory=session_factory,
                    vapid_private_key=private_key,
                    vapid_subject=subject,
                )
            )

    if channels:
        return CompositeNotifier(channels)

    LOGGER.info("No supported notification channels configured, using null notifier")
    return NullNotifier()
