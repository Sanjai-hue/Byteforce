"""Document storage behind one interface.

InsForge Storage is the intended backend. A local-disk implementation exists so
the pipeline still runs when storage is not reachable — the analysis only needs
the parsed text, so a storage outage degrades retention, not functionality.
"""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

import httpx

from app.core.config import Settings, get_settings

logger = logging.getLogger("reqguard.storage")


class StorageBackend(ABC):
    @abstractmethod
    async def upload(self, data: bytes, filename: str, content_type: str) -> tuple[str | None, str | None]:
        """Return (public_or_signed_url, storage_key). Either may be None."""

    @abstractmethod
    async def close(self) -> None: ...


class InsForgeStorage(StorageBackend):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._bucket = settings.insforge_storage_bucket
        self._client = httpx.AsyncClient(
            base_url=settings.insforge_url.rstrip("/"),
            headers={"Authorization": f"Bearer {settings.insforge_api_key}"},
            timeout=httpx.Timeout(60.0, connect=10.0),
        )

    async def upload(self, data: bytes, filename: str, content_type: str) -> tuple[str | None, str | None]:
        key = f"{uuid.uuid4().hex}_{filename}"
        try:
            response = await self._client.post(
                f"/api/storage/buckets/{self._bucket}/objects/{key}",
                files={"file": (filename, data, content_type)},
            )
        except httpx.HTTPError as exc:
            logger.warning("storage upload failed (network): %s", exc)
            return None, None

        if response.status_code >= 400:
            logger.warning(
                "storage upload failed: %s %s", response.status_code, response.text[:300]
            )
            return None, None

        try:
            payload = response.json()
        except ValueError:
            payload = {}
        url = payload.get("url") or payload.get("publicUrl") or payload.get("signedUrl")
        return url, payload.get("key", key)

    async def close(self) -> None:
        await self._client.aclose()


class LocalStorage(StorageBackend):
    """Fallback that keeps uploads on the backend's own disk."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    async def upload(self, data: bytes, filename: str, content_type: str) -> tuple[str | None, str | None]:
        key = f"{uuid.uuid4().hex}_{filename}"
        try:
            (self._root / key).write_bytes(data)
        except OSError as exc:
            logger.warning("local storage write failed: %s", exc)
            return None, None
        return None, key

    async def close(self) -> None:
        return None


def build_storage(settings: Settings | None = None) -> StorageBackend:
    settings = settings or get_settings()
    if settings.storage_enabled and settings.database_configured:
        return InsForgeStorage(settings)
    from app.core.config import BACKEND_DIR

    return LocalStorage(BACKEND_DIR / "var" / "uploads")
