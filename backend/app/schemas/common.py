"""Shared enums used across the pipeline, the database and the API."""

from __future__ import annotations

from enum import StrEnum


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    EXTRACTING = "extracting"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"


class RequirementType(StrEnum):
    FUNCTIONAL = "functional"
    NON_FUNCTIONAL = "non_functional"
    BUSINESS_RULE = "business_rule"
    CONSTRAINT = "constraint"
    OTHER = "other"


class IssueType(StrEnum):
    AMBIGUITY = "ambiguity"
    CONTRADICTION = "contradiction"
    DUPLICATE = "duplicate"
    MISSING_INFORMATION = "missing_information"
    DEPENDENCY = "dependency"


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class IssueStatus(StrEnum):
    OPEN = "open"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    RESOLVED = "resolved"
    NEEDS_REVIEW = "needs_review"


class RefinementStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EDITED = "edited"


class DuplicateClassification(StrEnum):
    DUPLICATE = "duplicate"
    OVERLAPPING = "overlapping"
    RELATED_BUT_DISTINCT = "related_but_distinct"
    NOT_DUPLICATE = "not_duplicate"


class ContradictionClassification(StrEnum):
    CONTRADICTION = "contradiction"
    PARTIAL_CONFLICT = "partial_conflict"
    COMPATIBLE = "compatible"
    UNRELATED = "unrelated"


class DependencyRelationship(StrEnum):
    DEPENDS_ON = "depends_on"
    ENABLES = "enables"
    REQUIRES = "requires"
    PREREQUISITE_FOR = "prerequisite_for"


class AnalysisStage(StrEnum):
    """Pipeline stages, in order, with the progress value each one reports."""

    QUEUED = "queued"
    PARSING = "parsing"
    EXTRACTING = "extracting_requirements"
    EMBEDDING = "generating_embeddings"
    DUPLICATES = "detecting_duplicates"
    AMBIGUITIES = "detecting_ambiguities"
    CONTRADICTIONS = "detecting_contradictions"
    DEPENDENCIES = "analyzing_dependencies"
    MISSING_INFO = "analyzing_missing_information"
    REFINEMENTS = "generating_refinements"
    TRACEABILITY = "building_traceability"
    COMPLETED = "completed"
    FAILED = "failed"


STAGE_PROGRESS: dict[AnalysisStage, int] = {
    AnalysisStage.QUEUED: 5,
    AnalysisStage.PARSING: 10,
    AnalysisStage.EXTRACTING: 25,
    AnalysisStage.EMBEDDING: 40,
    AnalysisStage.DUPLICATES: 55,
    AnalysisStage.AMBIGUITIES: 65,
    AnalysisStage.CONTRADICTIONS: 75,
    AnalysisStage.DEPENDENCIES: 85,
    AnalysisStage.MISSING_INFO: 90,
    AnalysisStage.REFINEMENTS: 95,
    AnalysisStage.TRACEABILITY: 98,
    AnalysisStage.COMPLETED: 100,
    AnalysisStage.FAILED: 100,
}

STAGE_LABELS: dict[AnalysisStage, str] = {
    AnalysisStage.QUEUED: "Queued",
    AnalysisStage.PARSING: "Reading document",
    AnalysisStage.EXTRACTING: "Extracting requirements",
    AnalysisStage.EMBEDDING: "Generating semantic embeddings",
    AnalysisStage.DUPLICATES: "Detecting duplicates",
    AnalysisStage.AMBIGUITIES: "Detecting ambiguities",
    AnalysisStage.CONTRADICTIONS: "Detecting contradictions",
    AnalysisStage.DEPENDENCIES: "Analyzing dependencies",
    AnalysisStage.MISSING_INFO: "Analyzing missing information",
    AnalysisStage.REFINEMENTS: "Generating refinements",
    AnalysisStage.TRACEABILITY: "Building traceability",
    AnalysisStage.COMPLETED: "Completed",
    AnalysisStage.FAILED: "Failed",
}
