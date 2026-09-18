"""Document upload, analysis kickoff, status, and every findings endpoint."""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, File, Query, Request, UploadFile

from app.api.deps import AIDep, EmbeddingsDep, ReposDep, SettingsDep, StorageDep, TraceabilityDep
from app.core.errors import ConflictError, NotFoundError, ReqGuardError
from app.document_processing.validators import validate_upload
from app.schemas.common import STAGE_LABELS, AnalysisStage, DocumentStatus
from app.services.analysis_orchestrator import AnalysisOrchestrator

logger = logging.getLogger("reqguard.api")

router = APIRouter(prefix="/api/documents", tags=["documents"])

_CONTENT_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
}


@router.post("/upload")
async def upload_document(
    request: Request,
    repos: ReposDep,
    storage: StorageDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File(description="Software Requirements Specification")],
) -> dict[str, Any]:
    data = await file.read()
    safe_name, file_type = validate_upload(data, file.filename or "", settings)

    url, key = await storage.upload(data, safe_name, _CONTENT_TYPES.get(file_type, "application/octet-stream"))

    document = await repos.documents.create(
        filename=safe_name,
        file_type=file_type,
        file_size=len(data),
        file_url=url,
        storage_key=key,
    )

    # The bytes are held in memory for the analysis request that follows, so a
    # storage outage never blocks analysis.
    request.app.state.pending_uploads[document["id"]] = data

    logger.info("uploaded %s (%s bytes) as %s", safe_name, len(data), document["id"])
    return {
        "document_id": document["id"],
        "filename": document["filename"],
        "file_type": document["file_type"],
        "file_size": document["file_size"],
        "status": document["status"],
    }


