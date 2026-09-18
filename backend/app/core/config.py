"""Application settings, loaded from environment variables."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent


def _insforge_project_defaults() -> dict[str, str]:
    """Read .insforge/project.json when present (local dev convenience).

    In production these values come from environment variables instead; this
    file is git-ignored and never shipped.
    """
    candidate = REPO_ROOT / ".insforge" / "project.json"
    try:
        data = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {
        "url": str(data.get("oss_host", "")),
        "api_key": str(data.get("api_key", "")),
    }


_DEFAULTS = _insforge_project_defaults()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env.local", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App -----------------------------------------------------------------
    app_name: str = "ReqGuard AI"
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")

    # --- CORS ----------------------------------------------------------------
    # Comma-separated list. Wildcards are deliberately not the default.
    cors_origins: str = Field(default="http://localhost:5173,http://127.0.0.1:5173")

    # --- InsForge (database + storage) --------------------------------------
    insforge_url: str = Field(default=_DEFAULTS.get("url", ""))
    insforge_api_key: str = Field(default=_DEFAULTS.get("api_key", ""))
    insforge_storage_bucket: str = Field(default="reqguard-documents")
    # When storage upload is unavailable the parsed text still flows through the
    # pipeline; the raw file is simply not retained.
    storage_enabled: bool = Field(default=True)

    # --- LLM -----------------------------------------------------------------
    # "groq" is the documented default. "openrouter" exists so the pipeline can
    # run against the InsForge AI gateway when no Groq key is provisioned.
    llm_provider: str = Field(default="groq")
    groq_api_key: str = Field(default="")
    groq_model: str = Field(default="openai/gpt-oss-20b")
    # Hidden reasoning is most of a gpt-oss call's tokens, and free-tier keys
    # have a daily token quota. "" leaves the provider default. gpt-oss models
    # accept low/medium/high; qwen models accept none/default.
    groq_reasoning_effort: str = Field(default="")
    openrouter_api_key: str = Field(default="")
    openrouter_model: str = Field(default="openai/gpt-4o-mini")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1")
    llm_timeout_seconds: float = Field(default=90.0)
    llm_max_retries: int = Field(default=2)
    # Total time one call may spend waiting out provider rate limits. Per-minute
    # token limits reset within 60 s; anything longer is a daily quota.
    llm_rate_limit_wait_seconds: float = Field(default=180.0)
    llm_temperature: float = Field(default=0.0)

    # --- Embeddings ----------------------------------------------------------
    embedding_model_name: str = Field(default="BAAI/bge-small-en-v1.5")
    embedding_dimensions: int = Field(default=384)
    # Candidate-pair thresholds. Configurable on purpose: no single threshold is
    # universally correct across requirement styles.
    duplicate_similarity_threshold: float = Field(default=0.82)
    contradiction_similarity_threshold: float = Field(default=0.70)
    dependency_similarity_threshold: float = Field(default=0.35)
    max_candidate_pairs: int = Field(default=300)

    # Confidence floors for reporting a finding. A weaker classification needs a
    # higher bar: "partial_conflict" and "overlapping" are where most low-value
    # noise appears, while a full contradiction/duplicate verdict is reported
    # whenever the model is reasonably sure.
    min_confidence_contradiction: float = Field(default=0.60)
    min_confidence_partial_conflict: float = Field(default=0.85)
    min_confidence_duplicate: float = Field(default=0.60)
    min_confidence_overlapping: float = Field(default=0.75)
    min_confidence_dependency: float = Field(default=0.40)

    # --- Uploads -------------------------------------------------------------
    max_upload_bytes: int = Field(default=15 * 1024 * 1024)
    allowed_extensions: str = Field(default="pdf,docx,txt")

    # --- Analysis limits -----------------------------------------------------
    max_requirements: int = Field(default=400)
    extraction_chunk_chars: int = Field(default=9000)

    @field_validator("llm_provider")
    @classmethod
    def _normalise_provider(cls, value: str) -> str:
        provider = value.strip().lower()
        if provider not in {"groq", "openrouter"}:
            raise ValueError("LLM_PROVIDER must be 'groq' or 'openrouter'")
        return provider

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def allowed_extension_set(self) -> set[str]:
        return {ext.strip().lower().lstrip(".") for ext in self.allowed_extensions.split(",") if ext.strip()}

    @property
    def database_configured(self) -> bool:
        return bool(self.insforge_url and self.insforge_api_key)

    @property
    def llm_configured(self) -> bool:
        if self.llm_provider == "groq":
            return bool(self.groq_api_key)
        return bool(self.openrouter_api_key)

    @property
    def active_llm_model(self) -> str:
        return self.groq_model if self.llm_provider == "groq" else self.openrouter_model


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
