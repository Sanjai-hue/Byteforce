"""Dependency analysis — logical prerequisite edges between requirements.

The model sees requirements in batches with overlap, so an edge between items far
apart in the document can still be found. Edges are de-duplicated and cycles
through an already-seen pair are dropped, because a dependency graph that loops
back on itself is not usable for sequencing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.ai.ai_service import AIService, format_requirements_block
from app.core.config import Settings
from app.schemas.ai_outputs import DependencyEdge
from app.schemas.common import DependencyRelationship
from app.services.requirement_service import RequirementRecord
from app.utils.resolve import RequirementResolver

logger = logging.getLogger("reqguard.dependencies")

BATCH_SIZE = 20
OVERLAP = 5
MIN_CONFIDENCE = 0.4


@dataclass(slots=True)
class DependencyFinding:
    source: RequirementRecord
    target: RequirementRecord
    edge: DependencyEdge


class DependencyService:
    def __init__(self, ai: AIService, settings: Settings) -> None:
        self._ai = ai
        self._settings = settings

    async def run(self, records: list[RequirementRecord]) -> list[DependencyFinding]:
        if len(records) < 2:
            return []

        resolver = RequirementResolver(records)
        findings: list[DependencyFinding] = []
        seen: set[tuple[str, str]] = set()

        for batch in _sliding_batches(records, BATCH_SIZE, OVERLAP):
            block = format_requirements_block([(r.code, r.original_text) for r in batch])
            result = await self._ai.analyze_dependencies(block)

            for edge in result.dependencies:
                source = resolver.resolve(edge.source_requirement)
                target = resolver.resolve(edge.target_requirement)
                if source is None or target is None:
                    continue
                if source.code == target.code:
                    continue
                if edge.confidence < self._settings.min_confidence_dependency:
                    continue

                key = (source.code, target.code)
                reverse = (target.code, source.code)
                if key in seen or reverse in seen:
                    # Keep the first direction the model committed to rather
                    # than storing both halves of the same relationship.
                    continue
                seen.add(key)
                findings.append(DependencyFinding(source=source, target=target, edge=edge))

        logger.info("dependency stage: %s edge(s) across %s requirement(s)", len(findings), len(records))
        return findings

    @staticmethod
    def to_rows(document_id: str, findings: list[DependencyFinding]) -> list[dict]:
        rows: list[dict] = []
        for finding in findings:
            try:
                relationship = DependencyRelationship(str(finding.edge.relationship)).value
            except ValueError:
                relationship = DependencyRelationship.DEPENDS_ON.value
            rows.append(
                {
                    "document_id": document_id,
                    "source_requirement": finding.source.db_id,
                    "target_requirement": finding.target.db_id,
                    "source_code": finding.source.code,
                    "target_code": finding.target.code,
                    "relationship": relationship,
                    "reason": finding.edge.reason,
                    "confidence": finding.edge.confidence,
                }
            )
        return rows


def _sliding_batches(items: list, size: int, overlap: int):
    """Yield overlapping windows so cross-batch relationships are still visible."""
    if len(items) <= size:
        yield items
        return
    step = max(1, size - overlap)
    for start in range(0, len(items), step):
        window = items[start : start + size]
        if len(window) < 2:
            break
        yield window
        if start + size >= len(items):
            break
