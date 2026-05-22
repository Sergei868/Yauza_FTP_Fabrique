"""FastAPI application for bild-facing endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta
import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from photofactory.api.auth import create_access_token, require_auth
from photofactory.batches import build_archive_name, build_batch_zip
from photofactory.api.schemas import (
    BatchDetail,
    BatchListItem,
    BatchPhotoItem,
    HealthResponse,
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
    mark_all_notifications_read,
    list_recent_notifications,
    list_recent_batches,
    set_app_setting,
)
from photofactory.db.session import build_session_factory
from photofactory.notifications.pwa import PwaNotifier
from photofactory.storage.yandex_disk import YandexDiskUploader

STATIC_DIR = Path(__file__).parent / "static"


def create_app(config: AppConfig) -> FastAPI:
    session_factory = build_session_factory(config)
    app = FastAPI(title="Yauza Photofactory API", version="0.1.0")

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
        _: str = Depends(require_auth(config)),
    ) -> list[BatchListItem]:
        with session_factory() as session:
            batches = list_recent_batches(session, limit=limit)
            response: list[BatchListItem] = []
            for batch in batches:
                photographer = get_photographer_by_id(session, batch.photographer_id)
                photographer_name = photographer.folder_name if photographer else "unknown"
                daily_sequence = get_batch_daily_sequence(session, batch)
                response.append(
                    BatchListItem(
                        id=batch.id,
                        batch_key=batch.batch_key,
                        photographer=photographer_name,
                        status=batch.status,
                        file_count=batch.file_count,
                        broken_files_count=batch.broken_files_count,
                        daily_sequence=daily_sequence,
                        total_size_bytes=batch.total_size_bytes,
                        archive_name=build_archive_name(photographer_name, batch.captured_at, daily_sequence),
                        captured_at=batch.captured_at,
                        created_at=batch.created_at,
                    )
                )
            return response

    @app.get("/api/batches/{batch_id}", response_model=BatchDetail)
    def get_batch(batch_id: str, _: str = Depends(require_auth(config))) -> BatchDetail:
        with session_factory() as session:
            batch = get_batch_by_id(session, batch_id)
            if batch is None:
                raise HTTPException(status_code=404, detail="Batch not found")
            photos = get_batch_photos(session, batch.id)
            photographer = get_photographer_by_id(session, batch.photographer_id)
            photographer_name = photographer.folder_name if photographer else "unknown"
            daily_sequence = get_batch_daily_sequence(session, batch)
            captured_at = batch.captured_at
            return BatchDetail(
                id=batch.id,
                batch_key=batch.batch_key,
                photographer=photographer_name,
                status=batch.status,
                file_count=batch.file_count,
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
                    )
                    for photo in photos
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
            source = Path(photo.original_path)
            if not source.exists():
                raise HTTPException(status_code=404, detail="Photo file not found")
            media_type = "image/jpeg" if source.suffix.lower() in (".jpg", ".jpeg") else "application/octet-stream"
            return FileResponse(source, media_type=media_type, filename=photo.filename)

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
            if not photos:
                raise HTTPException(status_code=404, detail="Batch has no photos")
            photographer = get_photographer_by_id(session, batch.photographer_id)
            photographer_name = photographer.folder_name if photographer else "unknown"
            daily_sequence = get_batch_daily_sequence(session, batch)
            captured_at = batch.captured_at

        temp_zip_path = build_batch_zip([(Path(photo.original_path), photo.filename) for photo in photos])

        if cleanup_incoming and photographer_name != "unknown":
            incoming_dir = config.paths.incoming / photographer_name
            for photo in photos:
                incoming_file = incoming_dir / photo.filename
                if incoming_file.exists():
                    incoming_file.unlink()

        filename = build_archive_name(photographer_name, captured_at, daily_sequence)
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
            if not photos:
                raise HTTPException(status_code=404, detail="Batch has no photos")
            photographer = get_photographer_by_id(session, batch.photographer_id)
            photographer_name = photographer.folder_name if photographer else "unknown"
            remote_dir = f"{config.yandex_disk.remote_base_path.rstrip('/')}/{photographer_name}"
            source_files = [(Path(photo.original_path), photo.filename) for photo in photos]
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
