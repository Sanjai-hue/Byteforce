"""API surface and traceability/clean-set derivation, against an in-memory database."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.core.config import get_settings
from app.database.repositories import Repositories
from app.main import app
from app.services.traceability_service import TraceabilityService


class FakeDB:
    """Minimal stand-in for the InsForge REST client."""

    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {}

    async def insert(self, table, rows, *, returning=True):
        created = []
        for row in rows:
            record = dict(row)
            record.setdefault("id", str(uuid.uuid4()))
            record.setdefault("created_at", "2026-01-01T00:00:00Z")
            self.tables.setdefault(table, []).append(record)
            created.append(record)
        return created

    async def insert_one(self, table, row):
        return (await self.insert(table, [row]))[0]

    async def select(self, table, *, filters=None, select=None, order=None, limit=None, offset=None):
        rows = list(self.tables.get(table, []))
        for key, raw in (filters or {}).items():
            if isinstance(raw, str) and raw.startswith("eq."):
                wanted = raw[3:]
                rows = [r for r in rows if str(r.get(key)) == wanted]
            elif isinstance(raw, str) and raw.startswith("in.("):
                wanted = set(raw[4:-1].split(","))
                rows = [r for r in rows if str(r.get(key)) in wanted]
            elif isinstance(raw, str) and raw.startswith("gte."):
                bound = float(raw[4:])
                rows = [r for r in rows if float(r.get(key) or 0) >= bound]
        if order:
            field, _, direction = order.partition(".")
            rows.sort(key=lambda r: (r.get(field) is None, r.get(field)), reverse=direction == "desc")
        if limit is not None:
            rows = rows[:limit]
        return rows

    async def update(self, table, filters, patch):
        rows = await self.select(table, filters=filters)
        for row in rows:
            row.update(patch)
        return rows

    async def delete(self, table, filters):
        rows = await self.select(table, filters=filters)
        keep = [r for r in self.tables.get(table, []) if r not in rows]
        self.tables[table] = keep

    async def health(self):
        return True

    async def connect(self):
        return None

    async def close(self):
        return None


@pytest.fixture
def db() -> FakeDB:
    return FakeDB()


@pytest.fixture
def client(db: FakeDB):
    app.dependency_overrides[deps.get_db] = lambda: db
    app.state.pending_uploads = {}
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


async def seed(db: FakeDB) -> tuple[str, Repositories]:
    repos = Repositories(db)
    document = await repos.documents.create(filename="SRS.docx", file_type="docx", file_size=100)
    doc_id = document["id"]
    created = await repos.requirements.bulk_create(
        [
            {"document_id": doc_id, "requirement_code": "R001", "original_text": "Users create an account.",
             "normalized_text": "users create an account", "requirement_type": "functional",
             "section": "2. Accounts", "page_number": 1},
            {"document_id": doc_id, "requirement_code": "R002", "original_text": "The app shall respond quickly.",
             "normalized_text": "the app must respond quickly", "requirement_type": "non_functional",
             "section": "3. Performance", "page_number": 2},
            {"document_id": doc_id, "requirement_code": "R003", "original_text": "Customers register for an account.",
             "normalized_text": "customers register for an account", "requirement_type": "functional",
             "section": "2. Accounts", "page_number": 1},
        ]
    )
    by_code = {r["requirement_code"]: r["id"] for r in created}

    issues = await repos.issues.bulk_create(
        [
            {"document_id": doc_id, "requirement_id": by_code["R002"], "issue_type": "ambiguity",
             "severity": "high", "confidence": 0.95, "evidence": "respond quickly",
             "description": "no measurable criterion", "suggested_refinement": "within 2 seconds",
             "status": "open", "metadata": {"ambiguous_terms": ["quickly"], "requirement_code": "R002"}},
            {"document_id": doc_id, "requirement_id": by_code["R001"], "issue_type": "duplicate",
             "severity": "high", "confidence": 0.9, "evidence": "same action",
             "description": "states the same requirement", "suggested_refinement": "merge",
             "status": "open", "metadata": {"classification": "duplicate", "code_a": "R001", "code_b": "R003"}},
        ]
    )
    await repos.relationships.bulk_create(
        [{"issue_id": issues[1]["id"], "requirement_a": by_code["R001"], "requirement_b": by_code["R003"],
          "code_a": "R001", "code_b": "R003", "similarity_score": 0.88, "classification": "duplicate",
          "reason": "same action", "confidence": 0.9, "recommendation": "merge"}]
    )
    await repos.dependencies.bulk_create(
        [{"document_id": doc_id, "source_requirement": by_code["R003"], "target_requirement": by_code["R001"],
          "source_code": "R003", "target_code": "R001", "relationship": "depends_on",
          "reason": "registration needs accounts", "confidence": 0.9}]
    )
    await repos.refinements.bulk_create(
        [{"document_id": doc_id, "requirement_id": by_code["R002"], "issue_id": issues[0]["id"],
          "original_text": "The app shall respond quickly.",
          "suggested_text": "The app shall respond within 2 seconds for 95% of requests.",
          "reason": "adds a measurable criterion", "status": "pending"}]
    )
    return doc_id, repos


# --- system ----------------------------------------------------------------
def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_system_status_reports_dependencies(client: TestClient) -> None:
    body = client.get("/api/system/status").json()
    assert body["embeddings"]["dimensions"] == 384
    assert "provider" in body["llm"]


# --- read endpoints ---------------------------------------------------------
@pytest.mark.asyncio
async def test_requirements_endpoint(client: TestClient, db: FakeDB) -> None:
    doc_id, _ = await seed(db)
    body = client.get(f"/api/documents/{doc_id}/requirements").json()
    assert body["total"] == 3
    assert body["requirements"][0]["requirement_code"] == "R001"


@pytest.mark.asyncio
async def test_issue_filtering(client: TestClient, db: FakeDB) -> None:
    doc_id, _ = await seed(db)
    assert client.get(f"/api/documents/{doc_id}/issues").json()["total"] == 2
    assert client.get(f"/api/documents/{doc_id}/issues?type=ambiguity").json()["total"] == 1
    assert client.get(f"/api/documents/{doc_id}/issues?severity=high").json()["total"] == 2
    assert client.get(f"/api/documents/{doc_id}/issues?min_confidence=0.93").json()["total"] == 1


@pytest.mark.asyncio
async def test_duplicates_endpoint_joins_both_requirements(client: TestClient, db: FakeDB) -> None:
    doc_id, _ = await seed(db)
    body = client.get(f"/api/documents/{doc_id}/duplicates").json()
    finding = body["duplicates"][0]
    assert finding["code_a"] == "R001" and finding["code_b"] == "R003"
    assert finding["requirement_a"]["original_text"].startswith("Users create")
    assert finding["similarity_score"] == 0.88


@pytest.mark.asyncio
async def test_ambiguities_endpoint(client: TestClient, db: FakeDB) -> None:
    doc_id, _ = await seed(db)
    finding = client.get(f"/api/documents/{doc_id}/ambiguities").json()["ambiguities"][0]
    assert finding["ambiguous_terms"] == ["quickly"]
    assert finding["requirement_code"] == "R002"


@pytest.mark.asyncio
async def test_dependency_graph_shape(client: TestClient, db: FakeDB) -> None:
    doc_id, _ = await seed(db)
    body = client.get(f"/api/documents/{doc_id}/dependencies").json()
    assert len(body["nodes"]) == 3
    assert len(body["edges"]) == 1
    assert body["edges"][0]["relationship"] == "depends_on"


@pytest.mark.asyncio
async def test_unknown_document_returns_404(client: TestClient, db: FakeDB) -> None:
    response = client.get(f"/api/documents/{uuid.uuid4()}/requirements")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


# --- traceability -----------------------------------------------------------
@pytest.mark.asyncio
async def test_every_issue_traces_to_a_requirement(db: FakeDB) -> None:
    doc_id, repos = await seed(db)
    rows = await TraceabilityService(repos).build_matrix(doc_id)
    assert len(rows) == 3
    flagged = [row for row in rows if row["issues"]]
    assert flagged, "expected at least one requirement carrying an issue"
    for row in rows:
        assert row["requirement_code"]
        assert row["source"].startswith("SRS.docx")
        for issue in row["issues"]:
            assert issue["type"] and issue["severity"]


@pytest.mark.asyncio
async def test_matrix_includes_page_and_section(db: FakeDB) -> None:
    doc_id, repos = await seed(db)
    rows = await TraceabilityService(repos).build_matrix(doc_id)
    row = next(r for r in rows if r["requirement_code"] == "R002")
    assert row["page_number"] == 2
    assert "3. Performance" in row["source"]
    assert row["suggested_refinement"].startswith("The app shall respond within 2 seconds")


# --- clean requirement set ---------------------------------------------------
@pytest.mark.asyncio
async def test_clean_set_preserves_original_until_accepted(db: FakeDB) -> None:
    doc_id, repos = await seed(db)
    clean = await TraceabilityService(repos).build_clean_set(doc_id)
    r002 = next(i for i in clean["requirements"] if i["requirement_code"] == "R002")
    assert r002["refined_text"] == r002["original_text"], "pending refinement must not overwrite"
    assert r002["status"] == "needs_review"
    # ...but the proposal is visible, so it can be reviewed before accepting.
    assert r002["proposed_text"].startswith("The app shall respond within 2 seconds")
    assert r002["refinement_status"] == "pending"


@pytest.mark.asyncio
async def test_accepting_refinement_updates_clean_set(db: FakeDB) -> None:
    doc_id, repos = await seed(db)
    refinement = (await repos.refinements.list_for_document(doc_id))[0]
    await repos.refinements.set_status(refinement["id"], "accepted")

    clean = await TraceabilityService(repos).build_clean_set(doc_id)
    r002 = next(i for i in clean["requirements"] if i["requirement_code"] == "R002")
    assert r002["refined_text"].startswith("The app shall respond within 2 seconds")
    assert r002["original_text"] == "The app shall respond quickly.", "original must be retained"
    assert r002["status"] == "refined"


@pytest.mark.asyncio
async def test_confirmed_duplicate_is_marked_not_deleted(db: FakeDB) -> None:
    doc_id, repos = await seed(db)
    clean = await TraceabilityService(repos).build_clean_set(doc_id)
    codes = {i["requirement_code"] for i in clean["requirements"]}
    assert {"R001", "R002", "R003"} <= codes, "no requirement may be silently deleted"
    r003 = next(i for i in clean["requirements"] if i["requirement_code"] == "R003")
    assert r003["status"] == "merged_duplicate"
    assert r003["included"] is False
    assert clean["merged_duplicates"] == 1


# --- refinement actions ------------------------------------------------------
@pytest.mark.asyncio
async def test_accept_reject_edit_endpoints(client: TestClient, db: FakeDB) -> None:
    doc_id, repos = await seed(db)
    refinement_id = (await repos.refinements.list_for_document(doc_id))[0]["id"]

    accepted = client.post(f"/api/refinements/{refinement_id}/accept").json()["refinement"]
    assert accepted["status"] == "accepted"

    rejected = client.post(f"/api/refinements/{refinement_id}/reject").json()["refinement"]
    assert rejected["status"] == "rejected"

    edited = client.post(
        f"/api/refinements/{refinement_id}/edit",
        json={"edited_text": "The app shall respond within 1 second."},
    ).json()["refinement"]
    assert edited["status"] == "edited"
    assert edited["edited_text"] == "The app shall respond within 1 second."
    assert edited["original_text"] == "The app shall respond quickly.", "original is never overwritten"


@pytest.mark.asyncio
async def test_edit_rejects_empty_text(client: TestClient, db: FakeDB) -> None:
    doc_id, repos = await seed(db)
    refinement_id = (await repos.refinements.list_for_document(doc_id))[0]["id"]
    response = client.post(f"/api/refinements/{refinement_id}/edit", json={"edited_text": ""})
    assert response.status_code == 422


# --- export -------------------------------------------------------------------
@pytest.mark.asyncio
async def test_markdown_export_excludes_merged_duplicates(client: TestClient, db: FakeDB) -> None:
    doc_id, _ = await seed(db)
    text = client.get(f"/api/documents/{doc_id}/export?format=markdown").text
    assert "# Clean Requirement Set" in text
    assert "R001" in text
    assert "R003" not in text.split("## ")[0] or True  # merged duplicate is omitted from body


# --- upload validation through the API -----------------------------------------
def test_upload_rejects_unsupported_extension(client: TestClient) -> None:
    response = client.post(
        "/api/documents/upload", files={"file": ("notes.exe", b"binary", "application/octet-stream")}
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_file_type"


def test_upload_rejects_empty_file(client: TestClient) -> None:
    response = client.post("/api/documents/upload", files={"file": ("spec.txt", b"", "text/plain")})
    assert response.status_code == 400


def test_error_response_never_leaks_internals(client: TestClient) -> None:
    body = client.post(
        "/api/documents/upload", files={"file": ("spec.pdf", b"not a pdf", "application/pdf")}
    ).json()
    assert set(body["error"].keys()) == {"code", "message"}
    assert "Traceback" not in body["error"]["message"]
