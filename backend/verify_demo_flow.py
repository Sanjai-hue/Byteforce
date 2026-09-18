"""Walk the full judge demo flow against a running backend.

    python verify_demo_flow.py [api_base_url]

Every step hits the real API. Nothing is stubbed and no result is assumed.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
SAMPLE = Path(__file__).resolve().parent.parent / "samples" / "ECommerce_SRS_Hackathon_Sample.docx"

passed = 0
failed = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {label}" + (f" — {detail}" if detail else ""))
    else:
        failed += 1
        print(f"  FAIL  {label}" + (f" — {detail}" if detail else ""))


def main() -> int:
    client = httpx.Client(base_url=BASE, timeout=120.0)
    print(f"ReqGuard demo flow against {BASE}\n")

    # 1. health
    print("1. Service health")
    health = client.get("/health")
    check("GET /health returns ok", health.status_code == 200 and health.json()["status"] == "ok")
    status = client.get("/api/system/status").json()
    check("database reachable", status["database"]["reachable"] is True)
    check("embedding model ready", status["embeddings"]["ready"] is True,
          f"{status['embeddings']['model']} ({status['embeddings']['dimensions']}d)")
    check("LLM configured", status["llm"]["configured"] is True, status["llm"]["model"])

    # 2. rejection paths
    print("\n2. Upload validation")
    bad_type = client.post("/api/documents/upload",
                           files={"file": ("notes.exe", b"binary", "application/octet-stream")})
    check("unsupported type rejected", bad_type.status_code == 415)
    empty = client.post("/api/documents/upload", files={"file": ("spec.txt", b"", "text/plain")})
    check("empty file rejected", empty.status_code == 400)
    fake_pdf = client.post("/api/documents/upload",
                           files={"file": ("spec.pdf", b"not a pdf at all", "application/pdf")})
    check("content/extension mismatch rejected", fake_pdf.status_code == 400)
    check("errors carry no stack trace",
          "Traceback" not in fake_pdf.text and "error" in fake_pdf.json())

    # 3. upload
    print("\n3. Upload the sample SRS")
    with SAMPLE.open("rb") as handle:
        upload = client.post("/api/documents/upload", files={"file": (SAMPLE.name, handle)})
    check("upload accepted", upload.status_code == 200, f"HTTP {upload.status_code}")
    if upload.status_code != 200:
        return 1
    document_id = upload.json()["document_id"]
    print(f"        document_id = {document_id}")

    # 4. analyse
    print("\n4. Run the analysis")
    started = client.post(f"/api/documents/{document_id}/analyze")
    check("analysis started", started.status_code == 200)

    seen_stages: list[str] = []
    final = None
    deadline = time.time() + 1500
    while time.time() < deadline:
        current = client.get(f"/api/documents/{document_id}/status").json()
        label = current.get("stage_label")
        if label and label not in seen_stages:
            seen_stages.append(label)
            print(f"        {current['progress']:3d}%  {label}")
        if current["status"] in {"completed", "failed"}:
            final = current
            break
        time.sleep(8)

    check("analysis completed", final is not None and final["status"] == "completed",
          (final or {}).get("error_message") or "")
    if not final or final["status"] != "completed":
        return 1
    check("progress reached 100", final["progress"] == 100)
    check("multiple stages reported", len(seen_stages) >= 5, f"{len(seen_stages)} stages")

    stats = final["stats"]
    print(f"        stats: {stats}")

    # 5. reports
    print("\n5. Reports")
    requirements = client.get(f"/api/documents/{document_id}/requirements").json()
    check("requirements extracted", requirements["total"] > 0, f"{requirements['total']}")
    check("requirement IDs are stable and ordered",
          requirements["requirements"][0]["requirement_code"] == "R001")
    check("original wording preserved",
          all(r["original_text"].strip() for r in requirements["requirements"]))

    ambiguities = client.get(f"/api/documents/{document_id}/ambiguities").json()
    check("ambiguity report populated", ambiguities["total"] > 0, f"{ambiguities['total']}")
    if ambiguities["total"]:
        first = ambiguities["ambiguities"][0]
        check("ambiguity carries evidence", bool(first.get("evidence")))
        check("ambiguity carries a suggested refinement", bool(first.get("suggested_refinement")))
        check("ambiguity traces to a requirement", first.get("requirement") is not None)

    contradictions = client.get(f"/api/documents/{document_id}/contradictions").json()
    check("contradiction report populated", contradictions["total"] > 0, f"{contradictions['total']}")
    if contradictions["total"]:
        first = contradictions["contradictions"][0]
        check("contradiction shows both requirements",
              first.get("requirement_a") is not None and first.get("requirement_b") is not None)
        check("contradiction carries evidence for each side",
              bool(first.get("evidence_a")) and bool(first.get("evidence_b")))

    duplicates = client.get(f"/api/documents/{document_id}/duplicates").json()
    check("duplicate report populated", duplicates["total"] > 0, f"{duplicates['total']}")
    if duplicates["total"]:
        first = duplicates["duplicates"][0]
        check("duplicate shows a similarity score", first.get("similarity_score") is not None,
              str(first.get("similarity_score")))
        check("duplicate shows an AI classification", bool(first.get("classification")))

    missing = client.get(f"/api/documents/{document_id}/missing-information").json()
    check("missing information report reachable", missing["total"] >= 0, f"{missing['total']}")

    graph = client.get(f"/api/documents/{document_id}/dependencies").json()
    check("dependency graph has nodes", len(graph["nodes"]) > 0, f"{len(graph['nodes'])} nodes")
    check("dependency graph has edges", graph["total_edges"] > 0, f"{graph['total_edges']} edges")
    if graph["edges"]:
        check("edges name both endpoints",
              all(e["source_code"] and e["target_code"] for e in graph["edges"]))

    # 6. traceability
    print("\n6. Traceability")
    matrix = client.get(f"/api/documents/{document_id}/traceability").json()
    check("matrix covers every requirement", matrix["total"] == requirements["total"])
    flagged = [row for row in matrix["rows"] if row["issues"]]
    check("matrix links findings to requirements", len(flagged) > 0, f"{len(flagged)} flagged rows")
    check("every row names a source", all(row["source"] for row in matrix["rows"]))

    issues = client.get(f"/api/documents/{document_id}/issues").json()
    traced = [i for i in issues["issues"] if i.get("requirement_id")]
    check("every issue traces to a requirement", len(traced) == issues["total"],
          f"{len(traced)}/{issues['total']}")

    # 7. filters
    print("\n7. Issue filters")
    only_ambiguity = client.get(f"/api/documents/{document_id}/issues?type=ambiguity").json()
    check("filter by type works",
          all(i["issue_type"] == "ambiguity" for i in only_ambiguity["issues"]))
    high_conf = client.get(f"/api/documents/{document_id}/issues?min_confidence=0.9").json()
    check("filter by confidence works",
          all(i["confidence"] >= 0.9 for i in high_conf["issues"]))

    # 8. refinement round trip
    print("\n8. Refinement accept / edit / reject")
    clean_before = client.get(f"/api/documents/{document_id}/clean-requirements").json()
    target = next((r for r in clean_before["requirements"] if r.get("refinement_id")), None)
    check("a refinement is available to action", target is not None)
    if target:
        refinement_id = target["refinement_id"]
        original_text = target["original_text"]

        accepted = client.post(f"/api/refinements/{refinement_id}/accept")
        check("accept succeeds", accepted.status_code == 200)

        clean_after = client.get(f"/api/documents/{document_id}/clean-requirements").json()
        updated = next(r for r in clean_after["requirements"]
                       if r["requirement_code"] == target["requirement_code"])
        check("accepted refinement changes the requirement text",
              updated["refined_text"] != original_text)
        check("original text is still retained", updated["original_text"] == original_text)
        check("status marked refined", updated["status"] == "refined")

        edited = client.post(f"/api/refinements/{refinement_id}/edit",
                             json={"edited_text": "The system shall respond within 1500 ms."})
        check("edit succeeds", edited.status_code == 200)
        clean_edit = client.get(f"/api/documents/{document_id}/clean-requirements").json()
        updated_edit = next(r for r in clean_edit["requirements"]
                            if r["requirement_code"] == target["requirement_code"])
        check("edited text is used", "1500 ms" in updated_edit["refined_text"])
        check("original still retained after edit", updated_edit["original_text"] == original_text)

        rejected = client.post(f"/api/refinements/{refinement_id}/reject")
        check("reject succeeds", rejected.status_code == 200)
        clean_reject = client.get(f"/api/documents/{document_id}/clean-requirements").json()
        updated_reject = next(r for r in clean_reject["requirements"]
                              if r["requirement_code"] == target["requirement_code"])
        check("rejected refinement restores the original",
              updated_reject["refined_text"] == original_text)

    # 9. export
    print("\n9. Export")
    export_json = client.get(f"/api/documents/{document_id}/export?format=json")
    check("JSON export works", export_json.status_code == 200 and "requirements" in export_json.json())
    export_md = client.get(f"/api/documents/{document_id}/export?format=markdown")
    check("Markdown export works",
          export_md.status_code == 200 and "# Clean Requirement Set" in export_md.text,
          f"{len(export_md.text)} chars")

    # 10. not found
    print("\n10. Unknown resources")
    missing_doc = client.get("/api/documents/00000000-0000-0000-0000-000000000000/requirements")
    check("unknown document returns 404", missing_doc.status_code == 404)

    client.close()
    print("\n" + "=" * 62)
    print(f"  {passed} passed, {failed} failed")
    print(f"  document_id for the UI: {document_id}")
    print("=" * 62)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
