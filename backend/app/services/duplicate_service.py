"""Duplicate detection: embedding similarity narrows candidates, the LLM decides.

Stage 1 is cosine similarity over BGE embeddings. Stage 2 asks the model to
classify only the surviving pairs. Semantic similarity alone never marks a
duplicate.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.ai.ai_service import AIService, format_pairs_block
from app.core.config import Settings
from app.schemas.ai_outputs import DuplicateVerdict
from app.schemas.common import DuplicateClassification, IssueType, Severity
from app.services.embedding_service import EmbeddingService
from app.services.requirement_service import RequirementRecord
from app.utils.resolve import RequirementResolver

logger = logging.getLogger("reqguard.duplicates")

# Severity by how strongly the pair collapses into one requirement.
_SEVERITY = {
    DuplicateClassification.DUPLICATE: Severity.HIGH,
    DuplicateClassification.OVERLAPPING: Severity.MEDIUM,
    DuplicateClassification.RELATED_BUT_DISTINCT: Severity.LOW,
}

_REPORTABLE = {
    DuplicateClassification.DUPLICATE,
    DuplicateClassification.OVERLAPPING,
}


@dataclass(slots=True)
class DuplicateFinding:
    record_a: RequirementRecord
    record_b: RequirementRecord
    similarity: float
    verdict: DuplicateVerdict


class DuplicateService:
    def __init__(self, ai: AIService, embeddings: EmbeddingService, settings: Settings) -> None:
        self._ai = ai
        self._embeddings = embeddings
        self._settings = settings

    def _floor_for(self, classification: str) -> float:
        if DuplicateClassification(classification) == DuplicateClassification.DUPLICATE:
            return self._settings.min_confidence_duplicate
        return self._settings.min_confidence_overlapping

    async def run(self, records: list[RequirementRecord]) -> list[DuplicateFinding]:
        if len(records) < 2:
            return []

        vectors = [record.embedding for record in records if record.embedding]
        if len(vectors) != len(records):
            logger.warning("some requirements have no embedding; duplicate stage skipped")
            return []

        candidates = self._embeddings.candidate_pairs(
            vectors,
            threshold=self._settings.duplicate_similarity_threshold,
            max_pairs=self._settings.max_candidate_pairs,
        )
        logger.info(
            "duplicate stage: %s candidate pair(s) from %s requirements (threshold %.2f)",
            len(candidates),
            len(records),
            self._settings.duplicate_similarity_threshold,
        )
        if not candidates:
            return []

        resolver = RequirementResolver(records)
        findings: list[DuplicateFinding] = []

        for batch in _batched(candidates, 8):
            pairs_block = format_pairs_block(
                [
                    (
                        records[pair.index_a].code,
                        records[pair.index_a].original_text,
                        records[pair.index_b].code,
                        records[pair.index_b].original_text,
                        pair.similarity,
                    )
                    for pair in batch
                ]
            )
            result = await self._ai.verify_duplicate(pairs_block)
            similarity_lookup = {
                frozenset({records[p.index_a].code, records[p.index_b].code}): p.similarity
                for p in batch
            }

            for verdict in result.verdicts:
                record_a = resolver.resolve(verdict.requirement_a)
                record_b = resolver.resolve(verdict.requirement_b)
                if record_a is None or record_b is None or record_a.code == record_b.code:
                    logger.debug("skipping verdict with unknown codes: %s", verdict)
                    continue
                if verdict.classification not in _REPORTABLE:
                    continue
                if verdict.confidence < self._floor_for(verdict.classification):
                    continue
                similarity = similarity_lookup.get(
                    frozenset({record_a.code, record_b.code}), 0.0
                )
                findings.append(
                    DuplicateFinding(
                        record_a=record_a,
                        record_b=record_b,
                        similarity=similarity,
                        verdict=verdict,
                    )
                )

        logger.info("duplicate stage: %s confirmed finding(s)", len(findings))
        return findings

    @staticmethod
    def to_rows(
        document_id: str, findings: list[DuplicateFinding]
    ) -> tuple[list[dict], list[dict]]:
        """Build (issue rows, relationship payloads) for persistence."""
        issues: list[dict] = []
        relationships: list[dict] = []
        for finding in findings:
            classification = DuplicateClassification(finding.verdict.classification)
            issues.append(
                {
                    "document_id": document_id,
                    "requirement_id": finding.record_a.db_id,
                    "issue_type": IssueType.DUPLICATE.value,
                    "severity": _SEVERITY.get(classification, Severity.LOW).value,
                    "confidence": finding.verdict.confidence,
                    "evidence": finding.verdict.evidence,
                    "description": finding.verdict.reason,
                    "suggested_refinement": finding.verdict.recommendation,
                    "status": "open",
                    "metadata": {
                        "classification": classification.value,
                        "similarity_score": round(finding.similarity, 4),
                        "code_a": finding.record_a.code,
                        "code_b": finding.record_b.code,
                        "recommendation": finding.verdict.recommendation,
                    },
                }
            )
            relationships.append(
                {
                    "requirement_a": finding.record_a.db_id,
                    "requirement_b": finding.record_b.db_id,
                    "code_a": finding.record_a.code,
                    "code_b": finding.record_b.code,
                    "similarity_score": round(finding.similarity, 4),
                    "classification": classification.value,
                    "reason": finding.verdict.reason,
                    "evidence_a": finding.verdict.evidence,
                    "evidence_b": finding.verdict.evidence,
                    "recommendation": finding.verdict.recommendation,
                    "confidence": finding.verdict.confidence,
                }
            )
        return issues, relationships


def _batched(items: list, size: int):
    for start in range(0, len(items), size):
        yield items[start : start + size]
