"""Persistence helpers for watcher batches."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from datetime import timezone

from photofactory.db.models import AppSetting, Batch, Notification, Photo, Photographer, PushSubscription


def get_or_create_photographer(session: Session, folder_name: str) -> Photographer:
    query = select(Photographer).where(Photographer.folder_name == folder_name)
    entity = session.execute(query).scalar_one_or_none()
    if entity is not None:
        return entity
    entity = Photographer(folder_name=folder_name)
    session.add(entity)
    session.flush()
    return entity


def create_batch_with_photos(
    session: Session,
    *,
    batch_key: str,
    photographer_folder_name: str,
    originals_dir: Path,
    backup_dir: Path,
    captured_at: datetime,
    silence_age_seconds: int,
    files: list[tuple[str, int]],
    broken_files_count: int = 0,
) -> Batch:
    photographer = get_or_create_photographer(session, photographer_folder_name)
    batch = Batch(
        batch_key=batch_key,
        photographer_id=photographer.id,
        status="fixed",
        originals_path=str(originals_dir),
        backup_path=str(backup_dir),
        file_count=len(files),
        broken_files_count=broken_files_count,
        total_size_bytes=sum(size for _, size in files),
        silence_age_seconds=silence_age_seconds,
        captured_at=captured_at,
    )
    session.add(batch)
    session.flush()

    for filename, size in files:
        session.add(
            Photo(
                batch_id=batch.id,
                filename=filename,
                original_path=str(originals_dir / filename),
                backup_path=str(backup_dir / filename),
                size_bytes=size,
            )
        )
    session.flush()
    return batch


def list_recent_batches(
    session: Session,
    limit: int = 100,
    include_downloaded: bool = False,
) -> list[Batch]:
    query = select(Batch)
    if not include_downloaded:
        query = query.where(Batch.status != "downloaded")
    query = query.order_by(Batch.created_at.desc()).limit(limit)
    return list(session.execute(query).scalars())


def get_batch_by_id(session: Session, batch_id: str) -> Batch | None:
    query = select(Batch).where(Batch.id == batch_id)
    return session.execute(query).scalar_one_or_none()


def mark_batch_downloaded(session: Session, batch_id: str) -> bool:
    batch = get_batch_by_id(session, batch_id)
    if batch is None:
        return False
    batch.status = "downloaded"
    session.flush()
    return True


def get_batch_by_key(session: Session, batch_key: str) -> Batch | None:
    query = select(Batch).where(Batch.batch_key == batch_key)
    return session.execute(query).scalar_one_or_none()


def get_batch_photos(session: Session, batch_id: str) -> list[Photo]:
    query = (
        select(Photo)
        .where(Photo.batch_id == batch_id)
        .order_by(Photo.created_at.asc())
    )
    return list(session.execute(query).scalars())


def get_photo_by_id(session: Session, photo_id: str) -> Photo | None:
    query = select(Photo).where(Photo.id == photo_id)
    return session.execute(query).scalar_one_or_none()


def get_photographer_by_id(session: Session, photographer_id: str) -> Photographer | None:
    query = select(Photographer).where(Photographer.id == photographer_id)
    return session.execute(query).scalar_one_or_none()


def create_in_app_batch_notification(
    session: Session,
    *,
    batch_id: str,
    batch_key: str,
    photographer: str,
    file_count: int,
    total_size_bytes: int,
) -> Notification:
    entity = Notification(
        kind="batch_finalized",
        title="Новая пачка",
        message=(
            f"Фотограф {photographer}: пачка {batch_key}, "
            f"{file_count} фото, {total_size_bytes} байт"
        ),
        channel="in_app",
        status="ready",
        batch_id=batch_id,
        photographer=photographer,
    )
    session.add(entity)
    session.flush()
    return entity


def list_recent_notifications(session: Session, limit: int = 100) -> list[Notification]:
    query = (
        select(Notification)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    return list(session.execute(query).scalars())


def mark_all_notifications_read(session: Session) -> int:
    query = select(Notification).where(Notification.status != "read")
    entities = list(session.execute(query).scalars())
    for item in entities:
        item.status = "read"
    session.flush()
    return len(entities)


def create_or_update_push_subscription(
    session: Session,
    *,
    endpoint: str,
    p256dh: str,
    auth: str,
    user_agent: str | None,
) -> PushSubscription:
    query = select(PushSubscription).where(PushSubscription.endpoint == endpoint)
    entity = session.execute(query).scalar_one_or_none()
    if entity is None:
        entity = PushSubscription(
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            user_agent=user_agent,
            is_active=True,
        )
        session.add(entity)
        session.flush()
        return entity

    entity.p256dh = p256dh
    entity.auth = auth
    entity.user_agent = user_agent
    entity.is_active = True
    entity.updated_at = datetime.now(tz=timezone.utc)
    session.flush()
    return entity


def deactivate_push_subscription(session: Session, endpoint: str) -> bool:
    query = select(PushSubscription).where(PushSubscription.endpoint == endpoint)
    entity = session.execute(query).scalar_one_or_none()
    if entity is None:
        return False
    entity.is_active = False
    entity.updated_at = datetime.now(tz=timezone.utc)
    session.flush()
    return True


def list_active_push_subscriptions(session: Session) -> list[PushSubscription]:
    query = select(PushSubscription).where(PushSubscription.is_active.is_(True))
    return list(session.execute(query).scalars())


def get_batch_daily_sequence(session: Session, batch: Batch) -> int:
    captured = batch.captured_at
    day_start = captured.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    query = select(func.count(Batch.id)).where(
        and_(
            Batch.captured_at >= day_start,
            Batch.captured_at < day_end,
            Batch.captured_at <= captured,
        )
    )
    return int(session.execute(query).scalar_one())


def get_app_setting(session: Session, key: str, default: str = "") -> str:
    query = select(AppSetting).where(AppSetting.key == key)
    entity = session.execute(query).scalar_one_or_none()
    if entity is None:
        return default
    return entity.value


def set_app_setting(session: Session, key: str, value: str) -> AppSetting:
    query = select(AppSetting).where(AppSetting.key == key)
    entity = session.execute(query).scalar_one_or_none()
    if entity is None:
        entity = AppSetting(key=key, value=value, updated_at=datetime.now(tz=timezone.utc))
        session.add(entity)
    else:
        entity.value = value
        entity.updated_at = datetime.now(tz=timezone.utc)
    session.flush()
    return entity
