"""Yandex Disk uploader for batch files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import httpx

from photofactory.config import YandexDiskConfig


@dataclass(frozen=True)
class YandexUploadResult:
    remote_path: str
    uploaded_files: int


class YandexDiskUploader:
    """Uploads files to Yandex Disk via public HTTP API."""

    API_BASE = "https://cloud-api.yandex.net/v1/disk/resources"

    def __init__(self, config: YandexDiskConfig) -> None:
        token = config.oauth_token.strip()
        if not config.enabled:
            raise ValueError("Yandex Disk is disabled in config")
        if not token:
            raise ValueError("Yandex Disk oauth_token is empty")
        self.config = config
        self.token = token

    def upload_batch_files(
        self,
        *,
        local_files: list[tuple[Path, str]],
        remote_dir: str,
    ) -> YandexUploadResult:
        self._ensure_remote_tree(remote_dir)
        uploaded = 0
        for local_path, remote_name in local_files:
            remote_path = f"{remote_dir.rstrip('/')}/{remote_name}"
            upload_url = self._get_upload_url(remote_path)
            with local_path.open("rb") as file_handle:
                response = httpx.put(upload_url, content=file_handle.read(), timeout=120)
                response.raise_for_status()
            uploaded += 1
        return YandexUploadResult(remote_path=remote_dir, uploaded_files=uploaded)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"OAuth {self.token}"}

    def _ensure_remote_tree(self, remote_dir: str) -> None:
        # Disk API does not create nested directories recursively.
        parts = [part for part in remote_dir.strip("/").split("/") if part]
        current = ""
        for part in parts:
            current = f"{current}/{part}" if current else f"/{part}"
            self._ensure_remote_dir(current)

    def _ensure_remote_dir(self, remote_dir: str) -> None:
        encoded_path = quote(remote_dir, safe="/")
        url = f"{self.API_BASE}?path={encoded_path}"
        response = httpx.put(url, headers=self._headers(), timeout=30)
        if response.status_code == 201:
            return
        if response.status_code == 409:
            verify = httpx.get(url, headers=self._headers(), timeout=30)
            if verify.status_code == 200:
                return
        response.raise_for_status()

    def _get_upload_url(self, remote_path: str) -> str:
        encoded_path = quote(remote_path, safe="/")
        url = f"{self.API_BASE}/upload?path={encoded_path}&overwrite=true"
        response = httpx.get(url, headers=self._headers(), timeout=30)
        response.raise_for_status()
        payload = response.json()
        href = str(payload.get("href", "")).strip()
        if not href:
            raise RuntimeError("Yandex Disk API did not return upload URL")
        return href
