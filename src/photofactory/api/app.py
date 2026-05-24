"""FastAPI application for bild-facing endpoints."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import FileResponse
from PIL import Image, ImageOps
from starlette.background import BackgroundTask

from photofactory.api.auth import AuthUser, create_access_token, require_admin, require_auth
from photofactory.batches import build_archive_name, build_batch_zip, build_selected_archive_name
from photofactory.api.schemas import (
    AdminSettingsResponse,
    AdminSettingsUpdateRequest,
    AdminApplyFtpResponse,
    ArchiveBatchDetail,
    ArchiveBatchListItem,
    AuthMeResponse,
    ArchiveClearResponse,
    ArchiveSettingsResponse,
    ArchiveSettingsUpdateRequest,
    ArchiveUsageResponse,
    BatchCleanupResponse,
    BatchDetail,
    BatchListItem,
    BatchPhotoItem,
    BatchSelectedDownloadRequest,
    HealthResponse,
    IncomingPhotographerItem,
    NotificationClearResponse,
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
    get_archive_limit_gb,
    get_archive_retention_hours,
    deactivate_push_subscription,
    get_photographer_by_id,
    get_app_setting,
    list_archive_batches,
    list_batches_for_archive_cleanup,
    mark_batch_downloaded,
    mark_batch_archived_deleted,
    mark_batch_removed_from_incoming,
    delete_all_notifications,
    increment_daily_counter,
    list_recent_notifications,
    list_recent_batches,
    set_archive_limit_gb,
    set_archive_retention_hours,
    set_app_setting,
)
from photofactory.db.session import build_session_factory
from photofactory.notifications.pwa import PwaNotifier
from photofactory.storage.yandex_disk import YandexDiskUploader

STATIC_DIR = Path(__file__).parent / "static"
THUMBNAIL_SIZE = 320
THUMBNAIL_QUALITY = 72
ARCHIVE_TTL_OPTIONS_HOURS = [1, 2, 3, 4, 5, 6, 8, 12, 24, 36]
SETTING_AUTH_BILD_USERNAME = "auth.bild.username"
SETTING_AUTH_BILD_PASSWORD = "auth.bild.password"
SETTING_AUTH_ADMIN_USERNAME = "auth.admin.username"
SETTING_AUTH_ADMIN_PASSWORD = "auth.admin.password"
SETTING_FTP_BILD_USERNAME = "ftp.bild.username"
SETTING_FTP_BILD_PASSWORD = "ftp.bild.password"
SETTING_FTP_PHOTOGRAPHER_USERNAME = "ftp.photographer.username"
SETTING_FTP_PHOTOGRAPHER_PASSWORD = "ftp.photographer.password"
SETTING_YADISK_OAUTH_TOKEN = "yandex_disk.oauth_token.override"
SETTING_YADISK_REMOTE_BASE = "yandex_disk.remote_base_path.override"


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
            _, incoming = resolve_photo_paths(
                photo_filename=photo.filename,
                original_path=photo.original_path,
                photographer_name=photographer_name,
            )
            if incoming.exists():
                incoming.unlink()

    def collect_archive_file_sources(photos: list) -> list[tuple[Path, str]]:
        sources: list[tuple[Path, str]] = []
        for photo in photos:
            source = Path(photo.original_path)
            if source.exists():
                sources.append((source, photo.filename))
        return sources

    def calculate_archive_usage_bytes(session) -> int:
        total = 0
        for batch in list_archive_batches(session, limit=2000):
            photos = get_batch_photos(session, batch.id)
            for photo in photos:
                source = Path(photo.original_path)
                if source.exists():
                    total += source.stat().st_size
        return total

    def cleanup_expired_archive(session) -> tuple[int, int, int]:
        now = datetime.now(tz=timezone.utc)
        cleaned_batches = 0
        deleted_files = 0
        deleted_bytes = 0
        expired_batches = list_batches_for_archive_cleanup(session, now=now, limit=2000)
        for batch in expired_batches:
            photos = get_batch_photos(session, batch.id)
            for photo in photos:
                source = Path(photo.original_path)
                if source.exists():
                    deleted_bytes += source.stat().st_size
                    source.unlink()
                    deleted_files += 1
            mark_batch_archived_deleted(session, batch_id=batch.id)
            cleaned_batches += 1
        return cleaned_batches, deleted_files, deleted_bytes

    def get_setting_value(session, key: str, default: str = "") -> str:
        return get_app_setting(session, key, default=default)

    def get_runtime_auth_credentials(session) -> dict[str, str]:
        return {
            "bild_username": get_setting_value(session, SETTING_AUTH_BILD_USERNAME, config.auth.username),
            "bild_password": get_setting_value(session, SETTING_AUTH_BILD_PASSWORD, config.auth.password),
            "admin_username": get_setting_value(session, SETTING_AUTH_ADMIN_USERNAME, config.auth.admin_username),
            "admin_password": get_setting_value(session, SETTING_AUTH_ADMIN_PASSWORD, config.auth.admin_password),
        }

    def get_runtime_yandex_config(session):
        token = get_setting_value(session, SETTING_YADISK_OAUTH_TOKEN, config.yandex_disk.oauth_token).strip()
        remote_base_path = get_setting_value(session, SETTING_YADISK_REMOTE_BASE, config.yandex_disk.remote_base_path).strip()
        enabled = config.yandex_disk.enabled and bool(token)
        return replace(
            config.yandex_disk,
            enabled=enabled,
            oauth_token=token,
            remote_base_path=remote_base_path or config.yandex_disk.remote_base_path,
        )

    def apply_ftp_runtime_settings(
        *,
        ftp_bild_username: str,
        ftp_bild_password: str,
        ftp_photographer_username: str,
        ftp_photographer_password: str,
    ) -> None:
        payload = {
            "ftp_bild_username": ftp_bild_username,
            "ftp_bild_password": ftp_bild_password,
            "ftp_photographer_username": ftp_photographer_username,
            "ftp_photographer_password": ftp_photographer_password,
        }
        script = r"""
