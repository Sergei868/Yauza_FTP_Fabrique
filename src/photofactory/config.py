"""Configuration loading for photofactory services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class PathsConfig:
    incoming: Path
    originals: Path
    backup: Path
    default_event_id: str
    default_session_id: str


@dataclass(frozen=True)
class BatchConfig:
    silence_seconds: int
    allowed_extensions: tuple[str, ...]
    poll_seconds: int
    write_backup_copy: bool


@dataclass(frozen=True)
class DatabaseConfig:
    url: str


@dataclass(frozen=True)
class ApiConfig:
    host: str
    port: int


@dataclass(frozen=True)
class AuthConfig:
    username: str
    password: str
    admin_username: str
    admin_password: str
    jwt_secret: str
    token_ttl_minutes: int


@dataclass(frozen=True)
class AppMetaConfig:
    name: str
    env: str
    base_url: str


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    default_chat_id: str


@dataclass(frozen=True)
class MaxConfig:
    webhook_url: str
    auth_token: str


@dataclass(frozen=True)
class PwaConfig:
    enabled: bool
    vapid_public_key: str
    vapid_private_key: str
    vapid_subject: str


@dataclass(frozen=True)
class NotificationsConfig:
    enabled: bool
    channels: tuple[str, ...]
    telegram: TelegramConfig
    max: MaxConfig
    pwa: PwaConfig


@dataclass(frozen=True)
class YandexDiskConfig:
    enabled: bool
    oauth_token: str
    remote_base_path: str


@dataclass(frozen=True)
class AppConfig:
    app: AppMetaConfig
    paths: PathsConfig
    batch: BatchConfig
    database: DatabaseConfig
    api: ApiConfig
    auth: AuthConfig
    notifications: NotificationsConfig
    yandex_disk: YandexDiskConfig


def _normalize_extensions(extensions: list[str]) -> tuple[str, ...]:
    normalized = []
    for ext in extensions:
        item = ext.lower().strip()
        if not item.startswith("."):
            item = f".{item}"
        normalized.append(item)
    return tuple(normalized)


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as file_handle:
        raw = yaml.safe_load(file_handle) or {}

    paths = raw.get("paths", {})
    batch = raw.get("batch", {})
    database = raw.get("database", {})
    api = raw.get("api", {})
    auth = raw.get("auth", {})
    app = raw.get("app", {})
    notifications = raw.get("notifications", {})
    yandex_disk = raw.get("yandex_disk", {})
    telegram = notifications.get("telegram", {})
    max_cfg = notifications.get("max", {})
    pwa_cfg = notifications.get("pwa", {})
    app_config = AppMetaConfig(
        name=str(app.get("name", "yauza-photofactory")),
        env=str(app.get("env", "development")),
        base_url=str(app.get("base_url", "http://127.0.0.1:8000")),
    )

    paths_config = PathsConfig(
        incoming=Path(paths["incoming"]),
        originals=Path(paths["originals"]),
        backup=Path(paths["backup"]),
        default_event_id=paths.get("default_event_id", "default"),
        default_session_id=paths.get("default_session_id", "unnamed"),
    )
    batch_config = BatchConfig(
        silence_seconds=int(batch.get("silence_seconds", 60)),
        allowed_extensions=_normalize_extensions(batch.get("allowed_extensions", [".jpg", ".jpeg"])),
        poll_seconds=int(batch.get("poll_seconds", 5)),
        write_backup_copy=bool(batch.get("write_backup_copy", True)),
    )
    database_config = DatabaseConfig(
        url=str(database.get("url", "postgresql://photofactory:CHANGE_ME@127.0.0.1:5432/photofactory"))
    )
    api_config = ApiConfig(
        host=str(api.get("host", "127.0.0.1")),
        port=int(api.get("port", 8000)),
    )
    auth_config = AuthConfig(
        username=str(auth.get("username", "bild")),
        password=str(auth.get("password", "CHANGE_ME")),
        admin_username=str(auth.get("admin_username", "admin")),
        admin_password=str(auth.get("admin_password", "CHANGE_ME_ADMIN")),
        jwt_secret=str(auth.get("jwt_secret", "CHANGE_ME_JWT_SECRET")),
        token_ttl_minutes=int(auth.get("token_ttl_minutes", 120)),
    )
    notifications_config = NotificationsConfig(
        enabled=bool(notifications.get("enabled", False)),
        channels=tuple(str(item).strip().lower() for item in notifications.get("channels", ["telegram"])),
        telegram=TelegramConfig(
            bot_token=str(telegram.get("bot_token", "")),
            default_chat_id=str(telegram.get("default_chat_id", "")),
        ),
        max=MaxConfig(
            webhook_url=str(max_cfg.get("webhook_url", "")),
            auth_token=str(max_cfg.get("auth_token", "")),
        ),
        pwa=PwaConfig(
            enabled=bool(pwa_cfg.get("enabled", False)),
            vapid_public_key=str(pwa_cfg.get("vapid_public_key", "")),
            vapid_private_key=str(pwa_cfg.get("vapid_private_key", "")),
            vapid_subject=str(pwa_cfg.get("vapid_subject", "")),
        ),
    )
    yandex_disk_config = YandexDiskConfig(
        enabled=bool(yandex_disk.get("enabled", False)),
        oauth_token=str(yandex_disk.get("oauth_token", "")),
        remote_base_path=str(yandex_disk.get("remote_base_path", "/YauzaPhotofactory")),
    )

    return AppConfig(
        app=app_config,
        paths=paths_config,
        batch=batch_config,
        database=database_config,
        api=api_config,
        auth=auth_config,
        notifications=notifications_config,
        yandex_disk=yandex_disk_config,
    )
