"""Parsing and upload validation: PDF, DOCX, TXT, and the failure paths."""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.core.errors import (
    DocumentParseError,
    EmptyDocumentError,
    FileTooLarge,
    UnsupportedFileType,
    ValidationFailure,
)
from app.document_processing.parser import chunk_blocks, parse_document
from app.document_processing.validators import sanitize_filename, validate_upload


# --- parsing ---------------------------------------------------------------
def test_parses_txt(sample_txt: bytes) -> None:
    parsed = parse_document(sample_txt, "txt", "sample.txt")
    assert len(parsed.blocks) > 10
    assert "shall allow" in parsed.full_text.lower()


def test_parses_docx(sample_docx: bytes) -> None:
    parsed = parse_document(sample_docx, "docx", "sample.docx")
    assert len(parsed.blocks) > 10
    assert any(block.section for block in parsed.blocks)


def test_parses_pdf_with_page_numbers(sample_pdf: bytes) -> None:
    parsed = parse_document(sample_pdf, "pdf", "sample.pdf")
    assert parsed.page_count >= 1
    pages = {block.page_number for block in parsed.blocks if block.page_number}
    assert pages, "PDF blocks must carry page numbers for traceability"


def test_pdf_and_docx_yield_equivalent_text(sample_pdf: bytes, sample_docx: bytes) -> None:
    pdf = parse_document(sample_pdf, "pdf", "s.pdf").full_text.lower()
    docx = parse_document(sample_docx, "docx", "s.docx").full_text.lower()
    for probe in ("guest checkout is not allowed", "multi-factor authentication"):
        assert probe in pdf and probe in docx


def test_detects_sections(sample_txt: bytes) -> None:
    parsed = parse_document(sample_txt, "txt", "sample.txt")
    sections = {block.section for block in parsed.blocks if block.section}
    assert len(sections) >= 5


def test_rejects_unsupported_type() -> None:
    with pytest.raises(UnsupportedFileType):
        parse_document(b"data", "xlsx", "book.xlsx")


def test_rejects_empty_document() -> None:
    with pytest.raises(EmptyDocumentError):
        parse_document(b"   \n  ", "txt", "empty.txt")


def test_rejects_corrupt_pdf() -> None:
    with pytest.raises((DocumentParseError, EmptyDocumentError)):
        parse_document(b"%PDF-1.4\nnot really a pdf", "pdf", "broken.pdf")


def test_rejects_corrupt_docx() -> None:
    with pytest.raises(DocumentParseError):
        parse_document(b"PK\x03\x04garbage-not-a-docx", "docx", "broken.docx")


def test_chunking_keeps_blocks_whole(sample_txt: bytes) -> None:
    parsed = parse_document(sample_txt, "txt", "sample.txt")
    chunks = chunk_blocks(parsed.blocks, 500)
    assert len(chunks) > 1
    rejoined = " ".join(text for text, _, _ in chunks)
    assert "guest checkout is not allowed" in rejoined.lower()


# --- validation ------------------------------------------------------------
def test_sanitize_filename_strips_paths() -> None:
    assert sanitize_filename("../../etc/passwd") == "etcpasswd" or "passwd" in sanitize_filename(
        "../../etc/passwd"
    )
    assert "/" not in sanitize_filename("a/b/c.txt")
    assert "\\" not in sanitize_filename(r"C:\temp\spec.docx")


def test_validate_rejects_bad_extension() -> None:
    settings = get_settings()
    with pytest.raises(UnsupportedFileType):
        validate_upload(b"hello", "notes.exe", settings)


def test_validate_rejects_empty_file() -> None:
    settings = get_settings()
    with pytest.raises(ValidationFailure):
        validate_upload(b"", "spec.txt", settings)


def test_validate_rejects_oversize_file() -> None:
    settings = get_settings()
    oversized = b"x" * (settings.max_upload_bytes + 1)
    with pytest.raises(FileTooLarge):
        validate_upload(oversized, "spec.txt", settings)


def test_validate_rejects_content_type_mismatch() -> None:
    """A .pdf that is not really a PDF must be refused."""
    settings = get_settings()
    with pytest.raises(ValidationFailure):
        validate_upload(b"just plain text", "spec.pdf", settings)


def test_validate_accepts_real_docx(sample_docx: bytes) -> None:
    settings = get_settings()
    name, file_type = validate_upload(sample_docx, "My Spec v2.docx", settings)
    assert file_type == "docx"
    assert name.endswith(".docx")
