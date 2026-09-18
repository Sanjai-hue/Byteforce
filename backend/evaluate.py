"""Score the pipeline against the labelled sample SRS.

Run after an analysis completes:

    python evaluate.py <document_id>

Ground-truth labels live in samples/evaluation_dataset.json. They are keyed by the
printed labels in the sample document (R001...), which the pipeline re-numbers in
document order, so labels are mapped onto real requirements by matching text.

Every number printed here is computed from the actual run. Nothing is hard-coded,
and the application itself never reads this file.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.config import get_settings  # noqa: E402
from app.database.client import InsForgeClient  # noqa: E402
from app.database.repositories import Repositories  # noqa: E402

SAMPLES = Path(__file__).resolve().parent.parent / "samples"

# Text fragments that uniquely identify each labelled requirement in the sample.
LABEL_PROBES: dict[str, str] = {
    "R001": "create an account using an email address",
    "R002": "log in using their email address",
    "R003": "mobile number and password only",
    "R004": "reset a forgotten password",
    "R005": "five consecutive failed login",
    "R006": "shall send notifications",
    "R007": "update their profile information",
    "R011": "search results shall be returned quickly",
    "R017": "register for an account",
    "R018": "complete a purchase using the checkout",
    "R019": "guest checkout is not allowed",
    "R020": "check out without creating an account",
    "R014": "add products to a shopping cart",
    "R024": "track the delivery status",
    "R026": "respond quickly to user requests",
    "R028": "refunds shall be processed in a reasonable",
    "R031": "appropriate level of access control",
    "R036": "secure against common web vulnerabilities",
    "R037": "multi-factor authentication",
    "R038": "only a username and password",
    "R041": "should be fast during normal usage",
    "R044": "shall be easy to use",
    "R045": "scale to handle large traffic",
    "R047": "allow administrators to export reports",
}


def prf(true_positive: int, false_positive: int, false_negative: int) -> tuple[float, float, float]:
    precision = true_positive / (true_positive + false_positive) if (true_positive + false_positive) else 0.0
    recall = true_positive / (true_positive + false_negative) if (true_positive + false_negative) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return precision, recall, f1


def line(name: str, tp: int, fp: int, fn: int) -> str:
    p, r, f = prf(tp, fp, fn)
    return f"{name:<22} TP={tp:<3} FP={fp:<3} FN={fn:<3} P={p:.2f} R={r:.2f} F1={f:.2f}"


async def main(document_id: str) -> int:
    truth = json.loads((SAMPLES / "evaluation_dataset.json").read_text(encoding="utf-8"))

    settings = get_settings()
    db = InsForgeClient(settings)
    await db.connect()
    repos = Repositories(db)

    requirements = await repos.requirements.list_for_document(document_id)
    if not requirements:
        print("No requirements found for that document id.")
        await db.close()
        return 1

    # Map each ground-truth label onto the code the pipeline actually assigned.
    label_to_code: dict[str, str] = {}
    for label, probe in LABEL_PROBES.items():
        for requirement in requirements:
            if probe.lower() in requirement["original_text"].lower():
                label_to_code[label] = requirement["requirement_code"]
                break

    missing = sorted(set(LABEL_PROBES) - set(label_to_code))
    if missing:
        print(f"note: {len(missing)} labelled requirement(s) were not extracted: {', '.join(missing)}")

    issues = await repos.issues.list_for_document(document_id)
    dependencies = await repos.dependencies.list_for_document(document_id)
    await db.close()

    def pair_set(issue_type: str, *, min_confidence: float = 0.0) -> set[frozenset[str]]:
        found = set()
        for issue in issues:
            if issue["issue_type"] != issue_type:
                continue
            if (issue.get("confidence") or 0) < min_confidence:
                continue
            metadata = issue.get("metadata") or {}
            a, b = metadata.get("code_a"), metadata.get("code_b")
            if a and b:
                found.add(frozenset({a, b}))
        return found

    print("=" * 78)
    print(f"ReqGuard AI — evaluation against labelled sample")
    print(f"document: {document_id}")
    print(f"requirements extracted: {len(requirements)}  (labelled set maps {len(label_to_code)})")
    print("=" * 78)

    # --- extraction --------------------------------------------------------
    extraction_tp = len(label_to_code)
    extraction_fn = len(missing)
    print(line("Requirement extract.", extraction_tp, 0, extraction_fn))

    # --- duplicates --------------------------------------------------------
    expected_dupes = {
        frozenset({label_to_code[d["a"]], label_to_code[d["b"]]})
        for d in truth["duplicates"]
        if d["a"] in label_to_code and d["b"] in label_to_code
    }
    found_dupes = pair_set("duplicate")
    tp = len(expected_dupes & found_dupes)
    print(line("Duplicate detection", tp, len(found_dupes - expected_dupes), len(expected_dupes - found_dupes)))

    # --- contradictions ----------------------------------------------------
    expected_contra = {
        frozenset({label_to_code[c["a"]], label_to_code[c["b"]]})
        for c in truth["contradictions"]
        if c["a"] in label_to_code and c["b"] in label_to_code
    }
    for floor in (0.0, 0.75, 0.9):
        found = pair_set("contradiction", min_confidence=floor)
        tp = len(expected_contra & found)
        label = "Contradiction det." if floor == 0.0 else f"  (confidence>={floor})"
        print(line(label, tp, len(found - expected_contra), len(expected_contra - found)))

    # --- ambiguity ---------------------------------------------------------
    expected_ambig = {label_to_code[a] for a in truth["ambiguities"] if a in label_to_code}
    found_ambig = {
        (issue.get("metadata") or {}).get("requirement_code")
        for issue in issues
        if issue["issue_type"] == "ambiguity"
    } - {None}
    tp = len(expected_ambig & found_ambig)
    print(line("Ambiguity detection", tp, len(found_ambig - expected_ambig), len(expected_ambig - found_ambig)))

    # --- missing information ------------------------------------------------
    expected_missing = {label_to_code[m] for m in truth["missing_information"] if m in label_to_code}
    found_missing = {
        (issue.get("metadata") or {}).get("requirement_code")
        for issue in issues
        if issue["issue_type"] == "missing_information"
    } - {None}
    tp = len(expected_missing & found_missing)
    print(line("Missing information", tp, len(found_missing - expected_missing), len(expected_missing - found_missing)))

    # --- dependencies -------------------------------------------------------
    expected_deps = {
        frozenset({label_to_code[d["source"]], label_to_code[d["target"]]})
        for d in truth["dependencies"]
        if d["source"] in label_to_code and d["target"] in label_to_code
    }
    found_deps = {frozenset({d["source_code"], d["target_code"]}) for d in dependencies}
    tp = len(expected_deps & found_deps)
    print(line("Dependency (undir.)", tp, len(found_deps - expected_deps), len(expected_deps - found_deps)))

    # --- traceability --------------------------------------------------------
    traceable = sum(1 for issue in issues if issue.get("requirement_id"))
    coverage = (traceable / len(issues) * 100) if issues else 100.0
    print("-" * 78)
    print(f"Traceability: {traceable}/{len(issues)} issues carry a source requirement id ({coverage:.1f}%)")
    print("=" * 78)
    print("Precision/recall above are measured on this run only, against a small")
    print("labelled sample. They are not a general accuracy claim.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python evaluate.py <document_id>")
        raise SystemExit(2)
    raise SystemExit(asyncio.run(main(sys.argv[1])))
