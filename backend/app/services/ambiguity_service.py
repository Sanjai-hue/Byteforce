"""Ambiguity and missing-information detection.

Both stages send requirements to the model in batches and keep only the findings
the model marks positive. The vague-term list is a hint inside the prompt, never
a standalone trigger: a requirement containing "quickly" is fine if it also
states a measurable criterion.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.ai.ai_service import AIService, format_requirements_block
from app.core.config import Settings
from app.schemas.ai_outputs import AmbiguityFinding, MissingInfoFinding
from app.schemas.common import IssueType, Severity
from app.services.requirement_service import RequirementRecord
from app.utils.resolve import RequirementResolver

logger = logging.getLogger("reqguard.ambiguity")

BATCH_SIZE = 12


@dataclass(slots=True)
class AmbiguityIssue:
    record: RequirementRecord
    finding: AmbiguityFinding


@dataclass(slots=True)
class MissingInfoIssue:
    record: RequirementRecord
    finding: MissingInfoFinding


class AmbiguityService:
    def __init__(self, ai: AIService, settings: Settings) -> None:
        self._ai = ai
        self._settings = settings

    async def run(self, records: list[RequirementRecord]) -> list[AmbiguityIssue]:
        if not records:
            return []

        resolver = RequirementResolver(records)
        issues: list[AmbiguityIssue] = []

        for batch in _batched(records, BATCH_SIZE):
            block = format_requirements_block([(r.code, r.original_text) for r in batch])
            result = await self._ai.detect_ambiguity(block)
            for finding in result.findings:
                if not finding.ambiguous:
                    continue
                record = resolver.resolve(finding.requirement_code)
                if record is None:
                    continue
                issues.append(AmbiguityIssue(record=record, finding=finding))

        logger.info("ambiguity stage: %s finding(s) across %s requirement(s)", len(issues), len(records))
        return issues

    @staticmethod
    def to_rows(document_id: str, issues: list[AmbiguityIssue]) -> list[dict]:
        rows: list[dict] = []
        for issue in issues:
            finding = issue.finding
            rows.append(
                {
                    "document_id": document_id,
                    "requirement_id": issue.record.db_id,
                    "issue_type": IssueType.AMBIGUITY.value,
                    "severity": _severity(finding.severity),
                    "confidence": finding.confidence,
                    "evidence": finding.evidence,
                    "description": finding.explanation,
                    "suggested_refinement": finding.suggested_refinement,
                    "status": "open",
                    "metadata": {
                        "ambiguous_terms": finding.ambiguous_terms,
                        "requirement_code": issue.record.code,
                    },
                }
            )
        return rows


class MissingInfoService:
    def __init__(self, ai: AIService, settings: Settings) -> None:
        self._ai = ai
        self._settings = settings

    async def run(self, records: list[RequirementRecord]) -> list[MissingInfoIssue]:
        if not records:
            return []

        resolver = RequirementResolver(records)
        issues: list[MissingInfoIssue] = []

        for batch in _batched(records, BATCH_SIZE):
            block = format_requirements_block([(r.code, r.original_text) for r in batch])
            result = await self._ai.analyze_missing_information(block)
            for finding in result.findings:
                if not finding.has_missing_information or not finding.missing_information:
                    continue
                record = resolver.resolve(finding.requirement_code)
                if record is None:
                    continue
                issues.append(MissingInfoIssue(record=record, finding=finding))

        logger.info("missing information stage: %s finding(s)", len(issues))
        return issues

    @staticmethod
    def to_rows(document_id: str, issues: list[MissingInfoIssue]) -> list[dict]:
        rows: list[dict] = []
        for issue in issues:
            finding = issue.finding
            rows.append(
                {
                    "document_id": document_id,
                    "requirement_id": issue.record.db_id,
                    "issue_type": IssueType.MISSING_INFORMATION.value,
                    "severity": _severity(finding.severity),
                    "confidence": finding.confidence,
                    "evidence": finding.evidence,
                    "description": finding.explanation,
                    "suggested_refinement": finding.suggested_refinement,
                    "status": "open",
                    "metadata": {
                        "missing_information": finding.missing_information,
                        "suggested_questions": finding.suggested_questions,
                        "requirement_code": issue.record.code,
                    },
                }
            )
        return rows


def _severity(value: str | Severity) -> str:
    try:
        return Severity(str(value)).value
    except ValueError:
        return Severity.MEDIUM.value


def _batched(items: list, size: int):
    for start in range(0, len(items), size):
        yield items[start : start + size]
