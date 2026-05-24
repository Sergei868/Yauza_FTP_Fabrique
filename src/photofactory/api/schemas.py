"""Pydantic response schemas for API endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class BatchListItem(BaseModel):
    id: str
    batch_key: str
    photographer: str
    status: str
    file_count: int
    broken_files_count: int
    daily_sequence: int
    total_size_bytes: int
    archive_name: str
    captured_at: datetime
    created_at: datetime
    photos: list["BatchListPhotoItem"] | None = None


class BatchListPhotoItem(BaseModel):
    id: str
    filename: str
    size_bytes: int
    image_url: str
    thumbnail_url: str


class BatchPhotoItem(BaseModel):
    id: str
    filename: str
    size_bytes: int
    original_path: str
    image_url: str
    thumbnail_url: str


class BatchDetail(BaseModel):
    id: str
    batch_key: str
    photographer: str
    status: str
    file_count: int
    broken_files_count: int
    daily_sequence: int
    total_size_bytes: int
    archive_name: str
    silence_age_seconds: int
    originals_path: str
    backup_path: str
    captured_at: datetime
    created_at: datetime
    photos: list[BatchPhotoItem]


class ArchiveBatchListItem(BaseModel):
    id: str
    batch_key: str
    photographer: str
    file_count: int
    broken_files_count: int
    daily_sequence: int
    total_size_bytes: int
    archive_name: str
    captured_at: datetime
    removed_from_incoming_at: datetime
    archive_expires_at: datetime


class ArchiveBatchDetail(BaseModel):
    id: str
    batch_key: str
    photographer: str
    file_count: int
    broken_files_count: int
    daily_sequence: int
    total_size_bytes: int
    archive_name: str
    captured_at: datetime
    removed_from_incoming_at: datetime
    archive_expires_at: datetime
    photos: list[BatchPhotoItem]


class ArchiveUsageResponse(BaseModel):
    used_bytes: int
    used_gb: float
    limit_gb: int
    usage_percent: float


class ArchiveSettingsResponse(BaseModel):
    ttl_hours: int
    ttl_options_hours: list[int]
    limit_gb: int


class ArchiveSettingsUpdateRequest(BaseModel):
    ttl_hours: int
    limit_gb: int


class ArchiveClearResponse(BaseModel):
    status: str
    cleared_batches: int
    deleted_files: int
    deleted_bytes: int


class HealthResponse(BaseModel):
    status: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    role: str


class AuthMeResponse(BaseModel):
    username: str
    role: str


class AdminSettingsResponse(BaseModel):
    bild_username: str
    bild_password: str | None = None
    admin_username: str
    admin_password: str | None = None
    ftp_bild_username: str
    ftp_bild_password: str | None = None
    ftp_bild_password_set: bool
    ftp_photographer_username: str
    ftp_photographer_password: str | None = None
    ftp_photographer_password_set: bool
    yandex_token_set: bool
    yandex_oauth_token: str | None = None
    yandex_remote_base_path: str


class AdminSettingsUpdateRequest(BaseModel):
    bild_username: str | None = None
    bild_password: str | None = None
    admin_username: str | None = None
    admin_password: str | None = None
    ftp_bild_username: str | None = None
    ftp_bild_password: str | None = None
    ftp_photographer_username: str | None = None
    ftp_photographer_password: str | None = None
    yandex_oauth_token: str | None = None
    yandex_remote_base_path: str | None = None


class AdminRevealSecretsRequest(BaseModel):
    admin_password: str


class AdminRevealSecretsResponse(BaseModel):
    bild_password: str | None = None
    admin_password: str | None = None
    ftp_bild_password: str | None = None
    ftp_photographer_password: str | None = None
    yandex_oauth_token: str | None = None
    expires_in_seconds: int


class AdminApplyFtpResponse(BaseModel):
    status: str
    ftp_bild_username: str
    ftp_photographer_username: str
    details: str


class NotificationItem(BaseModel):
    id: str
    kind: str
    title: str
    message: str
    channel: str
    status: str
    batch_id: str | None
    batch_key: str | None = None
    file_count: int | None = None
    total_size_bytes: int | None = None
    daily_sequence: int | None = None
    captured_at: datetime | None = None
    photographer: str | None
    created_at: datetime


class NotificationClearResponse(BaseModel):
    status: str
    deleted: int


class SmokeBatchRequest(BaseModel):
    photographer: str = "BildSmoke"
    filename: str = "SMOKE.jpg"
    content: str = "bild-smoke"


class SmokeBatchResponse(BaseModel):
    status: str
    photographer: str
    file_path: str


class YandexDiskUploadResponse(BaseModel):
    status: str
    batch_id: str
    remote_path: str
    uploaded_files: int


class YandexDiskAutoModeRequest(BaseModel):
    enabled: bool


class YandexDiskAutoModeResponse(BaseModel):
    enabled: bool


class IncomingPhotographerItem(BaseModel):
    folder_name: str
    file_count: int


class BatchCleanupResponse(BaseModel):
    status: str
    updated: int


class BatchSelectedDownloadRequest(BaseModel):
    photo_ids: list[str]


class PushSubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionUpsertRequest(BaseModel):
    endpoint: str
    keys: PushSubscriptionKeys
    user_agent: str | None = None


class PushSubscriptionDeleteRequest(BaseModel):
    endpoint: str


class PushSubscriptionResponse(BaseModel):
    status: str
    endpoint: str


class PwaTestPushRequest(BaseModel):
    title: str
    body: str


class PwaTestPushResponse(BaseModel):
    status: str
    sent: int
    failed: int
    deactivated: int
