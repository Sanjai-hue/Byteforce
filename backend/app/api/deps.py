"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.ai.ai_service import AIService
from app.core.config import Settings, get_settings
from app.core.errors import ConfigurationError
from app.database.client import InsForgeClient
from app.database.repositories import Repositories
from app.services.embedding_service import EmbeddingService, get_embedding_service
from app.services.storage_service import StorageBackend
from app.services.traceability_service import TraceabilityService


def get_db(request: Request) -> InsForgeClient:
    client: InsForgeClient | None = getattr(request.app.state, "db", None)
    if client is None:
        raise ConfigurationError("The database is not available.")
    return client


def get_repositories(db: Annotated[InsForgeClient, Depends(get_db)]) -> Repositories:
    return Repositories(db)


def get_storage(request: Request) -> StorageBackend:
    storage: StorageBackend | None = getattr(request.app.state, "storage", None)
    if storage is None:
        raise ConfigurationError("Storage is not available.")
    return storage


def get_embeddings() -> EmbeddingService:
    return get_embedding_service()


def get_ai_service(request: Request) -> AIService:
    """Build the AI service lazily so the app still starts without a key."""
    service: AIService | None = getattr(request.app.state, "ai", None)
    if service is None:
        settings = get_settings()
        if not settings.llm_configured:
            raise ConfigurationError(
                f"No API key is configured for the '{settings.llm_provider}' provider. "
                "Set it in the backend environment to run analysis."
            )
        service = AIService(settings=settings)
        request.app.state.ai = service
    return service


def get_traceability(
    repos: Annotated[Repositories, Depends(get_repositories)],
) -> TraceabilityService:
    return TraceabilityService(repos)


SettingsDep = Annotated[Settings, Depends(get_settings)]
ReposDep = Annotated[Repositories, Depends(get_repositories)]
StorageDep = Annotated[StorageBackend, Depends(get_storage)]
EmbeddingsDep = Annotated[EmbeddingService, Depends(get_embeddings)]
AIDep = Annotated[AIService, Depends(get_ai_service)]
TraceabilityDep = Annotated[TraceabilityService, Depends(get_traceability)]
