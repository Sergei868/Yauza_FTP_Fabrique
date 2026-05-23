"""Batch-related helpers shared by API and watcher."""

from __future__ import annotations

import tempfile
import zipfile
from datetime import datetime
from pathlib import Path


def build_archive_name(
    photographer_name: str,
    captured_at: datetime,
    daily_sequence: int,
) -> str:
    return f"{photographer_name}-{captured_at:%d}-{captured_at:%m}-{captured_at:%H%M}-{daily_sequence:03d}.zip"


def build_selected_archive_name(
    photographer_name: str,
    captured_at: datetime,
    *,
    daily_selected_counter: int,
    daily_sequence: int,
) -> str:
    return (
        f"{photographer_name}-{captured_at:%d}-{captured_at:%m}-{captured_at:%H%M}-"
        f"selected_{daily_selected_counter:03d}-{daily_sequence:03d}.zip"
    )


def build_batch_zip(file_paths: list[tuple[Path, str]]) -> Path:
    temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    temp_zip_path = Path(temp_zip.name)
    temp_zip.close()
    with zipfile.ZipFile(temp_zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source_path, arcname in file_paths:
            if source_path.exists():
                archive.write(source_path, arcname=arcname)
    return temp_zip_path
