"""FastAPI application for bild-facing endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta
import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import FileResponse
from PIL import Image, ImageOps
from starlette.background import BackgroundTask

from photofactory.api.auth import create_access_token, require_auth
from photofactory.batches import build_archive_name, build_batch_zip, build_selected_archive_name
from photofactory.api.schemas import (
    BatchCleanupResponse,
    BatchDetail,
    BatchListItem,
    BatchPhotoItem,
    BatchSelectedDownloadRequest,
    HealthResponse,
    IncomingPhotographerItem,
    NotificationMarkReadRequest,
    NotificationMarkReadResponse,
    NotificationItem,
    PwaTestPushRequest,
    PwaTestPushResponse,
    SmokeBatchRequest,
    SmokeBatchResponse,
    YandexDiskAutoModeRequest,
    YandexDiskAutoModeResponse,
    YandexDiskUploadResponse,
    PushSubscriptionDeleteRequest,
    PushSubscriptionResponse,
    PushSubscriptionUpsertRequest,
    TokenResponse,
)
from photofactory.config import AppConfig, load_config
from photofactory.db.repository import (
    get_batch_by_id,
    get_batch_daily_sequence,
    get_batch_photos,
    get_photo_by_id,
    create_or_update_push_subscription,
    deactivate_push_subscription,
    get_photographer_by_id,
    get_app_setting,
    mark_batch_downloaded,
    mark_all_notifications_read,
    increment_daily_counter,
    list_recent_notifications,
    list_recent_batches,
    set_app_setting,
)
from photofactory.db.session import build_session_factory
from photofactory.notifications.pwa import PwaNotifier
from photofactory.storage.yandex_disk import YandexDiskUploader

STATIC_DIR = Path(__file__).parent / "static"
THUMBNAIL_SIZE = 320
THUMBNAIL_QUALITY = 72


def create_app(config: AppConfig) -> FastAPI:
    session_factory = build_session_factory(config)
    app = FastAPI(title="Yauza Photofactory API", version="0.1.0")
    previews_root = config.paths.originals.parent / "previews"
    try:
        previews_root.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        previews_root = Path("/tmp/yauza-previews")
        previews_root.mkdir(parents=True, exist_ok=True)

    def ensure_thumbnail(source_path: Path, photo_id: str) -> Path:
        target = previews_root / f"{photo_id}.jpg"
        regenerate = True
        if target.exists():
            regenerate = target.stat().st_mtime < source_path.stat().st_mtime
        if not regenerate:
            return target
        try:
            with Image.open(source_path) as image:
                normalized = ImageOps.exif_transpose(image).convert("RGB")
                normalized.thumbnail((THUMBNAIL_SIZE, THUMBNAIL_SIZE))
                normalized.save(target, format="JPEG", quality=THUMBNAIL_QUALITY, optimize=True)
            return target
        except Exception:
            # Fallback: keep endpoint stable even for broken/non-image files.
            return source_path

    def resolve_photo_paths(
        *,
        photo_filename: str,
        original_path: str,
        photographer_name: str,
    ) -> tuple[Path, Path]:
        original = Path(original_path)
        incoming = config.paths.incoming / photographer_name / photo_filename
        return original, incoming

    def pick_readable_source(
        *,
        photo_filename: str,
        original_path: str,
        photographer_name: str,
    ) -> Path | None:
        original, incoming = resolve_photo_paths(
            photo_filename=photo_filename,
            original_path=original_path,
            photographer_name=photographer_name,
        )
        if original.exists():
            return original
        if incoming.exists():
            return incoming
        return None

    def list_active_photos_for_batch(photos: list, photographer_name: str) -> list:
        incoming_dir = config.paths.incoming / photographer_name
        return [photo for photo in photos if (incoming_dir / photo.filename).exists()]

    def remove_photo_files(photos: list, photographer_name: str) -> None:
        for photo in photos:
            original, incoming = resolve_photo_paths(
                photo_filename=photo.filename,
                original_path=photo.original_path,
                photographer_name=photographer_name,
            )
            if incoming.exists():
                incoming.unlink()
            if original.exists():
                original.unlink()

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get("/pwa/test")
    def pwa_test_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "pwa-test.html", media_type="text/html")

    @app.get("/pwa-test.js")
    def pwa_test_js() -> FileResponse:
        return FileResponse(STATIC_DIR / "pwa-test.js", media_type="application/javascript")

    @app.get("/bild")
    def bild_dashboard_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "bild-dashboard.html", media_type="text/html")

    @app.get("/bild-dashboard.js")
    def bild_dashboard_js() -> FileResponse:
        return FileResponse(STATIC_DIR / "bild-dashboard.js", media_type="application/javascript")

    @app.get("/sw.js")
    def service_worker_js() -> FileResponse:
        return FileResponse(STATIC_DIR / "sw.js", media_type="application/javascript")

    @app.post("/api/auth/token", response_model=TokenResponse)
    def issue_token(form: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
        if form.username != config.auth.username or form.password != config.auth.password:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )
        return TokenResponse(
            access_token=create_access_token(config, form.username),
            expires_in_seconds=config.auth.token_ttl_minutes * 60,
        )

    @app.get("/api/batches", response_model=list[BatchListItem])
    def get_batches(
        limit: int = Query(default=50, ge=1, le=500),
        include_downloaded: bool = Query(default=False),
        _: str = Depends(require_auth(config)),
    ) -> list[BatchListItem]:
        with session_factory() as session:
            probe_limit = min(500, max(limit * 4, limit))
            batches = list_recent_batches(session, limit=probe_limit, include_downloaded=include_downloaded)
            response: list[BatchListItem] = []
            for batch in batches:
                photographer = get_photographer_by_id(session, batch.photographer_id)
                photographer_name = photographer.folder_name if photographer else "unknown"
                photos = get_batch_photos(session, batch.id)
                active_photos = list_active_photos_for_batch(photos, photographer_name)
                if not include_downloaded and not active_photos:
                    continue
                daily_sequence = get_batch_daily_sequence(session, batch)
                response.append(
                    BatchListItem(
                        id=batch.id,
                        batch_key=batch.batch_key,
                        photographer=photographer_name,
                        status=batch.status,
                        file_count=len(active_photos) if not include_downloaded else batch.file_count,
                        broken_files_count=batch.broken_files_count,
                        daily_sequence=daily_sequence,
                        total_size_bytes=batch.total_size_bytes,
                        archive_name=build_archive_name(photographer_name, batch.captured_at, daily_sequence),
                        captured_at=batch.captured_at,
                        created_at=batch.created_at,
                    )
                )
                if len(response) >= limit:
                    break
            return response

    @app.get("/api/incoming/photographers", response_model=list[IncomingPhotographerItem])
    def get_incoming_photographers(
        _: str = Depends(require_auth(config)),
    ) -> list[IncomingPhotographerItem]:
        incoming_root = config.paths.incoming
        if not incoming_root.exists():
            return []
        result: list[IncomingPhotographerItem] = []
        allowed = set(config.batch.allowed_extensions)
        for item in sorted(incoming_root.iterdir(), key=lambda d: d.name.lower()):
            if not item.is_dir():
                continue
            count = 0
            for candidate in item.iterdir():
                if candidate.is_file() and candidate.suffix.lower() in allowed:
                    count += 1
            if count > 0:
                result.append(IncomingPhotographerItem(folder_name=item.name, file_count=count))
        return result

    @app.get("/api/batches/{batch_id}", response_model=BatchDetail)
    def get_batch(batch_id: str, _: str = Depends(require_auth(config))) -> BatchDetail:
        with session_factory() as session:
            batch = get_batch_by_id(session, batch_id)
            if batch is None:
                raise HTTPException(status_code=404, detail="Batch not found")
            photos = get_batch_photos(session, batch.id)
            photographer = get_photographer_by_id(session, batch.photographer_id)
            photographer_name = photographer.folder_name if photographer else "unknown"
            active_photos = list_active_photos_for_batch(photos, photographer_name)
            daily_sequence = get_batch_daily_sequence(session, batch)
            captured_at = batch.captured_at
            return BatchDetail(
                id=batch.id,
                batch_key=batch.batch_key,
                photographer=photographer_name,
                status=batch.status,
                file_count=len(active_photos),
                broken_files_count=batch.broken_files_count,
                daily_sequence=daily_sequence,
                total_size_bytes=batch.total_size_bytes,
                archive_name=build_archive_name(photographer_name, batch.captured_at, daily_sequence),
                silence_age_seconds=batch.silence_age_seconds,
                originals_path=batch.originals_path,
                backup_path=batch.backup_path,
                captured_at=batch.captured_at,
                created_at=batch.created_at,
                photos=[
                    BatchPhotoItem(
                        id=photo.id,
                        filename=photo.filename,
                        size_bytes=photo.size_bytes,
                        original_path=photo.original_path,
                        image_url=f"/api/photos/{photo.id}/content",
                        thumbnail_url=f"/api/photos/{photo.id}/thumbnail",
                    )
                    for photo in active_photos
                ],
            )

    @app.get("/api/photos/{photo_id}/content")
    def get_photo_content(
        photo_id: str,
        _: str = Depends(require_auth(config)),
    ) -> FileResponse:
        with session_factory() as session:
            photo = get_photo_by_id(session, photo_id)
            if photo is None:
                raise HTTPException(status_code=404, detail="Photo not found")
            batch = get_batch_by_id(session, photo.batch_id)
            if batch is None:
                raise HTTPException(status_code=404, detail="Batch not found")
            photographer = get_photographer_by_id(session, batch.photographer_id)
            photographer_name = photographer.folder_name if photographer else "unknown"
            source = pick_readable_source(
                photo_filename=photo.filename,
                original_path=photo.original_path,
                photographer_name=photographer_name,
            )
            if source is None:
                raise HTTPException(status_code=404, detail="Photo file not found")
            media_type = "image/jpeg" if source.suffix.lower() in (".jpg", ".jpeg") else "application/octet-stream"
            return FileResponse(source, media_type=media_type, filename=photo.filename)

    @app.get("/api/photos/{photo_id}/thumbnail")
    def get_photo_thumbnail(
        photo_id: str,
        _: str = Depends(require_auth(config)),
    ) -> FileResponse:
        with session_factory() as session:
            photo = get_photo_by_id(session, photo_id)
            if photo is None:
                raise HTTPException(status_code=404, detail="Photo not found")
            batch = get_batch_by_id(session, photo.batch_id)
            if batch is None:
                raise HTTPException(status_code=404, detail="Batch not found")
            photographer = get_photographer_by_id(session, batch.photographer_id)
            photographer_name = photographer.folder_name if photographer else "unknown"
            source = pick_readable_source(
                photo_filename=photo.filename,
                original_path=photo.original_path,
                photographer_name=photographer_name,
            )
            if source is None:
                raise HTTPException(status_code=404, detail="Photo file not found")
            preview = ensure_thumbnail(source, photo.id)
            return FileResponse(preview, media_type="image/jpeg", filename=f"{photo.filename}.thumb.jpg")

    @app.get("/api/batches/{batch_id}/download")
    def download_batch_zip(
        batch_id: str,
        cleanup_incoming: bool = Query(default=True),
        _: str = Depends(require_auth(config)),
    ) -> FileResponse:
        with session_factory() as session:
            batch = get_batch_by_id(session, batch_id)
            if batch is None:
                raise HTTPException(status_code=404, detail="Batch not found")
            photos = get_batch_photos(session, batch.id)
            photographer = get_photographer_by_id(session, batch.photographer_id)
            photographer_name = photographer.folder_name if photographer else "unknown"
            active_photos = list_active_photos_for_batch(photos, photographer_name)
            if not active_photos:
                raise HTTPException(status_code=404, detail="Batch has no active photos in incoming")
            daily_sequence = get_batch_daily_sequence(session, batch)
            captured_at = batch.captured_at

            zip_sources: list[tuple[Path, str]] = []
            for photo in active_photos:
                source = pick_readable_source(
                    photo_filename=photo.filename,
                    original_path=photo.original_path,
                    photographer_name=photographer_name,
                )
                if source is not None:
                    zip_sources.append((source, photo.filename))
            if not zip_sources:
                raise HTTPException(status_code=404, detail="No readable photo files for archive")
            temp_zip_path = build_batch_zip(zip_sources)

            if cleanup_incoming and photographer_name != "unknown":
                remove_photo_files(active_photos, photographer_name)
            if mark_batch_downloaded(session, batch_id):
                session.commit()

        filename = build_archive_name(photographer_name, captured_at, daily_sequence)
        return FileResponse(
            path=temp_zip_path,
            media_type="application/zip",
            filename=filename,
            background=BackgroundTask(lambda path: Path(path).unlink(missing_ok=True), str(temp_zip_path)),
        )

    @app.post("/api/batches/{batch_id}/download-selected")
    def download_selected_batch_zip(
        batch_id: str,
        payload: BatchSelectedDownloadRequest,
        _: str = Depends(require_auth(config)),
    ) -> FileResponse:
        selected_ids = {item for item in payload.photo_ids if item}
        if not selected_ids:
            raise HTTPException(status_code=400, detail="photo_ids is empty")
        with session_factory() as session:
            batch = get_batch_by_id(session, batch_id)
            if batch is None:
                raise HTTPException(status_code=404, detail="Batch not found")
            photos = get_batch_photos(session, batch.id)
            photographer = get_photographer_by_id(session, batch.photographer_id)
            photographer_name = photographer.folder_name if photographer else "unknown"
            active_photos = list_active_photos_for_batch(photos, photographer_name)
            selected_photos = [photo for photo in active_photos if photo.id in selected_ids]
            if not selected_photos:
                raise HTTPException(status_code=400, detail="Selected photos are not active in incoming")
            daily_sequence = get_batch_daily_sequence(session, batch)
            captured_at = batch.captured_at
            day_key = captured_at.strftime("%Y%m%d")
            selected_counter = increment_daily_counter(
                session,
                key_prefix="downloads.selected.counter",
                day_key=day_key,
            )

            zip_sources: list[tuple[Path, str]] = []
            for photo in selected_photos:
                source = pick_readable_source(
                    photo_filename=photo.filename,
                    original_path=photo.original_path,
                    photographer_name=photographer_name,
                )
                if source is not None:
                    zip_sources.append((source, photo.filename))
            if not zip_sources:
                raise HTTPException(status_code=404, detail="No readable selected files for archive")
            temp_zip_path = build_batch_zip(zip_sources)
            remove_photo_files(selected_photos, photographer_name)
            remaining_active = list_active_photos_for_batch(photos, photographer_name)
            if not remaining_active:
                mark_batch_downloaded(session, batch_id)
            session.commit()

        filename = build_selected_archive_name(
            photographer_name,
            captured_at,
            daily_selected_counter=selected_counter,
            daily_sequence=daily_sequence,
        )
        return FileResponse(
            path=temp_zip_path,
            media_type="application/zip",
            filename=filename,
            background=BackgroundTask(lambda path: Path(path).unlink(missing_ok=True), str(temp_zip_path)),
        )

    @app.post("/api/batches/{batch_id}/upload-yandex", response_model=YandexDiskUploadResponse)
    def upload_batch_to_yandex(
        batch_id: str,
        _: str = Depends(require_auth(config)),
    ) -> YandexDiskUploadResponse:
        if not config.yandex_disk.enabled:
            raise HTTPException(status_code=400, detail="Yandex Disk integration is disabled")
        with session_factory() as session:
            batch = get_batch_by_id(session, batch_id)
            if batch is None:
                raise HTTPException(status_code=404, detail="Batch not found")
            photos = get_batch_photos(session, batch.id)
            photographer = get_photographer_by_id(session, batch.photographer_id)
            photographer_name = photographer.folder_name if photographer else "unknown"
            remote_dir = f"{config.yandex_disk.remote_base_path.rstrip('/')}/{photographer_name}"
            active_photos = list_active_photos_for_batch(photos, photographer_name)
            source_files = [
                (config.paths.incoming / photographer_name / photo.filename, photo.filename)
                for photo in active_photos
                if (config.paths.incoming / photographer_name / photo.filename).exists()
            ]
            if not source_files:
                raise HTTPException(status_code=404, detail="Batch has no active files in incoming")
        try:
            uploader = YandexDiskUploader(config.yandex_disk)
            result = uploader.upload_batch_files(local_files=source_files, remote_dir=remote_dir)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Yandex upload failed: {exc}") from exc

        return YandexDiskUploadResponse(
            status="ok",
            batch_id=batch_id,
            remote_path=result.remote_path,
            uploaded_files=result.uploaded_files,
        )

    @app.get("/api/yandex/auto-upload", response_model=YandexDiskAutoModeResponse)
    def get_yandex_auto_upload(
        _: str = Depends(require_auth(config)),
    ) -> YandexDiskAutoModeResponse:
        if not config.yandex_disk.enabled:
            return YandexDiskAutoModeResponse(enabled=False)
        with session_factory() as session:
            enabled_raw = get_app_setting(session, "yandex_disk.auto_upload_all", default="false")
        return YandexDiskAutoModeResponse(enabled=enabled_raw.lower() == "true")

    @app.post("/api/batches/cleanup-processed", response_model=BatchCleanupResponse)
    def cleanup_processed_batches(
        _: str = Depends(require_auth(config)),
    ) -> BatchCleanupResponse:
        updated = 0
        with session_factory() as session:
            batches = list_recent_batches(session, limit=500, include_downloaded=False)
            for batch in batches:
                photographer = get_photographer_by_id(session, batch.photographer_id)
                photographer_name = photographer.folder_name if photographer else None
                if not photographer_name:
                    continue
                photos = get_batch_photos(session, batch.id)
                if not photos:
                    continue
                incoming_dir = config.paths.incoming / photographer_name
                exists_in_incoming = any((incoming_dir / photo.filename).exists() for photo in photos)
                if not exists_in_incoming and mark_batch_downloaded(session, batch.id):
                    updated += 1
            session.commit()
        return BatchCleanupResponse(status="ok", updated=updated)

    @app.post("/api/yandex/auto-upload", response_model=YandexDiskAutoModeResponse)
    def set_yandex_auto_upload(
        payload: YandexDiskAutoModeRequest,
        _: str = Depends(require_auth(config)),
    ) -> YandexDiskAutoModeResponse:
        if payload.enabled and not config.yandex_disk.enabled:
            raise HTTPException(status_code=400, detail="Yandex Disk integration is disabled")
        with session_factory() as session:
            set_app_setting(
                session,
                key="yandex_disk.auto_upload_all",
                value="true" if payload.enabled else "false",
            )
            session.commit()
        return YandexDiskAutoModeResponse(enabled=payload.enabled)

    @app.get("/api/notifications", response_model=list[NotificationItem])
    def get_notifications(
        limit: int = Query(default=50, ge=1, le=500),
        _: str = Depends(require_auth(config)),
    ) -> list[NotificationItem]:
        with session_factory() as session:
            entities = list_recent_notifications(session, limit=limit)
            return [
                NotificationItem(
                    id=item.id,
                    kind=item.kind,
                    title=item.title,
                    message=item.message,
                    channel=item.channel,
                    status=item.status,
                    batch_id=item.batch_id,
                    photographer=item.photographer,
                    created_at=item.created_at,
                )
                for item in entities
            ]

    @app.post("/api/notifications/mark-read", response_model=NotificationMarkReadResponse)
    def mark_notifications_read(
        payload: NotificationMarkReadRequest,
        _: str = Depends(require_auth(config)),
    ) -> NotificationMarkReadResponse:
        if payload.mode != "all":
            raise HTTPException(status_code=400, detail="Only mode=all is supported")
        with session_factory() as session:
            updated = mark_all_notifications_read(session)
            session.commit()
        return NotificationMarkReadResponse(status="ok", updated=updated)

    @app.get("/api/pwa/public-key")
    def get_pwa_public_key(_: str = Depends(require_auth(config))) -> dict[str, str]:
        return {"vapid_public_key": config.notifications.pwa.vapid_public_key}

    @app.post("/api/pwa/subscriptions", response_model=PushSubscriptionResponse)
    def upsert_pwa_subscription(
        payload: PushSubscriptionUpsertRequest,
        _: str = Depends(require_auth(config)),
    ) -> PushSubscriptionResponse:
        with session_factory() as session:
            create_or_update_push_subscription(
                session,
                endpoint=payload.endpoint,
                p256dh=payload.keys.p256dh,
                auth=payload.keys.auth,
                user_agent=payload.user_agent,
            )
            session.commit()
        return PushSubscriptionResponse(status="saved", endpoint=payload.endpoint)

    @app.delete("/api/pwa/subscriptions", response_model=PushSubscriptionResponse)
    def delete_pwa_subscription(
        payload: PushSubscriptionDeleteRequest,
        _: str = Depends(require_auth(config)),
    ) -> PushSubscriptionResponse:
        with session_factory() as session:
            existed = deactivate_push_subscription(session, endpoint=payload.endpoint)
            session.commit()
        return PushSubscriptionResponse(
            status="deleted" if existed else "not_found",
            endpoint=payload.endpoint,
        )

    @app.post("/api/pwa/test-push", response_model=PwaTestPushResponse)
    def send_test_pwa_push(
        payload: PwaTestPushRequest,
        _: str = Depends(require_auth(config)),
    ) -> PwaTestPushResponse:
        pwa_cfg = config.notifications.pwa
        if not pwa_cfg.enabled:
            raise HTTPException(status_code=400, detail="PWA notifications are disabled")
        if not pwa_cfg.vapid_private_key:
            raise HTTPException(status_code=400, detail="vapid_private_key is not configured")
        if not pwa_cfg.vapid_subject:
            raise HTTPException(status_code=400, detail="vapid_subject is not configured")

        notifier = PwaNotifier(
            session_factory=session_factory,
            vapid_private_key=pwa_cfg.vapid_private_key,
            vapid_subject=pwa_cfg.vapid_subject,
        )
        result = notifier.send_raw_payload(
            {
                "type": "test_push",
                "title": payload.title,
                "body": payload.body,
            }
        )
        return PwaTestPushResponse(
            status="ok",
            sent=result.sent,
            failed=result.failed,
            deactivated=result.deactivated,
        )

    @app.post("/api/dev/smoke-batch", response_model=SmokeBatchResponse)
    def create_smoke_batch(
        payload: SmokeBatchRequest,
        _: str = Depends(require_auth(config)),
    ) -> SmokeBatchResponse:
        target_dir = config.paths.incoming / payload.photographer
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / payload.filename
        # Minimal JPEG payload (SOI ... EOI) for watcher smoke-flow.
        target_file.write_bytes(b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xFF\xD9")
        old_time = datetime.now() - timedelta(minutes=2)
        os.utime(target_file, (old_time.timestamp(), old_time.timestamp()))
        return SmokeBatchResponse(status="queued", photographer=payload.photographer, file_path=str(target_file))

    return app


def load_app(config_path: str = "config.yaml") -> FastAPI:
    config = load_config(config_path)
    return create_app(config)
