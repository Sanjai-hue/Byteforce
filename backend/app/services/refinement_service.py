"""Refinement generation.

A refinement is always a *proposal* stored beside the original. The original
requirement row is never modified, so accepting or rejecting a suggestion is
fully reversible and the source text stays auditable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.ai.ai_service import AIService, format_refinement_block
from app.core.config import Settings
from app.services.requirement_service import RequirementRecord
from app.utils.resolve import RequirementResolver

logger = logging.getLogger("reqguard.refinements")

BATCH_SIZE = 8


@dataclass(slots=True)
class RefinementProposal:
    record: RequirementRecord
    suggested_text: str
    reason: str
    issue_id: str | None = None


class RefinementService:
    def __init__(self, ai: AIService, settings: Settings) -> None:
        self._ai = ai
        self._settings = settings

    async def run(
        self, problem_map: dict[str, tuple[RequirementRecord, list[str], str | None]]
    ) -> list[RefinementProposal]:
        """Generate one refinement per problematic requirement.

        problem_map maps requirement code -> (record, problem descriptions,
        originating issue id).
        """
        if not problem_map:
            return []

        entries = list(problem_map.values())
        proposals: list[RefinementProposal] = []
        resolver = RequirementResolver([record for record, _, _ in entries])
        issue_by_code = {record.code: issue_id for record, _, issue_id in entries}

        for batch in _batched(entries, BATCH_SIZE):
            block = format_refinement_block(
                [(record.code, record.original_text, "; ".join(problems)) for record, problems, _ in batch]
            )
            result = await self._ai.generate_refinement(block)
            for suggestion in result.refinements:
                record = resolver.resolve(suggestion.requirement_code)
                if record is None:
                    continue
                issue_id = issue_by_code.get(record.code)
                suggested = suggestion.suggested_text.strip()
                if not suggested or suggested == record.original_text.strip():
                    continue
                proposals.append(
                    RefinementProposal(
                        record=record,
                        suggested_text=suggested,
                        reason=suggestion.reason,
                        issue_id=issue_id,
                    )
                )

        logger.info("refinement stage: %s proposal(s)", len(proposals))
        return proposals

    @staticmethod
    def to_rows(document_id: str, proposals: list[RefinementProposal]) -> list[dict]:
        return [
            {
                "document_id": document_id,
                "requirement_id": proposal.record.db_id,
                "issue_id": proposal.issue_id,
                "original_text": proposal.record.original_text,
                "suggested_text": proposal.suggested_text,
                "reason": proposal.reason,
                "status": "pending",
            }
            for proposal in proposals
        ]


def _batched(items: list, size: int):
    for start in range(0, len(items), size):
        yield items[start : start + size]
