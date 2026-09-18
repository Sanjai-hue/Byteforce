"""Contradiction detection: topic-related candidates, then LLM reasoning.

Stage 1 selects pairs that are related enough to possibly conflict — a wider,
lower similarity band than duplicates, because contradictions often share a topic
without sharing wording. Stage 2 asks the model whether both can actually hold.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.ai.ai_service import AIService, format_pairs_block
from app.core.config import Settings
from app.schemas.ai_outputs import ContradictionVerdict
from app.schemas.common import ContradictionClassification, IssueType, Severity
from app.services.embedding_service import EmbeddingService
from app.services.requirement_service import RequirementRecord
from app.utils.resolve import RequirementResolver

logger = logging.getLogger("reqguard.contradictions")

_SEVERITY = {
    ContradictionClassification.CONTRADICTION: Severity.CRITICAL,
    ContradictionClassification.PARTIAL_CONFLICT: Severity.HIGH,
}

_REPORTABLE = {
    ContradictionClassification.CONTRADICTION,
    ContradictionClassification.PARTIAL_CONFLICT,
}


@dataclass(slots=True)
class ContradictionFinding:
    record_a: RequirementRecord
    record_b: RequirementRecord
    similarity: float
    verdict: ContradictionVerdict


class ContradictionService:
    def __init__(self, ai: AIService, embeddings: EmbeddingService, settings: Settings) -> None:
        self._ai = ai
        self._embeddings = embeddings
        self._settings = settings

    def _floor_for(self, classification: str) -> float:
        if ContradictionClassification(classification) == ContradictionClassification.CONTRADICTION:
            return self._settings.min_confidence_contradiction
        return self._settings.min_confidence_partial_conflict

    async def run(self, records: list[RequirementRecord]) -> list[ContradictionFinding]:
        if len(records) < 2:
            return []

        vectors = [record.embedding for record in records if record.embedding]
        if len(vectors) != len(records):
            logger.warning("some requirements have no embedding; contradiction stage skipped")
            return []

        # Contradictions live in a band: related enough to interact, not so
        # identical that they are simply the same requirement twice.
        candidates = self._embeddings.candidate_pairs(
            vectors,
            threshold=self._settings.contradiction_similarity_threshold,
            max_pairs=self._settings.max_candidate_pairs,
        )
        logger.info(
            "contradiction stage: %s candidate pair(s) (threshold %.2f)",
            len(candidates),
            self._settings.contradiction_similarity_threshold,
        )
        if not candidates:
            return []

        resolver = RequirementResolver(records)
        findings: list[ContradictionFinding] = []

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
            result = await self._ai.verify_contradiction(pairs_block)
            similarity_lookup = {
                frozenset({records[p.index_a].code, records[p.index_b].code}): p.similarity
                for p in batch
            }

            for verdict in result.verdicts:
                record_a = resolver.resolve(verdict.requirement_a)
                record_b = resolver.resolve(verdict.requirement_b)
                if record_a is None or record_b is None or record_a.code == record_b.code:
                    continue
                if verdict.classification not in _REPORTABLE:
                    continue
                if verdict.confidence < self._floor_for(verdict.classification):
                    # Below the reporting bar for this classification: a weak
                    # partial conflict is usually two requirements that merely
                    # touch the same topic.
                    continue
                similarity = similarity_lookup.get(
                    frozenset({record_a.code, record_b.code}), 0.0
                )
                findings.append(
                    ContradictionFinding(
                        record_a=record_a,
                        record_b=record_b,
                        similarity=similarity,
                        verdict=verdict,
                    )
                )

        logger.info("contradiction stage: %s confirmed finding(s)", len(findings))
        return findings

    @staticmethod
    def to_rows(
        document_id: str, findings: list[ContradictionFinding]
    ) -> tuple[list[dict], list[dict]]:
        issues: list[dict] = []
        relationships: list[dict] = []
        for finding in findings:
            classification = ContradictionClassification(finding.verdict.classification)
            issues.append(
                {
                    "document_id": document_id,
                    "requirement_id": finding.record_a.db_id,
                    "issue_type": IssueType.CONTRADICTION.value,
                    "severity": _SEVERITY.get(classification, Severity.MEDIUM).value,
                    "confidence": finding.verdict.confidence,
                    "evidence": finding.verdict.evidence_a,
                    "description": finding.verdict.explanation,
                    "suggested_refinement": finding.verdict.suggested_resolution,
                    "status": "open",
                    "metadata": {
                        "classification": classification.value,
                        "conflict_type": finding.verdict.conflict_type,
                        "similarity_score": round(finding.similarity, 4),
                        "code_a": finding.record_a.code,
                        "code_b": finding.record_b.code,
                        "evidence_a": finding.verdict.evidence_a,
                        "evidence_b": finding.verdict.evidence_b,
                        "suggested_resolution": finding.verdict.suggested_resolution,
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
                    "conflict_type": finding.verdict.conflict_type,
                    "reason": finding.verdict.explanation,
                    "evidence_a": finding.verdict.evidence_a,
                    "evidence_b": finding.verdict.evidence_b,
                    "recommendation": finding.verdict.suggested_resolution,
                    "confidence": finding.verdict.confidence,
                }
            )
        return issues, relationships


def _batched(items: list, size: int):
    for start in range(0, len(items), size):
        yield items[start : start + size]
