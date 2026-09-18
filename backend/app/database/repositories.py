"""Per-table data access. All SQL-ish concerns live here, not in services."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence

from app.core.errors import NotFoundError
from app.database.client import InsForgeClient, JsonDict, eq, vector_literal

DOCUMENTS = "documents"
REQUIREMENTS = "requirements"
ANALYSIS_RUNS = "analysis_runs"
ISSUES = "issues"
ISSUE_RELATIONSHIPS = "issue_relationships"
DEPENDENCIES = "dependencies"
REFINEMENTS = "refinements"

# Embeddings are large and never needed by the API layer.
REQUIREMENT_FIELDS = (
    "id,document_id,requirement_code,original_text,normalized_text,"
    "requirement_type,section,page_number,created_at"
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class DocumentRepository:
    def __init__(self, db: InsForgeClient) -> None:
        self._db = db

    async def create(
        self,
        *,
        filename: str,
        file_type: str,
        file_size: int,
        file_url: str | None = None,
        storage_key: str | None = None,
    ) -> JsonDict:
        return await self._db.insert_one(
            DOCUMENTS,
            {
                "filename": filename,
                "file_type": file_type,
                "file_size": file_size,
                "file_url": file_url,
                "storage_key": storage_key,
                "status": "uploaded",
            },
        )

    async def get(self, document_id: str) -> JsonDict:
        rows = await self._db.select(DOCUMENTS, filters={"id": eq(document_id)}, limit=1)
        if not rows:
            raise NotFoundError("That document does not exist.")
        return rows[0]

    async def list_recent(self, limit: int = 25) -> list[JsonDict]:
        return await self._db.select(DOCUMENTS, order="created_at.desc", limit=limit)

    async def set_status(self, document_id: str, status: str) -> None:
        await self._db.update(DOCUMENTS, {"id": eq(document_id)}, {"status": status})


class RequirementRepository:
    def __init__(self, db: InsForgeClient) -> None:
        self._db = db

    async def bulk_create(self, rows: Sequence[JsonDict]) -> list[JsonDict]:
        """Insert requirements in batches; embeddings go in as pgvector literals."""
        payload: list[JsonDict] = []
        for row in rows:
            record = dict(row)
            embedding = record.pop("embedding", None)
            if embedding is not None:
                record["embedding"] = vector_literal(embedding)
            payload.append(record)

        created: list[JsonDict] = []
        batch_size = 50
        for start in range(0, len(payload), batch_size):
            chunk = payload[start : start + batch_size]
            created.extend(await self._db.insert(REQUIREMENTS, chunk))
        return created

    async def list_for_document(self, document_id: str) -> list[JsonDict]:
        return await self._db.select(
            REQUIREMENTS,
            filters={"document_id": eq(document_id)},
            select=REQUIREMENT_FIELDS,
            order="requirement_code.asc",
            limit=1000,
        )

    async def get(self, requirement_id: str) -> JsonDict:
        rows = await self._db.select(
            REQUIREMENTS,
            filters={"id": eq(requirement_id)},
            select=REQUIREMENT_FIELDS,
            limit=1,
        )
        if not rows:
            raise NotFoundError("That requirement does not exist.")
        return rows[0]


class AnalysisRunRepository:
    def __init__(self, db: InsForgeClient) -> None:
        self._db = db

    async def create(self, document_id: str) -> JsonDict:
        return await self._db.insert_one(
            ANALYSIS_RUNS,
            {"document_id": document_id, "status": "pending", "stage": "queued", "progress": 0},
        )

    async def latest(self, document_id: str) -> JsonDict | None:
        rows = await self._db.select(
            ANALYSIS_RUNS,
            filters={"document_id": eq(document_id)},
            order="started_at.desc",
            limit=1,
        )
        return rows[0] if rows else None

    async def update_progress(
        self, run_id: str, *, status: str, stage: str, progress: int
    ) -> None:
        await self._db.update(
            ANALYSIS_RUNS,
            {"id": eq(run_id)},
            {"status": status, "stage": stage, "progress": progress},
        )

    async def complete(self, run_id: str, stats: dict[str, Any]) -> None:
        await self._db.update(
            ANALYSIS_RUNS,
            {"id": eq(run_id)},
            {
                "status": "completed",
                "stage": "completed",
                "progress": 100,
                "completed_at": _utcnow(),
                "stats": stats,
            },
        )

    async def fail(self, run_id: str, message: str) -> None:
        await self._db.update(
            ANALYSIS_RUNS,
            {"id": eq(run_id)},
            {
                "status": "failed",
                "stage": "failed",
                "completed_at": _utcnow(),
                "error_message": message[:1000],
            },
        )

    async def clear_for_document(self, document_id: str) -> None:
        """Remove prior analysis output so a re-run does not duplicate findings."""
        for table in (ISSUES, DEPENDENCIES, REFINEMENTS):
            await self._db.delete(table, {"document_id": eq(document_id)})
        await self._db.delete(REQUIREMENTS, {"document_id": eq(document_id)})


class IssueRepository:
    def __init__(self, db: InsForgeClient) -> None:
        self._db = db

    async def bulk_create(self, rows: Sequence[JsonDict]) -> list[JsonDict]:
        if not rows:
            return []
        created: list[JsonDict] = []
        for start in range(0, len(rows), 50):
            created.extend(await self._db.insert(ISSUES, list(rows[start : start + 50])))
        return created

    async def list_for_document(
        self,
        document_id: str,
        *,
        issue_type: str | None = None,
        severity: str | None = None,
        requirement_id: str | None = None,
        min_confidence: float | None = None,
    ) -> list[JsonDict]:
        filters: dict[str, Any] = {"document_id": eq(document_id)}
        if issue_type:
            filters["issue_type"] = eq(issue_type)
        if severity:
            filters["severity"] = eq(severity)
        if requirement_id:
            filters["requirement_id"] = eq(requirement_id)
        if min_confidence is not None:
            filters["confidence"] = f"gte.{min_confidence}"
        return await self._db.select(
            ISSUES, filters=filters, order="created_at.asc", limit=1000
        )

    async def get(self, issue_id: str) -> JsonDict:
        rows = await self._db.select(ISSUES, filters={"id": eq(issue_id)}, limit=1)
        if not rows:
            raise NotFoundError("That issue does not exist.")
        return rows[0]

    async def set_status(self, issue_id: str, status: str) -> None:
        await self._db.update(ISSUES, {"id": eq(issue_id)}, {"status": status})


class IssueRelationshipRepository:
    def __init__(self, db: InsForgeClient) -> None:
        self._db = db

    async def bulk_create(self, rows: Sequence[JsonDict]) -> list[JsonDict]:
        if not rows:
            return []
        created: list[JsonDict] = []
        for start in range(0, len(rows), 50):
            created.extend(
                await self._db.insert(ISSUE_RELATIONSHIPS, list(rows[start : start + 50]))
            )
        return created

    async def list_for_issues(self, issue_ids: Sequence[str]) -> list[JsonDict]:
        if not issue_ids:
            return []
        joined = ",".join(issue_ids)
        return await self._db.select(
            ISSUE_RELATIONSHIPS, filters={"issue_id": f"in.({joined})"}, limit=1000
        )


class DependencyRepository:
    def __init__(self, db: InsForgeClient) -> None:
        self._db = db

    async def bulk_create(self, rows: Sequence[JsonDict]) -> list[JsonDict]:
        if not rows:
            return []
        return await self._db.insert(DEPENDENCIES, list(rows))

    async def list_for_document(self, document_id: str) -> list[JsonDict]:
        return await self._db.select(
            DEPENDENCIES, filters={"document_id": eq(document_id)}, limit=1000
        )


class RefinementRepository:
    def __init__(self, db: InsForgeClient) -> None:
        self._db = db

    async def bulk_create(self, rows: Sequence[JsonDict]) -> list[JsonDict]:
        if not rows:
            return []
        created: list[JsonDict] = []
        for start in range(0, len(rows), 50):
            created.extend(await self._db.insert(REFINEMENTS, list(rows[start : start + 50])))
        return created

    async def list_for_document(self, document_id: str) -> list[JsonDict]:
        return await self._db.select(
            REFINEMENTS,
            filters={"document_id": eq(document_id)},
            order="created_at.asc",
            limit=1000,
        )

    async def get(self, refinement_id: str) -> JsonDict:
        rows = await self._db.select(REFINEMENTS, filters={"id": eq(refinement_id)}, limit=1)
        if not rows:
            raise NotFoundError("That refinement does not exist.")
        return rows[0]

    async def set_status(
        self, refinement_id: str, status: str, *, edited_text: str | None = None
    ) -> JsonDict:
        patch: JsonDict = {"status": status, "updated_at": _utcnow()}
        if edited_text is not None:
            patch["edited_text"] = edited_text
        updated = await self._db.update(REFINEMENTS, {"id": eq(refinement_id)}, patch)
        if not updated:
            raise NotFoundError("That refinement does not exist.")
        return updated[0]


class Repositories:
    """Bundle of every repository, built once per request."""

    def __init__(self, db: InsForgeClient) -> None:
        self.db = db
        self.documents = DocumentRepository(db)
        self.requirements = RequirementRepository(db)
        self.runs = AnalysisRunRepository(db)
        self.issues = IssueRepository(db)
        self.relationships = IssueRelationshipRepository(db)
        self.dependencies = DependencyRepository(db)
        self.refinements = RefinementRepository(db)
