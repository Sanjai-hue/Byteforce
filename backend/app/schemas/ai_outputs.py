"""Pydantic models that validate every LLM response.

Nothing reaches the database until it validates against one of these. If a model
returns malformed JSON the caller retries once with a correction prompt and then
fails the stage — it never invents a result.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import (
    ContradictionClassification,
    DependencyRelationship,
    DuplicateClassification,
    RequirementType,
    Severity,
)


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


def _clamp_confidence(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


# ---------------------------------------------------------------------------
# Requirement extraction
# ---------------------------------------------------------------------------
class ExtractedRequirement(_Base):
    original_text: str = Field(min_length=3)
    requirement_type: RequirementType = RequirementType.OTHER
    section: str | None = None
    source_label: str | None = Field(
        default=None,
        description="Requirement label as printed in the document, e.g. 'FR-12'.",
    )


class ExtractionResult(_Base):
    requirements: list[ExtractedRequirement] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Ambiguity
# ---------------------------------------------------------------------------
class AmbiguityFinding(_Base):
    requirement_code: str
    ambiguous: bool
    ambiguous_terms: list[str] = Field(default_factory=list)
    evidence: str = ""
    explanation: str = ""
    severity: Severity = Severity.MEDIUM
    confidence: float = 0.0
    suggested_refinement: str = ""

    @field_validator("confidence")
    @classmethod
    def _confidence(cls, value: float) -> float:
        return _clamp_confidence(value)


class AmbiguityResult(_Base):
    findings: list[AmbiguityFinding] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Duplicates
# ---------------------------------------------------------------------------
class DuplicateVerdict(_Base):
    requirement_a: str
    requirement_b: str
    classification: DuplicateClassification
    reason: str = ""
    evidence: str = ""
    confidence: float = 0.0
    recommendation: str = ""

    @field_validator("confidence")
    @classmethod
    def _confidence(cls, value: float) -> float:
        return _clamp_confidence(value)


class DuplicateResult(_Base):
    verdicts: list[DuplicateVerdict] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Contradictions
# ---------------------------------------------------------------------------
class ContradictionVerdict(_Base):
    requirement_a: str
    requirement_b: str
    classification: ContradictionClassification
    conflict_type: str = ""
    evidence_a: str = ""
    evidence_b: str = ""
    explanation: str = ""
    confidence: float = 0.0
    suggested_resolution: str = ""

    @field_validator("confidence")
    @classmethod
    def _confidence(cls, value: float) -> float:
        return _clamp_confidence(value)


class ContradictionResult(_Base):
    verdicts: list[ContradictionVerdict] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------
class DependencyEdge(_Base):
    source_requirement: str
    target_requirement: str
    relationship: DependencyRelationship
    reason: str = ""
    confidence: float = 0.0

    @field_validator("confidence")
    @classmethod
    def _confidence(cls, value: float) -> float:
        return _clamp_confidence(value)


class DependencyResult(_Base):
    dependencies: list[DependencyEdge] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Missing information
# ---------------------------------------------------------------------------
class MissingInfoFinding(_Base):
    requirement_code: str
    has_missing_information: bool
    missing_information: list[str] = Field(default_factory=list)
    evidence: str = ""
    explanation: str = ""
    severity: Severity = Severity.MEDIUM
    confidence: float = 0.0
    suggested_questions: list[str] = Field(default_factory=list)
    suggested_refinement: str = ""

    @field_validator("confidence")
    @classmethod
    def _confidence(cls, value: float) -> float:
        return _clamp_confidence(value)


class MissingInfoResult(_Base):
    findings: list[MissingInfoFinding] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Refinement
# ---------------------------------------------------------------------------
class RefinementSuggestion(_Base):
    requirement_code: str
    suggested_text: str = Field(min_length=3)
    reason: str = ""


class RefinementResult(_Base):
    refinements: list[RefinementSuggestion] = Field(default_factory=list)
