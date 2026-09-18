"""Thin async client over the InsForge PostgREST-style Database API.

The backend is the only writer. It authenticates with the project admin API key,
which bypasses row level security; the public anon key has no policy on any of
these tables and is rejected by Postgres.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Sequence

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import ConfigurationError, DatabaseError

logger = logging.getLogger("reqguard.db")

JsonDict = dict[str, Any]


class InsForgeClient:
    """Async CRUD access to InsForge tables."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client: httpx.AsyncClient | None = None

    # -- lifecycle ----------------------------------------------------------
    async def connect(self) -> None:
        if not self._settings.database_configured:
            raise ConfigurationError(
                "The database is not configured. Set INSFORGE_URL and INSFORGE_API_KEY."
            )
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._settings.insforge_url.rstrip("/"),
                headers={
                    "Authorization": f"Bearer {self._settings.insforge_api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(30.0, connect=10.0),
            )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            raise DatabaseError("Database client used before startup completed.")
        return self._client

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _path(table: str) -> str:
        return f"/api/database/records/{table}"

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self._http.request(method, url, **kwargs)
        except httpx.HTTPError as exc:  # network / timeout
            logger.error("database request failed: %s %s -> %s", method, url, exc)
            raise DatabaseError("Could not reach the database.", detail=str(exc)) from exc

        if response.status_code >= 400:
            # Body may contain schema detail; log it, never return it verbatim.
            logger.error(
                "database error: %s %s -> %s %s",
                method,
                url,
                response.status_code,
                response.text[:800],
            )
            raise DatabaseError(
                "The database rejected the request.",
                detail=f"{response.status_code}: {response.text[:400]}",
            )
        return response

    # -- CRUD ---------------------------------------------------------------
    async def insert(
        self, table: str, rows: Sequence[JsonDict], *, returning: bool = True
    ) -> list[JsonDict]:
        """Insert rows. The InsForge API always expects an array body."""
        if not rows:
            return []
        headers = {"Prefer": "return=representation"} if returning else {}
        response = await self._request(
            "POST", self._path(table), json=list(rows), headers=headers
        )
        if not returning or not response.content:
            return []
        payload = response.json()
        return payload if isinstance(payload, list) else [payload]

    async def insert_one(self, table: str, row: JsonDict) -> JsonDict:
        created = await self.insert(table, [row])
        if not created:
            raise DatabaseError("The database did not return the created row.")
        return created[0]

    async def select(
        self,
        table: str,
        *,
        filters: JsonDict | None = None,
        select: str | None = None,
        order: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[JsonDict]:
        params: dict[str, Any] = {}
        for key, value in (filters or {}).items():
            params[key] = value
        if select:
            params["select"] = select
        if order:
            params["order"] = order
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        response = await self._request("GET", self._path(table), params=params)
        payload = response.json()
        return payload if isinstance(payload, list) else [payload]

    async def update(self, table: str, filters: JsonDict, patch: JsonDict) -> list[JsonDict]:
        response = await self._request(
            "PATCH",
            self._path(table),
            params=filters,
            json=patch,
            headers={"Prefer": "return=representation"},
        )
        if not response.content:
            return []
        payload = response.json()
        return payload if isinstance(payload, list) else [payload]

    async def delete(self, table: str, filters: JsonDict) -> None:
        await self._request("DELETE", self._path(table), params=filters)

    async def health(self) -> bool:
        """Cheap connectivity probe used by /health."""
        try:
            await self.select("documents", select="id", limit=1)
            return True
        except DatabaseError:
            return False


def eq(value: Any) -> str:
    """Build a PostgREST equality filter value."""
    return f"eq.{value}"


def in_list(values: Iterable[Any]) -> str:
    joined = ",".join(str(v) for v in values)
    return f"in.({joined})"


def vector_literal(values: Sequence[float]) -> str:
    """pgvector accepts a bracketed, comma-separated string over HTTP."""
    return "[" + ",".join(f"{float(v):.6f}" for v in values) + "]"