import json
import os
import pwd
import re
import subprocess
import sys
from pathlib import Path

def ensure_user(username: str) -> None:
    try:
        pwd.getpwnam(username)
        subprocess.run(
            ["usermod", "-d", "/srv/yauza/incoming", "-s", "/usr/sbin/nologin", "-g", "yauza", username],
            check=True,
            capture_output=True,
            text=True,
        )
    except KeyError:
        subprocess.run(
            ["useradd", "-M", "-d", "/srv/yauza/incoming", "-s", "/usr/sbin/nologin", "-g", "yauza", username],
            check=True,
            capture_output=True,
            text=True,
        )

def set_password(username: str, password: str) -> None:
    subprocess.run(
        ["chpasswd"],
        check=True,
        input=f"{username}:{password}\n",
        text=True,
        capture_output=True,
    )

def update_vsftpd_config(bild_username: str, photographer_username: str) -> None:
    conf_path = Path("/etc/vsftpd.conf")
    text = conf_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    new_lines = []
    seen_user_config_dir = False
    for raw in lines:
        line = raw.strip()
        if line.startswith("cmds_denied="):
            continue
        if line.startswith("user_config_dir="):
            new_lines.append("user_config_dir=/etc/vsftpd_user_conf")
            seen_user_config_dir = True
            continue
        new_lines.append(raw)
    if not seen_user_config_dir:
        new_lines.append("user_config_dir=/etc/vsftpd_user_conf")
    conf_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    userlist_path = Path("/etc/vsftpd.userlist")
    userlist_path.write_text(f"{photographer_username}\n{bild_username}\n", encoding="utf-8")

    user_conf_dir = Path("/etc/vsftpd_user_conf")
    user_conf_dir.mkdir(parents=True, exist_ok=True)

    photographer_conf = "\n".join([
        "local_root=/srv/yauza/incoming",
        "write_enable=YES",
        "download_enable=NO",
        "cmds_denied=DELE,RMD,RNFR,RNTO,SITE_CHMOD",
        "",
    ])
    (user_conf_dir / photographer_username).write_text(photographer_conf, encoding="utf-8")

    bild_conf = "\n".join([
        "local_root=/srv/yauza/incoming",
        "write_enable=YES",
        "",
    ])
    (user_conf_dir / bild_username).write_text(bild_conf, encoding="utf-8")