@router.post("/{document_id}/analyze")
async def analyze_document(
    document_id: str,
    request: Request,
    background: BackgroundTasks,
    repos: ReposDep,
    ai: AIDep,
    embeddings: EmbeddingsDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    document = await repos.documents.get(document_id)

    run = await repos.runs.latest(document_id)
    if run and run["status"] in {"extracting", "analyzing", "pending"}:
        raise ConflictError("This document is already being analysed.")

    data = request.app.state.pending_uploads.get(document_id)
    if data is None:
        raise NotFoundError(
            "The uploaded file is no longer held by the server. Upload the document again to analyse it."
        )

    embeddings.load()  # raises clearly if the model is unavailable

    orchestrator = AnalysisOrchestrator(repos, ai, embeddings, settings)
    background.add_task(_run_analysis, orchestrator, document_id, data)

    await repos.documents.set_status(document_id, DocumentStatus.EXTRACTING.value)
    return {
        "document_id": document_id,
        "filename": document["filename"],
        "status": DocumentStatus.EXTRACTING.value,
        "message": "Analysis started.",
    }


async def _run_analysis(orchestrator: AnalysisOrchestrator, document_id: str, data: bytes) -> None:
    try:
        await orchestrator.analyze_document(document_id, data)
    except Exception:  # already logged and recorded on the run row
        logger.warning("background analysis ended with an error for %s", document_id)


@router.get("/{document_id}/status")
async def analysis_status(document_id: str, repos: ReposDep) -> dict[str, Any]:
    document = await repos.documents.get(document_id)
    run = await repos.runs.latest(document_id)

    if run is None:
        return {
            "document_id": document_id,
            "status": document["status"],
            "stage": AnalysisStage.QUEUED.value,
            "stage_label": STAGE_LABELS[AnalysisStage.QUEUED],
            "progress": 0,
            "error_message": None,
            "stats": {},
        }

    try:
        stage = AnalysisStage(run.get("stage") or AnalysisStage.QUEUED.value)
        stage_label = STAGE_LABELS[stage]
    except ValueError:
        stage_label = run.get("stage") or "Working"

    return {
        "document_id": document_id,
        "status": run["status"],
        "stage": run.get("stage"),
        "stage_label": stage_label,
        "progress": run.get("progress", 0),
        "error_message": run.get("error_message"),
        "stats": run.get("stats") or {},
        "started_at": run.get("started_at"),
        "completed_at": run.get("completed_at"),
    }


@router.get("")
async def list_documents(repos: ReposDep) -> dict[str, Any]:
    return {"documents": await repos.documents.list_recent()}


@router.get("/{document_id}/requirements")
async def list_requirements(document_id: str, repos: ReposDep) -> dict[str, Any]:
    await repos.documents.get(document_id)
    requirements = await repos.requirements.list_for_document(document_id)
    return {"document_id": document_id, "total": len(requirements), "requirements": requirements}


@router.get("/{document_id}/issues")
async def list_issues(
    document_id: str,
    repos: ReposDep,
    type: str | None = Query(default=None, description="ambiguity | contradiction | duplicate | missing_information"),
    severity: str | None = Query(default=None),
    requirement_id: str | None = Query(default=None),
    min_confidence: float | None = Query(default=None, ge=0.0, le=1.0),
) -> dict[str, Any]:
    await repos.documents.get(document_id)
    issues = await repos.issues.list_for_document(
        document_id,
        issue_type=type,
        severity=severity,
        requirement_id=requirement_id,
        min_confidence=min_confidence,
    )
    return {"document_id": document_id, "total": len(issues), "issues": issues}


async def _pair_findings(repos: ReposDep, document_id: str, issue_type: str) -> list[dict[str, Any]]:
    """Issues that describe a relationship, joined to both requirements."""
    await repos.documents.get(document_id)
    issues = await repos.issues.list_for_document(document_id, issue_type=issue_type)
    if not issues:
        return []

    relationships = await repos.relationships.list_for_issues([issue["id"] for issue in issues])
    by_issue = {rel["issue_id"]: rel for rel in relationships}

    requirements = await repos.requirements.list_for_document(document_id)
    by_id = {req["id"]: req for req in requirements}

    findings: list[dict[str, Any]] = []
    for issue in issues:
        relationship = by_issue.get(issue["id"], {})
        metadata = issue.get("metadata") or {}
        requirement_a = by_id.get(relationship.get("requirement_a"))
        requirement_b = by_id.get(relationship.get("requirement_b"))
        findings.append(
            {
                "issue_id": issue["id"],
                "issue_type": issue["issue_type"],
                "severity": issue["severity"],
                "confidence": issue["confidence"],
                "status": issue["status"],
                "description": issue.get("description"),
                "classification": relationship.get("classification") or metadata.get("classification"),
                "conflict_type": relationship.get("conflict_type") or metadata.get("conflict_type"),
                "similarity_score": relationship.get("similarity_score") or metadata.get("similarity_score"),
                "reason": relationship.get("reason"),
                "evidence_a": relationship.get("evidence_a") or issue.get("evidence"),
                "evidence_b": relationship.get("evidence_b"),
                "recommendation": relationship.get("recommendation") or issue.get("suggested_refinement"),
                "requirement_a": requirement_a,
                "requirement_b": requirement_b,
                "code_a": relationship.get("code_a") or metadata.get("code_a"),
                "code_b": relationship.get("code_b") or metadata.get("code_b"),
            }
        )
    return findings


@router.get("/{document_id}/duplicates")
async def list_duplicates(document_id: str, repos: ReposDep) -> dict[str, Any]:
    findings = await _pair_findings(repos, document_id, "duplicate")
    return {"document_id": document_id, "total": len(findings), "duplicates": findings}


@router.get("/{document_id}/contradictions")
async def list_contradictions(document_id: str, repos: ReposDep) -> dict[str, Any]:
    findings = await _pair_findings(repos, document_id, "contradiction")
    return {"document_id": document_id, "total": len(findings), "contradictions": findings}


@router.get("/{document_id}/ambiguities")
async def list_ambiguities(document_id: str, repos: ReposDep) -> dict[str, Any]:
    await repos.documents.get(document_id)
    issues = await repos.issues.list_for_document(document_id, issue_type="ambiguity")
    requirements = await repos.requirements.list_for_document(document_id)
    by_id = {req["id"]: req for req in requirements}
    refinements = await repos.refinements.list_for_document(document_id)
    refinement_by_issue = {ref["issue_id"]: ref for ref in refinements if ref.get("issue_id")}

    findings = []
    for issue in issues:
        requirement = by_id.get(issue.get("requirement_id"))
        metadata = issue.get("metadata") or {}
        refinement = refinement_by_issue.get(issue["id"])
        findings.append(
            {
                "issue_id": issue["id"],
                "requirement": requirement,
                "requirement_code": (requirement or {}).get("requirement_code"),
                "ambiguous_terms": metadata.get("ambiguous_terms", []),
                "evidence": issue.get("evidence"),
                "explanation": issue.get("description"),
                "severity": issue["severity"],
                "confidence": issue["confidence"],
                "status": issue["status"],
                "suggested_refinement": issue.get("suggested_refinement"),
                "refinement_id": (refinement or {}).get("id"),
                "refinement_status": (refinement or {}).get("status"),
            }
        )
    return {"document_id": document_id, "total": len(findings), "ambiguities": findings}


@router.get("/{document_id}/missing-information")
async def list_missing_information(document_id: str, repos: ReposDep) -> dict[str, Any]:
    await repos.documents.get(document_id)
    issues = await repos.issues.list_for_document(document_id, issue_type="missing_information")
    requirements = await repos.requirements.list_for_document(document_id)
    by_id = {req["id"]: req for req in requirements}

    findings = []
    for issue in issues:
        metadata = issue.get("metadata") or {}
        findings.append(
            {
                "issue_id": issue["id"],
                "requirement": by_id.get(issue.get("requirement_id")),
                "missing_information": metadata.get("missing_information", []),
                "suggested_questions": metadata.get("suggested_questions", []),
                "evidence": issue.get("evidence"),
                "explanation": issue.get("description"),
                "severity": issue["severity"],
                "confidence": issue["confidence"],
                "suggested_refinement": issue.get("suggested_refinement"),
            }
        )
    return {"document_id": document_id, "total": len(findings), "missing_information": findings}


@router.get("/{document_id}/dependencies")
async def dependency_graph(document_id: str, repos: ReposDep) -> dict[str, Any]:
    await repos.documents.get(document_id)
    requirements = await repos.requirements.list_for_document(document_id)
    dependencies = await repos.dependencies.list_for_document(document_id)

    connected = {dep["source_requirement"] for dep in dependencies} | {
        dep["target_requirement"] for dep in dependencies
    }

    nodes = [
        {
            "id": req["id"],
            "code": req["requirement_code"],
            "label": req["requirement_code"],
            "original_text": req["original_text"],
            "requirement_type": req["requirement_type"],
            "section": req.get("section"),
            "page_number": req.get("page_number"),
            "connected": req["id"] in connected,
        }
        for req in requirements
    ]
    edges = [
        {
            "id": dep["id"],
            "source": dep["source_requirement"],
            "target": dep["target_requirement"],
            "source_code": dep["source_code"],
            "target_code": dep["target_code"],
            "relationship": dep["relationship"],
            "reason": dep.get("reason"),
            "confidence": dep["confidence"],
        }
        for dep in dependencies
    ]
    return {"document_id": document_id, "nodes": nodes, "edges": edges, "total_edges": len(edges)}


@router.get("/{document_id}/traceability")
async def traceability_matrix(
    document_id: str, traceability: TraceabilityDep
) -> dict[str, Any]:
    rows = await traceability.build_matrix(document_id)
    return {"document_id": document_id, "total": len(rows), "rows": rows}


@router.get("/{document_id}/clean-requirements")
async def clean_requirements(document_id: str, traceability: TraceabilityDep) -> dict[str, Any]:
    return await traceability.build_clean_set(document_id)


@router.get("/{document_id}/export")
async def export_clean_set(
    document_id: str,
    repos: ReposDep,
    traceability: TraceabilityDep,
    format: str = Query(default="json", pattern="^(json|markdown)$"),
) -> Any:
    from fastapi.responses import PlainTextResponse

    document = await repos.documents.get(document_id)
    clean = await traceability.build_clean_set(document_id)

    if format == "json":
        return {"document": document, **clean}

    lines = [
        f"# Clean Requirement Set — {document['filename']}",
        "",
        f"Requirements: {clean['included']} of {clean['total']} "
        f"({clean['merged_duplicates']} merged as duplicates)",
        "",
    ]
    for item in clean["requirements"]:
        if not item["included"]:
            continue
        lines.append(f"## {item['requirement_code']} ({item['requirement_type']})")
        lines.append("")
        lines.append(item["refined_text"])
        if item["refined_text"] != item["original_text"]:
            lines.append("")
            lines.append(f"> Original: {item['original_text']}")
            if item.get("reason"):
                lines.append(f"> Reason: {item['reason']}")
        source = []
        if item.get("section"):
            source.append(str(item["section"]))
        if item.get("page_number"):
            source.append(f"page {item['page_number']}")
        if source:
            lines.append("")
            lines.append(f"_Source: {document['filename']} — {', '.join(source)}_")
        lines.append("")

    return PlainTextResponse("\n".join(lines), media_type="text/markdown")
