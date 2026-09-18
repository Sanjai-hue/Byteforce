"""ReqGuard AI — FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_documents, routes_refinements
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.database.client import InsForgeClient
from app.services.embedding_service import get_embedding_service
from app.services.storage_service import build_storage

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
)
logger = logging.getLogger("reqguard")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pending_uploads = {}
    app.state.ai = None

    # Database
    app.state.db = InsForgeClient(settings)
    try:
        await app.state.db.connect()
        logger.info("database client ready")
    except Exception as exc:
        logger.error("database unavailable at startup: %s", exc)

    # Storage
    app.state.storage = build_storage(settings)

    # Embedding model: loaded once, here, not per request.
    embeddings = get_embedding_service()
    try:
        embeddings.load()
    except Exception as exc:
        logger.error("embedding model unavailable at startup: %s", exc)

    if not settings.llm_configured:
        logger.warning(
            "no API key set for LLM provider '%s' — analysis will return a clear error until one is added",
            settings.llm_provider,
        )

    yield

    await app.state.db.close()
    await app.state.storage.close()
    if app.state.ai is not None:
        await app.state.ai.close()


app = FastAPI(
    title="ReqGuard AI",
    description="AI requirements-engineering agent: find requirement problems before they become software problems.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(routes_documents.router)
app.include_router(routes_refinements.router)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    """Liveness probe for Render/Railway."""
    return {"status": "ok"}


@app.get("/api/system/status", tags=["system"])
async def system_status() -> dict[str, Any]:
    """Readiness detail: which dependencies are actually usable."""
    embeddings = get_embedding_service()
    database_ok = False
    if getattr(app.state, "db", None) is not None:
        database_ok = await app.state.db.health()

    return {
        "status": "ok",
        "database": {"configured": settings.database_configured, "reachable": database_ok},
        "embeddings": {
            "model": settings.embedding_model_name,
            "dimensions": settings.embedding_dimensions,
            "ready": embeddings.is_ready,
            "error": embeddings.load_error,
        },
        "llm": {
            "provider": settings.llm_provider,
            "model": settings.active_llm_model,
            "configured": settings.llm_configured,
        },
        "thresholds": {
            "duplicate_similarity": settings.duplicate_similarity_threshold,
            "contradiction_similarity": settings.contradiction_similarity_threshold,
            "max_candidate_pairs": settings.max_candidate_pairs,
        },
    }
