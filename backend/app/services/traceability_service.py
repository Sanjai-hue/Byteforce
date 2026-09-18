"""Traceability matrix and the clean requirement set.

Both are derived at read time from stored rows, so they always reflect the
current accept/reject state of every refinement. Every issue carries the
requirement id it came from, so no finding can appear without a source.
"""

from __future__ import annotations

import logging
from typing import Any

from app.database.repositories import Repositories
from app.schemas.common import IssueType, RefinementStatus

logger = logging.getLogger("reqguard.traceability")

_ISSUE_LABEL = {
    IssueType.AMBIGUITY.value: "Ambiguity",
    IssueType.CONTRADICTION.value: "Contradiction",
    IssueType.DUPLICATE.value: "Duplicate",
    IssueType.MISSING_INFORMATION.value: "Missing information",
    IssueType.DEPENDENCY.value: "Dependency",
}


class TraceabilityService:
    def __init__(self, repos: Repositories) -> None:
        self._repos = repos

    async def build_matrix(self, document_id: str) -> list[dict[str, Any]]:
        document = await self._repos.documents.get(document_id)
        requirements = await self._repos.requirements.list_for_document(document_id)
        issues = await self._repos.issues.list_for_document(document_id)
        refinements = await self._repos.refinements.list_for_document(document_id)

        issues_by_requirement: dict[str, list[dict]] = {}
        for issue in issues:
            requirement_id = issue.get("requirement_id")
            if requirement_id:
                issues_by_requirement.setdefault(requirement_id, []).append(issue)

        refinements_by_requirement: dict[str, dict] = {}
        for refinement in refinements:
            requirement_id = refinement.get("requirement_id")
            if requirement_id and requirement_id not in refinements_by_requirement:
                refinements_by_requirement[requirement_id] = refinement

        filename = document.get("filename", "document")
        rows: list[dict[str, Any]] = []

        for requirement in requirements:
            requirement_id = requirement["id"]
            related = issues_by_requirement.get(requirement_id, [])
            refinement = refinements_by_requirement.get(requirement_id)

            page = requirement.get("page_number")
            source = f"{filename} / Page {page}" if page else filename
            if requirement.get("section"):
                source = f"{source} / {requirement['section']}"

            rows.append(
                {
                    "requirement_id": requirement_id,
                    "requirement_code": requirement["requirement_code"],
                    "original_text": requirement["original_text"],
                    "requirement_type": requirement["requirement_type"],
                    "section": requirement.get("section"),
                    "page_number": page,
                    "source": source,
                    "issues": [
                        {
                            "id": issue["id"],
                            "type": issue["issue_type"],
                            "label": _ISSUE_LABEL.get(issue["issue_type"], issue["issue_type"]),
                            "severity": issue["severity"],
                            "confidence": issue["confidence"],
                            "evidence": issue.get("evidence") or "",
                            "description": issue.get("description") or "",
                        }
                        for issue in related
                    ],
                    "evidence": " | ".join(
                        issue.get("evidence") or "" for issue in related if issue.get("evidence")
                    ),
                    "suggested_refinement": (refinement or {}).get("suggested_text"),
                    "refinement_id": (refinement or {}).get("id"),
                    "refinement_status": (refinement or {}).get("status"),
                    "status": _row_status(related, refinement),
                }
            )
        return rows

    async def build_clean_set(self, document_id: str) -> dict[str, Any]:
        """The cleaned requirement set.

        Accepted (or edited) refinements replace the text; the original is always
        retained alongside. Confirmed duplicates are marked as merged rather than
        deleted, and unresolved contradictions are flagged explicitly.
        """
        requirements = await self._repos.requirements.list_for_document(document_id)
        issues = await self._repos.issues.list_for_document(document_id)
        refinements = await self._repos.refinements.list_for_document(document_id)

        refinement_by_requirement: dict[str, dict] = {}
        for refinement in refinements:
            requirement_id = refinement.get("requirement_id")
            if not requirement_id:
                continue
            current = refinement_by_requirement.get(requirement_id)
            # Prefer an actioned refinement over a still-pending one.
            if current is None or (
                current.get("status") == RefinementStatus.PENDING.value
                and refinement.get("status") != RefinementStatus.PENDING.value
            ):
                refinement_by_requirement[requirement_id] = refinement

        duplicate_codes: set[str] = set()
        contradiction_codes: set[str] = set()
        for issue in issues:
            metadata = issue.get("metadata") or {}
            code_b = metadata.get("code_b")
            if issue["issue_type"] == IssueType.DUPLICATE.value:
                if metadata.get("classification") == "duplicate" and code_b:
                    # The second requirement of a confirmed duplicate folds into the first.
                    duplicate_codes.add(code_b)
            elif issue["issue_type"] == IssueType.CONTRADICTION.value:
                if issue.get("status") not in {"resolved", "accepted"}:
                    for key in ("code_a", "code_b"):
                        if metadata.get(key):
                            contradiction_codes.add(metadata[key])

        items: list[dict[str, Any]] = []
        for requirement in requirements:
            code = requirement["requirement_code"]
            refinement = refinement_by_requirement.get(requirement["id"])
            status = "unchanged"
            final_text = requirement["original_text"]
            reason = None

            if refinement:
                refinement_status = refinement.get("status")
                if refinement_status == RefinementStatus.ACCEPTED.value:
                    final_text = refinement["suggested_text"]
                    status = "refined"
                    reason = refinement.get("reason")
                elif refinement_status == RefinementStatus.EDITED.value:
                    final_text = refinement.get("edited_text") or refinement["suggested_text"]
                    status = "refined"
                    reason = refinement.get("reason")
                elif refinement_status == RefinementStatus.PENDING.value:
                    status = "needs_review"
                    reason = refinement.get("reason")

            if code in duplicate_codes:
                status = "merged_duplicate"
                reason = "Confirmed duplicate of an earlier requirement; retained for traceability."
            elif code in contradiction_codes and status != "refined":
                status = "contradiction_unresolved"
                reason = reason or "Conflicts with another requirement; resolve before implementation."

            items.append(
                {
                    "original_requirement_id": requirement["id"],
                    "requirement_code": code,
                    "original_text": requirement["original_text"],
                    "refined_text": final_text,
                    "requirement_type": requirement["requirement_type"],
                    "section": requirement.get("section"),
                    "page_number": requirement.get("page_number"),
                    "reason": reason,
                    "status": status,
                    "refinement_id": (refinement or {}).get("id"),
                    # The proposal itself, so a reviewer can read it before
                    # accepting. refined_text is only what is currently in force.
                    "proposed_text": (refinement or {}).get("edited_text")
                    or (refinement or {}).get("suggested_text"),
                    "refinement_status": (refinement or {}).get("status"),
                    "included": status != "merged_duplicate",
                }
            )

        return {
            "document_id": document_id,
            "total": len(items),
            "included": sum(1 for item in items if item["included"]),
            "merged_duplicates": sum(1 for item in items if item["status"] == "merged_duplicate"),
            "unresolved_contradictions": sum(
                1 for item in items if item["status"] == "contradiction_unresolved"
            ),
            "requirements": items,
        }


def _row_status(issues: list[dict], refinement: dict | None) -> str:
    if not issues:
        return "OK"
    if refinement and refinement.get("status") in {
        RefinementStatus.ACCEPTED.value,
        RefinementStatus.EDITED.value,
    }:
        return "Refined"
    if any(issue["severity"] == "critical" for issue in issues):
        return "Critical"
    return "Needs Review"
