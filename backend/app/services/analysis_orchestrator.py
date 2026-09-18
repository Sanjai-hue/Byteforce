"""The analysis pipeline.

Runs the stages in order, reporting progress after each one. A failure in any
stage marks the run failed with the reason — partial or invented results are
never written.
"""

from __future__ import annotations

import logging
from typing import Any

from app.ai.ai_service import AIService
from app.core.config import Settings
from app.core.errors import ReqGuardError
from app.database.repositories import Repositories
from app.document_processing.parser import parse_document
from app.schemas.common import STAGE_LABELS, STAGE_PROGRESS, AnalysisStage, DocumentStatus
from app.services.ambiguity_service import AmbiguityService, MissingInfoService
from app.services.contradiction_service import ContradictionService
from app.services.dependency_service import DependencyService
from app.services.duplicate_service import DuplicateService
from app.services.embedding_service import EmbeddingService
from app.services.refinement_service import RefinementService
from app.services.requirement_service import RequirementRecord, RequirementService

logger = logging.getLogger("reqguard.orchestrator")


class AnalysisOrchestrator:
    def __init__(
        self,
        repos: Repositories,
        ai: AIService,
        embeddings: EmbeddingService,
        settings: Settings,
    ) -> None:
        self._repos = repos
        self._ai = ai
        self._embeddings = embeddings
        self._settings = settings

        self._requirements = RequirementService(repos, ai, embeddings, settings)
        self._duplicates = DuplicateService(ai, embeddings, settings)
        self._contradictions = ContradictionService(ai, embeddings, settings)
        self._ambiguity = AmbiguityService(ai, settings)
        self._missing_info = MissingInfoService(ai, settings)
        self._dependencies = DependencyService(ai, settings)
        self._refinements = RefinementService(ai, settings)

    async def analyze_document(self, document_id: str, file_bytes: bytes) -> dict[str, Any]:
        document = await self._repos.documents.get(document_id)
        run = await self._repos.runs.create(document_id)
        run_id = run["id"]

        try:
            # Re-running replaces prior output rather than appending to it.
            await self._repos.runs.clear_for_document(document_id)

            # -- parse ------------------------------------------------------
            await self._progress(run_id, AnalysisStage.PARSING, DocumentStatus.EXTRACTING)
            parsed = parse_document(file_bytes, document["file_type"], document["filename"])
            logger.info(
                "parsed %s: %s block(s), %s page(s)",
                document["filename"],
                len(parsed.blocks),
                parsed.page_count,
            )

            # -- extract ----------------------------------------------------
            await self._progress(run_id, AnalysisStage.EXTRACTING, DocumentStatus.EXTRACTING)
            records = await self._requirements.extract(parsed)
            if not records:
                raise ReqGuardError(
                    "No software requirements were found in this document. "
                    "Check that it is a requirements specification."
                )

            # -- embed ------------------------------------------------------
            await self._progress(run_id, AnalysisStage.EMBEDDING, DocumentStatus.ANALYZING)
            self._requirements.embed(records)
            records = await self._requirements.persist(document_id, records)

            # -- duplicates -------------------------------------------------
            await self._progress(run_id, AnalysisStage.DUPLICATES, DocumentStatus.ANALYZING)
            duplicate_findings = await self._duplicates.run(records)
            duplicate_issues, duplicate_links = DuplicateService.to_rows(
                document_id, duplicate_findings
            )

            # -- ambiguity --------------------------------------------------
            await self._progress(run_id, AnalysisStage.AMBIGUITIES, DocumentStatus.ANALYZING)
            ambiguity_issues = await self._ambiguity.run(records)
            ambiguity_rows = AmbiguityService.to_rows(document_id, ambiguity_issues)

            # -- contradictions ---------------------------------------------
            await self._progress(run_id, AnalysisStage.CONTRADICTIONS, DocumentStatus.ANALYZING)
            contradiction_findings = await self._contradictions.run(records)
            contradiction_issues, contradiction_links = ContradictionService.to_rows(
                document_id, contradiction_findings
            )

            # -- dependencies -----------------------------------------------
            await self._progress(run_id, AnalysisStage.DEPENDENCIES, DocumentStatus.ANALYZING)
            dependency_findings = await self._dependencies.run(records)
            dependency_rows = DependencyService.to_rows(document_id, dependency_findings)

            # -- missing information ----------------------------------------
            await self._progress(run_id, AnalysisStage.MISSING_INFO, DocumentStatus.ANALYZING)
            missing_issues = await self._missing_info.run(records)
            missing_rows = MissingInfoService.to_rows(document_id, missing_issues)

            # -- persist issues ---------------------------------------------
            created_ambiguity = await self._repos.issues.bulk_create(ambiguity_rows)
            created_missing = await self._repos.issues.bulk_create(missing_rows)
            created_duplicates = await self._repos.issues.bulk_create(duplicate_issues)
            created_contradictions = await self._repos.issues.bulk_create(contradiction_issues)

            await self._link_relationships(created_duplicates, duplicate_links)
            await self._link_relationships(created_contradictions, contradiction_links)
            await self._repos.dependencies.bulk_create(dependency_rows)

            # -- refinements -------------------------------------------------
            await self._progress(run_id, AnalysisStage.REFINEMENTS, DocumentStatus.ANALYZING)
            problem_map = self._build_problem_map(
                records,
                ambiguity_issues,
                missing_issues,
                contradiction_findings,
                created_ambiguity,
                created_missing,
            )
            proposals = await self._refinements.run(problem_map)
            await self._repos.refinements.bulk_create(
                RefinementService.to_rows(document_id, proposals)
            )

            # -- done ---------------------------------------------------------
            await self._progress(run_id, AnalysisStage.TRACEABILITY, DocumentStatus.ANALYZING)
            stats = {
                "requirements": len(records),
                "ambiguities": len(ambiguity_rows),
                "contradictions": len(contradiction_issues),
                "duplicates": len(duplicate_issues),
                "dependencies": len(dependency_rows),
                "missing_information": len(missing_rows),
                "refinements": len(proposals),
                "llm_model": self._ai.model_name,
                "embedding_model": self._settings.embedding_model_name,
            }
            await self._repos.runs.complete(run_id, stats)
            await self._repos.documents.set_status(document_id, DocumentStatus.COMPLETED.value)
            logger.info("analysis complete for %s: %s", document_id, stats)
            return stats

        except ReqGuardError as exc:
            logger.error(
                "analysis failed for %s: %s (detail=%s)", document_id, exc.message, exc.detail
            )
            await self._repos.runs.fail(run_id, exc.message)
            await self._repos.documents.set_status(document_id, DocumentStatus.FAILED.value)
            raise
        except Exception as exc:  # noqa: BLE001 - last resort, always recorded
            logger.exception("analysis crashed for %s", document_id)
            await self._repos.runs.fail(run_id, f"Unexpected error: {exc}")
            await self._repos.documents.set_status(document_id, DocumentStatus.FAILED.value)
            raise

    # -- helpers ------------------------------------------------------------
    async def _progress(self, run_id: str, stage: AnalysisStage, doc_status: DocumentStatus) -> None:
        await self._repos.runs.update_progress(
            run_id,
            status=doc_status.value if doc_status != DocumentStatus.COMPLETED else "completed",
            stage=stage.value,
            progress=STAGE_PROGRESS[stage],
        )
        logger.info("stage %s (%s%%)", STAGE_LABELS[stage], STAGE_PROGRESS[stage])

    async def _link_relationships(
        self, created_issues: list[dict], payloads: list[dict]
    ) -> None:
        """Attach each pair payload to the issue row that was just created."""
        if not created_issues or not payloads:
            return
        rows = []
        for issue, payload in zip(created_issues, payloads, strict=False):
            row = dict(payload)
            row["issue_id"] = issue["id"]
            rows.append(row)
        await self._repos.relationships.bulk_create(rows)

    @staticmethod
    def _build_problem_map(
        records: list[RequirementRecord],
        ambiguity_issues,
        missing_issues,
        contradiction_findings,
        created_ambiguity: list[dict],
        created_missing: list[dict],
    ) -> dict[str, tuple[RequirementRecord, list[str], str | None]]:
        """Collect every requirement that has a problem worth rewriting."""
        problems: dict[str, tuple[RequirementRecord, list[str], str | None]] = {}

        def add(record: RequirementRecord, description: str, issue_id: str | None) -> None:
            existing = problems.get(record.code)
            if existing:
                existing[1].append(description)
            else:
                problems[record.code] = (record, [description], issue_id)

        for index, issue in enumerate(ambiguity_issues):
            issue_id = created_ambiguity[index]["id"] if index < len(created_ambiguity) else None
            terms = ", ".join(issue.finding.ambiguous_terms) or "vague wording"
            add(issue.record, f"Ambiguous ({terms}): {issue.finding.explanation}", issue_id)

        for index, issue in enumerate(missing_issues):
            issue_id = created_missing[index]["id"] if index < len(created_missing) else None
            missing = ", ".join(issue.finding.missing_information) or "unspecified details"
            add(issue.record, f"Missing information ({missing})", issue_id)

        for finding in contradiction_findings:
            add(
                finding.record_a,
                f"Conflicts with {finding.record_b.code}: {finding.verdict.explanation}",
                None,
            )

        return problems
