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


class HealthResponse(BaseModel):
    status: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int


class NotificationItem(BaseModel):
    id: str
    kind: str
    title: str
    message: str
    channel: str
    status: str
    batch_id: str | None
    photographer: str | None
    created_at: datetime


class NotificationMarkReadRequest(BaseModel):
    mode: str = "all"


class NotificationMarkReadResponse(BaseModel):
    status: str
    updated: int


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
