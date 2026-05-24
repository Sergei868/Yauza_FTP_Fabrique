"""Incoming folder watcher and batch finalization service."""

from __future__ import annotations

from dataclasses import replace
import json
import logging
import os
import shutil
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from photofactory.config import AppConfig
from photofactory.db.repository import (
    get_archive_retention_hours,
    get_batch_photos,
    get_photographer_by_id,
    list_batches_for_archive_cleanup,
    list_batches_for_archive_state_sync,
    mark_batch_archived_deleted,
    mark_batch_downloaded,
    mark_batch_removed_from_incoming,
    create_batch_with_photos,
    create_in_app_batch_notification,
    get_app_setting,
)
from photofactory.notifications.base import BatchNotification, Notifier, NullNotifier
from photofactory.storage.yandex_disk import YandexDiskUploader

LOGGER = logging.getLogger(__name__)
SETTING_YADISK_OAUTH_TOKEN = "yandex_disk.oauth_token.override"
SETTING_YADISK_REMOTE_BASE = "yandex_disk.remote_base_path.override"


@dataclass(frozen=True)
class FileEntry:
    path: Path
    mtime: float
    mtime_ns: int
    size: int


class BatchWatcher:
    """Scans incoming folders and finalizes batches after silence timeout."""

    def __init__(
        self,
        config: AppConfig,
        session_factory: sessionmaker[Session] | None = None,
        notifier: Notifier | None = None,
    ) -> None:
        self.config = config
        self.session_factory = session_factory
        self.notifier = notifier or NullNotifier()

    def run_forever(self) -> None:
        self._ensure_directories()
        LOGGER.info(
            "Watcher started: incoming=%s silence=%ss poll=%ss",
            self.config.paths.incoming,
            self.config.batch.silence_seconds,
            self.config.batch.poll_seconds,
        )
        while True:
            self.run_once()
            time.sleep(self.config.batch.poll_seconds)

    def run_once(self) -> None:
        incoming_root = self.config.paths.incoming
        photographer_dirs = [item for item in incoming_root.iterdir() if item.is_dir()]
        for photographer_dir in sorted(photographer_dirs, key=lambda item: item.name.lower()):
            entries = self._collect_supported_files(photographer_dir)
            if not entries:
                continue
            cutoff_ns = self._load_last_processed_mtime_ns(photographer_dir.name)
            pending_entries = [entry for entry in entries if entry.mtime_ns > cutoff_ns]
            if not pending_entries:
                continue
            newest_mtime = max(entry.mtime for entry in pending_entries)
            age_seconds = time.time() - newest_mtime
            if age_seconds < self.config.batch.silence_seconds:
                continue
            last_processed_ns = self._finalize_batch(photographer_dir, pending_entries, int(age_seconds))
            if last_processed_ns > cutoff_ns:
                self._store_last_processed_mtime_ns(photographer_dir.name, last_processed_ns)
        self._run_archive_maintenance()

    def _ensure_directories(self) -> None:
        self.config.paths.incoming.mkdir(parents=True, exist_ok=True)
        self.config.paths.originals.mkdir(parents=True, exist_ok=True)
        if self.config.batch.write_backup_copy:
            self.config.paths.backup.mkdir(parents=True, exist_ok=True)
        self._state_root().mkdir(parents=True, exist_ok=True)

    def _collect_supported_files(self, photographer_dir: Path) -> list[FileEntry]:
        entries: list[FileEntry] = []
        for item in photographer_dir.iterdir():
            if not item.is_file():
                continue
            if item.suffix.lower() not in self.config.batch.allowed_extensions:
                continue
            stat = item.stat()
            entries.append(
                FileEntry(
                    path=item,
                    mtime=stat.st_mtime,
                    mtime_ns=stat.st_mtime_ns,
                    size=stat.st_size,
                )
            )
        return entries

    def _finalize_batch(self, photographer_dir: Path, entries: list[FileEntry], age_seconds: int) -> int:
        photographer_name = photographer_dir.name
        batch_id = f"{datetime.now(tz=timezone.utc):%Y%m%d%H%M%S}-{uuid.uuid4().hex[:8]}"

        originals_dir = (
            self.config.paths.originals
            / self.config.paths.default_event_id
            / self.config.paths.default_session_id
            / photographer_name
            / batch_id
        )
        backup_dir = self.config.paths.backup / photographer_name / batch_id

        originals_dir.mkdir(parents=True, exist_ok=False)
        if self.config.batch.write_backup_copy:
            backup_dir.mkdir(parents=True, exist_ok=False)

        moved_files: list[tuple[str, int]] = []
        broken_files_count = 0
        total_size = 0
        captured_at = datetime.now(tz=timezone.utc)

        for entry in sorted(entries, key=lambda item: item.path.name.lower()):
            source = entry.path
            if not source.exists():
                LOGGER.warning("Skip disappeared file: %s", source)
                continue
            if not self._is_likely_jpeg(source):
                broken_files_count += 1
                continue

            destination_name = self._safe_unique_name(originals_dir, source.name)
            destination_original = originals_dir / destination_name
            shutil.copy2(source, destination_original)
            if self.config.batch.write_backup_copy:
                destination_backup = backup_dir / destination_name
                shutil.copy2(source, destination_backup)
            moved_files.append((destination_name, entry.size))
            total_size += entry.size

        manifest = {
            "batch_id": batch_id,
            "photographer": photographer_name,
            "silence_age_seconds": age_seconds,
            "captured_at_utc": captured_at.isoformat(),
            "source_folder": str(photographer_dir),
            "originals_folder": str(originals_dir),
            "backup_folder": str(backup_dir),
            "file_count": len(moved_files),
            "total_size_bytes": total_size,
            "files": [name for name, _ in moved_files],
        }
        (originals_dir / "batch-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )

        db_batch_id: str | None = None
        if self.session_factory is not None:
            with self.session_factory() as session:
                db_batch = create_batch_with_photos(
                    session,
                    batch_key=batch_id,
                    photographer_folder_name=photographer_name,
                    originals_dir=originals_dir,
                    backup_dir=backup_dir,
                    captured_at=captured_at,
                    silence_age_seconds=age_seconds,
                    files=moved_files,
                    broken_files_count=broken_files_count,
                )
                create_in_app_batch_notification(
                    session,
                    batch_id=db_batch.id,
                    batch_key=batch_id,
                    photographer=photographer_name,
                    file_count=len(moved_files),
                    total_size_bytes=total_size,
                )
                session.commit()
                db_batch_id = db_batch.id

        try:
            self.notifier.notify_batch_finalized(
                BatchNotification(
                    batch_key=batch_id,
                    batch_id=db_batch_id,
                    photographer=photographer_name,
                    file_count=len(moved_files),
                    broken_files_count=broken_files_count,
                    total_size_bytes=total_size,
                    base_url=self.config.app.base_url,
                )
            )
        except Exception:
            LOGGER.exception("Notifier failed for batch_key=%s", batch_id)

        try:
            self._maybe_upload_batch_to_yandex(
                photographer_name=photographer_name,
                source_entries=entries,
            )
        except Exception:
            LOGGER.exception("Yandex auto-upload failed for batch_key=%s", batch_id)

        LOGGER.info(
            "Batch finalized: photographer=%s batch_id=%s files=%d size=%dB",
            photographer_name,
            batch_id,
            len(moved_files),
            total_size,
        )
        return max((entry.mtime_ns for entry in entries), default=0)

    @staticmethod
    def _safe_unique_name(target_dir: Path, original_name: str) -> str:
        candidate = original_name
        stem = Path(original_name).stem
        suffix = Path(original_name).suffix
        index = 1
        while (target_dir / candidate).exists():
            candidate = f"{stem}-{index}{suffix}"
            index += 1
        return candidate

    @staticmethod
    def _is_likely_jpeg(path: Path) -> bool:
        if path.suffix.lower() not in (".jpg", ".jpeg"):
            return False
        try:
            with path.open("rb") as file_handle:
                head = file_handle.read(2)
                if head != b"\xFF\xD8":
                    return False
                size = path.stat().st_size
                if size < 4:
                    return False
                file_handle.seek(-2, os.SEEK_END)
                tail = file_handle.read(2)
                return tail == b"\xFF\xD9"
        except OSError:
            return False

    def _maybe_upload_batch_to_yandex(
        self,
        *,
        photographer_name: str,
        source_entries: list[FileEntry],
    ) -> None:
        if not source_entries or self.session_factory is None:
            return
        with self.session_factory() as session:
            auto_mode = get_app_setting(session, "yandex_disk.auto_upload_all", default="false")
            if auto_mode.lower() != "true":
                return
            runtime_token = get_app_setting(
                session,
                SETTING_YADISK_OAUTH_TOKEN,
                default=self.config.yandex_disk.oauth_token,
            ).strip()
            runtime_remote_base = get_app_setting(
                session,
                SETTING_YADISK_REMOTE_BASE,
                default=self.config.yandex_disk.remote_base_path,
            ).strip()
        if not self.config.yandex_disk.enabled or not runtime_token:
            return
        runtime_cfg = replace(
            self.config.yandex_disk,
            oauth_token=runtime_token,
            remote_base_path=runtime_remote_base or self.config.yandex_disk.remote_base_path,
            enabled=True,
        )
        remote_dir = f"{runtime_cfg.remote_base_path.rstrip('/')}/{photographer_name}"
        source_files = [(entry.path, entry.path.name) for entry in source_entries if entry.path.exists()]
        uploader = YandexDiskUploader(runtime_cfg)
        result = uploader.upload_batch_files(local_files=source_files, remote_dir=remote_dir)
        LOGGER.info(
            "Yandex auto-upload complete: dir=%s files=%d",
            result.remote_path,
            result.uploaded_files,
        )

    def _state_root(self) -> Path:
        return self.config.paths.originals / ".watcher-state"

    def _state_file(self, photographer_name: str) -> Path:
        safe_name = photographer_name.replace("/", "_")
        return self._state_root() / f"{safe_name}.json"

    def _load_last_processed_mtime_ns(self, photographer_name: str) -> int:
        state_file = self._state_file(photographer_name)
        if not state_file.exists():
            return 0
        try:
            payload = json.loads(state_file.read_text(encoding="utf-8"))
            value = int(payload.get("last_processed_mtime_ns", 0))
            return max(value, 0)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return 0

    def _store_last_processed_mtime_ns(self, photographer_name: str, value: int) -> None:
        state_file = self._state_file(photographer_name)
        payload = {
            "photographer": photographer_name,
            "last_processed_mtime_ns": int(max(value, 0)),
            "updated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        }
        state_file.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

    def _run_archive_maintenance(self) -> None:
        if self.session_factory is None:
            return
        now = datetime.now(tz=timezone.utc)
        with self.session_factory() as session:
            retention_hours = get_archive_retention_hours(session)
            candidates = list_batches_for_archive_state_sync(session, limit=1000)
            updated_markers = 0
            for batch in candidates:
                photographer = get_photographer_by_id(session, batch.photographer_id)
                photographer_name = photographer.folder_name if photographer else None
                if not photographer_name:
                    continue
                photos = get_batch_photos(session, batch.id)
                if not photos:
                    continue
                incoming_dir = self.config.paths.incoming / photographer_name
                has_incoming = any((incoming_dir / photo.filename).exists() for photo in photos)
                if has_incoming:
                    continue
                if batch.removed_from_incoming_at is None:
                    mark_batch_removed_from_incoming(
                        session,
                        batch_id=batch.id,
                        removed_at=now,
                        retention_hours=retention_hours,
                    )
                    mark_batch_downloaded(session, batch.id)
                    updated_markers += 1

            cleanup_candidates = list_batches_for_archive_cleanup(session, now=now, limit=1000)
            cleaned_batches = 0
            for batch in cleanup_candidates:
                photos = get_batch_photos(session, batch.id)
                for photo in photos:
                    source = Path(photo.original_path)
                    if source.exists():
                        source.unlink()
                mark_batch_archived_deleted(session, batch_id=batch.id)
                cleaned_batches += 1

            if updated_markers or cleaned_batches:
                session.commit()
                LOGGER.info(
                    "Archive maintenance complete: marked_removed=%d cleaned_batches=%d",
                    updated_markers,
                    cleaned_batches,
                )
            else:
                session.rollback()