def main() -> None:
    payload = json.loads(sys.argv[1])
    ftp_bild_username = payload["ftp_bild_username"].strip()
    ftp_bild_password = payload["ftp_bild_password"]
    ftp_photographer_username = payload["ftp_photographer_username"].strip()
    ftp_photographer_password = payload["ftp_photographer_password"]
    username_re = re.compile(r"^[a-z_][a-z0-9_-]{1,31}$")
    for name in (ftp_bild_username, ftp_photographer_username):
        if not username_re.match(name):
            raise SystemExit(f"Invalid linux username: {name}")
    if ftp_bild_username == ftp_photographer_username:
        raise SystemExit("FTP usernames must be different")
    if not ftp_bild_password or not ftp_photographer_password:
        raise SystemExit("FTP passwords must be non-empty")
    ensure_user(ftp_photographer_username)
    ensure_user(ftp_bild_username)
    set_password(ftp_photographer_username, ftp_photographer_password)
    set_password(ftp_bild_username, ftp_bild_password)
    update_vsftpd_config(ftp_bild_username, ftp_photographer_username)
    subprocess.run(["systemctl", "restart", "vsftpd"], check=True, capture_output=True, text=True)

if __name__ == "__main__":
    main()
"""
        result = subprocess.run(
            ["sudo", "-n", "python3", "-c", script, json.dumps(payload)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            details = (result.stderr or result.stdout or "unknown error").strip()
            raise HTTPException(status_code=500, detail=f"FTP apply failed: {details}")

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
        with session_factory() as session:
            creds = get_runtime_auth_credentials(session)
        role: str | None = None
        if form.username == creds["admin_username"] and form.password == creds["admin_password"]:
            role = "admin"
        elif form.username == creds["bild_username"] and form.password == creds["bild_password"]:
            role = "bild"
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )
        return TokenResponse(
            access_token=create_access_token(config, form.username, role),
            expires_in_seconds=config.auth.token_ttl_minutes * 60,
            role=role,
        )

    @app.get("/api/auth/me", response_model=AuthMeResponse)
    def get_auth_me(user: AuthUser = Depends(require_auth(config))) -> AuthMeResponse:
        return AuthMeResponse(username=user.username, role=user.role)

    @app.get("/api/admin/settings", response_model=AdminSettingsResponse)
    def get_admin_settings(_: AuthUser = Depends(require_admin(config))) -> AdminSettingsResponse:
        with session_factory() as session:
            auth_values = get_runtime_auth_credentials(session)
            ftp_bild_username = get_setting_value(session, SETTING_FTP_BILD_USERNAME, "bild_ftp")
            ftp_bild_password = get_setting_value(session, SETTING_FTP_BILD_PASSWORD, "")
            ftp_photographer_username = get_setting_value(session, SETTING_FTP_PHOTOGRAPHER_USERNAME, "upload")
            ftp_photographer_password = get_setting_value(session, SETTING_FTP_PHOTOGRAPHER_PASSWORD, "")
            yandex_token = get_setting_value(session, SETTING_YADISK_OAUTH_TOKEN, config.yandex_disk.oauth_token)
            yandex_remote_base = get_setting_value(session, SETTING_YADISK_REMOTE_BASE, config.yandex_disk.remote_base_path)
        return AdminSettingsResponse(
            bild_username=auth_values["bild_username"],
            bild_password=auth_values["bild_password"],
            admin_username=auth_values["admin_username"],
            admin_password=auth_values["admin_password"],
            ftp_bild_username=ftp_bild_username,
            ftp_bild_password=ftp_bild_password,
            ftp_bild_password_set=bool(ftp_bild_password),
            ftp_photographer_username=ftp_photographer_username,
            ftp_photographer_password=ftp_photographer_password,
            ftp_photographer_password_set=bool(ftp_photographer_password),
            yandex_token_set=bool(yandex_token),
            yandex_oauth_token=yandex_token,
            yandex_remote_base_path=yandex_remote_base,
        )

    @app.post("/api/admin/settings", response_model=AdminSettingsResponse)
    def update_admin_settings(
        payload: AdminSettingsUpdateRequest,
        _: AuthUser = Depends(require_admin(config)),
    ) -> AdminSettingsResponse:
        with session_factory() as session:
            if payload.bild_username is not None:
                normalized = payload.bild_username.strip()
                if not normalized:
                    raise HTTPException(status_code=400, detail="bild_username cannot be empty")
                set_app_setting(session, key=SETTING_AUTH_BILD_USERNAME, value=normalized)
            if payload.bild_password is not None and payload.bild_password.strip():
                set_app_setting(session, key=SETTING_AUTH_BILD_PASSWORD, value=payload.bild_password)
            if payload.admin_username is not None:
                normalized = payload.admin_username.strip()
                if not normalized:
                    raise HTTPException(status_code=400, detail="admin_username cannot be empty")
                set_app_setting(session, key=SETTING_AUTH_ADMIN_USERNAME, value=normalized)
            if payload.admin_password is not None and payload.admin_password.strip():
                set_app_setting(session, key=SETTING_AUTH_ADMIN_PASSWORD, value=payload.admin_password)
            if payload.ftp_bild_username is not None:
                normalized = payload.ftp_bild_username.strip()
                if not normalized:
                    raise HTTPException(status_code=400, detail="ftp_bild_username cannot be empty")
                set_app_setting(session, key=SETTING_FTP_BILD_USERNAME, value=normalized)
            if payload.ftp_bild_password is not None and payload.ftp_bild_password.strip():
                set_app_setting(session, key=SETTING_FTP_BILD_PASSWORD, value=payload.ftp_bild_password)
            if payload.ftp_photographer_username is not None:
                normalized = payload.ftp_photographer_username.strip()
                if not normalized:
                    raise HTTPException(status_code=400, detail="ftp_photographer_username cannot be empty")
                set_app_setting(
                    session,
                    key=SETTING_FTP_PHOTOGRAPHER_USERNAME,
                    value=normalized,
                )
            if payload.ftp_photographer_password is not None and payload.ftp_photographer_password.strip():
                set_app_setting(session, key=SETTING_FTP_PHOTOGRAPHER_PASSWORD, value=payload.ftp_photographer_password)
            if payload.yandex_oauth_token is not None and payload.yandex_oauth_token.strip():
                set_app_setting(session, key=SETTING_YADISK_OAUTH_TOKEN, value=payload.yandex_oauth_token.strip())
            if payload.yandex_remote_base_path is not None and payload.yandex_remote_base_path.strip():
                set_app_setting(session, key=SETTING_YADISK_REMOTE_BASE, value=payload.yandex_remote_base_path.strip())
            session.commit()

            auth_values = get_runtime_auth_credentials(session)
            ftp_bild_username = get_setting_value(session, SETTING_FTP_BILD_USERNAME, "bild_ftp")
            ftp_bild_password = get_setting_value(session, SETTING_FTP_BILD_PASSWORD, "")
            ftp_photographer_username = get_setting_value(session, SETTING_FTP_PHOTOGRAPHER_USERNAME, "upload")
            ftp_photographer_password = get_setting_value(session, SETTING_FTP_PHOTOGRAPHER_PASSWORD, "")
            yandex_token = get_setting_value(session, SETTING_YADISK_OAUTH_TOKEN, config.yandex_disk.oauth_token)
            yandex_remote_base = get_setting_value(session, SETTING_YADISK_REMOTE_BASE, config.yandex_disk.remote_base_path)

        return AdminSettingsResponse(
            bild_username=auth_values["bild_username"],
            bild_password=auth_values["bild_password"],
            admin_username=auth_values["admin_username"],
            admin_password=auth_values["admin_password"],
            ftp_bild_username=ftp_bild_username,
            ftp_bild_password=ftp_bild_password,
            ftp_bild_password_set=bool(ftp_bild_password),
            ftp_photographer_username=ftp_photographer_username,
            ftp_photographer_password=ftp_photographer_password,
            ftp_photographer_password_set=bool(ftp_photographer_password),
            yandex_token_set=bool(yandex_token),
            yandex_oauth_token=yandex_token,
            yandex_remote_base_path=yandex_remote_base,
        )

    @app.post("/api/admin/apply-ftp", response_model=AdminApplyFtpResponse)
    def apply_admin_ftp_settings(_: AuthUser = Depends(require_admin(config))) -> AdminApplyFtpResponse:
        with session_factory() as session:
            ftp_bild_username = get_setting_value(session, SETTING_FTP_BILD_USERNAME, "bild_ftp").strip()
            ftp_bild_password = get_setting_value(session, SETTING_FTP_BILD_PASSWORD, "")
            ftp_photographer_username = get_setting_value(session, SETTING_FTP_PHOTOGRAPHER_USERNAME, "upload").strip()
            ftp_photographer_password = get_setting_value(session, SETTING_FTP_PHOTOGRAPHER_PASSWORD, "")
        if not ftp_bild_password:
            raise HTTPException(status_code=400, detail="FTP password for bild is empty")
        if not ftp_photographer_password:
            raise HTTPException(status_code=400, detail="FTP password for photographer is empty")
        apply_ftp_runtime_settings(
            ftp_bild_username=ftp_bild_username,
            ftp_bild_password=ftp_bild_password,
            ftp_photographer_username=ftp_photographer_username,
            ftp_photographer_password=ftp_photographer_password,
        )
        return AdminApplyFtpResponse(
            status="ok",
            ftp_bild_username=ftp_bild_username,
            ftp_photographer_username=ftp_photographer_username,
            details="vsftpd users and per-user rules updated",
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
                mark_batch_removed_from_incoming(
                    session,
                    batch_id=batch_id,
                    retention_hours=get_archive_retention_hours(session),
                )
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
                mark_batch_removed_from_incoming(
                    session,
                    batch_id=batch_id,
                    retention_hours=get_archive_retention_hours(session),
                )
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
        with session_factory() as session:
            yandex_cfg = get_runtime_yandex_config(session)
            if not yandex_cfg.enabled:
                raise HTTPException(status_code=400, detail="Yandex Disk integration is disabled")
            batch = get_batch_by_id(session, batch_id)
            if batch is None:
                raise HTTPException(status_code=404, detail="Batch not found")
            photos = get_batch_photos(session, batch.id)
            photographer = get_photographer_by_id(session, batch.photographer_id)
            photographer_name = photographer.folder_name if photographer else "unknown"
            remote_dir = f"{yandex_cfg.remote_base_path.rstrip('/')}/{photographer_name}"
            active_photos = list_active_photos_for_batch(photos, photographer_name)
            source_files = [
                (config.paths.incoming / photographer_name / photo.filename, photo.filename)
                for photo in active_photos
                if (config.paths.incoming / photographer_name / photo.filename).exists()
            ]
            if not source_files:
                raise HTTPException(status_code=404, detail="Batch has no active files in incoming")
        try:
            uploader = YandexDiskUploader(yandex_cfg)
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
        _: AuthUser = Depends(require_admin(config)),
    ) -> YandexDiskAutoModeResponse:
        with session_factory() as session:
            yandex_cfg = get_runtime_yandex_config(session)
            if not yandex_cfg.enabled:
                return YandexDiskAutoModeResponse(enabled=False)
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
                    mark_batch_removed_from_incoming(
                        session,
                        batch_id=batch.id,
                        retention_hours=get_archive_retention_hours(session),
                    )
                    updated += 1
            session.commit()
        return BatchCleanupResponse(status="ok", updated=updated)

    @app.post("/api/yandex/auto-upload", response_model=YandexDiskAutoModeResponse)
    def set_yandex_auto_upload(
        payload: YandexDiskAutoModeRequest,
        _: AuthUser = Depends(require_admin(config)),
    ) -> YandexDiskAutoModeResponse:
        with session_factory() as session:
            yandex_cfg = get_runtime_yandex_config(session)
            if payload.enabled and not yandex_cfg.enabled:
                raise HTTPException(status_code=400, detail="Yandex Disk integration is disabled")
            set_app_setting(
                session,
                key="yandex_disk.auto_upload_all",
                value="true" if payload.enabled else "false",
            )
            session.commit()
        return YandexDiskAutoModeResponse(enabled=payload.enabled)

    @app.get("/api/archive/settings", response_model=ArchiveSettingsResponse)
    def get_archive_settings(_: str = Depends(require_auth(config))) -> ArchiveSettingsResponse:
        with session_factory() as session:
            ttl_hours = get_archive_retention_hours(session)
            limit_gb = get_archive_limit_gb(session)
        return ArchiveSettingsResponse(
            ttl_hours=ttl_hours,
            ttl_options_hours=ARCHIVE_TTL_OPTIONS_HOURS,
            limit_gb=limit_gb,
        )

    @app.post("/api/archive/settings", response_model=ArchiveSettingsResponse)
    def update_archive_settings(
        payload: ArchiveSettingsUpdateRequest,
        _: str = Depends(require_auth(config)),
    ) -> ArchiveSettingsResponse:
        if payload.ttl_hours not in ARCHIVE_TTL_OPTIONS_HOURS:
            raise HTTPException(status_code=400, detail="Unsupported TTL value")
        with session_factory() as session:
            ttl_hours = set_archive_retention_hours(session, payload.ttl_hours)
            limit_gb = set_archive_limit_gb(session, payload.limit_gb)
            session.commit()
        return ArchiveSettingsResponse(
            ttl_hours=ttl_hours,
            ttl_options_hours=ARCHIVE_TTL_OPTIONS_HOURS,
            limit_gb=limit_gb,
        )

    @app.get("/api/archive/usage", response_model=ArchiveUsageResponse)
    def get_archive_usage(_: str = Depends(require_auth(config))) -> ArchiveUsageResponse:
        with session_factory() as session:
            cleaned_batches, deleted_files, deleted_bytes = cleanup_expired_archive(session)
            if cleaned_batches or deleted_files or deleted_bytes:
                session.commit()
            used_bytes = calculate_archive_usage_bytes(session)
            limit_gb = get_archive_limit_gb(session)
        used_gb = round(used_bytes / (1024**3), 2)
        usage_percent = round(min(100.0, (used_gb / limit_gb) * 100 if limit_gb else 0), 1)
        return ArchiveUsageResponse(
            used_bytes=used_bytes,
            used_gb=used_gb,
            limit_gb=limit_gb,
            usage_percent=usage_percent,
        )

    @app.get("/api/archive/batches", response_model=list[ArchiveBatchListItem])
    def get_archive_batches(
        limit: int = Query(default=50, ge=1, le=500),
        _: str = Depends(require_auth(config)),
    ) -> list[ArchiveBatchListItem]:
        with session_factory() as session:
            cleaned_batches, deleted_files, deleted_bytes = cleanup_expired_archive(session)
            if cleaned_batches or deleted_files or deleted_bytes:
                session.commit()
            batches = list_archive_batches(session, limit=limit)
            response: list[ArchiveBatchListItem] = []
            for batch in batches:
                photos = get_batch_photos(session, batch.id)
                existing_photos = [photo for photo in photos if Path(photo.original_path).exists()]
                if not existing_photos:
                    mark_batch_archived_deleted(session, batch_id=batch.id)
                    continue
                photographer = get_photographer_by_id(session, batch.photographer_id)
                photographer_name = photographer.folder_name if photographer else "unknown"
                daily_sequence = get_batch_daily_sequence(session, batch)
                response.append(
                    ArchiveBatchListItem(
                        id=batch.id,
                        batch_key=batch.batch_key,
                        photographer=photographer_name,
                        file_count=len(existing_photos),
                        broken_files_count=batch.broken_files_count,
                        daily_sequence=daily_sequence,
                        total_size_bytes=sum(photo.size_bytes for photo in existing_photos),
                        archive_name=build_archive_name(photographer_name, batch.captured_at, daily_sequence),
                        captured_at=batch.captured_at,
                        removed_from_incoming_at=batch.removed_from_incoming_at or batch.created_at,
                        archive_expires_at=batch.archive_expires_at or batch.created_at,
                    )
                )
            session.commit()
            return response

    @app.get("/api/archive/batches/{batch_id}", response_model=ArchiveBatchDetail)
    def get_archive_batch_detail(
        batch_id: str,
        _: str = Depends(require_auth(config)),
    ) -> ArchiveBatchDetail:
        with session_factory() as session:
            cleaned_batches, deleted_files, deleted_bytes = cleanup_expired_archive(session)
            if cleaned_batches or deleted_files or deleted_bytes:
                session.commit()
            batch = get_batch_by_id(session, batch_id)
            if batch is None or batch.status == "archived_deleted":
                raise HTTPException(status_code=404, detail="Archive batch not found")
            photos = get_batch_photos(session, batch.id)
            existing_photos = [photo for photo in photos if Path(photo.original_path).exists()]
            if not existing_photos:
                mark_batch_archived_deleted(session, batch_id=batch.id)
                session.commit()
                raise HTTPException(status_code=404, detail="Archive files are missing")
            photographer = get_photographer_by_id(session, batch.photographer_id)
            photographer_name = photographer.folder_name if photographer else "unknown"
            daily_sequence = get_batch_daily_sequence(session, batch)
            return ArchiveBatchDetail(
                id=batch.id,
                batch_key=batch.batch_key,
                photographer=photographer_name,
                file_count=len(existing_photos),
                broken_files_count=batch.broken_files_count,
                daily_sequence=daily_sequence,
                total_size_bytes=sum(photo.size_bytes for photo in existing_photos),
                archive_name=build_archive_name(photographer_name, batch.captured_at, daily_sequence),
                captured_at=batch.captured_at,
                removed_from_incoming_at=batch.removed_from_incoming_at or batch.created_at,
                archive_expires_at=batch.archive_expires_at or batch.created_at,
                photos=[
                    BatchPhotoItem(
                        id=photo.id,
                        filename=photo.filename,
                        size_bytes=photo.size_bytes,
                        original_path=photo.original_path,
                        image_url=f"/api/photos/{photo.id}/content",
                        thumbnail_url=f"/api/photos/{photo.id}/thumbnail",
                    )
                    for photo in existing_photos
                ],
            )

    @app.get("/api/archive/batches/{batch_id}/download")
    def download_archive_batch_zip(
        batch_id: str,
        _: str = Depends(require_auth(config)),
    ) -> FileResponse:
        with session_factory() as session:
            batch = get_batch_by_id(session, batch_id)
            if batch is None:
                raise HTTPException(status_code=404, detail="Batch not found")
            if batch.status == "archived_deleted":
                raise HTTPException(status_code=404, detail="Archive batch not found")
            if batch.archive_expires_at and batch.archive_expires_at <= datetime.now(tz=timezone.utc):
                raise HTTPException(status_code=410, detail="Archive retention expired")
            photos = get_batch_photos(session, batch.id)
            zip_sources = collect_archive_file_sources(photos)
            if not zip_sources:
                mark_batch_archived_deleted(session, batch_id=batch.id)
                session.commit()
                raise HTTPException(status_code=404, detail="Archive files are missing")
            photographer = get_photographer_by_id(session, batch.photographer_id)
            photographer_name = photographer.folder_name if photographer else "unknown"
            daily_sequence = get_batch_daily_sequence(session, batch)
            filename = build_archive_name(photographer_name, batch.captured_at, daily_sequence)
            temp_zip_path = build_batch_zip(zip_sources)
        return FileResponse(
            path=temp_zip_path,
            media_type="application/zip",
            filename=filename,
            background=BackgroundTask(lambda path: Path(path).unlink(missing_ok=True), str(temp_zip_path)),
        )

    @app.post("/api/archive/batches/{batch_id}/download-selected")
    def download_selected_archive_batch_zip(
        batch_id: str,
        payload: BatchSelectedDownloadRequest,
        _: str = Depends(require_auth(config)),
    ) -> FileResponse:
        selected_ids = {item for item in payload.photo_ids if item}
        if not selected_ids:
            raise HTTPException(status_code=400, detail="photo_ids is empty")
        with session_factory() as session:
            batch = get_batch_by_id(session, batch_id)
            if batch is None or batch.status == "archived_deleted":
                raise HTTPException(status_code=404, detail="Archive batch not found")
            if batch.archive_expires_at and batch.archive_expires_at <= datetime.now(tz=timezone.utc):
                raise HTTPException(status_code=410, detail="Archive retention expired")
            photos = get_batch_photos(session, batch.id)
            selected_photos = [photo for photo in photos if photo.id in selected_ids and Path(photo.original_path).exists()]
            if not selected_photos:
                raise HTTPException(status_code=400, detail="Selected archive photos are unavailable")
            zip_sources = collect_archive_file_sources(selected_photos)
            if not zip_sources:
                raise HTTPException(status_code=404, detail="No readable selected archive files")
            photographer = get_photographer_by_id(session, batch.photographer_id)
            photographer_name = photographer.folder_name if photographer else "unknown"
            daily_sequence = get_batch_daily_sequence(session, batch)
            captured_at = batch.captured_at
            selected_counter = increment_daily_counter(
                session,
                key_prefix="downloads.archive_selected.counter",
                day_key=captured_at.strftime("%Y%m%d"),
            )
            temp_zip_path = build_batch_zip(zip_sources)
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

    @app.post("/api/archive/clear", response_model=ArchiveClearResponse)
    def clear_archive(_: str = Depends(require_auth(config))) -> ArchiveClearResponse:
        with session_factory() as session:
            batches = list_archive_batches(session, limit=5000)
            cleared_batches = 0
            deleted_files = 0
            deleted_bytes = 0
            for batch in batches:
                photos = get_batch_photos(session, batch.id)
                for photo in photos:
                    source = Path(photo.original_path)
                    if source.exists():
                        deleted_bytes += source.stat().st_size
                        source.unlink()
                        deleted_files += 1
                mark_batch_archived_deleted(session, batch_id=batch.id)
                cleared_batches += 1
            session.commit()
        return ArchiveClearResponse(
            status="ok",
            cleared_batches=cleared_batches,
            deleted_files=deleted_files,
            deleted_bytes=deleted_bytes,
        )

    @app.get("/api/notifications", response_model=list[NotificationItem])
    def get_notifications(
        limit: int = Query(default=50, ge=1, le=500),
        _: str = Depends(require_auth(config)),
    ) -> list[NotificationItem]:
        with session_factory() as session:
            entities = list_recent_notifications(session, limit=limit)
            result: list[NotificationItem] = []
            for item in entities:
                batch_key: str | None = None
                file_count: int | None = None
                total_size_bytes: int | None = None
                daily_sequence: int | None = None
                captured_at: datetime | None = None
                if item.batch_id:
                    batch = get_batch_by_id(session, item.batch_id)
                    if batch is not None:
                        batch_key = batch.batch_key
                        file_count = batch.file_count
                        total_size_bytes = batch.total_size_bytes
                        daily_sequence = get_batch_daily_sequence(session, batch)
                        captured_at = batch.captured_at
                result.append(
                    NotificationItem(
                        id=item.id,
                        kind=item.kind,
                        title=item.title,
                        message=item.message,
                        channel=item.channel,
                        status=item.status,
                        batch_id=item.batch_id,
                        batch_key=batch_key,
                        file_count=file_count,
                        total_size_bytes=total_size_bytes,
                        daily_sequence=daily_sequence,
                        captured_at=captured_at,
                        photographer=item.photographer,
                        created_at=item.created_at,
                    )
                )
            return result

    @app.post("/api/notifications/clear", response_model=NotificationClearResponse)
    def clear_notifications(
        _: str = Depends(require_auth(config)),
    ) -> NotificationClearResponse:
        with session_factory() as session:
            deleted = delete_all_notifications(session)
            session.commit()
        return NotificationClearResponse(status="ok", deleted=deleted)

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
