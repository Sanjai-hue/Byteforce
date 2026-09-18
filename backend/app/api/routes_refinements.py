"""Accept, reject or edit a suggested refinement.

None of these touch the requirement row. The original text always stays as it was
read from the document.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import ReposDep
from app.schemas.common import IssueStatus, RefinementStatus

router = APIRouter(prefix="/api/refinements", tags=["refinements"])


class EditRefinementRequest(BaseModel):
    edited_text: str = Field(min_length=3, max_length=4000)


async def _sync_issue_status(repos: ReposDep, refinement: dict[str, Any], status: str) -> None:
    issue_id = refinement.get("issue_id")
    if issue_id:
        await repos.issues.set_status(issue_id, status)


@router.post("/{refinement_id}/accept")
async def accept_refinement(refinement_id: str, repos: ReposDep) -> dict[str, Any]:
    updated = await repos.refinements.set_status(refinement_id, RefinementStatus.ACCEPTED.value)
    await _sync_issue_status(repos, updated, IssueStatus.ACCEPTED.value)
    return {"refinement": updated}


@router.post("/{refinement_id}/reject")
async def reject_refinement(refinement_id: str, repos: ReposDep) -> dict[str, Any]:
    updated = await repos.refinements.set_status(refinement_id, RefinementStatus.REJECTED.value)
    await _sync_issue_status(repos, updated, IssueStatus.REJECTED.value)
    return {"refinement": updated}


@router.post("/{refinement_id}/edit")
async def edit_refinement(
    refinement_id: str, payload: EditRefinementRequest, repos: ReposDep
) -> dict[str, Any]:
    updated = await repos.refinements.set_status(
        refinement_id, RefinementStatus.EDITED.value, edited_text=payload.edited_text.strip()
    )
    await _sync_issue_status(repos, updated, IssueStatus.ACCEPTED.value)
    return {"refinement": updated}


@router.get("/{refinement_id}")
async def get_refinement(refinement_id: str, repos: ReposDep) -> dict[str, Any]:
    return {"refinement": await repos.refinements.get(refinement_id)}
