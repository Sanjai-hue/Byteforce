"""AIService — the only place in the application that talks to an LLM.

Every method: build a focused prompt, call the model, parse the JSON, validate it
against a Pydantic schema. On invalid JSON it retries once with a correction
prompt; if that also fails the stage raises. It never falls back to fabricated
findings.
"""

from __future__ import annotations

import logging
from typing import Sequence, TypeVar

from pydantic import BaseModel, ValidationError

from app.ai import prompts
from app.ai.llm_client import LLMClient, build_llm_client, extract_json_object
from app.core.config import Settings, get_settings
from app.core.errors import AIResponseInvalid
from app.schemas.ai_outputs import (
    AmbiguityResult,
    ContradictionResult,
    DependencyResult,
    DuplicateResult,
    ExtractionResult,
    MissingInfoResult,
    RefinementResult,
)

logger = logging.getLogger("reqguard.ai")

TModel = TypeVar("TModel", bound=BaseModel)


class AIService:
    def __init__(self, client: LLMClient | None = None, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = client or build_llm_client(self._settings)

    @property
    def model_name(self) -> str:
        return self._client.model

    async def close(self) -> None:
        await self._client.close()

    # -- core call ----------------------------------------------------------
    async def _call(self, system: str, user: str, schema: type[TModel], *, stage: str) -> TModel:
        raw = await self._client.complete(
            system, user, temperature=self._settings.llm_temperature
        )

        parsed, error = self._try_parse(raw, schema)
        if parsed is not None:
            return parsed

        logger.warning("%s: invalid AI response, retrying with correction (%s)", stage, error)
        correction = prompts.CORRECTION_USER.format(error=error)
        raw_retry = await self._client.complete(
            system, f"{user}\n\n{correction}", temperature=self._settings.llm_temperature
        )
        parsed_retry, retry_error = self._try_parse(raw_retry, schema)
        if parsed_retry is not None:
            return parsed_retry

        logger.error("%s: AI response still invalid after retry (%s)", stage, retry_error)
        raise AIResponseInvalid(
            f"The AI response for {stage} could not be read. This analysis stage failed.",
            detail=retry_error,
        )

    @staticmethod
    def _try_parse(raw: str, schema: type[TModel]) -> tuple[TModel | None, str]:
        try:
            payload = extract_json_object(raw)
        except ValueError as exc:
            return None, str(exc)
        try:
            return schema.model_validate(payload), ""
        except ValidationError as exc:
            return None, exc.errors(include_url=False).__str__()[:400]

    # -- stages -------------------------------------------------------------
    async def extract_requirements(self, chunk: str, section_hint: str = "unknown") -> ExtractionResult:
        return await self._call(
            prompts.EXTRACTION_SYSTEM,
            prompts.EXTRACTION_USER.format(chunk=chunk, section_hint=section_hint),
            ExtractionResult,
            stage="requirement extraction",
        )

    async def detect_ambiguity(self, requirements_block: str) -> AmbiguityResult:
        return await self._call(
            prompts.AMBIGUITY_SYSTEM,
            prompts.AMBIGUITY_USER.format(requirements_block=requirements_block),
            AmbiguityResult,
            stage="ambiguity detection",
        )

    async def verify_duplicate(self, pairs_block: str) -> DuplicateResult:
        return await self._call(
            prompts.DUPLICATE_SYSTEM,
            prompts.DUPLICATE_USER.format(pairs_block=pairs_block),
            DuplicateResult,
            stage="duplicate verification",
        )

    async def verify_contradiction(self, pairs_block: str) -> ContradictionResult:
        return await self._call(
            prompts.CONTRADICTION_SYSTEM,
            prompts.CONTRADICTION_USER.format(pairs_block=pairs_block),
            ContradictionResult,
            stage="contradiction verification",
        )

    async def analyze_dependencies(self, requirements_block: str) -> DependencyResult:
        return await self._call(
            prompts.DEPENDENCY_SYSTEM,
            prompts.DEPENDENCY_USER.format(requirements_block=requirements_block),
            DependencyResult,
            stage="dependency analysis",
        )

    async def analyze_missing_information(self, requirements_block: str) -> MissingInfoResult:
        return await self._call(
            prompts.MISSING_INFO_SYSTEM,
            prompts.MISSING_INFO_USER.format(requirements_block=requirements_block),
            MissingInfoResult,
            stage="missing information analysis",
        )

    async def generate_refinement(self, requirements_block: str) -> RefinementResult:
        return await self._call(
            prompts.REFINEMENT_SYSTEM,
            prompts.REFINEMENT_USER.format(requirements_block=requirements_block),
            RefinementResult,
            stage="requirement refinement",
        )


# -- prompt block builders --------------------------------------------------
def format_requirements_block(
    items: Sequence[tuple[str, str]], *, header: str = "Requirements:"
) -> str:
    """Render (code, text) pairs for a prompt."""
    lines = [header]
    for code, text in items:
        lines.append(f"{code}: {text}")
    return "\n".join(lines)


def format_pairs_block(
    pairs: Sequence[tuple[str, str, str, str, float | None]],
) -> str:
    """Render candidate pairs as (code_a, text_a, code_b, text_b, similarity)."""
    lines = ["Candidate pairs:"]
    for code_a, text_a, code_b, text_b, similarity in pairs:
        lines.append("")
        if similarity is not None:
            lines.append(f"Pair {code_a} <-> {code_b} (embedding similarity {similarity:.3f})")
        else:
            lines.append(f"Pair {code_a} <-> {code_b}")
        lines.append(f"  {code_a}: {text_a}")
        lines.append(f"  {code_b}: {text_b}")
    return "\n".join(lines)


def format_refinement_block(items: Sequence[tuple[str, str, str]]) -> str:
    """Render (code, original_text, problems) for the refinement prompt."""
    lines = ["Requirements to rewrite:"]
    for code, text, problems in items:
        lines.append("")
        lines.append(f"{code}: {text}")
        lines.append(f"  Problems: {problems}")
    return "\n".join(lines)
