"""Stage 1-3: parse -> extract -> normalise -> embed -> persist.

Extraction preserves original wording exactly. Normalisation produces a separate
comparison string; it never replaces the original.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.ai.ai_service import AIService
from app.core.config import Settings
from app.database.repositories import Repositories
from app.document_processing.parser import ParsedDocument, chunk_blocks
from app.schemas.common import RequirementType
from app.services.embedding_service import EmbeddingService
from app.utils.text import looks_like_requirement, normalize_requirement

logger = logging.getLogger("reqguard.requirements")


@dataclass(slots=True)
class RequirementRecord:
    """A requirement in memory during analysis."""

    code: str
    original_text: str
    normalized_text: str
    requirement_type: str
    section: str | None
    page_number: int | None
    source_label: str | None = None
    embedding: list[float] = field(default_factory=list)
    db_id: str | None = None


class RequirementService:
    def __init__(
        self,
        repos: Repositories,
        ai: AIService,
        embeddings: EmbeddingService,
        settings: Settings,
    ) -> None:
        self._repos = repos
        self._ai = ai
        self._embeddings = embeddings
        self._settings = settings

    async def extract(self, parsed: ParsedDocument) -> list[RequirementRecord]:
        """Run LLM extraction over document chunks and assign stable IDs."""
        chunks = chunk_blocks(parsed.blocks, self._settings.extraction_chunk_chars)
        logger.info("extracting requirements from %s chunk(s)", len(chunks))

        records: list[RequirementRecord] = []
        seen: set[str] = set()

        for chunk_text, section_hint, first_page in chunks:
            result = await self._ai.extract_requirements(chunk_text, section_hint)
            for item in result.requirements:
                original = item.original_text.strip()
                if not original or not looks_like_requirement(original):
                    continue

                normalized = normalize_requirement(original)
                if not normalized or normalized in seen:
                    # Exact repeats of the same sentence are a parsing artefact,
                    # not a duplicate requirement worth reporting.
                    continue
                seen.add(normalized)

                page = self._locate_page(parsed, original, first_page)
                records.append(
                    RequirementRecord(
                        code="",  # assigned below, in document order
                        original_text=original,
                        normalized_text=normalized,
                        requirement_type=self._coerce_type(item.requirement_type),
                        section=item.section or section_hint if section_hint != "unknown" else item.section,
                        page_number=page,
                        source_label=item.source_label,
                    )
                )

                if len(records) >= self._settings.max_requirements:
                    logger.warning(
                        "requirement cap (%s) reached; stopping extraction",
                        self._settings.max_requirements,
                    )
                    break
            if len(records) >= self._settings.max_requirements:
                break

        for index, record in enumerate(records, start=1):
            record.code = f"R{index:03d}"

        logger.info("extracted %s requirement(s)", len(records))
        return records

    @staticmethod
    def _coerce_type(value: str | RequirementType) -> str:
        try:
            return RequirementType(str(value)).value
        except ValueError:
            return RequirementType.OTHER.value

    @staticmethod
    def _locate_page(parsed: ParsedDocument, text: str, fallback: int | None) -> int | None:
        """Find the page a requirement came from, so findings stay traceable."""
        probe = text[:60].strip()
        if probe:
            for block in parsed.blocks:
                if probe and probe in block.text and block.page_number is not None:
                    return block.page_number
        return fallback

    def embed(self, records: list[RequirementRecord]) -> None:
        if not records:
            return
        vectors = self._embeddings.embed_requirements([r.normalized_text for r in records])
        for record, vector in zip(records, vectors, strict=True):
            record.embedding = vector

    async def persist(
        self, document_id: str, records: list[RequirementRecord]
    ) -> list[RequirementRecord]:
        if not records:
            return []
        rows = [
            {
                "document_id": document_id,
                "requirement_code": record.code,
                "original_text": record.original_text,
                "normalized_text": record.normalized_text,
                "requirement_type": record.requirement_type,
                "section": record.section,
                "page_number": record.page_number,
                "embedding": record.embedding or None,
            }
            for record in records
        ]
        created = await self._repos.requirements.bulk_create(rows)

        by_code = {row["requirement_code"]: row["id"] for row in created}
        for record in records:
            record.db_id = by_code.get(record.code)
        return records
